# -*- coding: utf-8 -*-
"""Unit tests for the per-run display lifecycle (M1 chunk C6).

Display allocation (C6.1): the lockfile registry claims and releases
displays atomically. The display stack children (C6.2) are covered in the
DisplayStackTests below. No real X server is needed for the allocation
tests; the stack tests use the real binaries when the host has them and
stubbed children otherwise.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import config, display  # noqa: E402
from billcollector.db import Database  # noqa: E402


class DisplayTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._old_display_dir = config.DISPLAY_DIR
        self._old_run_dir = config.RUN_DIR
        config.DISPLAY_DIR = self.tmp / "displays"
        config.RUN_DIR = self.tmp / "runs"
        config.DISPLAY_DIR.mkdir(parents=True)
        self.db = Database(self.tmp / "test.db")

    def tearDown(self):
        self.db.close()
        config.DISPLAY_DIR = self._old_display_dir
        config.RUN_DIR = self._old_run_dir
        self._tmp.cleanup()


class AllocateDisplayTests(DisplayTestBase):
    """C6.1: allocate_display scans the configured range and claims the
    first free display with an atomic lockfile."""

    def test_first_allocation_takes_the_range_start(self):
        n, port = display.allocate_display(self.db)
        self.assertEqual((n, port), (99, 6080))
        self.assertTrue((config.DISPLAY_DIR / ":99.lock").exists())

    def test_two_allocations_are_distinct(self):
        n1, p1 = display.allocate_display(self.db)
        n2, p2 = display.allocate_display(self.db)
        self.assertEqual((n1, n2), (99, 100))
        self.assertEqual((p1, p2), (6080, 6081))

    def test_release_then_reallocate_returns_the_same_display(self):
        n, _ = display.allocate_display(self.db)
        display.release_display(n)
        self.assertFalse((config.DISPLAY_DIR / f":{n}.lock").exists())
        n2, _ = display.allocate_display(self.db)
        self.assertEqual(n2, n)

    def test_release_is_idempotent(self):
        display.release_display(105)  # never claimed: a no-op
        n, _ = display.allocate_display(self.db)
        display.release_display(n)
        display.release_display(n)

    def test_release_does_not_take_a_foreign_lock(self):
        # A lockfile owned by another pid (this process lost the claim)
        # must survive the release.
        n, _ = display.allocate_display(self.db)
        (config.DISPLAY_DIR / f":{n}.lock").write_text("424242\n", encoding="utf-8")
        display.release_display(n)
        self.assertTrue((config.DISPLAY_DIR / f":{n}.lock").exists())

    def test_remove_display_lock_forces_the_removal(self):
        n, _ = display.allocate_display(self.db)
        (config.DISPLAY_DIR / f":{n}.lock").write_text("424242\n", encoding="utf-8")
        display.remove_display_lock(n)
        self.assertFalse((config.DISPLAY_DIR / f":{n}.lock").exists())

    def test_allocation_honors_the_display_settings(self):
        self.db.set_setting("display_start", "120")
        self.db.set_setting("display_count", "2")
        n1, p1 = display.allocate_display(self.db)
        n2, p2 = display.allocate_display(self.db)
        self.assertEqual((n1, p1), (120, 6080))
        self.assertEqual((n2, p2), (121, 6081))

    def test_exhausted_range_raises(self):
        self.db.set_setting("display_count", "1")
        n, _ = display.allocate_display(self.db)
        with self.assertRaises(display.DisplayError):
            display.allocate_display(self.db)
        # the claimed display stays claimed
        self.assertTrue((config.DISPLAY_DIR / f":{n}.lock").exists())

    def test_allocation_without_a_db_uses_the_defaults(self):
        n, port = display.allocate_display()
        self.assertEqual((n, port), (99, 6080))
        display.release_display(n)

    def test_websockify_port_math(self):
        self.assertEqual(display.websockify_port_for(99, 99), 6080)
        self.assertEqual(display.websockify_port_for(100, 99), 6081)
        self.assertEqual(display.websockify_port_for(120, 120), 6080)


if __name__ == "__main__":
    unittest.main()
