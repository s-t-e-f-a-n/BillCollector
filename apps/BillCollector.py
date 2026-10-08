# BillCollector
# Retrieval of Documents from Web Services

import os
import sys
from dotenv import load_dotenv
import re
import time
import logging
import requests
import json
import configparser
from flatten_json import flatten

from BillCollectorServices_pw import retrieve_from_service_with_playwright
from vault_transport import VaultTransportError, pinned_api_url, vault_http_request
from helpers import *

logger = logging.getLogger(__name__)

# Function to extract strings before and within brackets
def extract_strings(line):
    match = re.search(r'([^\[]*)\[(.*?)\]', line)
    if match:
        before_bracket = match.group(1).strip()
        within_bracket = match.group(2).split(', ')
        return before_bracket, within_bracket
    return line.strip(), []

# --- Vaultwarden API client ---
# Every request carries an explicit timeout and is retried up to
# VAULT_MAX_ATTEMPTS times on transient failures (connection errors, timeouts,
# 5xx responses). A 4xx response is final: it is reported to the caller as a
# VaultAPIError carrying the status code, so callers can distinguish expected
# statuses (e.g. "no TOTP") from real failures.

VAULT_TIMEOUT = 10        # seconds per request
VAULT_MAX_ATTEMPTS = 3    # total attempts per request
VAULT_RETRY_BACKOFF = 2   # seconds; delay before retry N is backoff * N

