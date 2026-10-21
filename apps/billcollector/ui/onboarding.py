# -*- coding: utf-8 -*-
"""First-start onboarding wizard (M4 chunk C2, decision 2).

The ``/onboarding`` page walks a new operator through the three setup
steps that remain after the password was set on ``/login``:

- **Vault** - the vault API URL (+ optional host override) with a
  **Check** button (the same DNS vetting + status check the run preflight
  makes) and **Save** (the Settings keys ``vault_api_url`` /
  ``vault_api_host``; empty is allowed = environment fallback). Skipping
  is allowed but flagged: while no URL resolves, task runs fail at the
  vault preflight.
- **Tasks** - the imported task list with per-task enable toggles (each
  change goes through ``db.update_task`` + ``scheduler.sync_task``), an
  **Import from INI** button (re-runs ``import_ini`` with ``force=True``:
  only (service, user) pairs missing from the table are added), and a
  **New task** form (recipe file + profile dir derived as in the INI
  import).
- **Finish** - a summary and **Finish onboarding** (writes
  ``onboarding_done=1`` and navigates to the dashboard).

While the wizard is active the auth middleware redirects every
authenticated request except ``/onboarding`` to it (M4 C2, decision 1);
serve startup auto-completes it for upgraded installs, so the page is
normally only seen on a fresh first start.
"""

import os

from fastapi import Request
from nicegui import ui

from .. import config
from ..db import Database
from ..scheduler import TaskScheduler
from ..vault import (
    VAULT_MAX_ATTEMPTS,
    VAULT_RETRY_BACKOFF,
    VaultAPIError,
    bitwarden_api_check_status,
)
from vault_transport import VaultTransportError, pinned_api_url

from .auth import is_onboarding_active, require_auth
from .layout import build_layout
from .tasks import DEFAULT_CRON, _valid_cron


