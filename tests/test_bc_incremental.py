# -*- coding: utf-8 -*-
"""Opt-in incremental download contract with synthetic, isolated fixtures."""

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import collection, runner  # noqa: E402
from tests.test_bc_collection import _Page, _Events, _Listing  # noqa: E402
from billcollector import db as bcd  # noqa: E402
from billcollector import downloads as bcdl  # noqa: E402

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


class _StubDownload:
    def __init__(self, data, name, url="https://portal.example/invoice?token=x"):
        self.suggested_filename = name
        self.url = url
        self._data = data

    def save_as(self, target):
        Path(target).write_bytes(self._data)


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = bcd.Database(path=self.root / "test.db")
        self.out = self.root / "dl"
        self.db.set_setting("download_dir", str(self.out))
        self.tid = self.db.create_task("svc", "u1")
        self.rid = self.db.create_run(self.tid)
        self.task = {"id": self.tid}

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def published(self):
        return sorted(p.name for p in self.out.iterdir() if p.is_file())


class SourceKeyTests(_Base):
    def test_source_key_is_persisted_for_new_and_duplicate_rows(self):
        bcdl.track_download(_StubDownload(PDF, "a.pdf"), self.rid, self.task, self.db,
                            source_key="href=1")
        bcdl.track_download(_StubDownload(PDF, "a.pdf"), self.rid, self.task, self.db,
                            source_key="href=2")
        self.assertEqual(self.db.known_source_keys(self.tid), {"href=1", "href=2"})
        self.assertEqual(self.published(), ["a.pdf"])

    def test_known_keys_are_scoped_to_the_task(self):
        other = self.db.create_task("svc", "u2")
        bcdl.track_download(_StubDownload(PDF, "a.pdf"), self.rid, {"id": other}, self.db,
                            source_key="href=1")
        self.assertEqual(self.db.known_source_keys(self.tid), set())

    def test_existing_database_gains_the_column_and_keeps_rows(self):
        path = self.root / "old.db"
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE Download (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER,
              task_id INTEGER, url TEXT, filename TEXT, size INTEGER, sha256 TEXT,
              saved_path TEXT, created_at TEXT, duplicate_of_id INTEGER,
              state TEXT NOT NULL DEFAULT 'consumed', staged_path TEXT);
            INSERT INTO Download (task_id, filename, sha256) VALUES (7, 'old.pdf', 'abc');
        """)
        conn.commit()
        conn.close()
        migrated = bcd.Database(path=path)
        try:
            rows = migrated.list_downloads()
            self.assertEqual([(r["filename"], r["sha256"], r["source_key"]) for r in rows],
                             [("old.pdf", "abc", None)])
            self.assertEqual(migrated.known_source_keys(7), set())
        finally:
            migrated.close()


class IncrementalCollectionTests(_Base):
    options = {"key_attribute": "data-key", "max_items": 5,
               "timeout_ms": 1000, "event_window_ms": 5, "incremental": True}

    def collect(self, keys, *, options=None, task=None, content=PDF):
        page, context = _Page(), _Events()
        listing = _Listing(page, context, [
            {"data-key": key, "id": key,
             "download": _StubDownload(content, f"{index}.pdf")}
            for index, key in enumerate(keys)
        ])
        ctx = SimpleNamespace(page=page, context=context, files_downloaded=[],
                              db=self.db, task=task or self.task,
                              run_id=self.rid)
        result = runner._collection_actions(ctx)["download_all"](
            listing, self.options if options is None else options)
        return ctx, listing, result

    def test_stable_keys_survive_restart_and_skip_only_known_items(self):
        self.collect(["one"])
        self.db.close()
        self.db = bcd.Database(path=self.root / "test.db")
        ctx, listing, records = self.collect(["one", "two"])
        self.assertEqual(listing.clicked, ["two"])
        self.assertEqual(len(records), 1)
        self.assertEqual(self.db.known_source_keys(self.tid),
                         {"data-key=one", "data-key=two"})
        self.assertEqual(runner.run_result(False, ctx.files_downloaded), "success")

    def test_all_known_is_explicit_success_without_a_fake_download(self):
        self.collect(["one"])
        with self.assertLogs(runner.logger, level="INFO") as logs:
            ctx, listing, records = self.collect(["one"])
        self.assertIn("all items known", " ".join(logs.output))
        self.assertEqual(listing.clicked, [])
        self.assertEqual(records, [])
        self.assertEqual(ctx.files_downloaded, [])
        self.assertEqual(len(self.db.list_downloads()), 1)
        self.assertEqual(runner.run_result(False, [],
                         all_items_known=ctx.all_items_known), "success")
        for aborted, files, pause, expected in (
            (True, [], None, "failure"),
            (False, [{"result": "failure"}], None, "failure"),
            (False, [], "cancel", "cancelled"),
            (False, [], "timeout", "needs_attention"),
        ):
            with self.subTest(expected=expected):
                self.assertEqual(runner.run_result(aborted, files, pause,
                                 all_items_known=True), expected)
        self.assertEqual(runner.run_result(False, []), "failure")

    def test_keys_do_not_detect_or_fetch_in_place_corrections(self):
        self.collect(["one"])
        _, listing, _ = self.collect(["one"], content=PDF + b"corrected")
        self.assertEqual(listing.clicked, [])
        self.assertEqual((self.out / "0.pdf").read_bytes(), PDF)
        self.assertEqual(len(self.db.list_downloads()), 1)

    def test_non_opt_in_fetches_corrections_and_does_not_seed_keys(self):
        self.collect(["one"])
        for incremental in (None, False):
            options = {**self.options}
            options.pop("incremental")
            if incremental is not None:
                options["incremental"] = incremental
            with self.subTest(incremental=incremental), mock.patch.object(
                self.db, "known_source_keys", side_effect=AssertionError("must not query")
            ):
                ctx, listing, _ = self.collect(["one"], options=options,
                                               content=PDF + b"corrected")
            self.assertEqual(listing.clicked, ["one"])
            self.assertFalse(getattr(ctx, "all_items_known", False))
            self.assertIsNone(self.db.list_downloads()[-1]["source_key"])
        self.assertTrue(any(p.read_bytes() == PDF + b"corrected"
                            for p in self.out.iterdir() if p.is_file()))

    def test_task_and_attribute_scopes_are_independent(self):
        self.collect(["one"])
        other = {"id": self.db.create_task("svc", "u2")}
        _, listing, _ = self.collect(["one"], task=other)
        self.assertEqual(listing.clicked, ["one"])
        _, listing, _ = self.collect(["one"], options={**self.options, "key_attribute": "id"})
        self.assertEqual(listing.clicked, ["one"])
        self.assertEqual(self.db.known_source_keys(self.tid), {"data-key=one", "id=one"})

    def test_invalid_lists_are_not_all_known_success(self):
        self.collect(["one"])
        for keys in ([], ["one", "one"], [""], [str(i) for i in range(6)]):
            with self.subTest(keys=keys), self.assertRaises(collection.CollectionError):
                self.collect(keys)

    def test_partial_failure_keeps_only_committed_keys_for_retry(self):
        track = bcdl.track_download
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("synthetic")
            return track(*args, **kwargs)

        with mock.patch.object(bcdl, "track_download", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.collect(["one", "two"])
        self.assertEqual(self.db.known_source_keys(self.tid), {"data-key=one"})
        _, listing, _ = self.collect(["one", "two"])
        self.assertEqual(listing.clicked, ["two"])

    def test_old_unkeyed_download_is_acquired_without_backfill(self):
        options = {**self.options, "incremental": False}
        self.collect(["one"], options=options)
        _, listing, _ = self.collect(["one"])
        self.assertEqual(listing.clicked, ["one"])
        first, duplicate = self.db.list_downloads()
        self.assertIsNone(first["source_key"])
        self.assertEqual(duplicate["source_key"], "data-key=one")
        self.assertEqual(duplicate["duplicate_of_id"], first["id"])

    def test_failed_save_does_not_commit_a_key(self):
        with mock.patch.object(bcdl, "track_download", side_effect=OSError("synthetic")):
            with self.assertRaises(OSError):
                self.collect(["one"])
        self.assertEqual(self.db.known_source_keys(self.tid), set())
        _, listing, _ = self.collect(["one"])
        self.assertEqual(listing.clicked, ["one"])

    def test_legacy_callback_stays_positional_and_opt_in_fails_before_click(self):
        for incremental in (None, False, True):
            page, context = _Page(), _Events()
            listing = _Listing(page, context, [{"data-key": "one", "download": "file"}])
            save = mock.Mock(return_value="saved")
            options = {**self.options}
            options.pop("incremental")
            if incremental is not None:
                options["incremental"] = incremental
            with self.subTest(incremental=incremental):
                if incremental:
                    with self.assertRaisesRegex(collection.CollectionError, "runner"):
                        collection.download_all(page, context, listing, save, options)
                    self.assertEqual(listing.clicked, [])
                    save.assert_not_called()
                else:
                    self.assertEqual(collection.download_all(
                        page, context, listing, save, options), ["saved"])
                    save.assert_called_once_with("file")

    def test_option_is_strictly_boolean_and_zip_is_not_implemented(self):
        for options in ({"incremental": "yes"}, {"incremental": 1},
                        {"incremental": None}, {"unpack": "pdf"}):
            with self.subTest(options=options), self.assertRaises(collection.CollectionError):
                self.collect(["one"], options={**self.options, **options})

    def test_source_key_preserves_value_and_attribute(self):
        self.assertEqual(collection.source_key("href", "a=b"), "href=a=b")
        self.assertNotEqual(collection.source_key("id", "a=b"), "href=a=b")

    def test_schema_accepts_only_boolean_incremental(self):
        import jsonschema
        import yaml

        schema = yaml.safe_load((Path(__file__).resolve().parents[1] /
                                 "apps/recipes_playwright/recipe-pw-schema.yaml").read_text())
        method = schema["definitions"]["downloadAllMethod"]
        for value in (True, False):
            jsonschema.validate({"method": "download_all", "arguments": [
                {**self.options, "incremental": value}]}, method)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate({"method": "download_all", "arguments": [
                {**self.options, "incremental": "yes"}]}, method)


class SourceKeyRecoveryTests(_Base):
    def test_publication_without_row_recovers_key_from_journal(self):
        from billcollector.interrupt import RunInterrupted

        def interrupt(record):
            raise RunInterrupted("synthetic")

        with mock.patch.object(bcdl, "CONSUMERS", [interrupt]):
            with self.assertRaises(RunInterrupted):
                bcdl.track_download(_StubDownload(PDF, "a.pdf"), self.rid,
                                    self.task, self.db, source_key="href=one")
        self.db.conn.execute("DELETE FROM Download")
        self.db.conn.commit()
        with mock.patch.object(bcdl, "CONSUMERS", []) as consumers:
            bcdl.recover_downloads(self.db)
        self.assertEqual(consumers, [])
        self.assertEqual(self.db.known_source_keys(self.tid), {"href=one"})
        row, = self.db.list_downloads()
        self.assertEqual(row["state"], "consumed")

    def test_published_pending_delivery_retains_key_and_retries_consumer(self):
        def unavailable(record):
            raise OSError("synthetic")

        with mock.patch.object(bcdl, "CONSUMERS", [unavailable]):
            bcdl.track_download(_StubDownload(PDF, "a.pdf"), self.rid,
                                self.task, self.db, source_key="href=one")
        self.assertEqual(self.db.list_downloads()[0]["state"], "published")
        delivered = []
        with mock.patch.object(bcdl, "CONSUMERS", [delivered.append]):
            bcdl.recover_downloads(self.db)
        self.assertEqual(len(delivered), 1)
        self.assertEqual(self.db.known_source_keys(self.tid), {"href=one"})
        self.assertEqual(self.db.list_downloads()[0]["state"], "consumed")
