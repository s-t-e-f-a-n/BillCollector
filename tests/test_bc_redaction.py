# -*- coding: utf-8 -*-
"""Retention-policy tests for DOM evidence and step failures.

The page is synthetic and all persistence uses a temporary SQLite database.
No browser profile, vault, portal, or shared state is involved.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

import BillCollectorServices_pw as legacy  # noqa: E402
from billcollector import runner  # noqa: E402
from billcollector.db import Database  # noqa: E402
from billcollector.pagestate import PageState  # noqa: E402
from billcollector.redaction import failure_record, sanitize_url  # noqa: E402


SECRET = "synthetic-password-never-store"
SIGNED_URL = "https://portal.invalid/invoices/a.pdf?token=synthetic-secret#download"


class SyntheticPage:
    """Minimal local page whose filled password is visible to the DOM scan."""

    url = SIGNED_URL

    def __init__(self):
        self.elements = [
            {
                "tag": "input",
                "innerText": "",
                "computedText": "",
                "ariaLabel": "",
                "title": "",
                "placeholder": "",
                "id": "password",
                "onclick": "",
                "contenteditable": False,
                "href": "",
                "value": SECRET,
                "labelText": "",
                "rect": {"x": 10, "y": 20, "w": 180, "h": 24},
            },
            {
                "tag": "a",
                "innerText": "Invoice",
                "computedText": "Invoice",
                "ariaLabel": "",
                "title": "",
                "placeholder": "",
                "id": "invoice",
                "onclick": "",
                "contenteditable": False,
                "href": SIGNED_URL,
                "value": "",
                "labelText": "",
                "rect": {"x": 10, "y": 60, "w": 80, "h": 24},
            },
        ]

    def evaluate(self, script):
        if "MutationObserver" in script:
            return True
        return self.elements

    def fill(self, value):
        raise RuntimeError(f"portal rejected credential {value}")


class RetentionHelpersTests(unittest.TestCase):
    def test_url_retains_only_scheme_host_and_path(self):
        self.assertEqual(
            sanitize_url(SIGNED_URL),
            "https://portal.invalid/invoices/a.pdf",
        )
        self.assertEqual(
            sanitize_url("https://user:password@portal.invalid:8443/a?secret=1"),
            "https://portal.invalid:8443/a",
        )
        self.assertEqual(sanitize_url("javascript:synthetic-secret"), "javascript:")
        self.assertEqual(sanitize_url("http://[invalid"), "")

    def test_failure_records_use_only_fixed_categories(self):
        cases = [
            ("click", RuntimeError("strict mode violation: " + SECRET), "strict-mode"),
            ("fill", TimeoutError("timed out: " + SECRET), "timeout"),
            ("goto", RuntimeError("net::ERR_FAILED " + SECRET), "navigation"),
            ("expect_download", RuntimeError(SECRET), "download"),
            ("fill", RuntimeError(SECRET), "other"),
        ]
        for method, error, expected in cases:
            with self.subTest(expected):
                record = failure_record(method, error)
                self.assertEqual(record, {"method": method, "category": expected})
                self.assertNotIn(SECRET, json.dumps(record))


class PageStateRetentionTests(unittest.TestCase):
    def setUp(self):
        self.page = SyntheticPage()
        self.state = PageState("synthetic", 1, self.page)

    def test_filled_unlabelled_password_is_not_captured(self):
        serialized = json.dumps(self.state.interactive_elements)
        self.assertNotIn(SECRET, serialized)

        role_only = [
            entry for entry in self.state.interactive_elements
            if entry["role"] == "textbox"
        ]
        self.assertEqual(len(role_only), 1)
        self.assertEqual(role_only[0]["name"], "textbox")
        self.assertEqual(
            role_only[0]["locator"],
            {"locatorType": "get_by_role", "arguments": {"role": "textbox"}},
        )

    def test_link_url_is_redacted_before_sqlite_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            try:
                task_id = db.create_task("synthetic", "u1")
                run_id = db.create_run(task_id)
                db.insert_page_status(
                    run_id,
                    self.state.step_number,
                    interactive_elements=self.state.interactive_elements,
                )
                row = db.list_page_status(run_id)[0]
                self.assertNotIn("token=", row["interactive_elements"])
                self.assertNotIn("#download", row["interactive_elements"])
                self.assertIn(
                    "https://portal.invalid/invoices/a.pdf",
                    row["interactive_elements"],
                )
            finally:
                db.close()


class StepFailureRetentionTests(unittest.TestCase):
    STEP = {
        "step": 9,
        "description": "Synthetic credential failure",
        "graceful": True,
        "methods": [{"method": "fill", "arguments": [{"value": "{{PASSWORD}}"}]}],
    }
    EXPECTED = {"error": [{"method": "fill", "category": "other"}]}

    @staticmethod
    def _service():
        return SimpleNamespace(
            service="synthetic",
            usr="u1",
            pwd=SECRET,
            otp=None,
            page=SyntheticPage(),
        )

    def _assert_safe_failure(self, process_step, logger_name):
        with self.assertLogs(logger_name, level="WARNING") as captured:
            state = process_step(self._service(), self.STEP)
        evidence = json.dumps(state.error_status) + "\n" + "\n".join(captured.output)
        self.assertEqual(state.error_status, self.EXPECTED)
        self.assertNotIn(SECRET, evidence)
        self.assertNotIn("portal rejected", evidence)
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            try:
                task_id = db.create_task("synthetic", "u1")
                run_id = db.create_run(task_id)
                db.insert_page_status(
                    run_id,
                    state.step_number,
                    error=state.error_status,
                )
                stored_error = db.list_page_status(run_id)[0]["error"]
                self.assertEqual(json.loads(stored_error), self.EXPECTED)
                self.assertNotIn(SECRET, stored_error)
            finally:
                db.close()

    def test_daemon_runner_stores_and_logs_only_fixed_failure_category(self):
        self._assert_safe_failure(runner._process_step, "billcollector.runner")

    def test_legacy_runner_stores_and_logs_only_fixed_failure_category(self):
        self._assert_safe_failure(legacy.process_step, "BillCollectorServices_pw")


if __name__ == "__main__":
    unittest.main()
