"""NiceGUI app skeleton for the BillCollector daemon (M1 placeholder).

Serves the daemon HTTP endpoint with a placeholder index page and a
``/_alive`` health probe only. Authentication, task pages, and the
scheduler/orchestrator wiring land in later milestone chunks.
"""

import logging

from fastapi import Response
from nicegui import app as nicegui_app
from nicegui import ui

from ..db import Database

logger = logging.getLogger("billcollector.ui.app")


def start(host: str, port: int) -> None:
    """Build the placeholder index page and start the HTTP server (blocking).

    Lifecycle hooks are registered on the NiceGUI app object (NiceGUI 3.x
    API: ``app.on_startup`` / ``app.on_shutdown``) before ``ui.run``;
    ``show=False`` keeps the daemon from ever popping a browser window.
    """

    @nicegui_app.get("/_alive")
    def alive() -> Response:
        return Response("ok", media_type="text/plain")

    @ui.page("/", title="BillCollector")
    def index() -> None:
        ui.label("BillCollector daemon").classes("text-h4 font-bold")
        ui.label("M1 skeleton: daemon core only, no task pages yet.")
        db = Database()
        try:
            count = len(db.list_tasks())
        finally:
            db.close()
        ui.label(f"Tasks in database: {count}")

    def _on_startup() -> None:
        logger.info("serve ready on %s:%d", host, port)
        # scheduler + orchestrator startup (M1 item 4) lands in the next chunk

    def _on_shutdown() -> None:
        logger.info("serve shutting down")

    nicegui_app.on_startup(_on_startup)
    nicegui_app.on_shutdown(_on_shutdown)
    ui.run(host=host, port=port, title="BillCollector", show=False, reload=False)
