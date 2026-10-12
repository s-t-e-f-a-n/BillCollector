# -*- coding: utf-8 -*-
"""UI tests for the recipe editor page (M2 chunk D5.4).

Uses ``nicegui.testing.User`` (no browser), the same pattern as the
other UI tests: the main file builds the production wiring against a
fresh temp DB (``BC_UI_TEST_DB``). ``config.RECIPE_DIR`` is pointed at
a per-test temp dir (so the repo's recipes are never touched) and
``gitcommit.REPO_ROOT`` at a real temp git repo for the commit tests
(the shared DB makes the service names unique per test).
"""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import config, gitcommit  # noqa: E402
from billcollector.db import Database  # noqa: E402
from billcollector.orchestrator import Orchestrator  # noqa: E402
from billcollector.ui import auth  # noqa: E402

GOOD_PASSWORD = "ui-test-pass-1"

RECIPE = """\
$schema: "recipe-pw-schema.yaml"
services:
- serviceName: "SERVICE"
  description: "Full happy path."
  steps:
  - step: 1
    description: "Open the mock site landing page."
    methods:
    - method: "goto"
      arguments:
      - url: "http://127.0.0.1:8787/happy/"
  - step: 2
    description: "Dismiss the cookie banner."
    graceful: true
    methods:
    - method: "get_by_role"
      arguments:
      - role: "button"
      - name: "Reject"
    - method: "click"
"""

EDITED = RECIPE.replace('description: "Full happy path."',
                        'description: "Edited happy path."')


def _recipe(service: str) -> str:
    return RECIPE.replace('"SERVICE"', f'"{service}"')


def _edited(service: str) -> str:
    return _recipe(service).replace(
        'description: "Full happy path."',
        'description: "Edited happy path."')


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


def _stub_orchestrator(monkeypatch, started: list, stopped: list) -> None:
    """Recording stubs for the orchestrator's run actions (D3.2
    pattern: the class patch reaches the production instance)."""
    async def fake_start(self, task_id):
        started.append(task_id)
        return True

    async def fake_stop(self, task_id, timeout=None):
        stopped.append(task_id)
        return True

    monkeypatch.setattr(Orchestrator, "start_run", fake_start)
    monkeypatch.setattr(Orchestrator, "stop_run", fake_stop)


