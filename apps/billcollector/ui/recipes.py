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
"""

import yaml
from fastapi import Request
from nicegui import ui

from .. import config, gitcommit
from ..db import Database
from ..orchestrator import Orchestrator
from ..recipes import load_recipe, parse_steps, save_recipe, validate_recipe
from .auth import require_auth
from .layout import build_layout

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
