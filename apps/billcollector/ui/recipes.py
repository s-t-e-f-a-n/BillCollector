# -*- coding: utf-8 -*-
"""The per-service recipe editor page (M2 chunk D5.3).

``/recipes/<service>``: a CodeMirror YAML editor that loads the
per-service recipe file (shared by all tasks of the service - shown
explicitly with the service's task list), a read-only step-tree sidebar
(D5.1 ``parse_steps``, re-parsed on edit, a broken YAML document is
marked instead of rendered), **Validate** (inline result, run again on
save), and **Save** = validate -> ``save_recipe`` -> ``git_commit``
with the message ``recipe(<service>): <summary>`` when
``git_commit_enabled`` (the summary is the first changed service
description, else "edited via UI", locked decision 13). After a
successful save the page offers a **Run now** button per task of the
service (the D3 action, one click away).

M3 chunk S2.3 (decision 7): opened with ``?run=<run_id>`` (the
session page's **Repair recipe** link), the editor preloads the
**failure panel** from the run's ``pause_context``: the failure
screenshot (``/runfiles`` URL), the failed step (number, description,
expected locator chain, error), and the candidate rows (n, role, name,
locator type) each with a **Use** button. **Use** replaces the failed
step's locator prefix with the candidate's locator
(``apply_candidate_to_step``) and the editor reloads with the
rewritten YAML - the operator can fine-tune, then the existing
Validate -> Save -> git commit flow. Not applicable (the picker is
disabled with a hint, the YAML path): a non-``step_failed`` pause
(``wait_user``, ``download_failed``), a missing/corrupt context, a
context without a step number, or a step the replacement does not
apply to (no locator prefix, nested ``expect_download`` step).
"""

import json

import yaml
from fastapi import Request
from nicegui import ui

from .. import config, gitcommit
from ..db import Database
from ..orchestrator import Orchestrator
from ..recipes import (apply_candidate_to_step, load_recipe, parse_steps,
                       repair_target, save_recipe, validate_recipe)
from .auth import require_auth
from .layout import build_layout
from .runfiles import runfile_url

# The truthy spellings of the git_commit_enabled setting (a TEXT value).
_TRUTHY = ("1", "true", "yes", "on")


def _commit_summary(old_data, new_data) -> str:
    """The commit summary (locked decision 13): the first changed
    service description (a new service counts as changed), else
    "edited via UI"."""
    old = {}
    if isinstance(old_data, dict):
        for s in old_data.get("services") or []:
            if isinstance(s, dict):
                old[s.get("serviceName")] = s.get("description") or ""
    if isinstance(new_data, dict):
        for s in new_data.get("services") or []:
            if not isinstance(s, dict):
                continue
            desc = s.get("description") or ""
            if old.get(s.get("serviceName")) != desc:
                return desc or "edited via UI"
    return "edited via UI"


def failure_panel_data(run) -> dict:
    """The failure panel data (M3 S2.3), parsed from
    ``Run.pause_context``: the pause's ``reason``, the failed step's
    ``step_number`` and parsed step info (description, the expected
    locator chain), the error, the screenshot's ``/runfiles`` URL, and
    the candidate rows (n, role, name, locator type + the raw
    ``locator`` dict for ``apply_candidate_to_step``).

    ``context`` is None when the column is empty or the JSON is
    corrupt (the panel renders its hint instead); the row's other
    fields degrade to None / [] so a broken context never kills the
    editor."""
    context = None
    if run is not None and run["pause_context"]:
        try:
            context = json.loads(run["pause_context"])
        except (TypeError, ValueError):
            context = None
    if not isinstance(context, dict):
        context = None
    if context is None:
        return {"context": None, "reason": None, "step_number": None,
                "step": None, "error": None, "shot_url": None,
                "candidates": []}
    step = context.get("step")
    shot = context.get("screenshot")
    shot_path = shot.get("path") if isinstance(shot, dict) else None
    candidates = []
    for el in context.get("elements") or []:
        if not isinstance(el, dict):
            continue
        locator = el.get("locator")
        if not isinstance(locator, dict):
            continue
        candidates.append({
            "n": el.get("n"),
            "role": el.get("role"),
            "name": el.get("name"),
            "locator_type": locator.get("locatorType"),
            "locator": locator,
        })
    return {
        "context": context,
        "reason": context.get("reason"),
        "step_number": context.get("step_number"),
        "step": step if isinstance(step, dict) else None,
        "error": context.get("error"),
        "shot_url": runfile_url(shot_path),
        "candidates": candidates,
    }


def _locator_text(entry) -> str:
    """One expected-locator entry of the pause context's parsed step
    (``{"locator": name, "arguments": {...}}``) as ``name(k=v, ...)`` -
    the step-tree sidebar's method format (the failure panel's expected
    locator chain, M3 S2.3)."""
    if not isinstance(entry, dict):
        return "?"
    name = entry.get("locator", "?")
    args = entry.get("arguments") or {}
    if isinstance(args, dict) and args:
        return f"{name}({', '.join(f'{k}={v}' for k, v in args.items())})"
    return name


