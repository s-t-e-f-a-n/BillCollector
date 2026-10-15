# -*- coding: utf-8 -*-
"""UI tests for the recipe editor page (M2 chunk D5.4).

Uses ``nicegui.testing.User`` (no browser), the same pattern as the
other UI tests: the main file builds the production wiring against a
fresh temp DB (``BC_UI_TEST_DB``). ``config.RECIPE_DIR`` is pointed at
a per-test temp dir (so the repo's recipes are never touched) and
``gitcommit.REPO_ROOT`` at a real temp git repo for the commit tests
(the shared DB makes the service names unique per test).

M3 chunk S2.4 (the committed S2.3 tests): the editor opened with
``?run=<run_id>`` renders the failure panel from the run's seeded
``pause_context`` (the ``/runfiles`` screenshot URL, the step label,
the expected locator chain, the error, the candidate rows), **Use**
rewrites the failed step's locator chain in the editor (asserted on
the re-parsed YAML), and the existing Save flow then writes the file
+ the ``recipe(<service>): ...`` commit (the D5.4 pattern). The
not-applicable states show the disabled picker + a hint: a failed
step without a locator prefix (``goto``) and a non-``step_failed``
pause (``wait_user``).
"""

import asyncio
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

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

# The S2.4 repair-flow recipe: a goto step (no locator prefix, not a
# repair target), the login step with a locator prefix (the failed
# step), and a later fill step with the {{PASSWORD}} placeholder (the
# replacement must keep the actions and the later steps intact).
REPAIR_RECIPE = """\
$schema: "recipe-pw-schema.yaml"
services:
- serviceName: "SERVICE"
  description: "Repair flow."
  steps:
  - step: 1
    description: "Open the mock site landing page."
    methods:
    - method: "goto"
      arguments:
      - url: "http://127.0.0.1:8787/happy/"
  - step: 2
    description: "Log in to the portal."
    methods:
    - method: "get_by_role"
      arguments:
      - role: "button"
      - name: "Login"
    - method: "click"
  - step: 3
    description: "Fill the password field."
    methods:
    - method: "get_by_label"
      arguments:
      - text: "Password"
    - method: "fill"
      arguments:
      - value: "{{PASSWORD}}"
"""


def _recipe(service: str, template: str = RECIPE) -> str:
    return template.replace('"SERVICE"', f'"{service}"')


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
                 inside_repo: Path = None, template: str = RECIPE) -> dict:
    """A real recipe file in a temp RECIPE_DIR (inside the git repo
    when given) plus one task of the service."""
    if inside_repo is not None:
        recipe_dir = inside_repo / "recipes_playwright"
    else:
        recipe_dir = tmp_path / "recipes"
    recipe_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "RECIPE_DIR", recipe_dir)
    path = config.recipe_path_for(service)
    path.write_text(_recipe(service, template), encoding="utf-8")
    task = testdb.create_task(service, "user1", enabled=True, cron="0 0 1 * *")
    return {"path": path, "task": task}


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


# ---- M3 chunk S2.4 (the S2.3 repair flow, committed) ---------------------

def _step_failed_context(shot: Path, step_number: int = 2) -> dict:
    """A realistic ``step_failed`` pause context (the
    ``build_pause_context`` shape, M3 S2.1): the failing step's parsed
    ``transform_step_to_json`` output (step 1 is the prefix-less goto,
    step 2 the login step), the screenshot inside the runfiles tree,
    and the two scan candidates with their ``locator`` dicts."""
    if step_number == 1:
        step = {
            "description": "Open the mock site landing page.",
            "locators": [],
            "actions": [{"action": "goto",
                         "arguments": {"url": "http://127.0.0.1:8787/happy/"}}],
        }
    else:
        step = {
            "description": "Log in to the portal.",
            "locators": [{"locator": "get_by_role",
                          "arguments": {"role": "button", "name": "Login"}}],
            "actions": [{"action": "click", "arguments": {}}],
        }
    return {
        "reason": "step_failed",
        "prompt": "The login button was not found",
        "url": "http://127.0.0.1:8787/happy/",
        "page_title": "Login",
        "error": "Timeout 30000ms exceeded.",
        "step_number": step_number,
        "step": step,
        "screenshot": {"path": str(shot),
                       "data": base64.b64encode(b"pause-shot").decode()},
        "elements": [
            {"n": 1, "role": "button", "name": "Sign in",
             "rect": {"x": 0, "y": 0, "w": 10, "h": 10},
             "locator": {"locatorType": "get_by_role",
                         "arguments": {"role": "button", "name": "Sign in",
                                       "exact": True}}},
            {"n": 2, "role": "button", "name": "Sign In",
             "rect": {"x": 0, "y": 20, "w": 10, "h": 10},
             "locator": {"locatorType": "get_by_text",
                         "arguments": {"text": "Sign In", "exact": True}}},
        ],
        "page_text": "Sign in",
        "deadline_at": "2026-10-15 21:00:00",
    }


