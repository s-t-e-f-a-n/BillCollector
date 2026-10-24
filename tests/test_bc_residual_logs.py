"""Synthetic runner exceptions must not reach durable logs or SQLite notes."""

from pathlib import Path

from tests.test_bc_orchestrator import OrchestratorTestBase


# Use the real subprocess output monitor. Only browser/vault operations are
# replaced; every case calls the production exception handler before exiting 1.
RESIDUAL_RUNNER = '''
import logging
import os
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, os.environ["ORCH_TEST_APPS"])
from billcollector import pause, runner
from billcollector.db import Database

logging.basicConfig(level=logging.WARNING)
db = Database(os.environ["ORCH_TEST_DB"])
task_id = int(sys.argv[-1])
run_id = db.create_run(task_id, pid=os.getpid())
source = os.environ["ORCH_TEST_MODE"]
marker = "synthetic-retention-marker"
error = RuntimeError(marker)
page = Mock()
ctx = SimpleNamespace(
    page=page, context=Mock(), db=db, run_id=run_id, pause_count=1,
    files_downloaded=[], bcs=SimpleNamespace(usr="synthetic"),
)

if source == "scan":
    with patch.object(pause, "PageState", side_effect=error):
        assert pause.scan_elements(page) == []
elif source == "otp":
    bcs = SimpleNamespace(api_url="http://vault.invalid", vault_item_name="synthetic",
                          otp_fallback="fallback")
    with patch.object(runner, "get_totp", side_effect=runner.VaultAPIError(marker)):
        assert runner._fresh_otp(bcs) == "fallback"
elif source == "pause-screenshot":
    page.url = "https://portal.invalid/"
    page.title.return_value = "Synthetic"
    page.inner_text.return_value = "Synthetic"
    page.screenshot.side_effect = error
    with patch.object(pause, "PageState", return_value=SimpleNamespace(interactive_elements=[])):
        context = pause.build_pause_context(ctx, "wait_user", "Synthetic", None, None, "d")
    assert context["screenshot"] == {"path": None, "data": None}
elif source == "step-screenshot":
    page.screenshot.side_effect = error
    state = SimpleNamespace(step_number=1, locator_action="{}", interactive_elements=[], error_status=[])
    runner._record_step(ctx, state, {"step": 1})
elif source in {"browser", "recipe"}:
    recipe = {"services": [{"serviceName": "synthetic", "steps": [{"step": 1}]}]}
    launch_error = error if source == "browser" else None
    with patch.object(runner, "sync_playwright"), \\
            patch.object(runner, "_launch_browser", side_effect=launch_error), \\
            patch.object(runner, "_execute_step_with_pause", side_effect=error):
        assert runner._run_recipe(ctx, recipe) == ([], True, None)
elif source == "task":
    task_db = Mock()
    task_db.create_run.return_value = run_id
    task_db.get_task.return_value = {
        "recipe_file": "synthetic", "service": "synthetic",
        "login_locked": 0, "login_pending_run_id": None,
        "date_window_days": 90,
    }
    with patch.object(runner, "Database", return_value=task_db), \\
            patch.object(runner, "CheckRecipe", return_value={"services": []}), \\
            patch.object(runner, "_install_signal_handlers"), \\
            patch.object(runner.display, "allocate_display", return_value=(99, 6080)), \\
            patch.object(runner.display, "release_display"), \\
            patch.object(runner, "_start_display_stack", return_value=None), \\
            patch.object(runner, "_vault_preflight", return_value={}), \\
            patch.object(runner, "_RunContext", return_value=ctx), \\
            patch.object(runner, "_run_recipe", side_effect=error):
        assert runner.run_task(task_id) == 1
else:
    raise AssertionError("unknown synthetic source")

db.close()
sys.exit(1)
'''


class ResidualLogTests(OrchestratorTestBase):
    def test_exception_handlers_keep_safe_diagnostics_in_logs_and_failed_run_notes(self):
        self.stub.write_text(RESIDUAL_RUNNER, encoding="utf-8")
        for source, method in (
            ("scan", "scan_elements"),
            ("otp", "get_totp"),
            ("pause-screenshot", "screenshot"),
            ("step-screenshot", "screenshot"),
            ("browser", "launch_persistent_context"),
            ("recipe", "run_recipe"),
            ("task", "run_task"),
        ):
            with self.subTest(source=source):
                task_id = self.db.create_task("synthetic", source, enabled=True)
                orch = self._orch(mode=source)
                orch._env.update({"BC_DATA_DIR": str(self.tmp / "data")})
                self.assertEqual(self._run_to_exit(orch, task_id), 1)
                run = self.db.list_runs(task_id)[0]
                self.assertEqual(run["result"], "failure")
                self.assertEqual(self.db.get_task(task_id)["status"], "idle")
                for retained in (Path(run["log_path"]).read_text(), run["notes"]):
                    self.assertNotIn("synthetic-retention-marker", retained)
                    self.assertNotIn("Traceback", retained)
                    self.assertIn("'method': '" + method + "'", retained)
                    self.assertIn("'category': 'other'", retained)
