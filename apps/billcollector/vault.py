# -*- coding: utf-8 -*-
"""Shared Vaultwarden (bw serve) API client for BillCollector.

Used by the daemon runner (per-task credential resolution) and by the legacy
batch entry point (``apps/BillCollector.py``), which used to carry its own
copy of this client. Every request carries an explicit timeout and is
retried up to ``VAULT_MAX_ATTEMPTS`` times on transient failures
(connection errors, timeouts, 5xx responses). A 4xx response is final: it is
reported as a ``VaultAPIError`` carrying the status code, so callers can
distinguish expected statuses (e.g. "no TOTP") from real failures.

This module never calls ``sys.exit``: it raises ``VaultAPIError`` and lets
the caller decide (the batch entry point translates that into its documented
exit codes, the daemon runner records the run as failed).
"""

import json
import logging
import time

import requests
from flatten_json import flatten

from vault_transport import VaultTransportError, vault_http_request

logger = logging.getLogger(__name__)

VAULT_TIMEOUT = 10        # seconds per request
VAULT_MAX_ATTEMPTS = 3    # total attempts per request
VAULT_RETRY_BACKOFF = 2   # seconds; delay before retry N is backoff * N


class VaultAPIError(Exception):
    """Fatal Vaultwarden API error: a final 4xx response or exhausted retries."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def vault_request(method, url, payload=None):
    """One vault HTTP request with the shared retry policy.

    Transient failures (transport errors, timeouts, 5xx) are retried; a 4xx
    response raises immediately with its status code attached.
    """
    for attempt in range(1, VAULT_MAX_ATTEMPTS + 1):
        try:
            response = vault_http_request(method, url, payload, VAULT_TIMEOUT)
        except VaultTransportError as e:
            raise VaultAPIError(str(e)) from None
        except requests.exceptions.RequestException as e:
            # Exceptions can include the request URL, credentials or a response
            # body. Keep only bounded diagnostics (the class name) from this
            # credential service.
            logger.warning(
                f"Attempt {attempt}/{VAULT_MAX_ATTEMPTS} failed: network error ({type(e).__name__})")
            response = None
        else:
            if 400 <= response.status_code < 500:
                # Log the status only: the 4xx body can carry account identity.
                logger.warning(f"Client error: {response.status_code}")
                raise VaultAPIError(
                    f"Client error: {response.status_code}",
                    status=response.status_code)
            if response.status_code < 400:
                return response
            logger.warning(
                f"Attempt {attempt}/{VAULT_MAX_ATTEMPTS} failed: "
                f"server error {response.status_code}")
        if attempt < VAULT_MAX_ATTEMPTS:
            time.sleep(VAULT_RETRY_BACKOFF * attempt)
    raise VaultAPIError(f"Request failed after {VAULT_MAX_ATTEMPTS} attempts")


def get_json(url):
    """GET ``url`` and return the raw response body. Raises VaultAPIError."""
    return vault_request("GET", url).text


# Get a vault item's TOTP. A 400 from the TOTP endpoint means the item has no
# TOTP entry: an expected status, not a failure (the item is known to exist,
# it was fetched directly above). Any other 4xx is a real failure.
def get_totp(url):
    try:
        return vault_request("GET", url).text
    except VaultAPIError as e:
        if e.status == 400:
            logger.warning(f"No TOTP for this vault item, continuing without OTP: {e}")
            return None
        raise


# Check Bitwarden API status
def bitwarden_api_check_status(url):
    """Return (ok, status) for the vault: ok=False on a failed check,
    status in {"unlocked", "locked"} when the check itself succeeded."""
    content = get_json(f"{url}/status")
    logger.debug("Vault status request completed")
    if not is_json_property_value(content, "success", True):
        return False, None
    if not is_json_property_value(content, "data_template_status", "unlocked"):
        return True, "locked"
    return True, "unlocked"


def is_json_property_value(content, prop, val):
    if not is_json_valid(content):
        return False
    if not is_string_valid(prop):
        return False
    data = flatten(json.loads(content))
    result = data.get(prop)
    if (result) == val:
        return True
    return False


def is_json_valid(content):
    try:
        json.loads(content)
        return True
    except ValueError as e:
        logger.error(f"Error: Invalid JSON {e}")
        return False


def is_string_valid(string):
    try:
        if not isinstance(string, str) or not string or string.isspace():
            raise ValueError("Invalid string")
        return True
    except ValueError as e:
        logger.error(f"Error: {e}")
        return False


def post_json(url, payload):
    """POST ``payload``; returns the JSON body as a string, or False on error."""
    try:
        response = vault_request("POST", url, payload)
    except VaultAPIError as e:
        logger.error(str(e))
        return False
    if response.status_code in (200, 201):
        logger.info("Successfully posted!")
        return json.dumps(response.json())
    logger.error(f"Error: {response.status_code}")
    return False


def get_json_property_value(content, prop):
    data = flatten(json.loads(content))
    return data.get(prop)


def fetch_credentials(api_url, service, user):
    """Resolve the portal credentials of one task from the vault.

    The item name is the name-based link ``<service> <user>`` (decision 7).
    Returns ``{"user", "password", "otp", "url"}``; ``otp`` is None when the
    item has no TOTP entry, ``url`` is the item's first login URI
    (informational - the recipe's goto step holds the URL the engine visits).
    Raises VaultAPIError on any real failure.
    """
    item_name = f"{service} {user}".strip()
    item = get_json(f"{api_url}/object/item/{item_name}")
    totp_item = get_totp(f"{api_url}/object/totp/{item_name}")
    return {
        "user": get_json_property_value(item, "data_login_username"),
        "password": get_json_property_value(item, "data_login_password"),
        "otp": get_json_property_value(totp_item, "data_data") if totp_item is not None else None,
        "url": get_json_property_value(item, "data_login_uris_0_uri"),
    }
