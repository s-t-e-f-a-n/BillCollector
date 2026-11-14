# -*- coding: utf-8 -*-
"""Tests for the noVNC live-view proxy (C6: the noVNC access path).

The per-run live view is served on the UI port behind the existing UI
session - no noVNC port is published. ``vncproxy`` exposes three routes:
``GET /vnc/<port>/``, ``GET /vnc/<port>/<path>`` (the noVNC web client,
served from ``NOVNC_WEB_DIR`` with a traversal guard) and
``WS /vnc/<port>/websockify`` (the RFB tunnel to the run's loopback-bound
websockify). The port must be inside the configured websockify range **and**
the ``novnc_port`` of a live Run row (``result IS NULL``), else 404.

The HTTP routes are non-public paths, so the auth middleware (``ui/auth.py``)
307s an unauthenticated request to ``/login`` before any client file is
served. The auth middleware does not cover websocket scopes (a
``BaseHTTPMiddleware`` passes them through), so the tunnel route checks the
session itself - the ``SessionMiddleware`` decodes the cookie into
``scope["session"]`` for websocket scopes too - and rejects the upgrade
before the handshake when the session is missing or the port is disallowed.

HTTP tests run against the production wiring (the ``user`` fixture builds the
exact app via ``tests/ui_test_main.py``); the websocket tests drive an
isolated ``FastAPI`` app with the ``SessionMiddleware`` + the proxy route, so
the tunnel and its session gate are exercised without a NiceGUI server.
"""

import asyncio
import base64
import json
import os
import socket
import sys
import time
from pathlib import Path

import pytest
import websockets
from fastapi import FastAPI
from itsdangerous import TimestampSigner
from starlette.middleware.sessions import SessionMiddleware
from websockets.asyncio.server import serve as ws_serve

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import vncproxy  # noqa: E402
from billcollector.db import Database  # noqa: E402
from billcollector.ui.auth import get_session_secret  # noqa: E402


# ---- shared helpers ---------------------------------------------------------

def _session_cookie(secret: str) -> str:
    """The ``SessionMiddleware`` cookie for an authenticated session: the
    starlette middleware signs ``b64(json(session))`` with the persisted
    session secret (see ``ui/auth.py``), so the token must match that
    encoding exactly for the middleware to decode it."""
    data = base64.b64encode(
        json.dumps({"authenticated": True}).encode("utf-8"))
    return TimestampSigner(secret).sign(data).decode("utf-8")


def _seed_live_run(db: Database, port: int) -> int:
    """A live Run row (``result IS NULL``) whose ``novnc_port`` is ``port``
    - the row check the proxy's allowlist keys on."""
    task = db.create_task(f"svc-vnc-{port}", "user1", enabled=False)
    return db.create_run(task, novnc_port=port)


def _free_port_in_window(start=6080, stop=6120) -> int:
    """A bindable port inside the websockify window the proxy dials: the
    tunnel connects to ``127.0.0.1:<port>``, so the test's upstream must
    listen on a real, free port in that range."""
    for port in range(start, stop):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
        finally:
            probe.close()
    raise AssertionError("no free port in the websockify window")


# ---- HTTP: the session gate on the client-file routes ----------------------

@pytest.fixture
def testdb():
    """A direct connection to the same DB file the main file created (the
    ``user`` fixture runs ``tests/ui_test_main.py``, which publishes its DB
    path in ``BC_UI_TEST_DB``)."""
    db = Database(path=os.environ["BC_UI_TEST_DB"])
    yield db
    db.close()


