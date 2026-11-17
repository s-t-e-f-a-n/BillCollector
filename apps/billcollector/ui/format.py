# -*- coding: utf-8 -*-
"""Shared display formatting for the daemon UI (M3 chunk S1.2).

Extracted from ``task_detail`` so the session page (and any future page)
reuses the same wording conventions instead of re-implementing them.

Table column convention (used by every table in the UI):

- Alignment: numeric columns and the Actions column are
  ``align: "right"``; everything else (text, badges, timestamps) left.
- Labels: the service/user pair column is labelled "Task" in every table.
- Mono: technical cells (timestamps, cron, SHA, filenames, run ids,
  counts) render ``font-mono``. The flag is carried as ``mono: True`` in
  the column dict (q-table passes column dicts through to the client
  verbatim) and applied in the body slot via
  ``:class="col.mono ? 'font-mono' : ''"`` on the default cell span.
"""

from datetime import datetime


def table_column(name: str, label: str, *, align: str | None = None,
                 mono: bool = False) -> dict:
    """Build one q-table column dict following the table convention.

    ``align`` and ``mono`` are optional; both survive q-table's column
    normalisation to the client-side ``props.cols``."""
    column: dict = {"name": name, "label": label, "field": name}
    if align:
        column["align"] = align
    if mono:
        column["mono"] = True
    return column


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
