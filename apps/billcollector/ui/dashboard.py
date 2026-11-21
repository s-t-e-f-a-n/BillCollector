# -*- coding: utf-8 -*-
"""Dashboard page for the daemon UI (M2 chunk D2, run actions D3.2).

The operator's home page (spec: gui-concept-dashboard-spec, "Dashboard
specification"): a toolbar with the service/status filters, the
``[N waiting]`` badge and the **Run (filtered)** button, one table row
per task (status color-coded, ``waiting`` rows highlighted, rows keep
their service/user position) with a per-row icon action column
- the morphing **Run/Pause** button (play/pause icon, a hover tooltip
carries the action text), **Stop**, **Edit** and **View run**
(navigates same-tab to the run's session page, ``/runs/<run_id>``; a
live run opens the live session view, a finished one its ended view) -
and a live log pane that follows the selected run.

D3.2 run actions: all calls go through ``orchestrator.start_run`` /
``stop_run`` / ``pause_run`` (the same callbacks the scheduler uses).
Row **Run now** works for disabled tasks too (manual one-off; the
schedule is untouched); while the task is running the same button
morphs into **Pause** (pause at the next step boundary), and while the
row is waiting it morphs into **Resume** - the paused run's control
socket gets the protocol ``resume`` (the same path the session page's
Resume button uses), so a paused run can be resumed or **Stop**ped
from the row without opening the session page. **Stop** is enabled
while the run is running or paused (waiting). **Run (filtered)**
enqueues all *enabled* tasks in the filtered set (the global semaphore
serializes; skipped tasks are reported in a notify).

D3.3 task management (``ui.tasks``): the toolbar **Add task** button
opens the create dialog and a row **Edit** button opens the edit
dialog (cron + enabled); each change hits
``db.create_task``/``db.update_task`` + ``scheduler.sync_task``.

``ui.timer`` polls the DB (~2 s) and refreshes the table and badge
(WAL reads); the log pane reads the run's log file once, then follows
the orchestrator's log subscribers (D2.2) - re-pointing at the run it
should follow on every poll, so a run started via Run now after the page
load streams live too. Below the log pane, the step strip shows the
followed run's step screenshot thumbnails (full image on click); the
same thumbnails live in the task detail's run expansion (D4.1b).
"""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Request
from nicegui import background_tasks
from nicegui import ui

from ..control import ControlError
from ..db import Database
from ..orchestrator import Orchestrator
from ..scheduler import TaskScheduler, job_id_for
from .auth import require_auth
from .format import table_column
from .layout import build_layout
from .logpane import LogPane
from .runfiles import runfile_url
from .session import control_sock_alive, send_action
from .tasks import open_task_dialog
from .theme import kpi_card, set_kpi

# The task statuses a row can carry (Run results are a separate axis).
STATUSES = ("idle", "running", "waiting")

# Last-download filenames are truncated to this width (spec).
DOWNLOAD_NAME_WIDTH = 30

# The DB poll interval of the dashboard refresh (~2 s per the spec).
REFRESH_INTERVAL = 2.0

# The column list follows the shared table convention
# (``format.table_column``; see the note in format.py): numeric columns
# and Actions right-aligned, the service/user pair labelled "Task",
# technical cells mono.
COLUMNS = [
    table_column("task", "Task"),
    table_column("status", "Status"),
    table_column("login", "Login"),
    table_column("last_run", "Last run", mono=True),
    table_column("next_run", "Next run", mono=True),
    table_column("session", "Session"),
    table_column("last_download", "Last download", mono=True),
    table_column("actions", "Actions", align="right"),
]

