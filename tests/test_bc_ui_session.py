# -*- coding: utf-8 -*-
"""UI tests for the session page (M3 chunk S1.1).

The session page (``/runs/<run_id>``, the ntfy deep-link target, M3
decision 2) is a state machine (M3 decision 3) polled at ~2 s:
``waiting`` (the pause banner), ``running``, ``ended``, and the 404
label for an unknown run id. The S1.1 scaffold renders the header (run
id + the task-detail link), the state badge, and the per-state body;
the Copilot view (S1.2) and the noVNC / running / ended bodies (S1.3)
land on top of it. The M2 dashboard redirect tests move here with the
route (the updated known-id test asserts the session page, not a
redirect).

The ``waiting`` state needs a live control socket (the pause columns
survive a resume - see ``run_state``), so the waiting seeds bind a real
unix socket file at the Run row's ``control_sock`` path.
"""

import os
import socket
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector.db import Database  # noqa: E402
from billcollector.ui import auth  # noqa: E402
from billcollector.ui.session import run_state  # noqa: E402

GOOD_PASSWORD = "ui-test-pass-1"


# ---- run_state (the pure state mapping, M3 decision 3) -----------------

def test_run_state_maps_the_row_and_the_socket():
    """The state of a Run row: the result wins (ended), an open run is
    waiting only while its control socket is live (the pause columns
    survive a resume), and a missing row is unknown."""
    open_row = {"result": None, "pause_reason": None}
    assert run_state(None, False) == "unknown"
    assert run_state({**open_row, "result": "success"}, True) == "ended"
    # The stale case: a cancelled run keeps its pause columns (the
    # ended view shows the last pause context) - the result still wins.
    assert run_state({**open_row, "result": "cancelled",
                      "pause_reason": "step_failed"}, True) == "ended"
    assert run_state({**open_row, "pause_reason": "step_failed"},
                     True) == "waiting"
    # Resumed: the pause columns are set but the socket is dead.
    assert run_state({**open_row, "pause_reason": "step_failed"},
                     False) == "running"
    assert run_state(open_row, False) == "running"


# ---- fixtures and seeds --------------------------------------------------

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


def _bind_socket(path) -> None:
    """Bind (and leave) a unix socket file at ``path``: its presence is
    what ``control_sock_alive`` sees (the ControlServer unlinks it in
    ``close``)."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(path))
    sock.close()


def _seed_ended(db, result="success"):
    task = db.create_task("svc-e", "user1", enabled=False)
    run = db.create_run(task)
    db.update_run(run, result=result, ended_at="2026-10-11 08:00:00")
    return task, run


def _seed_running(db):
    task = db.create_task("svc-r", "user1", enabled=False)
    run = db.create_run(task)
    db.set_task_status(task, "running")
    return task, run


def _seed_waiting(db, tmp_path):
    task = db.create_task("svc-w", "user1", enabled=False)
    run = db.create_run(task)
    deadline = (datetime.now() + timedelta(seconds=600)).strftime(
        "%Y-%m-%d %H:%M:%S")
    sock_path = tmp_path / f"run-{run}.sock"
    _bind_socket(sock_path)
    db.update_run(run, pause_reason="captcha expected",
                  pause_prompt="Solve the captcha",
                  pause_deadline_at=deadline,
                  control_sock=str(sock_path))
    db.set_task_status(task, "waiting")
    return task, run, sock_path


# ---- page tests ------------------------------------------------------------

async def test_unknown_run_id_shows_a_404(user, testdb):
    """An unknown run id renders the 404 label (the M2 behavior)."""
    await _login(user, testdb)
    await user.open("/runs/9999")
    await user.should_see("Unknown run id: 9999 (404)")


async def test_known_run_id_shows_the_session_page(user, testdb):
    """The M2 redirect is gone (M3 S1.1): a known run id renders the
    session page - the run header, the ended state badge, the result,
    and the task-detail link."""
    task, run = _seed_ended(testdb, "success")
    await _login(user, testdb)
    await user.open(f"/runs/{run}")

    await user.should_see(f"Run {run}")
    (badge,) = user.find(marker="session-state").elements
    assert badge.text == "ended"
    await user.should_see("Finished: success")
    # The task link navigates to the task detail page.
    user.find(marker="session-task-link").click()
    await user.should_see(f"Task {task}: svc-e / user1", retries=10)


async def test_running_run_shows_the_running_state(user, testdb):
    task, run = _seed_running(testdb)
    await _login(user, testdb)
    await user.open(f"/runs/{run}")

    (badge,) = user.find(marker="session-state").elements
    assert badge.text == "running"
    await user.should_see("Running")


async def test_waiting_run_shows_the_pause_banner(user, testdb, tmp_path):
    """While the pause is live (socket bound): the waiting badge and the
    banner (reason, prompt, deadline countdown)."""
    task, run, _sock = _seed_waiting(testdb, tmp_path)
    await _login(user, testdb)
    await user.open(f"/runs/{run}")

    (badge,) = user.find(marker="session-state").elements
    assert badge.text == "waiting"
    await user.should_see("Paused")
    await user.should_see("Reason: captcha expected")
    await user.should_see("Prompt: Solve the captcha")
    (deadline_label,) = user.find(marker="session-pause-deadline").elements
    assert "remaining" in deadline_label.text


async def test_state_flips_to_running_when_the_socket_closes(user, testdb,
                                                             tmp_path):
    """The pause columns survive a resume (the socket is unlinked, the
    row is not): the ~2 s poll re-evaluates the socket and flips the
    badge and the body from waiting to running."""
    task, run, sock_path = _seed_waiting(testdb, tmp_path)
    await _login(user, testdb)
    await user.open(f"/runs/{run}")
    (badge,) = user.find(marker="session-state").elements
    assert badge.text == "waiting"

    os.unlink(str(sock_path))
    await user.should_see("Running", retries=20)
    (badge,) = user.find(marker="session-state").elements
    assert badge.text == "running"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
