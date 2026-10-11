"""NiceGUI app for the BillCollector daemon (M1 chunk C7.5).

Serves the daemon HTTP endpoint and wires the daemon lifecycle: on
startup the orchestrator's orphan cleanup runs (leftover active runs
from a previous daemon lifetime are marked interrupted) and the
scheduler starts (one cron job per enabled task, rebuilt from the Task
table). On shutdown the scheduler stops first (so no new job can
dispatch while runners are being reaped; a job that just started is
harmlessly cancelled - the monitoring of its live runner is its own
task, C7.5), and then every live runner's process group is terminated
(the orchestrator marks their runs interrupted and releases their
tasks). Authentication and task pages land in M2.
"""

import logging

from fastapi import Response
from nicegui import app as nicegui_app
from nicegui import ui

from ..db import Database
from ..orchestrator import Orchestrator
from ..scheduler import TaskScheduler

logger = logging.getLogger("billcollector.ui.app")


def build_lifecycle(db: Database, orchestrator: Orchestrator,
                    scheduler: TaskScheduler):
    """The serve startup/shutdown hooks (C7.5).

    Startup: mark the runs a previous daemon lifetime left open as
    interrupted (orphan cleanup), then start the scheduler (jobs
    re-synced from the Task table). Shutdown: stop the scheduler first
    (no new job can dispatch while runners are being reaped; a job that
    just started is harmlessly cancelled - the monitoring of its live
    runner is its own task, C7.5), then terminate every live runner
    (the orchestrator marks their runs interrupted and releases their
    tasks). Returned as ``(startup, shutdown)``; shutdown is a
    coroutine (the runner termination awaits the children' exit).
    """

    def startup() -> None:
        interrupted = orchestrator.cleanup_orphans()
        scheduler.start()
        logger.info("serve started: scheduler running, "
                    "%d orphan run(s) interrupted", interrupted)

    async def shutdown() -> None:
        scheduler.stop()
        await orchestrator.shutdown()
        logger.info("serve stopped: scheduler stopped, runners terminated")

    return startup, shutdown


def start(host: str, port: int) -> None:
    """Build the app, wire the daemon lifecycle, and start the HTTP
    server (blocking).

    Lifecycle hooks are registered on the NiceGUI app object (NiceGUI 3.x
    API: ``app.on_startup`` / ``app.on_shutdown``) before ``ui.run``;
    ``show=False`` keeps the daemon from ever popping a browser window.
    """
    db = Database()
    orchestrator = Orchestrator(db)
    scheduler = TaskScheduler(db, orchestrator.start_run)
    startup, shutdown = build_lifecycle(db, orchestrator, scheduler)

    @nicegui_app.get("/_alive")
    def alive() -> Response:
        return Response("ok", media_type="text/plain")

    @ui.page("/", title="BillCollector")
    def index() -> None:
        ui.label("BillCollector daemon").classes("text-h4 font-bold")
        ui.label("M1 skeleton: daemon core only, no task pages yet.")
        ui.label(f"Tasks in database: {len(db.list_tasks())}")

    nicegui_app.on_startup(startup)
    nicegui_app.on_shutdown(shutdown)
    ui.run(host=host, port=port, title="BillCollector", show=False, reload=False)
