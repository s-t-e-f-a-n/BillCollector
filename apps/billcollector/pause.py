# -*- coding: utf-8 -*-
"""The runner's pause subsystem (M1 chunk C5): the intervention mechanism.

A stuck run (a step that failed 3x, a failed download, or an explicit
``wait_user`` step) does not abort: it builds a machine-readable pause
context, persists it on the Run row, flips the task to ``waiting``, pushes
an ntfy deep link, and serves the versioned control socket (see
:mod:`billcollector.control`) from the main thread until the operator
resumes, cancels, or the pause deadline is exceeded.

The context payload is the AI-integration contract (decision 20): it must
stay complete, stable and small. Protocol changes need a version bump in
:mod:`billcollector.control` and a doc update.
"""

import base64
import json
import logging
from datetime import datetime, timedelta

from . import config, notify
from .control import ControlServer
from .interrupt import RunInterrupted
from .pagestate import PageState
from .redaction import sanitize_url

logger = logging.getLogger("billcollector.pause")

PAUSE_PAGE_TEXT_CAP = 20000   # visible page text cap for the context (~20 KB)
PAUSE_POLL_SECONDS = 0.5      # control-socket poll interval in the waiting loop
TS_FORMAT = "%Y-%m-%d %H:%M:%S"  # the timestamp format of db.now()


def parse_ts(value):
    """Parse a DB timestamp string (see :func:`billcollector.db.now`)."""
    return datetime.strptime(value, TS_FORMAT)


def deadline_after(seconds, reference=None):
    """Deadline timestamp string ``seconds`` after ``reference`` (default now)."""
    reference = reference or datetime.now()
    return (reference + timedelta(seconds=int(seconds))).strftime(TS_FORMAT)


def deadline_passed(deadline_at):
    """True when the current time is at or past the deadline string."""
    return datetime.now() >= parse_ts(deadline_at)


def control_sock_path(run_id):
    """Unix socket path of one run's control channel."""
    return config.RUN_DIR / f"run-{run_id}.sock"


def _number_elements(entries):
    """Add the overlay number ``n`` (1-based) to a raw pagestate scan."""
    numbered = []
    for n, entry in enumerate(entries or [], start=1):
        item = {
            "n": n,
            "role": entry.get("role"),
            "name": entry.get("name"),
            "rect": entry.get("rect"),
            "locator": entry.get("locator"),
            "actionTypes": entry.get("actionTypes"),
        }
        if entry.get("url"):
            item["url"] = entry["url"]
        numbered.append(item)
    return numbered


def scan_elements(page):
    """A fresh interactive-element scan (role/name/rect/locator/actionTypes).

    Returns [] when the scan fails: a broken scan must not kill the pause.
    A shutdown signal (RunInterrupted) always propagates (C7.5).
    """
    try:
        state = PageState("", 0, page)
    except RunInterrupted:
        raise  # a shutdown signal is not a scan failure to degrade around
    except Exception as e:
        logger.warning(f"Element scan failed: {type(e).__name__}: {e}")
        return []
    return state.interactive_elements or []


