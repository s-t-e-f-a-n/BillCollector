# -*- coding: utf-8 -*-
"""Unit tests for the recipe file API (M2 chunk D5.4).

``validate_recipe`` (valid / schema violation / broken YAML),
``parse_steps`` (nested ``expect_download`` steps, graceful flag,
methods with arguments), ``save_recipe`` (atomic replace, no partial
file on failure, unvalidated text refused), and
``apply_candidate_to_step`` (M3 S2.2: the repair flow's candidate
replacement - the locator prefix replaced, the actions kept, the
not-applicable steps rejected). Validation runs against the real
schema (``config.RECIPE_SCHEMA``).
"""

import copy
import os
import sys
from pathlib import Path

import pytest
import yaml

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
        arguments:
        - selector: "#invoice"
"""


REPAIR = """\
services:
- serviceName: "testhappy"
  description: "Happy path with a changed login button."
  steps:
  - step: 1
    description: "Open the mock site landing page."
    methods:
    - method: "goto"
      arguments:
      - url: "http://127.0.0.1:8787/happy/"
  - step: 2
    description: "Fill the password field (title locator)."
    methods:
    - method: "get_by_title"
      arguments:
      - text: "Password"
    - method: "fill"
      arguments:
      - value: "{{PASSWORD}}"
  - step: 3
    description: "Scoped chain (main -> textbox)."
    methods:
    - method: "get_by_role"
      arguments:
      - role: "main"
    - method: "get_by_role"
      arguments:
      - role: "textbox"
      - name: "E-mail address"
    - method: "click"
    - method: "fill"
      arguments:
      - value: "{{USERNAME}}"
  - step: 4
    description: "Click the first invoice row."
    methods:
    - method: "get_by_text"
      arguments:
      - text: "Invoice dated"
    - method: "first"
    - method: "click"
  - step: 5
    description: "Close the popup in the iframe."
    methods:
    - method: "locator"
      arguments:
      - selector: "iframe#popup-frame"
    - method: "content_frame"
    - method: "get_by_label"
      arguments:
      - text: "Close popup"
    - method: "click"
  - step: 6
    description: "Download the invoice."
    methods:
    - method: "expect_download"
    steps:
    - step: 99
      description: "inner"
      methods:
      - method: "get_by_role"
        arguments:
        - role: "link"
        - name: "Invoice"
        - exact: true
      - method: "first"
      - method: "click"
  - step: 7
    description: "Close the page."
    methods:
    - method: "close"
  - step: 8
    description: "Wait for the operator."
    methods:
    - method: "wait_user"
      arguments:
      - prompt: "act"