async def _wait(predicate, message: str, timeout: float = 2.0) -> None:
    """Poll until ``predicate()`` holds (the action handlers are async)."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError(message)
        await asyncio.sleep(0.01)


def _seed_recipe(tmp_path, monkeypatch, testdb, service: str,
                 inside_repo: Path = None) -> dict:
    """A real recipe file in a temp RECIPE_DIR (inside the git repo
    when given) plus one task of the service."""
    if inside_repo is not None:
        recipe_dir = inside_repo / "recipes_playwright"
    else:
        recipe_dir = tmp_path / "recipes"
    recipe_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "RECIPE_DIR", recipe_dir)
    path = config.recipe_path_for(service)
    path.write_text(_recipe(service), encoding="utf-8")
    task = testdb.create_task(service, "user1", enabled=True, cron="0 0 1 * *")
    return {"path": path, "task": task}


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


async def test_editor_loads_the_current_yaml(user, testdb, tmp_path,
                                             monkeypatch):
    """The editor shows the file content, the service's task list, and
    the step tree (D5.3)."""
    service = "svc-reca"
    _seed_recipe(tmp_path, monkeypatch, testdb, service)
    await _login(user, testdb)
    await user.open(f"/recipes/{service}")

    (editor,) = user.find(marker="recipe-editor").elements
    assert editor.value == _recipe(service)
    await user.should_see(content=f"Tasks: {service} / user1")
    await user.should_see(content="#1 Open the mock site landing page.")
    await user.should_see(content="Dismiss the cookie banner. (graceful)")
    await user.should_see(content="goto(url=http://127.0.0.1:8787/happy/)")
    await user.should_see(content="get_by_role(role=button, name=Reject)")


async def test_invalid_edit_shows_the_error_and_keeps_the_file(
        user, testdb, tmp_path, monkeypatch):
    """Validate and Save on a broken YAML document: the error is shown
    inline, nothing is written (D5.3/D5.4)."""
    service = "svc-recb"
    seed = _seed_recipe(tmp_path, monkeypatch, testdb, service)
    await _login(user, testdb)
    await user.open(f"/recipes/{service}")

    (editor,) = user.find(marker="recipe-editor").elements
    editor.value = "services: [broken"
    await user.should_see(content="(YAML parse error")

    user.find(marker="recipe-validate").click()
    (result,) = user.find(marker="recipe-result").elements
    assert "invalid YAML" in result.text

    user.find(marker="recipe-save").click()
    (result,) = user.find(marker="recipe-result").elements
    assert "invalid YAML" in result.text
    assert seed["path"].read_text(encoding="utf-8") == _recipe(service)


async def test_valid_edit_writes_the_file_without_commit_when_toggle_off(
        user, testdb, tmp_path, monkeypatch):
    """With git_commit_enabled off (the default): the file is written,
    no commit is attempted (D5.3, locked decision 13)."""
    service = "svc-recc"
    seed = _seed_recipe(tmp_path, monkeypatch, testdb, service)
    testdb.set_setting("git_commit_enabled", "false")
    await _login(user, testdb)
    await user.open(f"/recipes/{service}")

    (editor,) = user.find(marker="recipe-editor").elements
    editor.value = _edited(service)
    user.find(marker="recipe-save").click()

    assert seed["path"].read_text(encoding="utf-8") == _edited(service)
    (result,) = user.find(marker="recipe-result").elements
    assert "Saved" in result.text
    assert "committed" not in result.text


async def test_valid_edit_writes_the_file_and_commits(
        user, testdb, tmp_path, monkeypatch):
    """With git_commit_enabled on: the file is written and the commit
    lands in the repo with the message ``recipe(<service>): <summary>``
    (summary = the first changed service description, D5.2/D5.3)."""
    service = "svc-recd"
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "ui@test.local")
    _git(repo, "config", "user.name", "UI Test")
    monkeypatch.setattr(gitcommit, "REPO_ROOT", repo)
    seed = _seed_recipe(tmp_path, monkeypatch, testdb, service,
                        inside_repo=repo)
    _git(repo, "add", "--", "recipes_playwright")
    _git(repo, "commit", "-m", "initial recipe")
    testdb.set_setting("git_commit_enabled", "true")
    await _login(user, testdb)
    await user.open(f"/recipes/{service}")

    (editor,) = user.find(marker="recipe-editor").elements
    editor.value = _edited(service)
    user.find(marker="recipe-save").click()

    assert seed["path"].read_text(encoding="utf-8") == _edited(service)
    (result,) = user.find(marker="recipe-result").elements
    assert "committed" in result.text
    assert _git(repo, "log", "-1", "--pretty=%s") == \
        f"recipe({service}): Edited happy path."
    assert _git(repo, "status", "--porcelain") == ""


async def test_run_now_buttons_appear_after_a_successful_save(
        user, testdb, tmp_path, monkeypatch):
    """After a successful save: one Run now button per task of the
    service, routing to ``orchestrator.start_run`` (the D3 action)."""
    service = "svc-rece"
    seed = _seed_recipe(tmp_path, monkeypatch, testdb, service)
    started, stopped = [], []
    _stub_orchestrator(monkeypatch, started, stopped)
    await _login(user, testdb)
    await user.open(f"/recipes/{service}")

    await user.should_not_see(marker="recipe-run-now")
    (editor,) = user.find(marker="recipe-editor").elements
    editor.value = _edited(service)
    user.find(marker="recipe-save").click()

    run_btns = user.find(marker="recipe-run-now").elements
    assert len(run_btns) == 1
    user.find(marker="recipe-run-now").click()
    await _wait(lambda: seed["task"] in started,
                "Run now did not call start_run")
    assert started == [seed["task"]]
    assert stopped == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
