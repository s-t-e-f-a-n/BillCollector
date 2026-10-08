"""Check a disposable image with no network, vault or host runtime mounts.

From the repository root, after building the image:
    docker run --rm --network none --shm-size 256m \
        -v "$PWD/tests:/checks:ro" --entrypoint python3 IMAGE \
        /checks/check_image_runtime.py

Only packaged application code and synthetic tests are copied into a temporary
directory. Profiles, databases and downloads are private to this check.
"""

import os
import runpy
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright


def check_browser(headless):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            page.set_content("<h1>BillCollector runtime check</h1>")
            assert page.locator("h1").inner_text() == "BillCollector runtime check"
            if headless:
                assert page.screenshot().startswith(b"\x89PNG\r\n\x1a\n")
        finally:
            browser.close()
    print(f"PASS Chromium headless={headless}", flush=True)


def stop_process(process):
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def check_headed_browser():
    display = subprocess.Popen(
        ["Xvfb", ":99", "-screen", "0", "1280x720x24", "-nolisten", "tcp", "-ac"]
    )
    try:
        deadline = time.monotonic() + 30
        # Read Xvfb's standard socket; never create an insecure temporary file.
        while not Path("/tmp/.X11-unix/X99").exists():  # nosec B108
            if display.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("Xvfb did not start")
            time.sleep(0.1)
        environment = dict(os.environ, DISPLAY=":99")
        subprocess.run(
            [sys.executable, __file__, "--headed"], env=environment, check=True, timeout=60
        )
    finally:
        stop_process(display)


def check_ui(checkout):
    with tempfile.TemporaryFile(mode="w+") as log:
        process = subprocess.Popen(
            [sys.executable, "apps/bc_ui.py"], cwd=checkout, stdout=log, stderr=log
        )
        try:
            deadline = time.monotonic() + 60
            while process.poll() is None and time.monotonic() < deadline:
                try:
                    # Fixed loopback HTTP URL, with no user-provided scheme or host.
                    with urllib.request.urlopen("http://127.0.0.1:8000/", timeout=2) as response:  # nosec B310
                        assert response.status == 200
                        assert b"BillCollector" in response.read()
                    print("PASS NiceGUI HTTP startup", flush=True)
                    return
                except OSError:
                    time.sleep(0.2)
            log.seek(0)
            raise RuntimeError(f"NiceGUI did not start:\n{log.read()}")
        finally:
            stop_process(process)


def main():
    if os.getuid() == 0:
        raise RuntimeError("Run with the image's configured non-root identity")
    if sys.argv[1:] == ["--headed"]:
        check_browser(headless=False)
        return
    if sys.argv[1:]:
        raise ValueError("This check accepts no runtime or vault inputs")
    for key in list(os.environ):
        if key.startswith(("BW_", "VAULT_", "BILLCOLLECTOR_")):
            del os.environ[key]
    # Dependency consistency is checked during the build, before pip is removed.
    check_browser(headless=True)
    check_headed_browser()
    with tempfile.TemporaryDirectory(prefix="billcollector-image-") as directory:
        checkout = Path(directory)
        shutil.copytree(
            "/apps", checkout / "apps",
            ignore=shutil.ignore_patterns(
                "browser", "db", "Downloads", ".env", ".venv", "__pycache__",
                "*.log", ".bc*",
            ),
        )
        shutil.copytree(Path(__file__).resolve().parent, checkout / "tests")
        check_ui(checkout)
        # Helpers create private paths and reset the browser cache environment.
        # Restore only the packaged browser binaries after importing them.
        os.chdir(checkout)
        sys.path.insert(0, str(checkout / "apps"))
        sys.path.insert(0, str(checkout))
        from BillCollectorServices_pw import DatabaseManager
        from helpers import DB_FILE

        DatabaseManager(DB_FILE).close_connection()
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/apps/browser"
        sys.argv = ["tests/run_regression.py", "--ini", "tests/bc_regression.ini"]
        runpy.run_path("tests/run_regression.py", run_name="__main__")


if __name__ == "__main__":
    main()
