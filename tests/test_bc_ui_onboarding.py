# -*- coding: utf-8 -*-
"""UI tests for the first-start onboarding wizard (M4 chunk C2).

Uses ``nicegui.testing.User`` (no browser): the main file (pytest.ini
``main_file``) re-runs per test and builds the production wiring against
a fresh temp DB (``BC_UI_TEST_DB``) with onboarding already completed
(the upgraded-install simulation). The ``onboarding`` fixture re-activates
the wizard for a test by removing the completed flag. Covers decision 1
(wizard gating: middleware redirect, first-start login target, the
auto-complete rule) and decision 2 (vault check/save, INI re-import,
manual task creation, task toggle, finish).
"""

import configparser
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

import nicegui  # noqa: E402
from nicegui import ui  # noqa: E402

from billcollector import config  # noqa: E402
from billcollector.db import Database  # noqa: E402
from billcollector.scheduler import TaskScheduler  # noqa: E402
from billcollector.ui import auth  # noqa: E402
from billcollector.ui import onboarding as onb  # noqa: E402
from billcollector.vault import VaultAPIError  # noqa: E402

GOOD_PASSWORD = "ui-test-pass-1"
VAULT_URL = "http://192.168.1.20:6100"


@pytest.fixture
def testdb():
    """A direct connection to the same DB file the main file created."""
    db = Database(path=os.environ["BC_UI_TEST_DB"])
    yield db
    db.close()


@pytest.fixture
def onboarding(testdb):
    """Activate the wizard for this test: the main file simulates an
    upgraded install (``onboarding_done=1``), so drop the flag."""
    testdb.conn.execute(
        "DELETE FROM Settings WHERE key='onboarding_done'")
    testdb.conn.commit()
    yield


