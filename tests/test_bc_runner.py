# -*- coding: utf-8 -*-
"""Unit tests for the runner's retry/graceful decision logic (no vault, no browser)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector.runner import (  # noqa: E402
    MAX_STEP_ATTEMPTS,
    run_result,
    step_attempts,
)


class RetryDecisionTests(unittest.TestCase):
    def test_graceful_steps_are_single_attempt(self):
        self.assertEqual(step_attempts(True), 1)

    def test_non_graceful_steps_retry_up_to_three_times(self):
        self.assertEqual(MAX_STEP_ATTEMPTS, 3)
        self.assertEqual(step_attempts(False), MAX_STEP_ATTEMPTS)


class RunResultTests(unittest.TestCase):
    def test_aborted_run_is_failure(self):
        self.assertEqual(run_result(True, [{"result": "success"}]), "failure")

    def test_completed_run_without_downloads_is_failure(self):
        # Legacy success contract: success needs at least one download.
        self.assertEqual(run_result(False, []), "failure")

    def test_run_with_a_failed_download_is_failure(self):
        files = [{"result": "success"},
                 {"result": "failure: download error boom"}]
        self.assertEqual(run_result(False, files), "failure")

    def test_completed_run_with_successful_downloads_is_success(self):
        files = [{"result": "success"}, {"result": "success"}]
        self.assertEqual(run_result(False, files), "success")


if __name__ == "__main__":
    unittest.main()
