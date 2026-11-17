# -*- coding: utf-8 -*-
"""Task detail page (M2 chunk D4.1).

The operator's per-task page (``/tasks/<task_id>``; replaces the D2
placeholder): the header (service/user, status, enabled/cron, recipe
file), the icon run actions - the morphing **Run/Pause/Resume** button
(play_arrow idle, pause while running, play_arrow while waiting - the
paused run is resumed from the button via its control socket; a hover
tooltip carries the action text), **Stop** (enabled while the run is
running or paused), **Reset profile** with a confirmation dialog
(locked decision 8 / D3.4), **Clear login block**, and the **Recipe**
link -> the D5 page - the pause section while a run is ``waiting``
(D4.1c; M3 S1.1 adds the **Open session** link to the intervention
page), the run history with a per-run **View run** link (the session
page's live or ended view), per-run step rows and screenshot
thumbnails (D4.1b), the task's downloads (D4.3), and the live log of
the selected run (D4.1c, the shared D2.3 log pane).

All run actions go through ``orchestrator.start_run`` / ``stop_run`` /
``pause_run`` (the same callbacks the scheduler uses); **Reset
profile** goes through ``db.reset_profile`` (rejected unless the task
is idle). ``ui.timer`` polls the DB (~2 s) and updates the status
badge, the action button states (icon, tooltip, enabled), the pause
section, and the history/downloads sections.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from fastapi import Request
from nicegui import ui

from .. import config
from ..control import ControlError
from ..db import Database
from ..orchestrator import Orchestrator
from .auth import require_auth
from .downloads import BODY as DOWNLOAD_BODY
from .downloads import COLUMNS as DOWNLOAD_COLUMNS
from .downloads import build_download_rows
from .downloads import open_download_retry
from .format import deadline_text, table_column
from .layout import build_layout
from .logpane import LogPane
from .runfiles import runfile_url
from .session import control_sock_alive, send_action

# The badge colors of the task statuses (the dashboard's own mapping,
# rendered through its body slot).
STATUS_COLORS = {"running": "blue", "waiting": "orange", "idle": "grey"}

# The DB poll interval of the page refresh (the dashboard's ~2 s).
REFRESH_INTERVAL = 2.0

# Run-history cell widths (spec: the notes tail and the step action /
# error are truncated for the table, the full text lives in the log).
NOTES_TAIL = 120
ACTION_TAIL = 80
ERROR_TAIL = 120


def _fmt_ts(value) -> str:
    """A stored timestamp (``YYYY-mm-dd HH:MM:SS``) or ``—``."""
    return value or "—"


def _duration(started, ended) -> str:
    """``ended_at - started_at`` as ``Hh Mm Ss`` (the hours omitted when
    zero; ``—`` when either is missing or unparseable - a still-running
    run)."""
    if not (started and ended):
        return "—"
    try:
        s = datetime.strptime(started, "%Y-%m-%d %H:%M:%S")
        e = datetime.strptime(ended, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return "—"
    total = int((e - s).total_seconds())
    if total < 0:
        return "—"
    h, rem = divmod(total, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}h {m}m {sec}s" if h else f"{m}m {sec}s"


def _tail(value, width: int) -> str:
    """Truncate a cell value to the last ``width`` chars (``…`` prefix)."""
    if not value:
        return "—"
    value = str(value)
    return value if len(value) <= width else "…" + value[-width:]


def _step_rows(db: Database, run_id: int) -> list[dict]:
    """One display row per PageStatus of the run (D4.1b): the step number,
    the locator action, the error, and the screenshot's ``/runfiles`` URL
    (None when the step has no screenshot)."""
    rows = []
    for ps in db.list_page_status(run_id):
        rows.append({
            "id": ps["id"],
            "step": ps["step_number"] if ps["step_number"] is not None else "—",
            "action": _tail(ps["locator_action"], ACTION_TAIL),
            "error": _tail(ps["error"], ERROR_TAIL),
            "screenshot": runfile_url(ps["screenshot_path"]),
        })
    return rows


def _pause_screenshot_url(run) -> str | None:
    """The pause screenshot's ``/runfiles`` URL from ``Run.pause_context``
    (the context JSON's ``screenshot.path``), or None."""
    if not run["pause_context"]:
        return None
    try:
        context = json.loads(run["pause_context"])
    except (TypeError, ValueError):
        return None
    path = (context.get("screenshot") or {}).get("path")
    return runfile_url(path)


# The columns follow the shared table convention (``format.table_column``;
# see the note in format.py): numeric cells (Step) right-aligned mono, the
# technical Action cell mono.
STEP_COLUMNS = [
    table_column("step", "Step", align="right", mono=True),
    table_column("action", "Action", mono=True),
    table_column("error", "Error"),
    table_column("screenshot", "Screenshot"),
]

# The screenshot cell is an image thumbnail (a plain string cell cannot
# carry one): the slot renders ``props.row.screenshot`` as a ``q-img`` and
# the click dispatches a bubbling ``stepshot`` CustomEvent (the same
# pattern as the dashboard's ``rowaction``) that opens the full image in
# a dialog. The default cell span carries the mono flag of the table
# convention.
STEP_BODY = """
<q-tr :props="props">
  <q-td v-for="col in props.cols" :key="col.name">
    <q-img v-if="col.name === 'screenshot' && props.row.screenshot"
           :src="props.row.screenshot"
           style="height: 4rem; cursor: pointer;"
           @click="$event.currentTarget.dispatchEvent(new CustomEvent('stepshot', {detail: {url: props.row.screenshot}, bubbles: true}))"/>
    <span v-else :class="col.mono ? 'font-mono' : ''">{{ props.row[col.name] }}</span>
  </q-td>
</q-tr>
"""


def register_task_detail(db: Database, orchestrator: Orchestrator) -> None:
    """Register the task detail page (``/tasks/<task_id>``)."""

    @ui.page("/tasks/{task_id}")
    def task_detail_page(request: Request, task_id: int) -> None:
        redirect = require_auth(request)
        if redirect is not None:
            return redirect
        build_layout(active="Tasks")
        task = db.get_task(task_id)
        if task is None:
            ui.label(f"Unknown task id: {task_id} (404)").classes("text-red-600")
            return

        # ---- Header -----------------------------------------------------
        ui.label(f"Task {task['id']}: {task['service']} / "
                 f"{task['user'] or '—'}").classes("text-h4 font-bold")
        with ui.row().classes("items-center gap-2"):
            status_badge = ui.badge(
                task["status"],
                color=STATUS_COLORS.get(task["status"], "grey")).mark("detail-status")
            ui.label(f"Enabled: {'yes' if task['enabled'] else 'no'} · "
                     f"Cron: {task['cron'] or '—'}").mark("detail-schedule")
        recipe_path = task["recipe_file"] or str(
            config.recipe_path_for(task["service"]))
        recipe_state = "" if Path(recipe_path).exists() else " (missing)"
        login_status = ui.label().mark("detail-login-status")
        ui.label(f"Recipe: {Path(recipe_path).name}{recipe_state}"
                 ).mark("detail-recipe-label")

        # ---- Actions ----------------------------------------------------
        # Icon action buttons (hover tooltips carry the action text): the
        # morphing Run/Pause button (play_arrow idle, pause while running -
        # updated in the ~2 s refresh) starts or pauses the run; Stop and
        # Reset profile and Clear login block are the D3/D3.4 actions.
        with ui.row().classes("items-center gap-2"):
            run_btn = ui.button(icon="play_arrow").mark("detail-run").props("color=primary")
            with run_btn:
                run_btn_tooltip = ui.tooltip("Run now")
            stop_btn = ui.button(icon="stop").mark("detail-stop").props("color=negative")
            with stop_btn:
                ui.tooltip("Stop run")
            reset_btn = ui.button(icon="restart_alt").mark("detail-reset")
            with reset_btn:
                ui.tooltip("Reset profile")
            clear_login_btn = ui.button(icon="lock_open").mark("detail-login-clear")
            with clear_login_btn:
                ui.tooltip("Clear login block")
            with ui.link("Recipe", f"/recipes/{task['service']}").mark("detail-recipe"):
                ui.icon("description").classes("text-lg")

        recovery_input = ui.input(
            "Start date for this run (optional, YYYY-MM-DD)"
        ).mark("detail-date-from")

        async def on_run_now(_e) -> None:
            """The morphing Run/Pause/Resume button: the click re-reads
            the task status (the icon state can be a poll behind, so a
            stale icon can never dispatch the wrong action) - running
            sends the manual-pause signal (pause at the next step
            boundary), waiting sends the paused run's control socket the
            protocol ``resume`` (the session page's own path), idle
            starts a manual one-off (works for disabled tasks, the
            schedule is untouched)."""
            task = db.get_task(task_id)
            if task is None:
                return
            if task["status"] == "waiting":
                run = next((r for r in db.list_active_runs()
                            if r["task_id"] == task_id and r["pause_reason"]),
                           None)
                if run is None or not control_sock_alive(run):
                    ui.notify("No active pause to resume", type="warning")
                else:
                    try:
                        await asyncio.to_thread(
                            send_action, run["control_sock"], "resume")
                    except ControlError:
                        ui.notify("The run ended while resuming",
                                  type="warning")
                refresh()
                return
            if task["status"] == "running":
                paused = orchestrator.pause_run(task_id)
                if not paused:
                    ui.notify("No live runner to pause", type="warning")
                refresh()
                return
            override = recovery_input.value
            try:
                started = (await orchestrator.start_run(task_id, date_from=override)
                           if override else await orchestrator.start_run(task_id))
            except ValueError as e:
                ui.notify(str(e), type="warning")
                return
            if started:
                recovery_input.value = ""
            if not started:
                ui.notify("Not started (already running/waiting?)",
                          type="warning")
            refresh()

        async def on_stop(_e) -> None:
            """Row Stop: SIGTERM the live runner group (D3.1)."""
            stopped = await orchestrator.stop_run(task_id)
            if not stopped:
                ui.notify("No live runner to stop", type="warning")
            refresh()

        def on_reset(_e) -> None:
            """Reset profile: the confirmation dialog (locked decision 8);
            the delete itself is db.reset_profile (D3.4)."""
            with ui.dialog() as confirm, ui.card().classes("w-96"):
                confirm.open()
                ui.label("Reset the profile?").classes("text-h6")
                ui.label("The browser profile directory is deleted and the "
                         "next run cold-starts (the consent banner is shown "
                         "again).")
                with ui.row().classes("w-full justify-end items-center gap-2"):
                    ui.button("Cancel", on_click=confirm.close).props("flat")
                    ok_btn = ui.button("Reset").mark("detail-reset-confirm") \
                        .props("color=primary")

            def on_confirm(_e2) -> None:
                ok, error = db.reset_profile(task_id)
                if ok:
                    ui.notify("Profile reset; the next run cold-starts")
                else:
                    ui.notify(error, type="warning")
                confirm.close()
                refresh()

            ok_btn.on("click", on_confirm)

        run_btn.on("click", on_run_now)
        stop_btn.on("click", on_stop)
        reset_btn.on("click", on_reset)

        def on_clear_login(_e):
            with ui.dialog() as dialog, ui.card():
                ui.label("Allow one more login attempt?")
                ui.label("Check the credentials first. Manual browser submissions are not counted.")

                def confirm():
                    cleared = db.clear_login_lock(task_id)
                    ui.notify("One login attempt allowed" if cleared else
                              "Not cleared: task must be idle and blocked")
                    dialog.close()
                    refresh()

                ui.button("Cancel", on_click=dialog.close)
                ui.button("Allow one attempt", on_click=confirm).mark("detail-login-confirm")
            dialog.open()

        clear_login_btn.on("click", on_clear_login)

        # ---- Pause section (read-only, M2; resolution is M3) -------------
        pause_box = ui.column().classes("w-full").mark("detail-pause-box")
        pause_sig = {"sig": None}
        pause_state = {"deadline": None}

        def render_pause() -> None:
            """While the task's run is ``waiting``: the pause prompt,
            reason, deadline countdown (updated every poll), and the
            last pause screenshot (from ``Run.pause_context``)."""
            runs = [r for r in db.list_active_runs()
                    if r["task_id"] == task_id and r["pause_reason"]]
            run = runs[-1] if runs else None
            sig = run["id"] if run is not None else None
            if sig != pause_sig["sig"]:
                pause_sig["sig"] = sig
                pause_box.clear()
                pause_state["deadline"] = None
                if run is not None:
                    with pause_box:
                        with ui.card().classes(
                                "w-full bg-orange-50").mark("detail-pause"):
                            with ui.row().classes("items-center gap-2"):
                                ui.label("Paused").classes(
                                    "text-orange-900 text-h6")
                                # The intervention page (M3 decision 2):
                                # the operator acts from the session view,
                                # not from this read-only card.
                                ui.link("Open session",
                                        f"/runs/{run['id']}") \
                                    .mark("detail-pause-open")
                            ui.label(f"Reason: {run['pause_reason']}") \
                                .mark("detail-pause-reason")
                            if run["pause_prompt"]:
                                ui.label(f"Prompt: {run['pause_prompt']}") \
                                    .mark("detail-pause-prompt")
                            pause_state["deadline"] = ui.label("") \
                                .mark("detail-pause-deadline")
                            shot = _pause_screenshot_url(run)
                            if shot:
                                ui.image(shot).classes(
                                    "max-h-[24rem]") \
                                    .mark("detail-pause-shot")
            if (run is not None and pause_state["deadline"] is not None):
                pause_state["deadline"].set_text(
                    deadline_text(run["pause_deadline_at"]))

        render_pause()

        # ---- Run history -------------------------------------------------
        ui.label("Run history").classes("text-h6")
        history_box = ui.column().classes("w-full").mark("detail-history")
        history_sig = {"sig": None}

        def render_history() -> None:
            """The run history (D4.1b): one expansion per run (newest
            first) with the run's notes tail and its step rows. Rebuilt
            only when the run set or a run's result/end/outcome changes,
            so the poll keeps the user's expanded state in between."""
            runs = db.list_runs(task_id)
            sig = tuple((r["id"], r["result"], r["ended_at"],
                         r["collection_outcome"]) for r in runs)
            if sig == history_sig["sig"]:
                return
            history_sig["sig"] = sig
            history_box.clear()
            with history_box:
                for run in runs:
                    label = (
                        f"Run {run['id']} · {_fmt_ts(run['started_at'])} → "
                        f"{_fmt_ts(run['ended_at'])} · "
                        f"{run['result'] or 'running'} · "
                        f"{_duration(run['started_at'], run['ended_at'])}"
                    )
                    if run["collection_outcome"]:
                        label += f" · {run['collection_outcome']}"
                    with ui.expansion(label).classes("w-full"):
                        # Run-review reachability: the session page's live
                        # view while the run is open, its ended view after
                        # it finishes (a navigation link, R5).
                        with ui.row().classes("w-full justify-end"):
                            with ui.link("View run",
                                         f"/runs/{run['id']}"
                                         ).mark(f"detail-view-run-{run['id']}"):
                                ui.icon("open_in_browser").classes("text-lg")
                        if run["notes"]:
                            ui.label(f"Notes: {_tail(run['notes'], NOTES_TAIL)}"
                                     ).classes("text-grey-6").mark("detail-notes")
                        steps = _step_rows(db, run["id"])
                        if steps:
                            table = ui.table(columns=STEP_COLUMNS,
                                             rows=steps).classes("w-full")
                            table.mark("detail-steps")
                            table.add_slot("body", STEP_BODY)

                            def on_step_shot(e):
                                """Thumbnail click -> the full image in a
                                dialog (D4.1b)."""
                                detail = e.args if isinstance(e.args, dict) else {}
                                with ui.dialog() as dlg:
                                    dlg.open()
                                    ui.image(detail.get("url", "")
                                             ).classes("max-h-[80vh]")

                            # The js_handler emits the bare ``detail``
                            # payload (see the dashboard's rowaction
                            # binding): the args-spec form would arrive
                            # wrapped as ``{"detail": ...}``.
                            table.on("stepshot", on_step_shot,
                                     js_handler="(event) => emit(event.detail)")
                        else:
                            ui.label("No step rows recorded.").classes(
                                "text-grey-6")

        render_history()

        # ---- Task downloads ---------------------------------------------
        ui.label("Downloads").classes("text-h6")
        download_table = ui.table(columns=DOWNLOAD_COLUMNS,
                                  rows=[]).classes("w-full")
        download_table.mark("detail-downloads")
        download_table.add_slot("body", DOWNLOAD_BODY)
        download_sig = {"sig": None}

        def render_downloads() -> None:
            """The task's downloads (D4.1/D4.3): newest first, the
            duplicate_of rows badged, the exposed delivery state
            (issue #24 C8). Rebuilt only when the row set changed (the
            delivery state is part of the signature: a row finishing or
            failing a delivery changes it)."""
            rows = build_download_rows(db, task_id=task_id)
            sig = tuple(r["filename"] + r["date"] + r["delivery"]
                        for r in rows)
            if sig == download_sig["sig"]:
                return
            download_sig["sig"] = sig
            download_table.rows = rows

        def on_dl_retry(e) -> None:
            """Per-row Retry delivery (issue #24 C8): the confirmation
            dialog, then the orchestrator's retry subprocess (the shared
            body slot carries the button)."""
            detail = e.args if isinstance(e.args, dict) else {}
            download_id = detail.get("id")
            if download_id is None:
                return
            open_download_retry(download_id, orchestrator, refresh)

        download_table.on("dlretry", on_dl_retry,
                          js_handler="(event) => emit(event.detail)")

        render_downloads()

        # ---- Live log (the shared D2.3 pane) -----------------------------
        ui.label("Log").classes("text-h6")
        pane = LogPane(orchestrator)
        log_choice = {"label": None}

        def on_log_select(e) -> None:
            log_choice["label"] = e.value
            refresh_log()

        def refresh_log() -> None:
            """Follow the selected run: the explicit select choice, else
            the task's active run, else its newest run. The select shows
            one entry per run (stable labels, so a run finishing does not
            drop the user's choice); the pane loads the log file on
            follow and then receives live lines (D2.2)."""
            runs = db.list_runs(task_id)
            options = {f"Run {r['id']}": r["id"] for r in runs}
            if log_choice["label"] in options:
                follow_id = options[log_choice["label"]]
            else:
                active = next((r for r in runs if r["result"] is None), None)
                follow_id = (active["id"] if active is not None
                             else (runs[0]["id"] if runs else None))
            select.options = options
            desired = None
            if log_choice["label"] in options:
                desired = log_choice["label"]
            elif follow_id is not None:
                desired = f"Run {follow_id}"
            elif options:
                desired = next(iter(options))
            if desired is not None and select.value != desired:
                select.value = desired
            if follow_id is not None and pane.selected_run_id != follow_id:
                pane.follow(db.get_run(follow_id))

        select = ui.select(options={}, value=None, label="Run")
        select.on_value_change(on_log_select)
        refresh_log()

        # ---- Refresh ----------------------------------------------------
        def refresh() -> None:
            """DB poll (~2 s): the status badge and the action button
            states (the morphing Run/Pause/Resume icon, tooltip and
            enabled state self-heal here; Stop enabled while running or
            waiting, Reset profile only while idle), plus the history
            rebuild when the run set changed."""
            task = db.get_task(task_id)
            if task is None:
                return
            status = task["status"]
            status_badge.set_text(status)
            status_badge.props(
                f"color={STATUS_COLORS.get(status, 'grey')}")
            blocked = bool(task["login_locked"] or task["login_pending_run_id"] is not None)
            login_state = ("blocked" if task["login_locked"] else
                           "pending" if task["login_pending_run_id"] is not None else "available")
            login_status.set_text(
                f"Login: {login_state} · "
                f"Unproven attempts: {task['login_failures']}/{task['login_failure_limit']}")
            run_btn.icon = "pause" if status == "running" else "play_arrow"
            if status == "running":
                run_btn_tooltip.set_text("Pause at next step boundary")
            elif status == "waiting":
                run_btn_tooltip.set_text("Resume run")
            elif blocked:
                run_btn_tooltip.set_text("Run now (login blocked)")
            else:
                run_btn_tooltip.set_text("Run now")
            # Enabled while running (the morphed Pause sends the
            # manual-pause signal) and while waiting (the morphed Resume
            # resumes the paused run via its control socket); disabled
            # only while login-blocked.
            run_btn.set_enabled(not blocked)
            clear_login_btn.set_enabled(status == "idle" and bool(task["login_locked"]))
            # Stop reaches the live runner while the run is running or
            # paused (waiting).
            stop_btn.set_enabled(status in ("running", "waiting"))
            reset_btn.set_enabled(status == "idle")
            render_pause()
            render_history()
            render_downloads()
            refresh_log()

        ui.timer(REFRESH_INTERVAL, refresh)
        refresh()

        ui.context.client.on_disconnect(pane.close)
