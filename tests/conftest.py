# -*- coding: utf-8 -*-
"""Shared pytest configuration for the BillCollector test suite (M2 D1).

The runtime package lives in ``apps/``; make it importable for every test
module. Screen tests (``nicegui.testing.Screen``) drive a real Chromium via
the repo-local browser build, so point Playwright at it before playwright
is imported anywhere.

The ``BC_*`` env redirects send the daemon's runtime paths (data, db, logs,
downloads) into a per-session temp dir so the committed suite never touches
the repo's ``apps/data``, ``apps/db``, etc. Existing tests that pass explicit
paths or patch ``config`` attributes keep their own fixtures and are
unaffected. ``BC_BROWSER_DIR`` is deliberately NOT redirected: the repo
browser build must stay where Playwright expects it.
"""

import atexit
import ipaddress
import os
import shutil
import signal
import socket
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
APPS_DIR = REPO_ROOT / "apps"

if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(APPS_DIR / "browser"))

_TEST_ROOT = Path(tempfile.mkdtemp(prefix="bc-tests-"))
os.environ["BC_DATA_DIR"] = str(_TEST_ROOT / "data")
os.environ["BC_DB_DIR"] = str(_TEST_ROOT / "db")
os.environ["BC_DB_FILE"] = str(_TEST_ROOT / "db" / "bc.db")
os.environ["BC_PROFILE_ROOT"] = str(_TEST_ROOT / "profiles")
os.environ["BC_LOG_DIR"] = str(_TEST_ROOT / "logs")
os.environ["BC_DOWNLOAD_DIR"] = str(_TEST_ROOT / "downloads")
atexit.register(shutil.rmtree, _TEST_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolate_test_transports_and_signals(monkeypatch):
    """Permit local fixtures only; keep runner signal handlers inside one test.

    Mocked HTTP clients do not reach a socket. A forgotten notification mock
    must fail before a packet reaches any external/shared service.
    """
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}

    def check(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            host = address[0]
            try:
                local = ipaddress.ip_address(host).is_loopback
            except ValueError:
                local = host == "localhost"
            if not local:
                raise AssertionError("Tests may connect only to loopback fixtures")

    def connect(sock, address):
        check(sock, address)
        return original_connect(sock, address)

    def connect_ex(sock, address):
        check(sock, address)
        return original_connect_ex(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    yield
    for sig, handler in handlers.items():
        signal.signal(sig, handler)
