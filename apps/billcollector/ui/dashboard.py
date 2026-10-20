# -*- coding: utf-8 -*-
"""Dashboard page for the daemon UI (M2 chunk D2, run actions D3.2).

The operator's home page (spec: gui-concept-dashboard-spec, "Dashboard
specification"): a toolbar with the service/status filters, the
``[N waiting]`` badge and the **Run (filtered)** button, one table row
per task (status color-coded, ``waiting`` rows highlighted,
``running``/``waiting`` sorted first) with a per-row **Run now** /
**Stop** action column, and a live log pane that follows the selected
run.

D3.2 run actions: all calls go through ``orchestrator.start_run`` /
``stop_run`` (the same callbacks the scheduler uses). Row **Run now**
works for disabled tasks too (manual one-off; the schedule is
untouched) and is disabled while the task is active; **Stop** is
enabled only while running. **Run (filtered)** enqueues all *enabled*
tasks in the filtered set (the global semaphore serializes; skipped
tasks are reported in a notify).

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

from pathlib import Path

from fastapi import Request
from nicegui import background_tasks
from nicegui import ui

from ..db import Database
from ..orchestrator import Orchestrator
from ..scheduler import TaskScheduler, job_id_for
from .auth import require_auth
from .layout import build_layout
from .logpane import LogPane
from .runfiles import runfile_url
from .tasks import open_task_dialog

# The task statuses a row can carry (Run results are a separate axis).
STATUSES = ("idle", "running", "waiting")

# Last-download filenames are truncated to this width (spec).
DOWNLOAD_NAME_WIDTH = 30

# The DB poll interval of the dashboard refresh (~2 s per the spec).
REFRESH_INTERVAL = 2.0

COLUMNS = [
    {"name": "task", "label": "Service / User", "field": "task"},
    {"name": "status", "label": "Status", "field": "status"},
    {"name": "login", "label": "Login", "field": "login"},
    {"name": "last_run", "label": "Last run", "field": "last_run"},
    {"name": "next_run", "label": "Next run", "field": "next_run"},
    {"name": "session", "label": "Session", "field": "session"},
    {"name": "last_download", "label": "Last download", "field": "last_download"},
    {"name": "actions", "label": "Actions", "field": "actions"},
]

# Custom row body: plain string cells cannot carry colors (or buttons),
# so the cells are rendered through the QTable body slot - a color-coded
# status badge, the highlight of waiting rows (spec), and the D3.2 run
# action buttons.
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
# task-detail navigation.
ROW_BODY = """
<q-tr :props="props" :class="props.row.status === 'waiting' ? 'bg-amber-100' : ''">
  <q-td v-for="col in props.cols" :key="col.name" :props="{ ...props, col: col }">
    <q-badge v-if="col.name === 'status'"
             :color="props.row.status === 'running' ? 'blue' : (props.row.status === 'waiting' ? 'orange' : 'grey')"
             outline>{{ props.row[col.name] }}</q-badge>
     <span v-else-if="col.name === 'actions'">
       <q-btn size="sm" color="primary" label="Run now"
              :disable="props.row.login_blocked || props.row.status === 'running' || props.row.status === 'waiting'"
              @click.stop="$event.currentTarget.dispatchEvent(new CustomEvent('rowaction', {detail: {action: 'run', id: props.row.id, task: props.row.task}, bubbles: true}))"/>
       <q-btn size="sm" color="negative" label="Stop"
              :disable="props.row.status !== 'running'"
              @click.stop="$event.currentTarget.dispatchEvent(new CustomEvent('rowaction', {detail: {action: 'stop', id: props.row.id, task: props.row.task}, bubbles: true}))"/>
       <q-btn size="sm" label="Edit"
              @click.stop="$event.currentTarget.dispatchEvent(new CustomEvent('rowaction', {detail: {action: 'edit', id: props.row.id, task: props.row.task}, bubbles: true}))"/>
     </span>
    <span v-else>{{ props.row[col.name] }}</span>
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


def _last_run_cell(run) -> str:
    """Last run: timestamp + result (``—`` when the task never ran)."""
    if run is None:
        return "—"
    result = run["result"] or "running"
    return f"{run['started_at'] or '—'} · {result}"


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

    ``running``/``waiting`` rows come first, then service/user; the
    hidden ``id``/``service``/``user`` fields carry the row key (the
    table's ``row_key``) and the sort order."""
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
        })
    rows.sort(key=lambda r: (0 if r["status"] in ("running", "waiting") else 1,
                             r["service"], r["user"] or ""))
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
        build_layout(active="Dashboard")

        services = sorted({t["service"] for t in db.list_tasks()})
        service_select = ui.select(["All"] + services, value="All",
                                   label="Service").mark("service-filter")
        status_select = ui.select(["All"] + list(STATUSES), value="All",
                                  label="Status").mark("status-filter")
        rows = build_rows(db, scheduler)
        waiting = sum(1 for r in rows if r["status"] == "waiting")
        waiting_badge = ui.badge(f"{waiting} waiting",
                                 color="orange" if waiting else "grey")
        run_filtered_btn = ui.button("Run (filtered)").mark("run-filtered")
        add_task_btn = ui.button("Add task").mark("add-task")
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
                            ).classes("text-xs text-grey-6")

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
            refresh_log()
            render_steps()

        service_select.on_value_change(lambda _e: refresh())
        status_select.on_value_change(lambda _e: refresh())
        ui.timer(REFRESH_INTERVAL, refresh)

        def on_row_click(e) -> None:
            """Row click -> task detail (the full page lands in D4)."""
            args = e.args
            row = args.get("row") if isinstance(args, dict) else args
            if isinstance(row, dict) and "id" in row:
                ui.navigate.to(f"/tasks/{row['id']}")

        table.on("rowclick", on_row_click)

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
            """Row action buttons (D3.2/D3.3): Run now / Stop / Edit,
            routed from the body-slot buttons through the ``rowaction``
            CustomEvent (see ROW_BODY). Run now works for disabled tasks
            too (manual one-off, schedule unchanged); Stop only reaches a
            live runner. The claim inside start_run stays the
            authoritative double-start guard. Edit opens the D3.3 task
            dialog (cron + enabled)."""
            detail = e.args if isinstance(e.args, dict) else {}
            task_id = detail.get("id")
            if task_id is None:
                return
            if detail.get("action") == "run":
                started = await orchestrator.start_run(task_id)
                if not started:
                    ui.notify(f"{detail.get('task', task_id)}: not started "
                              "(already running/waiting?)", type="warning")
            elif detail.get("action") == "stop":
                stopped = await orchestrator.stop_run(task_id)
                if not stopped:
                    ui.notify(f"{detail.get('task', task_id)}: no live "
                              "runner to stop", type="warning")
            elif detail.get("action") == "edit":
                open_task_dialog(db, scheduler, refresh, task_id=task_id)
                return
            # Refresh immediately so the button states (Run now disabled
            # while active, Stop enabled only while running) follow the
            # new status without waiting for the ~2 s poll.
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
