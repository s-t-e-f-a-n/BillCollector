# -*- coding: utf-8 -*-
"""Settings page for the daemon UI (M2 chunk D6.1; restructured
2026-11-17: grouped cards, one Save).

``/settings`` edits the daemon settings stored in the ``Settings`` table
(locked decision 12). The fields are grouped into cards, each with a
subtitle title:

- **Security** - the UI password (change, bcrypt hash) with its confirm
  field and its own **Change password** action (``vpn_key`` icon); this
  is a separate transaction, not covered by the single Save (the
  confirm field makes it its own form)
- **Notifications** - ``ntfy_topic`` (opt-in push notifications),
  ``ui_base_url`` (base for the pause deep links)
- **Runs** - ``pause_deadline_seconds``, ``max_concurrency`` (takes
  effect on the next daemon start - the semaphore is built at
  construction), ``display_start``
- **Storage & session** - ``download_dir``, ``vnc_password`` (optional
  RFB auth second layer)
- **Vault** - the vault API ``vault_api_url`` / ``vault_api_host``
  (M4 C1: empty falls back to the ``BW_API_URL`` / ``BW_API_HOST``
  environment values; an empty field shows the currently effective
  environment value in its hint, re-read on page load only)
- **Git** - the ``git_commit_enabled`` switch

One **Save** button at the bottom (right-aligned, ``save`` icon,
tooltip) writes all daemon settings at once: every field is validated
first (``_validate``; the git switch needs no validation) and the save
is all-or-nothing - all valid writes every value (all ``FIELDS`` keys +
``git_commit_enabled``) and notifies "Settings saved"; any invalid
writes nothing and notifies the failing keys' names
(``invalid: <key>, <key>``). No dirty tracking: Save is always
available and idempotent. ``ui_password_hash``, ``session_secret`` and
``onboarding_done`` are not part of this form.
"""

from fastapi import Request
from nicegui import ui

from .. import config
from ..db import Database
from .auth import MIN_PASSWORD_LENGTH, hash_password, require_auth, set_password_hash
from .layout import build_layout

# (key, label, kind, hint): one entry per daemon setting. ``kind``
# drives the input element and the validation: ``text`` (non-empty),
# ``optional_text`` (empty allowed), ``int`` (positive integer),
# ``password`` (any value, empty allowed). The hints render below the
# input (``text-xs`` muted); the vault hints are replaced by the
# effective environment value when the field is empty.
FIELDS = (
    ("ntfy_topic", "ntfy topic", "optional_text",
     "Empty: no push notifications. Set a topic to opt in (public ntfy.sh "
     "or the bundled self-hosted profile)."),
    ("ui_base_url", "UI base URL", "text",
     "Base for the pause deep links; keep the loopback default or set a "
     "LAN-absolute URL (e.g. http://<nas-lan-ip>:8766) so links open on a "
     "phone on your network."),
    ("pause_deadline_seconds", "Pause deadline (seconds)", "int", ""),
    ("max_concurrency", "Max concurrency", "int",
     "Takes effect on the next daemon start."),
    ("display_start", "Display start", "int", ""),
    ("download_dir", "Download directory", "text", ""),
    ("vnc_password", "VNC password", "password",
     "Optional second layer (RFB auth) for non-standard deployments that "
     "publish the websockify ports; the supported path is the UI session."),
    ("vault_api_url", "Vault API URL", "optional_text",
     "Empty: use the BW_API_URL environment value."),
    ("vault_api_host", "Vault API host", "optional_text",
     "Optional Host header override; empty: the URL's host."),
)


def _field_spec(key: str):
    """The FIELDS entry of ``key`` (the cards render their fields in
    their own order; validation and the single Save iterate FIELDS)."""
    return next(item for item in FIELDS if item[0] == key)


