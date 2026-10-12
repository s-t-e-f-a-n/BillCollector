# -*- coding: utf-8 -*-
"""Task management for the daemon UI (M2 chunk D3.3).

Task CRUD lives on the dashboard as dialogs (no separate page in M2): the
toolbar **Add task** button opens the create dialog (service, user, cron
defaulting to ``0 0 1 * *``, enabled switch; the per-service recipe file
is derived from the service, shown read-only, and a missing file warns
but does not block creation - locked decision 9), and a row **Edit**
button opens the same dialog for an existing task (service/user
read-only, cron + enabled editable - the enabled switch is the
enable/disable toggle). Both render their content in a fixed-width
card, since a bare ``q-dialog`` floats its children over the
darkened backdrop where the fields are barely readable. Every change
goes through
``db.create_task`` / ``db.update_task`` + ``scheduler.sync_task`` (the
single task-change hook, C7.1). There is no task deletion in M2:
disabling is the off switch.
"""

from apscheduler.triggers.cron import CronTrigger
from nicegui import ui

from .. import config
from ..db import Database
from ..scheduler import TaskScheduler

# The cron a new task gets (locked decision 9).
DEFAULT_CRON = "0 0 1 * *"


def _valid_cron(cron: str) -> bool:
    """True when the string parses as a 5-field crontab expression
    (the same parser APScheduler uses for the job trigger)."""
    try:
        CronTrigger.from_crontab(cron)
        return True
    except ValueError:
        return False


def open_task_dialog(db: Database, scheduler: TaskScheduler, refresh,
                     task_id: int | None = None) -> None:
    """Open the create dialog (``task_id`` None) or the edit dialog.

    The content renders in a fixed-width card: a bare ``q-dialog`` floats
    its children over the darkened backdrop, where the labelled fields
    are barely readable and their widths collapse, so the card gives
    them a solid, roomy surface. ``refresh`` re-renders the dashboard
    table so the change is visible without waiting for the ~2 s poll."""
    task = db.get_task(task_id) if task_id is not None else None

    with ui.dialog() as dialog, ui.card().classes("w-96"):
        dialog.open()
        if task is None:
            ui.label("New task").classes("text-h6")
            ui.label("The recipe is shared by all tasks of a service "
                     "(per-service recipe file).").classes("text-grey-6")
            service_input = ui.input(label="Service").classes("w-full") \
                .mark("task-service")
            user_input = ui.input(label="User").classes("w-full") \
                .mark("task-user")
            cron_input = ui.input(label="Cron", value=DEFAULT_CRON) \
                .classes("w-full").mark("task-cron")
            enabled_switch = ui.switch("Enabled").mark("task-enabled")
            recipe_label = ui.label().classes("w-full text-grey-6") \
                .mark("task-recipe")

            def update_recipe_label(_e=None) -> None:
                service = (service_input.value or "").strip()
                if not service:
                    recipe_label.text = "Recipe (shared): —"
                    return
                path = config.recipe_path_for(service)
                state = "" if path.exists() else " (missing)"
                recipe_label.text = f"Recipe (shared): {path.name}{state}"

            service_input.on_value_change(update_recipe_label)
            update_recipe_label()
        else:
            ui.label(f"Edit task: {task['service']} / {task['user'] or '—'}"
                     ).classes("text-h6")
            service_input = None
            user_input = None
            cron_input = ui.input(label="Cron",
                                  value=task["cron"] or DEFAULT_CRON) \
                .classes("w-full").mark("task-cron")
            enabled_switch = ui.switch("Enabled",
                                       value=bool(task["enabled"])) \
                .mark("task-enabled")
            recipe = config.recipe_path_for(task["service"])
            state = "" if recipe.exists() else " (missing)"
            ui.label(f"Recipe (shared, read-only): {recipe.name}{state}"
                     ).classes("text-grey-6").mark("task-recipe")

        with ui.row().classes("w-full justify-end items-center gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            save_btn = ui.button("Save").mark("task-save").props("color=primary")

        def on_save() -> None:
            cron = (cron_input.value or "").strip() or None
            enabled = bool(enabled_switch.value)
            if cron is not None and not _valid_cron(cron):
                ui.notify(f"Invalid cron expression: {cron!r}", type="negative")
                return
            if task is None:
                service = (service_input.value or "").strip()
                if not service:
                    ui.notify("Service is required", type="negative")
                    return
                user = (user_input.value or "").strip()
                if db.get_task_by_service_user(service, user) is not None:
                    ui.notify(f"Task {service} / {user or '—'} already exists",
                              type="warning")
                    return
                recipe = config.recipe_path_for(service)
                new_id = db.create_task(
                    service, user,
                    recipe_file=str(recipe),
                    enabled=enabled, cron=cron,
                    profile_dir=str(config.profile_dir_for(service, user)))
                scheduler.sync_task(new_id)
                ui.notify(f"Task {service} / {user or '—'} created")
                if not recipe.exists():
                    ui.notify(f"Recipe file {recipe.name} is missing: the run "
                              "will fail until a recipe exists", type="warning")
            else:
                db.update_task(task_id, cron=cron, enabled=int(enabled))
                scheduler.sync_task(task_id)
                ui.notify(f"Task {task['service']} / {task['user'] or '—'} "
                          "updated")
            refresh()
            dialog.close()

        save_btn.on("click", on_save)
