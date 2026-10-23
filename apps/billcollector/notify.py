# -*- coding: utf-8 -*-
"""ntfy push notifications for pause events (decision 13).

Every pause pushes with a deep link to the session page
(``<UI_BASE_URL>/runs/<run_id>``) so the operator can act from a phone
without opening the dashboard first. Pushes are best-effort: a failed push
is logged and never affects the run.
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)

NTFY_TIMEOUT = 10  # seconds


def _ntfy_host():
    return os.environ.get("NTFY_HOST", "https://ntfy.sh").rstrip("/")


def notify_login_locked(db, task, *, dispatch=None):
    """Best-effort block notification. Do not include portal errors or secrets."""
    topic = (db.get_setting("ntfy_topic") or "").strip()
    if not topic:
        return False
    base = (db.get_setting("ui_base_url") or "").strip().rstrip("/")
    message = (f"Task {task['id']} blocked after {task['login_failures']} "
               "unproven login attempts. Check credentials before clearing.")
    if base:
        message += f"\n{base}/tasks/{task['id']}"
    url = f"{_ntfy_host()}/{topic}"
    if dispatch is not None:
        return dispatch(_send_login_locked, url, message)
    return _send_login_locked(url, message)


def _send_login_locked(url, message):
    try:
        response = requests.post(
            url, data=message.encode("utf-8"),
            headers={"Title": "BillCollector: login blocked", "Priority": "4",
                     "Tags": "lock"}, timeout=NTFY_TIMEOUT)
        return response.status_code == 200
    except requests.exceptions.RequestException as e:
        logger.warning("ntfy login block push failed: %s", type(e).__name__)
        return False


def notify_pause(db, run, task):
    """Push the pause banner with the session deep link. Returns True on success."""
    topic = (db.get_setting("ntfy_topic") or "").strip()
    if not topic:
        logger.info("No ntfy topic configured; skipping pause push.")
        return False
    base_url = (db.get_setting("ui_base_url") or "").strip().rstrip("/")
    deep_link = f"{base_url}/runs/{run['id']}" if base_url else f"/runs/{run['id']}"
    service_user = f"{task['service']} {task['user']}".strip()
    title = f"BillCollector: {service_user} needs attention"
    message = (run["pause_prompt"] or f"Run {run['id']} paused") + f"\n{deep_link}"
    try:
        response = requests.post(
            f"{_ntfy_host()}/{topic}",
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": "4", "Tags": "bell"},
            timeout=NTFY_TIMEOUT,
        )
        if response.status_code == 200:
            logger.info(f"ntfy pause push sent (topic {topic}, run {run['id']}).")
            return True
        logger.warning(f"ntfy pause push failed: HTTP {response.status_code}")
    except requests.exceptions.RequestException as e:
        # The exception can include the URL (and topic); keep the class name only.
        logger.warning(f"ntfy pause push failed: {type(e).__name__}")
    return False
