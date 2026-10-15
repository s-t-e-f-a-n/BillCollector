# -*- coding: utf-8 -*-
"""Recipe file handling for the UI (M2 chunk D5.1).

The per-service recipe files stay as git-versioned YAML on disk
(locked decision 7); this module is the UI's clean API over them -
locked decision 5 (no legacy ``BillCollectorCheckRecipe`` import, no
``exit()`` path): load, validate (``yaml.safe_load`` + jsonschema
against ``config.RECIPE_SCHEMA``, structured error text, never
raises), flatten the step tree for the editor's sidebar, the recipe
repair flow's candidate replacement (M3 S2.2: replace the failed
step's locator prefix with a pause-context scan candidate), and save
atomically (a temp file in the same directory + ``os.replace``;
unvalidated text is refused at the write site).
"""

import copy
import os
import tempfile
from pathlib import Path

import jsonschema
import yaml

from . import config


def validate_recipe(text: str, schema_path=None) -> tuple:
    """Parse the YAML ``text`` and validate it against the schema.

    Returns ``(ok, error, data)``; a broken YAML document or a schema
    violation is a result with structured error text, never an
    exception."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return False, f"invalid YAML: {str(e).strip()}", None
    try:
        with open(schema_path or config.RECIPE_SCHEMA, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        validator = jsonschema.Draft7Validator(schema)
        errors = sorted(validator.iter_errors(data),
                        key=lambda e: list(e.absolute_path))
    except (OSError, yaml.YAMLError, jsonschema.SchemaError) as e:
        return False, f"cannot load schema: {e}", None
    if errors:
        return False, "; ".join(
            f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in errors), None
    return True, None, data


def load_recipe(path) -> tuple:
    """Load a recipe file: ``(ok, error, text, data)``.

    ``text`` is the raw file content (None when the file cannot be
    read); ``data`` the parsed + validated document (None when the file
    is missing or does not validate)."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return False, f"cannot read recipe: {e}", None, None
    ok, error, data = validate_recipe(text)
    if not ok:
        return False, error, text, None
    return True, None, text, data


def _method_text(method) -> str:
    """One method entry as ``name(k=v, ...)`` for the step-tree sidebar."""
    if not isinstance(method, dict):
        return "?"
    name = method.get("method", "?")
    args = []
    for arg in method.get("arguments") or []:
        if isinstance(arg, dict):
            args.extend(f"{k}={v}" for k, v in arg.items())
    if args:
        return f"{name}({', '.join(args)})"
    return name


def _step_entry(step, depth: int = 0) -> dict:
    """One node of the step tree: number, description, graceful flag,
    the methods (with arguments), and the nested steps (the
    ``expect_download`` body) as ``children``."""
    step = step if isinstance(step, dict) else {}
    return {
        "number": step.get("step"),
        "description": step.get("description") or "",
        "graceful": bool(step.get("graceful")),
        "methods": [_method_text(m) for m in step.get("methods") or []],
        "depth": depth,
        "children": [_step_entry(s, depth + 1) for s in step.get("steps") or []],
    }


def parse_steps(data) -> list:
    """Flatten the recipe's step tree for the editor sidebar (D5.3).

    One entry per step of every service (top-level steps first, nested
    ``expect_download`` steps carried as ``children`` with
    ``depth`` +1); a non-recipe document yields an empty list."""
    if not isinstance(data, dict):
        return []
    steps = []
    for service in data.get("services") or []:
        if not isinstance(service, dict):
            continue
        for step in service.get("steps") or []:
            steps.append(_step_entry(step))
    return steps


# Methods that end a step's locator chain: the element actions
# (click/fill/press), the page-level methods (goto/close), and the
# special step methods (expect_download, wait_user). Everything before
# the first of these is the step's locator prefix - the locator
# methods plus the chain-continuing methods (first, content_frame, ...)
# that still produce the locator (or frame) the actions act on. The
# runner's pause-context heuristic (transform_step_to_json) also calls
# first/content_frame "actions"; for the repair flow they belong to the
# chain, because the candidate is the full locator of the real element
# and replaces the whole chain (decision 7).
_CHAIN_END_METHODS = frozenset({
    "click", "fill", "press", "goto", "close",
    "expect_download", "wait_user",
})


def _candidate_method_entry(candidate):
    """The recipe method entry of one scan candidate.

    ``{"locatorType": "get_by_role", "arguments": {...}}`` becomes
    ``{"method": "get_by_role", "arguments": [{...}, ...]}`` - one
    single-key dict per argument, in the candidate's key order (the
    recipe's list-of-single-key-dicts method shape). None when the
    candidate is malformed (not a dict, no usable locatorType, or
    arguments that are not a dict)."""
    if not isinstance(candidate, dict):
        return None
    locator_type = candidate.get("locatorType")
    if not isinstance(locator_type, str) or not locator_type:
        return None
    arguments = candidate.get("arguments") or {}
    if not isinstance(arguments, dict):
        return None
    entry = {"method": locator_type}
    if arguments:
        entry["arguments"] = [{key: value} for key, value in arguments.items()]
    return entry


