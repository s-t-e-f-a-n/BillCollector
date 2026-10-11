# -*- coding: utf-8 -*-
"""Task detail page placeholder (M2 chunk D2).

The full page (run history, step results + screenshots, task downloads,
pause section, live log, reset profile) lands in D4 and replaces this
placeholder; it exists from D2 so the dashboard's row-click navigation
works from the start.
"""

from fastapi import Request
from nicegui import ui

from ..db import Database
from .auth import require_auth
from .layout import build_layout


def register_task_detail(db: Database) -> None:
    """Register the task detail page (``/tasks/<task_id>``)."""

    @ui.page("/tasks/{task_id}")
    def task_detail_page(request: Request, task_id: int) -> None:
        redirect = require_auth(request)
        if redirect is not None:
            return redirect
        build_layout()
        task = db.get_task(task_id)
        if task is None:
            ui.label(f"Unknown task id: {task_id} (404)").classes("text-red-600")
            return
        ui.label(f"Task {task['id']}: {task['service']} / "
                 f"{task['user'] or '—'}").classes("text-h4 font-bold")
        ui.label(f"Status: {task['status']} · Enabled: "
                 f"{'yes' if task['enabled'] else 'no'}")
        ui.label("The full task detail page (history, steps, screenshots, "
                 "downloads, live log) lands in D4.")