async def _login(user, testdb) -> None:
    """Seed the password and authenticate the simulated session.

    With a hash stored, the login POST always redirects to ``/``; while
    the wizard is active the middleware then sends the next request to
    ``/onboarding``."""
    auth.set_password_hash(testdb, auth.hash_password(GOOD_PASSWORD))
    response = await user.http_client.post(
        "/login", data={"password": GOOD_PASSWORD}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


# ---- decision 1: wizard gating ---------------------------------------------

async def test_unauthenticated_request_goes_to_login_while_active(
        user, onboarding):
    """The unauthenticated redirect is unchanged by the wizard gate."""
    response = await user.http_client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/login"


async def test_authenticated_request_is_redirected_to_the_wizard(
        user, onboarding, testdb):
    """While active, every authenticated path except /onboarding bounces
    to the wizard (M4 C2, decision 1)."""
    await _login(user, testdb)
    for path in ("/", "/settings", "/downloads"):
        response = await user.http_client.get(path, follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/onboarding"


async def test_nicegui_static_assets_pass_the_wizard_gate(
        user, onboarding, testdb):
    """The page's own JS/CSS dependencies must pass through the gate; a
    redirect would 307 the module import to /onboarding, fail the bundle,
    and render the dead ES-modules fallback (M4 C2, decision 1)."""
    await _login(user, testdb)
    response = await user.http_client.get(
        f"/_nicegui/{nicegui.__version__}/static/dompurify.mjs",
        follow_redirects=False)
    assert response.status_code == 200
    assert "location" not in response.headers


async def test_the_wizard_page_is_reachable_while_active(
        user, onboarding, testdb):
    """The wizard itself must not redirect to itself (no loop)."""
    await _login(user, testdb)
    response = await user.http_client.get(
        "/onboarding", follow_redirects=False)
    assert response.status_code == 200


async def test_wizard_navigation_moves_between_steps(
        user, onboarding, testdb):
    """Continue/Back must move between the wizard's steps: the exit pass
    found the steps had no navigation at all (M4 exit pass, 2026-10-21)."""
    await _login(user, testdb)
    await user.open("/onboarding")

    stepper = next(iter(user.find(kind=ui.stepper).elements))
    assert stepper.value == "Vault"

    user.find(marker="onb-continue-vault").click()
    assert stepper.value == "Tasks"

    user.find(marker="onb-back-tasks").click()
    assert stepper.value == "Vault"

    user.find(marker="onb-continue-vault").click()
    user.find(marker="onb-continue-tasks").click()
    assert stepper.value == "Finish"

    user.find(marker="onb-back-finish").click()
    assert stepper.value == "Tasks"


async def test_first_start_password_targets_the_wizard(
        user, onboarding, testdb):
    """A fresh first start (no stored hash) lands on the wizard, not on
    the dashboard (M4 C2, decision 1)."""
    testdb.conn.execute(
        "DELETE FROM Settings WHERE key='ui_password_hash'")
    testdb.conn.commit()

    response = await user.http_client.post(
        "/login", data={"password": GOOD_PASSWORD,
                        "password_confirm": GOOD_PASSWORD},
        follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/onboarding"
    assert auth.get_password_hash(testdb) is not None


async def test_completed_wizard_is_not_enforced(user, testdb):
    """With the main file's completed state the gate is inert: protected
    pages load and the wizard shows its done page."""
    await _login(user, testdb)
    response = await user.http_client.get("/", follow_redirects=False)
    assert response.status_code == 200

    await user.open("/onboarding")
    await user.should_see("Onboarding is already complete.")
    assert user.find(marker="onb-done").elements


def test_auto_complete_onboarding_rule(tmp_path):
    """The serve-startup rule: a stored hash AND at least one enabled
    task auto-complete; any missing part keeps the wizard active (M4 C2,
    decision 1)."""
    db = Database(path=tmp_path / "t.db")
    try:
        assert auth.auto_complete_onboarding(db) is False  # nothing at all

        db.create_task("svc", "u1", enabled=True)
        assert auth.auto_complete_onboarding(db) is False  # no hash yet

        auth.set_password_hash(db, auth.hash_password("test-pass-12"))
        db.update_task(db.list_tasks()[0]["id"], enabled=0)
        assert auth.auto_complete_onboarding(db) is False  # no enabled task

        db.update_task(db.list_tasks()[0]["id"], enabled=1)
        assert auth.auto_complete_onboarding(db) is True
        assert db.get_setting("onboarding_done") == "1"
    finally:
        db.close()


# ---- decision 2, step 1: vault ---------------------------------------------

async def test_vault_check_reports_unlocked(user, onboarding, testdb,
                                            monkeypatch):
    """Check runs the same vetting + status call as the run preflight
    and reports an unlocked vault positively."""
    pinned = []
    monkeypatch.setattr(onb, "pinned_api_url",
                        lambda url, *a: pinned.append(url))
    monkeypatch.setattr(onb, "bitwarden_api_check_status",
                        lambda url: (True, "unlocked"))
    await _login(user, testdb)
    await user.open("/onboarding")

    (url_input,) = user.find(marker="onb-vault-url").elements
    url_input.value = VAULT_URL
    user.find(marker="onb-vault-check").click()

    assert pinned == [VAULT_URL]
    assert user.notify.contains("Vault reachable and unlocked")


async def test_vault_check_reports_locked(user, onboarding, testdb,
                                          monkeypatch):
    monkeypatch.setattr(onb, "pinned_api_url", lambda *a: None)
    monkeypatch.setattr(onb, "bitwarden_api_check_status",
                        lambda url: (True, "locked"))
    await _login(user, testdb)
    await user.open("/onboarding")

    (url_input,) = user.find(marker="onb-vault-url").elements
    url_input.value = VAULT_URL
    user.find(marker="onb-vault-check").click()

    assert user.notify.contains("Vault reachable but locked")


async def test_vault_check_without_url_is_rejected(user, onboarding, testdb,
                                                   monkeypatch):
    """An empty URL reports without touching the vault."""
    status_calls = []
    monkeypatch.setattr(onb, "pinned_api_url", lambda *a: None)
    monkeypatch.setattr(onb, "bitwarden_api_check_status",
                        lambda url: status_calls.append(url) or (True,
                                                                 "unlocked"))
    await _login(user, testdb)
    await user.open("/onboarding")

    # The input is pre-filled with the effective URL; clear it to reach
    # the empty-URL guard regardless of environment state.
    (url_input,) = user.find(marker="onb-vault-url").elements
    url_input.value = ""
    user.find(marker="onb-vault-check").click()

    assert user.notify.contains("Enter a vault API URL to check")
    assert status_calls == []


async def test_vault_check_reports_a_vault_error(user, onboarding, testdb,
                                                 monkeypatch):
    def boom(url):
        raise VaultAPIError("the vault said no")

    monkeypatch.setattr(onb, "pinned_api_url", lambda *a: None)
    monkeypatch.setattr(onb, "bitwarden_api_check_status", boom)
    await _login(user, testdb)
    await user.open("/onboarding")

    (url_input,) = user.find(marker="onb-vault-url").elements
    url_input.value = VAULT_URL
    user.find(marker="onb-vault-check").click()

    assert user.notify.contains("the vault said no")


async def test_vault_check_restores_the_environment(user, onboarding, testdb,
                                                    monkeypatch):
    """The entered pair is exported for the check only; the previous
    process values come back afterwards (unsaved values must not leak
    into later runs)."""
    monkeypatch.setenv("BW_API_URL", "http://env:6100")
    monkeypatch.setenv("BW_API_HOST", "env-host")
    monkeypatch.setattr(onb, "pinned_api_url", lambda *a: None)
    monkeypatch.setattr(onb, "bitwarden_api_check_status",
                        lambda url: (True, "unlocked"))
    await _login(user, testdb)
    await user.open("/onboarding")

    (url_input,) = user.find(marker="onb-vault-url").elements
    url_input.value = VAULT_URL
    user.find(marker="onb-vault-check").click()

    assert os.environ["BW_API_URL"] == "http://env:6100"
    assert os.environ["BW_API_HOST"] == "env-host"


async def test_vault_save_writes_the_settings(user, onboarding, testdb,
                                              monkeypatch):
    """Save writes both Settings rows (empty allowed) and hides the
    skip warning once a URL is present."""
    monkeypatch.delenv("BW_API_URL", raising=False)
    monkeypatch.delenv("BW_API_HOST", raising=False)
    await _login(user, testdb)
    await user.open("/onboarding")

    (warning,) = user.find(marker="onb-vault-warning").elements
    assert warning.visible

    (url_input,) = user.find(marker="onb-vault-url").elements
    url_input.value = VAULT_URL
    (host_input,) = user.find(marker="onb-vault-host").elements
    host_input.value = "vault.local"
    user.find(marker="onb-vault-save").click()

    assert testdb.get_setting("vault_api_url") == VAULT_URL
    assert testdb.get_setting("vault_api_host") == "vault.local"
    assert user.notify.contains("Vault settings saved")
    assert not warning.visible


# ---- decision 2, step 2: tasks ---------------------------------------------

async def test_import_from_ini_adds_only_missing_pairs(user, onboarding,
                                                       testdb, tmp_path,
                                                       monkeypatch):
    """The wizard's re-import runs import_ini(force=True): the temp INI's
    pairs are added (disabled, default cron); a second click adds
    nothing (the duplicate guard still applies)."""
    ini = tmp_path / "onb.ini"
    cp = configparser.ConfigParser()
    cp["Playwright"] = {"onb-svc-a": "u1, u2", "onb-svc-b": ""}
    with ini.open("w") as fh:
        cp.write(fh)
    monkeypatch.setattr(config, "INI_FILES", (ini,))
    await _login(user, testdb)
    await user.open("/onboarding")

    user.find(marker="onb-import-ini").click()

    tasks = {(t["service"], t["user"]) for t in testdb.list_tasks()}
    assert tasks == {("onb-svc-a", "u1"), ("onb-svc-a", "u2"),
                     ("onb-svc-b", "")}
    for task in testdb.list_tasks():
        assert task["enabled"] == 0
        assert task["cron"] == "0 0 1 * *"
    assert user.notify.contains("INI import: 3 task(s) added")

    user.find(marker="onb-import-ini").click()
    assert user.notify.contains("INI import: 0 task(s) added")
    assert len(testdb.list_tasks()) == 3


async def test_add_task_creates_a_disabled_task_with_derived_paths(
        user, onboarding, testdb, monkeypatch):
    """New task: (service, user, cron) with the recipe file and profile
    dir derived as in the INI import; the scheduler sync hook runs."""
    synced = []
    monkeypatch.setattr(TaskScheduler, "sync_task",
                        lambda self, task_id: synced.append(task_id))
    await _login(user, testdb)
    await user.open("/onboarding")

    (service_input,) = user.find(marker="onb-task-service").elements
    service_input.value = "onb-svc"
    (user_input,) = user.find(marker="onb-task-user").elements
    user_input.value = "onb-user1"
    (cron_input,) = user.find(marker="onb-task-cron").elements
    cron_input.value = "0 6 * * *"
    user.find(marker="onb-add-task").click()

    task = testdb.get_task_by_service_user("onb-svc", "onb-user1")
    assert task is not None
    assert task["enabled"] == 0
    assert task["cron"] == "0 6 * * *"
    assert task["recipe_file"].endswith("recipe-pw__onb-svc.yaml")
    assert task["profile_dir"].endswith("onb-svc_onb-user1")
    assert synced == [task["id"]]
    assert user.notify.contains("Task onb-svc / onb-user1 added")
    assert user.notify.contains("recipe-pw__onb-svc.yaml is missing")


async def test_add_task_rejects_duplicates_and_bad_crons(
        user, onboarding, testdb, monkeypatch):
    monkeypatch.setattr(TaskScheduler, "sync_task", lambda self, task_id: None)
    testdb.create_task("onb-dup", "u1", enabled=True)
    await _login(user, testdb)
    await user.open("/onboarding")

    (service_input,) = user.find(marker="onb-task-service").elements
    service_input.value = "onb-dup"
    (user_input,) = user.find(marker="onb-task-user").elements
    user_input.value = "u1"
    user.find(marker="onb-add-task").click()
    assert user.notify.contains("Task onb-dup / u1 already exists")

    (cron_input,) = user.find(marker="onb-task-cron").elements
    cron_input.value = "not a cron"
    service_input.value = "onb-other"
    user_input.value = "u9"
    user.find(marker="onb-add-task").click()
    assert user.notify.contains("Invalid cron expression")
    assert testdb.get_task_by_service_user("onb-other", "u9") is None


async def test_task_toggle_updates_enabled_and_syncs(user, onboarding,
                                                     testdb, monkeypatch):
    """The per-task switch writes the enabled flag through
    db.update_task and keeps the scheduler in step."""
    synced = []
    monkeypatch.setattr(TaskScheduler, "sync_task",
                        lambda self, task_id: synced.append(task_id))
    task_id = testdb.create_task("onb-tog", "u1", enabled=False)
    await _login(user, testdb)
    await user.open("/onboarding")

    (toggle,) = user.find(marker=f"onb-toggle-{task_id}").elements
    assert toggle.value is False
    toggle.value = True

    assert testdb.get_task(task_id)["enabled"] == 1
    assert synced == [task_id]
    assert user.notify.contains("Task onb-tog / u1 enabled")


# ---- decision 2, step 3: finish ---------------------------------------------

async def test_finish_writes_the_completed_flag(user, onboarding, testdb):
    """Finish onboarding writes onboarding_done=1; the middleware gate
    is inert afterwards."""
    await _login(user, testdb)
    await user.open("/onboarding")

    user.find(marker="onb-finish").click()

    assert testdb.get_setting("onboarding_done") == "1"
    response = await user.http_client.get("/", follow_redirects=False)
    assert response.status_code == 200


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