def _validate(key: str, kind: str, value):
    """Normalize a field value for the Settings table.

    Returns the string to store, or ``None`` when the value is invalid
    (the caller surfaces the error and writes nothing). ``optional_text``
    accepts the empty value (clearing a field falls back to the
    environment); required ``text`` does not."""
    if kind == "int":
        try:
            number = int(str(value).strip())
        except ValueError:
            return None
        return str(number) if number > 0 else None
    if kind == "password":
        return str(value)
    if kind == "optional_text":
        return str(value or "").strip()
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

        # The per-field inputs, collected for the single Save (the git
        # switch is read directly).
        controls: dict = {}

        def field_row(label: str, key: str, kind: str, hint: str):
            """One field row: the label (``w-48``) + the input (``w-72``)
            + the hint line below the input (``text-xs``, muted)."""
            with ui.row().classes("w-full items-start gap-3"):
                ui.label(label).classes("w-48 shrink-0 pt-3")
                with ui.column().classes("gap-1"):
                    if kind == "password":
                        control = ui.input(
                            value=db.get_setting(key) or "") \
                            .props("type=password").classes("w-72") \
                            .mark(f"set-{key}")
                    else:
                        control = ui.input(
                            value=db.get_setting(key) or "") \
                            .classes("w-72").mark(f"set-{key}")
                    if hint:
                        ui.label(hint).classes("text-xs text-slate-400")
            return control

        with ui.column().classes("w-full gap-6"):
            # ---- Security -------------------------------------------------
            with ui.card().classes("w-full"):
                ui.label("Security").classes("text-subtitle1")
                ui.label(
                    f"Change the login password (minimum "
                    f"{MIN_PASSWORD_LENGTH} characters).").classes(
                    "text-slate-400 text-sm mb-2")
                with ui.row().classes("items-end gap-2"):
                    password_input = ui.input(
                        label="New password").props("type=password") \
                        .classes("w-64").mark("set-password-new")
                    confirm_input = ui.input(
                        label="Repeat password").props("type=password") \
                        .classes("w-64").mark("set-password-confirm")
                    password_btn = ui.button(icon="vpn_key").mark(
                        "set-save-password")
                    with password_btn:
                        ui.tooltip("Change password")

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

            # ---- Notifications ---------------------------------------------
            with ui.card().classes("w-full"):
                ui.label("Notifications").classes("text-subtitle1")
                with ui.column().classes("w-full gap-4"):
                    for key in ("ntfy_topic", "ui_base_url"):
                        k, label, kind, hint = _field_spec(key)
                        controls[key] = field_row(label, k, kind, hint)

            # ---- Runs ------------------------------------------------------
            with ui.card().classes("w-full"):
                ui.label("Runs").classes("text-subtitle1")
                with ui.column().classes("w-full gap-4"):
                    for key in ("pause_deadline_seconds",
                                "max_concurrency", "display_start"):
                        k, label, kind, hint = _field_spec(key)
                        controls[key] = field_row(label, k, kind, hint)

            # ---- Storage & session ------------------------------------------
            with ui.card().classes("w-full"):
                ui.label("Storage & session").classes("text-subtitle1")
                with ui.column().classes("w-full gap-4"):
                    for key in ("download_dir", "vnc_password"):
                        k, label, kind, hint = _field_spec(key)
                        controls[key] = field_row(label, k, kind, hint)

            # ---- Vault -----------------------------------------------------
            # An empty field falls back to the environment: the hint then
            # shows the currently effective environment value (re-read on
            # page load only).
            vault_env = dict(zip(("vault_api_url", "vault_api_host"),
                                 config.vault_settings(db)))
            with ui.card().classes("w-full"):
                ui.label("Vault").classes("text-subtitle1")
                with ui.column().classes("w-full gap-4"):
                    for key, env_name in (("vault_api_url", "BW_API_URL"),
                                          ("vault_api_host",
                                           "BW_API_HOST")):
                        k, label, kind, hint = _field_spec(key)
                        stored = (db.get_setting(key) or "").strip()
                        env_value = vault_env[key]
                        if not stored and env_value:
                            hint = (f"Empty: using the {env_name} "
                                    f"environment value ({env_value}).")
                        elif (not stored and not env_value
                              and key == "vault_api_url"):
                            hint = ("Empty: no BW_API_URL environment "
                                    "value set.")
                        controls[key] = field_row(label, k, kind, hint)

            # ---- Git -------------------------------------------------------
            with ui.card().classes("w-full"):
                ui.label("Git").classes("text-subtitle1")
                with ui.row().classes("w-full items-start gap-3"):
                    ui.label("Git auto-commit").classes("w-48 shrink-0 pt-3")
                    with ui.column().classes("gap-1"):
                        commit_switch = ui.switch(
                            value=(db.get_setting("git_commit_enabled")
                                   or "").strip().lower()
                            in ("1", "true", "yes", "on")) \
                            .mark("set-git_commit_enabled")
                        ui.label("Auto-commit recipe edits saved in the "
                                 "UI.").classes("text-xs text-slate-400")

            # ---- One Save (all-or-nothing) ---------------------------------
            with ui.row().classes("w-full justify-end"):
                save_btn = ui.button(icon="save").props("color=primary") \
                    .mark("set-save")
                with save_btn:
                    ui.tooltip("Save all settings")

                def on_save_all(_e=None) -> None:
                    invalid = []
                    values = {}
                    for key, _label, kind, _hint in FIELDS:
                        stored = _validate(key, kind,
                                           controls[key].value)
                        if stored is None:
                            invalid.append(key)
                        else:
                            values[key] = stored
                    if invalid:
                        ui.notify(f"invalid: {', '.join(invalid)}",
                                  type="negative")
                        return
                    for key, stored in values.items():
                        db.set_setting(key, stored)
                    db.set_setting("git_commit_enabled",
                                   "true" if commit_switch.value
                                   else "false")
                    ui.notify("Settings saved", type="positive")

                save_btn.on("click", on_save_all)
