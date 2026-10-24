# -*- coding: utf-8 -*-
"""UI tests for the dashboard (M2 chunk D2).

Uses ``nicegui.testing.User`` (no browser): the main file (pytest.ini
``main_file``) builds the production wiring against a fresh temp DB
(``BC_UI_TEST_DB``). The tests seed three tasks - idle (a finished run
plus a download), running (an active run with a log file), waiting (a
paused active run) - and check the table rows, the filters, the waiting
badge, the sort order, the row-click navigation to the task detail
 placeholder, and the log pane content. The ``/runs/<run_id>`` deep link
 is the session page since M3 S1.1 (the M2 redirect is gone); its tests
 live in ``test_bc_ui_session.py``.

D3.2 adds the run actions: the row **Run now** / **Stop** buttons route
through the ``rowaction`` CustomEvent to ``orchestrator.start_run`` /
``stop_run`` (stubbed), and the toolbar **Run (filtered)** button
enqueues exactly the enabled, non-active tasks in the filtered set
(disabled and active tasks are skipped and reported in a notify).

D3.3 adds the task management dialogs: the toolbar **Add task** button
(create: service/user/cron/enabled, the derived recipe file shown
read-only with a missing-file warning, duplicate and invalid-cron
rejections) and the row **Edit** button (cron + the enabled toggle;
enabling flips the row's next-run cell from — to the live job's fire
time via ``scheduler.sync_task``)."""

import asyncio
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pytest
from nicegui import ui

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import config  # noqa: E402
from billcollector import scheduler as sched_mod  # noqa: E402
from billcollector.db import Database  # noqa: E402
from billcollector.orchestrator import Orchestrator  # noqa: E402
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
    assert response.status_code == 303
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
    run_running = testdb.create_run(running, log_path=str(log))
    testdb.set_task_status(running, "running")
    waiting = testdb.create_task("svc-a", "user2", enabled=False)
    testdb.update_run(testdb.create_run(waiting), pause_reason="paused by test")
    testdb.set_task_status(waiting, "waiting")
    return {"idle": idle, "running": running, "waiting": waiting,
            "run_idle": run_idle, "run_running": run_running, "log": log}


def _table_rows(user) -> list[dict]:
    """The dashboard table's rows (the single ui.table on the page)."""
    (table,) = user.find(kind=ui.table).elements
    return table.rows


def _set_filter(user, marker: str, value: str) -> None:
    """Drive a toolbar filter (setting the value fires on_value_change)."""
    (select,) = user.find(marker=marker).elements
    select.value = value


def _stub_orchestrator(monkeypatch, started: list, stopped: list) -> None:
    """Replace the orchestrator's run actions with recording stubs (D3.2).

    The patch targets the class methods rather than the instance so it
    reaches the production orchestrator the main file wired in - the
    test and the runpy'd main file share the same
    ``billcollector.orchestrator`` module (and hence class object). The
    stubs record the task id and return ``True`` so the row-action
    handlers take their success path (no warning notify)."""
    async def fake_start(self, task_id):
        started.append(task_id)
        return True

    async def fake_stop(self, task_id, timeout=None):
        stopped.append(task_id)
        return True

    monkeypatch.setattr(Orchestrator, "start_run", fake_start)
    monkeypatch.setattr(Orchestrator, "stop_run", fake_stop)


