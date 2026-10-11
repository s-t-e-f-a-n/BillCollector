# -*- coding: utf-8 -*-
"""Session-cookie authentication for the daemon UI (M2 chunk D1).

Single-operator auth: one bcrypt password hash in the Settings table. On
first start without a hash, ``/login`` shows a one-time set-password form
(locked decision 1); ``BC_UI_PASSWORD`` from the environment seeds the hash
instead. Sessions ride a Starlette ``SessionMiddleware`` cookie whose secret
is generated once and persisted in Settings (decision 2), so operator
sessions survive daemon restarts. Unauthenticated requests to non-public
paths are redirected to ``/login``.
"""

import logging
import os
import secrets

import bcrypt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse

from ..db import Database

logger = logging.getLogger("billcollector.ui.auth")

PUBLIC_PATHS = ("/login", "/_alive")
MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    """bcrypt hash of the password (stored as ASCII text in Settings)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    """True when the password matches the stored hash (never raises)."""
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def get_password_hash(db: Database):
    """The stored password hash, or None when no password has been set yet."""
    row = db.conn.execute(
        "SELECT value FROM Settings WHERE key='ui_password_hash'").fetchone()
    return row["value"] if row is not None and row["value"] else None


def set_password_hash(db: Database, hashed: str) -> None:
    db.set_setting("ui_password_hash", hashed)


def ensure_password(db: Database, env_password: str | None = None) -> bool:
    """Seed the password hash from ``BC_UI_PASSWORD`` on first start.

    Called from the serve startup before any request is served. Seeds the
    hash only when it is absent (a hash set via the UI is never overwritten).
    Returns True when a hash exists afterwards (login mode), False when
    ``/login`` must show the set-password form.
    """
    if get_password_hash(db) is not None:
        return True
    if env_password is None:
        env_password = os.environ.get("BC_UI_PASSWORD")
    if env_password:
        set_password_hash(db, hash_password(env_password))
        logger.info("ui password hash seeded from BC_UI_PASSWORD")
        return True
    return False


def get_session_secret(db: Database) -> str:
    """The persisted session secret (generated once, survives restarts).

    Must run before the first request is served: the SessionMiddleware is
    built with it and changing it later would invalidate every open session.
    """
    row = db.conn.execute(
        "SELECT value FROM Settings WHERE key='session_secret'").fetchone()
    if row is not None and row["value"]:
        return row["value"]
    secret = secrets.token_hex(32)
    db.set_setting("session_secret", secret)
    logger.info("ui session secret generated and persisted")
    return secret


def is_public_path(path: str) -> bool:
    """Paths reachable without authentication: /login, /_alive, NiceGUI static (/_*)."""
    return path in PUBLIC_PATHS or path.startswith("/_")


class AuthRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect unauthenticated requests to /login; public paths pass through.

    Must sit inside the SessionMiddleware (register it first, see
    :func:`register_auth`). Non-HTTP scopes (websocket, lifespan) pass
    through untouched.
    """

    async def dispatch(self, request, call_next):
        if not is_public_path(request.url.path) \
                and not request.session.get("authenticated"):
            return RedirectResponse(url="/login", status_code=307)
        return await call_next(request)


def require_auth(request):
    """Defensive session check for page builders.

    The middleware is the first line of defence; page builders run
    server-side per navigation, so each protected page also re-checks the
    session and redirects when it is missing (e.g. after a secret rotation
    invalidated every cookie). Returns a redirect Response, or None when
    the request is authenticated.
    """
    if not request.session.get("authenticated"):
        return RedirectResponse(url="/login", status_code=307)
    return None


def register_auth(app, db: Database) -> None:
    """Wire the auth middleware into the app (call before the server starts).

    Starlette wraps middleware in reverse add order, so the auth middleware
    (which needs ``request.session``) is added first and the
    SessionMiddleware second - the session ends up outside it.
    """
    app.add_middleware(AuthRedirectMiddleware)
    app.add_middleware(SessionMiddleware, secret_key=get_session_secret(db))
