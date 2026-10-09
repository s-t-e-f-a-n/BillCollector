"""Vault diagnostics tests using synthetic data and mocked requests only."""

import importlib
import io
import logging
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))
vault = importlib.import_module("billcollector.vault")
collector = importlib.import_module("BillCollector")


class VaultDiagnosticsTests(unittest.TestCase):
    marker = "SYNTHETIC_SENSITIVE_VALUE"
    url = "http://127.0.0.1:8087/object/item/SYNTHETIC_SENSITIVE_VALUE"

    def mock_request(self, **kwargs):
        # The vault client routes every request through vault_http_request
        # (transport PR #13); patch it where the client resolves the name.
        return patch.object(vault, "vault_http_request", **kwargs)

    def expected_call(self, method, payload):
        return call(method, self.url, payload, vault.VAULT_TIMEOUT)

    def response(self, status, body=None):
        return SimpleNamespace(status_code=status, text=body or self.marker)

    def assert_safe(self, logs, error=None):
        diagnostic = "\n".join(logs.output)
        if error is not None:
            diagnostic += "\n" + str(error)
        self.assertNotIn(self.marker, diagnostic)
        self.assertNotIn(self.url, diagnostic)
        return diagnostic

    def test_real_http_dependency_logs_are_private_in_both_console_modes(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
            def log_message(self, *args):
                pass

        helpers = importlib.import_module("helpers.BillCollectorHelpers")
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for debug in (False, True):
                with self.subTest(debug=debug), tempfile.TemporaryDirectory() as directory:
                    root = logging.getLogger()
                    handlers, level = root.handlers[:], root.level
                    dependency = [logging.getLogger("urllib3")]
                    levels = [logger.level for logger in dependency]
                    root.handlers = []
                    console = io.StringIO()
                    logfile = Path(directory) / "bc.log"
                    try:
                        with patch.object(sys, "stdout", console):
                            helpers.setup_logging(str(logfile), debug=debug)
                            url = f"http://127.0.0.1:{server.server_port}/object/item/{self.marker}"
                            response = vault.vault_request("GET", url)
                            self.assertEqual(response.status_code, 200)
                            logging.getLogger("synthetic.application").info("safe application event")
                        for handler in root.handlers:
                            handler.flush()
                        for output in (console.getvalue(), logfile.read_text()):
                            self.assertNotIn(self.marker, output)
                            self.assertNotIn(url, output)
                            self.assertIn("safe application event", output)
                    finally:
                        for handler in root.handlers:
                            handler.close()
                        root.handlers = handlers
                        root.setLevel(level)
                        for logger, old_level in zip(dependency, levels):
                            logger.setLevel(old_level)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_final_4xx_retains_status_without_response_body(self):
        for status in (400, 401, 403, 404, 429):
            with self.subTest(status=status), \
                    self.mock_request( return_value=self.response(status)) as request, \
                    patch.object(vault.time, "sleep") as sleep, \
                    self.assertLogs(vault.logger, level="DEBUG") as logs:
                with self.assertRaises(vault.VaultAPIError) as error:
                    vault.get_json(self.url)
                self.assertEqual(error.exception.status, status)
                self.assertIn(str(status), self.assert_safe(logs))
                self.assertEqual(request.call_args_list, [self.expected_call("GET", None)])
                sleep.assert_not_called()
            with self.mock_request( return_value=self.response(status)):
                with self.assertRaises(vault.VaultAPIError) as error:
                    vault.vault_request("GET", self.url)
                self.assertEqual(error.exception.status, status)
                self.assertNotIn(self.marker, str(error.exception))

    def test_5xx_retries_without_response_body_or_url(self):
        with self.mock_request( return_value=self.response(503)) as request, \
                patch.object(vault.time, "sleep") as sleep, \
                self.assertLogs(vault.logger, level="DEBUG") as logs:
            with self.assertRaises(vault.VaultAPIError) as error:
                vault.vault_request("GET", self.url)
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
                    patch.object(vault.time, "sleep") as sleep, \
                    self.assertLogs(vault.logger, level="DEBUG") as logs:
                with self.assertRaises(vault.VaultAPIError) as error:
                    vault.vault_request("GET", self.url)
                diagnostic = self.assert_safe(logs, error.exception)
                self.assertIn(f"network error ({exception_type.__name__})", diagnostic)
                self.assertEqual(request.call_count, 3)
                self.assertEqual(sleep.call_args_list, [call(2), call(4)])

    def test_transient_failures_recover_with_same_payload_and_timeout(self):
        success = self.response(200)
        payload = {"synthetic": self.marker}
        with self.mock_request( side_effect=[
                requests.exceptions.Timeout(self.marker), self.response(502), success]) as request, \
                patch.object(vault.time, "sleep") as sleep, \
                self.assertLogs(vault.logger, level="DEBUG") as logs:
            self.assertIs(vault.vault_request("POST", self.url, payload), success)
            self.assert_safe(logs)
            self.assertEqual(request.call_args_list, [self.expected_call("POST", payload)] * 3)
            self.assertEqual(sleep.call_args_list, [call(2), call(4)])

    def test_expected_no_totp_still_returns_none(self):
        with self.mock_request( return_value=self.response(400)) as request, \
                patch.object(vault.time, "sleep") as sleep, \
                self.assertLogs(vault.logger, level="DEBUG") as logs:
            self.assertIsNone(vault.get_totp(self.url))
            self.assertIn("No TOTP", self.assert_safe(logs))
            self.assertEqual(request.call_count, 1)
            sleep.assert_not_called()

    def test_other_totp_errors_raise_with_status(self):
        with self.mock_request( return_value=self.response(403)), \
                self.assertLogs(vault.logger, level="DEBUG") as logs:
            with self.assertRaises(vault.VaultAPIError) as error:
                vault.get_totp(self.url)
            self.assertEqual(error.exception.status, 403)
            self.assertIn("403", self.assert_safe(logs))

    def test_status_check_does_not_dump_successful_body_at_debug_level(self):
        body = json.dumps({"success": True, "data": {"template": {"status": "unlocked"}},
                           "synthetic": self.marker})
        with self.mock_request( return_value=self.response(200, body)), \
                self.assertLogs(vault.logger, level="DEBUG") as logs:
            self.assertEqual(vault.bitwarden_api_check_status(self.url), (True, "unlocked"))
            self.assert_safe(logs)

    def test_locked_or_failed_status_is_logged_before_exit(self):
        config = collector.defs(None, "http://127.0.0.1:8087", fname="unused.ini")
        for result, expected in (((True, "locked"), "Vault API status: locked"),
                                 ((False, None), "Vault API status: check failed")):
            with self.subTest(expected=expected), \
                    patch.object(collector, "is_domain_local_ip", return_value="127.0.0.1", create=True), \
                    patch.object(collector, "pinned_api_url", create=True), \
                    patch.object(collector, "bitwarden_api_check_status", return_value=result), \
                    self.assertLogs(collector.logger, level="ERROR") as logs:
                with self.assertRaises(SystemExit) as exit_result:
                    collector.WebRetriDoc(config, "playwright")
                self.assertEqual(exit_result.exception.code, 1)
                self.assertIn(expected, "\n".join(logs.output))

    def test_post_errors_and_unexpected_success_status_are_safe(self):
        for status in (403, 202):
            with self.subTest(status=status), \
                    self.mock_request( return_value=self.response(status)), \
                    self.assertLogs(vault.logger, level="DEBUG") as logs:
                self.assertFalse(vault.post_json(self.url, {"synthetic": self.marker}))
                self.assertIn(str(status), self.assert_safe(logs))

    def test_successful_get_and_post_still_return_payload(self):
        body = {"success": True, "synthetic": self.marker}
        response = self.response(200, json.dumps(body))
        response.json = lambda: body
        with self.mock_request( return_value=response):
            self.assertEqual(json.loads(vault.get_json(self.url)), body)
            with self.assertLogs(vault.logger, level="DEBUG") as logs:
                self.assertEqual(json.loads(vault.post_json(self.url, body)), body)
                self.assert_safe(logs)


if __name__ == "__main__":
    unittest.main()
