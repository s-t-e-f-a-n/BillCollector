# -*- coding: utf-8 -*-
"""The session page (M3 chunk S1.1).

``/runs/<run_id>`` is the operator's intervention page - the ntfy deep
link target (M3 decision 2); it replaces the M2 redirect to the task
detail. The page is a state machine (M3 decision 3) polled from the DB
at the same ~2 s regime as the other pages:

- ``waiting`` -> the pause banner (reason, prompt, deadline countdown);
  the Copilot view (live screenshot, the numbered overlay, the element
  actions, Resume / Cancel) lands in S1.2
- ``running`` -> read-only observation; the latest step screenshots and
  the noVNC tab land in S1.3
- ``ended``   -> the result (``success`` / ``failure`` / ``interrupted``
  / ``cancelled`` / ``needs_attention``); the result summary and the
  read-only last pause context land in S1.3
- an unknown run id -> the 404 label (the M2 behavior)

The Run row's pause columns are not cleared when a pause resolves (a
resume keeps ``pause_reason`` / ``pause_context`` so the ended view can
still show the last pause), so the state of an open run is decided by
the control socket's liveness (see :func:`run_state`), not by
``pause_reason`` alone.
"""

import os

from fastapi import Request
from nicegui import ui

from ..db import Database
from .auth import require_auth
from .format import deadline_text
from .layout import build_layout

# The ~2 s DB poll regime (the other pages' interval).
REFRESH_INTERVAL = 2.0

# The badge colors of the page states (the dashboard's status colors).
STATE_COLORS = {"waiting": "orange", "running": "blue", "ended": "grey"}


def control_sock_alive(run) -> bool:
    """Whether the run's control socket is live: its file (bound while
    the waiting loop serves it, unlinked on resume, cancel, timeout, or
    shutdown) still exists. A ``control_sock`` left behind by a
    resolved pause reads as dead."""
    path = run["control_sock"]
    return bool(path) and os.path.exists(path)


def run_state(run, sock_alive: bool) -> str:
    """The session-page state of a Run row (M3 decision 3): ``unknown``
    (no row), ``ended`` (a result is set), ``waiting`` (an open run with
    an active pause), ``running`` (open, no active pause).

    ``sock_alive`` (see :func:`control_sock_alive`) distinguishes a
    live pause from a run executing after its pause was resolved - the
    pause columns survive the resume (the ended view still shows the
    last pause context)."""
    if run is None:
        return "unknown"
    if run["result"] is not None:
        return "ended"
    if run["pause_reason"] and sock_alive:
        return "waiting"
    return "running"


def _render_state(box, run, state, refs) -> None:
    """The state's content (the S1.1 scaffold; S1.2/S1.3 replace the
    waiting / running / ended bodies in place). ``refs`` carries the
    per-poll update target across re-renders (the waiting banner's
    deadline label)."""
    refs["deadline"] = None
    with box:
        if state == "waiting":
            with ui.card().classes("w-full bg-orange-50").mark("session-pause"):
                ui.label("Paused").classes("text-orange-900 text-h6")
                if run["pause_reason"]:
                    ui.label(f"Reason: {run['pause_reason']}") \
                        .mark("session-pause-reason")
                if run["pause_prompt"]:
                    ui.label(f"Prompt: {run['pause_prompt']}") \
                        .mark("session-pause-prompt")
                refs["deadline"] = ui.label("").mark("session-pause-deadline")
        elif state == "running":
            ui.label("Running").classes("text-h6").mark("session-running")
        else:
            ui.label(f"Finished: {run['result']}") \
                .classes("text-h6").mark("session-ended")


def register_session(db: Database) -> None:
    """Register the session page (``/runs/<run_id>``; M3 decision 2 - the
    ntfy deep link target, replacing the M2 task-detail redirect)."""

    @ui.page("/runs/{run_id}")
    def session_page(request: Request, run_id: int) -> None:
        redirect = require_auth(request)
        if redirect is not None:
            return redirect
        build_layout()
        run = db.get_run(run_id)
        if run is None:
            ui.label(f"Unknown run id: {run_id} (404)").classes("text-red-600")
            return

        # ---- Header -----------------------------------------------------
        ui.label(f"Run {run_id}").classes("text-h4 font-bold") \
            .mark("session-title")
        task = db.get_task(run["task_id"])
        if task is not None:
            ui.link(f"Task {task['id']}: {task['service']} / "
                    f"{task['user'] or '—'}",
                    f"/tasks/{task['id']}").mark("session-task-link")

        # ---- State machine (M3 decision 3, the ~2 s poll) ---------------
        refs = {"deadline": None}
        state = run_state(run, control_sock_alive(run))
        state_badge = ui.badge(
            state, color=STATE_COLORS.get(state, "grey")).mark("session-state")
        content_box = ui.column().classes("w-full").mark("session-content")
        state_sig = {"sig": state}
        _render_state(content_box, run, state, refs)
        if state == "waiting" and refs["deadline"] is not None:
            refs["deadline"].set_text(deadline_text(run["pause_deadline_at"]))

        def refresh() -> None:
            run_row = db.get_run(run_id)
            if run_row is None:
                return
            new_state = run_state(run_row, control_sock_alive(run_row))
            state_badge.set_text(new_state)
            state_badge.props(f"color={STATE_COLORS.get(new_state, 'grey')}")
            if new_state != state_sig["sig"]:
                state_sig["sig"] = new_state
                content_box.clear()
                _render_state(content_box, run_row, new_state, refs)
            if new_state == "waiting" and refs["deadline"] is not None:
                refs["deadline"].set_text(
                    deadline_text(run_row["pause_deadline_at"]))

        ui.timer(REFRESH_INTERVAL, refresh)
        refresh()
