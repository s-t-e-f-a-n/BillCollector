"""Exact-name vault lookup avoids case-insensitive CLI ambiguity."""
import json
from unittest import mock

import pytest

from billcollector import vault


def response(data):
    return json.dumps({"success": True, "data": data})


def test_case_variants_resolve_exact_id_and_totp_by_id():
    chosen = {"id": "exact-id", "name": "CC Genevois"}
    detail = {**chosen, "login": {"username": "synthetic-user", "password": "synthetic-password",
                                "uris": [{"uri": "https://portal.invalid"}]}}
    with mock.patch.object(vault, "get_json", side_effect=[
            response({"data": [{"id": "other-id", "name": "CC genevois"}, chosen]}),
            response(detail)]) as get, mock.patch.object(vault, "get_totp", return_value=None) as totp:
        result = vault.fetch_credentials("http://127.0.0.1:8087", "CC", "Genevois")
    assert result["item_id"] == "exact-id"
    assert result["user"] == "synthetic-user"
    assert result["password"] == "synthetic-password"
    assert result["otp"] is None
    assert get.call_args_list == [
        mock.call("http://127.0.0.1:8087/list/object/items?search=CC%20Genevois"),
        mock.call("http://127.0.0.1:8087/object/item/exact-id")]
    totp.assert_called_once_with("http://127.0.0.1:8087/object/totp/exact-id")


@pytest.mark.parametrize("items", [[], [{"id": "one", "name": "CC genevois"}],
    [{"id": "a", "name": "CC Genevois"}, {"id": "b", "name": "CC Genevois"}],
    [{"id": "../SECRET_TOKEN", "name": "CC Genevois"}]])
def test_missing_ambiguous_or_invalid_id_fails_without_totp_or_secret_output(items):
    with mock.patch.object(vault, "get_json", return_value=response({"data": items})) as get, \
            mock.patch.object(vault, "get_totp") as totp:
        with pytest.raises(vault.VaultAPIError) as error:
            vault.fetch_credentials("http://127.0.0.1:8087", "CC", "Genevois")
    assert "SECRET_TOKEN" not in str(error.value)
    assert "Genevois" not in str(error.value)
    assert get.call_count == 1
    totp.assert_not_called()


def test_changed_item_identity_is_rejected():
    with mock.patch.object(vault, "get_json", side_effect=[
            response({"data": [{"id": "id", "name": "CC Genevois"}]}),
            response({"id": "id", "name": "other"})]), mock.patch.object(vault, "get_totp") as totp:
        with pytest.raises(vault.VaultAPIError):
            vault.fetch_credentials("http://127.0.0.1:8087", "CC", "Genevois")
    totp.assert_not_called()


def test_fresh_totp_uses_exact_id_after_initial_lookup():
    from types import SimpleNamespace
    from billcollector import runner
    bcs = SimpleNamespace(api_url="http://127.0.0.1:8087", vault_item_id="exact-id",
                          vault_item_name="CC Genevois", otp_fallback=None)
    with mock.patch.object(runner, "get_totp", return_value=response({"data":"synthetic-otp"})) as get:
        assert runner._fresh_otp(bcs) == "synthetic-otp"
    get.assert_called_once_with("http://127.0.0.1:8087/object/totp/exact-id")


def test_daemon_preflight_fetches_credentials_through_real_transport(monkeypatch):
    """Exercise status, exact lookup, item and optional TOTP over real HTTP."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from billcollector import runner

    received = []
    item_name = "CC Genevois & #/?"
    item = {"id": "exact-id", "name": item_name, "login": {
        "username": "synthetic-user", "password": "synthetic-password",
        "uris": [{"uri": "https://portal.invalid"}]}}
    search_path = "/list/object/items?search=CC%20Genevois%20%26%20%23%2F%3F"
    routes = {
        "/status": (200, {"template": {"status": "unlocked"}}),
        search_path: (200, {"data": [{"id": "other-id", "name": item_name.lower()}, item]}),
        "/object/item/exact-id": (200, item),
        "/object/totp/exact-id": (400, {}),
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append((self.path, self.headers.get("Host")))
            status, data = routes.get(self.path, (404, {}))
            body = response(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    api_url = f"http://127.0.0.1:{server.server_port}"
    # Only inject configuration; preflight, DNS, transport and HTTP stay real.
    monkeypatch.setattr(runner.config, "vault_settings", lambda db: (api_url, ""))
    monkeypatch.setenv("BW_API_URL", api_url)
    monkeypatch.setenv("BW_API_HOST", "")
    try:
        result = runner._vault_preflight({"service": "CC", "user": "Genevois & #/?"}, None)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert result == {"item_id": "exact-id", "user": "synthetic-user",
                      "password": "synthetic-password", "otp": None,
                      "url": "https://portal.invalid"}
    assert received == [(path, f"127.0.0.1:{server.server_port}") for path in routes]
