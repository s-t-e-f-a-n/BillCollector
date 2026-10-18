# -*- coding: utf-8 -*-
"""The session page (M3 chunks S1.1-S1.3).

``/runs/<run_id>`` is the operator's intervention page - the ntfy deep
link target (M3 decision 2); it replaces the M2 redirect to the task
detail. The page is a state machine (M3 decision 3) polled from the DB
at the same ~2 s regime as the other pages:

- ``waiting`` -> the pause banner (reason, prompt, deadline countdown)
  and the tabs (S1.3): the Copilot view (S1.2, active by default) with
  the live screenshot + numbered overlay (decision 5), the element
   select (``n · role · name``), the action bar (click / fill / press /
   drag per the element's ``actionTypes``), **Resume** and **Cancel**
   (confirmation dialog -> the protocol ``cancel``), the initial
   screenshot/elements fetch on page load, the ~5 s poll and the
   immediate post-action refresh (decision 4), an empty ``elements``
   list rendering the noVNC hint (decision 1) - and the noVNC tab
   (decision 6)
- ``running`` -> read-only observation (S1.3): the run's step
  screenshots (the ``PageStatus`` DB pattern, the dashboard step strip;
  the strip fills in live as new rows land) and the noVNC tab
  (decision 6), the step strip active by default
- ``ended``   -> the result (``success`` / ``failure`` / ``interrupted``
  / ``cancelled`` / ``needs_attention``) and, when ``pause_context`` is
  set, the last pause context read-only (reason, prompt, screenshot,
  elements). No noVNC (the display stack is reaped)
- an unknown run id -> the 404 label (the M2 behavior)

The **Repair recipe** link (M3 chunk S2.3, decision 7) is offered for a
``step_failed`` pause - while the run is waiting and after it has
ended (the pause columns survive the resume): it links to the recipe
editor with the run's failure context preloaded
(``/recipes/<service>?run=<run_id>``), where the candidate picker is
the primary repair path.

The noVNC tab (M3 decision 6) is a full-size iframe whose ``src`` is
built *client-side* (the ``NOVNC_SRC_SCRIPT`` body script) from
``window.location.hostname`` and the run's websockify port (the
iframe's ``data-novnc-port`` attribute) - one URL works for a
localhost operator and a LAN operator (websockify listens on all
interfaces, x11vnc is ``-localhost``). The RFB password (the
``vnc_password`` setting) is entered in noVNC's own prompt, never in
the URL.

The Run row's pause columns are not cleared when a pause resolves (a
resume keeps ``pause_reason`` / ``pause_context`` so the ended view can
still show the last pause), so the state of an open run is decided by
the control socket's liveness (see :func:`run_state`), not by
``pause_reason`` alone.

Every control-socket request opens a short-lived client (decision 4) and
runs in a worker thread - the blocking socket call must never sit on
the UI event loop; all element updates happen back on the loop.
"""

import asyncio
import base64
import json
import os

from fastapi import Request
from nicegui import ui

from ..control import ControlClient, ControlError
from ..db import Database
from .auth import require_auth
from .format import deadline_text
from .layout import build_layout
from .runfiles import runfile_url

# The ~2 s DB poll regime (the other pages' interval).
REFRESH_INTERVAL = 2.0

# The Copilot poll (M3 decision 4): while waiting, the live screenshot
# and the element list are re-fetched every ~5 s (the page changes
# after an action), plus an immediate refresh right after every action.
COPILOT_REFRESH_INTERVAL = 5.0

# The badge colors of the page states (the dashboard's status colors).
STATE_COLORS = {"waiting": "orange", "running": "blue", "ended": "grey"}

# The empty-elements hint (M3 decision 1): a pause whose scan found no
# interactive element (the drag CAPTCHA is the standing case) is a
# state, not an error - the operator uses the noVNC view instead.
EMPTY_ELEMENTS_HINT = (
    "No interactive elements were detected on this page. "
    "Use the noVNC view to operate the page directly.")

