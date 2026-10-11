# -*- coding: utf-8 -*-
"""Per-run display lifecycle (M1 chunk C6).

Every run gets its own Xvfb display (decision 16: headful always): the
runner allocates a display number from the configured range
(``display_start`` .. ``display_start + display_count - 1``), claims it
with an atomic lockfile under ``data/displays/``, and owns the child
process stack (Xvfb + x11vnc + websockify) that gives the run its virtual
screen and the noVNC fallback channel. The display is released when the
run finishes; a lock left behind by a crashed run is freed by the
orchestrator's startup cleanup (C7.4).

The runner allocates the display (not the orchestrator) so that the
standalone ``python -m billcollector run <task_id>`` works without the
daemon (decision locked in the M1 chunk plan).

The stack children share the runner's process group (C7.5): the daemon
shutdown signals the runner's whole group, so the stack dies with the
runner even when the runner cannot clean up itself.
"""

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

from . import config

logger = logging.getLogger("billcollector.display")

WEBSOCKIFY_BASE_PORT = 6080  # websockify port = 6080 + (display - display_start)
VNC_BASE_PORT = 5900         # x11vnc RFB port = 5900 + display
XVFB_DEFAULT_SCREEN = "1280x1024x24"
NOVNC_WEB_DIR = Path("/usr/share/novnc")  # apt novnc web client (vnc.html)
X_SOCKET_DIR = Path("/tmp/.X11-unix")
XVFB_READY_TIMEOUT = 10.0
_STOP_TIMEOUT = 5.0


class DisplayError(Exception):
    """The display range is exhausted or a display operation failed."""


def websockify_port_for(display, display_start):
    """Websockify (noVNC) port of a display within the configured range."""
    return WEBSOCKIFY_BASE_PORT + (display - display_start)


def lock_path_for(display, display_dir=None):
    """Lockfile of one display in the claim registry (data/displays/:N.lock)."""
    base = Path(display_dir) if display_dir else config.DISPLAY_DIR
    return base / f":{display}.lock"


def _setting(db, key):
    """Settings-table value with the config default as fallback."""
    if db is not None:
        value = db.get_setting(key)
        if value is not None and str(value).strip():
            return value
    return config.DEFAULT_SETTINGS.get(key)


def display_range(db=None):
    """(display_start, display_count) from the Settings table (or defaults)."""
    start = int(_setting(db, "display_start"))
    count = int(_setting(db, "display_count"))
    return start, count


def allocate_display(db=None):
    """Claim the next free Xvfb display in the configured range.

    The claim is an atomic ``O_EXCL`` lockfile (one per display), so
    concurrent runners never take the same display. Returns
    ``(display_number, websockify_port)``. Raises DisplayError when no
    display in the range is free (stale locks of crashed runs are freed
    by the orchestrator's startup cleanup, C7.4)."""
    start, count = display_range(db)
    for n in range(start, start + count):
        lock = lock_path_for(n)
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"{os.getpid()}\n")
        logger.info(f"Allocated display :{n} (lockfile {lock.name})")
        return n, websockify_port_for(n, start)
    raise DisplayError(
        f"no free display in :{start}..:{start + count - 1}")


def release_display(display, display_dir=None):
    """Release a display claimed by this process.

    PID-checked unlink (the lockfile records the claiming pid): a lock
    that vanished or was re-claimed by someone else is left in place.
    Best-effort - the display is gone from this run's perspective either
    way."""
    lock = lock_path_for(display, display_dir)
    try:
        owner = lock.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return
    except OSError as e:
        logger.warning(f"Could not read display lock {lock}: {e}")
        return
    if owner != str(os.getpid()):
        logger.warning(
            f"Display lock {lock.name} is owned by pid {owner or 'unknown'}, "
            f"not this process ({os.getpid()}); leaving it in place")
        return
    try:
        lock.unlink()
    except FileNotFoundError:
        pass


def remove_display_lock(display, display_dir=None):
    """Force-remove a display lockfile without an ownership check.

    For the orchestrator's startup cleanup of crashed runs (C7.4), where
    the claiming process is long gone and the lock is stale by
    definition."""
    lock = lock_path_for(display, display_dir)
    try:
        lock.unlink()
    except FileNotFoundError:
        pass


def rfb_auth_file_for(run_id):
    """Per-run x11vnc auth file (deleted with the run's artifacts)."""
    return config.RUN_DIR / str(run_id) / "vnc.rfbauth"


