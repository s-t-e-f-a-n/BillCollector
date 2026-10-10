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
"""

import logging
import os
from pathlib import Path

from . import config

logger = logging.getLogger("billcollector.display")

WEBSOCKIFY_BASE_PORT = 6080  # websockify port = 6080 + (display - display_start)


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