# The numbered overlay badges (M3 decision 5): plain elements (no slot
# template), positioned absolutely by percentage over the screenshot.
BADGE_CLASSES = (
    "absolute -translate-x-1/2 -translate-y-1/2 rounded-full bg-blue-600 "
    "text-white text-xs font-bold w-6 h-6 flex items-center justify-center "
    "cursor-pointer z-10")

# The noVNC src patcher (M3 decision 6): registered once per page via
# ui.add_body_html (ui.html cannot carry scripts). A MutationObserver
# finds every noVNC iframe (the state bodies are re-rendered on state
# changes, so the iframe may appear after the script ran) and sets its
# src from window.location.hostname + data-novnc-port - one URL works
# for a localhost operator and a LAN operator.
NOVNC_SRC_SCRIPT = """
<script>
(function () {
  function patch(frame) {
    var port = frame.getAttribute('data-novnc-port');
    if (port && !frame.getAttribute('src')) {
      frame.src = 'http://' + window.location.hostname + ':' + port +
        '/vnc.html?autoconnect=true';
    }
  }
  function patchAll() {
    document.querySelectorAll('iframe[data-novnc-port]').forEach(patch);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', patchAll);
  } else {
    patchAll();
  }
  new MutationObserver(patchAll).observe(document.body,
    {childList: true, subtree: true});
})();
</script>
"""


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


def png_dims(data) -> tuple[int, int] | None:
    """The width and height of a PNG in bytes, read from the first
    chunk: the 8-byte signature, the 4-byte chunk length, the ``IHDR``
    type, then the 4-byte big-endian width and height at bytes 16-24 -
    no dependency (M3 decision 5: the overlay only needs the size).
    None when the data is missing, truncated, not a PNG signature, or
    does not start with an IHDR chunk: a non-PNG/corrupt screenshot
    renders without an overlay (the screenshot and the element list
    stay usable)."""
    if not isinstance(data, (bytes, bytearray)) or len(data) < 24:
        return None
    if bytes(data[:8]) != b"\x89PNG\r\n\x1a\n":
        return None
    if bytes(data[12:16]) != b"IHDR":
        return None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    if width <= 0 or height <= 0:
        return None
    return width, height


def overlay_pct(rect, img_w: int, img_h: int) -> tuple[float, float] | None:
    """The center of an element ``rect`` (``{x, y, w, h}`` viewport
    pixels) as a percentage of the screenshot's pixel size (M3
    decision 5): ``left = (x + w/2) / img_w``, ``top = (y + h/2) /
    img_h``, each times 100. None when the image size is unusable (the
    zero-size guard), the rect is missing, or its values are not
    numeric - one bad rect must not kill the overlay."""
    if img_w is None or img_h is None or img_w <= 0 or img_h <= 0:
        return None
    rect = rect or {}
    try:
        x = float(rect.get("x", 0))
        y = float(rect.get("y", 0))
        w = float(rect.get("w", 0))
        h = float(rect.get("h", 0))
    except (TypeError, ValueError):
        return None
    return (x + w / 2) / img_w * 100, (y + h / 2) / img_h * 100


def novnc_iframe_html(port: int) -> str:
    """The noVNC tab's iframe (M3 decision 6): the noVNC web client,
    whose ``src`` is built *client-side* (the page-level
    ``NOVNC_SRC_SCRIPT``) from ``window.location.hostname`` and the
    run's websockify port (``data-novnc-port``) - one URL works for a
    localhost operator and a LAN operator (websockify listens on all
    interfaces, x11vnc is ``-localhost``). The RFB password is entered
    in noVNC's own prompt - never in the URL."""
    return (f"<iframe data-novnc-port=\"{port}\" "
            "class='w-full rounded' "
            "style='height: 70vh; border: 1px solid #cbd5e1; "
            "background: #0f172a;'></iframe>")


