# -*- coding: utf-8 -*-
"""UI tests for the task detail page and the downloads page (M2 chunk
D4.4).

Uses ``nicegui.testing.User`` (no browser), the same pattern as the
dashboard tests: the main file (pytest.ini ``main_file``) builds the
production wiring against a fresh temp DB (``BC_UI_TEST_DB``). The
seeds create a real runfiles tree under ``config.RUN_DIR`` (the
session temp dir, see ``tests/conftest.py``), so the step screenshots
and the pause screenshot get their ``/runfiles`` URLs from a real
directory. The run actions route through the stubbed orchestrator
(D3.2 pattern), the profile reset through the confirmation dialog
(D3.4).
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from nicegui import ui

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import config  # noqa: E402
from billcollector.db import Database  # noqa: E402
from billcollector.orchestrator import Orchestrator  # noqa: E402
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


def _stub_orchestrator(monkeypatch, started: list, stopped: list) -> None:
    """Replace the orchestrator's run actions with recording stubs.

    The patch targets the class methods so it reaches the production
    orchestrator the main file wired in (the test and the runpy'd main
    file share the ``billcollector.orchestrator`` module)."""
    async def fake_start(self, task_id):
        started.append(task_id)
        return True

    async def fake_stop(self, task_id, timeout=None):
        stopped.append(task_id)
        return True

    monkeypatch.setattr(Orchestrator, "start_run", fake_start)
    monkeypatch.setattr(Orchestrator, "stop_run", fake_stop)


async def _wait(predicate, message: str, timeout: float = 2.0) -> None:
    """Poll until ``predicate()`` holds (the action handlers are async)."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError(message)
        await asyncio.sleep(0.01)


def _seed_detail(testdb, tmp_path) -> dict:
    """One task with a finished run (fixed started/ended so the
    duration cell is deterministic), a log file, two PageStatus rows
    with screenshots in a real runfiles tree, and two downloads (the
    second a duplicate of the first)."""
    task = testdb.create_task("svc-a", "user1", enabled=True, cron="0 0 1 * *")
    run = testdb.create_run(task)
    run_dir = config.RUN_DIR / str(run)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "step_1.png").write_bytes(b"png-one")
    (run_dir / "step_2.png").write_bytes(b"png-two")
    log = tmp_path / f"run-{run}.log"
    log.write_text("detail log line\n", encoding="utf-8")
    testdb.update_run(run, started_at="2026-10-11 08:00:00",
                      ended_at="2026-10-11 08:04:05", result="success",
                      log_path=str(log), notes="first line\nsecond line")
    testdb.insert_page_status(
        run, 1,
        locator_action='{"step": 1, "description": "open the portal"}',
        screenshot_path=str(run_dir / "step_1.png"))
    testdb.insert_page_status(
        run, 2,
        locator_action='{"step": 2, "description": "download"}',
        screenshot_path=str(run_dir / "step_2.png"),
        error="timed out waiting")
    dl1 = testdb.insert_download(run, task, "http://dl.example/a.pdf",
                                 "invoice-a.pdf", 1234, "0123456789abcdef",
                                 str(tmp_path / "a.pdf"))
    testdb.insert_download(run, task, "http://dl.example/a2.pdf",
                           "invoice-a.pdf", 1234, "0123456789abcdef",
                           str(tmp_path / "a2.pdf"), duplicate_of_id=dl1)
    return {"task": task, "run": run, "run_dir": run_dir, "dl1": dl1}


