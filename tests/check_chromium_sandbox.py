"""Exercise the packaged daemon and batch launchers using synthetic data only.

Run through run_sandbox_container.py, in an owned network-none container.
"""

import argparse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
# Fixed executable/argument vectors; no shell or credentials.
import subprocess  # nosec B404
import sys
import tempfile
from threading import Thread
import time
from types import SimpleNamespace

sys.path.insert(0, "/apps")

from playwright.sync_api import sync_playwright  # noqa: E402

from billcollector import config, runner  # noqa: E402
import BillCollectorServices_pw as batch  # noqa: E402


class Portal(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/invoice":
            body = b"%PDF-1.4 sandbox synthetic invoice"
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", 'attachment; filename="synthetic.pdf"')
        else:
            body = b'<a href="/invoice">Download</a>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


@contextmanager
def display():
    process = subprocess.Popen(  # nosec B603
        ["/usr/bin/Xvfb", ":99", "-screen", "0", "1280x720x24", "-nolisten", "tcp", "-ac"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 15
        while not Path("/tmp/.X11-unix/X99").exists():  # nosec B108
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("Synthetic display failed")
            time.sleep(0.1)
        os.environ["DISPLAY"] = ":99"
        yield
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def sandbox_status(page, expected, mode):
    page.set_content("<h1>Synthetic renderer</h1>")
    if mode == "daemon":
        page.goto("chrome://sandbox")
        text = " ".join(page.locator("body").inner_text().split())
        active = all(value in text for value in (
            "You are adequately sandboxed.", "PID namespaces Yes",
            "Network namespaces Yes", "Seccomp-BPF sandbox Yes"))
        if not (active == (expected == 'active')):
            raise RuntimeError(text)
        if expected == "active":
            if 'Layer 1 Sandbox Namespace' not in text:
                raise RuntimeError(text)
    # The batch headless shell has no chrome://sandbox page. Check kernel
    # evidence for real renderers instead; Docker's filter alone is insufficient.
    def status(path):
        return dict(line.split(":", 1) for line in path.read_text().splitlines())

    parent = status(Path("/proc/self/status"))
    renderers = []
    for path in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            if b"--type=renderer" not in path.read_bytes():
                continue
            info = status(path.with_name("status"))
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        active = (len(info["NSpid"].split()) > len(parent["NSpid"].split())
                  and int(info["Seccomp_filters"]) > int(parent["Seccomp_filters"])
                  and info["NoNewPrivs"].strip() == "1")
        renderers.append(active)
    if not (renderers and all((active == (expected == 'active') for active in renderers))):
        raise RuntimeError(renderers)
    print(f"PASS {mode}: sandbox={expected}, renderer kernel evidence", flush=True)


def check_launcher(playwright, mode, expected, root, origin, failures):
    ctx = SimpleNamespace(task={"service": "synthetic", "user": "sandbox"},
                          bcs=SimpleNamespace())

    def launch():
        failures.clear()
        if mode == "daemon":
            runner._launch_browser(ctx, playwright)
            return ctx.context, ctx.page
        browser = batch.InitBrowser(playwright, SimpleNamespace(dbg=False))
        if browser is None:
            raise RuntimeError("Batch launch rejected")
        return browser, browser.new_page()

    try:
        browser, page = launch()
    except Exception:
        if expected != "blocked":
            raise
        if not (failures and any((marker in failures[-1] for marker in ('No usable sandbox', 'Operation not permitted', 'Failed to move to new namespace')))):
            raise RuntimeError('Launch failed without a demonstrated sandbox denial')
        print(f"PASS {mode}: launch rejected; no fallback", flush=True)
        return
    try:
        if not (expected != 'blocked'):
            raise RuntimeError('Browser launched when a sandbox rejection was expected')
        sandbox_status(page, expected, mode)
        page.goto(origin)
        page.evaluate("localStorage.setItem('synthetic', 'retained')")
        with page.expect_download() as pending:
            page.get_by_role("link", name="Download").click()
        output = root / f"{mode}.pdf"
        pending.value.save_as(output)
        if not (output.read_bytes() == b'%PDF-1.4 sandbox synthetic invoice'):
            raise RuntimeError('Synthetic check failed')
        print(f"PASS {mode}: PDF download", flush=True)
    finally:
        browser.close()
    if mode == "daemon":
        browser, page = launch()
        try:
            sandbox_status(page, expected, mode)
            page.goto(origin)
            if not (page.evaluate("localStorage.getItem('synthetic')") == 'retained'):
                raise RuntimeError('Synthetic check failed')
            prefs = config.profile_dir_for("synthetic", "sandbox") / "Default/Preferences"
            if not (json.loads(prefs.read_text())['plugins']['always_open_pdf_externally']):
                raise RuntimeError('Synthetic check failed')
            print("PASS daemon: persistent storage and PDF preference", flush=True)
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect", choices=("active", "disabled", "blocked"), required=True)
    parser.add_argument("--force-sandbox", action="store_true",
                        help="Baseline feasibility probe only; override the omitted launch option")
    args = parser.parse_args()
    if not (os.getuid() != 0):
        raise RuntimeError('A nonroot image is required')
    server = ThreadingHTTPServer(("127.0.0.1", 0), Portal)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="sandbox-check-") as directory, display(), \
                sync_playwright() as playwright:
            root = Path(directory)
            config.PROFILE_ROOT = root / "profiles"
            batch.CHROMIUM_PLAYWRIGHT_PROFILE = str(root / "batch")
            original = playwright.chromium.launch_persistent_context
            failures = []

            def observed_launch(**kwargs):
                if args.force_sandbox:
                    kwargs["chromium_sandbox"] = True
                try:
                    return original(**kwargs)
                except Exception as error:
                    failures.append(str(error))
                    raise

            playwright = SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=observed_launch))
            for mode in ("daemon", "batch"):
                check_launcher(playwright, mode, args.expect, root,
                               f"http://127.0.0.1:{server.server_port}", failures)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
