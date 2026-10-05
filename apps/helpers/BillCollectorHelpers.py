# -*- coding: utf-8 -*-
import fcntl
import os
import sys
import logging
import logging.handlers
import threading
import time

from sshkeyboard import listen_keyboard, stop_listening

logger = logging.getLogger(__name__)


# Bill Collector Helpers
# This module contains helper functions and classes of the Bill Collector application.

# Basic Settings; files and dirs relative to the script's application directory
APP_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))                      # Application directory
DOWNLOAD_DIR = os.path.join(APP_DIR, "Downloads")                                           # Directory for downloaded files
INI_DEFAULT_FILE = os.path.join(APP_DIR, "bc_default.ini")                                  # Default INI file
INI_DEFAULT_TEST_FILE = os.path.join(APP_DIR, "bc_test.ini")                                # Test INI file
LOG_DEFAULT_FILE = os.path.join(APP_DIR, "bc.log")                                          # Default log file

RECIPES_PLAYWRIGHT_DIR = os.path.join(APP_DIR, "recipes_playwright")                        # Directory for recipes
RECIPES_PLAYWRIGHT_SCHEMA_FILE = os.path.join(RECIPES_PLAYWRIGHT_DIR, "recipe-pw-schema.yaml")  # Schema file for Playwright recipes
RECIPES_PLAYWRIGHT_PREFIX = "recipe-pw__"                                                   # Prefix for Playwright recipes
RECIPES_PLAYWRIGHT_CODE_DIR = os.path.join(RECIPES_PLAYWRIGHT_DIR, ".code")                  # Directory for Playwright python code 
CHROMIUM_PLAYWRIGHT_DIR = os.path.join(APP_DIR, "browser")                                  # Directory for Chromium Playwright
CHROMIUM_PLAYWRIGHT_PROFILE = os.path.join(CHROMIUM_PLAYWRIGHT_DIR, "profile")              # Directory for Chromium Playwright profile

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = CHROMIUM_PLAYWRIGHT_DIR                            # Set environment variable for Playwright browsers path

DB_DIR = os.path.join(APP_DIR, "db")                                                        # Directory for database files
DB_FILE = os.path.join(DB_DIR, "bc.db")                                                     # Database file
os.makedirs(DB_DIR, exist_ok=True)

LOCK_FILE = os.path.join(APP_DIR, ".bc.lock")                                               # Run lock file (flock)

# Reject a second concurrent run (overlapping cron starts, UI run + debug
# session, two manual runs). The lock is a non-blocking exclusive flock on
# LOCK_FILE: the kernel holds it on the file descriptor and releases it
# automatically when the process exits - even on SIGKILL - so no stale-lock
# cleanup is needed. The caller must keep the returned handle alive for the
# lifetime of the process (closing the fd releases the lock).
def acquire_run_lock():
    try:
        lock = open(LOCK_FILE, "a+")
    except OSError as e:
        logger.error(f"Error: cannot open run lock {LOCK_FILE}: {e}")
        sys.exit(1)
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.error(f"Another BillCollector run is already in progress "
                     f"(lock file: {LOCK_FILE}); refusing to start.")
        sys.exit(1)
    except OSError as e:
        logger.error(f"Error: cannot lock run lock {LOCK_FILE}: {e}")
        sys.exit(1)
    logger.info(f"Run lock acquired: {LOCK_FILE}")
    return lock

# Configure the root logger: optional rotating file handler plus a plain stdout handler
# (stdout is what the daemon streams to the UI)
def setup_logging(logfile=None, debug=False, max_bytes=5_000_000, backup_count=5):
    # HTTP debug records contain request URLs, including private vault item names.
    # Disable dependency logging before the idempotence guard for every entry point.
    for name in ("urllib3", "requests.packages.urllib3"):
        logging.getLogger(name).setLevel(logging.CRITICAL + 1)
    root = logging.getLogger()
    if root.handlers:  # idempotent - safe if called twice in one process
        return
    root.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s %(name)s [%(process)d] %(levelname)s: %(message)s",
        "%b %d %H:%M:%S")
    fmt.converter = time.localtime
    if logfile is not None:
        file_handler = logging.handlers.RotatingFileHandler(
            logfile, maxBytes=max_bytes, backupCount=backup_count)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if debug else logging.INFO)
    console.setFormatter(fmt)
    root.addHandler(console)

# Map yaml recipe action types to perform functions
ACTION_MAP = {
    "playwright": 
    {"goto": "perform__goto",
    "click": "perform__click",
    "fill": "perform__fill",
    "expect_download": "perform__expect_download"},
}

# Map yaml variables to function variables
VARIABLE_MAP = {
    "{{USERNAME}}": lambda bcs: bcs.usr,
    "{{PASSWORD}}": lambda bcs: bcs.pwd,
    "{{OTP}}": lambda bcs: bcs.otp,
}

# Dynamic keyword mapping for multi-language string replacements ---
VARIABLE_LABELS = {
    "{{USERNAME}}": ["username", "benutzername", "user", "login", "e-mail", "email", "mail"],
    "{{PASSWORD}}": ["password", "passwort", "pwd", "kennwort"],
    "{{OTP}}": ["totp", "authcode", "verification", "code", "mfa"],
}

# Service variables
class ServiceObj:
    def __init__(self, service, usr, pwd, otp, dbg, dld, yml=None, drv=None, page=None, db=None, run_table=None):
        self.service = service
        self.db = db
        self.run_table = run_table
        self.page = page
        self.drv = drv
        self.usr = usr
        self.pwd = pwd
        self.otp = otp
        self.dbg = dbg
        self.dld = dld
        self.yml = yml

# Web Element Object
class WebElementObj:
    class SelectorObj:
        def __init__(self, locator, element):
            self.locator = locator
            self.element = element
    def __init__(self, timeout=10, variable=None, graceful=False, keys=None):
        self.timeout = timeout
        self.graceful = graceful
        self.variable = variable
        self.keys = keys

# Check whether the current process runs inside a debugger
# sys.gettrace() covers pdb and classic tracing; debugpy (VS Code) and PyCharm
# inject pydevd, and on Python 3.12+ trace via sys.monitoring, not sys.settrace
def is_debug_session():
    if sys.gettrace():
        return True
    return "pydevd" in sys.modules or "debugpy" in sys.modules

# Start keyboard listener if debugging is enabled
def on_debug_start_keyboard_listener(bcs):
    global listener_thread
    if bcs.dbg == True: 
        global pause
        pause = True
        listener_thread = threading.Thread(target=thread_keyboard_listener, daemon=True)
        listener_thread.start()

# Stop keyboard listener if debugging is enabled
def on_debug_stop_keyboard_listener(bcs):
    global listener_thread
    if bcs.dbg == True:
       pause = True
       stop_listening()
       listener_thread.join()

# THREAD - Keyboard listener (space key to pause/resume)
def thread_keyboard_listener():
    def handle_key_press(key):
        global pause
        if key == "space": pause = not pause
    listen_keyboard(on_press=handle_key_press)

# Check for pause for debugging if debugging is enabled
def on_debug_pause_check(bcs):
    if bcs.dbg: pause_check()

# Pause check
def pause_check():
    global pause
    if pause: logger.info("Paused. Press <SPACE> to resume.")
    while pause: time.sleep(0.1)
    logger.info("Resume.")
    pause = True # Pause again after resuming
