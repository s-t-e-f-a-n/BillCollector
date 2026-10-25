# -*- coding: utf-8 -*-
"""Offline LLM recipe doctor (dev-side, Stage 1).

Given a service recipe and one captured pause context (a run that
paused on a failed step), proposes a repaired step or recipe via a
local OpenAI-compatible LLM endpoint.

Design constraints:

- Text-only LLM input (no vision): the pause context's structured
  element list + page text carry the page state.
- Strict-JSON output contract (``fix_type`` step/recipe/none).
- Every proposal passes the existing ``validate_recipe`` gate before
  it is shown or written.
- The recipe file is only touched with ``--apply`` (the
  human-approval gate); the default is a dry-run diff on stdout.
- Dev-side only: no daemon import, no protocol change, the daemon is
  unaffected when the LLM endpoint is down or missing.
"""

import copy
import difflib
import json
import re
from pathlib import Path

import requests
import yaml

from . import config, recipes

# --- recipe YAML style (matches the files produced by the codegen
# helper: plain keys, double-quoted argument string values) ----------

class DoubleQuoted(str):
    """Marker: represent this string value with double quotes."""


class _Dumper(yaml.SafeDumper):
    pass


def _represent_double_quoted(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')


_Dumper.add_representer(DoubleQuoted, _represent_double_quoted)


def _quote_step(step):
    """Deep-copy a step and double-quote its argument string values."""
    step = copy.deepcopy(step)

    def quote(step_node):
        for method in step_node.get("methods") or []:
            if not isinstance(method, dict):
                continue
            args = method.get("arguments")
            if not isinstance(args, list):
                continue
            method["arguments"] = [
                {key: DoubleQuoted(value) if isinstance(value, str) else value
                 for key, value in entry.items()}
                if isinstance(entry, dict) else entry
                for entry in args]
        for child in step_node.get("steps") or []:
            if isinstance(child, dict):
                quote(child)

    quote(step)
    return step


def _order_method(method):
    """One method entry with its keys in the recipe's order."""
    if not isinstance(method, dict):
        return method
    ordered = {}
    for key in ("method", "arguments"):
        if key in method:
            ordered[key] = method[key]
    for key in method:
        if key not in ordered:
            ordered[key] = method[key]
    return ordered


def serialize_step(step) -> str:
    """One step as a YAML block (keys in the recipe's order)."""
    ordered = {}
    for key in ("step", "description", "graceful", "methods", "steps",
                "submit", "phases"):
        if key in step:
            ordered[key] = step[key]
    for key in step:
        if key not in ordered:
            ordered[key] = step[key]
    if isinstance(ordered.get("methods"), list):
        ordered["methods"] = [_order_method(m)
                              for m in ordered["methods"]]
    return yaml.dump(_quote_step(ordered), Dumper=_Dumper, sort_keys=False,
                     allow_unicode=True, default_flow_style=False)


_STEP_RE = re.compile(r"^(\s*)- step:\s*(\d+)\s*$")


def _top_level_step_blocks(lines):
    """``[(step_number, indent, start, end)]`` of the top-level steps.

    Top level = the smallest ``- step:`` indent in the file (nested
    ``expect_download`` steps are deeper). ``end`` is the index of the
    first line after the block (exclusive): the next top-level step,
    the first shallower line, or EOF."""
    blocks = []
    for index, line in enumerate(lines):
        match = _STEP_RE.match(line)
        if match:
            blocks.append([int(match.group(2)), len(match.group(1)),
                           index, None])
    if not blocks:
        return []
    top = min(block[1] for block in blocks)
    tops = [block for block in blocks if block[1] == top]
    for pos, block in enumerate(tops):
        if pos + 1 < len(tops):
            block[3] = tops[pos + 1][2]
        else:
            end = len(lines)
            for after in range(block[2] + 1, len(lines)):
                line = lines[after]
                if not line.strip():
                    continue
                if len(line) - len(line.lstrip()) < top:
                    end = after
                    break
            block[3] = end
    return [(block[0], block[1], block[2], block[3]) for block in tops]


def replace_step_in_text(text, step_number, fixed_step):
    """Replace the top-level step ``step_number`` block in the raw
    recipe text with the re-serialized ``fixed_step``.

    Only the step's own lines are re-serialized; every other line of
    the file stays byte-identical (minimal review diff). Returns the
    new text, or ``None`` when the step is absent from the top-level
    steps (nested steps are never repaired)."""
    if not isinstance(fixed_step, dict) or not isinstance(
            fixed_step.get("methods"), list):
        return None
    if "step" not in fixed_step:
        fixed_step = {"step": step_number, **fixed_step}
    if fixed_step.get("step") != step_number:
        return None
    lines = text.splitlines()
    blocks = _top_level_step_blocks(lines)
    match = next((block for block in blocks if block[0] == step_number),
                 None)
    if match is None:
        return None
    _number, indent, start, end = match
    dumped = serialize_step(fixed_step).splitlines()
    body = []
    for pos, line in enumerate(dumped):
        if pos == 0:
            body.append(" " * indent + "- " + line)
        else:
            body.append(" " * (indent + 2) + line)
    new_text = "\n".join(lines[:start] + body + lines[end:])
    if text.endswith("\n"):
        new_text += "\n"
    return new_text


# --- pause context ---------------------------------------------------

def load_pause_context(pause=None, from_run=None, db=None):
    """Load one pause context: ``(ok, error, context)``.

    ``pause`` is a JSON file or a directory (the newest
    ``*_pause.json`` wins); ``from_run`` reads ``Run.pause_context``
    by run id from the local DB."""
    if pause:
        path = Path(pause)
        if path.is_dir():
            files = sorted((p for p in path.glob("*_pause.json")
                            if p.is_file()),
                           key=lambda p: p.stat().st_mtime)
            if not files:
                return False, f"no *_pause.json file in {path}", None
            path = files[-1]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            return False, f"cannot read pause context {path}: {e}", None
        return _check_pause(data)
    if from_run is not None:
        row = db.get_run(from_run)
        if row is None or not row["pause_context"]:
            return False, f"run {from_run} has no pause context", None
        try:
            data = json.loads(row["pause_context"])
        except json.JSONDecodeError as e:
            return False, f"run {from_run} pause context is not JSON: {e}", None
        return _check_pause(data)
    return False, "one of --pause or --from-run is required", None


def _check_pause(data):
    if (not isinstance(data, dict)
            or not isinstance(data.get("step"), dict)
            or data.get("step_number") is None):
        return False, "pause context is missing the failed step", None
    return True, None, data


# --- prompt ----------------------------------------------------------

_ELEMENT_LINES_CAP = 120
_PAGE_TEXT_CAP = 8000


def build_prompt(service, pause, recipe_text):
    """The (system, user) prompt pair. Text-only by design."""
    step = pause.get("step") or {}
    visible = [e for e in pause.get("elements") or []
               if isinstance(e, dict)
               and isinstance(e.get("rect"), dict)
               and e["rect"].get("w", 0) > 0]
    element_lines = []
    for e in visible[:_ELEMENT_LINES_CAP]:
        rect = e["rect"]
        loc = e.get("locator") or {}
        args = ", ".join(f"{k}={v!r}"
                         for k, v in (loc.get("arguments") or {}).items())
        element_lines.append(
            f"{e.get('n')}: {e.get('role')} | {e.get('name')} "
            f"| {int(rect.get('x', 0))},{int(rect.get('y', 0))},"
            f"{int(rect.get('w', 0))},{int(rect.get('h', 0))} "
            f"| {loc.get('locatorType')}({args})")
    page_text = (pause.get("page_text") or "")[:_PAGE_TEXT_CAP]
    error = json.dumps(pause.get("error"), ensure_ascii=False)
    system = (
        "You are the repair doctor of BillCollector, a Playwright-based "
        "bill collection daemon. Recipes are YAML documents whose steps "
        "chain Playwright method calls (locators then one action) that "
        "drive a headless browser per service. A run failed at one step "
        "and paused; you get the failing step, the failure category, and "
        "a snapshot of the page at failure time. Propose the minimal "
        "corrected step.\n"
        "Method vocabulary (Playwright sync API as used by the runner): "
        "locators get_by_role, get_by_label, get_by_text, get_by_title, "
        "get_by_placeholder, get_by_test_id, locator; chain-continuing "
        "first, nth, last, content_frame; actions click, fill, press; "
        "page-level goto, close; expect_download wraps the download "
        "steps. A step is {step, description, methods} plus an optional "
        "\"graceful\": true flag: a graceful step gets one attempt and "
        "its failure does not abort the run - use it for conditional UI "
        "such as a cookie-consent banner that only appears until its "
        "choice is stored. Each method is "
        "{method, arguments} where arguments is a list of single-key "
        "dicts, e.g. {role: button}, {name: Login}, {value: "
        "\"{{PASSWORD}}\"}, {key: Tab}, {selector: \"#login\"}. "
        "Placeholders {{USERNAME}} {{PASSWORD}} {{OTP}} must be kept "
        "verbatim. press takes key (not value); fill takes value; goto "
        "takes url. click, fill and press also accept {force: true} in "
        "arguments - the runner forwards it to the Playwright call and "
        "it skips the actionability checks; the event is still "
        "dispatched at the element's point and routed by normal hit "
        "testing, so force does not click through an interactive "
        "overlay. When a covering banner or dialog is visible in the "
        "snapshot, prefer a graceful step that dismisses it first; use "
        "force: true only when the target is present, visible, and no "
        "covering overlay is identifiable.\n"
        "Reply with exactly one JSON object and nothing else:\n"
        "{\"explanation\": \"at most two sentences\", "
        "\"fix_type\": \"step\" | \"recipe\" | \"none\", "
        "\"step_number\": <int>, "
        "\"fixed_step\": <full replacement step object or null>}\n"
        "Rules: fix_type step = replace only the failing top-level "
        "step (fixed_step carries its step number); fix_type recipe = "
        "the whole document changed (then fixed_step is null and "
        "\"fixed_recipe\": \"<full YAML text>\" is set instead); "
        "fix_type none = no in-place fix exists (portal flow changed "
        "beyond a step edit - say what a human must do). Prefer a "
        "locator that matches an element present in the snapshot; drop "
        "a step whose element is gone; never invent steps beyond the "
        "failing one; keep the step's intent and the following steps "
        "working.")
    user = (
        f"SERVICE: {service}\n"
        f"FAILED STEP NUMBER: {pause.get('step_number')}\n"
        f"ERROR: {error}\n"
        f"PAGE URL: {pause.get('url')}\n"
        f"PAGE TITLE: {pause.get('page_title')}\n\n"
        f"FAILING STEP (JSON):\n"
        f"{json.dumps(step, ensure_ascii=False, indent=1)}\n\n"
        f"CURRENT RECIPE (YAML):\n---\n{recipe_text}---\n\n"
        f"PAGE ELEMENTS AT FAILURE (visible, "
        f"{len(visible)} total, first {_ELEMENT_LINES_CAP} shown):\n"
        + ("\n".join(element_lines) if element_lines else "(none)")
        + f"\n\nPAGE TEXT (truncated to {_PAGE_TEXT_CAP} chars):\n"
        + page_text
    )
    return system, user


# --- LLM -------------------------------------------------------------

def call_llm(base_url, model, system, user, api_key=None, timeout=120):
    """One OpenAI-compatible chat completion; returns the message text.

    ``base_url`` may be given with or without the /chat/completions
    suffix (Ollama /v1, vLLM, LM Studio, ...)."""
    url = base_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {"model": model, "temperature": 0,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
    response = requests.post(url, json=payload, headers=headers,
                             timeout=timeout)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def parse_llm_response(text):
    """The JSON object of a model reply (fence- and prose-tolerant).

    Raises ValueError when no complete object is present."""
    t = str(text).strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    start = t.find("{")
    if start < 0:
        raise ValueError("no JSON object in LLM reply")
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(t)):
        c = t[i]
        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
        elif c == '"':
            in_string = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return json.loads(t[start:i + 1])
    raise ValueError("unbalanced JSON object in LLM reply")


# --- orchestrator ----------------------------------------------------

def run_doctor(service, pause=None, from_run=None, db=None,
               llm_url=None, llm_model=None, llm_api_key=None,
               prompt_file=None, llm_response=None, out=None,
               apply=False, timeout=120):
    """The doctor CLI body; returns the process exit code.

    0 fix produced (applied with --apply); 1 the LLM says no in-place
    fix exists; 2 usage / LLM / parse / validation error; 3 recipe or
    pause-context load error."""
    path = config.recipe_path_for(service)
    ok, error, recipe_text, recipe_data = recipes.load_recipe(path)
    if not ok:
        print(f"doctor: {error}")
        return 3

    ok, error, pause_ctx = load_pause_context(pause, from_run, db)
    if not ok:
        print(f"doctor: {error}")
        return 3

    system, user = build_prompt(service, pause_ctx, recipe_text)
    if prompt_file:
        Path(prompt_file).write_text(
            f"# SYSTEM PROMPT\n{system}\n\n# USER PROMPT\n{user}\n",
            encoding="utf-8")
        print(f"doctor: prompt written to {prompt_file}")
        return 0

    if llm_response:
        reply = Path(llm_response).read_text(encoding="utf-8")
    else:
        if not llm_url or not llm_model:
            print("doctor: no LLM endpoint - set --llm-url/--llm-model "
                  "or BC_LLM_URL/BC_LLM_MODEL (or use --prompt-file to "
                  "inspect the prompt, --llm-response for a canned "
                  "reply)")
            return 2
        try:
            reply = call_llm(llm_url, llm_model, system, user,
                             api_key=llm_api_key, timeout=timeout)
        except (requests.RequestException, KeyError, ValueError) as e:
            print(f"doctor: LLM call failed: {e}")
            return 2

    try:
        fix = parse_llm_response(reply)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"doctor: cannot parse LLM reply: {e}\n--- reply ---\n{reply}")
        return 2

    fix_type = fix.get("fix_type")
    print(f"doctor: {fix.get('explanation', '').strip()}")
    if fix.get("confidence"):
        print(f"doctor: confidence: {fix['confidence']}")

    if fix_type == "none":
        print("doctor: no in-place fix - the portal flow changed beyond a "
              "step edit (re-author with the codegen helper, or rescue "
              "the run via Copilot/noVNC and fix the recipe by hand)")
        return 1

    if fix_type == "step":
        step_number = fix.get("step_number", pause_ctx.get("step_number"))
        new_text = replace_step_in_text(recipe_text, step_number,
                                        fix.get("fixed_step"))
        if new_text is None:
            print(f"doctor: cannot apply fix to top-level step "
                  f"{step_number} (absent, nested, or malformed "
                  f"fixed_step)")
            return 2
    elif fix_type == "recipe":
        new_text = str(fix.get("fixed_recipe") or "")
    else:
        print(f"doctor: unknown fix_type {fix_type!r} (expected "
              f"step/recipe/none)")
        return 2

    ok, error, _data = recipes.validate_recipe(new_text)
    if not ok:
        print(f"doctor: proposed recipe fails validation: {error}")
        return 2

    for line in difflib.unified_diff(
            recipe_text.splitlines(), new_text.splitlines(),
            fromfile=f"a/{path.name}", tofile=f"b/{path.name}", lineterm=""):
        print(line)

    if apply:
        ok, error = recipes.save_recipe(path, new_text)
        if not ok:
            print(f"doctor: save failed: {error}")
            return 2
        print(f"doctor: saved {path}")
    elif out:
        Path(out).write_text(new_text, encoding="utf-8")
        print(f"doctor: proposed recipe written to {out} "
              f"(recipe file untouched)")
    else:
        print("doctor: dry run - recipe file untouched (use --apply to "
              f"write {path})")
    return 0
