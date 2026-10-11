# -*- coding: utf-8 -*-
"""Unit tests for the daemon data layer (schema, ini import, settings, dedup)."""

import configparser
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import db as bcd  # noqa: E402


class ProfileResetTests(unittest.TestCase):
    """D3.4: the additive profile_reset_at migration and reset_profile."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = bcd.Database(path=self.root / "test.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def task_columns(self, conn):
        return {r["name"] for r in
                conn.execute("PRAGMA table_info(Task)").fetchall()}

    def test_fresh_db_has_the_profile_reset_column(self):
        self.assertIn("profile_reset_at", self.task_columns(self.db.conn))

    def test_migration_adds_the_column_to_a_pre_existing_db(self):
        # A DB file created with the pre-D3.4 Task schema (no
        # profile_reset_at column).
        legacy = self.root / "legacy.db"
        conn = sqlite3.connect(legacy)
        conn.execute(
            """CREATE TABLE Task (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   service TEXT NOT NULL, user TEXT NOT NULL,
                   recipe_file TEXT, enabled INTEGER NOT NULL DEFAULT 0,
                   cron TEXT, last_run TEXT, next_run TEXT,
                   status TEXT NOT NULL DEFAULT 'idle', profile_dir TEXT,
                   created_at TEXT, updated_at TEXT)""")
        conn.execute("INSERT INTO Task (service, user) VALUES ('svc', 'u1')")
        conn.commit()
        conn.close()

        db2 = bcd.Database(path=legacy)
        try:
            self.assertIn("profile_reset_at", self.task_columns(db2.conn))
            # The migration is additive: the pre-existing row survives
            # with a NULL reset timestamp.
            row = db2.get_task(1)
            self.assertEqual(row["service"], "svc")
            self.assertIsNone(row["profile_reset_at"])
        finally:
            db2.close()

    def test_migration_is_idempotent(self):
        # A second open of the same file re-runs the PRAGMA check without
        # error and without duplicating the column.
        bcd.Database(path=self.root / "again.db")
        db2 = bcd.Database(path=self.root / "again.db")
        try:
            cols = [r["name"] for r in
                    db2.conn.execute("PRAGMA table_info(Task)").fetchall()]
            self.assertEqual(cols.count("profile_reset_at"), 1)
        finally:
            db2.close()

    def test_reset_profile_deletes_the_dir_and_sets_the_timestamp(self):
        profile = self.root / "profiles" / "svc_u1"
        profile.mkdir(parents=True)
        (profile / "marker.txt").write_text("warm profile", encoding="utf-8")
        tid = self.db.create_task("svc", "u1", profile_dir=str(profile))

        ok, err = self.db.reset_profile(tid)
        self.assertTrue(ok, err)
        self.assertIsNone(err)
        self.assertFalse(profile.exists())
        self.assertIsNotNone(self.db.get_task(tid)["profile_reset_at"])

    def test_reset_profile_without_a_dir_still_records_the_reset(self):
        # No profile_dir at all (a task that never ran): the reset is
        # recorded so the dashboard can show it.
        tid = self.db.create_task("svc", "u2")
        ok, err = self.db.reset_profile(tid)
        self.assertTrue(ok, err)
        self.assertIsNotNone(self.db.get_task(tid)["profile_reset_at"])

    def test_reset_profile_rejected_for_a_running_or_waiting_task(self):
        tid = self.db.create_task("svc", "u3")
        for status in ("running", "waiting"):
            self.db.set_task_status(tid, status)
            ok, err = self.db.reset_profile(tid)
            self.assertFalse(ok, f"{status} should be rejected")
            self.assertIn(status, err)
        self.assertIsNone(self.db.get_task(tid)["profile_reset_at"])

    def test_reset_profile_of_an_unknown_task_is_rejected(self):
        ok, err = self.db.reset_profile(999)
        self.assertFalse(ok)
        self.assertIn("does not exist", err)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = bcd.Database(path=Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def tables(self):
        rows = self.db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {r["name"] for r in rows}

    def test_schema_tables_created(self):
        for t in ("Task", "Run", "PageStatus", "Download", "Settings"):
            self.assertIn(t, self.tables())

    def test_ini_import_creates_disabled_tasks(self):
        ini = Path(self.tmp.name) / "sample.ini"
        cp = configparser.ConfigParser()
        cp["Playwright"] = {"svcA": "user1, user2", "svcB": ""}
        with ini.open("w") as fh:
            cp.write(fh)

        created = self.db.import_ini([ini])
        self.assertEqual(created, 3)  # svcA/user1, svcA/user2, svcB/(empty)
        # configparser lowercases option names, matching the batch path which
        # reads the same ini with the same parser (recipes are lowercase too).
        tasks = {(t["service"], t["user"]) for t in self.db.list_tasks()}
        self.assertIn(("svca", "user1"), tasks)
        self.assertIn(("svca", "user2"), tasks)
        self.assertIn(("svcb", ""), tasks)

        for t in self.db.list_tasks():
            self.assertEqual(t["enabled"], 0, "imported tasks start disabled")
            self.assertEqual(t["status"], "idle")
            self.assertEqual(t["cron"], "0 0 1 * *")
            self.assertTrue(t["recipe_file"].endswith(".yaml"))

    def test_ini_import_is_one_time(self):
        ini = Path(self.tmp.name) / "s2.ini"
        cp = configparser.ConfigParser()
        cp["Playwright"] = {"svcA": "u1"}
        with ini.open("w") as fh:
            cp.write(fh)
        self.assertEqual(self.db.import_ini([ini]), 1)
        # A second import must be a no-op (Task table is no longer empty).
        self.assertEqual(self.db.import_ini([ini]), 0)
        self.assertEqual(len(self.db.list_tasks()), 1)

    def test_settings_get_set_and_defaults(self):
        self.assertEqual(self.db.get_setting("missing_key"), None)
        self.assertEqual(self.db.get_setting("max_concurrency"), "1")  # default
        self.db.set_setting("ntfy_topic", "mytopic")
        self.assertEqual(self.db.get_setting("ntfy_topic"), "mytopic")

    def test_claim_task_run_lock(self):
        tid = self.db.create_task("svc", "u1")
        self.assertTrue(self.db.claim_task_run(tid))
        self.assertEqual(self.db.get_task(tid)["status"], "running")
        self.assertFalse(self.db.claim_task_run(tid))  # already running
        self.db.set_task_status(tid, "waiting")
        self.assertFalse(self.db.claim_task_run(tid))  # waiting is locked too
        self.db.set_task_status(tid, "idle")
        self.assertTrue(self.db.claim_task_run(tid))    # idle can be claimed

    def test_download_dedup_lookup(self):
        tid = self.db.create_task("svc", "u1")
        rid = self.db.create_run(tid)
        self.db.insert_download(rid, tid, "http://x/a.pdf", "a.pdf", 10, "sha-AAA", "/tmp/a.pdf")
        self.assertIsNone(self.db.find_download_by_sha(tid, "sha-BBB"))
        hit = self.db.find_download_by_sha(tid, "sha-AAA")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["filename"], "a.pdf")

    def test_run_and_page_status_roundtrip(self):
        tid = self.db.create_task("svc", "u1")
        rid = self.db.create_run(tid, display=99, control_sock="/tmp/x.sock")
        run = self.db.get_run(rid)
        self.assertEqual(run["display"], 99)
        self.assertEqual(run["control_sock"], "/tmp/x.sock")
        self.db.update_run(rid, result="success", ended_at="now")
        self.assertEqual(self.db.get_run(rid)["result"], "success")

        self.db.insert_page_status(rid, 3, locator_action={"actions": []},
                                   error={"error": [{"method": "click", "message": "nope"}]})
        ps = self.db.list_page_status(rid)
        self.assertEqual(len(ps), 1)
        self.assertEqual(ps[0]["step_number"], 3)
        import json
        self.assertIn("error", json.loads(ps[0]["error"]))

    def test_active_and_waiting_runs(self):
        tid = self.db.create_task("svc", "u1")
        rid1 = self.db.create_run(tid)
        rid2 = self.db.create_run(tid)
        self.assertEqual({r["id"] for r in self.db.list_active_runs()}, {rid1, rid2})
        self.assertEqual(self.db.list_waiting_runs(), [])
        self.db.update_run(rid1, pause_reason="step_failed", pause_prompt="please")
        waiting = self.db.list_waiting_runs()
        self.assertEqual([r["id"] for r in waiting], [rid1])
        self.db.update_run(rid1, result="success", ended_at="now")
        # Finalized: no longer active nor waiting, even though pause_reason is set.
        self.assertEqual(self.db.list_waiting_runs(), [])
        self.assertEqual([r["id"] for r in self.db.list_active_runs()], [rid2])


if __name__ == "__main__":
    unittest.main()
