# -*- coding: utf-8 -*-
"""UI tests for the settings page (M2 chunk D6.3).

Uses ``nicegui.testing.User`` (no browser), the same pattern as the
other UI tests: the main file builds the production wiring against a
fresh temp DB (``BC_UI_TEST_DB``). Covers the D6.1 contract: each field
writes its own Settings row (round-trip: the row is written and a
reloaded page shows the value), the git auto-commit switch round-trips
``true``/``false``, and the password change validates length/match and
then rejects the old password while accepting the new one.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector.db import Database  # noqa: E402
from billcollector.ui import auth  # noqa: E402

GOOD_PASSWORD = "ui-test-pass-1"
NEW_PASSWORD = "new-test-pass-9"

# (key, value to save, value the Settings table must hold afterwards).
TEXT_FIELDS = (
    ("ntfy_topic", "bc-topic-test", "bc-topic-test"),
    ("pause_deadline_seconds", "2700", "2700"),
    ("max_concurrency", "2", "2"),
    ("display_start", "101", "101"),
    ("download_dir", "/data/downloads", "/data/downloads"),
    ("ui_base_url", "http://10.0.0.5:8000", "http://10.0.0.5:8000"),
    ("vnc_password", "vnc-test-pass", "vnc-test-pass"),
)


@pytest.fixture
def testdb():
    """A direct connection to the same DB file the main file created."""
    db = Database(path=os.environ["BC_UI_TEST_DB"])
    yield db
    db.close()


async def _login(user, testdb) -> None:
    """Seed the password and authenticate the simulated session."""
    auth.set_password_hash(testdb, auth.hash_password(GOOD_PASSWORD))
    response = await user.http_client.post(
        "/login", data={"password": GOOD_PASSWORD}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def _field(user, key: str):
    (control,) = user.find(marker=f"set-{key}").elements
    return control


async def test_settings_page_shows_the_current_values(user, testdb):
    """The inputs are pre-filled from the Settings table (defaults for
    unset keys) and the switch reflects git_commit_enabled."""
    testdb.set_setting("ntfy_topic", "bc-topic-seeded")
    testdb.set_setting("pause_deadline_seconds", "3600")
    testdb.set_setting("git_commit_enabled", "true")
    await _login(user, testdb)
    await user.open("/settings")

    assert _field(user, "ntfy_topic").value == "bc-topic-seeded"
    assert _field(user, "pause_deadline_seconds").value == "3600"
    (switch,) = user.find(marker="set-git_commit_enabled").elements
    assert switch.value is True


@pytest.mark.parametrize(
    "key, new_value, stored",
    TEXT_FIELDS,
    ids=[key for key, _v, _s in TEXT_FIELDS],
)
async def test_field_round_trip_writes_its_settings_row(
        user, testdb, key, new_value, stored):
    """Editing a field and saving writes exactly its Settings row; a
    reloaded page shows the new value (D6.1/D6.3)."""
    await _login(user, testdb)
    await user.open("/settings")

    _field(user, key).value = new_value
    user.find(marker=f"set-save-{key}").click()

    assert testdb.get_setting(key) == stored
    assert user.notify.contains(f"{key} saved")

    await user.open("/settings")  # reload: the value comes from the table
    assert _field(user, key).value == new_value


async def test_invalid_field_values_are_rejected(user, testdb):
    """Non-integer or non-positive numbers and empty required fields
    write nothing (D6.1)."""
    await _login(user, testdb)
    await user.open("/settings")

    _field(user, "pause_deadline_seconds").value = "not-a-number"
    user.find(marker="set-save-pause_deadline_seconds").click()
    assert testdb.get_setting("pause_deadline_seconds") == "1800"
    assert user.notify.contains("pause_deadline_seconds: invalid value")

    _field(user, "max_concurrency").value = "0"
    user.find(marker="set-save-max_concurrency").click()
    assert testdb.get_setting("max_concurrency") == "1"

    _field(user, "ntfy_topic").value = "   "
    user.find(marker="set-save-ntfy_topic").click()
    assert testdb.get_setting("ntfy_topic") == "billcollector"


async def test_git_commit_switch_round_trips(user, testdb):
    """The switch stores ``true``/``false`` and a reloaded page shows
    the stored state (D6.1)."""
    await _login(user, testdb)
    await user.open("/settings")

    (switch,) = user.find(marker="set-git_commit_enabled").elements
    assert switch.value is False  # the default
    switch.value = True
    user.find(marker="set-save-git_commit_enabled").click()
    assert testdb.get_setting("git_commit_enabled") == "true"

    await user.open("/settings")
    (switch,) = user.find(marker="set-git_commit_enabled").elements
    assert switch.value is True
    switch.value = False
    user.find(marker="set-save-git_commit_enabled").click()
    assert testdb.get_setting("git_commit_enabled") == "false"


async def test_password_change_rejects_the_old_and_accepts_the_new(
        user, testdb):
    """The change form writes the new bcrypt hash; the old password is
    rejected at login, the new one accepted (D6.1/D6.3)."""
    await _login(user, testdb)
    await user.open("/settings")

    _field(user, "password-new").value = NEW_PASSWORD
    _field(user, "password-confirm").value = NEW_PASSWORD
    user.find(marker="set-save-password").click()

    assert user.notify.contains("Password updated")
    assert auth.verify_password(NEW_PASSWORD, auth.get_password_hash(testdb))

    response = await user.http_client.post(
        "/login", data={"password": GOOD_PASSWORD}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?error=wrong_password"

    response = await user.http_client.post(
        "/login", data={"password": NEW_PASSWORD}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


async def test_password_change_validates_length_and_match(user, testdb):
    """Too-short and mismatched passwords are rejected with a notify
    and the stored hash is left untouched (D6.1)."""
    await _login(user, testdb)
    await user.open("/settings")

    _field(user, "password-new").value = "short-1"
    _field(user, "password-confirm").value = "short-1"
    user.find(marker="set-save-password").click()
    assert user.notify.contains("at least")
    assert auth.verify_password(GOOD_PASSWORD, auth.get_password_hash(testdb))

    _field(user, "password-new").value = NEW_PASSWORD
    _field(user, "password-confirm").value = "different-pass"
    user.find(marker="set-save-password").click()
    assert user.notify.contains("must match")
    assert auth.verify_password(GOOD_PASSWORD, auth.get_password_hash(testdb))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
