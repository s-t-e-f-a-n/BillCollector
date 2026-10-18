# -*- coding: utf-8 -*-
"""UI tests for the session page (M3 chunks S1.1-S1.4).

The session page (``/runs/<run_id>``, the ntfy deep-link target, M3
decision 2) is a state machine (M3 decision 3) polled at ~2 s:
``waiting`` (the pause banner + the Copilot / noVNC tabs), ``running``
(the step strip + noVNC), ``ended`` (the result + the last pause
context), and the 404 label for an unknown run id.

S1.4 adds the unit tests for the page's pure functions (``png_dims``,
``overlay_pct``, ``pause_context_summary``; the state mapping is the
S1.1 ``run_state`` test) and the Copilot / running / ended view tests.
The waiting view is driven against a **stubbed** control-socket client:
the session module's ``control_client`` factory is monkeypatched (the
D3.2 shared-module pattern - the test and the runpy'd main file share
the same ``billcollector.ui.session`` module), so no real socket is
needed. Asserted: the numbered overlay badges at their rect-center
percentages, the ``n · role · name`` element select, the badge-tap
selection, the per-action protocol arguments (``click n``, ``fill n +
text``, ``press key``, ``drag n + dx + dy``), the ``resume`` and
``cancel`` dispatch (the cancel requires the confirmation), the
ControlError degrade (a notify, never a crash), the empty-elements
noVNC hint (decision 1), and the noVNC iframe carrying the run's
websockify port (decision 6). The ``running`` view is tested against a
real runfiles tree (the PageStatus step strip), the ``ended`` view with
a seeded ``pause_context``.

The ``waiting`` state needs a live control socket (the pause columns
survive a resume - see ``run_state``), so the waiting seeds bind a real
unix socket file at the Run row's ``control_sock`` path.

M3 chunk S2.4 (the committed S2.3 tests): the **Repair recipe** link
(``/recipes/<service>?run=<run_id>``) is offered for a ``step_failed``
pause - in the waiting view's pause banner and in the ended view (the
pause columns survive the resume) - and never for the other pause
reasons (``wait_user`` ...).
"""

import asyncio
import base64
import json
import os
import socket
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import config  # noqa: E402
from billcollector.control import ControlError  # noqa: E402
from billcollector.db import Database  # noqa: E402
from billcollector.ui import auth, session  # noqa: E402
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


# ---- png_dims (the overlay's PNG size parse, M3 decision 5) ------------

def _png_header(width: int, height: int) -> bytes:
    """A minimal PNG: the 8-byte signature, the 4-byte chunk length, the
    ``IHDR`` type and the big-endian width/height - the 24 bytes
    ``png_dims`` reads (no full image is needed)."""
    return (b"\x89PNG\r\n\x1a\n" + (0).to_bytes(4, "big") + b"IHDR"
            + width.to_bytes(4, "big") + height.to_bytes(4, "big"))


def test_png_dims_reads_the_ihdr_size():
    assert session.png_dims(_png_header(800, 600)) == (800, 600)
    # A decoded screenshot may arrive as bytes or bytearray.
    assert session.png_dims(bytearray(_png_header(12, 34))) == (12, 34)


def test_png_dims_rejects_missing_truncated_and_non_png():
    assert session.png_dims(None) is None
    assert session.png_dims(b"") is None
    assert session.png_dims(_png_header(10, 10)[:23]) is None  # truncated
    assert session.png_dims(b"GIF89a" + b"\x00" * 20) is None  # not a PNG
    bad_ihdr = (b"\x89PNG\r\n\x1a\n" + (0).to_bytes(4, "big")
                + b"IDAT" + b"\x00" * 8)
    assert session.png_dims(bad_ihdr) is None  # no IHDR chunk
    assert session.png_dims(_png_header(0, 10)) is None  # zero width


# ---- overlay_pct (the badge placement, M3 decision 5) -------------------

def test_overlay_pct_centers_the_rect():
    """left = (x + w/2) / img_w, top = (y + h/2) / img_h (percent):
    the rect {10, 20, 200, 40} in a 200x200 image centers at
    (55%, 20%); the 180x30 rect at y 80 centers at (50%, 47.5%)."""
    assert session.overlay_pct({"x": 10, "y": 20, "w": 200, "h": 40},
                               200, 200) == pytest.approx((55.0, 20.0))
    assert session.overlay_pct({"x": 10, "y": 80, "w": 180, "h": 30},
                               200, 200) == pytest.approx((50.0, 47.5))


