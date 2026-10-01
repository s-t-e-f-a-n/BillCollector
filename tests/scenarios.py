# -*- coding: utf-8 -*-
"""Single source of truth for the local regression test environment.

Imported by both the mock portal (tests/mock_portal/) and the Layer A
harness (tests/run_regression.py).

- SITES: per-site registry - scenario switches and per-user document data.
  The mock portal validates logins against the passwords stored here.
- CREDENTIALS: the values the harness passes to the scraping engine,
  emulating the vault. For the 'wrongpass' user the password differs on
  purpose from the registry, so the mock rejects the login.
- TOTP_SECRETS: per-user base32 TOTP secrets for the vault e2e mode
  (--vault). The mock's OTP endpoint also accepts a valid TOTP computed
  from the user's secret; the real Vaultwarden items carry the same
  secrets.
- EXPECTATIONS: per (service, user) pair - expected engine return value,
  expected DB 'Service' result, expected downloaded filenames, and - for
  the graceful scenario - the label of the step that must be recorded as
  a graceful error in the run table.

Users are short descriptive keywords when they carry test semantics
(wrongpass, nodocts, dlerror), otherwise userN. No real person names.
"""

PORT_DEFAULT = 8787

# Invoice row labels per document id (rendered on the /invoices page).
INVOICE_DATES = {
    "invoice_1": "Invoice dated 2026-07-01",
    "invoice_2": "Invoice dated 2026-08-01",
}

CONTRACT_LABEL = "Contract info_{user} (PDF)"
BONUS_LABEL = "Bonus document"

# service name (INI key, recipe name) -> mock site (path base)
SERVICE_TO_SITE = {
    "testhappy": "happy",
    "testgraceful": "graceful",
    "testbadlogin": "badlogin",
    "testempty": "empty",
    "testdlfail": "dlfail",
    "testwaituser": "waituser",
    "testcaptchadrag": "captchadrag",
    "testautopause": "autopause",
}

# TOTP secrets for the vault e2e mode (--vault). Fake test secrets - safe to
# commit, like the fake passwords. 'wrongpass' deliberately has no secret:
# its vault item has no TOTP (the pair aborts before the OTP step is
# reached, and the no-TOTP path of get_totp is exercised).
TOTP_SECRETS = {
    ("happy", "user1"): "ITMSBTU3L2H7CAOQWNRNCZIFDY",
    ("happy", "user2"): "O3JK2AF3JJGLLOIUIWGWAQVD2I",
    ("happy", "user3"): "YZJRV3XEFK6U2DJOTJNTZQB5XQ",
    ("graceful", "user1"): "OI5ILWLO37R6CSZHFUTUR2RWNM",
    ("empty", "nodocts"): "UYAKJVYVWEXHC2VD5VNHEWT3CQ",
    ("dlfail", "dlerror"): "EGMZHGTBSQJF75XG2V4UYEO7BU",
}

# Full user data: two invoice rows plus a contract document.
def _full_users(*names, password=None, otp="123456"):
    users = {}
    for name in names:
        users[name] = {
            "password": password if password is not None else f"{name}-pass",
            "otp": otp,
            "invoices": ["invoice_1", "invoice_2"],
            "contract": True,
        }
    return users

SITES = {
    # Layer A
    "happy": {
        "reject_login": False,
        "empty_docs": False,
        "download_500": False,
        "hide_bonus": False,
        "next_after_otp": "dashboard",
        "users": _full_users("user1", "user2", "user3"),
    },
    "graceful": {
        "reject_login": False,
        "empty_docs": False,
        "download_500": False,
        "hide_bonus": True,   # "Bonus document" is never rendered
        "next_after_otp": "dashboard",
        "users": _full_users("user1"),
    },
    "badlogin": {
        "reject_login": False,   # rejection comes from the wrong password
        "empty_docs": False,
        "download_500": False,
        "hide_bonus": False,
        "next_after_otp": "dashboard",
        "users": _full_users("wrongpass", password="correct-password"),
    },
    "empty": {
        "reject_login": False,
        "empty_docs": True,
        "download_500": False,
        "hide_bonus": False,
        "next_after_otp": "dashboard",
        "users": _full_users("nodocts"),
    },
    "dlfail": {
        "reject_login": False,
        "empty_docs": False,
        "download_500": True,
        "hide_bonus": False,
        "next_after_otp": "dashboard",
        "users": {
            "dlerror": {
                "password": "dlerror-pass",
                "otp": "123456",
                "invoices": ["invoice_1"],
                "contract": False,
            },
        },
    },
    # Layer B (executed by the daemon runner, not by the Layer A harness)
    "waituser": {
        "reject_login": False,
        "empty_docs": False,
        "download_500": False,
        "hide_bonus": False,
        "next_after_otp": "verify",
        "users": _full_users("user1"),
    },
    "captchadrag": {
        "reject_login": False,
        "empty_docs": False,
        "download_500": False,
        "hide_bonus": False,
        "next_after_otp": "drag",
        "users": _full_users("user1"),
    },
    "autopause": {
        "reject_login": False,
        "empty_docs": False,
        "download_500": False,
        "hide_bonus": False,
        "next_after_otp": "challenge",
        "users": _full_users("user1"),
    },
}