def _render_step(container, entry) -> None:
    """One step-tree node (and its nested children): the step line
    (graceful steps flagged) and one line per method."""
    indent = "    " * entry["depth"]
    title = f"#{entry['number'] or '?'} {entry['description'] or '—'}"
    if entry["graceful"]:
        title += " (graceful)"
    with container:
        ui.label(indent + title).classes("text-grey-9")
        for method in entry["methods"]:
            ui.label(indent + "  " + method).classes(
                "text-grey-6 text-xs font-mono")
    for child in entry["children"]:
        _render_step(container, child)


def register_recipe_editor(db: Database, orchestrator: Orchestrator) -> None:
    """Register the recipe editor page (``/recipes/<service>``)."""

    @ui.page("/recipes/{service}", title="Recipe editor")
    def recipe_page(request: Request, service: str) -> None:
        redirect = require_auth(request)
        if redirect is not None:
            return redirect
        build_layout()

        path = config.recipe_path_for(service)
        _ok, _error, text, old_data = load_recipe(path)
        state = "" if path.exists() else " (missing)"
        tasks = [t for t in db.list_tasks() if t["service"] == service]

        with ui.row().classes("w-full items-center gap-3"):
            ui.label(f"Recipe: {service}").classes("text-h6")
            ui.label(f"{path.name}{state}").classes("text-grey-6")
        ui.label("The recipe is shared by all tasks of this service."
                 ).classes("text-grey-6")
        if tasks:
            task_list = ", ".join(
                f"{t['service']} / {t['user'] or '—'}" for t in tasks)
            ui.label(f"Tasks: {task_list}").classes("text-grey-7") \
                .mark("recipe-tasks")

        # ---- Failure panel (?run=<run_id>, M3 S2.3, decision 7) ----------
        run_param = request.query_params.get("run")
        try:
            run_id = int(run_param) if run_param is not None else None
        except (TypeError, ValueError):
            run_id = None
        repair_run = db.get_run(run_id) if run_id is not None else None
        panel = (failure_panel_data(repair_run)
                 if repair_run is not None else None)
        repair_hint = None
        if panel is not None:
            if panel["context"] is None:
                repair_hint = ("No usable pause context for this run; "
                               "edit the YAML below.")
            elif panel["reason"] != "step_failed":
                repair_hint = (
                    f"This pause is a "
                    f"{panel['reason'] or 'pause without a reason'}, "
                    "not a step failure; the candidate picker does not "
                    "apply - edit the YAML below.")
            elif repair_target(old_data, panel["step_number"]) is None:
                repair_hint = ("The failed step cannot be "
                               "candidate-repaired (missing from the "
                               "recipe, a nested step, or no locator "
                               "prefix); edit the YAML below.")
            elif not panel["candidates"]:
                repair_hint = ("No candidate elements in the pause "
                               "context; edit the YAML below.")

        def on_use(candidate: dict) -> None:
            """The candidate row's **Use** (M3 S2.3, decision 7): the
            editor's current YAML is parsed and the failed step's
            locator prefix is replaced with the candidate's locator
            (``apply_candidate_to_step``); the editor reloads with the
            rewritten YAML (the operator can fine-tune - the advanced
            path), then the existing Validate -> Save flow applies."""
            try:
                doc = yaml.safe_load(editor.value)
            except yaml.YAMLError as e:
                set_result(f"invalid YAML in the editor: {str(e).strip()}",
                           False)
                return
            new_doc = apply_candidate_to_step(doc, panel["step_number"],
                                              candidate["locator"])
            if new_doc is None:
                set_result("The candidate does not apply to the current "
                           "editor content; edit the YAML directly.",
                           False)
                return
            editor.value = yaml.safe_dump(new_doc, sort_keys=False,
                                          width=4096, allow_unicode=True)
            render_tree()
            set_result(f"Step {panel['step_number']} locator replaced with "
                       f"{candidate['locator_type']}; review, then "
                       "Validate and Save.", True)

        if panel is not None:
            step_no = panel["step_number"]
            step_label = f"Step {step_no if step_no is not None else '?'}"
            if panel["step"] is not None and panel["step"].get("description"):
                step_label += f": {panel['step']['description']}"
            with ui.card().classes("w-full bg-red-50") \
                    .mark("recipe-failure"):
                ui.label(f"Failure (run {repair_run['id']})") \
                    .classes("text-red-900 text-h6") \
                    .mark("recipe-failure-title")
                if panel["shot_url"]:
                    ui.image(panel["shot_url"]).classes("max-h-[24rem]") \
                        .mark("recipe-failure-shot")
                if panel["step"] is not None:
                    ui.label(step_label).classes("text-red-900") \
                        .mark("recipe-failure-step")
                    for loc in panel["step"].get("locators") or []:
                        ui.label(_locator_text(loc)).classes(
                            "text-sm font-mono text-grey-8") \
                            .mark("recipe-failure-locator")
                if panel["error"]:
                    ui.label(f"Error: {panel['error']}").classes(
                        "text-red-800").mark("recipe-failure-error")
                if repair_hint:
                    ui.label(repair_hint).classes("text-grey-7") \
                        .mark("recipe-repair-hint")
                for cand in panel["candidates"]:
                    with ui.row().classes("items-center gap-2") \
                            .mark("recipe-candidate-row"):
                        ui.label(
                            f"{cand['n']} · {cand['role']} · "
                            f"{cand['name']} ({cand['locator_type']})"
                        ).classes("text-sm").mark("recipe-candidate")
                        use_btn = ui.button("Use").props("no-caps dense") \
                            .mark(f"recipe-use-{cand['n']}")
                        if repair_hint is None:
                            use_btn.on("click",
                                       lambda _e, c=cand: on_use(c))
                        else:
                            use_btn.disable()

        with ui.row().classes("w-full gap-4 items-start"):
            with ui.column().classes("w-72 shrink-0 gap-2"):
                ui.label("Step tree").classes("text-subtitle1")
                tree_body = ui.column().classes("w-full gap-1 text-sm")
            with ui.column().classes("flex-grow items-start gap-2"):
                editor = ui.codemirror(
                    value=text or "", language="YAML"
                ).classes("w-full h-[480px]").mark("recipe-editor")
                result_label = ui.label().mark("recipe-result")
                with ui.row().classes("gap-2"):
                    validate_btn = ui.button("Validate").mark("recipe-validate")
                    save_btn = ui.button("Save").mark("recipe-save").props(
                        "color=primary")
                run_section = ui.column().classes("w-full")

        def render_tree() -> None:
            """Re-parse the editor content into the step-tree sidebar;
            a YAML parse failure is marked instead of rendered."""
            tree_body.clear()
            with tree_body:
                try:
                    doc = yaml.safe_load(editor.value)
                except yaml.YAMLError as e:
                    ui.label(f"(YAML parse error: {str(e).strip()})").classes(
                        "text-red-600").mark("recipe-tree-error")
                    return
                steps = parse_steps(doc)
                if not steps:
                    ui.label("(no steps)").classes("text-grey-6")
                    return
                for step in steps:
                    _render_step(tree_body, step)

        def set_result(message: str, ok: bool) -> None:
            result_label.text = message
            result_label.classes(
                replace="text-green-700" if ok else "text-red-600")

        def on_validate(_e=None) -> None:
            ok, error, _data = validate_recipe(editor.value)
            set_result("Valid." if ok else error, ok)

        def build_run_section() -> None:
            """After a successful save: one Run now button per task of
            the service (the D3 action, one click away)."""
            run_section.clear()
            current = [t for t in db.list_tasks() if t["service"] == service]
            if not current:
                return
            with run_section:
                ui.label("Run now:").classes("text-subtitle1")
                with ui.row().classes("gap-2"):
                    for task in current:
                        btn = ui.button(
                            f"{task['user'] or '—'}: Run now").mark("recipe-run-now")

                        async def on_run(_e=None, tid=task["id"],
                                         label=task["user"] or "—") -> None:
                            started = await orchestrator.start_run(tid)
                            if not started:
                                ui.notify(
                                    f"{label}: not started (already "
                                    "running/waiting?)", type="warning")

                        btn.on("click", on_run)

        def on_save(_e=None) -> None:
            """Save = validate -> save_recipe -> git_commit (when
            enabled). Validation failure writes nothing."""
            ok, error, new_data = validate_recipe(editor.value)
            if not ok:
                set_result(error, False)
                ui.notify("Recipe does not validate; nothing saved",
                          type="negative")
                return
            ok, error = save_recipe(path, editor.value)
            if not ok:
                set_result(error, False)
                ui.notify(error, type="negative")
                return
            summary = _commit_summary(old_data, new_data)
            if (db.get_setting("git_commit_enabled") or "").strip().lower() \
                    in _TRUTHY:
                ok, out = gitcommit.git_commit(
                    [str(path)], f"recipe({service}): {summary}")
                if ok:
                    set_result(f"Saved and committed: {summary}.", True)
                else:
                    set_result(f"Saved, but git commit failed: {out}", False)
                    ui.notify(f"Git commit failed: {out}", type="negative")
                    return
            else:
                set_result(f"Saved {path.name}.", True)
            render_tree()
            build_run_section()

        editor.on_value_change(render_tree)
        validate_btn.on("click", on_validate)
        save_btn.on("click", on_save)
        render_tree()
