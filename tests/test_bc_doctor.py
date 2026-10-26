# -*- coding: utf-8 -*-
"""Unit tests for the offline LLM recipe doctor (Stage 1).

Prompt building (text-only), LLM reply parsing (fence/prose
tolerance), the surgical step replacement in raw recipe text
(minimal diff, nested/absent step rejection), pause-context loading
(file, directory, DB), and the full dry-run/apply path with a
canned LLM reply against a copy of the real buhl recipe.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import config, doctor, recipes  # noqa: E402
from billcollector.db import Database  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
BUHL = REPO / "apps" / "recipes_playwright" / "recipe-pw__buhl.yaml"
# The live recipe already carries the doctor's step-5 fix (key, not
# value); the tests run against the pre-fix baseline so the canned
# fix still produces a diff, regardless of the recipe's state.
BUHL_TEXT = BUHL.read_text(encoding="utf-8").replace(
    '      - key: "Tab"', '      - value: "Tab"')

BUHL_FIX = {
    "explanation": "press() takes key, not value.",
    "fix_type": "step",
    "step_number": 5,
    "confidence": "high",
    "fixed_step": {
        "step": 5,
        "description": "",
        "methods": [
            {"method": "get_by_role",
             "arguments": [{"role": "textbox"},
                           {"name": "E-Mail-Adresse"}]},
            {"method": "press", "arguments": [{"key": "Tab"}]},
        ],
    },
}


def _pause_file(tmp_path):
    pause = {
        "reason": "step_failed",
        "step_number": 5,
        "error": {"error": [{"method": "press", "category": "other"}]},
        "url": "https://www.buhl.de/mein-buhlkonto/",
        "page_title": "Mein BuhlKonto",
        "step": {"locators": [], "actions": []},
        "elements": [],
        "page_text": "login page",
    }
    path = tmp_path / "buhl_pause.json"
    path.write_text(json.dumps(pause))
    return path


def _canned(tmp_path, fix):
    path = tmp_path / "reply.json"
    path.write_text("```json\n" + json.dumps(fix) + "\n```")
    return path


# --- step replacement in raw text -------------------------------------

def test_replace_step_minimal_diff():
    new_text = doctor.replace_step_in_text(BUHL_TEXT, 5,
                                           BUHL_FIX["fixed_step"])
    assert new_text is not None
    old = BUHL_TEXT.splitlines()
    new = new_text.splitlines()
    assert len(old) == len(new)
    changed = [i for i, (a, b) in enumerate(zip(old, new)) if a != b]
    assert len(changed) == 1
    assert old[changed[0]] == '      - value: "Tab"'
    assert new[changed[0]] == '      - key: "Tab"'
    ok, error, _data = recipes.validate_recipe(new_text)
    assert ok, error


def test_replace_step_rejections():
    assert doctor.replace_step_in_text(BUHL_TEXT, 99,
                                       BUHL_FIX["fixed_step"]) is None
    # 10 is a nested expect_download step: never a repair target
    assert doctor.replace_step_in_text(BUHL_TEXT, 10,
                                       BUHL_FIX["fixed_step"]) is None
    mismatch = dict(BUHL_FIX["fixed_step"], step=6)
    assert doctor.replace_step_in_text(BUHL_TEXT, 5, mismatch) is None
    assert doctor.replace_step_in_text(BUHL_TEXT, 5, {"step": 5}) is None
    assert doctor.replace_step_in_text(
        BUHL_TEXT, 5, {"step": 5, "methods": "nope"}) is None


def test_replace_step_missing_number_injected():
    step = {k: v for k, v in BUHL_FIX["fixed_step"].items()
            if k != "step"}
    new_text = doctor.replace_step_in_text(BUHL_TEXT, 5, step)
    assert new_text is not None
    assert "  - step: 5" in new_text


def test_replace_step_graceful_roundtrip():
    step = {
        "step": 2,
        "description": "",
        "graceful": True,
        "methods": [
            {"method": "get_by_label",
             "arguments": [{"text": "Nur technisch notwendige"}]},
            {"method": "click"},
        ],
    }
    new_text = doctor.replace_step_in_text(BUHL_TEXT, 2, step)
    assert new_text is not None
    lines = new_text.splitlines()
    idx = lines.index("  - step: 2")
    assert lines[idx + 1] == "    description: ''"
    assert lines[idx + 2] == "    graceful: true"
    ok, error, _data = recipes.validate_recipe(new_text)
    assert ok, error


def test_replace_step_force_argument_roundtrip():
    step = {
        "step": 2,
        "description": "",
        "graceful": True,
        "methods": [
            {"method": "get_by_label",
             "arguments": [{"text": "Nur technisch notwendige"}]},
            {"method": "click", "arguments": [{"force": True}]},
        ],
    }
    new_text = doctor.replace_step_in_text(BUHL_TEXT, 2, step)
    assert new_text is not None
    old = BUHL_TEXT.splitlines()
    new = new_text.splitlines()
    idx = new.index("  - step: 2")
    assert new[idx + 7] == "    - method: click"
    assert new[idx + 8] == "      arguments:"
    assert new[idx + 9] == "      - force: true"
    assert new[idx + 10] == "  - step: 3"
    # minimal diff: exactly the two argument lines inserted, nothing else
    assert new[:idx + 8] == old[:idx + 8]
    assert new[idx + 10:] == old[idx + 8:]
    assert len(new) == len(old) + 2
    ok, error, _data = recipes.validate_recipe(new_text)
    assert ok, error


# --- LLM reply parsing --------------------------------------------------

def test_parse_llm_response_variants():
    assert doctor.parse_llm_response('{"fix_type": "step"}') == {
        "fix_type": "step"}
    fenced = '```json\n{"fix_type": "step", "note": "a{b}"}\n```'
    assert doctor.parse_llm_response(fenced)["note"] == "a{b}"
    prose = 'Here you go: {"fix_type": "none"} Hope that helps!'
    assert doctor.parse_llm_response(prose)["fix_type"] == "none"
    with pytest.raises(ValueError):
        doctor.parse_llm_response("no json here")
    with pytest.raises(ValueError):
        doctor.parse_llm_response('{"fix_type": "step"')


# --- prompt building ----------------------------------------------------

def test_build_prompt_text_only():
    pause = {
        "step_number": 5,
        "error": {"error": [{"method": "press", "category": "other"}]},
        "url": "https://www.buhl.de/mein-buhlkonto/",
        "page_title": "Mein BuhlKonto",
        "step": {"locators": [], "actions": []},
        "elements": [
            {"n": 1, "role": "textbox", "name": "E-Mail-Adresse",
             "rect": {"x": 441, "y": 225, "w": 383, "h": 56},
             "locator": {"locatorType": "get_by_role",
                         "arguments": {"role": "textbox",
                                       "name": "E-Mail-Adresse"}}},
            {"n": 2, "role": "button", "name": "HiddenThing",
             "rect": {"x": 0, "y": 0, "w": 0, "h": 0},
             "locator": {"locatorType": "get_by_role",
                         "arguments": {"role": "button",
                                       "name": "HiddenThing"}}},
        ],
        "page_text": "x" * 20000,
    }
    system, user = doctor.build_prompt("buhl", pause, BUHL_TEXT)
    assert "SERVICE: buhl" in user
    assert "E-Mail-Adresse" in user
    assert "HiddenThing" not in user  # hidden elements are excluded
    assert "base64" not in system + user
    assert "fix_type" in system
    assert len(user) < 30000  # page text truncated


def test_build_prompt_force_guidance():
    pause = {
        "step_number": 3,
        "error": {},
        "url": "https://example.com",
        "page_title": "t",
        "step": {"locators": [], "actions": []},
        "elements": [],
        "page_text": "",
    }
    system, _user = doctor.build_prompt("svc", pause, BUHL_TEXT)
    assert "force: true" in system
    assert "actionability" in system
    assert "dismiss" in system  # prefer a graceful banner dismiss
    assert "hit testing" in system  # force does not click through overlays


# --- pause context loading ----------------------------------------------

def test_load_pause_context_file_and_dir(tmp_path):
    pause = {"step": {}, "step_number": 1, "error": {}}
    (tmp_path / "svc_pause.json").write_text(json.dumps(pause))
    ok, _err, ctx = doctor.load_pause_context(
        pause=str(tmp_path / "svc_pause.json"))
    assert ok and ctx["step_number"] == 1
    ok, _err, ctx = doctor.load_pause_context(pause=str(tmp_path))
    assert ok and ctx == pause


def test_load_pause_context_errors(tmp_path):
    (tmp_path / "bad_pause.json").write_text("{}")
    ok, err, _ctx = doctor.load_pause_context(
        pause=str(tmp_path / "bad_pause.json"))
    assert not ok and "step" in err
    ok, err, _ctx = doctor.load_pause_context(
        pause=str(tmp_path / "missing.json"))
    assert not ok and "cannot read" in err
    ok, err, _ctx = doctor.load_pause_context()
    assert not ok


def test_load_pause_context_from_db(tmp_path, monkeypatch):
    db = Database(path=tmp_path / "bc.db")
    db.conn.execute(
        "INSERT INTO Run (id, task_id, result) VALUES (?, ?, 'paused')",
        (1, 1))
    db.conn.commit()
    ctx = {"step": {}, "step_number": 2, "error": {}}
    db.conn.execute(
        "UPDATE Run SET pause_context = ? WHERE id = 1",
        (json.dumps(ctx),))
    db.conn.commit()
    ok, _err, got = doctor.load_pause_context(from_run=1, db=db)
    assert ok and got == ctx
    ok, err, _got = doctor.load_pause_context(from_run=99, db=db)
    assert not ok


# --- orchestrator: dry run / apply / error paths -------------------------

def test_run_doctor_dry_run(tmp_path, monkeypatch, capsys):
    recipe_dir = tmp_path / "recipes"
    recipe_dir.mkdir()
    (recipe_dir / "recipe-pw__buhl.yaml").write_text(BUHL_TEXT)
    monkeypatch.setattr(config, "RECIPE_DIR", recipe_dir)
    rc = doctor.run_doctor("buhl", pause=str(_pause_file(tmp_path)),
                           llm_response=str(_canned(tmp_path, BUHL_FIX)))
    out = capsys.readouterr().out
    assert rc == 0
    assert '- key: "Tab"' in out
    assert "dry run" in out
    assert (recipe_dir / "recipe-pw__buhl.yaml").read_text(
        encoding="utf-8") == BUHL_TEXT


def test_run_doctor_apply(tmp_path, monkeypatch, capsys):
    recipe_dir = tmp_path / "recipes"
    recipe_dir.mkdir()
    (recipe_dir / "recipe-pw__buhl.yaml").write_text(BUHL_TEXT)
    monkeypatch.setattr(config, "RECIPE_DIR", recipe_dir)
    rc = doctor.run_doctor("buhl", pause=str(_pause_file(tmp_path)),
                           llm_response=str(_canned(tmp_path, BUHL_FIX)),
                           apply=True)
    out = capsys.readouterr().out
    assert rc == 0
    assert "saved" in out
    new = (recipe_dir / "recipe-pw__buhl.yaml").read_text(encoding="utf-8")
    assert '- key: "Tab"' in new
    ok, error, _data = recipes.validate_recipe(new)
    assert ok, error


def test_run_doctor_out_file(tmp_path, monkeypatch):
    recipe_dir = tmp_path / "recipes"
    recipe_dir.mkdir()
    (recipe_dir / "recipe-pw__buhl.yaml").write_text(BUHL_TEXT)
    monkeypatch.setattr(config, "RECIPE_DIR", recipe_dir)
    out_file = tmp_path / "proposed.yaml"
    rc = doctor.run_doctor("buhl", pause=str(_pause_file(tmp_path)),
                           llm_response=str(_canned(tmp_path, BUHL_FIX)),
                           out=str(out_file))
    assert rc == 0
    assert '- key: "Tab"' in out_file.read_text(encoding="utf-8")
    assert (recipe_dir / "recipe-pw__buhl.yaml").read_text(
        encoding="utf-8") == BUHL_TEXT


def test_run_doctor_no_in_place_fix(tmp_path, capsys):
    fix = {"explanation": "portal flow changed", "fix_type": "none"}
    rc = doctor.run_doctor("buhl", pause=str(_pause_file(tmp_path)),
                           llm_response=str(_canned(tmp_path, fix)))
    assert rc == 1
    assert "no in-place fix" in capsys.readouterr().out


def test_run_doctor_no_endpoint(tmp_path):
    rc = doctor.run_doctor("buhl", pause=str(_pause_file(tmp_path)),
                           llm_url="", llm_model="")
    assert rc == 2


def test_run_doctor_invalid_proposal(tmp_path, capsys):
    bad = {"explanation": "x", "fix_type": "recipe",
           "fixed_recipe": "services: [unclosed"}
    rc = doctor.run_doctor("buhl", pause=str(_pause_file(tmp_path)),
                           llm_response=str(_canned(tmp_path, bad)))
    assert rc == 2
    assert "validation" in capsys.readouterr().out


def test_run_doctor_bad_reply(tmp_path, capsys):
    path = tmp_path / "reply.txt"
    path.write_text("I cannot help with that.")
    rc = doctor.run_doctor("buhl", pause=str(_pause_file(tmp_path)),
                           llm_response=str(path))
    assert rc == 2
    assert "parse" in capsys.readouterr().out


def test_run_doctor_prompt_file(tmp_path):
    prompt = tmp_path / "prompt.txt"
    rc = doctor.run_doctor("buhl", pause=str(_pause_file(tmp_path)),
                           prompt_file=str(prompt))
    assert rc == 0
    text = prompt.read_text(encoding="utf-8")
    assert "# SYSTEM PROMPT" in text
    assert "# USER PROMPT" in text
    assert "SERVICE: buhl" in text


def test_run_doctor_missing_recipe(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "RECIPE_DIR", tmp_path)
    rc = doctor.run_doctor("ghost", pause=str(_pause_file(tmp_path)))
    assert rc == 3
