# BillCollector UI
# Minimal NiceGUI supervisor page: manually start/stop one service's scraping
# run and watch its stdout live. The UI is a pure subprocess supervisor - the
# scraping code stays untouched (except the additive --service flag).

import asyncio
import configparser
import json
import os
import signal
import sys
import time
from datetime import datetime

from nicegui import ui, app

# Paths relative to this file (the apps/ directory)
APP_DIR = os.path.dirname(os.path.realpath(__file__))
STATE_FILE = os.path.join(APP_DIR, ".bc_ui_run.json")

INI_CHOICES = ["bc_test.ini", "bc_default.ini"]   # plus a "custom" free-path entry
LOG_MAX_LINES = 2000                              # drop oldest lines beyond this
STOP_TIMEOUT = 10                                 # seconds of SIGTERM before SIGKILL

# Global state of the supervised run (shared across all open pages)
run = {"status": "idle", "proc": None, "start_time": None, "stop_requested": False}
pages = []            # per-page element handles, for status/log broadcast
startup_notes = []    # on_startup notes, shown when a page opens

STATUS_CLASSES = {
    "idle": "text-gray-400",
    "running": "text-green-600",
    "finished": "text-blue-600",
    "stopped": "text-amber-600",
    "error": "text-red-600",
}


def parse_ini_services(ini_path):
    """Return the service names of the [Playwright] section, case preserved."""
    parser = configparser.ConfigParser()
    parser.optionxform = str
    try:
        parser.read(ini_path, encoding="utf-8")
    except (configparser.Error, OSError):
        return []
    if "Playwright" not in parser:
        return []
    return [name for name in parser["Playwright"] if name]


def _group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _log(line):
    """Push one line to the log of every open page."""
    for ctl in list(pages):
        try:
            ctl["log"].push(line)
        except Exception:
            pages.remove(ctl)


def _apply(ctl, status):
    running = status == "running"
    ctl["status"].set_text(status)
    ctl["status"].classes(replace=STATUS_CLASSES.get(status.split(" (")[0], "text-gray-400"))
    if running:
        ctl["start"].disable()
        ctl["stop"].enable()
    else:
        ctl["start"].enable()
        ctl["stop"].disable()


def _set_status(status):
    run["status"] = status
    for ctl in list(pages):
        _apply(ctl, status)


def _write_state(pgid, ini, service):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"pgid": pgid, "ini": ini, "service": service,
                   "started": datetime.now().isoformat()}, f)


def _remove_state():
    try:
        os.remove(STATE_FILE)
    except FileNotFoundError:
        pass


async def pump(proc):
    """Consume the run's stdout line by line until the process exits."""
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        _log(line.decode(errors="replace").rstrip("\n"))
    rc = await proc.wait()
    if run["proc"] is proc:
        run["proc"] = None
        _remove_state()
        if run["stop_requested"]:
            _set_status("stopped")
        else:
            _set_status("finished" if rc == 0 else f"finished (exit {rc})")
    for ctl in list(pages):
        ctl["timer"].active = False
        ctl["elapsed"].set_text("")


async def start_run(ini, service):
    """Spawn the supervised run. Returns (ok, message)."""
    if run["proc"] is not None:
        return False, "a run is already in progress"
    if not ini or not os.path.isfile(ini):
        _set_status("error")
        _log(f"INI file not found: {ini!r}")
        return False, "ini file not found"
    if not service:
        _set_status("error")
        _log("No service selected.")
        return False, "no service selected"
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "BillCollector.py", ini, "--service", service,
            cwd=APP_DIR,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True)
    except Exception as e:
        _set_status("error")
        _log(f"Failed to start run: {e}")
        return False, str(e)
    run["proc"] = proc
    run["start_time"] = time.time()
    run["stop_requested"] = False
    _write_state(proc.pid, ini, service)
    _set_status("running")
    _log(f"Started: {service} | ini {ini} | pid {proc.pid}")
    for ctl in list(pages):
        ctl["timer"].active = True
    asyncio.create_task(pump(proc))
    return True, f"started pid {proc.pid}"


