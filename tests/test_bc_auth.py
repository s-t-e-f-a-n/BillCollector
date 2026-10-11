# -*- coding: utf-8 -*-
"""Unit tests for the UI auth core (M2 chunk D1).

Covers the password hash helpers, the first-start seeding contract
(seed once from BC_UI_PASSWORD, never overwrite a stored hash, absent
hash + no env value -> set-password mode), the persisted session secret,
and the public-path predicate used by the auth middleware."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector.db import Database  # noqa: E402
from billcollector.ui import auth  # noqa: E402


class AuthCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(path=Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    # ---- hash / verify ----------------------------------------------------
    def test_hash_verify_round_trip(self):
        hashed = auth.hash_password("s3cret-pw")
        self.assertTrue(auth.verify_password("s3cret-pw", hashed))

    def test_verify_rejects_a_wrong_password(self):
        hashed = auth.hash_password("s3cret-pw")
        self.assertFalse(auth.verify_password("wrong", hashed))

    def test_verify_never_raises_on_a_corrupt_hash(self):
        self.assertFalse(auth.verify_password("anything", "not-a-bcrypt-hash"))
        self.assertFalse(auth.verify_password("anything", ""))

    def test_hashes_are_salt_unique(self):
        self.assertNotEqual(auth.hash_password("same"), auth.hash_password("same"))

    # ---- password storage / seeding ----------------------------------------
    def test_get_password_hash_absent_is_none(self):
        self.assertIsNone(auth.get_password_hash(self.db))

    def test_ensure_password_seeds_from_env_value_once(self):
        self.assertTrue(auth.ensure_password(self.db, env_password="seeded-pw-1"))
        self.assertTrue(auth.verify_password("seeded-pw-1",
                                             auth.get_password_hash(self.db)))
        # a second call (and a different env value) must not overwrite
        self.assertTrue(auth.ensure_password(self.db, env_password="other-pw"))
        self.assertTrue(auth.verify_password("seeded-pw-1",
                                             auth.get_password_hash(self.db)))
        self.assertFalse(auth.verify_password("other-pw",
                                              auth.get_password_hash(self.db)))

    def test_ensure_password_reads_bc_ui_password_env(self):
        with mock.patch.dict(os.environ, {"BC_UI_PASSWORD": "from-env-pw"}):
            self.assertTrue(auth.ensure_password(self.db))
        self.assertTrue(auth.verify_password("from-env-pw",
                                             auth.get_password_hash(self.db)))

    def test_ensure_password_absent_hash_and_no_env_is_set_mode(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(auth.ensure_password(self.db))
        self.assertIsNone(auth.get_password_hash(self.db))

    # ---- session secret -----------------------------------------------------
    def test_session_secret_generated_once_and_persisted(self):
        first = auth.get_session_secret(self.db)
        self.assertTrue(first)
        # a fresh Database handle on the same file sees the same secret
        other = Database(path=self.db.path)
        try:
            self.assertEqual(auth.get_session_secret(other), first)
        finally:
            other.close()

    # ---- public path predicate -----------------------------------------------
    def test_public_path_predicate(self):
        for public in ("/login", "/_alive", "/_nicegui/static/x.js",
                       "/_nicegui/3.17.1/foo.css"):
            self.assertTrue(auth.is_public_path(public), public)
        for protected in ("/", "/tasks/1", "/recipes/svc", "/runs/7",
                          "/downloads", "/settings", "/loginfo"):
            self.assertFalse(auth.is_public_path(protected), protected)


if __name__ == "__main__":
    unittest.main()
