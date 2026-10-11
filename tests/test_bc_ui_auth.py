# -*- coding: utf-8 -*-
"""UI tests for auth (M2 chunk D1).

Uses ``nicegui.testing.User`` (no browser): the main file (pytest.ini
``main_file``) builds the production wiring against a fresh temp DB,
and these tests drive the HTTP layer - the unauthenticated redirect,
the first-start set-password form, login with a wrong/correct password,
and the public ``/_alive`` endpoint."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector.db import Database  # noqa: E402
from billcollector.ui import auth  # noqa: E402

GOOD_PASSWORD = "ui-test-pass-1"


@pytest.fixture
def testdb():
    """A direct connection to the same DB file the main file created."""
    db = Database(path=os.environ["BC_UI_TEST_DB"])
    yield db
    db.close()


async def _set_password(user, password: str) -> None:
    """Complete the first-start set-password form (hash is persisted)."""
    response = await user.http_client.post(
        "/login", data={"password": password, "password_confirm": password},
        follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


async def test_unauthenticated_request_redirects_to_login(user):
    response = await user.http_client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/login"


async def test_first_start_shows_the_set_password_form(user, testdb):
    assert auth.get_password_hash(testdb) is None
    await user.open("/")  # follows the redirect to /login
    await user.should_see("First start: set the password for the UI login.")


async def test_set_password_too_short_is_rejected_with_error(user, testdb):
    response = await user.http_client.post(
        "/login", data={"password": "short", "password_confirm": "short"},
        follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?error=too_short"
    page = await user.http_client.get("/login?error=too_short")
    assert "must be at least" in page.text
    assert auth.get_password_hash(testdb) is None


async def test_set_password_mismatch_is_rejected_with_error(user, testdb):
    response = await user.http_client.post(
        "/login", data={"password": "good-pass-1", "password_confirm": "other"},
        follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?error=mismatch"
    page = await user.http_client.get("/login?error=mismatch")
    assert "must match" in page.text
    assert auth.get_password_hash(testdb) is None


async def test_set_password_success_redirects_and_persists(user, testdb):
    await _set_password(user, GOOD_PASSWORD)
    assert auth.get_password_hash(testdb) is not None
    assert auth.verify_password(GOOD_PASSWORD, auth.get_password_hash(testdb))


async def test_wrong_password_stays_on_login_with_error(user, testdb):
    await _set_password(user, GOOD_PASSWORD)
    response = await user.http_client.post(
        "/login", data={"password": "wrong-pass"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?error=wrong_password"
    page = await user.http_client.get("/login?error=wrong_password")
    assert "Wrong password." in page.text


async def test_correct_password_reaches_the_protected_index(user, testdb):
    # D2 replaced the D1 index placeholder with the dashboard; the header
    # and the (empty) waiting badge are the page's identity now.
    await _set_password(user, GOOD_PASSWORD)
    await user.open("/")
    await user.should_see("BillCollector")
    await user.should_see("0 waiting")


async def test_alive_is_public_without_authentication(user):
    response = await user.http_client.get("/_alive")
    assert response.status_code == 200
    assert response.text == "ok"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