async def _wait(predicate, message: str, timeout: float = 2.0) -> None:
    """Poll until ``predicate()`` holds (D3.2).

    The row-action handler is async and the Run (filtered) enqueue is
    fanned out through ``background_tasks``; both run as tasks on the
    simulation's loop, so the test yields control here until the recorded
    call lands."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError(message)
        await asyncio.sleep(0.01)


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


async def test_log_pane_repoints_to_a_run_started_after_the_page_load(
        user, testdb, tmp_path):
    """The Run now flow (D2.3 live log): a run started after the page
    load is picked up on the next ~2 s poll - the pane clears the old
    run's content and shows the new run's log file, then streams its
    live lines from there."""
    _seed(testdb, tmp_path)
    await _login(user, testdb)
    await user.open("/")
    await user.should_see("daemon boot")

    # A new run starts (the row Run now would: claim, spawn, Run row).
    log2 = tmp_path / "fresh-run.log"
    log2.write_text("fresh run line\n", encoding="utf-8")
    task2 = testdb.create_task("svc-c", "user1", enabled=True,
                               cron="0 0 1 * *")
    testdb.create_run(task2, log_path=str(log2))
    testdb.set_task_status(task2, "running")

    # The ~2 s poll re-points the pane at the new active run (the retry
    # window spans the poll interval).
    await user.should_see("fresh run line", retries=10)


async def test_step_strip_shows_the_followed_run_screenshots(
        user, testdb, tmp_path):
    """The step strip below the log pane (the at-a-glance view of the
    followed run's steps, the task detail's run expansion carries the
    full table): the PageStatus screenshots with their step numbers; a
    thumbnail click opens the full image in a dialog."""
    seed = _seed(testdb, tmp_path)
    run = seed["run_running"]
    run_dir = config.RUN_DIR / str(run)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "step_3.png").write_bytes(b"png-dash")
    testdb.insert_page_status(run, 3, locator_action='{"step": 3}',
                              screenshot_path=str(run_dir / "step_3.png"))
    testdb.insert_page_status(run, 4, locator_action='{"step": 4}')

    await _login(user, testdb)
    await user.open("/")

    await user.should_see(f"Steps · Run {run}")
    (img,) = user.find(kind=ui.image).elements
    # Only the step with a screenshot is rendered (the runfiles tree
    # holds the file, so the URL maps).
    assert img.source == f"/runfiles/{run}/step_3.png"
    # The step number labels the thumbnail.
    labels = user.find(kind=ui.label).elements
    assert any(label.text == "3" for label in labels)
    # The thumbnail click opens the full image in a dialog (a second
    # ui.image with the same source).
    user.find(kind=ui.image).click()
    assert len(user.find(kind=ui.image).elements) == 2


async def test_run_now_calls_start_run(user, testdb, tmp_path, monkeypatch):
    """Row Run now routes to ``orchestrator.start_run`` (D3.2)."""
    seed = _seed(testdb, tmp_path)
    started, stopped = [], []
    _stub_orchestrator(monkeypatch, started, stopped)
    await _login(user, testdb)
    await user.open("/")

    # The idle task is not active: its Run now button is enabled, and the
    # click routes through the rowaction CustomEvent to start_run.
    user.find(kind=ui.table).trigger(
        "rowaction",
        {"action": "run", "id": seed["idle"], "task": "svc-a / user1"})
    await _wait(lambda: seed["idle"] in started,
                "Run now did not call start_run")
    assert started == [seed["idle"]]
    assert stopped == []


async def test_stop_calls_stop_run(user, testdb, tmp_path, monkeypatch):
    """Row Stop routes to ``orchestrator.stop_run`` (D3.2)."""
    seed = _seed(testdb, tmp_path)
    started, stopped = [], []
    _stub_orchestrator(monkeypatch, started, stopped)
    await _login(user, testdb)
    await user.open("/")

    # The running task is the only one whose Stop button is enabled.
    user.find(kind=ui.table).trigger(
        "rowaction", {"action": "stop", "id": seed["running"],
                      "task": "svc-b / user1"})
    await _wait(lambda: seed["running"] in stopped,
                "Stop did not call stop_run")
    assert stopped == [seed["running"]]
    assert started == []


async def test_run_filtered_enqueues_only_enabled_tasks(user, testdb, tmp_path,
                                                        monkeypatch):
    """Toolbar Run (filtered) enqueues exactly the enabled, non-active
    tasks in the (unfiltered) set (D3.2)."""
    seed = _seed(testdb, tmp_path)
    started, stopped = [], []
    _stub_orchestrator(monkeypatch, started, stopped)
    await _login(user, testdb)
    await user.open("/")

    user.find(marker="run-filtered").click()
    await _wait(lambda: len(started) == 1,
                "Run (filtered) did not enqueue the idle task")
    # Only the enabled+idle task is enqueued; the disabled task and the
    # active task are reported in a notify, not started.
    assert started == [seed["idle"]]
    assert stopped == []
    assert user.notify.contains("Run enqueued for 1 task(s)")
    assert user.notify.contains("svc-a / user2 (disabled)")
    assert user.notify.contains("svc-b / user1 (active)")


async def test_run_filtered_respects_the_service_filter(user, testdb, tmp_path,
                                                        monkeypatch):
    """Run (filtered) only considers tasks in the filtered set (D3.2)."""
    _seed(testdb, tmp_path)
    started, stopped = [], []
    _stub_orchestrator(monkeypatch, started, stopped)
    await _login(user, testdb)
    await user.open("/")

    # svc-b holds a single task, and it is active: nothing is enqueued,
    # the task is reported as skipped, and no enqueue notify is raised.
    _set_filter(user, "service-filter", "svc-b")
    user.find(marker="run-filtered").click()
    # No task is enqueued, so no background start_run is scheduled.
    await asyncio.sleep(0.05)
    assert started == []
    assert user.notify.contains("svc-b / user1 (active)")
    assert not user.notify.contains("Run enqueued")


def _latest(user, marker: str):
    """The newest element carrying the marker (D3.3).

    A closed dialog is hidden, not deleted: after a second dialog opens,
    the markers of both dialogs match, and the element with the highest
    id belongs to the newest one (ids are monotonic per client)."""
    return max(user.find(marker=marker).elements, key=lambda e: e.id)


async def test_add_task_dialog_creates_a_task(user, testdb, tmp_path, monkeypatch):
    """Toolbar Add task: the create dialog inserts the task (D3.3)."""
    _seed(testdb, tmp_path)
    await _login(user, testdb)
    await user.open("/")

    synced = []

    def fake_sync(self, task_id):
        synced.append(task_id)

    monkeypatch.setattr(TaskScheduler, "sync_task", fake_sync)

    user.find(marker="add-task").click()
    service = _latest(user, "task-service")
    user_input = _latest(user, "task-user")
    service.value = "svc-c"
    user_input.value = "user9"
    _latest(user, "task-date-window").value = 30
    # The recipe file is derived from the service and shown read-only;
    # the missing file is made explicit (a warning, not a block).
    await user.should_see("Recipe (shared): recipe-pw__svc-c.yaml (missing)")
    user.find(marker="task-save").click()

    rows = _table_rows(user)
    assert any(r["task"] == "svc-c / user9" for r in rows)
    task = testdb.get_task_by_service_user("svc-c", "user9")
    assert task is not None
    assert task["enabled"] == 0
    assert task["cron"] == "0 0 1 * *"
    assert task["status"] == "idle"
    assert task["date_window_days"] == 30
    assert task["recipe_file"].endswith("recipe-pw__svc-c.yaml")
    assert task["profile_dir"].endswith("svc-c_user9")
    # Every create goes through the scheduler hook (C7.1).
    assert synced == [task["id"]]
    assert user.notify.contains("Task svc-c / user9 created")
    assert user.notify.contains("recipe-pw__svc-c.yaml is missing")


async def test_add_task_rejects_a_duplicate(user, testdb, tmp_path, monkeypatch):
    """The (service, user) UNIQUE constraint is surfaced as a notify, not
    an exception (D3.3)."""
    _seed(testdb, tmp_path)
    await _login(user, testdb)
    await user.open("/")

    monkeypatch.setattr(TaskScheduler, "sync_task", lambda self, task_id: None)

    for _ in range(2):
        user.find(marker="add-task").click()
        _latest(user, "task-service").value = "svc-c"
        _latest(user, "task-user").value = "user9"
        user.find(marker="task-save").click()
        # A closed dialog stays in the page layout (hidden, not deleted),
        # so the second attempt opens on a fresh page load.
        await user.open("/")

    assert len([t for t in testdb.list_tasks()
                if t["service"] == "svc-c"]) == 1
    assert user.notify.contains("Task svc-c / user9 already exists")
    assert user.notify.messages.count("Task svc-c / user9 created") == 1


async def test_add_task_rejects_an_invalid_cron(user, testdb, tmp_path):
    """A cron that does not parse is not saved (D3.3)."""
    _seed(testdb, tmp_path)
    await _login(user, testdb)
    await user.open("/")

    user.find(marker="add-task").click()
    _latest(user, "task-service").value = "svc-c"
    _latest(user, "task-user").value = "user9"
    _latest(user, "task-cron").value = "not a cron"
    user.find(marker="task-save").click()

    assert testdb.get_task_by_service_user("svc-c", "user9") is None
    assert user.notify.contains("Invalid cron expression")
    assert not user.notify.contains("created")


async def test_edit_dialog_cron_and_enable_flip_the_row(user, testdb, tmp_path):
    """Row Edit: the dialog's cron + enabled toggle update the task, and
    the row's next-run cell flips from — to the live job's fire time
    (D3.3)."""
    seed = _seed(testdb, tmp_path)
    await _login(user, testdb)
    await user.open("/")

    tid = seed["waiting"]  # disabled, no cron
    row = next(r for r in _table_rows(user) if r["id"] == tid)
    assert row["next_run"] == "—"

    # The Edit button routes through the same rowaction CustomEvent as
    # Run now / Stop (D3.2 pattern).
    user.find(kind=ui.table).trigger(
        "rowaction", {"action": "edit", "id": tid, "task": "svc-a / user2"})
    await user.should_see("Edit task: svc-a / user2")

    (cron,) = user.find(marker="task-cron").elements
    cron.value = "0 0 1 * *"
    user.find(marker="task-enabled").click()  # toggle off -> on
    user.find(marker="task-save").click()

    task = testdb.get_task(tid)
    assert task["enabled"] == 1
    assert task["cron"] == "0 0 1 * *"
    rows = _table_rows(user)
    row = next(r for r in rows if r["id"] == tid)
    # sync_task created the live APScheduler job: the next-run cell flips
    # from — to a parseable timestamp without waiting for the poll.
    assert row["next_run"] != "—"
    datetime.strptime(row["next_run"], "%Y-%m-%d %H:%M:%S")
    assert user.notify.contains("Task svc-a / user2 updated")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
