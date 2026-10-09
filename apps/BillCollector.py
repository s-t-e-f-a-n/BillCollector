# BillCollector
# Retrieval of Documents from Web Services

import os
import sys
from dotenv import load_dotenv
import re
import logging
import configparser

from BillCollectorServices_pw import retrieve_from_service_with_playwright
from billcollector.vault import (
    VAULT_MAX_ATTEMPTS,
    VAULT_RETRY_BACKOFF,
    VaultAPIError,
    bitwarden_api_check_status,
    get_json,
    get_json_property_value,
    get_totp,
    is_json_property_value,
    post_json,
)
from vault_transport import VaultTransportError, pinned_api_url
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

# The Vaultwarden API client lives in billcollector.vault (shared with the
# daemon runner): explicit timeouts, 3x retry on transient failures, 4xx
# reported as VaultAPIError with the status code. This entry point translates
# VaultAPIError into its documented exit codes.

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
    try:
        ret, status = bitwarden_api_check_status(self.api)
    except VaultAPIError as e:
        # Log only the parsed state; the status body also holds account identity.
        logger.error(f"Vault API status check failed: {e}")
        sys.exit(1)
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
                try:
                    item = get_json(f"{self.api}/object/item/{service_user}")
                    username = get_json_property_value(item, "data_login_username")
                    passsword = get_json_property_value(item, "data_login_password")
                    uri = get_json_property_value(item, "data_login_uris_0_uri")
                    item = get_totp(f"{self.api}/object/totp/{service_user}")
                    if item is not None: totp = get_json_property_value(item, "data_data")
                    else: totp = None
                except VaultAPIError as e:
                    # A vault failure aborts only this pair; the remaining
                    # services still run and the process exits 1 at the end.
                    logger.error(f"Service {service_user}: vault credential error: {e}")
                    failed = True
                    continue

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
