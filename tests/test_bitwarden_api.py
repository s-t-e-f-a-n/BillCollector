import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps"))

from BillCollector import (  # noqa: E402
    WebRetriDoc,
    bitwarden_api_check_status,
    get_json,
    post_json,
)


class BitwardenApiTests(unittest.TestCase):
    @patch.dict("os.environ", {"BW_API_HOST": "127.0.0.1:8087"})
    @patch("BillCollector.requests.get")
    def test_get_uses_configured_host_header(self, request_get):
        response = MagicMock(text='{"success":true}')
        request_get.return_value = response

        self.assertEqual(get_json("http://bitwarden-cli:8087/status"),
                         '{"success":true}')
        request_get.assert_called_once_with(
            "http://bitwarden-cli:8087/status",
            headers={"Host": "127.0.0.1:8087"})
        response.raise_for_status.assert_called_once_with()

    @patch.dict("os.environ", {"BW_API_HOST": "127.0.0.1:8087"})
    @patch("BillCollector.requests.post")
    def test_post_uses_configured_host_header(self, request_post):
        response = MagicMock()
        response.json.return_value = {"success": True}
        request_post.return_value = response

        self.assertEqual(post_json("http://bitwarden-cli:8087/sync", None),
                         '{"success": true}')
        request_post.assert_called_once_with(
            "http://bitwarden-cli:8087/sync", json=None,
            headers={"Host": "127.0.0.1:8087"})
        response.raise_for_status.assert_called_once_with()

    @patch("BillCollector.requests.get")
    def test_http_error_returns_failed_status_without_json_type_error(self,
                                                                      request_get):
        response = MagicMock()
        response.raise_for_status.side_effect = requests.HTTPError("403")
        request_get.return_value = response

        self.assertEqual(
            bitwarden_api_check_status("http://bitwarden-cli:8087"),
            (False, None))

    @patch("BillCollector.post_json", return_value='{"success": true}')
    @patch("BillCollector.bitwarden_api_check_status",
           return_value=(True, "unlocked"))
    @patch("BillCollector.is_domain_local_ip")
    def test_empty_recipe_skips_vault_dns_and_syncs(self, dns_lookup,
                                                    check_status, sync):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as recipe:
            config = SimpleNamespace(
                vault=None,
                api="http://bitwarden-cli:8087",
                fname=recipe.name,
                debug=False,
            )

            WebRetriDoc(config)

        dns_lookup.assert_not_called()
        check_status.assert_called_once_with("http://bitwarden-cli:8087")
        sync.assert_called_once_with("http://bitwarden-cli:8087/sync", None)


if __name__ == "__main__":
    unittest.main()