def _locator_prefix_len(step) -> int:
    """The number of leading locator-prefix methods of a step.

    The prefix runs up to (not including) the first chain-ending
    method; 0 means the step has no locator prefix (no methods, or the
    first method ends the chain - goto/close/expect_download/
    wait_user)."""
    count = 0
    for method_entry in step.get("methods") or []:
        name = method_entry.get("method") if isinstance(method_entry, dict) else None
        if name in _CHAIN_END_METHODS:
            break
        count += 1
    return count


def _find_repair_step(recipe_data, step_number):
    """The top-level step ``step_number`` can be candidate-repaired:
    ``(service_index, step_index, step)``; None otherwise (a non-recipe
    document, a non-int step number, the number missing from the
    top-level steps - nested ``expect_download`` steps are never
    repaired - or a step with no locator prefix). The first step with
    the number decides, so a prefix-less step is never skipped for a
    later same-numbered step."""
    if not isinstance(recipe_data, dict):
        return None
    if isinstance(step_number, bool) or not isinstance(step_number, int):
        return None
    for service_index, service in enumerate(recipe_data.get("services") or []):
        if not isinstance(service, dict):
            continue
        for step_index, step in enumerate(service.get("steps") or []):
            if isinstance(step, dict) and step.get("step") == step_number:
                if _locator_prefix_len(step) > 0:
                    return service_index, step_index, step
                return None
    return None


def repair_target(recipe_data, step_number):
    """The step a candidate replacement applies to (M3 S2.3) - the
    picker's not-applicable check (decision 7): the top-level step
    ``step_number`` when it carries a locator prefix, else None (a
    non-recipe document, a non-int/missing step number, a step absent
    from the top-level steps - nested ``expect_download`` steps are
    never repaired - or a step with no locator prefix: the goto/close/
    expect_download/wait_user steps). Read-only: the document is never
    mutated."""
    found = _find_repair_step(recipe_data, step_number)
    return found[2] if found is not None else None


def apply_candidate_to_step(recipe_data, step_number, candidate):
    """Replace a step's locator prefix with a scan candidate (M3 S2.2).

    The pure core of the recipe repair flow (decision 7): the step's
    locator prefix - the leading run of methods up to the first
    chain-ending method - is replaced by the candidate's locator as a
    single method entry, and the trailing action methods (click/fill/
    press with their arguments, e.g. ``{{PASSWORD}}``) are kept
    unchanged. The candidate's ``arguments`` dict becomes the recipe's
    list of single-key dicts with its key order preserved. Chain-
    continuing methods (``first``, ``content_frame``, ...) are part of
    the prefix: the candidate is the full locator of the real element,
    so a scoped chain (``get_by_role(main)`` -> ``get_by_role(textbox)``)
    is replaced whole; the operator can still fine-tune the rewritten
    YAML (the advanced path).

    ``recipe_data`` is the parsed recipe document (the ``services``
    list); ``step_number`` the top-level step number (the pause
    context's ``step_number``); ``candidate`` the scan entry's
    ``locator`` dict (``locatorType`` + ``arguments``).

    Returns a new document (the input is never mutated) or ``None``
    when not applicable (the picker's YAML-path hint): a malformed
    candidate, or the step is not a repair target (see
    :func:`repair_target`)."""
    entry = _candidate_method_entry(candidate)
    if entry is None:
        return None
    found = _find_repair_step(recipe_data, step_number)
    if found is None:
        return None
    service_index, step_index, step = found
    methods = step.get("methods") or []
    document = copy.deepcopy(recipe_data)
    new_step = document["services"][service_index]["steps"][step_index]
    new_step["methods"] = [entry] + methods[_locator_prefix_len(step):]
    return document


def save_recipe(path, text: str) -> tuple:
    """Atomically write the recipe file: ``(ok, error)``.

    The text is validated first - unvalidated text is refused (the UI
    always validates, but the refusal keeps the guarantee at the write
    site). The write is a temp file in the same directory +
    ``os.replace`` (atomic on the same filesystem), so the recipe file
    is never left half-written."""
    ok, error, _data = validate_recipe(text)
    if not ok:
        return False, error
    path = Path(path)
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp",
                                   dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except OSError as e:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        return False, f"cannot write recipe: {e}"
    return True, None
