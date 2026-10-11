# -*- coding: utf-8 -*-
"""Login / set-password page for the daemon UI (M2 chunk D1).

The form submits natively (plain HTTP POST to /login) so the handler can
read ``request.form()`` and set the session cookie; no websocket
round-trip is involved in authentication. Two modes:

- set-password (first start, no hash stored yet): two password fields,
  minimum length 8, both must match;
- login (hash stored): one password field, wrong password re-renders with
  an inline error and no state change.

The page (GET) and the POST handler are separate routes: the NiceGUI page
route only accepts GET, so the submission runs on a plain FastAPI POST
route. Failures bounce back to ``/login?error=<code>`` and the page maps
the code to an inline message (no free-form text in the query string).
"""

import logging

from fastapi import Request
from fastapi.responses import RedirectResponse
from nicegui import app as nicegui_app
from nicegui import ui

from . import auth

logger = logging.getLogger("billcollector.ui.login")

_ERRORS = {
    "too_short": ("Password must be at least "
                  f"{auth.MIN_PASSWORD_LENGTH} characters."),
    "mismatch": "The two password fields must match.",
    "wrong_password": "Wrong password.",
}

_FORM_CSS = """
.bc-login-input {
    width: 100%; margin: 0.5rem 0; padding: 0.5rem 0.75rem;
    border: 1px solid #ccc; border-radius: 4px; font-size: 1rem;
}
.bc-login-button {
    padding: 0.5rem 1.5rem; border: none; border-radius: 4px;
    background: #1976d2; color: white; font-size: 1rem; cursor: pointer;
}
.bc-login-button:hover { background: #1565c0; }
"""


def register_login_page(db) -> None:
    """Register the /login page (GET) and the /login POST handler."""

    @ui.page("/login", title="BillCollector")
    def login_page(request: Request) -> None:
        error = _ERRORS.get(request.query_params.get("error") or "")
        set_mode = auth.get_password_hash(db) is None
        ui.add_head_html(f"<style>{_FORM_CSS}</style>")
        ui.label("BillCollector").classes("text-h4 font-bold")
        if set_mode:
            ui.label("First start: set the password for the UI login.")
        else:
            ui.label("Sign in to the BillCollector dashboard.")
        if error:
            ui.label(error).classes("text-red-600").mark("login-error")

        confirm_input = ('<input type="password" name="password_confirm" '
                         'class="bc-login-input" placeholder="Repeat password">') \
            if set_mode else ""
        submit = "Set password" if set_mode else "Sign in"
        ui.html(
            '<form method="post" action="/login">'
            '<input type="password" name="password" '
            'class="bc-login-input" placeholder="Password" autofocus>'
            f"{confirm_input}"
            f'<br><button type="submit" class="bc-login-button">{submit}</button>'
            "</form>")

    @nicegui_app.post("/login")
    async def login_post(request: Request):
        """Handle the native form POST; redirects only (no page render).

        All redirects are 303 See Other, not 307: a 307 would make the
        browser re-POST to the Location, which 405s on the GET-only page
        routes (e.g. the success redirect to /)."""
        form = await request.form()
        password = str(form.get("password") or "")
        stored = auth.get_password_hash(db)
        if stored is None:
            confirm = str(form.get("password_confirm") or "")
            if len(password) < auth.MIN_PASSWORD_LENGTH:
                return RedirectResponse("/login?error=too_short", status_code=303)
            if password != confirm:
                return RedirectResponse("/login?error=mismatch", status_code=303)
            auth.set_password_hash(db, auth.hash_password(password))
            logger.info("ui password set via the first-start form")
        elif not auth.verify_password(password, stored):
            return RedirectResponse("/login?error=wrong_password", status_code=303)
        request.session["authenticated"] = True
        return RedirectResponse("/", status_code=303)
