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
from billcollector.redaction import (  # noqa: E402
    failure_category,
    failure_record,
    sanitize_url,
)


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

    def test_url_strips_path_parameters(self):
        self.assertEqual(
            sanitize_url(
                "https://portal.invalid/invoice.do;jsessionid=ABC/"
                "view;tracking=SECRET?token=synthetic-secret"
            ),
            "https://portal.invalid/invoice.do/view",
        )

    def test_nested_blob_and_filesystem_urls_keep_the_sanitized_inner_url(self):
        self.assertEqual(
            sanitize_url("blob:https://p.example/1b2c?token=synthetic-secret"),
            "blob:https://p.example/1b2c",
        )
        self.assertEqual(
            sanitize_url(
                "filesystem:https://p.example/temporary/a;session=SECRET?x=1"
            ),
            "filesystem:https://p.example/temporary/a",
        )

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

    def test_failure_category_uses_exception_type_before_text(self):
        cases = [
            ("click", TimeoutError(SECRET), "timeout"),
            ("wait_for_timeout", TypeError("timed out " + SECRET), "other"),
            (
                "click",
                AttributeError("Method 'expect_navigation' not found " + SECRET),
                "other",
            ),
            ("goto", RuntimeError("net::ERR_FAILED " + SECRET), "navigation"),
        ]
        for method, error, expected in cases:
            with self.subTest(method=method, error_type=type(error).__name__):
                self.assertEqual(failure_category(method, error), expected)

    def test_strict_mode_record_keeps_only_the_resolved_count(self):
        error = RuntimeError(
            'strict mode violation: get_by_role("button") resolved to 3 elements: '
            f'- locator resolved to <input value="{SECRET}">'
        )
        record = failure_record("click", error)
        self.assertEqual(
            record,
            {"method": "click", "category": "strict-mode", "resolved_count": 3},
        )
        self.assertNotIn(SECRET, json.dumps(record))

    def test_strict_mode_without_the_count_pattern_has_no_resolved_count(self):
        record = failure_record("click", RuntimeError("strict mode violation: " + SECRET))
        self.assertEqual(record, {"method": "click", "category": "strict-mode"})

    def test_non_strict_mode_record_has_no_resolved_count(self):
        record = failure_record("fill", TimeoutError("timed out after 30000 ms"))
        self.assertEqual(record, {"method": "fill", "category": "timeout"})


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

    def test_role_only_fallback_is_limited_to_textboxes(self):
        page = SyntheticPage()
        page.elements = [
            {
                "tag": "input", "inputType": "text", "innerText": "",
                "computedText": "", "ariaLabel": "", "title": "",
                "placeholder": "", "id": "first", "onclick": "",
                "contenteditable": False, "href": "", "value": "",
                "labelText": "", "rect": {"x": 0, "y": 0, "w": 1, "h": 1},
            },
            {
                "tag": "textarea", "inputType": "", "innerText": "",
                "computedText": "", "ariaLabel": "", "title": "",
                "placeholder": "", "id": "second", "onclick": "",
                "contenteditable": False, "href": "", "value": "",
                "labelText": "", "rect": {"x": 0, "y": 0, "w": 1, "h": 1},
            },
            {
                "tag": "button", "inputType": "", "innerText": "",
                "computedText": "", "ariaLabel": "", "title": "",
                "placeholder": "", "id": "icon", "onclick": "",
                "contenteditable": False, "href": "", "value": "",
                "labelText": "", "rect": {"x": 0, "y": 0, "w": 1, "h": 1},
            },
        ]

        entries = PageState("synthetic", 2, page).interactive_elements
        role_only = [
            entry for entry in entries
            if entry["locator"]["locatorType"] == "get_by_role"
            and "name" not in entry["locator"]["arguments"]
        ]
        self.assertEqual(len(role_only), 1)
        self.assertEqual(role_only[0]["locator"]["arguments"], {"role": "textbox"})
        self.assertFalse(any(entry["role"] == "button" for entry in role_only))

    def test_submit_value_is_retained_but_password_value_is_not(self):
        page = SyntheticPage()
        page.elements = [
            {
                "tag": "input", "inputType": "submit", "innerText": "",
                "computedText": "", "ariaLabel": "", "title": "",
                "placeholder": "", "id": "login", "onclick": "",
                "contenteditable": False, "href": "", "value": "Anmelden",
                "labelText": "", "rect": {"x": 0, "y": 0, "w": 1, "h": 1},
            },
            {
                "tag": "input", "inputType": "password", "innerText": "",
                "computedText": "", "ariaLabel": "", "title": "",
                "placeholder": "", "id": "password", "onclick": "",
                "contenteditable": False, "href": "", "value": SECRET,
                "labelText": "", "rect": {"x": 0, "y": 0, "w": 1, "h": 1},
            },
        ]

        entries = PageState("synthetic", 3, page).interactive_elements
        serialized = json.dumps(entries)
        self.assertIn("Anmelden", serialized)
        self.assertNotIn(SECRET, serialized)
        self.assertTrue(any(
            entry["role"] == "button" and entry["name"] == "Anmelden"
            for entry in entries
        ))

    def test_id_is_retained_as_additive_metadata_only_when_present(self):
        page = SyntheticPage()
        page.elements = [
            {
                "tag": "input", "inputType": "text", "innerText": "",
                "computedText": "", "ariaLabel": "User", "title": "",
                "placeholder": "", "id": "user", "onclick": "",
                "contenteditable": False, "href": "", "value": "",
                "labelText": "", "rect": {"x": 0, "y": 0, "w": 1, "h": 1},
            },
            {
                "tag": "input", "inputType": "text", "innerText": "",
                "computedText": "", "ariaLabel": "Code", "title": "",
                "placeholder": "", "id": "", "onclick": "",
                "contenteditable": False, "href": "", "value": "",
                "labelText": "", "rect": {"x": 0, "y": 5, "w": 1, "h": 1},
            },
        ]

        entries = PageState("synthetic", 5, page).interactive_elements
        with_id = [e for e in entries if e["name"] == "User"]
        without_id = [e for e in entries if e["name"] == "Code"]
        self.assertTrue(with_id)
        self.assertTrue(without_id)
        self.assertTrue(all(e.get("id") == "user" for e in with_id))
        self.assertTrue(all("id" not in e for e in without_id))
        for entry in entries:
            self.assertEqual(
                list(entry)[:5],
                ["role", "name", "locator", "rect", "actionTypes"],
            )


