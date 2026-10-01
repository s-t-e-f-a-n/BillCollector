# -*- coding: utf-8 -*-
"""Mock portal FastAPI app.

One site per scenario under its own path base (e.g. /happy/...), driven by
the SITES registry in tests/scenarios.py. Cookie model:

- 'consent' cookie: Path=/<site>/, one year Max-Age -> persists in a
  persistent browser profile -> the cookie banner shows only on the 1st run.
- 'session_<site>' cookie: Path=/<site>/, session-scoped (no Max-Age) ->
  gone when the browser closes -> re-login on every run.
Each site is isolated by the cookie Path.
"""

import base64
import hashlib
import hmac
import random
import struct
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from tests.scenarios import (
    BONUS_LABEL,
    CONTRACT_LABEL,
    INVOICE_DATES,
    SITES,
    TOTP_SECRETS,
    download_filename,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"

CONSENT_MAX_AGE = 31536000  # one year


def totp_candidates(secret, now=None):
    """Valid 6-digit TOTP codes for a base32 secret (RFC 6238, SHA-1, 30 s
    period, +/-1 time window). The vault e2e mode feeds the engine a code
    from the real Vaultwarden item; this is the mock's side of the check."""
    if not secret:
        return set()
    key = base64.b32decode(secret.upper() + "=" * ((8 - len(secret)) % 8))
    t = int((now if now is not None else time.time()) // 30)
    codes = set()
    for counter in (t - 1, t, t + 1):
        if counter < 0:
            continue  # only reachable within the first 30 s of the epoch
        digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
        codes.add(f"{value % 10**6:06d}")
    return codes


def make_pdf(title):
    """Byte-stable minimal PDF: fully deterministic content (no timestamps),
    so repeated downloads are byte-identical (sha256 dedup scenario)."""
    content = f"BT /F1 14 Tf 72 720 Td ({title}) Tj ET"
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n"
        + content.encode() + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(out))
        out += str(i).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n"
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (b"trailer\n<< /Size " + str(len(objs) + 1).encode()
            + b" /Root 1 0 R >>\nstartxref\n" + str(xref_pos).encode() + b"\n%%EOF")
    return out


def create_app():
    app = FastAPI()
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # In-memory per-site state: overrides for the "changed website" repair
    # drill, and the displayed CAPTCHA codes. Fresh on every process start;
    # the admin endpoints can reset them at runtime.
    overrides = {site: {} for site in SITES}
    verify_codes = {}

    def site_cfg(site):
        return SITES.get(site)

    def session_user(request, site):
        cookie = request.cookies.get(f"session_{site}")
        if cookie and ":" in cookie:
            s, user = cookie.split(":", 1)
            if s == site and user in SITES[site]["users"]:
                return user
        return None

    def not_found():
        return JSONResponse({"detail": "Unknown site"}, status_code=404)

    def landing_ctx(request, site, login_error=False):
        return {
            "site": site,
            "path": f"/{site}",
            "show_banner": "consent" not in request.cookies,
            "login_button": overrides[site].get("login_button", "Log in"),
            "reject_button": overrides[site].get("reject_button", "Reject"),
            "login_error": login_error,
        }

    # --- Health -----------------------------------------------------------

    @app.get("/health")
    async def health():
        return JSONResponse({"ok": True})

    # --- Admin (changed-website repair drill) -----------------------------

    @app.post("/admin/{site}/mutate")
    async def admin_mutate(request: Request, site: str):
        if site_cfg(site) is None:
            return not_found()
        body = await request.json()
        for key, value in body.items():
            overrides[site][key] = value
        return JSONResponse({"ok": True, "overrides": overrides[site]})

    @app.post("/admin/{site}/reset")
    async def admin_reset(site: str):
        if site_cfg(site) is None:
            return not_found()
        overrides[site] = {}
        for key in [k for k in verify_codes if k.startswith(site + ":")]:
            del verify_codes[key]
        return JSONResponse({"ok": True})

    # --- Consent ------------------------------------------------------------

    @app.get("/{site}/consent")
    async def consent(site: str):
        if site_cfg(site) is None:
            return not_found()
        resp = RedirectResponse(f"/{site}/", status_code=302)
        resp.set_cookie("consent", "1", path=f"/{site}/", max_age=CONSENT_MAX_AGE)
        return resp

    # --- Landing / login ----------------------------------------------------

    @app.get("/{site}/", response_class=HTMLResponse)
    async def landing(request: Request, site: str):
        if site_cfg(site) is None:
            return not_found()
        if session_user(request, site):
            return RedirectResponse(f"/{site}/dashboard", status_code=302)
        return templates.TemplateResponse(request, "landing.html", landing_ctx(request, site))

    @app.post("/{site}/login")
    async def login(request: Request, site: str):
        cfg = site_cfg(site)
        if cfg is None:
            return not_found()
        form = await request.form()
        user = str(form.get("email", "")).strip()
        ucfg = cfg["users"].get(user)
        ok = (
            not cfg["reject_login"]
            and ucfg is not None
            and str(form.get("user_id", "")).strip() == user
            and str(form.get("alias", "")).strip() == user
            and str(form.get("pwd_title", "")).strip() == ucfg["password"]
            and str(form.get("pwd", "")).strip() == ucfg["password"]
        )
        if ok:
            resp = RedirectResponse(f"/{site}/otp", status_code=302)
            resp.set_cookie(f"session_{site}", f"{site}:{user}", path=f"/{site}/")
            return resp
        # Re-render the landing page with "Login failed" (no redirect).
        return templates.TemplateResponse(
            request, "landing.html", landing_ctx(request, site, login_error=True), status_code=200
        )

    # --- OTP ----------------------------------------------------------------

    @app.get("/{site}/otp", response_class=HTMLResponse)
    async def otp_page(request: Request, site: str):
        cfg = site_cfg(site)
        if cfg is None:
            return not_found()
        user = session_user(request, site)
        if user is None:
            return RedirectResponse(f"/{site}/", status_code=302)
        return templates.TemplateResponse(request, "otp.html", {
            "site": site, "path": f"/{site}", "user": user, "otp_error": False,
        })

    @app.post("/{site}/otp")
    async def otp_submit(request: Request, site: str):
        cfg = site_cfg(site)
        if cfg is None:
            return not_found()
        user = session_user(request, site)
        if user is None:
            return RedirectResponse(f"/{site}/", status_code=302)
        form = await request.form()
        code = str(form.get("otp", "")).strip()
        ucfg = cfg["users"][user]
        if code == ucfg["otp"] or code in totp_candidates(TOTP_SECRETS.get((site, user))):
            return RedirectResponse(f"/{site}/{cfg['next_after_otp']}", status_code=302)
        return templates.TemplateResponse(request, "otp.html", {
            "site": site, "path": f"/{site}", "user": user, "otp_error": True,
        }, status_code=200)

    # --- Layer B scenario pages ----------------------------------------------

    @app.get("/{site}/verify", response_class=HTMLResponse)
    async def verify_page(request: Request, site: str):
        cfg = site_cfg(site)
        if cfg is None:
            return not_found()
        user = session_user(request, site)
        if user is None:
            return RedirectResponse(f"/{site}/", status_code=302)
        key = f"{site}:{user}"
        if key not in verify_codes:
            verify_codes[key] = f"{random.randint(0, 999999):06d}"
        return templates.TemplateResponse(request, "verify.html", {
            "site": site, "path": f"/{site}",
            "code": verify_codes[key], "otp_error": False,
        })

    @app.post("/{site}/verify")
    async def verify_submit(request: Request, site: str):
        cfg = site_cfg(site)
        if cfg is None:
            return not_found()
        user = session_user(request, site)
        if user is None:
            return RedirectResponse(f"/{site}/", status_code=302)
        form = await request.form()
        if str(form.get("code", "")).strip() == verify_codes.get(f"{site}:{user}"):
            return RedirectResponse(f"/{site}/dashboard", status_code=302)
        return templates.TemplateResponse(request, "verify.html", {
            "site": site, "path": f"/{site}",
            "code": verify_codes.get(f"{site}:{user}", ""), "otp_error": True,
        }, status_code=200)

    @app.get("/{site}/drag", response_class=HTMLResponse)
    async def drag_page(request: Request, site: str):
        cfg = site_cfg(site)
        if cfg is None:
            return not_found()
        if session_user(request, site) is None:
            return RedirectResponse(f"/{site}/", status_code=302)
        return templates.TemplateResponse(request, "drag.html", {
            "site": site, "path": f"/{site}",
        })

    @app.get("/{site}/challenge", response_class=HTMLResponse)
    async def challenge_page(request: Request, site: str):
        cfg = site_cfg(site)
        if cfg is None:
            return not_found()
        if session_user(request, site) is None:
            return RedirectResponse(f"/{site}/", status_code=302)
        return templates.TemplateResponse(request, "challenge.html", {
            "site": site, "path": f"/{site}",
        })

    # --- Popup (iframe document) ----------------------------------------------

    @app.get("/{site}/popup", response_class=HTMLResponse)
    async def popup(request: Request, site: str):
        if site_cfg(site) is None:
            return not_found()
        return templates.TemplateResponse(request, "popup.html", {
            "site": site, "path": f"/{site}",
        })

    # --- Session-protected pages -----------------------------------------------

    @app.get("/{site}/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request, site: str):
        cfg = site_cfg(site)
        if cfg is None:
            return not_found()
        user = session_user(request, site)
        if user is None:
            return RedirectResponse(f"/{site}/", status_code=302)
        return templates.TemplateResponse(request, "dashboard.html", {
            "site": site, "path": f"/{site}", "user": user,
        })

    @app.get("/{site}/account", response_class=HTMLResponse)
    async def account(request: Request, site: str):
        cfg = site_cfg(site)
        if cfg is None:
            return not_found()
        user = session_user(request, site)
        if user is None:
            return RedirectResponse(f"/{site}/", status_code=302)
        return templates.TemplateResponse(request, "account.html", {
            "site": site, "path": f"/{site}", "user": user,
        })

    @app.get("/{site}/invoices", response_class=HTMLResponse)
    async def invoices(request: Request, site: str):
        cfg = site_cfg(site)
        if cfg is None:
            return not_found()
        user = session_user(request, site)
        if user is None:
            return RedirectResponse(f"/{site}/", status_code=302)
        ucfg = cfg["users"][user]
        invoice_rows = [
            (INVOICE_DATES[doc], doc) for doc in ucfg["invoices"]
        ] if not cfg["empty_docs"] else []
        return templates.TemplateResponse(request, "invoices.html", {
            "site": site, "path": f"/{site}", "user": user,
            "invoice_rows": invoice_rows,
            "contract_label": CONTRACT_LABEL.format(user=user)
            if (not cfg["empty_docs"] and ucfg["contract"]) else None,
            "show_bonus": (not cfg["empty_docs"]) and not cfg["hide_bonus"],
            "bonus_label": BONUS_LABEL,
        })

    @app.get("/{site}/download/{doc}")
    async def download(request: Request, site: str, doc: str):
        cfg = site_cfg(site)
        if cfg is None:
            return not_found()
        user = session_user(request, site)
        if user is None:
            return RedirectResponse(f"/{site}/", status_code=302)
        ucfg = cfg["users"][user]
        if cfg["download_500"]:
            return Response(content="Internal Server Error", status_code=500)
        if doc not in ucfg["invoices"] and doc != "contract":
            return not_found()
        filename = download_filename(site, user, doc)
        title = (INVOICE_DATES.get(doc) or CONTRACT_LABEL.format(user=user)
                 or f"Document {doc}").replace("(", r"\(").replace(")", r"\)")
        pdf = make_pdf(f"{site} {user} {doc}")
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return app
