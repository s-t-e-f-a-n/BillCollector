# -*- coding: utf-8 -*-
"""Unit tests for the serve lifecycle hooks (M1 chunk C7.5).

``build_lifecycle`` returns the startup/shutdown hooks ``serve``
registers: on startup the orchestrator's orphan cleanup runs before the
scheduler starts, and on shutdown the scheduler stops before the
orchestrator terminates the live runners (see the orchestrator/scheduler
module docstrings for why the shutdown order matters)."""

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

import socketio  # noqa: E402
from nicegui import core as nicegui_core  # noqa: E402

from billcollector.ui import app as ui_app  # noqa: E402


def _disconnect_first_receive(event_type):
    """A ``receive`` whose first (and only) event is a client disconnect -
    what uvicorn yields when the client went away before the app read its
    request (see the workaround in ``billcollector/ui/app.py``)."""

    async def receive():
        return {"type": event_type}

    return receive


def _collecting_send(events):
    """A ``send`` that records every ASGI event instead of writing it."""

    async def send(message):
        events.append(message)

    return send


def _socketio_http_scope():
    return {"type": "http", "method": "GET", "path": "/socket.io/",
            "raw_path": b"/socket.io/", "query_string":
            b"EIO=4&transport=polling", "headers": [], "root_path": "",
            "client": ("127.0.0.1", 12345), "server": ("127.0.0.1", 8000),
            "scheme": "http", "http_version": "1.1",
            "asgi": {"version": "3.0"}}


class SocketIoDisconnectToleranceTests(unittest.IsolatedAsyncioTestCase):
    """A client that disconnects before its socket.io request is delivered
    used to unwind the whole middleware stack with an unhandled
    ``KeyError('REQUEST_METHOD')`` from engineio's ASGI driver (logged as
    a 500 "Exception in ASGI application"). The wrapper in
    ``billcollector/ui/app.py`` answers 499 instead."""

    async def test_unpatched_engineio_raises_on_the_disconnect_scope(self):
        """Sanity: this input really is the upstream crash trigger (so the
        wrapper is not masking nothing; when engineio fixes it, remove the
        wrapper and this test)."""
        server = socketio.AsyncServer(async_mode="asgi",
                                      start_service_task=False)
        with self.assertRaises(KeyError) as ctx:
            await server.handle_request(
                _socketio_http_scope(),
                _disconnect_first_receive("http.disconnect"),
                _collecting_send([]))
        self.assertEqual(ctx.exception.args, ("REQUEST_METHOD",))

    async def test_patched_sio_answers_499_instead_of_raising(self):
        events = []
        await nicegui_core.sio.handle_request(
            _socketio_http_scope(),
            _disconnect_first_receive("http.disconnect"),
            _collecting_send(events))
        self.assertEqual(
            events,
            [{"type": "http.response.start", "status": 499, "headers": []},
             {"type": "http.response.body", "body": b""}])

    async def test_patched_sio_closes_a_disconnected_websocket(self):
        events = []
        scope = dict(_socketio_http_scope())
        scope["type"] = "websocket"
        await nicegui_core.sio.handle_request(
            scope,
            _disconnect_first_receive("websocket.disconnect"),
            _collecting_send(events))
        self.assertEqual(events, [{"type": "websocket.close", "code": 1000}])

    async def test_mounted_stack_answers_499_without_a_traceback(self):
        """The full production stack (auth/session BaseHTTPMiddleware
        layers + routing + the /_nicegui_ws/ mount) tolerates the
        disconnect: no exception escapes and a response is sent (the
        middleware layers would otherwise raise "No response returned")."""
        events = []
        scope = dict(_socketio_http_scope())
        scope["path"] = "/_nicegui_ws/socket.io/"
        scope["raw_path"] = b"/_nicegui_ws/socket.io/"
        await nicegui_core.app(scope,
                               _disconnect_first_receive("http.disconnect"),
                               _collecting_send(events))
        self.assertTrue(events)
        self.assertEqual(events[0]["type"], "http.response.start")
        self.assertEqual(events[0]["status"], 499)


class BuildLifecycleTests(unittest.TestCase):
    def test_startup_runs_the_orphan_cleanup_before_the_scheduler_starts(self):
        calls = []

        class FakeOrchestrator:
            def cleanup_orphans(self):
                calls.append("cleanup")
                return 0

        class FakeScheduler:
            def start(self):
                calls.append("scheduler_start")

        startup, _ = ui_app.build_lifecycle(None, FakeOrchestrator(),
                                            FakeScheduler())
        startup()
        self.assertEqual(calls, ["cleanup", "scheduler_start"])

    def test_shutdown_stops_the_scheduler_before_terminating_the_runners(self):
        calls = []

        class FakeOrchestrator:
            async def shutdown(self):
                calls.append("orchestrator_shutdown")

        class FakeScheduler:
            def stop(self):
                calls.append("scheduler_stop")

        _, shutdown = ui_app.build_lifecycle(None, FakeOrchestrator(),
                                             FakeScheduler())
        asyncio.run(shutdown())
        self.assertEqual(calls, ["scheduler_stop", "orchestrator_shutdown"])


if __name__ == "__main__":
    unittest.main()
