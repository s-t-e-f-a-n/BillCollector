# -*- coding: utf-8 -*-
"""Dashboard page for the daemon UI (M2 chunk D2).

The operator's home page (spec: gui-concept-dashboard-spec, "Dashboard
specification"): a toolbar with the service/status filters and the
``[N waiting]`` badge, one table row per task (status color-coded,
``waiting`` rows highlighted, ``running``/``waiting`` sorted first), and
a live log pane that follows the selected run.

The run buttons land in D3; the task detail page is a placeholder until
D4. ``ui.timer`` polls the DB (~2 s) and refreshes the table and badge
(WAL reads); the log pane reads the run's log file once, then follows
the orchestrator's log subscribers (D2.2).
"""

from pathlib import Path

from fastapi import Request
from nicegui import ui

from ..db import Database
from ..orchestrator import Orchestrator
from ..scheduler import TaskScheduler, job_id_for
from .auth import require_auth
from .layout import build_layout

# The task statuses a row can carry (Run results are a separate axis).
STATUSES = ("idle", "running", "waiting")

# The log pane keeps at most this many lines (spec: ~2000).
LOG_MAX_LINES = 2000

# Last-download filenames are truncated to this width (spec).
DOWNLOAD_NAME_WIDTH = 30

# The DB poll interval of the dashboard refresh (~2 s per the spec).
REFRESH_INTERVAL = 2.0

COLUMNS = [
    {"name": "task", "label": "Service / User", "field": "task"},
    {"name": "status", "label": "Status", "field": "status"},
    {"name": "last_run", "label": "Last run", "field": "last_run"},
    {"name": "next_run", "label": "Next run", "field": "next_run"},
    {"name": "session", "label": "Session", "field": "session"},
    {"name": "last_download", "label": "Last download", "field": "last_download"},
]

# Custom row body: plain string cells cannot carry colors, so the cells
# are rendered through the QTable body slot - a color-coded status badge
# and the highlight of waiting rows (spec).
#
# The template must NOT be wrapped in <template v-slot="props">: NiceGUI
# compiles the slot string with the Vue *runtime* compiler (nicegui.js),
# which passes the slot scope in as the component prop ``props``. A
# v-slot-wrapped root is an SFC-only construct and makes the runtime
# compiler crash (TypeError: reading 'type'), blanking the whole page.
ROW_BODY = """
<q-tr :props="props" :class="props.row.status === 'waiting' ? 'bg-amber-100' : ''">
  <q-td v-for="col in props.cols" :key="col.name" :props="{ ...props, col: col }">
    <q-badge v-if="col.name === 'status'"
             :color="props.row.status === 'running' ? 'blue' : (props.row.status === 'waiting' ? 'orange' : 'grey')"
             outline>{{ props.row[col.name] }}</q-badge>
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
    newest run's started_at). The last reset lands with D3.4 (the
    ``profile_reset_at`` column)."""
    profile = task["profile_dir"]
    present = bool(profile) and Path(profile).exists()
    used = (latest_run["started_at"] or "")[:10] if latest_run else ""
    parts = ["profile present" if present else "profile missing"]
    parts.append(f"last used {used}" if used else "never used")
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
        ui.space()

        table = ui.table(columns=COLUMNS, rows=rows).classes("w-full")
        table.add_slot("body", ROW_BODY)

        log = ui.log(max_lines=LOG_MAX_LINES).classes("w-full h-64")
        selected_run_id = {"id": None}

        def load_run_log(run) -> None:
            """Show the run's log file content (the pane's initial state)."""
            log.clear()
            if run is not None and run["log_path"]:
                path = Path(run["log_path"])
                if path.exists():
                    for line in path.read_text(encoding="utf-8",
                                               errors="replace").splitlines():
                        log.push(line)

        def on_log_line(task_id: int, run_id, line: str) -> None:
            """Live lines (D2.2) for the followed run only."""
            if run_id is not None and run_id == selected_run_id["id"]:
                log.push(line)

        initial = _default_run(db)
        if initial is not None:
            selected_run_id["id"] = initial["id"]
        load_run_log(initial)
        orchestrator.add_log_subscriber(on_log_line)

        def refresh() -> None:
            """DB poll (~2 s): rebuild the table and the waiting badge."""
            rows = build_rows(db, scheduler,
                              service=service_select.value or "All",
                              status=status_select.value or "All")
            table.rows = rows
            waiting = sum(1 for r in rows if r["status"] == "waiting")
            waiting_badge.set_text(f"{waiting} waiting")
            waiting_badge.props(
                f"color={'orange' if waiting else 'grey'}")

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

        ui.context.client.on_disconnect(
            lambda: orchestrator.remove_log_subscriber(on_log_line))

    @ui.page("/runs/{run_id}")
    def runs_redirect(request: Request, run_id: int) -> None:
        """The ntfy deep link: the session view is M3, so the run's task
        detail page is the target until then (D2.3)."""
        redirect = require_auth(request)
        if redirect is not None:
            return redirect
        run = db.get_run(run_id)
        if run is None:
            build_layout()
            ui.label(f"Unknown run id: {run_id} (404)").classes("text-red-600")
            return
        ui.navigate.to(f"/tasks/{run['task_id']}")