def build_pause_context(ctx, reason, prompt, step_action_json, error, deadline_at,
                        step_number=None):
    """Build the machine-readable pause payload (the intervention context).

    ``step_action_json`` is the failing step's locator-action JSON (the
    ``transform_step_to_json`` output), or None for pauses without a
    failing step (``wait_user``). ``step_number`` is the failing step's
    recipe number, carried as the additive ``step_number`` payload key
    (sibling of the parsed ``step`` key, M3 decision 8): it lets a
    consumer find the step in the recipe without parsing the prompt
    string; None for pauses without a step. Never raises for page
    errors: every page access is best-effort, a degraded context is
    still a context. A shutdown signal (RunInterrupted) always propagates
    (C7.5): it is the end of the run, not a page error to degrade around.
    """
    page = ctx.page
    url = None
    page_title = None
    page_text = None
    try:
        url = sanitize_url(page.url)
    except RunInterrupted:
        raise
    except Exception:
        pass
    try:
        page_title = page.title()
    except RunInterrupted:
        raise
    except Exception:
        pass
    try:
        page_text = page.inner_text("body")
        if len(page_text) > PAUSE_PAGE_TEXT_CAP:
            page_text = page_text[:PAUSE_PAGE_TEXT_CAP]
    except RunInterrupted:
        raise
    except Exception:
        pass

    screenshot_path = None
    screenshot_data = None
    try:
        target_dir = config.RUN_DIR / str(ctx.run_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"pause_{ctx.pause_count}.png"
        page.screenshot(path=str(path))
        screenshot_path = str(path)
        screenshot_data = base64.b64encode(path.read_bytes()).decode("ascii")
    except RunInterrupted:
        raise
    except Exception as e:
        logger.warning(f"Pause screenshot failed (run continues): {type(e).__name__}: {e}")

    step = None
    if step_action_json:
        try:
            step = json.loads(step_action_json)
        except ValueError:
            step = {"raw": step_action_json}

    return {
        "reason": reason,
        "prompt": prompt,
        "url": url,
        "page_title": page_title,
        "error": error,
        "step_number": step_number,
        "step": step,
        "screenshot": {"path": screenshot_path, "data": screenshot_data},
        "elements": _number_elements(scan_elements(page)),
        "page_text": page_text,
        "deadline_at": deadline_at,
    }


def persist_pause(db, run_id, task_id, reason, prompt, context, deadline_at):
    """Write the Run pause columns, flip the run to waiting state, and mark
    the task ``waiting`` (the scheduler's row lock must not re-trigger it)."""
    db.update_run(
        run_id,
        pause_reason=reason,
        pause_prompt=prompt,
        pause_context=json.dumps(context),
        pause_deadline_at=deadline_at,
    )
    db.set_task_status(task_id, "waiting")


def _element_center(numbered, n):
    """Viewport coordinates of the center of element ``n`` of a numbered scan."""
    for entry in numbered:
        if entry.get("n") == n:
            rect = entry.get("rect") or {}
            x = float(rect.get("x", 0))
            y = float(rect.get("y", 0))
            w = float(rect.get("w", 0))
            h = float(rect.get("h", 0))
            return x + w / 2, y + h / 2
    raise ValueError(f"element {n} not found in the current page scan")


def _require_element_number(value, name="n"):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive element number")
    return value


def make_action_handlers(ctx):
    """The control-socket handler map of one paused run (decision:
    coordinate-based - every element action resolves ``n`` from a fresh
    pagestate scan and acts on the element's rect center)."""
    page = ctx.page

    def screenshot():
        data = page.screenshot()
        return {"screenshot": base64.b64encode(data).decode("ascii")}

    def elements():
        return {"elements": _number_elements(scan_elements(page))}

    def context():
        return {"context": ctx.last_pause_context}

    def click(n):
        _require_element_number(n)
        cx, cy = _element_center(_number_elements(scan_elements(page)), n)
        page.mouse.click(cx, cy)
        return {"action": "click", "n": n}

    def fill(n, text=""):
        _require_element_number(n)
        cx, cy = _element_center(_number_elements(scan_elements(page)), n)
        page.mouse.click(cx, cy)
        page.keyboard.type(str(text))
        return {"action": "fill", "n": n}

    def press(key):
        page.keyboard.press(str(key))
        return {"action": "press", "key": str(key)}

    def drag(n, dx=0, dy=0):
        _require_element_number(n)
        cx, cy = _element_center(_number_elements(scan_elements(page)), n)
        page.mouse.move(cx, cy)
        page.mouse.down()
        page.mouse.move(cx + float(dx), cy + float(dy), steps=10)
        page.mouse.up()
        return {"action": "drag", "n": n, "dx": float(dx), "dy": float(dy)}

    return {
        "screenshot": screenshot,
        "elements": elements,
        "context": context,
        "click": click,
        "fill": fill,
        "press": press,
        "drag": drag,
    }


def pause_loop(ctx, reason, prompt, step_action_json, error, step_number=None):
    """One pause: persist the context, push ntfy, serve the control socket.

    ``step_number`` is the failing step's recipe number, forwarded to the
    pause context (M3 decision 8); None for pauses without a step.
    Blocks in the waiting loop (main thread, between steps, so sync
    Playwright calls from the action handlers are safe). Returns
    ``"resume"``, ``"cancel"`` or ``"timeout"``.
    """
    db = ctx.db
    deadline_seconds = int(db.get_setting("pause_deadline_seconds") or 1800)
    deadline_at = deadline_after(deadline_seconds)
    ctx.pause_count += 1
    ctx.last_pause_deadline = parse_ts(deadline_at)

    context = build_pause_context(
        ctx, reason, prompt, step_action_json, error, deadline_at, step_number)
    ctx.last_pause_context = context
    persist_pause(db, ctx.run_id, ctx.task["id"], reason, prompt, context, deadline_at)
    notify.notify_pause(db, db.get_run(ctx.run_id), ctx.task)

    sock_path = control_sock_path(ctx.run_id)
    server = ControlServer(sock_path, make_action_handlers(ctx))
    try:
        # server.start() binds the socket file; it is inside the try so a
        # shutdown signal (RunInterrupted) landing in the setup window
        # between the bind and the waiting loop still unlinks the file in
        # the finally (C7.5).
        server.start()
        db.update_run(ctx.run_id, control_sock=str(sock_path))
        logger.warning(f"Run {ctx.run_id} paused ({reason}): {prompt}")
        while True:
            server.poll(PAUSE_POLL_SECONDS)
            if server.resume_requested:
                return "resume"
            if server.cancel_requested:
                return "cancel"
            if deadline_passed(deadline_at):
                logger.error(
                    f"Run {ctx.run_id} pause deadline ({deadline_at}) exceeded")
                return "timeout"
    finally:
        server.close()
