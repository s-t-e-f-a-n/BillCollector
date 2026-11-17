# -*- coding: utf-8 -*-
"""UI tests for the task index page (``/tasks``).

Uses ``nicegui.testing.User`` (no browser), the same pattern as the
dashboard tests: the main file (pytest.ini ``main_file``) builds the
production wiring against a fresh temp DB (``BC_UI_TEST_DB``). The seed
is the dashboard's (an idle task with a finished run, a running task
with an active run, a waiting task with a paused run); the page shows
one row per task sorted by service then user, the status and last-run
badges as row data, and a row click navigates to the task detail
(``/tasks/<task_id>``)."""

import os
import sys
from pathlib import Path

import pytest
from nicegui import ui

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector.db import Database  # noqa: E402
from billcollector.ui import auth  # noqa: E402

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
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def _seed(testdb, tmp_path) -> dict:
    """The dashboard's seed: three tasks across two services (the index
    page carries no run actions, so only the rows are of interest)."""
    idle = testdb.create_task("svc-a", "user1", enabled=True, cron="0 0 1 * *")
    run_idle = testdb.create_run(idle)
    testdb.update_run(run_idle, started_at="2026-10-11 08:00:00",
                      result="success", ended_at="2026-10-11 08:00:00")
    running = testdb.create_task("svc-b", "user1", enabled=True, cron="* * * * *")
    log = tmp_path / "run.log"
    log.write_text("daemon boot\n", encoding="utf-8")
    testdb.create_run(running, log_path=str(log))
    testdb.set_task_status(running, "running")
    waiting = testdb.create_task("svc-a", "user2", enabled=False)
    testdb.update_run(testdb.create_run(waiting), pause_reason="paused by test")
    testdb.set_task_status(waiting, "waiting")
    return {"idle": idle, "running": running, "waiting": waiting,
            "run_idle": run_idle}


def _table_rows(user) -> list[dict]:
    """The task index table's rows (the single ui.table on the page)."""
    (table,) = user.find(kind=ui.table).elements
    return table.rows


async def test_one_row_per_task_sorted_and_populated(user, testdb, tmp_path):
    """One row per task, sorted by service then user (no status-first
    reordering, unlike the dashboard), with the status/last-run cells."""
    _seed(testdb, tmp_path)
    await _login(user, testdb)
    await user.open("/tasks")

    rows = _table_rows(user)
    assert [r["task"] for r in rows] == [
        "svc-a / user1", "svc-a / user2", "svc-b / user1"]
    assert [r["status"] for r in rows] == ["idle", "waiting", "running"]
    assert [r["enabled"] for r in rows] == ["yes", "no", "yes"]
    assert [r["cron"] for r in rows] == ["0 0 1 * *", "—", "* * * * *"]
    # No live job for any seeded task (the scheduler started empty).
    assert all(r["next_run"] == "—" for r in rows)

    idle_row, waiting_row, running_row = rows
    # The finished run: its full timestamp + the result badge's row data.
    assert idle_row["last_run_date"] == "2026-10-11 08:00:00"
    assert idle_row["last_run_result"] == "success"
    assert idle_row["last_run_result_color"] == "green"
    # Active runs have no result yet: the last-run cell renders —.
    assert waiting_row["last_run_result"] is None
    assert running_row["last_run_result"] is None
    # The running seed run carries its started_at (create_run stamps it).
    assert running_row["last_run_date"]


async def test_row_click_navigates_to_the_task_detail(user, testdb, tmp_path):
    seed = _seed(testdb, tmp_path)
    await _login(user, testdb)
    await user.open("/tasks")

    row = next(r for r in _table_rows(user) if r["id"] == seed["running"])
    user.find(kind=ui.table).trigger("rowclick", {"row": row})
    # The navigation is a background page load: allow a few extra retries.
    await user.should_see(f"Task {seed['running']}: svc-b / user1", retries=10)


async def test_empty_state_shows_when_no_tasks(user, testdb):
    await _login(user, testdb)
    await user.open("/tasks")

    await user.should_see("No tasks yet.")
    await user.should_see("Open the dashboard to add the first task")
    assert _table_rows(user) == []


async def test_unauthenticated_request_redirects_to_login(user):
    response = await user.http_client.get("/tasks", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/login"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
