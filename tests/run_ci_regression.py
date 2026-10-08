"""Run existing regression scenarios in a fresh private copy of tracked inputs."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    # Reuse installed binaries, never copy any live browser profile or DB.
    # Unset: prefer install_local.sh's apps/browser, else Playwright's own platform default ("").
    configured_cache = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    local_browsers = ROOT / "apps" / "browser"
    if configured_cache == "0":
        browser_cache = "0"
    elif configured_cache:
        browser_cache = str(Path(configured_cache).resolve())
    else:
        browser_cache = str(local_browsers) if local_browsers.is_dir() else ""
    # Tracked plus untracked, non-ignored inputs, so work in progress is exercised.
    tracked = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard",
                                       "apps", "tests"], cwd=ROOT)
    with tempfile.TemporaryDirectory(prefix="billcollector-ci-") as directory:
        checkout = Path(directory)
        for raw_name in tracked.split(b"\0"):
            if not raw_name:
                continue
            name = Path(os.fsdecode(raw_name))
            if name.name == ".env" or {"db", "browser", "Downloads", "profiles", ".venv"} & set(name.parts):
                raise RuntimeError("Runtime data unexpectedly tracked in CI inputs")
            source = ROOT / name
            if source.is_symlink():
                raise RuntimeError("Symlink unexpectedly tracked in CI inputs")
            if not source.exists():
                print(f"Skipping tracked input deleted in the working tree: {name}", file=sys.stderr)
                continue
            target = checkout / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        # Run inside the private copy: helper imports also create DB directories.
        bootstrap = """
import os, runpy, sys
sys.path.insert(0, 'apps')
from BillCollectorServices_pw import DatabaseManager
from helpers import DB_FILE
DatabaseManager(DB_FILE).close_connection()
if sys.argv[1]:
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = sys.argv[1]
else:
    os.environ.pop('PLAYWRIGHT_BROWSERS_PATH', None)  # helpers forced the private copy's empty apps/browser
sys.argv = ['tests/run_regression.py', '--ini', 'tests/bc_regression.ini']
runpy.run_path('tests/run_regression.py', run_name='__main__')
"""
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("BW_", "BILLCOLLECTOR_", "VAULT_"))}
        result = subprocess.run([sys.executable, "-c", bootstrap, browser_cache],
                                cwd=checkout, env=environment, check=False)
        return result.returncode


if __name__ == "__main__":
    sys.exit(main())
