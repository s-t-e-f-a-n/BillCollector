# -*- coding: utf-8 -*-
"""Settings page for the daemon UI (M2 chunk D6.1).

``/settings`` edits the daemon settings stored in the ``Settings`` table
(locked decision 12): the UI password (change, bcrypt hash),
``ntfy_topic``, ``pause_deadline_seconds``, ``max_concurrency`` (takes
effect on the next daemon start - the semaphore is built at
construction), ``git_commit_enabled``, ``download_dir``,
``display_start``, ``ui_base_url``, and ``vnc_password``. Each field
writes its own Settings row on save (a ``ui.notify`` confirms), so a
field that fails validation (non-integer, non-positive, or empty where
required) is the only one not written.
"""

from fastapi import Request
from nicegui import ui

from ..db import Database
from .auth import MIN_PASSWORD_LENGTH, hash_password, require_auth, set_password_hash
from .layout import build_layout

# (key, label, kind, hint): one row per daemon setting. ``kind`` drives
# the input element and the validation: ``text`` (non-empty), ``int``
# (positive integer), ``password`` (any value, empty allowed).
FIELDS = (
    ("ntfy_topic", "ntfy topic", "text", ""),
    ("pause_deadline_seconds", "Pause deadline (seconds)", "int", ""),
    ("max_concurrency", "Max concurrency", "int",
     "Takes effect on the next daemon start."),
    ("display_start", "Display start", "int", ""),
    ("download_dir", "Download directory", "text", ""),
    ("ui_base_url", "UI base URL", "text", ""),
    ("vnc_password", "VNC password", "password", ""),
)


def _validate(key: str, kind: str, value):
    """Normalize a field value for the Settings table.

    Returns the string to store, or ``None`` when the value is invalid
    (the caller surfaces the error and writes nothing)."""
    if kind == "int":
        try:
            number = int(str(value).strip())
        except ValueError:
            return None
        return str(number) if number > 0 else None
    if kind == "password":
        return str(value)
    # text
    text = str(value).strip()
    return text if text else None


def register_settings(db: Database) -> None:
    """Register the settings page (``/settings``)."""

    @ui.page("/settings", title="Settings")
    def settings_page(request: Request) -> None:
        redirect = require_auth(request)
        if redirect is not None:
            return redirect
        build_layout(active="Settings")

        ui.label("Settings").classes("text-h6")

        with ui.column().classes("w-full gap-6"):
            # ---- UI password ------------------------------------------------
            with ui.column().classes("w-full gap-2"):
                ui.label("UI password").classes("text-subtitle1")
                ui.label(
                    f"Change the login password (minimum "
                    f"{MIN_PASSWORD_LENGTH} characters).").classes(
                    "text-grey-6 text-sm")
                with ui.row().classes("items-end gap-2"):
                    password_input = ui.input(
                        label="New password").props("type=password") \
                        .classes("w-64").mark("set-password-new")
                    confirm_input = ui.input(
                        label="Repeat password").props("type=password") \
                        .classes("w-64").mark("set-password-confirm")
                    password_btn = ui.button("Change password").mark(
                        "set-save-password")

                def on_password(_e=None) -> None:
                    new = str(password_input.value or "")
                    confirm = str(confirm_input.value or "")
                    if len(new) < MIN_PASSWORD_LENGTH:
                        ui.notify(
                            f"Password must be at least "
                            f"{MIN_PASSWORD_LENGTH} characters.",
                            type="negative")
                        return
                    if new != confirm:
                        ui.notify("The two password fields must match.",
                                  type="negative")
                        return
                    set_password_hash(db, hash_password(new))
                    password_input.value = ""
                    confirm_input.value = ""
                    ui.notify("Password updated", type="positive")

                password_btn.on("click", on_password)

            # ---- Daemon settings --------------------------------------------
            with ui.column().classes("w-full gap-2"):
                ui.label("Daemon settings").classes("text-subtitle1")
                for key, label, kind, hint in FIELDS:
                    with ui.row().classes("w-full items-center gap-3"):
                        ui.label(label).classes("w-48 shrink-0")
                        if kind == "password":
                            control = ui.input(value=db.get_setting(key) or "") \
                                .props("type=password").classes("w-72") \
                                .mark(f"set-{key}")
                        else:
                            control = ui.input(value=db.get_setting(key) or "") \
                                .classes("w-72").mark(f"set-{key}")
                        if hint:
                            ui.label(hint).classes("text-grey-6 text-xs")
                        btn = ui.button("Save").mark(f"set-save-{key}")

                        def on_save(_e=None, key=key, kind=kind,
                                    control=control) -> None:
                            stored = _validate(key, kind, control.value)
                            if stored is None:
                                ui.notify(
                                    f"{key}: invalid value", type="negative")
                                return
                            db.set_setting(key, stored)
                            ui.notify(f"{key} saved", type="positive")

                        btn.on("click", on_save)

                # ---- git auto-commit (switch) --------------------------------
                with ui.row().classes("w-full items-center gap-3"):
                    ui.label("Git auto-commit").classes("w-48 shrink-0")
                    commit_switch = ui.switch(
                        value=(db.get_setting("git_commit_enabled") or "")
                        .strip().lower() in ("1", "true", "yes", "on")) \
                        .mark("set-git_commit_enabled")
                    ui.label("Auto-commit recipe edits saved in the UI.") \
                        .classes("text-grey-6 text-xs")
                    commit_btn = ui.button("Save").mark(
                        "set-save-git_commit_enabled")

                    def on_commit(_e=None) -> None:
                        db.set_setting("git_commit_enabled",
                                       "true" if commit_switch.value
                                       else "false")
                        ui.notify("git_commit_enabled saved", type="positive")

                    commit_btn.on("click", on_commit)