# What the harness feeds the engine (emulates the vault values).
CREDENTIALS = {
    "testhappy": {
        "user1": {"user": "user1", "password": "user1-pass", "otp": "123456"},
        "user2": {"user": "user2", "password": "user2-pass", "otp": "123456"},
        "user3": {"user": "user3", "password": "user3-pass", "otp": "123456"},
    },
    "testgraceful": {
        "user1": {"user": "user1", "password": "user1-pass", "otp": "123456"},
    },
    "testbadlogin": {
        # Deliberately wrong password -> the mock rejects the login.
        "wrongpass": {"user": "wrongpass", "password": "wrong-password", "otp": "123456"},
    },
    "testempty": {
        "nodocts": {"user": "nodocts", "password": "nodocts-pass", "otp": "123456"},
    },
    "testdlfail": {
        "dlerror": {"user": "dlerror", "password": "dlerror-pass", "otp": "123456"},
    },
    # Layer B: present for completeness; executed by the daemon runner.
    "testwaituser": {
        "user1": {"user": "user1", "password": "user1-pass", "otp": "123456"},
    },
    "testcaptchadrag": {
        "user1": {"user": "user1", "password": "user1-pass", "otp": "123456"},
    },
    "testautopause": {
        "user1": {"user": "user1", "password": "user1-pass", "otp": "123456"},
    },
}

# Per-pair expectations. 'graceful_error' names the label of the step that
# must be recorded as a graceful error in the run table (testgraceful only).
EXPECTATIONS = {
    "testhappy": {
        "user1": {
            "return": True, "service_result": "success",
            "downloads": ["invoice_happy_user1_1.pdf", "contract_info_happy_user1.pdf"],
        },
        "user2": {
            "return": True, "service_result": "success",
            "downloads": ["invoice_happy_user2_1.pdf", "contract_info_happy_user2.pdf"],
        },
        "user3": {
            "return": True, "service_result": "success",
            "downloads": ["invoice_happy_user3_1.pdf", "contract_info_happy_user3.pdf"],
        },
    },
    "testgraceful": {
        "user1": {
            "return": True, "service_result": "success",
            "downloads": ["invoice_graceful_user1_1.pdf", "contract_info_graceful_user1.pdf"],
            "graceful_error": BONUS_LABEL,
        },
    },
    "testbadlogin": {
        "wrongpass": {"return": False, "service_result": "failure", "downloads": []},
    },
    "testempty": {
        "nodocts": {"return": False, "service_result": "failure", "downloads": []},
    },
    "testdlfail": {
        "dlerror": {"return": False, "service_result": "failure", "downloads": []},
    },
    # Layer B pairs abort deterministically under the batch engine.
    "testwaituser": {
        "user1": {"return": False, "service_result": "failure", "downloads": []},
    },
    "testcaptchadrag": {
        "user1": {"return": False, "service_result": "failure", "downloads": []},
    },
    "testautopause": {
        "user1": {"return": False, "service_result": "failure", "downloads": []},
    },
}

def site_url(port, site):
    """Base URL of a mock site, e.g. http://127.0.0.1:8787/happy/."""
    return f"http://127.0.0.1:{port}/{site}/"

def download_filename(site, user, doc):
    """Content-Disposition filename of a download (site prefix prevents
    collisions in the shared Downloads dir)."""
    if doc == "contract":
        return f"contract_info_{site}_{user}.pdf"
    if doc in INVOICE_DATES:
        return f"invoice_{site}_{user}_{doc.split('_')[1]}.pdf"
    raise ValueError(f"Unknown document id: {doc}")

def expected_downloads(site, user):
    """Filenames the happy-path recipe actually downloads: the first invoice
    row (the recipe clicks 'first') plus the contract, where present."""
    site_cfg = SITES[site]
    if site_cfg["empty_docs"]:
        return []
    u = site_cfg["users"][user]
    files = []
    if u["invoices"]:
        files.append(download_filename(site, user, u["invoices"][0]))
    if u["contract"]:
        files.append(download_filename(site, user, "contract"))
    return files