def _wait_user_context(shot: Path) -> dict:
    """A ``wait_user`` pause context: no failing step (``step`` and
    ``step_number`` are None) but the scan candidates are still present
    (the picker must be disabled by the reason, not the candidates)."""
    return {
        "reason": "wait_user",
        "prompt": "Wait for the user to complete the manual step",
        "url": "http://127.0.0.1:8787/happy/",
        "page_title": "Manual step",
        "error": None,
        "step_number": None,
        "step": None,
        "screenshot": {"path": str(shot),
                       "data": base64.b64encode(b"pause-shot").decode()},
        "elements": [
            {"n": 1, "role": "button", "name": "Continue",
             "rect": {"x": 0, "y": 0, "w": 10, "h": 10},
             "locator": {"locatorType": "get_by_role",
                         "arguments": {"role": "button", "name": "Continue",
                                       "exact": True}}},
        ],
        "page_text": "Continue",
        "deadline_at": "2026-10-15 21:00:00",
    }


def _seed_repair_run(tmp_path, monkeypatch, testdb, service: str,
                     kind: str = "step_failed", step_number: int = 2,
                     inside_repo: Path = None) -> dict:
    """The repair recipe (the 3-step template) plus an ended run whose
    ``pause_context`` survived (the editor's ``?run=`` failure panel,
    M3 S2.3): the screenshot lives in the real runfiles tree so the
    ``/runfiles`` URL resolves, and the context is built from that path
    (``kind`` selects the ``step_failed`` / ``wait_user`` context)."""
    seed = _seed_recipe(tmp_path, monkeypatch, testdb, service,
                        inside_repo=inside_repo, template=REPAIR_RECIPE)
    run = testdb.create_run(seed["task"])
    run_dir = config.RUN_DIR / str(run)
    run_dir.mkdir(parents=True, exist_ok=True)
    shot = run_dir / "pause_1.png"
    shot.write_bytes(b"pause-shot")
    if kind == "step_failed":
        context = _step_failed_context(shot, step_number)
    else:
        context = _wait_user_context(shot)
    testdb.update_run(run, result="cancelled", ended_at="2026-10-15 08:00:00",
                      pause_reason=context["reason"],
                      pause_context=json.dumps(context),
                      notes="Paused at the login step")
    seed["run"] = run
    return seed


async def _open_repair(user, testdb, service: str, run: int) -> None:
    """Login + open the editor with the run's failure context
    preloaded (the session page's **Repair recipe** link target)."""
    await _login(user, testdb)
    await user.open(f"/recipes/{service}?run={run}")


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


# ---- the S2.3 repair flow (M3 chunk S2.4) ---------------------------------

async def test_failure_panel_renders_from_the_pause_context(user, testdb,
                                                            tmp_path,
                                                            monkeypatch):
    """Opened with ``?run=<run_id>``: the failure panel renders from the
    seeded ``pause_context`` - the title, the screenshot's ``/runfiles``
    URL, the step label, the expected locator chain, the error, and one
    row per candidate (S2.3, decision 7)."""
    service = "svc-repa"
    seed = _seed_repair_run(tmp_path, monkeypatch, testdb, service)
    await _open_repair(user, testdb, service, seed["run"])

    (title,) = user.find(marker="recipe-failure-title").elements
    assert title.text == f"Failure (run {seed['run']})"
    (shot,) = user.find(marker="recipe-failure-shot").elements
    assert shot.source == f"/runfiles/{seed['run']}/pause_1.png"
    (step,) = user.find(marker="recipe-failure-step").elements
    assert step.text == "Step 2: Log in to the portal."
    locators = user.find(marker="recipe-failure-locator").elements
    assert [loc.text for loc in locators] == \
        ["get_by_role(role=button, name=Login)"]
    (error,) = user.find(marker="recipe-failure-error").elements
    assert error.text == "Error: Timeout 30000ms exceeded."
    rows = user.find(marker="recipe-candidate-row").elements
    assert len(rows) == 2
    candidates = [c.text for c in
                  user.find(marker="recipe-candidate").elements]
    assert sorted(candidates) == [
        "1 · button · Sign in (get_by_role)",
        "2 · button · Sign In (get_by_text)",
    ]
    await user.should_not_see(marker="recipe-repair-hint")
    (use1,) = user.find(marker="recipe-use-1").elements
    (use2,) = user.find(marker="recipe-use-2").elements
    assert use1.enabled and use2.enabled


