"""Runtime startup with an unwritable application tree and private data."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

APPS = Path(__file__).resolve().parents[1] / "apps"


def copy_apps(destination):
    shutil.copytree(
        APPS, destination,
        ignore=shutil.ignore_patterns(
            ".venv", "browser", "data", "db", "Downloads", "__pycache__",
            ".env", "*.log", ".bc.lock",
        ),
    )


def environment(apps, runtime):
    # Never inherit a real vault endpoint or the suite's BC_* directories.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("BC_", "BW_"))}
    env.update(
        PYTHONPATH=str(apps), PYTHONDONTWRITEBYTECODE="1",
        BC_DATA_DIR=str(runtime), BC_DB_DIR=str(runtime / "db"),
        BC_DB_FILE=str(runtime / "db" / "bc.db"),
        BC_PROFILE_ROOT=str(runtime / "profiles"),
        BC_DOWNLOAD_DIR=str(runtime / "output"),
    )
    return env


def test_runner_starts_with_only_configured_runtime_writable(tmp_path):
    apps = tmp_path / "apps"
    runtime = tmp_path / "runtime"
    copy_apps(apps)
    apps.chmod(0o555)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "billcollector", "run", "999999"],
            cwd=apps, env=environment(apps, runtime),
            capture_output=True, text=True, timeout=30,
        )
        # A missing synthetic task reaches the runner without a vault call,
        # display stack, browser, recipe or provider access.
        assert result.returncode == 1, result.stderr
        assert "runner: task 999999 not found" in result.stderr
        assert "PermissionError" not in result.stderr
        assert not (apps / "db").exists()
        assert (runtime / "db" / "bc.db").is_file()
        for name in ("profiles", "output", "logs", "displays", "runs"):
            assert (runtime / name).is_dir(), name
    finally:
        apps.chmod(0o755)


def test_legacy_database_creates_default_directory_when_opened(tmp_path):
    apps = tmp_path / "apps"
    copy_apps(apps)
    env = environment(apps, tmp_path / "unused")
    env = {key: value for key, value in env.items()
           if not key.startswith("BC_")}
    result = subprocess.run(
        [sys.executable, "-c", """
from pathlib import Path
from helpers import APP_DIR, DB_DIR, DB_FILE
from billcollector import config
from BillCollectorServices_pw import DatabaseManager
root = Path(APP_DIR)
assert Path(DB_DIR) == root / 'db'
assert Path(DB_FILE) == root / 'db' / 'bc.db'
assert config.DB_FILE == root / 'db' / 'bc.db'
assert config.PROFILE_ROOT == root / 'browser' / 'profiles'
assert config.DOWNLOAD_DIR == root / 'Downloads'
assert not Path(DB_DIR).exists()
database = DatabaseManager(DB_FILE)
assert database.conn.execute('SELECT COUNT(*) FROM Service').fetchone() == (0,)
database.conn.close()
assert Path(DB_FILE).is_file()
"""], cwd=apps, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "unused").exists()
