# -*- coding: utf-8 -*-

# Bill Collector Helpers
# This module contains helper functions and classes for the Bill Collector application.

# Basic Settings; files and dirs relative to the script
DOWNLOAD_DIR = "Downloads"                                          # Directory for downloaded files
INI_DEFAULT_FILE = "bc_default.ini"                                 # Default INI file
INI_DEFAULT_TEST_FILE = "bc_test.ini"                               # Test INI file
LOG_DEFAULT_FILE = "bc.log"                                         # Default log file

RECIPES_SELENIUM_DIR = "recipes_selenium"                           # Directory for recipes
RECIPES_SELENIUM_PREFIX = "recipe-se__"                             # Prefix for Selenium recipes
CHROMIUM_SELENIUM_DIR = "chrome-linux64/chrome"                     # Directory for Chromium Selenium
CHROMEDRIVER_SELENIUM_DIR = "chromedriver-linux64/chromedriver"     # Directory for ChromeDriver Selenium

RECIPES_PLAYWRIGHT_DIR = "recipes_playwright"                       # Directory for recipes
RECIPES_PLAYWRIGHT_PREFIX = "recipe-pw__"                           # Prefix for Playwright recipes

# Service variables
class service_vars:
    def __init__(self, usr, pwd, otp, dbg, dld, yml=None, drv=None):
        self.drv = drv
        self.usr = usr
        self.pwd = pwd
        self.otp = otp
        self.dbg = dbg
        self.dld = dld
        self.yml = yml

# Web Element Object
class webElementObj:
    class selectorObj:
        def __init__(self, locator, element):
            self.locator = locator
            self.element = element
    def __init__(self, timeout=10, variable=None, graceful=False, keys=None):
        self.timeout = timeout
        self.graceful = graceful
        self.variable = variable
        self.keys = keys
