# -*- coding: utf-8 -*-
"""Recipe file handling for the UI (M2 chunk D5.1).

The per-service recipe files stay as git-versioned YAML on disk
(locked decision 7); this module is the UI's clean API over them -
locked decision 5 (no legacy ``BillCollectorCheckRecipe`` import, no
``exit()`` path): load, validate (``yaml.safe_load`` + jsonschema
against ``config.RECIPE_SCHEMA``, structured error text, never
raises), flatten the step tree for the editor's sidebar, and save
atomically (a temp file in the same directory + ``os.replace``;
unvalidated text is refused at the write site).
"""

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
