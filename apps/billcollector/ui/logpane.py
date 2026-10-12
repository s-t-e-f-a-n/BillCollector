# -*- coding: utf-8 -*-
"""The shared run log pane (M2 chunk D4.1c).

Extracted from the dashboard (D2.3) so the task detail page reuses the
exact same behavior: a ``ui.log`` element that shows a run's log file
content once, then follows the orchestrator's live stdout lines (D2.2)
for the selected run only. The pane keeps at most ~2000 lines (spec).
"""

from pathlib import Path

from nicegui import ui

from ..orchestrator import Orchestrator

# The log pane keeps at most this many lines (spec: ~2000).
LOG_MAX_LINES = 2000


class LogPane:
    """A ``ui.log`` pane that follows one run at a time."""

    def __init__(self, orchestrator: Orchestrator,
                 max_lines: int = LOG_MAX_LINES) -> None:
        self.orchestrator = orchestrator
        self.selected_run_id = None
        self.log = ui.log(max_lines=max_lines).classes("w-full h-64")
        orchestrator.add_log_subscriber(self._on_line)

    def follow(self, run) -> None:
        """Follow ``run`` (a Run row, or None): show its log file
        content, then the live lines of that run only."""
        self.selected_run_id = run["id"] if run is not None else None
        self.log.clear()
        if run is not None and run["log_path"]:
            path = Path(run["log_path"])
            if path.exists():
                for line in path.read_text(encoding="utf-8",
                                           errors="replace").splitlines():
                    self.log.push(line)

    def _on_line(self, task_id: int, run_id, line: str) -> None:
        """Live lines (D2.2) for the followed run only."""
        if run_id is not None and run_id == self.selected_run_id:
            self.log.push(line)

    def close(self) -> None:
        """Unregister the subscriber (call on client disconnect)."""
        self.orchestrator.remove_log_subscriber(self._on_line)