def write_rfb_auth(path, password):
    """Create the x11vnc auth file for a password (``x11vnc -storepasswd``).

    Raises DisplayError when x11vnc is missing or refuses the password."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            ["x11vnc", "-storepasswd", password, str(path)],
            capture_output=True, text=True, timeout=15)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        raise DisplayError(f"could not create the VNC auth file: {e}") from e
    if proc.returncode != 0:
        raise DisplayError(f"x11vnc -storepasswd failed: "
                           f"{proc.stderr.strip() or proc.stdout.strip()}")
    return path


def _stack_env():
    """Environment for the display-stack children.

    WSL2+WSLg sessions export ``WAYLAND_DISPLAY``, and x11vnc (0.9.16)
    refuses to start against it ("Wayland display server detected").
    The stack only ever talks to X11 (the run's Xvfb), so the variable
    is stripped and the session type pinned to x11 for every child."""
    env = dict(os.environ)
    env.pop("WAYLAND_DISPLAY", None)
    env["XDG_SESSION_TYPE"] = "x11"
    return env


def _spawn(binary, *args, env=None):
    """Start one display-stack child (stdio to devnull, wayland-free env).

    The child deliberately stays in the runner's process group (C7.5): a
    daemon shutdown signals the runner's whole group (orchestrator
    shutdown), so the stack dies with the runner even when the runner
    cannot clean up itself; a terminal Ctrl+C on the standalone runner
    reaches the stack through the group as well (the runner's SIGINT
    handler makes that a graceful stop).

    Raises DisplayError when the binary is missing or the spawn fails."""
    try:
        return subprocess.Popen(
            [str(binary), *[str(a) for a in args]],
            env=env if env is not None else _stack_env(),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
    except FileNotFoundError as e:
        raise DisplayError(
            f"display binary not found: {e.filename} "
            f"(install the display stack: apt install x11vnc websockify novnc)"
        ) from e
    except OSError as e:
        raise DisplayError(f"could not start {binary}: {e}") from e


def _wait_for_x_display(display, timeout=XVFB_READY_TIMEOUT):
    """Wait for the X server socket of a display (Xvfb startup)."""
    socket_path = X_SOCKET_DIR / f"X{display}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if socket_path.exists():
            return
        time.sleep(0.05)
    raise DisplayError(
        f"Xvfb :{display} did not create {socket_path} within {int(timeout)}s")


def start_display_stack(display, rfb_auth_file=None, websockify_port=None,
                        binaries=None):
    """Spawn the per-run display stack for one display:

    - ``Xvfb :N`` (the virtual screen, default 1280x1024x24),
    - ``x11vnc -display :N -rfbport 5900+N -localhost`` - password auth
      only when an rfb auth file is given (default: localhost-only, no
      auth; the setting is empty by default),
    - ``websockify <port> 127.0.0.1:5900+N`` - the noVNC channel, serving
      the noVNC web client when the apt ``novnc`` package is present.

    ``binaries`` may override the binary per role ({"Xvfb", "x11vnc",
    "websockify"}) for tests. Returns the list of child Popen objects
    (stop_display_stack reaps them); a partially started stack is torn
    down and DisplayError is raised."""
    bins = {"Xvfb": "Xvfb", "x11vnc": "x11vnc", "websockify": "websockify"}
    if binaries:
        bins.update(binaries)
    if rfb_auth_file is not None and not Path(rfb_auth_file).exists():
        raise DisplayError(f"VNC auth file missing: {rfb_auth_file}")
    if websockify_port is None:
        websockify_port = websockify_port_for(
            display, int(config.DEFAULT_SETTINGS["display_start"]))

    env = _stack_env()
    children = []
    try:
        xvfb = _spawn(bins["Xvfb"], f":{display}", "-screen", "0",
                      XVFB_DEFAULT_SCREEN, env=env)
        children.append(xvfb)
        if xvfb.poll() is not None:
            raise DisplayError(
                f"Xvfb :{display} exited immediately (rc={xvfb.returncode})")
        _wait_for_x_display(display)

        vnc_args = ["-display", f":{display}", "-rfbport",
                    VNC_BASE_PORT + display, "-localhost"]
        if rfb_auth_file is not None:
            vnc_args += ["-rfbauth", str(rfb_auth_file)]
        else:
            vnc_args += ["-nopw"]
        children.append(_spawn(bins["x11vnc"], *vnc_args, env=env))

        ws_args = [websockify_port, f"127.0.0.1:{VNC_BASE_PORT + display}"]
        if NOVNC_WEB_DIR.is_dir():
            ws_args = ["--web", str(NOVNC_WEB_DIR), *ws_args]
        children.append(_spawn(bins["websockify"], *ws_args, env=env))
        logger.info(
            f"Display stack started for :{display} (x11vnc port "
            f"{VNC_BASE_PORT + display}, websockify port {websockify_port})")
        return children
    except Exception:
        stop_display_stack(children)
        raise


def stop_display_stack(children):
    """Terminate and reap the display-stack children (SIGKILL when they
    ignore SIGTERM). Tolerates already-dead children."""
    for proc in reversed(children or []):
        if proc.poll() is None:
            proc.terminate()
    for proc in children or []:
        try:
            proc.wait(timeout=_STOP_TIMEOUT)
        except subprocess.TimeoutExpired:
            logger.warning(f"Display child {proc.pid} ignored SIGTERM; killing")
            proc.kill()
            try:
                proc.wait(timeout=_STOP_TIMEOUT)
            except subprocess.TimeoutExpired:
                logger.error(f"Display child {proc.pid} could not be reaped")


def binaries_present():
    """True when the whole display stack is installed on this host."""
    return all(shutil.which(b) for b in ("Xvfb", "x11vnc", "websockify"))
