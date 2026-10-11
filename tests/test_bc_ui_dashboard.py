# -*- coding: utf-8 -*-
"""UI tests for the dashboard (M2 chunk D2).

Uses ``nicegui.testing.User`` (no browser): the main file (pytest.ini
``main_file``) builds the production wiring against a fresh temp DB
(``BC_UI_TEST_DB``). The tests seed three tasks - idle (a finished run
plus a download), running (an active run with a log file), waiting (a
paused active run) - and check the table rows, the filters, the waiting
badge, the sort order, the row-click navigation to the task detail
placeholder, the log pane content, and the ``/runs/<run_id>`` deep link
(known id redirects, unknown id 404s)."""

import asyncio
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from nicegui import ui

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import scheduler as sched_mod  # noqa: E402
from billcollector.db import Database  # noqa: E402
from billcollector.scheduler import TaskScheduler  # noqa: E402
from billcollector.ui import auth  # noqa: E402
from billcollector.ui.dashboard import next_run  # noqa: E402

GOOD_PASSWORD = "ui-test-pass-1"


@pytest.fixture
def testdb():
    """A direct connection to the same DB file the main file created."""
    db = Database(path=os.environ["BC_UI_TEST_DB"])
    yield db
    db.close()


async def _login(user, testdb) -> None:
    """Seed the password and authenticate the simulated session."""
    auth.set_password_hash(testdb, auth.hash_password(GOOD_PASSWORD))
    response = await user.http_client.post(
        "/login", data={"password": GOOD_PASSWORD}, follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/"


def _seed(testdb, tmp_path) -> dict:
    """The D2.4 seed: three tasks across two services.

    ``svc-a/user1`` is idle (one finished run + a download),
    ``svc-b/user1`` is running (an active run with a log file), and
    ``svc-a/user2`` is waiting (a paused active run). The scheduler was
    started by the lifecycle before any task existed, so the live
    jobstore has no jobs: every row's next-run cell is ``—``."""
    idle = testdb.create_task("svc-a", "user1", enabled=True, cron="0 0 1 * *")
    run_idle = testdb.create_run(idle)
    testdb.update_run(run_idle, result="success", ended_at="2026-10-11 08:00:00")
    testdb.insert_download(run_idle, idle, "http://dl.example/a.pdf",
                           "invoice-a.pdf", 1234, "sha-a",
                           str(tmp_path / "invoice-a.pdf"))
    running = testdb.create_task("svc-b", "user1", enabled=True, cron="* * * * *")
    log = tmp_path / "run.log"
    log.write_text("daemon boot\nline two\n", encoding="utf-8")
    testdb.create_run(running, log_path=str(log))
    testdb.set_task_status(running, "running")
    waiting = testdb.create_task("svc-a", "user2", enabled=False)
    testdb.update_run(testdb.create_run(waiting), pause_reason="paused by test")
    testdb.set_task_status(waiting, "waiting")
    return {"idle": idle, "running": running, "waiting": waiting,
            "run_idle": run_idle, "log": log}


def _table_rows(user) -> list[dict]:
    """The dashboard table's rows (the single ui.table on the page)."""
    (table,) = user.find(kind=ui.table).elements
    return table.rows


def _set_filter(user, marker: str, value: str) -> None:
    """Drive a toolbar filter (setting the value fires on_value_change)."""
    (select,) = user.find(marker=marker).elements
    select.value = value


def test_next_run_reads_the_live_jobstore():
    """The live-job path of ``next_run`` (D2.3): with a running
    scheduler and an enabled task it returns the job's ``next_run_time``
    (the UI tests above only cover the no-job ``—`` path, so this pins
    the attribute read against the real APScheduler job)."""
    tmp = tempfile.TemporaryDirectory()
    try:
        db = Database(Path(tmp.name) / "bc.db")
        task = db.create_task("svc", "u1", enabled=True, cron="* * * * *")
        disabled = db.create_task("svc", "u2", enabled=False, cron="* * * * *")

        async def run_stub(task_id):
            pass

        sched = TaskScheduler(db, run_stub)
        try:
            async def cycle():
                sched.start()
                try:
                    return next_run(sched, task), next_run(sched, disabled)
                finally:
                    sched.stop()
            live, off = asyncio.run(cycle())
        finally:
            sched_mod._run_callback = None
            db.close()

        # The enabled task's job is live: a parseable timestamp (not —).
        parsed = datetime.strptime(live, "%Y-%m-%d %H:%M:%S")
        assert live != "—"
        assert parsed is not None
        # The disabled task has no job: —.
        assert off == "—"
    finally:
        tmp.cleanup()


async def test_one_row_per_task_sorted_and_populated(user, testdb, tmp_path):
    seed = _seed(testdb, tmp_path)
    await _login(user, testdb)
    await user.open("/")

    rows = _table_rows(user)
    # running/waiting first (service/user order), then the idle task.
    assert [r["task"] for r in rows] == [
        "svc-a / user2", "svc-b / user1", "svc-a / user1"]
    assert [r["status"] for r in rows] == ["waiting", "running", "idle"]
    # No live job for any seeded task (the scheduler started empty).
    assert all(r["next_run"] == "—" for r in rows)

    waiting_row, running_row, idle_row = rows
    assert "profile missing" in waiting_row["session"]
    # The active run has no result yet: the last-run cell says running.
    assert running_row["last_run"].endswith("· running")
    assert running_row["session"].endswith("last used "
                                          + running_row["last_run"][:10])
    # The finished run: its started_at date + result; the download's
    # filename + date.
    assert idle_row["last_run"].endswith("· success")
    assert idle_row["last_run"].startswith(
        testdb.get_run(seed["run_idle"])["started_at"][:10] + " ")
    assert idle_row["last_download"].startswith("invoice-a.pdf · ")
    # The waiting badge counts the waiting rows of the unfiltered table.
    await user.should_see("1 waiting")


async def test_service_filter_narrows_the_rows(user, testdb, tmp_path):
    _seed(testdb, tmp_path)
    await _login(user, testdb)
    await user.open("/")

    _set_filter(user, "service-filter", "svc-a")
    rows = _table_rows(user)
    assert [r["task"] for r in rows] == ["svc-a / user2", "svc-a / user1"]
    # The waiting row survives the filter: the badge stays at one.
    await user.should_see("1 waiting")
    assert all(r["service"] == "svc-a" for r in rows)


async def test_status_filter_narrows_the_rows_and_badge(user, testdb, tmp_path):
    _seed(testdb, tmp_path)
    await _login(user, testdb)
    await user.open("/")

    _set_filter(user, "status-filter", "running")
    rows = _table_rows(user)
    assert [r["task"] for r in rows] == ["svc-b / user1"]
    assert [r["status"] for r in rows] == ["running"]
    await user.should_see("0 waiting")


async def test_row_click_navigates_to_the_task_detail(user, testdb, tmp_path):
    seed = _seed(testdb, tmp_path)
    await _login(user, testdb)
    await user.open("/")

    row = next(r for r in _table_rows(user) if r["id"] == seed["running"])
    user.find(kind=ui.table).trigger("rowclick", {"row": row})
    # The navigation is a background page load: allow a few extra retries.
    await user.should_see(f"Task {seed['running']}: svc-b / user1", retries=10)


async def test_log_pane_shows_the_followed_run_log(user, testdb, tmp_path):
    _seed(testdb, tmp_path)
    await _login(user, testdb)
    await user.open("/")

    # The pane follows the most recent running run: its log file content.
    await user.should_see("daemon boot")
    await user.should_see("line two")


async def test_unknown_run_id_shows_a_404(user, testdb, tmp_path):
    _seed(testdb, tmp_path)
    await _login(user, testdb)
    await user.open("/runs/9999")
    await user.should_see("Unknown run id: 9999 (404)")


async def test_known_run_id_redirects_to_the_task_detail(user, testdb, tmp_path):
    seed = _seed(testdb, tmp_path)
    await _login(user, testdb)
    await user.open(f"/runs/{seed['run_idle']}")
    await user.should_see(f"Task {seed['idle']}: svc-a / user1", retries=10)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