def test_overlay_pct_guards_zero_size_and_non_numeric_rects():
    rect = {"x": 0, "y": 0, "w": 10, "h": 10}
    assert session.overlay_pct(rect, 0, 100) is None
    assert session.overlay_pct(rect, 100, 0) is None
    assert session.overlay_pct(rect, None, 100) is None
    assert session.overlay_pct({"x": "a", "y": 0, "w": 10, "h": 10},
                               100, 100) is None


# ---- pause_context_summary (the ended view's card) ----------------------

def test_pause_context_summary_parses_the_context():
    row = {"pause_context": json.dumps({
        "reason": "step_failed",
        "prompt": "Solve the captcha",
        "screenshot": {"path": str(config.RUN_DIR / "9999" / "pause_1.png")},
        "elements": [{"n": 1, "role": "button", "name": "Verify"}],
    })}
    summary = session.pause_context_summary(row)
    assert summary["reason"] == "step_failed"
    assert summary["prompt"] == "Solve the captcha"
    assert summary["shot_url"] == "/runfiles/9999/pause_1.png"
    assert summary["elements"] == ["1 · button · Verify"]


def test_pause_context_summary_degrades_on_missing_or_corrupt():
    assert session.pause_context_summary({"pause_context": None}) is None
    assert session.pause_context_summary({"pause_context": ""}) is None
    assert session.pause_context_summary(
        {"pause_context": "{not json"}) is None
    assert session.pause_context_summary(
        {"pause_context": "[1, 2]"}) is None  # not a dict


# ---- NOVNC_SRC_SCRIPT (the iframe src patcher, M3 decision 6) ------------

def test_novnc_src_script_builds_an_absolute_url():
    """The noVNC iframe ``src`` must be an absolute URL: the patcher
    prefixes the ``http://`` scheme to ``window.location.hostname`` (websockify
    serves the noVNC client on plain HTTP). A relative URL (the M3 Wave 1
    pass regression) is resolved against the session page and 404s."""
    assert "'http://' + window.location.hostname" in session.NOVNC_SRC_SCRIPT


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


def _seed_ended_with_pause(db, tmp_path, result="cancelled",
                           pause_reason="step_failed"):
    """An ended run whose ``pause_context`` survived (the ended view's
    last-pause card): a screenshot in the runfiles tree + two elements.
    ``pause_reason`` is the Run column the **Repair recipe** link keys
    on (the context's own ``reason`` is the read-only summary's)."""
    task = db.create_task("svc-p", "user1", enabled=False)
    run = db.create_run(task)
    run_dir = config.RUN_DIR / str(run)
    run_dir.mkdir(parents=True, exist_ok=True)
    shot = run_dir / "pause_1.png"
    shot.write_bytes(b"pause-shot")
    context = {
        "reason": pause_reason,
        "prompt": "The login button was not found",
        "screenshot": {"path": str(shot), "data": "aW1hZ2U="},
        "elements": [
            {"n": 1, "role": "button", "name": "Sign in",
             "rect": {"x": 0, "y": 0, "w": 10, "h": 10}},
            {"n": 2, "role": "textbox", "name": "Password",
             "rect": {"x": 0, "y": 20, "w": 10, "h": 10}},
        ],
    }
    db.update_run(run, result=result, ended_at="2026-10-11 08:00:00",
                  pause_reason=pause_reason,
                  pause_context=json.dumps(context),
                  notes="Paused at the login step")
    return task, run


def _seed_running(db, novnc_port=None):
    task = db.create_task("svc-r", "user1", enabled=False)
    run = db.create_run(task, novnc_port=novnc_port)
    db.set_task_status(task, "running")
    return task, run


