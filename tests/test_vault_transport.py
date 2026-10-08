"""Synthetic vault transport checks: all DNS and HTTP operations are mocked."""

import importlib
from contextlib import nullcontext
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import requests
from urllib3.exceptions import MaxRetryError, NewConnectionError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))
transport = importlib.import_module("vault_transport")
collector = importlib.import_module("BillCollector")


def dns(*addresses):
    return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM,
             6, "", (ip, 8087)) for ip in addresses]


class VaultTransportTests(unittest.TestCase):
    url = "http://bw.local:8087/object/item/synthetic"

    def test_local_ranges_and_default_port(self):
        for address in ("127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.0.1", "::1", "fd00::1"):
            with self.subTest(address=address), \
                    patch.object(transport.socket, "getaddrinfo", return_value=dns(address)) as resolve:
                target, host = transport.pinned_api_url("http://bw.local/status")
                numeric = f"[{address}]" if ":" in address else address
                self.assertEqual(target, f"http://{numeric}:80/status")
                self.assertEqual(host, "bw.local")
                resolve.assert_called_once_with("bw.local", 80, type=socket.SOCK_STREAM)

    def test_public_mixed_empty_and_link_local_answers_are_rejected(self):
        for answers in (dns("8.8.8.8"), dns("127.0.0.1", "8.8.8.8"), [], dns("169.254.169.254")):
            with self.subTest(answers=answers), \
                    patch.object(transport.socket, "getaddrinfo", return_value=answers), \
                    patch.object(transport.requests, "Session") as session:
                with self.assertRaises(transport.VaultTransportError):
                    transport.vault_http_request("GET", self.url, None, 10)
                session.assert_not_called()

    def test_unsafe_url_forms_are_rejected_before_dns(self):
        for url in (None, "https://bw.local/status", "http://user:password@bw.local/",
                    "http://bw.local:0/", "http://bw.local:99999/", "http://bw.local/?token=synthetic",
                    "http://bw.local/#synthetic", "file:///synthetic", "not-a-url"):
            with self.subTest(url=url), patch.object(transport.socket, "getaddrinfo") as resolve:
                with self.assertRaises(transport.VaultTransportError):
                    transport.pinned_api_url(url)
                resolve.assert_not_called()

    def test_dns_failure_is_a_bounded_configuration_error(self):
        with patch.object(transport.socket, "getaddrinfo", side_effect=OSError("SYNTHETIC_PRIVATE_MARKER")):
            with self.assertRaises(transport.VaultTransportError) as error:
                transport.pinned_api_url(self.url)
            self.assertNotIn("SYNTHETIC_PRIVATE_MARKER", str(error.exception))

    def test_transient_dns_recovers_in_request_and_preflight(self):
        success = SimpleNamespace(status_code=200)
        for preflight in (False, True):
            with self.subTest(preflight=preflight), \
                    patch.object(transport.socket, "getaddrinfo", side_effect=[
                        socket.gaierror(socket.EAI_AGAIN, "SYNTHETIC_PRIVATE_MARKER"), dns("127.0.0.1")]) as resolve, \
                    patch.object(transport.time, "sleep") as sleep, \
                    patch.object(transport.requests, "Session") as factory, \
                    (self.assertLogs(collector.logger) if not preflight else nullcontext()):
                factory.return_value.__enter__.return_value.request.return_value = success
                if preflight:
                    self.assertEqual(transport.pinned_api_url(self.url)[0], self.url.replace("bw.local", "127.0.0.1"))
                else:
                    self.assertIs(collector.vault_request("GET", self.url), success)
                self.assertEqual(resolve.call_count, 2)
                sleep.assert_called_once_with(2)

    def test_unknown_name_while_sidecar_restarts_is_retried(self):
        success = SimpleNamespace(status_code=200)
        for errno in (socket.EAI_NONAME, socket.EAI_FAIL):
            with self.subTest(errno=errno), \
                    patch.object(transport.socket, "getaddrinfo", side_effect=[
                        socket.gaierror(errno, "SYNTHETIC_PRIVATE_MARKER"), dns("127.0.0.1")]) as resolve, \
                    patch.object(collector.time, "sleep") as sleep, \
                    patch.object(transport.requests, "Session") as factory, self.assertLogs(collector.logger):
                factory.return_value.__enter__.return_value.request.return_value = success
                self.assertIs(collector.vault_request("GET", self.url), success)
                self.assertEqual(resolve.call_count, 2)
                sleep.assert_called_once_with(2)

    def test_preflight_uses_caller_retry_policy(self):
        with patch.object(transport.socket, "getaddrinfo", side_effect=socket.gaierror(socket.EAI_NONAME, "x")) as resolve, \
                patch.object(transport.time, "sleep") as sleep:
            with self.assertRaises(transport.VaultTransportError) as error:
                transport.pinned_api_url(self.url, attempts=4, backoff=3)
            self.assertEqual(resolve.call_count, 4)
            self.assertEqual(sleep.call_args_list, [call(3), call(6), call(9)])
            self.assertIn("after 4 attempts", str(error.exception))

    def test_dns_failure_exhausts_only_three_attempts(self):
        with patch.object(transport.socket, "getaddrinfo", side_effect=socket.gaierror(socket.EAI_AGAIN, "private")) as resolve, \
                patch.object(transport.time, "sleep") as sleep, self.assertLogs(collector.logger):
            with self.assertRaises(collector.VaultAPIError):
                collector.vault_request("GET", self.url)
            self.assertEqual(resolve.call_count, 3)
            self.assertEqual(sleep.call_args_list, [call(2), call(4)])

    def test_connection_falls_back_only_to_validated_addresses(self):
        session = MagicMock()
        session.__enter__.return_value = session
        success = SimpleNamespace(status_code=200)
        session.request.side_effect = [requests.exceptions.ConnectionError(
            MaxRetryError(None, "synthetic", NewConnectionError(None, "connection refused"))), success]
        with patch.dict(os.environ, {"BW_API_HOST": ""}), \
                patch.object(transport.socket, "getaddrinfo", return_value=dns("127.0.0.1", "::1")), \
                patch.object(transport.requests, "Session", return_value=session):
            self.assertIs(transport.vault_http_request("GET", self.url, None, 10), success)
            self.assertEqual([entry.args[1] for entry in session.request.call_args_list],
                             [self.url.replace("bw.local", "127.0.0.1"), self.url.replace("bw.local", "[::1]")])
            # Only the connect budget is shared; the read timeout stays the full per-request value.
            self.assertTrue(all(entry.kwargs["timeout"] == (5, 10) for entry in session.request.call_args_list))

    def test_read_timeout_does_not_replay_on_another_address(self):
        session = MagicMock()
        session.__enter__.return_value = session
        session.request.side_effect = requests.exceptions.ReadTimeout("private")
        with patch.dict(os.environ, {"BW_API_HOST": ""}), \
                patch.object(transport.socket, "getaddrinfo", return_value=dns("127.0.0.1", "::1")), \
                patch.object(transport.requests, "Session", return_value=session):
            with self.assertRaises(requests.exceptions.RequestException):
                transport.vault_http_request("POST", self.url, {}, 10)
            session.request.assert_called_once()

    def test_partial_response_does_not_replay_post_on_another_address(self):
        received = []
        attempts = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append(self.path)
                self.send_response(200)
                self.send_header("Content-Length", "100")
                self.end_headers()
                self.wfile.write(b"x")
                self.wfile.flush()
                time.sleep(0.6)
            def log_message(self, *args):
                pass

        class TracedSession(requests.Session):
            def request(self, *args, **kwargs):
                attempts.append(args[1])
                return super().request(*args, **kwargs)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://synthetic.local:{server.server_port}/sync"
        try:
            with patch.dict(os.environ, {"BW_API_HOST": ""}), \
                    patch.object(transport.requests, "Session", TracedSession):
                # Synthetic DNS answers; numeric connections use the real loopback port.
                def resolve(host, port, *args, **kwargs):
                    family = socket.AF_INET
                    return [(family, socket.SOCK_STREAM, 6, "", (host, port))] if host.startswith("127.") else dns("127.0.0.1", "127.0.0.2")
                with patch.object(transport.socket, "getaddrinfo", side_effect=resolve):
                    with self.assertRaises(requests.exceptions.RequestException):
                        transport.vault_http_request("POST", url, {}, 0.4)
            self.assertEqual(len(attempts), 1)
            self.assertEqual(received, ["/sync"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_invalid_host_encoding_is_refused_before_connection(self):
        with patch.dict(os.environ, {"BW_API_HOST": "vault-☃"}), \
                patch.object(transport.socket, "getaddrinfo", return_value=dns("127.0.0.1")), \
                patch.object(transport.requests, "Session") as factory:
            with self.assertRaises(transport.VaultTransportError):
                transport.vault_http_request("GET", self.url, None, 10)
            factory.assert_not_called()

    def test_connection_is_pinned_with_proxy_and_redirects_disabled(self):
        session = MagicMock()
        session.__enter__.return_value = session
        response = SimpleNamespace(status_code=200)
        session.request.return_value = response
        with patch.dict(os.environ, {"HTTP_PROXY": "http://proxy.invalid", "BW_API_HOST": ""}), \
                patch.object(transport.socket, "getaddrinfo", return_value=dns("192.168.1.2", "127.0.0.1")), \
                patch.object(transport.requests, "Session", return_value=session):
            self.assertIs(transport.vault_http_request("POST", self.url, {"synthetic": True}, 10), response)
            self.assertFalse(session.trust_env)
            session.request.assert_called_once_with(
                "POST", "http://127.0.0.1:8087/object/item/synthetic", json={"synthetic": True},
                timeout=(5, 10), headers={"Host": "bw.local:8087"}, allow_redirects=False)
            session.__exit__.assert_called_once()

    def test_host_override_and_dns_rechecked_for_each_request(self):
        session = MagicMock()
        session.__enter__.return_value = session
        session.request.return_value.status_code = 200
        with patch.dict(os.environ, {"BW_API_HOST": "127.0.0.1:8087"}), \
                patch.object(transport.socket, "getaddrinfo", side_effect=[dns("127.0.0.1"), dns("127.0.0.2")]) as resolve, \
                patch.object(transport.requests, "Session", return_value=session):
            for _ in range(2):
                transport.vault_http_request("GET", self.url, None, 10)
            self.assertEqual(resolve.call_count, 2)
            self.assertEqual([c.args[1] for c in session.request.call_args_list],
                             [self.url.replace("bw.local", "127.0.0.1"), self.url.replace("bw.local", "127.0.0.2")])
            self.assertEqual(session.request.call_args.kwargs["headers"], {"Host": "127.0.0.1:8087"})

    def test_host_header_injection_is_refused(self):
        with patch.dict(os.environ, {"BW_API_HOST": "localhost\r\nX-Fake: synthetic"}), \
                patch.object(transport.socket, "getaddrinfo", return_value=dns("127.0.0.1")), \
                patch.object(transport.requests, "Session") as session:
            with self.assertRaises(transport.VaultTransportError):
                transport.vault_http_request("GET", self.url, None, 10)
            session.assert_not_called()

    def test_redirect_response_is_final_without_retry(self):
        session = MagicMock()
        session.__enter__.return_value = session
        session.request.return_value.status_code = 302
        with patch.dict(os.environ, {"BW_API_HOST": ""}), \
                patch.object(transport.socket, "getaddrinfo", return_value=dns("127.0.0.1")), \
                patch.object(transport.requests, "Session", return_value=session), \
                patch.object(collector.time, "sleep") as sleep:
            with self.assertRaises(collector.VaultAPIError) as error:
                collector.vault_request("GET", self.url)
            self.assertIn("redirects", str(error.exception))
            self.assertEqual(session.request.call_count, 1)
            sleep.assert_not_called()

    def test_network_exception_is_sanitized(self):
        session = MagicMock()
        session.__enter__.return_value = session
        session.request.side_effect = requests.exceptions.Timeout("SYNTHETIC_PRIVATE_MARKER")
        with patch.dict(os.environ, {"BW_API_HOST": ""}), \
                patch.object(transport.socket, "getaddrinfo", return_value=dns("127.0.0.1")), \
                patch.object(transport.requests, "Session", return_value=session):
            with self.assertRaises(requests.exceptions.RequestException) as error:
                transport.vault_http_request("GET", self.url, None, 10)
            self.assertNotIn("SYNTHETIC_PRIVATE_MARKER", str(error.exception))
            self.assertIn("(Timeout)", str(error.exception))
            self.assertIs(type(error.exception), requests.exceptions.Timeout)
            self.assertIsNone(error.exception.__cause__)

    def test_retry_timeout_backoff_and_success_are_preserved(self):
        success = SimpleNamespace(status_code=200, text="synthetic response")
        with patch.object(collector, "vault_http_request", side_effect=[
                requests.exceptions.Timeout("synthetic"), SimpleNamespace(status_code=503, text="synthetic"), success]) as request, \
                patch.object(collector.time, "sleep") as sleep, self.assertLogs(collector.logger):
            self.assertIs(collector.vault_request("GET", self.url), success)
            self.assertEqual(request.call_args_list, [call("GET", self.url, None, 10)] * 3)
            self.assertEqual(sleep.call_args_list, [call(2), call(4)])

    def test_optional_totp_and_final_4xx_are_preserved(self):
        with patch.object(collector, "vault_http_request", return_value=SimpleNamespace(status_code=400, text="synthetic")) as request, \
                patch.object(collector.time, "sleep") as sleep, self.assertLogs(collector.logger):
            self.assertIsNone(collector.get_totp(self.url))
            request.assert_called_once()
            sleep.assert_not_called()
        with patch.object(collector, "vault_http_request", return_value=SimpleNamespace(status_code=403, text="synthetic")):
            with self.assertRaises(collector.VaultAPIError) as error:
                collector.vault_request("GET", self.url)
            self.assertEqual(error.exception.status, 403)

    def test_preflight_checks_api_not_remote_backend(self):
        config = collector.defs("cloud.invalid", self.url, fname="unused.ini")
        with patch.object(collector, "pinned_api_url", side_effect=transport.VaultTransportError("synthetic refusal")) as validate, \
                patch.object(collector, "bitwarden_api_check_status") as status, self.assertLogs(collector.logger):
            with self.assertRaises(SystemExit):
                collector.WebRetriDoc(config, "playwright")
            validate.assert_called_once_with(self.url, collector.VAULT_MAX_ATTEMPTS, collector.VAULT_RETRY_BACKOFF)
            status.assert_not_called()


if __name__ == "__main__":
    unittest.main()