"""

CAND_ROLE = {"locatorType": "get_by_role",
             "arguments": {"role": "button", "name": "Sign in", "exact": True}}
CAND_TEXT = {"locatorType": "get_by_text",
             "arguments": {"text": "Sign in", "exact": True}}


def _repair_data():
    ok, error, data = recipes.validate_recipe(REPAIR)
    assert ok is True, error
    return data


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
    assert child["methods"] == ["click(selector=#invoice)"]
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


def test_apply_candidate_replaces_the_prefix_and_keeps_the_actions():
    data = _repair_data()
    out = recipes.apply_candidate_to_step(data, 2, CAND_ROLE)
    assert out is not None
    methods = out["services"][0]["steps"][1]["methods"]
    assert methods == [
        {"method": "get_by_role",
         "arguments": [{"role": "button"}, {"name": "Sign in"},
                       {"exact": True}]},
        {"method": "fill", "arguments": [{"value": "{{PASSWORD}}"}]},
    ]
    # the rest of the step is untouched
    assert out["services"][0]["steps"][1]["step"] == 2
    assert out["services"][0]["steps"][1]["description"] == \
        "Fill the password field (title locator)."
    # the rest of the document is untouched
    assert out["services"][0]["steps"][2] == data["services"][0]["steps"][2]


def test_apply_candidate_does_not_mutate_the_input():
    data = _repair_data()
    snapshot = copy.deepcopy(data)
    out = recipes.apply_candidate_to_step(data, 2, CAND_ROLE)
    assert out is not None
    assert data == snapshot


def test_apply_candidate_method_entry_shape_and_key_order():
    data = _repair_data()
    out = recipes.apply_candidate_to_step(data, 2, CAND_ROLE)
    (entry,) = out["services"][0]["steps"][1]["methods"][:1]
    assert entry["method"] == "get_by_role"
    # one single-key dict per argument, in the candidate's key order
    assert entry["arguments"] == [
        {"role": "button"}, {"name": "Sign in"}, {"exact": True}]
    out = recipes.apply_candidate_to_step(
        data, 2, {"locatorType": "get_by_role",
                  "arguments": {"name": "Sign in", "role": "button",
                                "exact": True}})
    (entry,) = out["services"][0]["steps"][1]["methods"][:1]
    assert entry["arguments"] == [
        {"name": "Sign in"}, {"role": "button"}, {"exact": True}]


def test_apply_candidate_get_by_text():
    data = _repair_data()
    out = recipes.apply_candidate_to_step(data, 2, CAND_TEXT)
    methods = out["services"][0]["steps"][1]["methods"]
    assert methods[0] == {"method": "get_by_text",
                          "arguments": [{"text": "Sign in"}, {"exact": True}]}
    assert methods[1] == {"method": "fill",
                          "arguments": [{"value": "{{PASSWORD}}"}]}


def test_apply_candidate_replaces_a_scoped_chain_whole():
    data = _repair_data()
    out = recipes.apply_candidate_to_step(data, 3, CAND_ROLE)
    methods = out["services"][0]["steps"][2]["methods"]
    # the whole chain (get_by_role(main) -> get_by_role(textbox)) is
    # replaced by the single candidate; both actions keep their
    # arguments
    assert methods == [
        {"method": "get_by_role",
         "arguments": [{"role": "button"}, {"name": "Sign in"},
                       {"exact": True}]},
        {"method": "click"},
        {"method": "fill", "arguments": [{"value": "{{USERNAME}}"}]},
    ]


def test_apply_candidate_replaces_chain_continuations():
    data = _repair_data()
    # first: the chain continuation is part of the prefix
    out = recipes.apply_candidate_to_step(data, 4, CAND_TEXT)
    methods = out["services"][0]["steps"][3]["methods"]
    assert methods == [
        {"method": "get_by_text",
         "arguments": [{"text": "Sign in"}, {"exact": True}]},
        {"method": "click"},
    ]
    # content_frame: the iframe chain is replaced whole
    out = recipes.apply_candidate_to_step(data, 5, CAND_ROLE)
    methods = out["services"][0]["steps"][4]["methods"]
    assert methods == [
        {"method": "get_by_role",
         "arguments": [{"role": "button"}, {"name": "Sign in"},
                       {"exact": True}]},
        {"method": "click"},
    ]


def test_apply_candidate_candidate_without_arguments():
    data = _repair_data()
    out = recipes.apply_candidate_to_step(data, 4,
                                          {"locatorType": "get_by_test_id"})
    methods = out["services"][0]["steps"][3]["methods"]
    assert methods[0] == {"method": "get_by_test_id"}
    assert "arguments" not in methods[0]
    assert methods[1] == {"method": "click"}


def test_apply_candidate_rejects_a_goto_step():
    data = _repair_data()
    assert recipes.apply_candidate_to_step(data, 1, CAND_ROLE) is None


def test_apply_candidate_rejects_a_missing_step():
    data = _repair_data()
    assert recipes.apply_candidate_to_step(data, 99, CAND_ROLE) is None


def test_apply_candidate_rejects_nested_steps():
    data = _repair_data()
    # the expect_download step itself has no locator prefix ...
    assert recipes.apply_candidate_to_step(data, 6, CAND_ROLE) is None
    # ... and the nested step (number 99, top-level only search) is
    # never repaired (decision 7: the YAML path)
    assert recipes.apply_candidate_to_step(data, 99, CAND_ROLE) is None


def test_apply_candidate_rejects_close_and_wait_user_steps():
    data = _repair_data()
    assert recipes.apply_candidate_to_step(data, 7, CAND_ROLE) is None
    assert recipes.apply_candidate_to_step(data, 8, CAND_ROLE) is None


def test_apply_candidate_rejects_malformed_candidates():
    data = _repair_data()
    for bad in (None, "get_by_role", [], {},
                {"locatorType": 42}, {"locatorType": ""},
                {"arguments": {"role": "button"}},
                {"locatorType": "get_by_role", "arguments": ["role", "x"]},
                {"locatorType": "get_by_role", "arguments": "role"}):
        assert recipes.apply_candidate_to_step(data, 2, bad) is None, bad


def test_apply_candidate_rejects_non_recipe_documents():
    for bad in (None, {}, [], {"services": []}, {"services": "nope"}):
        assert recipes.apply_candidate_to_step(bad, 2, CAND_ROLE) is None, bad


def test_apply_candidate_rejects_non_integer_step_numbers():
    data = _repair_data()
    for bad in ("2", None, 2.0, [2]):
        assert recipes.apply_candidate_to_step(data, bad, CAND_ROLE) is None, bad


def test_apply_candidate_rewritten_document_validates():
    data = _repair_data()
    for step_number, candidate in ((2, CAND_ROLE), (3, CAND_ROLE),
                                   (4, CAND_TEXT), (5, CAND_ROLE)):
        out = recipes.apply_candidate_to_step(data, step_number, candidate)
        assert out is not None
        ok, error, _parsed = recipes.validate_recipe(yaml.safe_dump(out))
        assert ok is True, error


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
