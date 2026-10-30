"""Browser cache precedence and safe launch diagnostics without live services."""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

from billcollector import runner
from billcollector.redaction import launch_failure_record

APPS = Path(__file__).resolve().parents[1] / "apps"


@pytest.mark.parametrize("order", ["runner", "helpers-first"])
@pytest.mark.parametrize("playwright_path,browser_path", [
    (None, None), ("", None), ("/synthetic/cache", None),
    ("/synthetic/cache", "/synthetic/fallback"),
    ("", "/synthetic/fallback"), (None, "/synthetic/fallback"),
    ("0", "/synthetic/fallback"), (None, ""), ("", ""),
])
def test_runner_import_respects_browser_cache(tmp_path, order, playwright_path, browser_path):
    env = {k:v for k,v in os.environ.items()
           if not k.startswith(("BC_", "BW_")) and k != "PLAYWRIGHT_BROWSERS_PATH"}
    env.update(PYTHONPATH=str(APPS), PYTHONDONTWRITEBYTECODE="1",
               BC_DATA_DIR=str(tmp_path / "runtime"), BC_DB_DIR=str(tmp_path / "db"),
               BC_DB_FILE=str(tmp_path / "db/proof.db"))
    if playwright_path is not None:
        env["PLAYWRIGHT_BROWSERS_PATH"] = playwright_path
    if browser_path is not None:
        env["BC_BROWSER_DIR"] = browser_path
    code = ("from helpers import BillCollectorHelpers;" if order == "helpers-first" else "")
    code += "from billcollector import runner, config;import os,json;print(json.dumps(dict(cache=os.environ['PLAYWRIGHT_BROWSERS_PATH'],browser=str(config.BROWSER_DIR))))"
    result = subprocess.run([sys.executable, "-c", code], env=env, cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    proof = json.loads(result.stdout)
    assert proof["cache"] == (playwright_path or browser_path or str(APPS / "browser"))
    assert proof["browser"] == (browser_path or str(APPS / "browser"))
    assert not (tmp_path / "runtime").exists()
    assert not (tmp_path / "db").exists()


def test_launch_failure_logs_a_reason_without_secret_details(caplog):
    error = RuntimeError("BrowserType.launch_persistent_context: Executable doesn't exist at /synthetic/SECRET_TOKEN\nCall log: --password=SECRET_PASSWORD")
    with mock.patch.object(runner, "sync_playwright"), mock.patch.object(runner, "_launch_browser", side_effect=error):
        assert runner._run_recipe(SimpleNamespace(), {"services":[]}) == ([], True, None)
    assert "RuntimeError" in caplog.text
    assert "Browser executable does not exist" in caplog.text
    assert "SECRET_TOKEN" not in caplog.text
    assert "SECRET_PASSWORD" not in caplog.text
    assert "Call log" not in caplog.text


def test_unrecognized_launch_line_never_enters_public_evidence():
    record = launch_failure_record(RuntimeError("private-username private-password https://fixture.invalid/?token=secret\npermission denied"))
    assert record["message"] == "Browser launch failed; unrecognized details omitted"
    assert "private-" not in json.dumps(record)
    assert "token" not in json.dumps(record)
