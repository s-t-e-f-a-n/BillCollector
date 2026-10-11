# -*- coding: utf-8 -*-
"""Unit tests for the serve lifecycle hooks (M1 chunk C7.5).

``build_lifecycle`` returns the startup/shutdown hooks ``serve``
registers: on startup the orchestrator's orphan cleanup runs before the
scheduler starts, and on shutdown the scheduler stops before the
orchestrator terminates the live runners (see the orchestrator/scheduler
module docstrings for why the shutdown order matters)."""

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector.ui import app as ui_app  # noqa: E402


class BuildLifecycleTests(unittest.TestCase):
    def test_startup_runs_the_orphan_cleanup_before_the_scheduler_starts(self):
        calls = []

        class FakeOrchestrator:
            def cleanup_orphans(self):
                calls.append("cleanup")
                return 0

        class FakeScheduler:
            def start(self):
                calls.append("scheduler_start")

        startup, _ = ui_app.build_lifecycle(None, FakeOrchestrator(),
                                            FakeScheduler())
        startup()
        self.assertEqual(calls, ["cleanup", "scheduler_start"])

    def test_shutdown_stops_the_scheduler_before_terminating_the_runners(self):
        calls = []

        class FakeOrchestrator:
            async def shutdown(self):
                calls.append("orchestrator_shutdown")

        class FakeScheduler:
            def stop(self):
                calls.append("scheduler_stop")

        _, shutdown = ui_app.build_lifecycle(None, FakeOrchestrator(),
                                             FakeScheduler())
        asyncio.run(shutdown())
        self.assertEqual(calls, ["scheduler_stop", "orchestrator_shutdown"])


if __name__ == "__main__":
    unittest.main()
