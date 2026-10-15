# -*- coding: utf-8 -*-
"""Shared display formatting for the daemon UI (M3 chunk S1.2).

Extracted from ``task_detail`` so the session page (and any future page)
reuses the same wording conventions instead of re-implementing them.
"""

from datetime import datetime


def deadline_text(deadline_at) -> str:
    """The pause deadline with its countdown (``Deadline: … (mm:ss
    remaining)``), or ``… (passed)`` once it is over."""
    if not deadline_at:
        return "Deadline: —"
    try:
        dl = datetime.strptime(deadline_at, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return f"Deadline: {deadline_at}"
    remaining = int((dl - datetime.now()).total_seconds())
    if remaining <= 0:
        return f"Deadline: {deadline_at} (passed)"
    h, rem = divmod(remaining, 3600)
    m, s = divmod(rem, 60)
    left = f"{h}h {m:02d}m" if h else f"{m:02d}:{s:02d}"
    return f"Deadline: {deadline_at} ({left} remaining)"