async def stop_run():
    """Stop the supervised run: SIGTERM the group, escalate to SIGKILL."""
    if run["proc"] is None or run["status"] != "running":
        return
    run["stop_requested"] = True
    pgid = run["proc"].pid
    _log("Stop requested (SIGTERM) ...")
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        _log("Run already gone.")
        return
    try:
        await asyncio.wait_for(run["proc"].wait(), timeout=STOP_TIMEOUT)
    except asyncio.TimeoutError:
        _log(f"Still alive after {STOP_TIMEOUT} s (SIGKILL) ...")
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def cleanup_orphans():
    """Kill a run left behind by a previous UI instance, or drop a stale state file."""
    if not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
        pgid = int(state["pgid"])
    except (OSError, ValueError, KeyError, TypeError):
        _remove_state()
        startup_notes.append("Removed stale .bc_ui_run.json (unreadable).")
        return
    if not _group_alive(pgid):
        _remove_state()
        startup_notes.append("Removed stale .bc_ui_run.json (process no longer alive).")
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
        for _ in range(50):  # up to 5 s grace before escalation
            if not _group_alive(pgid):
                break
            time.sleep(0.1)
        if _group_alive(pgid):
            os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    _remove_state()
    startup_notes.append(f"Cleaned up orphaned run (pgid {pgid}, "
                         f"ini {state.get('ini')}, service {state.get('service')}).")


app.on_startup(cleanup_orphans)


@ui.page("/")
def index():
    # --- layout ----------------------------------------------------------------
    with ui.row().classes("items-end gap-3"):
        ini_select = ui.select(INI_CHOICES + ["custom"], value="bc_test.ini",
                               label="ini file").classes("w-44")
        ini_input = ui.input("ini path", placeholder="path to ini file").classes("w-72")
        service_select = ui.select([], label="service").classes("w-56")
        start_btn = ui.button("Start")
        stop_btn = ui.button("Stop").props("outline")
    with ui.row().classes("items-center gap-4"):
        status_label = ui.label(run["status"])
        elapsed_label = ui.label("")
    log = ui.log(max_lines=LOG_MAX_LINES)
    log.classes("w-full h-96")

    ini_input.visible = False

    # --- page behavior -----------------------------------------------------------
    def ini_path():
        if ini_select.value == "custom":
            return (ini_input.value or "").strip()
        return os.path.join(APP_DIR, ini_select.value)

    def refresh_services():
        path = ini_path()
        services = parse_ini_services(path) if path and os.path.isfile(path) else []
        service_select.options = services
        service_select.value = services[0] if services else None
        service_select.update()

    def ini_changed():
        ini_input.visible = ini_select.value == "custom"
        refresh_services()

    ini_select.on_value_change(lambda _: ini_changed())
    ini_input.on_value_change(lambda _: refresh_services())

    async def start():
        await start_run(ini_path(), service_select.value)

    async def stop():
        await stop_run()

    start_btn.on_click(start)
    stop_btn.on_click(stop)

    # --- bookkeeping ---------------------------------------------------------------
    def tick():
        if run["proc"] is not None and run["start_time"] is not None:
            secs = int(time.time() - run["start_time"])
            h, rem = divmod(secs, 3600)
            m, s = divmod(rem, 60)
            elapsed_label.set_text(f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}")

    ctl = {"status": status_label, "elapsed": elapsed_label, "start": start_btn,
           "stop": stop_btn, "log": log,
           "timer": ui.timer(1.0, tick, active=run["proc"] is not None)}

    for note in startup_notes:
        _log(note)
    startup_notes.clear()

    refresh_services()
    _apply(ctl, run["status"])
    pages.append(ctl)
    ui.context.client.on_disconnect(lambda: pages.remove(ctl))


if __name__ == "__main__":
    ui.run(port=8000, host="0.0.0.0", title="BillCollector", show=False, reload=False)
