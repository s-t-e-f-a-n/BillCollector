# -*- coding: utf-8 -*-
"""Mock portal: one FastAPI app hosting one site per regression test
scenario under its own path base (e.g. /happy/...), emulating realistic
bill portals (consent banner, login, OTP, popup, navigation, downloads,
Layer B CAPTCHA pages, admin repair-drill endpoints).

Run from the repo root: python3 -m tests.mock_portal --port 8787
"""