# Custom row body: plain string cells cannot carry colors (or buttons),
# so the cells are rendered through the QTable body slot - a color-coded
# status badge, the highlight of waiting rows (spec), and the row action
# icon buttons: the morphing **Run/Pause/Resume** (play_arrow when
# idle, pause while running, play_arrow again while waiting - the
# paused run is resumed from the row via its control socket), **Stop**
# (enabled while running or waiting), **Edit** and **View run** (the
# row's newest run, live or ended - a live run opens the live session
# view, a finished run the ended view). Every icon button carries a
# ``q-tooltip`` with the action text (mouse-over).
#
# The template must NOT be wrapped in <template v-slot="props">: NiceGUI
# compiles the slot string with the Vue *runtime* compiler (nicegui.js),
# which passes the slot scope in as the component prop ``props``. A
# v-slot-wrapped root is an SFC-only construct and makes the runtime
# compiler crash (TypeError: reading 'type'), blanking the whole page.
#
# Action buttons: the slot template is not a NiceGUI element, so a click
# cannot call a Python handler directly. Instead the button dispatches a
# bubbling DOM ``rowaction`` CustomEvent (``detail`` = the payload) on
# itself; ``table.on("rowaction", ...)`` below lands on the q-table root
# element through Vue's attr fallthrough (the nicegui table wrapper and
# QTable do not declare the event), where the NiceGUI client has bound
# the listener. The binding's ``js_handler`` re-emits the bare
# ``event.detail`` (the args-spec form would filter the event's fields
# and arrive wrapped as ``{"detail": ...}``). ``.stop`` keeps the click
# from reaching the row, so an action click never triggers the row's
# task-detail navigation. The morphing button dispatches
# ``action: 'pause'`` while the row is running, ``'resume'`` while it
# is waiting (with ``id`` = the row's ``active_run_id`` - the run id,
# not the task id - because the resume goes to that run's control
# socket), and ``'run'`` otherwise (with the row's task id); the
# **View run** button dispatches ``action: 'view-run'`` with
# ``id: active_run_id || latest_run_id`` (the run id, not the task id)
# and is enabled whenever the task has any run.
#
# Row click: Quasar's q-table only emits its own rowClick event on the
# default body rendering - with this custom body slot the row never gets
# the click binding - so the tr dispatches a bubbling DOM ``rowclick``
# CustomEvent (``detail`` = the row's task id), bound below with the same
# bare-``detail`` js_handler; the buttons' ``.stop`` keeps their clicks
# from also triggering it.
ROW_BODY = """
<q-tr :props="props"
      :class="[props.row.status === 'waiting' ? 'bg-amber-500/10' : '', 'cursor-pointer']"
      @click="$event.currentTarget.dispatchEvent(new CustomEvent('rowclick', {detail: {id: props.row.id}, bubbles: true}))">
  <q-td v-for="col in props.cols" :key="col.name" :props="{ ...props, col: col }">
    <q-badge v-if="col.name === 'status'"
             :color="props.row.status === 'running' ? 'blue' : (props.row.status === 'waiting' ? 'orange' : 'grey')"
             outline>{{ props.row[col.name] }}</q-badge>
      <span v-else-if="col.name === 'actions'">
         <q-btn size="sm" color="primary"
                :icon="props.row.status === 'running' ? 'pause' : 'play_arrow'"
                :disable="props.row.status === 'idle' && props.row.login_blocked"
                @click.stop="$event.currentTarget.dispatchEvent(new CustomEvent('rowaction', {detail: {action: props.row.status === 'running' ? 'pause' : (props.row.status === 'waiting' ? 'resume' : 'run'), id: props.row.status === 'waiting' ? props.row.active_run_id : props.row.id, task: props.row.task}, bubbles: true}))">
           <q-tooltip>{{ props.row.status === 'running' ? 'Pause at next step boundary' : (props.row.status === 'waiting' ? 'Resume run' : (props.row.login_blocked ? 'Run now (login blocked)' : 'Run now')) }}</q-tooltip>
         </q-btn>
         <q-btn size="sm" color="negative" icon="stop"
                :disable="props.row.status !== 'running' && props.row.status !== 'waiting'"
               @click.stop="$event.currentTarget.dispatchEvent(new CustomEvent('rowaction', {detail: {action: 'stop', id: props.row.id, task: props.row.task}, bubbles: true}))">
          <q-tooltip>Stop run</q-tooltip>
        </q-btn>
        <q-btn size="sm" icon="edit"
               @click.stop="$event.currentTarget.dispatchEvent(new CustomEvent('rowaction', {detail: {action: 'edit', id: props.row.id, task: props.row.task}, bubbles: true}))">
          <q-tooltip>Edit task (cron, enabled)</q-tooltip>
        </q-btn>
        <q-btn size="sm" icon="open_in_browser"
               :disable="!props.row.active_run_id && !props.row.latest_run_id"
               @click.stop="$event.currentTarget.dispatchEvent(new CustomEvent('rowaction', {detail: {action: 'view-run', id: props.row.active_run_id || props.row.latest_run_id, task: props.row.task}, bubbles: true}))">
          <q-tooltip>View run</q-tooltip>
        </q-btn>
      </span>
    <span v-else :class="col.mono ? 'font-mono' : ''">{{ props.row[col.name] }}</span>
  </q-td>
</q-tr>
"""