def register_onboarding(db: Database, scheduler: TaskScheduler) -> None:
    """Register the onboarding wizard (``/onboarding``)."""

    @ui.page("/onboarding", title="Onboarding")
    def onboarding_page(request: Request) -> None:
        redirect = require_auth(request)
        if redirect is not None:
            return redirect
        build_layout(active="")

        ui.label("Onboarding").classes("text-h6")

        if not is_onboarding_active(db):
            ui.label("Onboarding is already complete.").mark("onb-done")
            ui.button("Go to the dashboard",
                      on_click=lambda: ui.navigate.to("/")).mark("onb-goto")
            return

        ui.label(
            "Set up BillCollector: the vault, your tasks, and a final "
            "check. You can skip a step and fix it later in Settings."
        ).classes("text-grey-6")

        effective_url, effective_host = config.vault_settings(db)

        stepper = ui.stepper() \
            .classes("w-full").props("padding='8px' header-nav")
        with stepper:
            # ---- Step 1: Vault --------------------------------------------
            with ui.step("Vault", "Vault"):
                ui.label("Vaultwarden (bw serve) API").classes("text-subtitle1")
                ui.label(
                    "The local vault API the runs read their portal "
                    "credentials from (must be a local http:// URL)."
                ).classes("text-grey-6")
                vault_url_input = ui.input(
                    label="Vault API URL", value=effective_url) \
                    .classes("w-96").mark("onb-vault-url")
                vault_host_input = ui.input(
                    label="Vault API host (optional)", value=effective_host) \
                    .classes("w-96").mark("onb-vault-host")
                vault_warning = ui.label(
                    "No vault API URL (neither saved nor in the "
                    "environment): task runs will fail at the vault "
                    "preflight until you set one. You can continue and "
                    "fix it later in Settings."
                ).classes("text-orange-8 text-sm").mark("onb-vault-warning")

                def refresh_warning() -> None:
                    vault_warning.visible = \
                        not str(vault_url_input.value or "").strip()

                refresh_warning()

                with ui.row().classes("gap-2"):
                    check_btn = ui.button("Check").mark("onb-vault-check")
                    save_btn = ui.button("Save").mark("onb-vault-save")

                def on_check(_e=None) -> None:
                    """DNS vetting + status check of the entered values.

                    The entered pair is exported into the process
                    environment for the duration of the check only (the
                    transport reads BW_API_HOST from the environment);
                    the previous values are restored afterwards, so
                    unsaved values never leak into later runs."""
                    api_url = str(vault_url_input.value or "").strip()
                    if not api_url:
                        ui.notify("Enter a vault API URL to check",
                                  type="negative")
                        return
                    saved_env = {name: os.environ.get(name)
                                 for name in ("BW_API_URL", "BW_API_HOST")}
                    os.environ["BW_API_URL"] = api_url
                    os.environ["BW_API_HOST"] = \
                        str(vault_host_input.value or "").strip()
                    try:
                        pinned_api_url(api_url, VAULT_MAX_ATTEMPTS,
                                       VAULT_RETRY_BACKOFF)
                        ok, status = bitwarden_api_check_status(api_url)
                    except (VaultTransportError, VaultAPIError) as exc:
                        ui.notify(str(exc), type="negative")
                        return
                    finally:
                        for name, value in saved_env.items():
                            if value is None:
                                os.environ.pop(name, None)
                            else:
                                os.environ[name] = value
                    if not ok:
                        ui.notify(
                            "Vault check failed: the status endpoint did "
                            "not answer", type="negative")
                        return
                    if status == "unlocked":
                        ui.notify("Vault reachable and unlocked",
                                  type="positive")
                    else:
                        ui.notify("Vault reachable but locked: unlock the "
                                  "vault in Vaultwarden", type="warning")

                def on_vault_save(_e=None) -> None:
                    db.set_setting("vault_api_url",
                                   str(vault_url_input.value or "").strip())
                    db.set_setting("vault_api_host",
                                   str(vault_host_input.value or "").strip())
                    refresh_warning()
                    ui.notify("Vault settings saved", type="positive")

                check_btn.on("click", on_check)
                save_btn.on("click", on_vault_save)

                with ui.stepper_navigation().classes("items-center"):
                    continue_btn = ui.button("Continue").mark(
                        "onb-continue-vault")

                def on_continue_vault(_e=None) -> None:
                    """Move to the tasks step (the vault is optional)."""
                    stepper.value = "Tasks"

                continue_btn.on("click", on_continue_vault)

            # ---- Step 2: Tasks --------------------------------------------
            with ui.step("Tasks", "Tasks"):
                ui.label("Tasks").classes("text-subtitle1")
                ui.label(
                    "Import the tasks from your INI file or create one "
                    "manually, then enable the tasks the daemon should "
                    "run on schedule."
                ).classes("text-grey-6")
                tasks_box = ui.column().classes("w-full gap-1")

                def render_tasks() -> None:
                    tasks_box.clear()
                    with tasks_box:
                        tasks = db.list_tasks()
                        if not tasks:
                            ui.label(
                                "No tasks yet: import from INI or add one "
                                "below."
                            ).classes("text-grey-6").mark("onb-no-tasks")
                        for task in tasks:
                            with ui.row().classes("w-full items-center gap-3"):
                                ui.label(
                                    f"#{task['id']} · {task['service']} / "
                                    f"{task['user'] or '—'}"
                                ).classes("w-56")
                                ui.label(task["cron"] or "—") \
                                    .classes("w-32 text-grey-6")
                                recipe = config.recipe_path_for(
                                    task["service"])
                                ui.label(
                                    recipe.name
                                    + ("" if recipe.exists()
                                       else " (missing)")
                                ).classes("w-64 text-grey-6")
                                toggle = ui.switch(
                                    value=bool(task["enabled"])) \
                                    .mark(f"onb-toggle-{task['id']}")

                                def on_toggle(_e=None, task_id=task["id"]) \
                                        -> None:
                                    task = db.get_task(task_id)
                                    if task is None:
                                        return
                                    enabled = int(bool(toggle.value))
                                    db.update_task(task_id, enabled=enabled)
                                    scheduler.sync_task(task_id)
                                    state = "enabled" if enabled else "disabled"
                                    ui.notify(
                                        f"Task {task['service']} / "
                                        f"{task['user'] or '—'} {state}",
                                        type="positive")

                                toggle.on_value_change(on_toggle)

                render_tasks()

                import_btn = ui.button("Import from INI").mark(
                    "onb-import-ini")

                def on_import(_e=None) -> None:
                    """Re-import the INI: only pairs missing from the Task
                    table are added (the duplicate guard still applies),
                    including ones the user deleted (M4 C2, decision 2)."""
                    created = db.import_ini(force=True)
                    render_tasks()
                    ui.notify(
                        f"INI import: {created} task(s) added (existing "
                        "tasks left untouched)", type="positive")

                import_btn.on("click", on_import)

                with ui.column().classes("w-full gap-2"):
                    ui.label("New task").classes("text-subtitle1")
                    with ui.row().classes("items-end gap-2"):
                        service_input = ui.input(label="Service") \
                            .classes("w-40").mark("onb-task-service")
                        user_input = ui.input(label="User") \
                            .classes("w-40").mark("onb-task-user")
                        cron_input = ui.input(label="Cron",
                                              value=DEFAULT_CRON) \
                            .classes("w-40").mark("onb-task-cron")
                        enabled_switch = ui.switch("Enabled") \
                            .mark("onb-task-enabled")
                        add_btn = ui.button("Add task").mark("onb-add-task")

                def on_add_task(_e=None) -> None:
                    service = str(service_input.value or "").strip()
                    user_ = str(user_input.value or "").strip()
                    cron = str(cron_input.value or "").strip() or DEFAULT_CRON
                    if not service:
                        ui.notify("Service is required", type="negative")
                        return
                    if not _valid_cron(cron):
                        ui.notify(f"Invalid cron expression: {cron!r}",
                                  type="negative")
                        return
                    if db.get_task_by_service_user(service, user_) is not None:
                        ui.notify(
                            f"Task {service} / {user_ or '—'} already "
                            "exists", type="warning")
                        return
                    new_id = db.create_task(
                        service, user_,
                        recipe_file=str(config.recipe_path_for(service)),
                        enabled=bool(enabled_switch.value), cron=cron,
                        profile_dir=str(
                            config.profile_dir_for(service, user_)))
                    scheduler.sync_task(new_id)
                    service_input.value = ""
                    user_input.value = ""
                    render_tasks()
                    ui.notify(f"Task {service} / {user_ or '—'} added",
                              type="positive")
                    recipe = config.recipe_path_for(service)
                    if not recipe.exists():
                        ui.notify(
                            f"Recipe file {recipe.name} is missing: the "
                            "run will fail until a recipe exists",
                            type="warning")

                add_btn.on("click", on_add_task)

                with ui.stepper_navigation().classes("items-center"):
                    back_btn = ui.button("Back").props("flat").mark(
                        "onb-back-tasks")
                    continue_btn = ui.button("Continue").mark(
                        "onb-continue-tasks")

                def on_back_tasks(_e=None) -> None:
                    stepper.value = "Vault"

                def on_continue_tasks(_e=None) -> None:
                    stepper.value = "Finish"

                back_btn.on("click", on_back_tasks)
                continue_btn.on("click", on_continue_tasks)

            # ---- Step 3: Finish -------------------------------------------
            with ui.step("Finish", "Finish"):
                ui.label("Finish").classes("text-subtitle1")

                tasks = db.list_tasks()
                enabled = sum(1 for t in tasks if t["enabled"])
                missing = sum(
                    1 for t in tasks
                    if not config.recipe_path_for(t["service"]).exists())
                vault_state, _host = config.vault_settings(db)
                vault_note = vault_state or (
                    "not configured (runs will fail at the vault preflight)")
                ui.label(
                    f"{len(tasks)} task(s), {enabled} enabled, "
                    f"{missing} with a missing recipe file. "
                    f"Vault API URL: {vault_note}."
                ).classes("text-sm").mark("onb-summary")
                ui.label(
                    "After finishing you can change everything in "
                    "Settings (the ntfy topic, the deep-link base URL, the "
                    "vault API) and on the dashboard (per-task cron and "
                    "enabled)."
                ).classes("text-grey-6 text-sm")
                with ui.stepper_navigation().classes("items-center"):
                    back_btn = ui.button("Back").props("flat").mark(
                        "onb-back-finish")
                    finish_btn = ui.button("Finish onboarding").mark(
                        "onb-finish")

                def on_back_finish(_e=None) -> None:
                    stepper.value = "Tasks"

                def on_finish(_e=None) -> None:
                    db.set_setting("onboarding_done", "1")
                    ui.navigate.to("/")

                back_btn.on("click", on_back_finish)
                finish_btn.on("click", on_finish)