def pause_context_summary(run) -> dict | None:
    """The ended view's last pause context (M3 decision 3), parsed from
    ``Run.pause_context``: ``reason``, ``prompt``, the screenshot's
    ``/runfiles`` URL, and the elements as ``n · role · name`` lines.
    None when the column is empty or the JSON is corrupt - a broken
    context must not kill the ended view (the card is just omitted)."""
    if not run["pause_context"]:
        return None
    try:
        context = json.loads(run["pause_context"])
    except (TypeError, ValueError):
        return None
    if not isinstance(context, dict):
        return None
    shot = context.get("screenshot")
    shot_path = shot.get("path") if isinstance(shot, dict) else None
    elements = []
    for el in context.get("elements") or []:
        if not isinstance(el, dict):
            continue
        elements.append(
            f"{el.get('n')} · {el.get('role')} · {el.get('name')}")
    return {
        "reason": context.get("reason"),
        "prompt": context.get("prompt"),
        "shot_url": runfile_url(shot_path),
        "elements": elements,
    }


def repair_recipe_url(run, task) -> str | None:
    """The session page's **Repair recipe** link (M3 S2.3, decision 7):
    for a ``step_failed`` pause (waiting or ended), the recipe editor
    with the run's failure context preloaded
    (``/recipes/<service>?run=<run_id>``). None for the other pause
    reasons (``wait_user``, ``download_failed`` - the YAML path) and
    for a run whose task row is missing."""
    if run["pause_reason"] != "step_failed" or task is None:
        return None
    return f"/recipes/{task['service']}?run={run['id']}"


def control_client(sock_path: str) -> ControlClient:
    """One short-lived control-socket client (M3 decision 4): the UI
    opens a fresh client per request (the socket lives under
    ``BC_DATA_DIR``, shared with the runner). Module-level so the UI
    tests can stub it (the D3.2 shared-module pattern) without a real
    socket."""
    return ControlClient(sock_path)


def send_action(sock_path: str, action: str, **args) -> dict:
    """One control request (blocking; called from a worker thread, never
    the UI event loop). Returns the response payload, raises
    :class:`ControlError` on transport failure or an ``ok: false``
    response."""
    return control_client(sock_path).request(action, **args)


def fetch_copilot(sock_path: str) -> tuple[str, list]:
    """One Copilot fetch (blocking; called from a worker thread): the
    live screenshot (base64) and the numbered element list."""
    client = control_client(sock_path)
    shot = client.request("screenshot").get("screenshot", "")
    elements = client.request("elements").get("elements", [])
    return shot, elements


def _render_state(box, run, state, refs, renderers) -> None:
    """The state's content (M3 decision 3): ``renderers`` maps each
    state to the page's view renderer (waiting S1.2, running / ended
    S1.3); ``refs`` carries the per-poll update targets across
    re-renders (the deadline label, the Copilot timer, the step strip)."""
    refs["deadline"] = None
    refs["copilot_timer"] = None
    refs["steps_box"] = None
    refs["steps_sig"] = None
    with box:
        renderers[state](box, run, refs)


