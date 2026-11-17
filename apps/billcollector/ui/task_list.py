# -*- coding: utf-8 -*-
"""Task index page (``/tasks``).

One row per task: the task label (service/user), the status badge, the
enabled flag, the cron, the last run (timestamp + result badge) and the
next cron fire. Rows are sorted by service, then user; a row click
navigates to the task detail (``/tasks/<task_id>``). No run actions and
no dialogs live here - those stay on the dashboard and the task detail.

``ui.timer`` polls the DB (~2 s, the app's existing regime) and rebuilds
the table. The column list follows the shared table convention
(``format.table_column``; mono on Cron / Last run / Next run).
"""

from fastapi import Request
from nicegui import ui

from ..db import Database
from ..scheduler import TaskScheduler
from .auth import require_auth
from .dashboard import next_run
from .format import table_column
from .layout import build_layout

# The DB poll interval of the page refresh (the dashboard's ~2 s).
REFRESH_INTERVAL = 2.0

# The badge colors of a run result in the Last run cell (a still-running
# run has no result, hence no badge - the task's status badge carries the
# live state).
RESULT_COLORS = {
    "success": "green",
    "failure": "red",
    "needs_attention": "orange",
    "interrupted": "grey",
    "cancelled": "grey",
}

COLUMNS = [
    table_column("task", "Task"),
    table_column("status", "Status"),
    table_column("enabled", "Enabled"),
    table_column("cron", "Cron", mono=True),
    table_column("last_run", "Last run", mono=True),
    table_column("next_run", "Next run", mono=True),
]

# Custom row body: plain string cells cannot carry the status badge or the
# last-run result badge, so the cells render through the QTable body slot.
# The template must NOT be wrapped in <template v-slot="props"> (see the
# dashboard's ROW_BODY note): the runtime compiler passes the slot scope in
# as the component prop ``props``. The result badge's color is resolved on
# the Python side (``last_run_result_color``) because the runtime-compiled
# template has no module scope to look colors up in.
ROW_BODY = """
<q-tr :props="props">
  <q-td v-for="col in props.cols" :key="col.name" :props="{ ...props, col: col }">
    <q-badge v-if="col.name === 'status'"
             :color="props.row.status === 'running' ? 'blue' : (props.row.status === 'waiting' ? 'orange' : 'grey')"
             outline>{{ props.row[col.name] }}</q-badge>
    <span v-else-if="col.name === 'last_run'">
      <template v-if="props.row.last_run_result">
        <span :class="col.mono ? 'font-mono' : ''">{{ props.row.last_run_date }}</span>
        <q-badge :color="props.row.last_run_result_color"
                 outline class="ml-1">{{ props.row.last_run_result }}</q-badge>
      </template>
      <span v-else :class="col.mono ? 'font-mono' : ''">—</span>
    </span>
    <span v-else-if="col.name === 'enabled'" class="text-grey-6">{{ props.row[col.name] }}</span>
    <span v-else :class="col.mono ? 'font-mono' : ''">{{ props.row[col.name] }}</span>
  </q-td>
</q-tr>
"""


def build_rows(db: Database, scheduler: TaskScheduler) -> list[dict]:
    """One display row per task, sorted by service then user.

    ``last_run_date``/``last_run_result`` carry the task's newest Run row
    (``db.list_runs`` is id-DESC, so row 0 is the newest); a task that
    never ran has both None (the cell renders ``—``)."""
    rows = []
    for task in db.list_tasks():
        runs = db.list_runs(task["id"])
        latest = runs[0] if runs else None
        result = latest["result"] if latest else None
        rows.append({
            "id": task["id"],
            "task": f"{task['service']} / {task['user'] or '—'}",
            "status": task["status"],
            "enabled": "yes" if task["enabled"] else "no",
            "cron": task["cron"] or "—",
            "last_run_date": (latest["started_at"] or "—") if latest else None,
            "last_run_result": result,
            "last_run_result_color": RESULT_COLORS.get(result, "grey"),
            "next_run": next_run(scheduler, task["id"]),
        })
    rows.sort(key=lambda r: (r["task"].split(" / ")[0],
                             r["task"].split(" / ")[1]))
    return rows


def register_task_index(db: Database, scheduler: TaskScheduler) -> None:
    """Register the task index page (``/tasks``)."""

    @ui.page("/tasks", title="Tasks")
    def task_index(request: Request) -> None:
        redirect = require_auth(request)
        if redirect is not None:
            return redirect
        build_layout(active="Tasks")

        ui.label("Tasks").classes("text-h5 font-bold")

        rows = build_rows(db, scheduler)
        table = ui.table(columns=COLUMNS, rows=rows).classes("w-full")
        table.add_slot("body", ROW_BODY)

        empty = ui.column().classes("gap-1")
        empty.visible = not rows
        with empty:
            ui.label("No tasks yet.").classes("text-grey-7")
            with ui.link("Open the dashboard to add the first task", "/") \
                    .classes("text-blue-700"):
                ui.icon("dashboard").classes("text-xl")

        def refresh() -> None:
            """DB poll (~2 s): rebuild the table, toggle the empty state."""
            rows = build_rows(db, scheduler)
            table.rows = rows
            empty.visible = not rows

        ui.timer(REFRESH_INTERVAL, refresh)

        def on_row_click(e) -> None:
            """Row click -> task detail (the same pattern as the
            dashboard)."""
            args = e.args
            row = args.get("row") if isinstance(args, dict) else args
            if isinstance(row, dict) and "id" in row:
                ui.navigate.to(f"/tasks/{row['id']}")

        table.on("rowclick", on_row_click)
