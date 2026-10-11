# -*- coding: utf-8 -*-
"""Versioned control-socket protocol (the intervention contract).

A unix socket per running session carries JSON-line messages between a
client (the web UI's Copilot view, or a test harness) and the runner's
waiting loop. The first field of every message is ``v`` (starts at 1);
protocol changes need a version bump and a doc update.

Protocol (v1):
    request  {"v": 1, "action": <name>, "args": {...}}
    response {"v": 1, "ok": true, ...payload}
             {"v": 1, "ok": false, "error": "..."}

Actions:
    screenshot -> {"screenshot": <base64 PNG>}
    elements   -> {"elements": [{n, role, name, rect, locator, actionTypes[, url]}]}
    context    -> {"context": <machine-readable pause payload>}
    click      {n}
    fill       {n, text}
    press      {key}
    drag       {n, dx, dy}   (relative mouse drag from element n)
    resume     (reserved: ends the pause, consumed by the runner)
    cancel     (reserved: aborts the run, consumed by the runner)

The server side (``ControlServer``) is served by the runner's MAIN thread
while it is in the waiting loop: the waiting loop calls ``poll()`` between
steps, so sync Playwright calls made by the action handlers are safe. The
UI opens a short-lived connection per request (``ControlClient``).
"""

import json
import logging
import os
import select
import socket

from .interrupt import RunInterrupted

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 4 * 1024 * 1024   # request and response cap
CLIENT_TIMEOUT = 120                  # seconds; screenshots are big
_READ_TIMEOUT = 60                    # seconds to receive one full request line


class ControlError(Exception):
    """A control-socket request failed (transport or protocol)."""


def _encode(msg):
    return (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")


class ControlServer:
    """Server side, polled from the runner's main thread in the waiting loop."""

    def __init__(self, sock_path, handlers):
        """``handlers`` maps action name to a callable ``f(**args) -> dict``.
        ``resume`` and ``cancel`` are reserved and must not be in ``handlers``."""
        if "resume" in handlers or "cancel" in handlers:
            raise ValueError("resume and cancel are reserved protocol actions")
        self.sock_path = str(sock_path)
        self.handlers = handlers
        self.resume_requested = False
        self.cancel_requested = False
        self._sock = None

    def start(self):
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(self.sock_path)
        self._sock.listen(4)
        self._sock.setblocking(False)

    def poll(self, timeout=0.5):
        """Handle one pending request, if any. Returns True when one was handled."""
        if self._sock is None:
            return False
        try:
            ready, _, _ = select.select([self._sock], [], [], timeout)
        except OSError:
            return False
        if not ready:
            return False
        try:
            conn, _ = self._sock.accept()
        except OSError:
            return False
        try:
            response = self._serve_connection(conn)
        except RunInterrupted:
            raise  # a shutdown signal during an action ends the run, not the request
        except Exception as e:
            logger.exception(f"Control socket error: {e}")
            response = {"v": PROTOCOL_VERSION, "ok": False, "error": str(e)}
        try:
            conn.sendall(_encode(response))
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass
        return True

    def _serve_connection(self, conn):
        conn.settimeout(_READ_TIMEOUT)
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = conn.recv(4096)
            if not chunk:
                return {"v": PROTOCOL_VERSION, "ok": False, "error": "client disconnected"}
            buf += chunk
            if len(buf) > MAX_MESSAGE_BYTES:
                return {"v": PROTOCOL_VERSION, "ok": False, "error": "request too large"}
        try:
            msg = json.loads(buf.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {"v": PROTOCOL_VERSION, "ok": False, "error": "malformed JSON request"}
        if not isinstance(msg, dict):
            return {"v": PROTOCOL_VERSION, "ok": False, "error": "request must be a JSON object"}
        if msg.get("v") != PROTOCOL_VERSION:
            return {"v": PROTOCOL_VERSION, "ok": False,
                    "error": f"unsupported protocol version {msg.get('v')!r}"}
        action = msg.get("action")
        args = msg.get("args") or {}
        if not isinstance(args, dict):
            return {"v": PROTOCOL_VERSION, "ok": False, "error": "args must be a JSON object"}
        if action == "resume":
            self.resume_requested = True
            return {"v": PROTOCOL_VERSION, "ok": True}
        if action == "cancel":
            self.cancel_requested = True
            return {"v": PROTOCOL_VERSION, "ok": True}
        handler = self.handlers.get(action)
        if handler is None:
            return {"v": PROTOCOL_VERSION, "ok": False, "error": f"unknown action {action!r}"}
        try:
            payload = handler(**args)
        except RunInterrupted:
            raise  # a shutdown signal during an action ends the run, not the request
        except Exception as e:
            # A failed action is reported to the client; the pause stays active.
            logger.warning(f"Control action {action} failed: {e}")
            return {"v": PROTOCOL_VERSION, "ok": False, "error": f"{action} failed: {e}"}
        if payload is None:
            payload = {}
        return {"v": PROTOCOL_VERSION, "ok": True, **payload}

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if os.path.exists(self.sock_path):
            try:
                os.unlink(self.sock_path)
            except OSError:
                pass


class ControlClient:
    """Client side: one short-lived connection per request (UI and tests)."""

    def __init__(self, sock_path, timeout=CLIENT_TIMEOUT):
        self.sock_path = str(sock_path)
        self.timeout = timeout

    def request(self, action, **args):
        """Send one action and return the full response dict.

        Raises :class:`ControlError` on transport failure or ``ok: false``.
        """
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(self.timeout)
            sock.connect(self.sock_path)
            sock.sendall(_encode({"v": PROTOCOL_VERSION, "action": action, "args": args}))
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
                if len(buf) > MAX_MESSAGE_BYTES:
                    raise ControlError("response too large")
            if not buf:
                raise ControlError("server closed the connection")
            msg = json.loads(buf.decode("utf-8"))
        except (socket.timeout, ConnectionError, OSError) as e:
            raise ControlError(f"control socket request failed: {type(e).__name__}: {e}") from None
        except (ValueError, UnicodeDecodeError) as e:
            raise ControlError(f"malformed control response: {e}") from None
        finally:
            sock.close()
        if not isinstance(msg, dict) or not msg.get("ok", False):
            raise ControlError(msg.get("error", "unknown control error") if isinstance(msg, dict) else "bad response")
        return msg