def register_session(db: Database) -> None:
    """Register the session page (``/runs/<run_id>``; M3 decision 2 - the
    ntfy deep link target, replacing the M2 task-detail redirect)."""

    @ui.page("/runs/{run_id}")
    async def session_page(request: Request, run_id: int) -> None:
        redirect = require_auth(request)
        if redirect is not None:
            return redirect
        build_layout()
        # The noVNC iframes of the alive states get their src client-side
        # (M3 decision 6): one URL works for localhost and LAN operators.
        ui.add_body_html(NOVNC_SRC_SCRIPT)
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

        # ---- State views (waiting S1.2, running / ended S1.3) ------------
        refs: dict = {}

        def selected_element() -> dict | None:
            """The element of the select's current value from the last
            fetched list (None when nothing is selected)."""
            value = refs["elem_select"].value
            if value is None:
                return None
            return next((e for e in refs["elements"]
                         if e.get("n") == value), None)

        def update_actionbar() -> None:
            """Enable the per-element actions per the selected
            element's ``actionTypes`` (click / fill) and the target
            requirement: click / fill / drag need a selection, press is
            a plain keyboard action and always works."""
            el = selected_element()
            types = (el or {}).get("actionTypes") or []
            refs["click_btn"].set_enabled(bool(el) and "click" in types)
            refs["fill_btn"].set_enabled(bool(el) and "fill" in types)
            refs["fill_input"].set_enabled(bool(el) and "fill" in types)
            refs["drag_btn"].set_enabled(el is not None)
            refs["drag_dx"].set_enabled(el is not None)
            refs["drag_dy"].set_enabled(el is not None)

        def on_badge_tap(_e, n: int) -> None:
            """Tapping a numbered badge selects that element into the
            action bar (mobile-first: the phone is a first-class
            intervention device, M3 decision 5)."""
            if any(el.get("n") == n for el in refs["elements"]):
                refs["elem_select"].value = n
                update_actionbar()

        def render_copilot(shot_b64: str, elements: list) -> None:
            """The Copilot render from one fetch (the ~5 s poll, the
            post-action refresh): the screenshot + overlay rebuilt -
            the badges are positioned by percentage over the image
            (M3 decision 5) - and the element select and the
            empty-elements hint (M3 decision 1). The action bar
            survives the refresh (its enabled state is re-synced, the
            inputs keep their text)."""
            refs["elements"] = elements
            shot_bytes = None
            try:
                shot_bytes = base64.b64decode(shot_b64 or "") or None
            except (TypeError, ValueError):
                shot_bytes = None
            dims = png_dims(shot_bytes)
            box = refs["shot_box"]
            box.clear()
            with box:
                with ui.column().classes("w-full relative") \
                        .mark("session-shot-wrap"):
                    if shot_bytes is not None:
                        ui.image(f"data:image/png;base64,{shot_b64}") \
                            .classes("w-full max-h-[40rem]") \
                            .mark("session-screenshot")
                    if dims is not None:
                        img_w, img_h = dims
                        for el in elements:
                            pos = overlay_pct(el.get("rect"), img_w, img_h)
                            if pos is None:
                                continue
                            left, top = pos
                            n = el.get("n")
                            badge = ui.label(str(n)).classes(BADGE_CLASSES) \
                                .style(f"left: {left:.2f}%; top: {top:.2f}%")
                            badge.mark(f"session-badge-{n}")
                            badge.on("click", lambda _e, n=n: on_badge_tap(_e, n))
            has_elements = bool(elements)
            refs["hint"].set_visibility(not has_elements)
            refs["elem_select"].set_visibility(has_elements)
            if has_elements:
                options = {
                    el.get("n"):
                        f"{el.get('n')} · {el.get('role')} · {el.get('name')}"
                    for el in elements
                }
                # set_options keeps the selection when the element is
                # still there, resets it to None otherwise.
                refs["elem_select"].set_options(options)
            update_actionbar()

        async def refresh_copilot() -> None:
            """The Copilot refresh (M3 decision 4): while waiting, one
            blocking fetch (screenshot + elements) in a worker thread,
            then the render on the event loop. A ControlError (the run
            ended mid-request, the socket is unlinked) degrades to a
            notify + the DB state refresh - never a page crash."""
            run_row = db.get_run(run_id)
            if run_row is None:
                refresh()
                return
            if run_state(run_row, control_sock_alive(run_row)) != "waiting":
                refresh()
                return
            try:
                shot, elements = await asyncio.to_thread(
                    fetch_copilot, run_row["control_sock"])
            except ControlError as e:
                ui.notify(f"Session refresh failed: {e}", type="warning")
                refresh()
                return
            # Re-check after the fetch: a resume/cancel that landed
            # while it ran must not render into a state body that is
            # gone (the page self-heals on the next poll).
            current = db.get_run(run_id)
            if current is None or run_state(current,
                                            control_sock_alive(current)) \
                    != "waiting":
                refresh()
                return
            render_copilot(shot, elements)

        async def copilot_poll() -> None:
            """The ~5 s Copilot poll (M3 decision 4); the timer is
            created in ``render_copilot_view`` and stopped in
            ``refresh`` when the run leaves the waiting state."""
            await refresh_copilot()

        async def do_action(action: str, note: str, **args) -> bool:
            """Send one control action (M3 decision 4): the blocking
            socket request in a worker thread, then a ui.notify with
            ``note`` on the event loop. The action's protocol arguments
            travel in ``args`` (``text`` among them for ``fill``) - they
            must not collide with the signature's own names. A
            ControlError (the run ended mid-request) degrades to a
            notify + the DB state refresh - never a page crash. True
            when the action was sent."""
            run_row = db.get_run(run_id)
            if run_row is None or not run_row["control_sock"]:
                ui.notify(f"{action}: no live control channel",
                          type="warning")
                return False
            try:
                await asyncio.to_thread(
                    send_action, run_row["control_sock"], action, **args)
            except ControlError as e:
                ui.notify(f"{action} failed: {e}", type="negative")
                refresh()
                return False
            ui.notify(note)
            return True

        def refresh() -> None:
            """DB poll (~2 s): the state badge, the state body on a
            state change (the Copilot timer stops when the run leaves
            the waiting state), the deadline countdown while waiting,
            and the step strip while running (new PageStatus rows)."""
            run_row = db.get_run(run_id)
            if run_row is None:
                return
            new_state = run_state(run_row, control_sock_alive(run_row))
            state_badge.set_text(new_state)
            state_badge.props(f"color={STATE_COLORS.get(new_state, 'grey')}")
            if new_state != state_sig["sig"]:
                state_sig["sig"] = new_state
                if refs.get("copilot_timer") is not None:
                    refs["copilot_timer"].cancel()
                refs["copilot_timer"] = None
                content_box.clear()
                _render_state(content_box, run_row, new_state, refs,
                              renderers)
            if new_state == "waiting" and refs.get("deadline") is not None:
                refs["deadline"].set_text(
                    deadline_text(run_row["pause_deadline_at"]))
            if new_state == "running" and refs.get("steps_box") is not None:
                render_running_steps(refs)

        def render_novnc(run) -> None:
            """The noVNC tab (M3 decision 6): the client-host iframe
            while the run is alive (rendered only in the running and
            waiting states). No port on the row (no display was
            allocated) -> a hint instead of a dead iframe."""
            port = run["novnc_port"]
            if port is None:
                ui.label("noVNC is not available for this run.") \
                    .classes("text-grey-7").mark("session-novnc-unavailable")
            else:
                ui.html(novnc_iframe_html(port), sanitize=False) \
                    .mark("session-novnc")

        def open_shot(url: str) -> None:
            """Step thumbnail click -> the full image in a dialog (the
            dashboard step-strip pattern)."""
            with ui.dialog() as dlg:
                dlg.open()
                ui.image(url).classes("max-h-[80vh]")

        def render_copilot_view(run, refs) -> None:
            """The Copilot tab of the waiting view (S1.2, M3 decisions
            1/4/5): the live screenshot + overlay are rebuilt on every
            refresh; the element select and the action bar are stable
            across refreshes (the inputs keep their text, the enabled
            state is re-synced). Renders into the *current* slot (the
            Copilot tab panel, decision 3) - the caller must open the
            tab panel first. The ~5 s Copilot poll (decision 4) starts
            here and stops in ``refresh`` when the run leaves the
            waiting state."""
            refs["elements"] = []
            refs["shot_box"] = ui.column().classes("w-full") \
                .mark("session-shot-box")
            refs["hint"] = ui.label(EMPTY_ELEMENTS_HINT) \
                .classes("text-grey-7").mark("session-novnc-hint")
            refs["hint"].set_visibility(False)
            refs["elem_select"] = ui.select(
                options={}, value=None, label="Element") \
                .props("clearable").mark("session-elem-select")
            refs["elem_select"].set_visibility(False)
            refs["elem_select"].on_value_change(
                lambda _e: update_actionbar())
            with ui.row().classes(
                    "w-full flex-wrap items-center gap-2") \
                    .mark("session-actionbar"):
                refs["click_btn"] = ui.button("Click").props("no-caps") \
                    .mark("session-click")
                refs["fill_input"] = ui.input("") \
                    .props("dense outlined").classes("w-40") \
                    .mark("session-fill-input")
                refs["fill_btn"] = ui.button("Fill").props("no-caps") \
                    .mark("session-fill")
                refs["press_input"] = ui.input("") \
                    .props("dense outlined").classes("w-28") \
                    .mark("session-press-input")
                refs["press_btn"] = ui.button("Press").props("no-caps") \
                    .mark("session-press")
                refs["drag_dx"] = ui.number("dx", value=0,
                                            format="%.0f") \
                    .props("dense outlined").classes("w-20") \
                    .mark("session-drag-dx")
                refs["drag_dy"] = ui.number("dy", value=0,
                                            format="%.0f") \
                    .props("dense outlined").classes("w-20") \
                    .mark("session-drag-dy")
                refs["drag_btn"] = ui.button("Drag").props("no-caps") \
                    .mark("session-drag")
            with ui.row().classes("w-full items-center gap-2") \
                    .mark("session-controls"):
                refs["resume_btn"] = ui.button("Resume") \
                    .props("no-caps color=primary") \
                    .mark("session-resume")
                refs["cancel_btn"] = ui.button("Cancel") \
                    .props("no-caps color=negative") \
                    .mark("session-cancel")

            with ui.dialog() as cancel_dialog, ui.card().classes("w-96"):
                ui.label("Cancel the run?").classes("text-h6")
                ui.label("The pause is aborted and the run ends as "
                         "cancelled.")
                with ui.row().classes(
                        "w-full justify-end items-center gap-2"):
                    ui.button("Go back", on_click=cancel_dialog.close) \
                        .props("flat").mark("session-cancel-go-back")
                    cancel_ok = ui.button("Cancel run") \
                        .mark("session-cancel-confirm") \
                        .props("color=negative")

            async def on_click(_e) -> None:
                el = selected_element()
                if el is None:
                    return
                if await do_action("click", f"Click {el['n']} sent",
                                   n=el["n"]):
                    await refresh_copilot()

            async def on_fill(_e) -> None:
                el = selected_element()
                if el is None:
                    return
                if await do_action("fill", f"Fill {el['n']} sent",
                                   n=el["n"],
                                   text=str(refs["fill_input"].value
                                             or "")):
                    await refresh_copilot()

            async def on_press(_e) -> None:
                key = str(refs["press_input"].value or "").strip()
                if not key:
                    ui.notify("Enter a key to press", type="warning")
                    return
                if await do_action("press", f"Press {key} sent",
                                   key=key):
                    await refresh_copilot()

            async def on_drag(_e) -> None:
                el = selected_element()
                if el is None:
                    return

                def num(value) -> float:
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        return 0.0

                if await do_action(
                        "drag", f"Drag {el['n']} sent", n=el["n"],
                        dx=num(refs["drag_dx"].value),
                        dy=num(refs["drag_dy"].value)):
                    await refresh_copilot()

            async def on_resume(_e) -> None:
                if await do_action("resume",
                                   "Resume sent; the run continues"):
                    refresh()

            def on_cancel(_e) -> None:
                cancel_dialog.open()

            async def on_cancel_confirm(_e) -> None:
                cancel_dialog.close()
                if await do_action("cancel",
                                   "Cancel sent; the run ends"):
                    refresh()

            refs["click_btn"].on("click", on_click)
            refs["fill_btn"].on("click", on_fill)
            refs["press_btn"].on("click", on_press)
            refs["drag_btn"].on("click", on_drag)
            refs["resume_btn"].on("click", on_resume)
            refs["cancel_btn"].on("click", on_cancel)
            cancel_ok.on("click", on_cancel_confirm)

            refs["copilot_timer"] = ui.timer(
                COPILOT_REFRESH_INTERVAL, copilot_poll)
            update_actionbar()

        def render_waiting(box, run, refs) -> None:
            """The waiting view (M3 decision 3, S1.2/S1.3): the pause
            banner (reason, prompt, deadline countdown) and the tabs -
            the Copilot view (active by default) and the noVNC tab
            (decision 6). The Copilot poll starts in the Copilot view
            and stops in ``refresh`` when the run leaves the waiting
            state."""
            with box:
                with ui.card().classes("w-full bg-orange-50") \
                        .mark("session-pause"):
                    ui.label("Paused").classes("text-orange-900 text-h6")
                    if run["pause_reason"]:
                        ui.label(f"Reason: {run['pause_reason']}") \
                            .mark("session-pause-reason")
                    if run["pause_prompt"]:
                        ui.label(f"Prompt: {run['pause_prompt']}") \
                            .mark("session-pause-prompt")
                    refs["deadline"] = ui.label("") \
                        .mark("session-pause-deadline")
                    # The Repair recipe link (M3 S2.3): a step_failed
                    # pause offers the candidate picker directly.
                    repair_url = repair_recipe_url(
                        run, db.get_task(run["task_id"]))
                    if repair_url:
                        ui.link("Repair recipe", repair_url) \
                            .props("no-caps").classes("text-blue-700") \
                            .mark("session-repair")
                with ui.tabs().classes("w-full") as tabs:
                    ui.tab("Copilot").mark("session-copilot-tab")
                    ui.tab("noVNC").mark("session-novnc-tab")
                with ui.tab_panels(tabs, value="Copilot") \
                        .classes("w-full"):
                    with ui.tab_panel("Copilot") \
                            .mark("session-copilot-panel"):
                        render_copilot_view(run, refs)
                    with ui.tab_panel("noVNC") \
                            .mark("session-novnc-tab-panel"):
                        render_novnc(run)

        def render_running_steps(refs) -> None:
            """The running view's step strip (M3 decision 3, the
            dashboard step-strip DB pattern): the run's PageStatus
            screenshots as a compact row (full image on click),
            rebuilt only when new rows land - the strip fills in live
            as the run progresses (``refresh`` calls this every poll)."""
            rows = db.list_page_status(run_id)
            sig = tuple(r["id"] for r in rows)
            if sig == refs.get("steps_sig"):
                return
            refs["steps_sig"] = sig
            box = refs["steps_box"]
            box.clear()
            shots = []
            for r in rows:
                url = runfile_url(r["screenshot_path"])
                if url:
                    shots.append((r["step_number"], url))
            with box:
                if not shots:
                    ui.label("No step screenshots yet.").classes(
                        "text-grey-6").mark("session-no-steps")
                    return
                ui.label("Steps").classes("text-h6") \
                    .mark("session-steps-label")
                with ui.row().classes("flex-wrap items-end gap-2") \
                        .mark("session-step-thumbs"):
                    for step_no, url in shots:
                        with ui.column().classes("items-center gap-1"):
                            ui.image(url).classes(
                                "h-20 cursor-pointer rounded") \
                                .mark("session-step-thumb") \
                                .on("click", lambda _e, u=url: open_shot(u))
                            ui.label(
                                str(step_no if step_no is not None
                                    else "—")
                            ).classes("text-xs text-grey-6")

        def render_running(box, run, refs) -> None:
            """The running view (M3 decision 3, S1.3): read-only
            observation - the step strip (the ``PageStatus`` DB
            pattern) and the noVNC tab (decision 6), the step strip
            active by default. The strip is updated on every poll."""
            with box:
                ui.label("Running").classes("text-h6") \
                    .mark("session-running")
                with ui.tabs().classes("w-full") as tabs:
                    ui.tab("Steps").mark("session-steps-tab")
                    ui.tab("noVNC").mark("session-novnc-tab")
                with ui.tab_panels(tabs, value="Steps").classes("w-full"):
                    with ui.tab_panel("Steps") \
                            .mark("session-steps-panel"):
                        refs["steps_box"] = ui.column().classes("w-full")
                        render_running_steps(refs)
                    with ui.tab_panel("noVNC") \
                            .mark("session-novnc-tab-panel"):
                        render_novnc(run)

        def render_ended(box, run, refs) -> None:
            """The ended view (M3 decision 3, S1.3): the result summary
            (result + timestamps + notes) and, when ``pause_context``
            is set, the last pause context read-only (reason, prompt,
            screenshot, elements). No noVNC - the display stack is
            reaped with the run."""
            with box:
                with ui.card().classes("w-full").mark("session-result"):
                    ui.label(f"Finished: {run['result']}") \
                        .classes("text-h6").mark("session-ended")
                    with ui.row().classes("items-center gap-4") \
                            .mark("session-result-times"):
                        ui.label(f"Started: {run['started_at'] or '—'}") \
                            .mark("session-result-started")
                        ui.label(f"Ended: {run['ended_at'] or '—'}") \
                            .mark("session-result-ended")
                # The Repair recipe link (M3 S2.3): the pause columns
                # survive the resume, so a step_failed run that ended
                # (cancelled / needs_attention / ...) still offers the
                # candidate picker on its last failure.
                repair_url = repair_recipe_url(
                    run, db.get_task(run["task_id"]))
                if repair_url:
                    ui.link("Repair recipe", repair_url) \
                        .props("no-caps").classes("text-blue-700") \
                        .mark("session-repair")
                if run["notes"]:
                    ui.label(f"Notes: {run['notes']}") \
                        .classes("text-grey-6").mark("session-notes")
                summary = pause_context_summary(run)
                if summary is not None:
                    with ui.card().classes("w-full bg-slate-50") \
                            .mark("session-last-pause"):
                        ui.label("Last pause (read-only)").classes("text-h6") \
                            .mark("session-last-pause-title")
                        if summary["reason"]:
                            ui.label(f"Reason: {summary['reason']}") \
                                .mark("session-last-pause-reason")
                        if summary["prompt"]:
                            ui.label(f"Prompt: {summary['prompt']}") \
                                .mark("session-last-pause-prompt")
                        if summary["shot_url"]:
                            ui.image(summary["shot_url"]) \
                                .classes("max-h-[24rem]") \
                                .mark("session-last-pause-shot")
                        if summary["elements"]:
                            ui.label("Elements at pause time:") \
                                .classes("text-grey-6 mt-2") \
                                .mark("session-last-pause-elements-label")
                            for line in summary["elements"]:
                                ui.label(line).classes("text-sm text-grey-7") \
                                    .mark("session-last-pause-element")

        # ---- State machine (M3 decision 3, the ~2 s poll) ---------------
        state = run_state(run, control_sock_alive(run))
        state_badge = ui.badge(
            state, color=STATE_COLORS.get(state, "grey")).mark("session-state")
        content_box = ui.column().classes("w-full").mark("session-content")
        state_sig = {"sig": state}
        renderers = {
            "waiting": render_waiting,
            "running": render_running,
            "ended": render_ended,
        }
        _render_state(content_box, run, state, refs, renderers)
        if state == "waiting" and refs.get("deadline") is not None:
            refs["deadline"].set_text(deadline_text(run["pause_deadline_at"]))
            # The initial Copilot fetch (M3 decision 4): the operator
            # gets the live screenshot and the element list immediately
            # (without it the first ~5 s tick would leave the page
            # empty); it degrades to a notify when the socket is gone.
            await refresh_copilot()

        ui.timer(REFRESH_INTERVAL, refresh)
        refresh()
