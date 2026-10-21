# -*- coding: utf-8 -*-
"""Tests for the vault API resolution (M4 chunk C1).

A non-empty Settings row (``vault_api_url`` / ``vault_api_host``) wins
over the environment (``BW_API_URL`` / ``BW_API_HOST``); a missing or
blank row falls back to the environment. The runner exports the
effective pair into the process environment before the vault calls, so
the env-reading transport sees the same values the preflight validated
(env-only and legacy batch deployments are unchanged: the export of the
env value is a no-op).
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import config, runner  # noqa: E402
from billcollector.db import Database  # noqa: E402

ENV_VARS = ("BW_API_URL", "BW_API_HOST")


class VaultSettingsResolutionTests(unittest.TestCase):
    """config.vault_settings: the Settings-over-env resolution order."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "bc.db")
        self._saved = {name: os.environ.pop(name, None) for name in ENV_VARS}

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self.db.close()
        self._tmp.cleanup()

    def test_settings_win_over_env(self):
        os.environ["BW_API_URL"] = "http://env-host:6100"
        os.environ["BW_API_HOST"] = "env-host"
        self.db.set_setting("vault_api_url", "http://set-host:6100")
        self.assertEqual(config.vault_settings(self.db),
                         ("http://set-host:6100", "env-host"))
        self.db.set_setting("vault_api_host", "set-host")
        self.assertEqual(config.vault_settings(self.db),
                         ("http://set-host:6100", "set-host"))

    def test_env_fallback_when_settings_unset(self):
        os.environ["BW_API_URL"] = "http://env-host:6100"
        os.environ["BW_API_HOST"] = "env-host"
        self.assertEqual(config.vault_settings(self.db),
                         ("http://env-host:6100", "env-host"))

    def test_blank_settings_value_falls_back_to_env(self):
        os.environ["BW_API_URL"] = "http://env-host:6100"
        os.environ["BW_API_HOST"] = ""
        self.db.set_setting("vault_api_url", "   ")
        self.db.set_setting("vault_api_host", "")
        self.assertEqual(config.vault_settings(self.db),
                         ("http://env-host:6100", ""))

    def test_both_unset_is_empty(self):
        self.db.set_setting("vault_api_url", "")
        self.assertEqual(config.vault_settings(self.db), ("", ""))


class VaultPreflightTests(unittest.TestCase):
    """runner._vault_preflight: effective URL selection and env export."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "bc.db")
        self.task = {"service": "svc", "user": "u1"}
        self._saved = {name: os.environ.pop(name, None) for name in ENV_VARS}
        self._patches = [
            mock.patch.object(runner, "pinned_api_url"),
            mock.patch.object(runner, "bitwarden_api_check_status",
                              return_value=(True, "unlocked")),
            mock.patch.object(runner, "fetch_credentials",
                              return_value={"user": "u", "password": "p",
                                            "otp": None, "url": None}),
        ]
        self.pinned = self._patches[0].start()
        self._patches[1].start()
        self._fetch = self._patches[2].start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self.db.close()
        self._tmp.cleanup()

    def test_settings_values_are_used_and_exported(self):
        self.db.set_setting("vault_api_url", "http://set-host:6100")
        self.db.set_setting("vault_api_host", "set-host")
        os.environ["BW_API_URL"] = "http://env-host:6100"
        os.environ["BW_API_HOST"] = "env-host"
        runner._vault_preflight(self.task, self.db)
        self.pinned.assert_called_once_with(
            "http://set-host:6100", runner.VAULT_MAX_ATTEMPTS,
            runner.VAULT_RETRY_BACKOFF)
        self._fetch.assert_called_once_with("http://set-host:6100", "svc", "u1")
        # The effective pair is exported for the env-reading transport.
        self.assertEqual(os.environ["BW_API_URL"], "http://set-host:6100")
        self.assertEqual(os.environ["BW_API_HOST"], "set-host")

    def test_env_only_is_unchanged(self):
        os.environ["BW_API_URL"] = "http://env-host:6100"
        os.environ["BW_API_HOST"] = ""
        runner._vault_preflight(self.task, self.db)
        self.pinned.assert_called_once_with(
            "http://env-host:6100", runner.VAULT_MAX_ATTEMPTS,
            runner.VAULT_RETRY_BACKOFF)
        # The export of the env value is a no-op for env-only deployments.
        self.assertEqual(os.environ["BW_API_URL"], "http://env-host:6100")
        self.assertEqual(os.environ["BW_API_HOST"], "")

    def test_unset_url_raises(self):
        with self.assertRaises(runner.VaultTransportError):
            runner._vault_preflight(self.task, self.db)
        self.pinned.assert_not_called()


if __name__ == "__main__":
    unittest.main()
