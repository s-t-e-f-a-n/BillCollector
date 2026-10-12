# -*- coding: utf-8 -*-
"""Downloads page (M2 chunk D4.3).

``/downloads`` lists every Download row (task service/user, run,
filename, size, truncated sha256, the duplicate_of badge, date), newest
first, with an optional task filter. Read-only in M2 (the download
management itself is not part of the M2 surface). The row builder and
the body slot are shared with the task detail page's downloads section
(D4.1), so both views render the same columns.
"""

from fastapi import Request
from nicegui import ui

from ..db import Database
from .auth import require_auth
from .layout import build_layout

# The width a filename is truncated to on the page.
NAME_WIDTH = 40

COLUMNS = [
    {"name": "task", "label": "Task", "field": "task"},
    {"name": "run", "label": "Run", "field": "run"},
    {"name": "filename", "label": "Filename", "field": "filename"},
    {"name": "size", "label": "Size", "field": "size"},
    {"name": "sha256", "label": "SHA256", "field": "sha256"},
    {"name": "duplicate", "label": "Duplicate", "field": "duplicate"},
    {"name": "date", "label": "Date", "field": "date"},
]

# A deduplicated download is rendered as an outlined badge (a plain
# string cell cannot carry one): the slot draws the ``duplicate`` cell
# as a ``q-badge`` whenever it is not ``—`` (the same slot pattern as
# the dashboard's body).
BODY = """
<q-tr :props="props">
  <q-td v-for="col in props.cols" :key="col.name">
    <q-badge v-if="col.name === 'duplicate' && props.row[col.name] !== '—'"
             color="orange" outline>{{ props.row[col.name] }}</q-badge>
    <span v-else>{{ props.row[col.name] }}</span>
  </q-td>
</q-tr>
"""


def _size(value) -> str:
    """A byte count as ``12,345 B`` (``—`` when unknown)."""
    return "—" if value is None else f"{value:,} B"


def _truncate(name, width: int = NAME_WIDTH) -> str:
    """Truncate a filename for the page (the dashboard's width is
    smaller; the page has the room for more)."""
    if not name:
        return "—"
    return name if len(name) <= width else name[:width - 3] + "..."


def build_download_rows(db: Database, task_id: int | None = None) -> list[dict]:
    """One display row per Download, newest first (D4.3).

    The hidden ``task_id`` field carries the row's task for the filter
    options (the table's ``row_key`` is the row index, as on the
    dashboard)."""
    rows = []
    for d in reversed(db.list_downloads(task_id=task_id)):
        task = db.get_task(d["task_id"]) if d["task_id"] is not None else None
        rows.append({
            "id": d["id"],
            "task_id": d["task_id"],
            "task": (f"{task['service']} / {task['user'] or '—'}"
                     if task is not None else "—"),
            "run": d["run_id"] if d["run_id"] is not None else "—",
            "filename": _truncate(d["filename"]),
            "size": _size(d["size"]),
            "sha256": (d["sha256"][:12] + "…") if d["sha256"] else "—",
            "duplicate": (f"duplicate of #{d['duplicate_of_id']}"
                          if d["duplicate_of_id"] else "—"),
            "date": (d["created_at"] or "—")[:19],
        })
    return rows


def register_downloads(db: Database) -> None:
    """Register the downloads page (``/downloads``)."""

    @ui.page("/downloads")
    def downloads_page(request: Request) -> None:
        redirect = require_auth(request)
        if redirect is not None:
            return redirect
        build_layout(active="Downloads")

        rows = build_download_rows(db)
        options = {"All": None}
        for row in rows:
            if row["task_id"] is not None:
                options.setdefault(row["task"], row["task_id"])
        task_select = ui.select(options, value="All",
                                label="Task").mark("downloads-filter")
        table = ui.table(columns=COLUMNS, rows=rows).classes("w-full")
        table.add_slot("body", BODY)

        def on_filter(_e) -> None:
            value = task_select.value
            task_id = options.get(value) if value != "All" else None
            table.rows = build_download_rows(db, task_id=task_id)

        task_select.on_value_change(on_filter)