async def test_unauthenticated_request_is_redirected_to_login(user, testdb):
    """A non-public path with no session: the auth middleware 307s to
    /login before any client file is served (no noVNC file leaks without a
    session)."""
    response = await user.http_client.get("/vnc/6080/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/login"


async def test_authenticated_request_serves_the_client_files(user, testdb,
                                                             tmp_path, monkeypatch):
    """With a session and an allowed port (in range + a live Run), the
    client files are served from the noVNC web dir (the index and a nested
    asset, media type inferred from the extension)."""
    web = tmp_path / "novnc"
    (web / "core").mkdir(parents=True)
    (web / "vnc.html").write_text("<html>vnc client</html>", encoding="utf-8")
    (web / "core" / "nocu.js").write_text("console.log('vnc')", encoding="utf-8")
    monkeypatch.setattr(vncproxy, "NOVNC_WEB_DIR", web)
    _seed_live_run(testdb, 6080)

    headers = {"cookie": "session=" + _session_cookie(get_session_secret(testdb))}
    index = await user.http_client.get("/vnc/6080/", headers=headers)
    assert index.status_code == 200
    assert "vnc client" in index.text
    assert index.headers["content-type"].startswith("text/html")

    asset = await user.http_client.get("/vnc/6080/core/nocu.js", headers=headers)
    assert asset.status_code == 200
    assert "console.log" in asset.text


async def test_in_range_port_without_a_live_run_is_a_404(user, testdb):
    """6081 is inside the default range but no live Run owns it: 404, even
    with a session (the row check keeps the surface explicit and stops
    in-container port probing)."""
    headers = {"cookie": "session=" + _session_cookie(get_session_secret(testdb))}
    response = await user.http_client.get("/vnc/6081/", headers=headers)
    assert response.status_code == 404


async def test_port_outside_the_range_is_a_404(user, testdb):
    """A port outside the websockify range is rejected even when a live Run
    claims it (the range check runs first)."""
    _seed_live_run(testdb, 9999)
    headers = {"cookie": "session=" + _session_cookie(get_session_secret(testdb))}
    response = await user.http_client.get("/vnc/9999/", headers=headers)
    assert response.status_code == 404


async def test_missing_client_file_is_a_404(user, testdb, tmp_path, monkeypatch):
    """An allowed port that names a file not present in the client dir is a
    404 (no path falls through to the filesystem)."""
    web = tmp_path / "novnc"
    web.mkdir()
    (web / "vnc.html").write_text("<html>vnc</html>", encoding="utf-8")
    monkeypatch.setattr(vncproxy, "NOVNC_WEB_DIR", web)
    _seed_live_run(testdb, 6080)

    headers = {"cookie": "session=" + _session_cookie(get_session_secret(testdb))}
    response = await user.http_client.get("/vnc/6080/does_not_exist.js",
                                          headers=headers)
    assert response.status_code == 404


async def test_traversal_via_the_route_is_rejected(user, testdb, tmp_path,
                                                   monkeypatch):
    """A percent-encoded ``..`` that would escape the client dir (the
    realistic browser vector) is a 404 and never leaks the file behind it."""
    web = tmp_path / "novnc"
    web.mkdir()
    (web / "vnc.html").write_text("<html>vnc</html>", encoding="utf-8")
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET DATA", encoding="utf-8")
    monkeypatch.setattr(vncproxy, "NOVNC_WEB_DIR", web)
    _seed_live_run(testdb, 6080)

    headers = {"cookie": "session=" + _session_cookie(get_session_secret(testdb))}
    response = await user.http_client.get("/vnc/6080/%2e%2e/secret.txt",
                                          headers=headers)
    assert response.status_code == 404
    assert "TOP SECRET" not in response.text


# ---- traversal guard (the pure path resolver, unit) ------------------------

def test_client_file_rejects_traversal_and_missing(tmp_path, monkeypatch):
    """``_client_file`` resolves the path inside the client dir: a normal
    file resolves, a path that escapes the dir (``..``) or a missing file
    is rejected (None)."""
    web = tmp_path / "novnc"
    (web / "core").mkdir(parents=True)
    (web / "vnc.html").write_text("vnc", encoding="utf-8")
    (web / "core" / "nocu.js").write_text("js", encoding="utf-8")
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET", encoding="utf-8")
    monkeypatch.setattr(vncproxy, "NOVNC_WEB_DIR", web)

    assert vncproxy._client_file("vnc.html") == web / "vnc.html"
    assert vncproxy._client_file("core/nocu.js") == web / "core/nocu.js"
    # a resolved target that escapes the client dir is rejected
    assert vncproxy._client_file("../secret.txt") is None
    assert vncproxy._client_file("core/../../secret.txt") is None
    assert vncproxy._client_file("vnc.html/../../../secret.txt") is None
    # a missing file is rejected
    assert vncproxy._client_file("nope.js") is None


# ---- websocket: the session-gated tunnel -----------------------------------

@pytest.fixture
def ws_db(tmp_path):
    """A scratch DB for the isolated websocket tests (independent of the
    UI-simulation main file)."""
    db = Database(path=str(tmp_path / "vnc-proxy.db"))
    yield db
    db.close()


@pytest.fixture
def ws_app(ws_db):
    """An isolated app carrying the proxy route and the ``SessionMiddleware``
    (the only middleware the tunnel depends on - the auth middleware passes
    websocket scopes through)."""
    app = FastAPI()
    vncproxy.register_vnc_proxy(app, ws_db)
    app.add_middleware(SessionMiddleware, secret_key=get_session_secret(ws_db))
    return app


def _ws_scope(port: int, cookie: str | None = None) -> dict:
    """A raw ASGI websocket scope for ``/vnc/<port>/websockify`` (with the
    session cookie when given) - the shape the server transport provides."""
    headers = [(b"host", b"test")]
    if cookie is not None:
        headers.append((b"cookie", ("session=" + cookie).encode("utf-8")))
    path = f"/vnc/{port}/websockify"
    return {
        "type": "websocket",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "ws",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 54321),
        "server": ("test", 80),
    }


async def _drive_websocket(app, scope):
    """Drive one websocket request through the ASGI app and return
    ``(sent, receive_queue, task)``: the caller feeds client frames into the
    queue and inspects the ASGI send events in ``sent``. The initial
    ``websocket.connect`` (which ``WebSocket.accept`` consumes) is pre-queued."""
    receive_queue: asyncio.Queue = asyncio.Queue()
    receive_queue.put_nowait({"type": "websocket.connect"})
    sent = []

    async def receive():
        return await receive_queue.get()

    async def send(message):
        sent.append(message)

    task = asyncio.create_task(app(scope, receive, send))
    return sent, receive_queue, task