class BrowserDomScanRetentionTests(unittest.TestCase):
    """Run the real DOM scan script in Chromium against a local page."""

    def test_browser_scan_reads_button_values_but_not_filled_inputs(self):
        try:
            from playwright.sync_api import sync_playwright
            playwright = sync_playwright().start()
        except Exception as e:  # pragma: no cover - depends on local browser
            self.skipTest(f"Playwright unavailable: {type(e).__name__}")
        try:
            try:
                browser = playwright.chromium.launch()
            except Exception as e:  # pragma: no cover - depends on local browser
                self.skipTest(f"Chromium unavailable: {type(e).__name__}")
            try:
                page = browser.new_page()
                page.set_content(
                    '<input type="password" id="pw">'
                    '<input type="text" id="user">'
                    '<textarea id="note"></textarea>'
                    '<input type="submit" value="Anmelden">'
                )
                page.fill("#pw", SECRET)
                page.fill("#user", SECRET + "-user")
                page.fill("#note", SECRET + "-note")

                entries = PageState("synthetic", 4, page).interactive_elements
            finally:
                browser.close()
        finally:
            playwright.stop()

        serialized = json.dumps(entries)
        self.assertNotIn(SECRET, serialized)
        self.assertTrue(any(
            entry["role"] == "button" and entry["name"] == "Anmelden"
            for entry in entries
        ))


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
