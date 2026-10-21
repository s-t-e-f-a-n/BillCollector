# -*- coding: utf-8 -*-
"""NiceGUI main file for the UI tests (nicegui.testing.User simulation).

Executed via runpy by the ``user`` fixture (pytest.ini ``main_file``).
Builds the exact production wiring (``ui.app.build_app`` + the C7.5
lifecycle hooks) against a fresh temp DB, and publishes the DB path in
``BC_UI_TEST_DB`` so test fixtures can open the same file to seed or
inspect state. In the simulation ``ui.run`` performs no server start.
"""

import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps"))

from billcollector.db import Database  # noqa: E402
from billcollector.orchestrator import Orchestrator  # noqa: E402
from billcollector.scheduler import TaskScheduler  # noqa: E402
from billcollector.ui import app as ui_app  # noqa: E402
from nicegui import app as nicegui_app  # noqa: E402
from nicegui import ui  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="bc-ui-test-")
os.environ["BC_UI_TEST_DB"] = str(Path(_TMP) / "test.db")

db = Database(path=os.environ["BC_UI_TEST_DB"])
# M4 C2: the tests exercise the post-onboarding app; simulate the serve
# startup auto-complete (an upgraded install) so the onboarding gate in
# the auth middleware does not redirect every page to /onboarding.
# The onboarding tests (test_bc_ui_onboarding.py) re-activate the wizard
# per test.
db.set_setting("onboarding_done", "1")
orchestrator = Orchestrator(db)
scheduler = TaskScheduler(db, orchestrator.start_run)
startup, shutdown = ui_app.build_lifecycle(db, orchestrator, scheduler)
ui_app.build_app(db, orchestrator, scheduler)

nicegui_app.on_startup(startup)
nicegui_app.on_shutdown(shutdown)

ui.run(host="127.0.0.1", port=8000, title="BillCollector",
       show=False, reload=False)
