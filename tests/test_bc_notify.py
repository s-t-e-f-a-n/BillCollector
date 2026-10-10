# -*- coding: utf-8 -*-
"""Unit tests for the ntfy pause push (decision 13, M1 chunk C5.6).

No network: ``requests.post`` is stubbed and the ntfy host is pinned via
the NTFY_HOST env var.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

import requests  # noqa: E402

from billcollector import notify  # noqa: E402
from billcollector.db import Database  # noqa: E402


class NotifyPauseTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.db = Database(self.tmp / "test.db")
        task_id = self.db.create_task("svc", "u1")
        self.run_id = self.db.create_run(task_id)
        self.task = self.db.get_task(task_id)
        self.run = self.db.get_run(self.run_id)
        self.db.set_setting("ntfy_topic", "bc-topic")
        self.db.set_setting("ui_base_url", "http://ui.example:8000")

    def tearDown(self):
        self.db.close()
        self._tmp.cleanup()

    def _ok_response(self):
        return mock.Mock(status_code=200)

    def test_no_topic_skips_the_push(self):
        self.db.set_setting("ntfy_topic", "")
        with mock.patch.object(notify.requests, "post") as post:
            self.assertFalse(notify.notify_pause(self.db, self.run, self.task))
        post.assert_not_called()

    def test_push_carries_the_deep_link(self):
        self.db.update_run(self.run_id, pause_prompt="Type the code")
        self.run = self.db.get_run(self.run_id)
        with mock.patch.dict(os.environ, {"NTFY_HOST": "https://ntfy.test"}), \
                mock.patch.object(notify.requests, "post",
                                  return_value=self._ok_response()) as post:
            self.assertTrue(notify.notify_pause(self.db, self.run, self.task))
        post.assert_called_once()
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://ntfy.test/bc-topic")
        message = kwargs["data"].decode("utf-8")
        self.assertEqual(
            message,
            f"Type the code\nhttp://ui.example:8000/runs/{self.run_id}")
        self.assertEqual(kwargs["headers"]["Title"],
                         "BillCollector: svc u1 needs attention")
        self.assertEqual(kwargs["headers"]["Priority"], "4")
        self.assertEqual(kwargs["headers"]["Tags"], "bell")
        self.assertEqual(kwargs["timeout"], notify.NTFY_TIMEOUT)

    def test_push_without_ui_base_url_uses_a_relative_link(self):
        self.db.set_setting("ui_base_url", "")
        self.db.update_run(self.run_id, pause_prompt="p")
        self.run = self.db.get_run(self.run_id)
        with mock.patch.dict(os.environ, {"NTFY_HOST": "https://ntfy.test"}), \
                mock.patch.object(notify.requests, "post",
                                  return_value=self._ok_response()) as post:
            self.assertTrue(notify.notify_pause(self.db, self.run, self.task))
        message = post.call_args.kwargs["data"].decode("utf-8")
        self.assertEqual(message, f"p\n/runs/{self.run_id}")

    def test_push_without_prompt_falls_back_to_a_generic_banner(self):
        with mock.patch.dict(os.environ, {"NTFY_HOST": "https://ntfy.test"}), \
                mock.patch.object(notify.requests, "post",
                                  return_value=self._ok_response()) as post:
            self.assertTrue(notify.notify_pause(self.db, self.run, self.task))
        message = post.call_args.kwargs["data"].decode("utf-8")
        self.assertTrue(message.startswith(f"Run {self.run_id} paused\n"))

    def test_http_failure_returns_false(self):
        with mock.patch.dict(os.environ, {"NTFY_HOST": "https://ntfy.test"}), \
                mock.patch.object(notify.requests, "post",
                                  return_value=mock.Mock(status_code=500)):
            self.assertFalse(notify.notify_pause(self.db, self.run, self.task))

    def test_transport_error_is_swallowed(self):
        # A failed push is logged and never affects the run.
        with mock.patch.dict(os.environ, {"NTFY_HOST": "https://ntfy.test"}), \
                mock.patch.object(notify.requests, "post",
                                  side_effect=requests.exceptions.ConnectionError("boom")):
            self.assertFalse(notify.notify_pause(self.db, self.run, self.task))


if __name__ == "__main__":
    unittest.main()