async def test_detail_page_shows_header_history_steps_and_downloads(
        user, testdb, tmp_path):
    """Header (status badge, schedule, recipe), the run history with the
    step rows and their screenshot URLs, the task downloads with the
    duplicate badge, and the log pane's content (D4.1b/D4.1c/D4.3)."""
    seed = _seed_detail(testdb, tmp_path)
    await _login(user, testdb)
    await user.open(f"/tasks/{seed['task']}")

    await user.should_see(f"Task {seed['task']}: svc-a / user1")
    (badge,) = user.find(marker="detail-status").elements
    assert badge.text == "idle"
    await user.should_see("Enabled: yes · Cron: 0 0 1 * *")
    await user.should_see("Recipe: recipe-pw__svc-a.yaml (missing)")

    # The history: one expansion per run; the header (the expansion's
    # label prop, readable server-side as ``text``) carries the result
    # and the duration. ``get_computed_prop`` is a client-side JS
    # round-trip the User simulation cannot answer.
    (exp,) = user.find(kind=ui.expansion).elements
    header = exp.text
    assert f"Run {seed['run']}" in header
    assert "success · 4m 5s" in header

    # Step rows: the screenshot URLs map into the real runfiles tree
    # (the tables are marked; ``find(kind=...).elements`` is an
    # unordered set).
    (steps_table,) = user.find(marker="detail-steps").elements
    rows = steps_table.rows
    assert [r["screenshot"] for r in rows] == [
        f"/runfiles/{seed['run']}/step_1.png",
        f"/runfiles/{seed['run']}/step_2.png"]
    assert rows[0]["step"] == 1
    assert rows[1]["error"].endswith("timed out waiting")

    # The task downloads: newest first, the duplicate badged.
    (downloads_table,) = user.find(marker="detail-downloads").elements
    drows = downloads_table.rows
    assert len(drows) == 2
    assert all(r["filename"] == "invoice-a.pdf" for r in drows)
    assert drows[0]["duplicate"] == f"duplicate of #{seed['dl1']}"
    assert drows[1]["duplicate"] == "—"

    # The log pane follows the (only) run: its log file content.
    await user.should_see("detail log line")


async def test_action_buttons_follow_the_task_status(user, testdb, tmp_path):
    """While the task is running: Run now and Reset profile are
    disabled, Stop is enabled (D4.1/D4.4)."""
    task = testdb.create_task("svc-r", "user1", enabled=True)
    testdb.create_run(task)
    testdb.set_task_status(task, "running")
    await _login(user, testdb)
    await user.open(f"/tasks/{task}")

    (badge,) = user.find(marker="detail-status").elements
    assert badge.text == "running"
    (run_btn,) = user.find(marker="detail-run").elements
    (stop_btn,) = user.find(marker="detail-stop").elements
    (reset_btn,) = user.find(marker="detail-reset").elements
    assert run_btn.enabled is False
    assert stop_btn.enabled is True
    assert reset_btn.enabled is False


async def test_detail_run_now_routes_to_start_run(user, testdb, tmp_path,
                                                  monkeypatch):
    """Detail-page Run now routes to ``orchestrator.start_run`` (D4.1)."""
    seed = _seed_detail(testdb, tmp_path)
    started, stopped = [], []
    _stub_orchestrator(monkeypatch, started, stopped)
    await _login(user, testdb)
    await user.open(f"/tasks/{seed['task']}")

    (run_btn,) = user.find(marker="detail-run").elements
    assert run_btn.enabled is True
    user.find(marker="detail-run").click()
    await _wait(lambda: seed["task"] in started,
                "detail Run now did not call start_run")
    assert started == [seed["task"]]
    assert stopped == []


async def test_detail_stop_routes_to_stop_run(user, testdb, tmp_path,
                                              monkeypatch):
    """Detail-page Stop routes to ``orchestrator.stop_run`` (D4.1)."""
    task = testdb.create_task("svc-s", "user1", enabled=True)
    testdb.create_run(task)
    testdb.set_task_status(task, "running")
    started, stopped = [], []
    _stub_orchestrator(monkeypatch, started, stopped)
    await _login(user, testdb)
    await user.open(f"/tasks/{task}")

    (stop_btn,) = user.find(marker="detail-stop").elements
    assert stop_btn.enabled is True
    user.find(marker="detail-stop").click()
    await _wait(lambda: task in stopped,
                "detail Stop did not call stop_run")
    assert stopped == [task]
    assert started == []