def _truncate(name: str, width: int = DOWNLOAD_NAME_WIDTH) -> str:
    """Truncate a filename for the last-download column (spec)."""
    return name if len(name) <= width else name[:width - 3] + "..."


def next_run(scheduler: TaskScheduler, task_id: int) -> str:
    """The task's next cron fire from the live jobstore (D2.3).

    ``Task.next_run`` is not maintained by the scheduler, so the display
    reads the APScheduler job's ``next_run_time`` (job id ``task-<id>``).
    Disabled tasks have no job: ``—``."""
    if not scheduler.scheduler.running:
        return "—"
    job = scheduler.scheduler.get_job(job_id_for(task_id))
    if job is None or job.next_run_time is None:
        return "—"
    return job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")


# One-line hover tooltips for the three KPI cards (locked decision: every
# new chrome element carries mouse-over text).
KPI_TASKS_TIP = "Enabled/total tasks; running and waiting right now."
KPI_DOWNLOADS_TIP = "Files collected in the last 30 days (all states)."
KPI_NEXT_RUN_TIP = "Time to the next scheduled cron fire (enabled tasks)."


def next_run_countdown(scheduler: TaskScheduler, db: Database):
    """The earliest upcoming cron fire as ``(datetime, task)``.

    Mirrors :func:`next_run`'s jobstore pattern (job id ``task-<id>``)
    but returns the raw datetimes, so the KPI strip can take the min over
    enabled tasks and render a live countdown. ``(None, None)`` when no
    enabled task has a scheduled job (or the scheduler is stopped)."""
    if not scheduler.scheduler.running:
        return None, None
    best_dt = None
    best_task = None
    for task in db.list_tasks():
        if not task["enabled"]:
            continue
        job = scheduler.scheduler.get_job(job_id_for(task["id"]))
        if job is None or job.next_run_time is None:
            continue
        if best_dt is None or job.next_run_time < best_dt:
            best_dt = job.next_run_time
            best_task = task
    return best_dt, best_task


def _countdown(dt) -> str:
    """Format a future datetime as ``in HH:MM:SS`` (floored at zero)."""
    total = int((dt - datetime.now(dt.tzinfo)).total_seconds())
    if total < 0:
        total = 0
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"in {h:02d}:{m:02d}:{s:02d}"


def kpi_data(db: Database, scheduler: TaskScheduler) -> dict:
    """The KPI strip's three ``(value, sub)`` pairs, recomputed per poll.

    Kept separate from the render so it is unit-testable without a
    browser: task counts by status, the downloads inside the 30-day
    window (all delivery states), and the next cron fire's countdown +
    its task's ``service/user``.
    """
    tasks = db.list_tasks()
    total = len(tasks)
    enabled = sum(1 for t in tasks if t["enabled"])
    running = sum(1 for t in tasks if t["status"] == "running")
    waiting = sum(1 for t in tasks if t["status"] == "waiting")
    task_sub = (f"{running} running · {waiting} waiting"
                if (running or waiting) else "all idle")

    cutoff = (datetime.now() - timedelta(days=30)).strftime(
        "%Y-%m-%d %H:%M:%S")
    window = [d for d in db.list_downloads()
              if (d["created_at"] or "") >= cutoff]
    newest = max((d["created_at"] for d in window if d["created_at"]),
                 default="")

    dt, task = next_run_countdown(scheduler, db)
    if dt is None:
        next_value, next_sub = "—", ""
    else:
        next_value = _countdown(dt)
        next_sub = f"{task['service']} / {task['user'] or '—'}"

    return {
        "tasks": (f"{enabled}/{total}", task_sub),
        "downloads": (str(len(window)), newest[:10] or "—"),
        "next_run": (next_value, next_sub),
    }