def _seed_waiting(db, tmp_path, novnc_port=None,
                  pause_reason="captcha expected"):
    task = db.create_task("svc-w", "user1", enabled=False)
    run = db.create_run(task, novnc_port=novnc_port)
    deadline = (datetime.now() + timedelta(seconds=600)).strftime(
        "%Y-%m-%d %H:%M:%S")
    sock_path = tmp_path / f"run-{run}.sock"
    _bind_socket(sock_path)
    db.update_run(run, pause_reason=pause_reason,
                  pause_prompt="Solve the captcha",
                  pause_deadline_at=deadline,
                  control_sock=str(sock_path))
    db.set_task_status(task, "waiting")
    return task, run, sock_path


# ---- the stubbed control client (D3.2 shared-module pattern) ------------

class StubControlClient:
    """A recording stand-in for ``ControlClient``: the session module's
    client factory is patched to always return this instance, so every
    fetch/action in the page hits it instead of a real socket.
    ``fail_actions`` raise ``ControlError`` (the run-ended-mid-request
    degrade path, decision 4)."""

    def __init__(self, sock_path, elements, shot_b64, fail_actions=()):
        self.sock_path = sock_path
        self.elements = elements
        self.shot_b64 = shot_b64
        self.fail_actions = set(fail_actions)
        self.calls: list[tuple[str, dict]] = []

    def request(self, action, **args):
        self.calls.append((action, args))
        if action in self.fail_actions:
            raise ControlError(f"stub failure for {action}")
        if action == "screenshot":
            return {"screenshot": self.shot_b64}
        if action == "elements":
            return {"elements": self.elements}
        return {}


def _stub_control(monkeypatch, elements, shot_b64, fail_actions=()):
    """Patch the session module's client factory to one shared stub and
    return it (the call record survives the per-request factory)."""
    client = StubControlClient("", elements, shot_b64, fail_actions)
    monkeypatch.setattr(session, "control_client", lambda path: client)
    return client


# The 200x200 "screenshot" and the element list the waiting tests share
# (badge centers: n1 55.00/20.00, n2 50.00/47.50, n3 30.00/75.00).
SHOT_B64 = base64.b64encode(_png_header(200, 200)).decode()
ELEMENTS = [
    {"n": 1, "role": "button", "name": "I am not a robot",
     "rect": {"x": 10, "y": 20, "w": 200, "h": 40},
     "actionTypes": ["click"]},
    {"n": 2, "role": "textbox", "name": "verification code",
     "rect": {"x": 10, "y": 80, "w": 180, "h": 30},
     "actionTypes": ["fill"]},
    {"n": 3, "role": "button", "name": "Verify",
     "rect": {"x": 10, "y": 130, "w": 100, "h": 40},
     "actionTypes": ["click"]},
]


