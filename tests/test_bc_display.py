# -*- coding: utf-8 -*-
"""Unit tests for the per-run display lifecycle (M1 chunk C6).

Display allocation (C6.1): the lockfile registry claims and releases
displays atomically. The display stack children (C6.2) are covered in the
DisplayStackTests below. No real X server is needed for the allocation
tests; the stack tests use the real binaries when the host has them and
stubbed children otherwise.
"""

import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

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


def _stub_script(tmp):
    """A stand-in display binary: ignores its arguments and stays alive."""
    import stat

    script = tmp / "stub-bin"
    script.write_text("#!/bin/sh\nsleep 60\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP
                 | stat.S_IXOTH)
    return str(script)


class DisplayStackTests(DisplayTestBase):
    """C6.2: start_display_stack spawns Xvfb + x11vnc + websockify as
    children; stop_display_stack terminates and reaps them. The real
    binaries are used when the host has the whole stack; otherwise the
    children are stubbed with a sleep script."""

    def _stub_binaries(self):
        stub = _stub_script(self.tmp)
        return {"Xvfb": stub, "x11vnc": stub, "websockify": stub}

    def test_stubbed_stack_starts_alive_and_reaps(self):
        with mock.patch.object(display, "_wait_for_x_display"):
            children = display.start_display_stack(
                99, websockify_port=6080, binaries=self._stub_binaries())
        try:
            self.assertEqual(len(children), 3)
            for proc in children:
                self.assertIsNone(proc.poll())
        finally:
            display.stop_display_stack(children)
        for proc in children:
            self.assertIsNotNone(proc.poll())

    def test_default_websockify_port_comes_from_the_range_start(self):
        spawned = []
        real_spawn = display._spawn

        def recording_spawn(binary, *args, env=None):
            spawned.append(args)
            return real_spawn(binary, *args, env=env)

        with mock.patch.object(display, "_wait_for_x_display"), \
                mock.patch.object(display, "_spawn", recording_spawn):
            children = display.start_display_stack(
                99, websockify_port=None, binaries=self._stub_binaries())
            try:
                # the websockify child is the spawn targeting the localhost
                # RFB port; its listen port defaults to 6080 for :99
                ws_args = next(a for a in spawned if "127.0.0.1:5999" in a)
                self.assertIn(6080, ws_args)
            finally:
                display.stop_display_stack(children)

    def test_stack_children_get_a_wayland_free_env(self):
        # WSLg sessions export WAYLAND_DISPLAY and x11vnc refuses to
        # start against it, so no child may inherit the variable.
        spawned = []
        real_spawn = display._spawn

        def recording_spawn(binary, *args, env=None):
            spawned.append((binary, dict(env) if env is not None else None))
            return real_spawn(binary, *args, env=env)

        old = os.environ.get("WAYLAND_DISPLAY")
        os.environ["WAYLAND_DISPLAY"] = "wayland-0"
        try:
            with mock.patch.object(display, "_wait_for_x_display"), \
                    mock.patch.object(display, "_spawn", recording_spawn):
                children = display.start_display_stack(
                    99, websockify_port=6080,
                    binaries=self._stub_binaries())
                try:
                    self.assertEqual(len(spawned), 3)
                    for binary, env in spawned:
                        self.assertIsNotNone(env, str(binary))
                        self.assertNotIn("WAYLAND_DISPLAY", env, str(binary))
                        self.assertEqual(env.get("XDG_SESSION_TYPE"), "x11",
                                         str(binary))
                finally:
                    display.stop_display_stack(children)
        finally:
            if old is None:
                os.environ.pop("WAYLAND_DISPLAY", None)
            else:
                os.environ["WAYLAND_DISPLAY"] = old

    def test_start_rolls_back_when_a_binary_is_missing(self):
        stub = _stub_script(self.tmp)
        spawned = []
        real_spawn = display._spawn

        def recording_spawn(binary, *args, env=None):
            proc = real_spawn(binary, *args, env=env)
            spawned.append(proc)
            return proc

        with mock.patch.object(display, "_wait_for_x_display"), \
                mock.patch.object(display, "_spawn", recording_spawn):
            with self.assertRaises(display.DisplayError):
                display.start_display_stack(
                    99, websockify_port=6080,
                    binaries={"Xvfb": stub, "x11vnc": "/nonexistent/x11vnc",
                              "websockify": stub})
        # the already-started Xvfb stub must have been reaped by the rollback
        self.assertEqual(len(spawned), 1)
        time.sleep(0.2)
        self.assertIsNotNone(spawned[0].poll())

    def test_missing_auth_file_is_rejected_before_any_spawn(self):
        with mock.patch.object(display, "_spawn") as spawn:
            with self.assertRaises(display.DisplayError):
                display.start_display_stack(
                    99, rfb_auth_file=self.tmp / "nope",
                    websockify_port=6080, binaries=self._stub_binaries())
        spawn.assert_not_called()

    def test_rfb_auth_file_path_is_per_run(self):
        path = display.rfb_auth_file_for(7)
        self.assertEqual(path, config.RUN_DIR / "7" / "vnc.rfbauth")

    @unittest.skipUnless(
        display.binaries_present(),
        "display stack binaries not installed on this host")
    def test_real_stack_starts_alive_and_reaps(self):
        # A high display keeps the test away from any real :99 on the host.
        self.db.set_setting("display_start", "120")
        n, port = display.allocate_display(self.db)
        self.assertEqual(n, 120)
        try:
            children = display.start_display_stack(n, websockify_port=port)
        except display.DisplayError:
            self.skipTest("real stack could not start on this host")
        try:
            for proc in children:
                self.assertIsNone(proc.poll())
            self.assertTrue((display.X_SOCKET_DIR / f"X{n}").exists())
        finally:
            display.stop_display_stack(children)
            display.release_display(n)
        for proc in children:
            self.assertIsNotNone(proc.poll())
        self.assertFalse((display.X_SOCKET_DIR / f"X{n}").exists())

    @unittest.skipUnless(
        shutil.which("x11vnc"), "x11vnc not installed on this host")
    def test_write_rfb_auth_creates_the_auth_file(self):
        path = display.rfb_auth_file_for(1)
        display.write_rfb_auth(path, "secret")
        self.assertTrue(path.exists())
        self.assertGreater(path.stat().st_size, 0)

    def test_write_rfb_auth_raises_when_the_binary_is_missing(self):
        with mock.patch.object(
                display.subprocess, "run",
                side_effect=FileNotFoundError("x11vnc")):
            with self.assertRaises(display.DisplayError):
                display.write_rfb_auth(self.tmp / "auth", "secret")
        self.assertFalse((self.tmp / "auth").exists())


if __name__ == "__main__":
    unittest.main()