def _last_run_cell(run) -> str:
    """Last run: timestamp + result + collection outcome (``—`` when the
    task never ran; the outcome is omitted when the row predates it)."""
    if run is None:
        return "—"
    result = run["result"] or "running"
    text = f"{run['started_at'] or '—'} · {result}"
    if run["collection_outcome"]:
        text += f" · {run['collection_outcome']}"
    return text


def _session_cell(task, latest_run) -> str:
    """Session facts only (spec): profile dir present? + last used (the
    newest run's started_at) + last reset (``profile_reset_at``, D3.4)."""
    profile = task["profile_dir"]
    present = bool(profile) and Path(profile).exists()
    used = (latest_run["started_at"] or "")[:10] if latest_run else ""
    parts = ["profile present" if present else "profile missing"]
    parts.append(f"last used {used}" if used else "never used")
    if task["profile_reset_at"]:
        parts.append(f"reset {task['profile_reset_at'][:10]}")
    return " · ".join(parts)


def _download_cell(db: Database, task_id: int) -> str:
    """Last download: newest filename (truncated) + date (spec)."""
    downloads = db.list_downloads(task_id=task_id)
    if not downloads:
        return "—"
    last = downloads[-1]
    name = last["filename"] or "—"
    return f"{_truncate(name)} · {(last['created_at'] or '')[:10]}"


def build_rows(db: Database, scheduler: TaskScheduler,
               service: str = "All", status: str = "All") -> list[dict]:
    """One display row per task, filtered and sorted per the spec.

    Rows are sorted by service/user only - a task keeps its row position
    while it runs (``running``/``waiting`` rows do not jump to the top);
    the hidden ``id``/``service``/``user`` fields carry the row key (the
    table's ``row_key``) and the sort order. ``active_run_id`` carries
    the task's newest active run (``result IS NULL``; ``None`` when the
    task has no live run) and ``latest_run_id`` the task's newest Run
    row at all (``None`` when the task never ran) - together they are
    the per-row **View run** button's target (``active_run_id ||
    latest_run_id``: a live run opens the live session view, a finished
    one the ended view; the body-slot template cannot query the DB, so
    the ids are resolved here and only the button, not a cell, reads
    them)."""
    active_by_task = {}
    for run in db.list_active_runs():
        active_by_task[run["task_id"]] = run["id"]
    rows = []
    for task in db.list_tasks():
        if service != "All" and task["service"] != service:
            continue
        if status != "All" and task["status"] != status:
            continue
        runs = db.list_runs(task["id"])
        latest = runs[0] if runs else None
        rows.append({
            "id": task["id"],
            "service": task["service"],
            "user": task["user"],
            "task": f"{task['service']} / {task['user'] or '—'}",
            "status": task["status"],
            "login_blocked": bool(task["login_locked"] or task["login_pending_run_id"] is not None),
            "login": ("blocked" if task["login_locked"] else
                      "pending" if task["login_pending_run_id"] is not None else "available"),
            "last_run": _last_run_cell(latest),
            "next_run": next_run(scheduler, task["id"]),
            "session": _session_cell(task, latest),
            "last_download": _download_cell(db, task["id"]),
            "active_run_id": active_by_task.get(task["id"]),
            "latest_run_id": latest["id"] if latest else None,
        })
    rows.sort(key=lambda r: (r["service"], r["user"] or ""))
    return rows