class VaultAPIError(Exception):
    """Fatal Vaultwarden API error: a final 4xx response or exhausted retries."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status

def vault_request(method, url, payload=None):
    for attempt in range(1, VAULT_MAX_ATTEMPTS + 1):
        try:
            response = vault_http_request(method, url, payload, VAULT_TIMEOUT)
        except VaultTransportError as e:
            raise VaultAPIError(str(e)) from None
        except requests.exceptions.RequestException as e:
            # Exceptions can include the request URL, credentials or a response
            # body. Keep only bounded diagnostics (the class name) from this credential service.
            logger.warning(f"Attempt {attempt}/{VAULT_MAX_ATTEMPTS} failed: network error ({type(e).__name__})")
            response = None
        else:
            if 400 <= response.status_code < 500:
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

# Get web content
def get_json(url):
    try:
        return vault_request("GET", url).text
    except VaultAPIError as e:
        logger.error(str(e))
        sys.exit(1)

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
        logger.error(str(e))
        sys.exit(1)

# Check Bitwarden API status
def bitwarden_api_check_status(url):
    content = get_json(f"{url}/status")
    logger.debug("Vault status request completed")
    if not is_json_property_value(content, "success", True): return False, None
    else: 
        if not is_json_property_value(content, "data_template_status", "unlocked"): return True, "locked"
        return True, "unlocked"

def is_json_property_value(content, prop, val):
    if not is_json_valid(content): return False
    if not is_string_valid(prop): return False
    data = flatten(json.loads(content))
    result=data.get(prop)
    if (result) == val: return True
    else: return False

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
    try:
        response = vault_request("POST", url, payload)
    except VaultAPIError as e:
        logger.error(str(e))
        return False
    if response.status_code == 201 or response.status_code == 200:
        logger.info("Successfully posted!")
        return json.dumps(response.json())
    else:
        logger.error(f"Error: {response.status_code}")
        return False

def get_json_property_value(content, prop):
    data = flatten(json.loads(content))
    result=data.get(prop)
    return result

class defs:
    def __init__(self, vault, api, fname=INI_DEFAULT_FILE, debug=False):
        self.vault = vault
        self.api = api
        self.fname = fname
        self.debug = debug

def WebRetriDoc(self, type=None, service=None):

    # Vet the actual API endpoint, not the Cloud or Vaultwarden server behind it.
    try:
        pinned_api_url(self.api, VAULT_MAX_ATTEMPTS, VAULT_RETRY_BACKOFF)
    except VaultTransportError as e:
        logger.error(str(e))
        sys.exit(1)
    logger.info("Vault API resolves only to local addresses")

    # Check if Bitarden API at <bw_api_url> responds with success=true
    ret, status = bitwarden_api_check_status(self.api)
    if not ret or not status == "unlocked":
        # Log only the parsed state; the status body also holds account identity.
        logger.error("Vault API status: " + ("locked" if ret else "check failed (success is not true)"))
        sys.exit(1)
    logger.info(status)

    # Sync database
    ret = post_json(f"{self.api}/sync", None)
    if not ret:
        sys.exit(1)
    if not is_json_property_value(ret, "success", True):
        sys.exit(1)
    logger.info("Vault is sync'd successfully.")

    #################
    # Loop over Web Services
    script = configparser.ConfigParser()
    try:
        script.read(self.fname, encoding="utf-8")
    except configparser.Error as e:
        logger.error(f"Error: Reading ini-script: {e}")
        sys.exit(1)
    
    matched = False
    failed = False
    for automation_library in script.sections():
        if automation_library == None: break
        if type != None and automation_library.lower() != type.lower(): continue

        for servicename, users_list in script[automation_library].items():
            if service is not None and servicename.lower() != service.lower():
                continue
            matched = True
            users = []
            if not servicename: break    
            if users_list:
                users = [user.strip() for user in users_list.split(",")]
            else:
                users.insert(0, "")

            # handle service variant with list of users in array
            for user in users:
                service_user = f"{servicename} {user}".strip()
                logger.info(f"Service {service_user} started.")

                # Retrieve credentials
                item = get_json(f"{self.api}/object/item/{service_user}")
                username = get_json_property_value(item, "data_login_username")
                passsword = get_json_property_value(item, "data_login_password")
                uri = get_json_property_value(item, "data_login_uris_0_uri")
                item = get_totp(f"{self.api}/object/totp/{service_user}")
                if item is not None: totp = get_json_property_value(item, "data_data") 
                else: totp = None 

                # Download Documents with the help of the appropriate automation library
                if automation_library.lower() == "playwright":
                    if not retrieve_from_service_with_playwright(servicename, uri, username, passsword, totp, self.debug):
                        # Skip the failed service/user pair; the remaining services
                        # still run. The run exits with code 1 if any pair failed.
                        logger.error(f"Service {service_user} failed; continuing with the next service.")
                        failed = True
    #
    #################

    if service is not None and not matched:
        logger.warning(f"Service filter '{service}' matched no service in {self.fname}; nothing was done.")

    if failed:
        logger.error("Run finished with failed service(s); exiting with code 1.")
        sys.exit(1)

if __name__ == "__main__":
    sys.stdout = sys.__stdout__

    load_dotenv()

    # Optional per-service filter: --service <NAME>. Extracted before the
    # positional handling, so the existing <ini> [debug] call (incl. cron)
    # stays fully compatible.
    service = None
    if "--service" in sys.argv[1:]:
        if sys.argv[-1] == "--service":
            logger.error("Error: --service requires a value.")
            sys.exit(1)
        idx = sys.argv.index("--service")
        service = sys.argv[idx + 1]
        del sys.argv[idx:idx + 2]

    bc = defs(None, os.getenv("BW_API_URL"))

    if is_debug_session():
        # Debugging
        logger.info("Executed in debugger. Debug mode enabled.")
        bc.fname = INI_DEFAULT_TEST_FILE
        bc.debug = True
    else:
        # Command line handling
        if len(sys.argv) < 2 or len(sys.argv) > 3:
            logger.error(" Usage: python3 BillCollector.py <ini-filename> [\"debug\"] [--service <NAME>]")
            sys.exit(1)
        if os.path.isfile(sys.argv[1]) == False:
            logger.error(f"File {sys.argv[1]} not found.")
            sys.exit(1)
        # The optional 2nd positional argument is the debug switch and its
        # value is honored: "debug"/"True"/"1" turn it on, "False"/"0"/"no"/
        # "off" keep it off. The previous presence-only check forced debug on
        # for any value, so the documented `BillCollector.sh <ini> False` run
        # unexpectedly ran headed with debug logging.
        if len(sys.argv) == 2:
            bc.debug = False
        else:
            bc.debug = sys.argv[2].strip().lower() in {"1", "true", "t", "yes", "y", "on", "debug"}
            if bc.debug:
                logger.info("Debug mode enabled.")
            else:
                logger.info(f"Debug mode off (switch: {sys.argv[2]}).")
        bc.fname = sys.argv[1]

    setup_logging(LOG_DEFAULT_FILE, debug=bc.debug)

    # Reject a second concurrent run (overlapping cron starts, UI run + debug
    # session). The module-level handle keeps the fd - and the lock - open
    # until the process exits.
    run_lock = acquire_run_lock()

    WebRetriDoc(bc, "playwright", service)
