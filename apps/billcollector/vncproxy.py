# -*- coding: utf-8 -*-
"""The noVNC live-view proxy (C6: the noVNC access path).

The per-run live view is served on the UI port behind the existing UI
session - no noVNC ports are published:

- ``GET /vnc/<port>/`` and ``GET /vnc/<port>/<path>`` serve the noVNC
  web client from ``NOVNC_WEB_DIR`` (apt novnc), path-mapped with a
  traversal guard. These are non-public paths, so the auth middleware
  (``ui/auth.py``) 307s unauthenticated requests to ``/login`` - no
  client file is ever served without a session.
- ``WS /vnc/<port>/websockify`` tunnels the RFB WebSocket to the
  run's loopback-bound websockify. The auth middleware does not cover
  websocket scopes, so the route checks the session itself (the
  SessionMiddleware decodes the cookie into ``scope["session"]`` for
  websocket scopes as well) and rejects the upgrade before the
  handshake when the session is missing or invalid.

The port must be inside the configured display range (websockify port
= ``WEBSOCKIFY_BASE_PORT`` + index within the range) **and** the
``novnc_port`` of a live Run row (``result IS NULL``) - otherwise 404.
The display stack is runner-owned and reaped with the run, so a dead
port would fail to connect anyway; the row check keeps the surface
explicit and stops in-container port probing.
"""

import asyncio
import logging
from pathlib import Path

from fastapi import WebSocket
from starlette.responses import FileResponse, PlainTextResponse

from . import display
from .db import Database

logger = logging.getLogger("billcollector.vncproxy")

# The noVNC web client directory (module level so the tests can
# monkeypatch it to a fixture tree).
NOVNC_WEB_DIR = display.NOVNC_WEB_DIR


def _port_allowed(db: Database, port: int) -> bool:
    """Whether ``port`` may be proxied: inside the websockify range of
    the configured display range and the ``novnc_port`` of a live Run
    row (see the module docstring)."""
    start, count = display.display_range(db)
    if not (display.WEBSOCKIFY_BASE_PORT <= port
            < display.WEBSOCKIFY_BASE_PORT + count):
        return False
    return db.has_live_novnc_port(port)


def _client_file(path: str) -> Path | None:
    """The noVNC client file for ``/vnc/<port>/<path>`` (or None): the
    path is resolved inside ``NOVNC_WEB_DIR`` - a resolved target that
    escapes the client dir (``..``) or is not an existing file is a
    404."""
    base = NOVNC_WEB_DIR
    target = (base / path).resolve()
    if not target.is_file() or not target.is_relative_to(base.resolve()):
        return None
    return target


def _serve_client_file(db: Database, port: int, path: str):
    """One ``/vnc/<port>/…`` response: 404 when the port is not
    allowed or the file is not in the client dir, the file otherwise
    (media type guessed from the extension)."""
    if not _port_allowed(db, port):
        return PlainTextResponse("Not found", status_code=404)
    target = _client_file(path)
    if target is None:
        return PlainTextResponse("Not found", status_code=404)
    return FileResponse(target)


async def _tunnel(websocket: WebSocket, upstream) -> None:
    """Pump frames between the client WebSocket and the upstream
    websockify connection until either side closes, then close both.

    Two pump tasks run until one finishes (the client went away or the
    upstream closed); the other is cancelled, the upstream connection
    is closed, and the client WebSocket is closed (a no-op when the
    client already went away)."""

    async def client_to_upstream() -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("bytes") is not None:
                await upstream.send(message["bytes"])
            elif message.get("text") is not None:
                await upstream.send(message["text"])

    async def upstream_to_client() -> None:
        async for frame in upstream:
            if isinstance(frame, (bytes, bytearray, memoryview)):
                await websocket.send_bytes(bytes(frame))
            else:
                await websocket.send_text(str(frame))

    to_upstream = asyncio.create_task(client_to_upstream())
    to_client = asyncio.create_task(upstream_to_client())
    try:
        await asyncio.wait((to_upstream, to_client),
                           return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (to_upstream, to_client):
            task.cancel()
        await upstream.close()
    await websocket.close()


def register_vnc_proxy(app, db: Database) -> None:
    """Register the noVNC proxy routes on the app (called from
    ``ui/app.py::build_app``).

    The routes are distinct from the Socket.IO mount (``/socket.io``);
    the engineio disconnect-tolerant wrapper in ``ui/app.py`` is
    unaffected.
    """
    from websockets.asyncio.client import connect as ws_connect

    @app.get("/vnc/{port}/")
    def vnc_index(port: int):
        return _serve_client_file(db, port, "vnc.html")

    @app.get("/vnc/{port}/{path:path}")
    def vnc_asset(port: int, path: str):
        return _serve_client_file(db, port, path)

    @app.websocket("/vnc/{port}/websockify")
    async def websockify_tunnel(websocket: WebSocket, port: int) -> None:
        # The auth middleware does not cover websocket scopes: check
        # the session here (the SessionMiddleware decoded the cookie
        # into scope["session"]) and reject before the handshake when
        # it is missing or invalid.
        session = websocket.scope.get("session")
        if not (session or {}).get("authenticated"):
            await websocket.close(code=1008)
            return
        if not _port_allowed(db, port):
            await websocket.close(code=1008)
            return
        try:
            async with ws_connect(f"ws://127.0.0.1:{port}/websockify",
                                  max_size=None) as upstream:
                await websocket.accept()
                await _tunnel(websocket, upstream)
        except OSError:
            # The upstream websockify is unreachable (the display stack
            # died between the row check and the connect): the
            # handshake was not accepted, so the client sees a 403.
            logger.warning("vncproxy: websockify upstream :%d unreachable", port)
            await websocket.close(code=1011)
        except Exception:
            logger.exception("vncproxy: tunnel for :%d failed", port)
            try:
                await websocket.close(code=1011)
            except Exception:
                pass
