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
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APPS_DIR = REPO_ROOT / "apps"

if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(APPS_DIR / "browser"))

_TEST_ROOT = Path(tempfile.mkdtemp(prefix="bc-tests-"))
os.environ.setdefault("BC_DATA_DIR", str(_TEST_ROOT / "data"))
os.environ.setdefault("BC_DB_DIR", str(_TEST_ROOT / "db"))
os.environ.setdefault("BC_LOG_DIR", str(_TEST_ROOT / "logs"))
os.environ.setdefault("BC_DOWNLOAD_DIR", str(_TEST_ROOT / "downloads"))
atexit.register(shutil.rmtree, _TEST_ROOT, ignore_errors=True)
