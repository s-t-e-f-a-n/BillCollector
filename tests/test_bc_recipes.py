# -*- coding: utf-8 -*-
"""Unit tests for the recipe file API (M2 chunk D5.4).

``validate_recipe`` (valid / schema violation / broken YAML),
``parse_steps`` (nested ``expect_download`` steps, graceful flag,
methods with arguments), and ``save_recipe`` (atomic replace, no
partial file on failure, unvalidated text refused). Validation runs
against the real schema (``config.RECIPE_SCHEMA``).
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import recipes  # noqa: E402

VALID = """\
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

NESTED = """\
services:
- serviceName: "svc"
  steps:
  - step: 1
    description: "one"
    methods:
    - method: "goto"
      arguments:
      - url: "http://x/"
  - step: 2
    description: "two"
    graceful: true
    methods:
    - method: "expect_download"
    steps:
    - step: 1
      description: "inner"
      methods:
      - method: "click"
"""


def test_validate_recipe_accepts_a_valid_recipe():
    ok, error, data = recipes.validate_recipe(VALID)
    assert ok is True
    assert error is None
    assert data["services"][0]["serviceName"] == "testhappy"
    assert len(data["services"][0]["steps"]) == 2


def test_validate_recipe_reports_a_schema_violation_with_a_path():
    bad = VALID.replace("- step: 1\n", '- step: "two"\n')
    ok, error, data = recipes.validate_recipe(bad)
    assert ok is False
    assert data is None
    assert "services/0/steps/0/step" in error
    assert "integer" in error


def test_validate_recipe_reports_broken_yaml():
    ok, error, data = recipes.validate_recipe("services: [unclosed")
    assert ok is False
    assert data is None
    assert "invalid YAML" in error


def test_validate_recipe_rejects_an_empty_document():
    ok, error, data = recipes.validate_recipe("")
    assert ok is False
    assert data is None
    assert error


def test_load_recipe_roundtrip(tmp_path):
    path = tmp_path / "recipe-pw__testhappy.yaml"
    path.write_text(VALID, encoding="utf-8")
    ok, error, text, data = recipes.load_recipe(path)
    assert ok is True
    assert error is None
    assert text == VALID
    assert data["services"][0]["steps"][1]["graceful"] is True


def test_load_recipe_missing_file():
    ok, error, text, data = recipes.load_recipe("/nonexistent/recipe.yaml")
    assert ok is False
    assert text is None
    assert data is None
    assert error


def test_load_recipe_invalid_file_keeps_the_text(tmp_path):
    path = tmp_path / "recipe.yaml"
    path.write_text("services: [broken", encoding="utf-8")
    ok, error, text, data = recipes.load_recipe(path)
    assert ok is False
    assert text == "services: [broken"
    assert data is None
    assert "invalid YAML" in error


def test_parse_steps_flat_and_nested():
    ok, error, data = recipes.validate_recipe(NESTED)
    assert ok is True
    steps = recipes.parse_steps(data)
    assert len(steps) == 2

    first = steps[0]
    assert first["number"] == 1
    assert first["description"] == "one"
    assert first["graceful"] is False
    assert first["depth"] == 0
    assert first["methods"] == ["goto(url=http://x/)"]
    assert first["children"] == []

    second = steps[1]
    assert second["graceful"] is True
    assert second["methods"] == ["expect_download"]
    (child,) = second["children"]
    assert child["number"] == 1
    assert child["description"] == "inner"
    assert child["depth"] == 1
    assert child["methods"] == ["click"]
    assert child["children"] == []


def test_parse_steps_empty_documents():
    assert recipes.parse_steps(None) == []
    assert recipes.parse_steps({}) == []
    assert recipes.parse_steps({"services": []}) == []


def test_save_recipe_replaces_the_file(tmp_path):
    path = tmp_path / "recipe.yaml"
    path.write_text(VALID, encoding="utf-8")
    new = VALID.replace("Full happy path.", "Full happy path. (edited)")
    ok, error = recipes.save_recipe(path, new)
    assert ok is True
    assert error is None
    assert path.read_text(encoding="utf-8") == new
    assert list(tmp_path.glob("*.tmp")) == []


def test_save_recipe_refuses_unvalidated_text(tmp_path):
    path = tmp_path / "recipe.yaml"
    path.write_text(VALID, encoding="utf-8")
    ok, error = recipes.save_recipe(path, "services: [broken")
    assert ok is False
    assert error
    assert path.read_text(encoding="utf-8") == VALID


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses permissions")
def test_save_recipe_no_partial_file_on_write_failure(tmp_path):
    path = tmp_path / "recipe.yaml"
    path.write_text(VALID, encoding="utf-8")
    os.chmod(tmp_path, 0o555)
    try:
        ok, error = recipes.save_recipe(path, VALID.replace(
            "Full happy path.", "Full happy path. (edited)"))
        assert ok is False
        assert error
    finally:
        os.chmod(tmp_path, 0o755)
    assert path.read_text(encoding="utf-8") == VALID
    assert list(tmp_path.glob("*.tmp")) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