async def test_reset_profile_confirms_then_resets(user, testdb, tmp_path):
    """Reset profile: the confirmation dialog, then the profile dir is
    gone and ``profile_reset_at`` is recorded (D3.4/D4.1)."""
    profile = tmp_path / "profile-svc-p"
    profile.mkdir()
    task = testdb.create_task("svc-p", "user1", profile_dir=str(profile))
    await _login(user, testdb)
    await user.open(f"/tasks/{task}")

    (reset_btn,) = user.find(marker="detail-reset").elements
    assert reset_btn.enabled is True
    user.find(marker="detail-reset").click()
    await user.should_see("Reset the profile?")
    user.find(marker="detail-reset-confirm").click()

    assert not profile.exists()
    assert testdb.get_task(task)["profile_reset_at"] is not None
    assert user.notify.contains("Profile reset")


async def test_pause_section_shows_prompt_deadline_and_screenshot(
        user, testdb, tmp_path):
    """While the run is waiting: the pause card shows the reason, the
    prompt, the deadline countdown, and the pause screenshot's
    ``/runfiles`` URL (D4.1c; read-only in M2)."""
    task = testdb.create_task("svc-w", "user1", enabled=False)
    run = testdb.create_run(task)
    run_dir = config.RUN_DIR / str(run)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "pause_1.png").write_bytes(b"png-pause")
    deadline = (datetime.now() + timedelta(seconds=600)).strftime(
        "%Y-%m-%d %H:%M:%S")
    context = {"reason": "captcha",
               "screenshot": {"path": str(run_dir / "pause_1.png"),
                              "data": "xxx"}}
    testdb.update_run(run, pause_reason="captcha expected",
                      pause_prompt="Solve the captcha",
                      pause_context=json.dumps(context),
                      pause_deadline_at=deadline)
    testdb.set_task_status(task, "waiting")

    await _login(user, testdb)
    await user.open(f"/tasks/{task}")

    await user.should_see("Paused")
    await user.should_see("Reason: captcha expected")
    await user.should_see("Prompt: Solve the captcha")
    (deadline_label,) = user.find(marker="detail-pause-deadline").elements
    assert "remaining" in deadline_label.text
    (shot,) = user.find(marker="detail-pause-shot").elements
    assert shot.source == f"/runfiles/{run}/pause_1.png"
    # M3 S1.1: the card links to the session page (the intervention
    # target, decision 2).
    user.find(marker="detail-pause-open").click()
    await user.should_see(f"Run {run}", retries=10)


async def test_downloads_page_lists_rows_with_the_duplicate_badge(
        user, testdb, tmp_path):
    """The downloads page lists every download, newest first, with the
    duplicate_of badge and the task filter (D4.3)."""
    _seed_detail(testdb, tmp_path)  # two downloads on svc-a
    task2 = testdb.create_task("svc-b", "user1", enabled=False)
    run2 = testdb.create_run(task2)
    testdb.insert_download(run2, task2, "http://dl.example/b.pdf",
                           "report-b.pdf", 999, "fedcba9876543210",
                           str(tmp_path / "b.pdf"))

    await _login(user, testdb)
    await user.open("/downloads")

    (table,) = user.find(kind=ui.table).elements
    rows = table.rows
    assert len(rows) == 3
    assert {r["filename"] for r in rows} == {"invoice-a.pdf", "report-b.pdf"}
    assert sum(1 for r in rows if r["duplicate"] != "—") == 1

    # The task filter narrows to one task's rows.
    (select,) = user.find(marker="downloads-filter").elements
    select.value = "svc-b / user1"
    rows = table.rows
    assert len(rows) == 1
    assert rows[0]["filename"] == "report-b.pdf"
    assert rows[0]["task"] == "svc-b / user1"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
