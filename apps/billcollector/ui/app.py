# -*- coding: utf-8 -*-
"""NiceGUI app for the BillCollector daemon (M1 chunk C7.5, M2 chunk D1).

Serves the daemon HTTP endpoint and wires the daemon lifecycle: on
startup the orchestrator's orphan cleanup runs (leftover active runs
from a previous daemon lifetime are marked interrupted) and the
scheduler starts (one cron job per enabled task, rebuilt from the Task
table). On shutdown the scheduler stops first (so no new job can
dispatch while runners are being reaped; a job that just started is
harmlessly cancelled - the monitoring of its live runner is its own
task, C7.5), and then every live runner's process group is terminated
(the orchestrator marks their runs interrupted and releases their
tasks).

M2 D1: session-cookie authentication (``ui.auth``) with the ``/login``
page (set-password on first start, then login); every non-public path
redirects to ``/login`` until the session carries ``authenticated``.
M2 D2: the dashboard (``/``: task table with filters and the waiting
badge, the live log pane, the ``/runs/<run_id>`` deep-link route) and
the task detail page (``/tasks/<task_id>``, full page since D4) are
wired in here. M2 D4: ``config.RUN_DIR`` is exposed as the ``runfiles``
 static directory (``/runfiles/<run_id>/…``; locked decision 10 keeps it
   distinct from the ``/runs/<run_id>`` deep-link route) and the downloads
   page (``/downloads``) is registered. M2 D5: the per-service recipe
   editor (``/recipes/<service>``) is registered. M2 D6: the settings
   page (``/settings``, the Settings-table fields of locked decision 12)
   is registered. M3 S1.1: the session page (``/runs/<run_id>``, the ntfy
   deep-link target; M3 decision 2) replaces the M2 dashboard redirect.
"""

import logging

from fastapi import Response
from nicegui import app as nicegui_app
from nicegui import core as _nicegui_core
from nicegui import ui

from ..db import Database
from ..orchestrator import Orchestrator
from ..scheduler import TaskScheduler
from .auth import register_auth
from .dashboard import register_dashboard
from .downloads import register_downloads
from .login import register_login_page
from .recipes import register_recipe_editor
from .runfiles import register_runfiles
from .session import register_session
from .settings import register_settings
from .task_detail import register_task_detail

logger = logging.getLogger("billcollector.ui.app")

# --- Slot-template DOM globals (Vue 3 runtime-compiler workaround) ------------
#
# NiceGUI slot templates (the dashboard ROW_BODY and the task-detail
# STEP_BODY) are compiled on the client by Vue's *runtime* compiler, which
# wraps the generated render code in a ``with (_ctx)`` scope. For
# runtime-compiled components, Vue's instance proxy answers that scope's
# ``has`` probe affirmatively for every identifier that is not in a small
# built-in allow-list (Math, JSON, Date, ...) and its ``get`` probe then
# returns ``undefined`` instead of falling through to the browser globals.
# ``new CustomEvent(...)`` in a slot template's inline ``@click`` handler
# therefore throws ``TypeError: CustomEvent is not a constructor`` before
# the event is ever dispatched: the dashboard row-action buttons (Run now /
# Stop / Edit) and the task-detail screenshot click silently do nothing,
# and no event reaches the server. The proxy's ``get`` does consult
# ``app.config.globalProperties`` - Vue's documented escape hatch for
# exactly this situation - so expose the ``CustomEvent`` constructor there.
# NiceGUI injects ``vue_config_script`` into every page's module script
# before ``app.mount`` (where ``app`` is the Vue app in scope), so the
# binding is in place before the first render. Add further browser globals
# (e.g. ``window``) here if a future slot template needs them.
nicegui_app.config.vue_config_script += (
    "\napp.config.globalProperties.CustomEvent = CustomEvent;\n"
)

# --- Socket.IO client-disconnect tolerance (python-engineio bug) -------------
#
# The engineio ASGI driver (``engineio/async_drivers/asgi.py``,
# ``translate_request``) returns an *empty* environ when the first ASGI
# event is neither ``http.request`` nor ``websocket.connect`` - i.e. when
# the client went away before its request was delivered (an aborted
# preconnect, a reload that kills an in-flight poll, a WSL2
# localhost-forward drop; uvicorn's ``receive`` then yields
# ``http.disconnect`` first). Its only caller (``engineio/async_server.py``,
# ``AsyncServer.handle_request``) then indexes
# ``environ['REQUEST_METHOD']`` unconditionally: the unhandled ``KeyError``
# unwinds through the whole middleware stack (including the auth
# BaseHTTPMiddleware) and is logged as a 500 "Exception in ASGI
# application" although no client is left to answer. python-engineio 4.14.0
# (latest) still ships this, so the workaround is a wrapper, not a pin.
#
# The wrapper must *send a response* on that path: the mount sits below
# BaseHTTPMiddleware layers, whose ``call_next`` turns "the wrapped app
# sent nothing" into ``RuntimeError("No response returned.")`` - swapping
# one traceback for an equally noisy one. 499 (client closed request) is
# the honest status; uvicorn drops writes to an already-closed transport,
# so nothing reaches the wire.
_sio = _nicegui_core.sio
if not getattr(_sio, "_billcollector_disconnect_tolerant", False):
    _orig_handle_request = _sio.handle_request

    async def _tolerant_handle_request(*args, **kwargs):
        try:
            return await _orig_handle_request(*args, **kwargs)
        except KeyError as exc:
            if exc.args != ("REQUEST_METHOD",) or len(args) < 3 \
                    or not isinstance(args[0], dict):
                raise
            scope, send = args[0], args[2]
            if scope.get("type") == "http":
                await send({"type": "http.response.start", "status": 499,
                            "headers": []})
                await send({"type": "http.response.body", "body": b""})
            elif scope.get("type") == "websocket":
                await send({"type": "websocket.close", "code": 1000})
            else:
                raise

    _sio.handle_request = _tolerant_handle_request
    _sio._billcollector_disconnect_tolerant = True


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


def build_app(db: Database, orchestrator: Orchestrator,
              scheduler: TaskScheduler) -> None:
    """Register all routes and the auth middleware on the shared app object.

    Factored out of :func:`start` so the UI tests can build the exact
    production wiring against a scratch DB without starting a server.
    """

    @nicegui_app.get("/_alive")
    def alive() -> Response:
        return Response("ok", media_type="text/plain")

    register_auth(nicegui_app, db)
    register_login_page(db)
    register_dashboard(db, orchestrator, scheduler)
    register_task_detail(db, orchestrator)
    register_session(db)
    register_recipe_editor(db, orchestrator)
    register_downloads(db)
    register_settings(db)
    register_runfiles(nicegui_app)


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
    build_app(db, orchestrator, scheduler)

    nicegui_app.on_startup(startup)
    nicegui_app.on_shutdown(shutdown)
    ui.run(host=host, port=port, title="BillCollector", show=False, reload=False)
