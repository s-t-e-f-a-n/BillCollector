import os
import re
import inspect
import sqlite3
import json

from datetime import datetime

from playwright.sync_api import Playwright, sync_playwright, Route, Request, Page

from BillCollectorRecipes import CheckRecipe
from BillCollectorHelpers import *

def InitBrowser(p, bcs):
    """Initialize the browser with a persistent context to always open PDF externally"""
    try:
        browser = p.chromium.launch_persistent_context(
            headless=not bcs.dbg,
            user_data_dir=CHROMIUM_PLAYWRIGHT_PROFILE
            )
        # following Default/Preferences entry is required:
        #   {
        #       "plugins": {
        #           "always_open_pdf_externally": true
        #       }
        #   }
        # Todo: add general method for profile creation/preparation
        #  https://www.chromium.org/administrators/configuring-other-preferences/
        #  https://support.google.com/chrome/a/answer/187948?sjid=14232849532875888309-EU
        # Following has not worked for me: https://github.com/microsoft/playwright/issues/7822
        #
    except Exception as e:
        print(f"Error: {e}")
        return None
    return browser

class DatabaseManager:
    """Manages service-specific and run-specific tables."""
    
    def __init__(self, db_name):
        """Initialize the central tracking system."""
        self.db_name = db_name
        self.conn = sqlite3.connect(self.db_name)
        self.cursor = self.conn.cursor()

        # Central service tracking table
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS Service (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_name TEXT NOT NULL,
            run_number INTEGER NOT NULL,
            run_table TEXT NOT NULL,
            timestamp_end DATETIME,
            download_info JSON,
            result TEXT
        );
        """)
        self.conn.commit()

    def create_service_run_table(self, service_name):
        """Creates a new run table for a service and registers it in the Service table."""
        run_number = self.get_latest_run_number(service_name) + 1
        run_id = f"{service_name}_Run{run_number}"
        table_name = f"PageStatus_{run_id}"

        # Create the service run table
        self.cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_name TEXT NOT NULL,
            step_number INTEGER NOT NULL,
            action TEXT NOT NULL,
            action_args JSON,
            locator TEXT,
            locator_args JSON,
            aria_snapshot JSON,
            dom_status TEXT,
            result TEXT
        );
        """)

        # Register the run in the Service table
        self.cursor.execute("""
        INSERT INTO Service (service_name, run_number, run_table) 
        VALUES (?, ?, ?)
        """, (service_name, run_number, table_name))

        self.conn.commit()
        return table_name  # Return the created table name

    def get_latest_run_number(self, service_name):
        """Finds the highest run number for a service."""
        self.cursor.execute("SELECT MAX(run_number) FROM Service WHERE service_name = ?", (service_name,))
        result = self.cursor.fetchone()[0]
        return result if result else 0  # Start at 0 if no previous runs exist

    def insert_page_status(self, table_name, page_state):
        """Stores a PageState entry in the correct service run table."""
        self.cursor.execute(f"""
        INSERT INTO {table_name} (
            service_name, step_number, action, action_args, locator, 
            locator_args, aria_snapshot, dom_status, result
        ) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            page_state.service_name,
            page_state.step_number,
            page_state.action,
            json.dumps(page_state.action_args),
            page_state.locator,
            json.dumps(page_state.locator_args),
            json.dumps(page_state.aria_snapshot),
            page_state.dom_status,
            page_state.error_status  # Stores error message or None
        ))

        self.conn.commit()

    def finalize_service_run(self, service_name, run_table, download_info, result):
        """Updates the Service table with timestamp_end, download_info, and result at the end of a service run."""
        timestamp_end = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        download_info_json = json.dumps(download_info) if download_info else None

        self.cursor.execute("""
            UPDATE Service 
            SET timestamp_end = ?, download_info = ?, result = ?
            WHERE service_name = ? AND run_table = ?
        """, (timestamp_end, download_info_json, result, service_name, run_table))

        self.conn.commit()

    def close_connection(self):
        """Closes the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
            self.cursor = None

    # Insert step-by-step details
    class PageState:
        def __init__(self, service_name, step_number):
            self.service_name = service_name
            self.step_number = step_number
            self.action = "Click"
            self.action_args = {"button": "submit"}
            self.locator = "xpath://button[@id='submit']"
            self.locator_args = {"visible": True}
            self.aria_snapshot = {"role": "button", "name": "Submit"}
            self.dom_status = "<button id='submit'>Submit</button>"
            self.error_status = None

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

class PageState:
    """Represents the state of a page at a given time."""
    def __init__(self, 
                 service_name: str,
                 step_number: int,
                 page: Page, 
                 action: str, 
                 action_args: dict, 
                 locator: str, 
                 locator_args: dict
                 ):
        
        self.service_name = service_name
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.step_number = step_number
        self.action = action
        self.action_args = action_args or {}
        self.locator = locator
        self.locator_args = locator_args or {}
        self.aria_snapshot = page.accessibility.snapshot()
        self.dom_status = page.content()
        self.error_status = None
        self.download_info = None

    def set_error(self, error_message: str):
        """Sets an error status"""
        self.error_status = error_message

    def set_download_info(self, download_info):
        """Sets the download information"""
        self.download_info = download_info

    def to_dict(self):
        """Returns the object data as a dictionary"""
        return {
            "action_type": self.action_type,
            "locator_method": self.locator_method,
            "aria_snapshot": self.aria_snapshot,
            "dom_status": self.dom_status,
            "error_status": self.error_status,
            "download_info": self.download_info,
        }


def retrieve_from_service_with_playwright(service, url, user, pwd, otp, debug):
    """Retrieve file from service - main function - Playwright variant    """

    bcs = ServiceObj(service=service, usr=user, pwd=pwd, otp=otp, dbg=debug, dld=DOWNLOAD_DIR)
    if not os.path.exists(bcs.dld):
        os.makedirs(bcs.dld)
    
    on_debug_start_keyboard_listener(bcs)
    try:
        sname = service.lower().replace(" ", "_")
        bcs.yml = CheckRecipe(f"{APP_DIR}/{RECIPES_PLAYWRIGHT_DIR}/{RECIPES_PLAYWRIGHT_PREFIX}{sname}.yaml")
        
        if bcs.yml == None: raise Exception(f"Recipe {sname} not found.")
        file_downloaded = perform_actions(bcs)
        if file_downloaded != None: print(f"Service {service} for {bcs.usr} finished with downloaded file(s) {file_downloaded}.")
        else: print(f"Service {service} for {bcs.usr} finished without a file downloaded.")
        on_debug_stop_keyboard_listener(bcs)
        return True
    except Exception as e:
        print(f"EXCEPTION in {inspect.currentframe().f_code.co_name}(): {e}")
        print(f"Service {service} for {bcs.usr} not successfully finished.")
        on_debug_stop_keyboard_listener(bcs)
        return False

def perform_actions(bcs):
    """Perform actions from YAML recipe on web elements - helper function for dispatching actions"""
    file_downloaded = []

    try:
        with sync_playwright() as p:
            bcs.drv = InitBrowser(p, bcs)
            bcs.page = bcs.drv.new_page()
            bcs.page.context.clear_cookies()

            # Parse the YAML structure
            services = bcs.yml.get('services', [])
            
            for service in services:
                    service_name = service.get('serviceName')
                    print(f"Processing Service: {service_name} for {bcs.usr}.")
                    
                    # Initialize the database manager and create a service run table
                    db = DatabaseManager(DB_FILE)
                    run_table = db.create_service_run_table(service_name)

                    steps = service.get('steps', [])
                    for step in sorted(steps, key=lambda x: x.get('step', 0)):  # Sort by step number
                        step_state = process_step(bcs, step)
                      
                        if step_state and step_state.download_info != None:
                            step_state.download_info.value.save_as(os.path.join(
                                                                    DOWNLOAD_DIR, 
                                                                    step_state.download_info.value.suggested_filename))
                            file_downloaded.append(step_state.download_info.value)
                        if step_state:
                            # Save the page state to the database
                            db.insert_page_status(run_table, step_state)

                    db.finalize_service_run(
                        service_name=service_name,
                        run_table=run_table,
                        download_info = {
                            "suggested_filename": step_state.download_info.value.suggested_filename,
                            "url": step_state.download_info.value.url,
                            },
                        result=step_state.error_status
                    )

                    # Close the database connection
                    db.close_connection()

            # Close the page after processing all steps
            bcs.page.close()
            bcs.drv.close()

    except Exception as e:
        print(f"EXCEPTION in {inspect.currentframe().f_code.co_name}(): {e}")
    else:
        return file_downloaded

def process_step(bcs, step):
    """Process a single step, handling nested steps recursively."""
    step_number = step.get('step')
    description = step.get('description', "No description provided.")
    action_type = step.get('actionType', [])
    arguments = step.get('arguments', [])
    locators = step.get('locators', [])
    nested_steps = step.get("steps", [])

    print(f"  Processing Step {step_number}: {action_type} - {description}")
    on_debug_pause_check(bcs)

    if locators and nested_steps:
        raise Exception("Error: Locators and nested steps cannot be used together in the same step.")

    perform_action_name = ACTION_MAP.get("playwright", {}).get(action_type)
    if perform_action_name is None:
        raise Exception(f"Error: Unsupported action type: {action_type}")

    perform_action = globals().get(perform_action_name)
    if not callable(perform_action):
        raise Exception(f"Error: Function {perform_action_name} is not callable or not found")

    return ( perform_action(bcs, arguments, locators or nested_steps, step_number) ) 
    

def perform__goto(bcs, arguments, locators, step_number):
    """Navigate to a URL provided in the arguments."""
    url = next((item.get('url') for item in (arguments or []) if 'url' in item), None)
    if url:
        bcs.page.goto(url)
        print(f"  Navigated to {url}")
        page_state = PageState(bcs.service, step_number, bcs.page, "goto", f"'url': {url}", None, None)
        page_state.set_error(None)
        return page_state
    else:
        raise Exception("URL not provided in arguments.")
    
def perform__click(bcs, arguments, locators, step_number):
    """Click on a web element using the specified locator."""
    return ( perform_locator_action(bcs, "click", arguments, locators, step_number) )

def perform__fill(bcs, arguments, locators, step_number):
    """Fill a web element using the specified locator."""
    return ( perform_locator_action(bcs, "fill", arguments, locators, step_number) )

def perform__expect_download(bcs, arguments, steps, step_number):
    """Expect a download to occur after performing actions."""
    with bcs.page.expect_download() as download_info:
        for step in sorted(steps, key=lambda x: x.get('step', 0)):
            page_state = process_step(bcs, step)
        page_state.set_download_info(download_info)
    return page_state

def perform_locator_action(bcs, action, arguments, locators, step_number):
    """Perform action on locator: page.<locator-method>(**locator_kwargs).<action>(**action_kwargs)"""
    # Safely process action arguments
    action_kwargs = {}
    action_orig_kwargs = {}
    if arguments:
        for arg in arguments:
            for key, value in arg.items():
                value_copy = str(value)
                # Find all occurrences of variables in {{}} format
                matches = re.findall(r"\{\{(.*?)\}\}", str(value))
                for match in matches:
                    full_variable = f"{{{{{match}}}}}"  # Recreate full variable format
                    # Replace if variable exists in VARIABLE_MAP
                    if full_variable in VARIABLE_MAP:
                        value = value.replace(full_variable, str(VARIABLE_MAP[full_variable](bcs)))
                # Store the resolved value
                action_kwargs[key] = value
                action_orig_kwargs[key] = value_copy

    # Extract locator information
    locator_type = next((item.get("locatorType") for item in (locators or []) if "locatorType" in item), None)
    locator_arguments = next((item for item in (locators or []) if "arguments" in item), None)

    # Create action with (optional) arguments on locator with arguments
    if locator_type and locator_arguments:
        locator_kwargs = {key: value for arg in locator_arguments.get("arguments", []) if arg for key, value in arg.items()}
        if locator_kwargs:
            locator_method = getattr(bcs.page, locator_type, None)
            if callable(locator_method):
                locator_object = locator_method(**locator_kwargs)
                if hasattr(locator_object, action):  # Ensure action method exists
                    action_method = getattr(locator_object, action)
                    if callable(action_method):
                        page_state = PageState(bcs.service, step_number, bcs.page, action, action_orig_kwargs, locator_type, locator_kwargs)
                        try:
                            action_method(**action_kwargs)  # Execute action with arguments
                            page_state.set_error(None)
                        except Exception as e:
                            page_state.set_error(str(e))
                        finally:
                            return page_state
                    else:
                        raise TypeError(f"Error: '{action}' is not callable on {locator_object}")
                else:
                    raise AttributeError(f"Error: Action '{action}' not found on locator '{locator_type}'")
            else:
                raise AttributeError(f"Error: Locator method '{locator_type}' not found on bcs.page")
    else:
        raise ValueError("Error: LocatorType or arguments not provided.")
