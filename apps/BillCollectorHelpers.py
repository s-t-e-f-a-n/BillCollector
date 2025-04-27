# -*- coding: utf-8 -*-
import os
import threading
import time

from sshkeyboard import listen_keyboard, stop_listening


# Bill Collector Helpers
# This module contains helper functions and classes of the Bill Collector application.

# Basic Settings; files and dirs relative to the script's application directory
APP_DIR = os.path.dirname(os.path.realpath(__file__))                                       # Application directory
DOWNLOAD_DIR = os.path.join(APP_DIR, "Downloads")                                           # Directory for downloaded files
INI_DEFAULT_FILE = os.path.join(APP_DIR, "bc_default.ini")                                  # Default INI file
INI_DEFAULT_TEST_FILE = os.path.join(APP_DIR, "bc_test.ini")                                # Test INI file
LOG_DEFAULT_FILE = os.path.join(APP_DIR, "bc.log")                                          # Default log file

RECIPES_SELENIUM_DIR = "recipes_selenium"                                                   # Directory for recipes
RECIPES_SELENIUM_SCHEMA_FILE = "recipe-se-schema.yaml"                                      # Schema file for Selenium recipes
RECIPES_SELENIUM_PREFIX = "recipe-se__"                                                     # Prefix for Selenium recipes
CHROMIUM_SELENIUM_DIR = os.path.join(APP_DIR, "chrome-linux64", "chrome")                   # Directory for Chromium Selenium
CHROMEDRIVER_SELENIUM_DIR = os.path.join(APP_DIR, "chromedriver-linux64", "chromedriver")   # Directory for ChromeDriver Selenium

RECIPES_PLAYWRIGHT_DIR = "recipes_playwright"                                               # Directory for recipes
RECIPES_PLAYWRIGHT_SCHEMA_FILE = "recipe-pw-schema.yaml"                                    # Schema file for Playwright recipes
RECIPES_PLAYWRIGHT_PREFIX = "recipe-pw__"                                                   # Prefix for Playwright recipes
CHROMIUM_PLAYWRIGHT_DIR = os.path.join(APP_DIR, "browser")                                  # Directory for Chromium Playwright
CHROMIUM_PLAYWRIGHT_PROFILE = os.path.join(CHROMIUM_PLAYWRIGHT_DIR, "profile")              # Directory for Chromium Playwright profile

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = CHROMIUM_PLAYWRIGHT_DIR                            # Set environment variable for Playwright browsers path

DB_DIR = os.path.join(APP_DIR, "db")                                                        # Directory for database files
DB_FILE = os.path.join(DB_DIR, "bc.db")                                                     # Database file

# Service variables
class ServiceObj:
    def __init__(self, service, usr, pwd, otp, dbg, dld, yml=None, drv=None, page=None):
        self.service = service
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
    if pause: print ("Paused. Press <SPACE> to resume.")
    while pause: time.sleep(0.1)
    print ("Resume.")
    pause = True # Pause again after resuming
