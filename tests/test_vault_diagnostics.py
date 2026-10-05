"""Vault diagnostics tests using synthetic data and mocked requests only."""

import importlib
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))
collector = importlib.import_module("BillCollector")


class VaultDiagnosticsTests(unittest.TestCase):
    marker = "SYNTHETIC_SENSITIVE_VALUE"
    url = "http://127.0.0.1:8087/object/item/SYNTHETIC_SENSITIVE_VALUE"

    def mock_request(self, **kwargs):
        # Also exercise the same diagnostics after the focused transport PR lands.
        if hasattr(collector, "vault_http_request"):
            return patch.object(collector, "vault_http_request", **kwargs)
        return patch.object(collector.requests, "request", **kwargs)

    def expected_call(self, method, payload):
        if hasattr(collector, "vault_http_request"):
            return call(method, self.url, payload, 10)
        return call(method, self.url, json=payload, timeout=10)

    def response(self, status, body=None):
        return SimpleNamespace(status_code=status, text=body or self.marker)

    def assert_safe(self, logs, error=None):
        diagnostic = "\n".join(logs.output)
        if error is not None:
            diagnostic += "\n" + str(error)
        self.assertNotIn(self.marker, diagnostic)
        self.assertNotIn(self.url, diagnostic)
        return diagnostic

    def test_final_4xx_retains_status_without_response_body(self):
        for status in (400, 401, 403, 404, 429):
            with self.subTest(status=status), \
                    self.mock_request( return_value=self.response(status)) as request, \
                    patch.object(collector.time, "sleep") as sleep, \
                    self.assertLogs(collector.logger, level="DEBUG") as logs:
                with self.assertRaises(SystemExit) as exit_result:
                    collector.get_json(self.url)
                self.assertEqual(exit_result.exception.code, 1)
                self.assertIn(str(status), self.assert_safe(logs))
                self.assertEqual(request.call_args_list, [self.expected_call("GET", None)])
                sleep.assert_not_called()
            with self.mock_request( return_value=self.response(status)):
                with self.assertRaises(collector.VaultAPIError) as error:
                    collector.vault_request("GET", self.url)
                self.assertEqual(error.exception.status, status)
                self.assertNotIn(self.marker, str(error.exception))

    def test_5xx_retries_without_response_body_or_url(self):
        with self.mock_request( return_value=self.response(503)) as request, \
                patch.object(collector.time, "sleep") as sleep, \
                self.assertLogs(collector.logger, level="DEBUG") as logs:
            with self.assertRaises(collector.VaultAPIError) as error:
                collector.vault_request("GET", self.url)
            diagnostic = self.assert_safe(logs, error.exception)
            self.assertIn("server error 503", diagnostic)
            self.assertIn("Attempt 3/3", diagnostic)
            self.assertIn("after 3 attempts", diagnostic)
            self.assertEqual(request.call_args_list, [self.expected_call("GET", None)] * 3)
            self.assertEqual(sleep.call_args_list, [call(2), call(4)])

    def test_network_errors_do_not_log_raw_exception(self):
        for exception_type in (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                               requests.exceptions.RequestException):
            with self.subTest(exception=exception_type.__name__), \
                    self.mock_request( side_effect=exception_type(self.url)) as request, \
                    patch.object(collector.time, "sleep") as sleep, \
                    self.assertLogs(collector.logger, level="DEBUG") as logs:
                with self.assertRaises(collector.VaultAPIError) as error:
                    collector.vault_request("GET", self.url)
                self.assertIn("network error", self.assert_safe(logs, error.exception))
                self.assertEqual(request.call_count, 3)
                self.assertEqual(sleep.call_args_list, [call(2), call(4)])

    def test_transient_failures_recover_with_same_payload_and_timeout(self):
        success = self.response(200)
        payload = {"synthetic": self.marker}
        with self.mock_request( side_effect=[
                requests.exceptions.Timeout(self.marker), self.response(502), success]) as request, \
                patch.object(collector.time, "sleep") as sleep, \
                self.assertLogs(collector.logger, level="DEBUG") as logs:
            self.assertIs(collector.vault_request("POST", self.url, payload), success)
            self.assert_safe(logs)
            self.assertEqual(request.call_args_list, [self.expected_call("POST", payload)] * 3)
            self.assertEqual(sleep.call_args_list, [call(2), call(4)])

    def test_expected_no_totp_still_returns_none(self):
        with self.mock_request( return_value=self.response(400)) as request, \
                patch.object(collector.time, "sleep") as sleep, \
                self.assertLogs(collector.logger, level="DEBUG") as logs:
            self.assertIsNone(collector.get_totp(self.url))
            self.assertIn("No TOTP", self.assert_safe(logs))
            self.assertEqual(request.call_count, 1)
            sleep.assert_not_called()

    def test_other_totp_errors_still_exit_one(self):
        with self.mock_request( return_value=self.response(403)), \
                self.assertLogs(collector.logger, level="DEBUG") as logs:
            with self.assertRaises(SystemExit) as exit_result:
                collector.get_totp(self.url)
            self.assertEqual(exit_result.exception.code, 1)
            self.assertIn("403", self.assert_safe(logs))

    def test_status_check_does_not_dump_successful_body_at_debug_level(self):
        body = json.dumps({"success": True, "data": {"template": {"status": "unlocked"}},
                           "synthetic": self.marker})
        with self.mock_request( return_value=self.response(200, body)), \
                self.assertLogs(collector.logger, level="DEBUG") as logs:
            self.assertEqual(collector.bitwarden_api_check_status(self.url), (True, "unlocked"))
            self.assert_safe(logs)

    def test_post_errors_and_unexpected_success_status_are_safe(self):
        for status in (403, 202):
            with self.subTest(status=status), \
                    self.mock_request( return_value=self.response(status)), \
                    self.assertLogs(collector.logger, level="DEBUG") as logs:
                self.assertFalse(collector.post_json(self.url, {"synthetic": self.marker}))
                self.assertIn(str(status), self.assert_safe(logs))

    def test_successful_get_and_post_still_return_payload(self):
        body = {"success": True, "synthetic": self.marker}
        response = self.response(200, json.dumps(body))
        response.json = lambda: body
        with self.mock_request( return_value=response):
            self.assertEqual(json.loads(collector.get_json(self.url)), body)
            with self.assertLogs(collector.logger, level="DEBUG") as logs:
                self.assertEqual(json.loads(collector.post_json(self.url, body)), body)
                self.assert_safe(logs)


if __name__ == "__main__":
    unittest.main()
