# -*- coding: utf-8 -*-
"""Downloads page (M2 chunk D4.3).

``/downloads`` lists every Download row (task service/user, run,
filename, size, truncated sha256, the duplicate_of badge, the exposed
delivery state, date), newest first, with an optional task filter. The
per-row **Retry delivery** action (issue #24 C8) confirms, then routes
to the orchestrator's retry subprocess. The row builder, the body slot,
and the retry dialog are shared with the task detail page's downloads
section (D4.1), so both views render the same columns and action.
"""

from fastapi import Request
from nicegui import ui

from ..db import Database
from ..orchestrator import Orchestrator
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
    {"name": "delivery", "label": "Delivery", "field": "delivery"},
    {"name": "date", "label": "Date", "field": "date"},
    {"name": "actions", "label": "Actions", "field": "actions"},
]

# A deduplicated download is rendered as an outlined badge (a plain
# string cell cannot carry one): the slot draws the ``duplicate`` cell
# as a ``q-badge`` whenever it is not ``—`` (the same slot pattern as
# the dashboard's body). The per-row **Retry delivery** button (issue
# #24 C8) appears only on retryable rows; as on the dashboard, the slot
# template is not a NiceGUI element, so the button dispatches a
# bubbling DOM ``dlretry`` CustomEvent (``detail`` = the payload) that
# the owning page binds on the table root with the same bare-``detail``
# js_handler, and ``.stop`` keeps the click from reaching the row.
BODY = """
<q-tr :props="props">
  <q-td v-for="col in props.cols" :key="col.name">
    <q-badge v-if="col.name === 'duplicate' && props.row[col.name] !== '—'"
             color="orange" outline>{{ props.row[col.name] }}</q-badge>
    <span v-else-if="col.name === 'actions'">
      <q-btn v-if="props.row.retryable" size="sm" label="Retry delivery"
             @click.stop="$event.currentTarget.dispatchEvent(new CustomEvent('dlretry', {detail: {id: props.row.id, task: props.row.task}, bubbles: true}))"/>
    </span>
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


def _delivery_label(state, attempts) -> str:
    """The exposed delivery state (issue #24 C8): the four internal
    states mapped to the operator-facing labels, ``failed delivery (N)``
    carrying the attempt count (``—`` when it was never attempted), and
    ``—`` for an unknown state."""
    if state == "staged":
        return "downloaded"
    if state == "published":
        return "pending delivery"
    if state == "consumed":
        return "delivered"
    if state == "failed":
        return f"failed delivery ({'—' if attempts is None else attempts})"
    return "—"


def build_download_rows(db: Database, task_id: int | None = None) -> list[dict]:
    """One display row per Download, newest first (D4.3).

    The hidden ``task_id`` field carries the row's task for the filter
    options (the table's ``row_key`` is the row index, as on the
    dashboard). The hidden ``retryable`` field drives the per-row Retry
    delivery button (issue #24 C8): every non-``consumed``,
    non-duplicate row."""
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
            "delivery": _delivery_label(d["state"], d["delivery_attempts"]),
            "date": (d["created_at"] or "—")[:19],
            "retryable": d["state"] != "consumed" and not d["duplicate_of_id"],
        })
    return rows


def open_download_retry(download_id: int, orchestrator: Orchestrator,
                        refresh) -> None:
    """The delivery-retry confirmation dialog (issue #24 C8), shared by
    the downloads page and the task detail page.

    Delivery is at-least-once (the consumer's idempotency key is the
    task plus the document's sha256), so the dialog states that the
    consumer may receive the document again. On confirm the
    orchestrator's retry subprocess runs (consumers stay out of the UI
    process); the outcome is notified and the rows rebuilt."""
    with ui.dialog() as confirm, ui.card().classes("w-96"):
        confirm.open()
        ui.label("Retry the delivery?").classes("text-h6")
        ui.label("Delivery is at-least-once and keyed on the task and the "
                 "document's sha256: the consumer may receive the "
                 "document again.")
        with ui.row().classes("w-full justify-end items-center gap-2"):
            ui.button("Cancel", on_click=confirm.close).props("flat")
            ok_btn = ui.button("Retry").mark("downloads-retry-confirm") \
                .props("color=primary")

    async def on_confirm(_e) -> None:
        ok, error = await orchestrator.retry_delivery(download_id)
        if ok:
            ui.notify(f"Delivery retried for download #{download_id}")
        else:
            ui.notify(error or "Manual delivery retry failed", type="warning")
        confirm.close()
        refresh()

    ok_btn.on("click", on_confirm)


def register_downloads(db: Database, orchestrator: Orchestrator) -> None:
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

        def refresh() -> None:
            """Rebuild the rows for the current filter (also after a
            delivery retry changed a row's state)."""
            value = task_select.value
            task_id = options.get(value) if value != "All" else None
            table.rows = build_download_rows(db, task_id=task_id)

        task_select.on_value_change(refresh)

        def on_dl_retry(e) -> None:
            """Per-row Retry delivery (issue #24 C8): the confirmation
            dialog, then the orchestrator's retry subprocess."""
            detail = e.args if isinstance(e.args, dict) else {}
            download_id = detail.get("id")
            if download_id is None:
                return
            open_download_retry(download_id, orchestrator, refresh)

        # The js_handler emits the CustomEvent's bare ``detail`` payload
        # (the dashboard's rowaction contract; the User simulation's
        # ``trigger("dlretry", ...)`` delivers the same bare payload).
        table.on("dlretry", on_dl_retry,
                 js_handler="(event) => emit(event.detail)")
