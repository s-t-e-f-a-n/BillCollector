# -*- coding: utf-8 -*-
"""Unit tests for the recipe git auto-commit (M2 chunk D5.4).

``git_commit`` is exercised in a real temp git repo (local identity,
no global config touched): a commit lands with the exact message; a
second no-op commit succeeds without a new commit; a dirty unrelated
file is never swept in (only the recipe file is staged/committed).
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import gitcommit  # noqa: E402

RECIPE_NAME = "recipe-pw__testhappy.yaml"

RECIPE = """\
$schema: "recipe-pw-schema.yaml"
services:
- serviceName: "testhappy"
  description: "Full happy path."
  steps:
  - step: 1
    description: "Open the mock site landing page."
    methods:
    - method: "goto"
      arguments:
      - url: "http://127.0.0.1:8787/happy/"
"""


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A real temp git repo with the recipe file committed."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "ui@test.local")
    _git(repo, "config", "user.name", "UI Test")
    recipe = repo / RECIPE_NAME
    recipe.write_text(RECIPE, encoding="utf-8")
    _git(repo, "add", "--", RECIPE_NAME)
    _git(repo, "commit", "-m", "initial recipe")
    return {"repo": repo, "recipe": recipe}


def test_commit_lands_with_the_exact_message(repo):
    recipe: Path = repo["recipe"]
    recipe.write_text(RECIPE.replace("Full happy path.",
                                     "Edited happy path."), encoding="utf-8")
    ok, out = gitcommit.git_commit(
        [recipe], "recipe(testhappy): Edited happy path.", repo=repo["repo"])
    assert ok is True, out
    assert _git(repo["repo"], "log", "-1", "--pretty=%s") == \
        "recipe(testhappy): Edited happy path."
    assert _git(repo["repo"], "status", "--porcelain") == ""


def test_noop_commit_succeeds_without_a_new_commit(repo):
    ok, out = gitcommit.git_commit(
        [repo["recipe"]], "recipe(testhappy): edited via UI", repo=repo["repo"])
    assert ok is True, out
    assert "nothing to commit" in out
    assert _git(repo["repo"], "rev-list", "--count", "HEAD") == "1"
    assert _git(repo["repo"], "log", "-1", "--pretty=%s") == "initial recipe"


def test_only_the_recipe_file_is_committed_with_a_dirty_repo(repo):
    recipe: Path = repo["recipe"]
    other = repo["repo"] / "other.txt"
    other.write_text("unrelated", encoding="utf-8")
    recipe.write_text(RECIPE.replace("Full happy path.",
                                     "Edited happy path."), encoding="utf-8")
    ok, out = gitcommit.git_commit(
        [recipe], "recipe(testhappy): Edited happy path.", repo=repo["repo"])
    assert ok is True, out
    committed = _git(repo["repo"], "show", "--name-only", "--pretty=")
    assert committed == RECIPE_NAME
    status = _git(repo["repo"], "status", "--porcelain")
    assert "other.txt" in status  # still dirty, never committed


def test_missing_repo_fails_cleanly(tmp_path):
    ok, out = gitcommit.git_commit([tmp_path / "x.yaml"], "m",
                                   repo=tmp_path / "no-repo")
    assert ok is False
    assert out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