async def test_use_rewrites_the_step_chain_in_the_editor(user, testdb,
                                                         tmp_path,
                                                         monkeypatch):
    """**Use** replaces the failed step's locator prefix with the
    candidate's locator and the editor reloads with the re-dumped YAML:
    the re-parsed document carries the candidate's method entry, the
    step's action keeps following it, and the later steps (the
    ``{{PASSWORD}}`` fill) are untouched."""
    service = "svc-repb"
    seed = _seed_repair_run(tmp_path, monkeypatch, testdb, service)
    await _open_repair(user, testdb, service, seed["run"])

    user.find(marker="recipe-use-1").click()

    (editor,) = user.find(marker="recipe-editor").elements
    steps = yaml.safe_load(editor.value)["services"][0]["steps"]
    assert steps[1]["methods"] == [
        {"method": "get_by_role",
         "arguments": [{"role": "button"}, {"name": "Sign in"},
                       {"exact": True}]},
        {"method": "click"},
    ]
    assert steps[2]["methods"] == [
        {"method": "get_by_label", "arguments": [{"text": "Password"}]},
        {"method": "fill", "arguments": [{"value": "{{PASSWORD}}"}]},
    ]
    assert steps[0] == {"step": 1, "description": "Open the mock site "
                                                  "landing page.",
                        "methods": [{"method": "goto",
                                     "arguments": [{"url":
                                                    "http://127.0.0.1:"
                                                    "8787/happy/"}]}]}
    (result,) = user.find(marker="recipe-result").elements
    assert result.text == ("Step 2 locator replaced with get_by_role; "
                           "review, then Validate and Save.")
    # The step tree re-rendered with the new chain.
    await user.should_see(
        content="get_by_role(role=button, name=Sign in, exact=True)")


async def test_use_then_save_writes_the_file_and_commits(user, testdb,
                                                         tmp_path,
                                                         monkeypatch):
    """The rewritten editor content runs through the existing Validate
    -> Save flow (the D5.4 pattern): the file is written and, with
    ``git_commit_enabled`` on, the ``recipe(<service>): ...`` commit
    lands in the repo."""
    service = "svc-repc"
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "ui@test.local")
    _git(repo, "config", "user.name", "UI Test")
    monkeypatch.setattr(gitcommit, "REPO_ROOT", repo)
    seed = _seed_repair_run(tmp_path, monkeypatch, testdb, service,
                            inside_repo=repo)
    _git(repo, "add", "--", "recipes_playwright")
    _git(repo, "commit", "-m", "initial recipe")
    testdb.set_setting("git_commit_enabled", "true")
    await _open_repair(user, testdb, service, seed["run"])

    user.find(marker="recipe-use-1").click()
    user.find(marker="recipe-save").click()

    (editor,) = user.find(marker="recipe-editor").elements
    assert seed["path"].read_text(encoding="utf-8") == editor.value
    (result,) = user.find(marker="recipe-result").elements
    assert "Saved and committed" in result.text
    assert _git(repo, "log", "-1", "--pretty=%s") == \
        f"recipe({service}): edited via UI"
    assert _git(repo, "status", "--porcelain") == ""
    # The committed file carries the candidate's locator.
    committed = yaml.safe_load(_git(
        repo, "show", f"HEAD:recipes_playwright/{seed['path'].name}"))
    assert committed["services"][0]["steps"][1]["methods"][0] == {
        "method": "get_by_role",
        "arguments": [{"role": "button"}, {"name": "Sign in"},
                      {"exact": True}],
    }


async def test_goto_step_shows_the_disabled_picker_and_hint(user, testdb,
                                                            tmp_path,
                                                            monkeypatch):
    """A failed step without a locator prefix (the ``goto`` step): the
    picker is disabled with the not-repairable hint (the YAML path) -
    the failure panel itself still renders."""
    service = "svc-repd"
    seed = _seed_repair_run(tmp_path, monkeypatch, testdb, service,
                            step_number=1)
    await _open_repair(user, testdb, service, seed["run"])

    (step,) = user.find(marker="recipe-failure-step").elements
    assert step.text == "Step 1: Open the mock site landing page."
    await user.should_not_see(marker="recipe-failure-locator")
    (hint,) = user.find(marker="recipe-repair-hint").elements
    assert "cannot be candidate-repaired" in hint.text
    (use1,) = user.find(marker="recipe-use-1").elements
    (use2,) = user.find(marker="recipe-use-2").elements
    assert not use1.enabled and not use2.enabled
    # A disabled Use button leaves the editor content untouched.
    (editor,) = user.find(marker="recipe-editor").elements
    assert editor.value == _recipe(service, REPAIR_RECIPE)


async def test_wait_user_pause_disables_the_picker_with_a_hint(user, testdb,
                                                               tmp_path,
                                                               monkeypatch):
    """A pause that is not a step failure (``wait_user``): the picker is
    disabled with the not-a-step-failure hint even though the context
    carries candidate elements."""
    service = "svc-repe"
    seed = _seed_repair_run(tmp_path, monkeypatch, testdb, service,
                            kind="wait_user")
    await _open_repair(user, testdb, service, seed["run"])

    await user.should_not_see(marker="recipe-failure-step")
    (hint,) = user.find(marker="recipe-repair-hint").elements
    assert "not a step failure" in hint.text
    assert len(user.find(marker="recipe-candidate-row").elements) == 1
    (use1,) = user.find(marker="recipe-use-1").elements
    assert not use1.enabled


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