def _default_run(db: Database):
    """The run the log pane follows initially: the most recent running
    run, else the most recent waiting run, else the most recent finished
    run (spec)."""
    active = db.list_active_runs()
    if active:
        for run in reversed(active):
            task = db.get_task(run["task_id"])
            if task is not None and task["status"] == "running":
                return run
        return active[-1]
    for run in db.list_runs():
        if run["result"] is not None:
            return run
    return None


def register_dashboard(db: Database, orchestrator: Orchestrator,
                       scheduler: TaskScheduler) -> None:
    """Register the dashboard (``/``) and the ntfy deep-link route
    (``/runs/<run_id>``)."""

    @ui.page("/", title="BillCollector")
    def index(request: Request) -> None:
        redirect = require_auth(request)
        if redirect is not None:
            return redirect
        build_layout(active="Dashboard",
                     daemon_running=scheduler.scheduler.running)

        # ---- KPI strip (above the toolbar) --------------------------------
        # Three cards: task counts, downloads in the last 30 days, and the
        # next cron fire's live countdown. The value/sub labels are updated
        # in place on each poll (set_kpi) rather than rebuilt.
        data = kpi_data(db, scheduler)
        with ui.grid(columns=3).classes("w-full gap-3").mark("kpi-strip"):
            kpi_tasks = kpi_card("Tasks", data["tasks"][0],
                                 data["tasks"][1],
                                 tooltip=KPI_TASKS_TIP).mark("kpi-tasks")
            kpi_downloads = kpi_card(
                "Downloads (30 days)", data["downloads"][0],
                data["downloads"][1],
                tooltip=KPI_DOWNLOADS_TIP).mark("kpi-downloads")
            kpi_next = kpi_card("Next run", data["next_run"][0],
                                data["next_run"][1],
                                tooltip=KPI_NEXT_RUN_TIP).mark("kpi-next")
        kpi_tasks.kpi_value.mark("kpi-tasks-value")
        kpi_downloads.kpi_value.mark("kpi-downloads-value")
        kpi_next.kpi_value.mark("kpi-next-value")

        services = sorted({t["service"] for t in db.list_tasks()})
        service_select = ui.select(["All"] + services, value="All",
                                   label="Service").mark("service-filter")
        status_select = ui.select(["All"] + list(STATUSES), value="All",
                                  label="Status").mark("status-filter")
        rows = build_rows(db, scheduler)
        waiting = sum(1 for r in rows if r["status"] == "waiting")
        waiting_badge = ui.badge(f"{waiting} waiting",
                                 color="orange" if waiting else "grey")
        run_filtered_btn = ui.button("Run (filtered)", icon="play_arrow").mark("run-filtered")
        add_task_btn = ui.button(icon="add").mark("add-task")
        with add_task_btn:
            ui.tooltip("Add task")
        ui.space()

        table = ui.table(columns=COLUMNS, rows=rows).classes("w-full")
        table.add_slot("body", ROW_BODY)

        pane = LogPane(orchestrator)

        def refresh_log() -> None:
            """Follow the run the pane should show (D2.2/D2.3 live log):
            the most recent active run, else the most recent finished run
            (the dashboard has no run selector, so a run started via Run now
            is picked up on the next poll and streams live from there - the
            pane loads the log file on follow, then receives live lines)."""
            run = _default_run(db)
            if run is not None and pane.selected_run_id != run["id"]:
                pane.follow(run)

        refresh_log()

        # ---- Step screenshots of the followed run -------------------------
        # The run's step thumbnails (D4.1b also shows them in the task
        # detail's run expansion; the dashboard strip is the at-a-glance
        # view the operator asked for): the followed run's PageStatus
        # screenshots as a compact row, rebuilt only when the followed
        # run or its step rows change, so the strip fills in live while a
        # run is in progress. A thumbnail click opens the full image in a
        # dialog (a plain element handler - the strip is built from real
        # NiceGUI elements, not a slot template, so no CustomEvent is
        # needed).
        steps_box = ui.column().classes("w-full")
        steps_sig = {"sig": None}

        def open_shot(url: str) -> None:
            """Thumbnail click -> the full image in a dialog."""
            with ui.dialog() as dlg:
                dlg.open()
                ui.image(url).classes("max-h-[80vh]")

        def render_steps() -> None:
            """Rebuild the strip when the followed run or its step rows
            changed (the signature: the run id + the PageStatus ids)."""
            run_id = pane.selected_run_id
            rows = db.list_page_status(run_id) if run_id is not None else []
            sig = (run_id, tuple(r["id"] for r in rows))
            if sig == steps_sig["sig"]:
                return
            steps_sig["sig"] = sig
            steps_box.clear()
            shots = []
            for r in rows:
                url = runfile_url(r["screenshot_path"])
                if url:
                    shots.append((r["step_number"], url))
            if not shots:
                return
            with steps_box:
                ui.label(f"Steps · Run {run_id}").classes("text-h6") \
                    .mark("step-thumbs-label")
                with ui.row().classes("items-end gap-2 step-thumbs") \
                        .mark("step-thumbs"):
                    for step_no, url in shots:
                        with ui.column().classes("items-center gap-1"):
                            ui.image(url).classes(
                                "h-20 cursor-pointer rounded") \
                                .on("click", lambda _e, u=url: open_shot(u))
                            ui.label(
                                str(step_no if step_no is not None else "—")
                            ).classes("text-xs text-slate-400")

        render_steps()

        def refresh() -> None:
            """DB poll (~2 s): rebuild the table and the waiting badge,
            re-point the log pane at the run it should follow, and refresh
            the step strip of the followed run."""
            rows = build_rows(db, scheduler,
                              service=service_select.value or "All",
                              status=status_select.value or "All")
            table.rows = rows
            waiting = sum(1 for r in rows if r["status"] == "waiting")
            waiting_badge.set_text(f"{waiting} waiting")
            waiting_badge.props(
                f"color={'orange' if waiting else 'grey'}")
            data = kpi_data(db, scheduler)
            set_kpi(kpi_tasks, *data["tasks"])
            set_kpi(kpi_downloads, *data["downloads"])
            set_kpi(kpi_next, *data["next_run"])
            refresh_log()
            render_steps()

        service_select.on_value_change(lambda _e: refresh())
        status_select.on_value_change(lambda _e: refresh())
        ui.timer(REFRESH_INTERVAL, refresh)

        def on_row_click(e) -> None:
            """Row click -> task detail (the tr dispatches the bubbling
            rowclick CustomEvent; see ROW_BODY)."""
            detail = e.args if isinstance(e.args, dict) else {}
            task_id = detail.get("id")
            if task_id is not None:
                ui.navigate.to(f"/tasks/{task_id}")

        # The js_handler emits the CustomEvent's bare ``detail`` payload
        # (the rowaction contract; the User simulation's
        # ``trigger("rowclick", ...)`` delivers the same bare payload).
        table.on("rowclick", on_row_click,
                 js_handler="(event) => emit(event.detail)")

        def on_run_filtered(_e) -> None:
            """Toolbar Run (filtered): enqueue every *enabled* task in the
            filtered set (D3.2). The global semaphore serializes the runs;
            disabled and already-active tasks are skipped and reported."""
            rows = build_rows(db, scheduler,
                              service=service_select.value or "All",
                              status=status_select.value or "All")
            enqueued = []
            skipped = []
            for row in rows:
                task = db.get_task(row["id"])
                if task is None:
                    continue
                if not task["enabled"]:
                    skipped.append(f"{row['task']} (disabled)")
                    continue
                if task["login_locked"] or task["login_pending_run_id"] is not None:
                    skipped.append(f"{row['task']} (login blocked)")
                    continue
                if task["status"] in ("running", "waiting"):
                    skipped.append(f"{row['task']} (active)")
                    continue
                enqueued.append(row["task"])
                background_tasks.create(orchestrator.start_run(row["id"]))
            if enqueued:
                ui.notify(f"Run enqueued for {len(enqueued)} task(s)")
            if skipped:
                ui.notify("Skipped: " + ", ".join(skipped), type="warning")
            if not enqueued and not skipped:
                ui.notify("No tasks in the filtered set", type="warning")

        run_filtered_btn.on("click", on_run_filtered)

        def on_add_task(_e) -> None:
            """Toolbar Add task (D3.3): the create dialog."""
            open_task_dialog(db, scheduler, refresh)

        add_task_btn.on("click", on_add_task)

        async def on_row_action(e) -> None:
            """Row action buttons (D3.2/D3.3): Run/Pause/Resume / Stop /
            Edit / View run, routed from the body-slot icon buttons
            through the ``rowaction`` CustomEvent (see ROW_BODY). Run
            now works for disabled tasks too (manual one-off, schedule
            unchanged); Pause sends the runner the manual-pause signal
            (pause at the next step boundary) and, like Stop, only
            reaches a live runner; Resume sends the paused run's
            control socket the protocol ``resume`` (the session page's
            own path) - its payload ``id`` is the run id, not the task
            id. The claim inside start_run stays the authoritative
            double-start guard. Edit opens the D3.3 task dialog (cron +
            enabled). View run navigates same-tab to the run's session
            page (``/runs/<run_id>``); its payload ``id`` is the row's
            newest run id (live first, else the last finished one - the
            run id, not the task id)."""
            detail = e.args if isinstance(e.args, dict) else {}
            if detail.get("action") == "view-run":
                # The navigation leaves the page, so do not refresh. The
                # None guard covers the edge where the run row was just
                # finalized; it self-heals on the next ~2 s poll.
                run_id = detail.get("id")
                if run_id is None:
                    ui.notify(f"{detail.get('task')}: no run",
                              type="warning")
                    return
                ui.navigate.to(f"/runs/{run_id}")
                return
            if detail.get("action") == "resume":
                # The payload id is the run id (the row's active run):
                # the resume goes to that run's control socket, the same
                # path the session page's Resume button uses. A dead
                # socket (the pause resolved, the run ended) degrades to
                # a notify; the ~2 s poll shows the true state.
                run = (db.get_run(detail.get("id"))
                       if detail.get("id") is not None else None)
                if run is None or not control_sock_alive(run):
                    ui.notify(f"{detail.get('task')}: no active pause to "
                              "resume", type="warning")
                else:
                    try:
                        await asyncio.to_thread(
                            send_action, run["control_sock"], "resume")
                    except ControlError:
                        ui.notify(f"{detail.get('task')}: the run ended "
                                  "while resuming", type="warning")
                refresh()
                return
            task_id = detail.get("id")
            if task_id is None:
                return
            if detail.get("action") == "run":
                started = await orchestrator.start_run(task_id)
                if not started:
                    ui.notify(f"{detail.get('task', task_id)}: not started "
                              "(already running/waiting?)", type="warning")
            elif detail.get("action") == "pause":
                paused = orchestrator.pause_run(task_id)
                if not paused:
                    ui.notify(f"{detail.get('task', task_id)}: no live "
                              "runner to pause", type="warning")
            elif detail.get("action") == "stop":
                stopped = await orchestrator.stop_run(task_id)
                if not stopped:
                    ui.notify(f"{detail.get('task', task_id)}: no live "
                              "runner to stop", type="warning")
            elif detail.get("action") == "edit":
                open_task_dialog(db, scheduler, refresh, task_id=task_id)
                return
            # Refresh immediately so the button states (the morphing
            # button per status, Stop enabled while running or waiting)
            # follow the new status without waiting for the ~2 s poll.
            refresh()

        # The js_handler emits the CustomEvent's bare ``detail`` payload:
        # with the ``["detail"]`` args spec instead, the client only
        # filters the event's fields and the server receives
        # ``{"detail": ...}`` (wrapped), which the handler above does not
        # expect. The bare payload is also exactly what the User
        # simulation's ``trigger("rowaction", ...)`` delivers, so both
        # paths agree on the contract.
        table.on("rowaction", on_row_action,
                 js_handler="(event) => emit(event.detail)")

        ui.context.client.on_disconnect(pane.close)
