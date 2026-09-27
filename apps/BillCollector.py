# BillCollector
# Retrieval of Documents from Web Services

import os
import sys
from dotenv import load_dotenv
import re
from nslookup import Nslookup
import time
import logging
import requests
import json
import configparser
from flatten_json import flatten

from BillCollectorServices_pw import retrieve_from_service_with_playwright
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

def extract_ip(string):
    # Regex for IP addresses
    ip_pattern = re.compile(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b')
    match = ip_pattern.search(string)
    if match:
        return match.group()
    return None

def is_local_ip(ip):
    # Local IP ranges
    local_ip_ranges = [
        re.compile(r'^10\.'),  # 10.0.0.0 - 10.255.255.255
        re.compile(r'^172\.(1[6-9]|2[0-9]|3[0-1])\.'),  # 172.16.0.0 - 172.31.255.255
        re.compile(r'^192\.168\.'),  # 192.168.0.0 - 192.168.255.255
    ]
    for pattern in local_ip_ranges:
        if pattern.match(ip):
            return True
    return False

# Check DNS for domain is directing to local IP
def is_domain_local_ip(domain, try_count=3):
    dns_query = Nslookup()
    for attempt in range(1, try_count + 1):
        try:
            ips_record = dns_query.dns_lookup(domain)
            ip = extract_ip(' '.join(ips_record.answer))
            if ip:
                if is_local_ip(ip):
                    return ip
                else:
                    logger.error("No local IP address.")
                    return False
            else:
                logger.warning(f"No IP address received on attempt {attempt}.")
        except Exception as e:
            logger.warning(f"DNS Exception on attempt {attempt}: {e}")
        finally:
            time.sleep(1)

# Get web content
def get_json(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if 400 <= response.status_code < 500:
            if "No TOTP" in response.text: 
                pass
            else: 
                logger.error(f"Client error: {response.status_code} - {response.text}")
                sys.exit(1)
        else: 
            logger.error(f"Error with request: {e}")
            sys.exit(1)
    except (requests.exceptions.ConnectionError, 
            requests.exceptions.Timeout, 
            requests.exceptions.RequestException) as e:
        logger.error(f"Error with request: {e}")
        sys.exit(1)
    else:
        return response.text

# Check Bitwarden API status
def bitwarden_api_check_status(url):
    content = get_json(f"{url}/status")
    logger.debug(content)
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
    response = requests.post(url, json=payload)
    if response.status_code == 201 or response.status_code == 200:
        logger.info("Successfully posted!")
        return json.dumps(response.json())
    else:
        logger.error(f"Error: {response.status_code} - {response.text}")
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

    # Check if <domain> is resolvable and directs to a local IP address
    ip = is_domain_local_ip(self.vault)
    if not ip:
        sys.exit(1)
    logger.info(f"{self.vault} is resolvable and directs to local IP {ip}")

    # Check if Bitarden API at <bw_api_url> responds with success=true
    ret, status = bitwarden_api_check_status(self.api)
    if not ret or not status == "unlocked":
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
                item = get_json(f"{self.api}/object/totp/{service_user}")
                if item is not None: totp = get_json_property_value(item, "data_data") 
                else: totp = None 

                # Download Documents with the help of the appropriate automation library
                if automation_library.lower() == "playwright":
                    retrieve_from_service_with_playwright(servicename, uri, username, passsword, totp, self.debug)
    #
    #################

    if service is not None and not matched:
        logger.warning(f"Service filter '{service}' matched no service in {self.fname}; nothing was done.")

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

    bc = defs(
        os.getenv("VAULT_HOST"), 
        os.getenv("BW_API_URL")) #, 

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
        if len(sys.argv) == 2:
            bc.debug = False
        else:
            bc.debug = True
            logger.info("Debug mode enabled.")
        bc.fname = sys.argv[1]

    setup_logging(LOG_DEFAULT_FILE, debug=bc.debug)

    WebRetriDoc(bc, "playwright", service)