async def _wait(predicate, message: str, timeout: float = 2.0) -> None:
    """Poll until ``predicate()`` holds (the action handlers are async
    tasks on the simulation's loop)."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError(message)
        await asyncio.sleep(0.01)


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
    # A non-step_failed pause does not offer the candidate picker.
    await user.should_not_see(marker="session-repair")


async def test_waiting_view_offers_the_repair_recipe_link(user, testdb,
                                                          tmp_path,
                                                          monkeypatch):
    """A ``step_failed`` pause (M3 S2.3, decision 7): the pause banner
    offers the **Repair recipe** link to the editor with the run's
    failure context preloaded."""
    _stub_control(monkeypatch, ELEMENTS, SHOT_B64)
    task, run, _sock = _seed_waiting(testdb, tmp_path,
                                     pause_reason="step_failed")
    await _login(user, testdb)
    await user.open(f"/runs/{run}")

    (badge,) = user.find(marker="session-state").elements
    assert badge.text == "waiting"
    (link,) = user.find(marker="session-repair").elements
    assert link.text == "Repair recipe"
    assert link._props["href"] == f"/recipes/svc-w?run={run}"


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


# ---- the waiting view (Copilot, M3 decisions 1/4/5/6) ---------------------

async def test_waiting_view_renders_the_overlay_and_novnc(user, testdb,
                                                          tmp_path,
                                                          monkeypatch):
    """The Copilot view: the live screenshot with the numbered overlay
    (the badges at their rect-center percentages, decision 5), the
    ``n · role · name`` element select, and the noVNC iframe carrying
    the run's websockify port (decision 6). The initial fetch lands
    before the page is returned - the operator sees the page
    immediately, not on the first ~5 s tick."""
    client = _stub_control(monkeypatch, ELEMENTS, SHOT_B64)
    task, run, _sock = _seed_waiting(testdb, tmp_path, novnc_port=6081)
    await _login(user, testdb)
    await user.open(f"/runs/{run}")

    (badge,) = user.find(marker="session-state").elements
    assert badge.text == "waiting"
    await user.should_see(marker="session-screenshot")
    for n, left, top in ((1, "55.00%", "20.00%"),
                         (2, "50.00%", "47.50%"),
                         (3, "30.00%", "75.00%")):
        (b,) = user.find(marker=f"session-badge-{n}").elements
        assert b.text == str(n)
        assert b.style["left"] == left
        assert b.style["top"] == top
    (sel,) = user.find(marker="session-elem-select").elements
    assert sel.options == {
        1: "1 · button · I am not a robot",
        2: "2 · textbox · verification code",
        3: "3 · button · Verify",
    }
    (html,) = user.find(marker="session-novnc").elements
    assert 'data-novnc-port="6081"' in html.content
    # The initial fetch hit the stub (screenshot + elements).
    assert ("screenshot", {}) in client.calls
    assert ("elements", {}) in client.calls


async def test_waiting_view_no_novnc_port_shows_a_hint(user, testdb,
                                                       tmp_path,
                                                       monkeypatch):
    """A waiting run without an allocated display (novnc_port None)
    renders a hint instead of a dead iframe."""
    _stub_control(monkeypatch, ELEMENTS, SHOT_B64)
    task, run, _sock = _seed_waiting(testdb, tmp_path)
    await _login(user, testdb)
    await user.open(f"/runs/{run}")

    (hint,) = user.find(marker="session-novnc-unavailable").elements
    assert "not available" in hint.text
    await user.should_not_see(marker="session-novnc")


async def test_badge_tap_selects_the_element(user, testdb, tmp_path,
                                             monkeypatch):
    """Tapping a numbered badge selects the element into the action bar
    (mobile-first, decision 5): the select's value updates and the
    per-element actions re-sync (element 2 is fill-only: fill and drag
    enabled, click disabled)."""
    _stub_control(monkeypatch, ELEMENTS, SHOT_B64)
    task, run, _sock = _seed_waiting(testdb, tmp_path)
    await _login(user, testdb)
    await user.open(f"/runs/{run}")

    await user.should_see(marker="session-badge-2")
    user.find(marker="session-badge-2").click()
    (sel,) = user.find(marker="session-elem-select").elements
    assert sel.value == 2
    (click,) = user.find(marker="session-click").elements
    (fill,) = user.find(marker="session-fill").elements
    (drag,) = user.find(marker="session-drag").elements
    assert not click.enabled
    assert fill.enabled
    assert drag.enabled


async def test_click_dispatches_the_element_number(user, testdb, tmp_path,
                                                   monkeypatch):
    client = _stub_control(monkeypatch, ELEMENTS, SHOT_B64)
    task, run, _sock = _seed_waiting(testdb, tmp_path)
    await _login(user, testdb)
    await user.open(f"/runs/{run}")

    (sel,) = user.find(marker="session-elem-select").elements
    sel.value = 1
    user.find(marker="session-click").click()
    await _wait(lambda: any(a == "click" for a, _ in client.calls),
                "the click action was not dispatched")
    assert ("click", {"n": 1}) in client.calls


async def test_fill_dispatches_the_element_and_the_text(user, testdb,
                                                        tmp_path, monkeypatch):
    client = _stub_control(monkeypatch, ELEMENTS, SHOT_B64)
    task, run, _sock = _seed_waiting(testdb, tmp_path)
    await _login(user, testdb)
    await user.open(f"/runs/{run}")

    (sel,) = user.find(marker="session-elem-select").elements
    sel.value = 2
    user.find(marker="session-fill-input").type("123456")
    user.find(marker="session-fill").click()
    await _wait(lambda: any(a == "fill" for a, _ in client.calls),
                "the fill action was not dispatched")
    assert ("fill", {"n": 2, "text": "123456"}) in client.calls


async def test_press_dispatches_the_key_without_a_selection(user, testdb,
                                                            tmp_path,
                                                            monkeypatch):
    client = _stub_control(monkeypatch, ELEMENTS, SHOT_B64)
    task, run, _sock = _seed_waiting(testdb, tmp_path)
    await _login(user, testdb)
    await user.open(f"/runs/{run}")

    user.find(marker="session-press-input").type("Enter")
    user.find(marker="session-press").click()
    await _wait(lambda: any(a == "press" for a, _ in client.calls),
                "the press action was not dispatched")
    assert ("press", {"key": "Enter"}) in client.calls


async def test_drag_dispatches_the_element_and_dx_dy(user, testdb, tmp_path,
                                                     monkeypatch):
    client = _stub_control(monkeypatch, ELEMENTS, SHOT_B64)
    task, run, _sock = _seed_waiting(testdb, tmp_path)
    await _login(user, testdb)
    await user.open(f"/runs/{run}")

    (sel,) = user.find(marker="session-elem-select").elements
    sel.value = 1
    (dx,) = user.find(marker="session-drag-dx").elements
    (dy,) = user.find(marker="session-drag-dy").elements
    dx.value = 250
    dy.value = -10
    user.find(marker="session-drag").click()
    await _wait(lambda: any(a == "drag" for a, _ in client.calls),
                "the drag action was not dispatched")
    assert ("drag", {"n": 1, "dx": 250.0, "dy": -10.0}) in client.calls


async def test_resume_dispatches_the_protocol_action(user, testdb, tmp_path,
                                                     monkeypatch):
    client = _stub_control(monkeypatch, ELEMENTS, SHOT_B64)
    task, run, _sock = _seed_waiting(testdb, tmp_path)
    await _login(user, testdb)
    await user.open(f"/runs/{run}")

    user.find(marker="session-resume").click()
    await _wait(lambda: any(a == "resume" for a, _ in client.calls),
                "the resume action was not dispatched")
    assert ("resume", {}) in client.calls


async def test_cancel_requires_confirmation_then_dispatches(user, testdb,
                                                            tmp_path,
                                                            monkeypatch):
    client = _stub_control(monkeypatch, ELEMENTS, SHOT_B64)
    task, run, _sock = _seed_waiting(testdb, tmp_path)
    await _login(user, testdb)
    await user.open(f"/runs/{run}")

    user.find(marker="session-cancel").click()
    await user.should_see("Cancel the run?")
    # Nothing is sent before the confirmation.
    assert not any(a == "cancel" for a, _ in client.calls)
    user.find(marker="session-cancel-confirm").click()
    await _wait(lambda: any(a == "cancel" for a, _ in client.calls),
                "the cancel action was not dispatched")
    assert ("cancel", {}) in client.calls


async def test_copilot_refresh_control_error_degrades_to_a_notify(user,
                                                                  testdb,
                                                                  tmp_path,
                                                                  monkeypatch):
    """A ControlError on the fetch (the run ended mid-request) degrades
    to a notify + the DB state refresh - the page never crashes
    (decision 4)."""
    _stub_control(monkeypatch, ELEMENTS, SHOT_B64,
                  fail_actions=("screenshot",))
    task, run, _sock = _seed_waiting(testdb, tmp_path)
    await _login(user, testdb)
    await user.open(f"/runs/{run}")

    assert user.notify.contains("Session refresh failed")
    # The page is alive: the waiting banner is intact, no overlay.
    await user.should_see("Paused")
    await user.should_not_see(marker="session-badge-1")


async def test_action_control_error_degrades_to_a_notify(user, testdb,
                                                         tmp_path,
                                                         monkeypatch):
    """A ControlError on an action (the run ended mid-request) degrades
    to a notify + the DB state refresh - the page never crashes
    (decision 4)."""
    _stub_control(monkeypatch, ELEMENTS, SHOT_B64, fail_actions=("click",))
    task, run, _sock = _seed_waiting(testdb, tmp_path)
    await _login(user, testdb)
    await user.open(f"/runs/{run}")

    await user.should_see(marker="session-badge-1")
    (sel,) = user.find(marker="session-elem-select").elements
    sel.value = 1
    user.find(marker="session-click").click()
    await _wait(lambda: user.notify.contains("click failed"),
                "the failed action was not reported")
    # The page is alive after the failed action.
    await user.should_see("Paused")


async def test_empty_elements_shows_the_novnc_hint(user, testdb, tmp_path,
                                                   monkeypatch):
    """An empty element list (the drag CAPTCHA pause) is a state, not an
    error: the noVNC hint shows and the select hides (decision 1)."""
    _stub_control(monkeypatch, [], SHOT_B64)
    task, run, _sock = _seed_waiting(testdb, tmp_path)
    await _login(user, testdb)
    await user.open(f"/runs/{run}")

    (hint,) = user.find(marker="session-novnc-hint").elements
    assert "noVNC" in hint.text
    await user.should_not_see(marker="session-elem-select")
    await user.should_not_see(marker="session-badge-1")


# ---- the running view (M3 decision 3, the PageStatus DB pattern) ---------

async def test_running_view_shows_step_screenshots_and_no_action_bar(
        user, testdb, tmp_path):
    """The running view is read-only: the step strip renders the run's
    PageStatus screenshots from the real runfiles tree (the dashboard
    step-strip pattern) and the noVNC tab is available while the run is
    alive - there is no action bar."""
    task, run = _seed_running(testdb, novnc_port=6082)
    run_dir = config.RUN_DIR / str(run)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "step_1.png").write_bytes(b"step-1")
    testdb.insert_page_status(run, 1, screenshot_path=str(run_dir / "step_1.png"))
    (run_dir / "step_2.png").write_bytes(b"step-2")
    testdb.insert_page_status(run, 2, screenshot_path=str(run_dir / "step_2.png"))
    await _login(user, testdb)
    await user.open(f"/runs/{run}")

    (badge,) = user.find(marker="session-state").elements
    assert badge.text == "running"
    thumbs = user.find(marker="session-step-thumb").elements
    assert sorted(img.source for img in thumbs) == sorted(
        [f"/runfiles/{run}/step_1.png", f"/runfiles/{run}/step_2.png"])
    await user.should_not_see(marker="session-actionbar")
    await user.should_not_see(marker="session-elem-select")
    (html,) = user.find(marker="session-novnc").elements
    assert 'data-novnc-port="6082"' in html.content


# ---- the ended view (M3 decision 3, the last pause context) ---------------

async def test_ended_run_shows_result_and_last_pause_context(user, testdb,
                                                             tmp_path):
    """The ended view: the result summary and, when ``pause_context``
    survived, the last pause read-only (reason, prompt, the screenshot's
    /runfiles URL, the element lines). No noVNC - the display stack is
    reaped with the run."""
    task, run = _seed_ended_with_pause(testdb, tmp_path)
    await _login(user, testdb)
    await user.open(f"/runs/{run}")

    (badge,) = user.find(marker="session-state").elements
    assert badge.text == "ended"
    await user.should_see("Finished: cancelled")
    await user.should_see("Notes: Paused at the login step")
    await user.should_see("Reason: step_failed")
    await user.should_see("Prompt: The login button was not found")
    (img,) = user.find(marker="session-last-pause-shot").elements
    assert img.source == f"/runfiles/{run}/pause_1.png"
    await user.should_see("1 · button · Sign in")
    await user.should_see("2 · textbox · Password")
    await user.should_not_see(marker="session-novnc")


async def test_ended_step_failed_run_offers_the_repair_recipe_link(
        user, testdb, tmp_path):
    """The pause columns survive the resume (M3 S2.3): a ``step_failed``
    run that ended still offers the candidate picker on its last
    failure."""
    task, run = _seed_ended_with_pause(testdb, tmp_path)
    await _login(user, testdb)
    await user.open(f"/runs/{run}")

    (badge,) = user.find(marker="session-state").elements
    assert badge.text == "ended"
    (link,) = user.find(marker="session-repair").elements
    assert link.text == "Repair recipe"
    assert link._props["href"] == f"/recipes/svc-p?run={run}"


async def test_ended_wait_user_run_has_no_repair_recipe_link(user, testdb,
                                                             tmp_path):
    """A ``wait_user`` pause is not a step failure: the ended view offers
    no **Repair recipe** link (the YAML path)."""
    task, run = _seed_ended_with_pause(testdb, tmp_path,
                                       pause_reason="wait_user")
    await _login(user, testdb)
    await user.open(f"/runs/{run}")

    (badge,) = user.find(marker="session-state").elements
    assert badge.text == "ended"
    await user.should_not_see(marker="session-repair")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