async def _wait_for(sent, predicate, message: str, timeout: float = 5.0):
    """Poll ``sent`` until ``predicate(sent)`` holds (the tunnel and the
    upstream run as concurrent tasks on the loop)."""
    deadline = time.monotonic() + timeout
    while not predicate(sent):
        if time.monotonic() >= deadline:
            raise AssertionError(message)
        await asyncio.sleep(0.01)


def _cancel_task(task) -> None:
    task.cancel()


async def test_unauthenticated_websocket_upgrade_is_rejected(ws_app, ws_db):
    """No session: the upgrade is rejected before the handshake (1008, no
    accept) - the RFB tunnel is never opened without a UI session."""
    port = _free_port_in_window()
    sent, _q, task = await _drive_websocket(ws_app, _ws_scope(port))
    try:
        await _wait_for(sent, lambda s: any(m["type"] == "websocket.close"
                                            for m in s),
                        "the unauthenticated upgrade was not closed")
        (close,) = [m for m in sent if m["type"] == "websocket.close"]
        assert close.get("code") == 1008
        assert not any(m["type"] == "websocket.accept" for m in sent)
    finally:
        _cancel_task(task)


async def test_websocket_upgrade_with_a_disallowed_port_is_rejected(ws_app, ws_db):
    """A session but a port with no live Run: rejected before the handshake
    (1008, no accept) - the tunnel is not opened for an unallocated port."""
    port = _free_port_in_window()
    cookie = _session_cookie(get_session_secret(ws_db))
    sent, _q, task = await _drive_websocket(ws_app, _ws_scope(port, cookie))
    try:
        await _wait_for(sent, lambda s: any(m["type"] == "websocket.close"
                                            for m in s),
                        "the disallowed-port upgrade was not closed")
        (close,) = [m for m in sent if m["type"] == "websocket.close"]
        assert close.get("code") == 1008
        assert not any(m["type"] == "websocket.accept" for m in sent)
    finally:
        _cancel_task(task)


async def test_authenticated_websocket_tunnels_both_ways(ws_app, ws_db):
    """With a session and an allowed port (in range + a live Run), the
    tunnel accepts and pumps frames both ways: a client frame is relayed to
    the upstream websockify, the upstream reply is relayed back, and a
    client disconnect closes the tunnel."""
    port = _free_port_in_window()
    ws_db.set_setting("display_count", str(port - 6080 + 1))
    _seed_live_run(ws_db, port)
    received = []

    async def handler(ws):
        try:
            while True:
                msg = await ws.recv()
                received.append(msg)
                await ws.send(msg if isinstance(msg, (bytes, bytearray))
                              else str(msg).encode("utf-8"))
        except websockets.exceptions.ConnectionClosed:
            pass

    cookie = _session_cookie(get_session_secret(ws_db))
    async with ws_serve(handler, "127.0.0.1", port):
        sent, q, task = await _drive_websocket(ws_app, _ws_scope(port, cookie))
        try:
            await _wait_for(sent, lambda s: any(m["type"] == "websocket.accept"
                                                for m in s),
                            "the authenticated upgrade was not accepted")
            await q.put({"type": "websocket.receive", "bytes": b"rfb-003"})
            await _wait_for(sent, lambda s: any(
                m["type"] == "websocket.send" and m.get("bytes") == b"rfb-003"
                for m in s), "the upstream echo was not relayed to the client")
            await q.put({"type": "websocket.disconnect", "code": 1000})
            await _wait_for(sent, lambda s: any(m["type"] == "websocket.close"
                                                for m in s),
                            "the tunnel did not close on client disconnect")
            assert b"rfb-003" in received
        finally:
            _cancel_task(task)


async def test_upstream_close_closes_the_client_websocket(ws_app, ws_db):
    """When the upstream websockify closes (the display stack died), the
    last upstream frame is relayed and the client websocket is closed - the
    operator sees the screen die, not a hung socket."""
    port = _free_port_in_window()
    ws_db.set_setting("display_count", str(port - 6080 + 1))
    _seed_live_run(ws_db, port)

    async def handler(ws):
        msg = await ws.recv()
        await ws.send(b"final:" + msg)
        await ws.close()

    cookie = _session_cookie(get_session_secret(ws_db))
    async with ws_serve(handler, "127.0.0.1", port):
        sent, q, task = await _drive_websocket(ws_app, _ws_scope(port, cookie))
        try:
            await _wait_for(sent, lambda s: any(m["type"] == "websocket.accept"
                                                for m in s),
                            "the authenticated upgrade was not accepted")
            await q.put({"type": "websocket.receive", "bytes": b"bye"})
            await _wait_for(sent, lambda s: any(
                m["type"] == "websocket.send" and m.get("bytes") == b"final:bye"
                for m in s), "the upstream frame was not relayed to the client")
            await _wait_for(sent, lambda s: any(m["type"] == "websocket.close"
                                                for m in s),
                            "the client websocket was not closed after the "
                            "upstream closed")
        finally:
            _cancel_task(task)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
