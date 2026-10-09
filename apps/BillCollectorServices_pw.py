import os
import shutil
import re
import inspect
import logging
import sqlite3
import json

from datetime import datetime
from playwright.sync_api import Playwright, sync_playwright, Route, Request, Page
from helpers import *
from billcollector.config import chromium_args

logger = logging.getLogger(__name__)

class StepAbortError(Exception):
    """A non-graceful step (or download) failed: abort the remaining steps of the run.
    Carries the PageState of the failing step so it can still be recorded in the DB."""

    def __init__(self, message, page_state=None):
        super().__init__(message)
        self.page_state = page_state

def InitBrowser(p, bcs):
    """Initialize the browser with a persistent context to always open PDF externally"""
    try:
        if not init_browser_profile():
            raise Exception("Failed to initialize browser profile.")
        browser = p.chromium.launch_persistent_context(
            headless=not bcs.dbg,
            user_data_dir=CHROMIUM_PLAYWRIGHT_PROFILE,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 \
                     (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            args=chromium_args(),
            )
    except Exception as e:
        logger.error(f"Error: {e}")
        return None
    return browser

def init_browser_profile():
    """Initialize the browser profile for Playwright Chromium."""
    # https://www.chromium.org/administrators/configuring-other-preferences/
    # https://support.google.com/chrome/a/answer/187948?sjid=14232849532875888309-EU
    # The following has not worked for me: https://github.com/microsoft/playwright/issues/7822
    try:
        if os.path.exists(CHROMIUM_PLAYWRIGHT_PROFILE):
            shutil.rmtree(CHROMIUM_PLAYWRIGHT_PROFILE)  # Remove existing profile directory
        os.makedirs(os.path.join(CHROMIUM_PLAYWRIGHT_PROFILE, "Default"), exist_ok=True)  # Create a new profile directory
        content = {"plugins": {"always_open_pdf_externally": True}} # Set the preference to always open PDFs externally
        with open(os.path.join(CHROMIUM_PLAYWRIGHT_PROFILE, "Default", "Preferences"), "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2)
    except Exception as e:
        logger.error(f"Error initializing browser profile: {e}")
        return False
    else:
        return True

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
            timestamp_start DATETIME,
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
            locator_action JSON,
            interactive_elements JSON,
            result JSON
        );
        """)

        # Get the local timestamp
        local_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Register the run in the Service table and set the start timestamp
        self.cursor.execute("""
        INSERT INTO Service (service_name, run_number, run_table, timestamp_start) 
        VALUES (?, ?, ?, ?)
        """, (service_name, run_number, table_name, local_time))

        self.conn.commit()
        return table_name

    def get_latest_run_number(self, service_name):
        """Finds the highest run number for a service."""
        self.cursor.execute("SELECT MAX(run_number) FROM Service WHERE service_name = ?", (service_name,))
        result = self.cursor.fetchone()[0]
        return result if result else 0  # Start at 0 if no previous runs exist

    def insert_page_status(self, table_name, page_state):
        """Stores a PageState entry in the correct service run table."""
        self.cursor.execute(f"""
        INSERT INTO {table_name} (
            service_name, step_number, locator_action, interactive_elements, result
        ) 
        VALUES (?, ?, ?, ?, ?)
        """, (
            page_state.service_name,
            page_state.step_number,
            json.dumps(page_state.locator_action),  # Stores locator and action information
            json.dumps(page_state.interactive_elements),  # Stores interactive elements
            json.dumps(page_state.error_status)  # Stores error message or None
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

# PageState (interactive-element scan incl. bounding boxes) lives in
# billcollector.pagestate: shared with the daemon runner (M1 extraction).
from billcollector.pagestate import PageState


def retrieve_from_service_with_playwright(service, url, user, pwd, otp, debug):
    """Retrieve file from service - main function - Playwright variant.

    Returns True only if the run completed without aborting and at least one file
    was downloaded successfully; False otherwise (failed/aborted step or no
    download). The caller is expected to treat False as a failed run.
    """

    bcs = ServiceObj(service=service, usr=user, pwd=pwd, otp=otp, dbg=debug, dld=DOWNLOAD_DIR)
    if not os.path.exists(bcs.dld):
        os.makedirs(bcs.dld)
    
    on_debug_start_keyboard_listener(bcs)
    try:
        sname = service.lower().replace(" ", "_")
        bcs.yml = CheckRecipe(os.path.join(RECIPES_PLAYWRIGHT_DIR,f"{RECIPES_PLAYWRIGHT_PREFIX}{sname}.yaml"),
            RECIPES_PLAYWRIGHT_SCHEMA_FILE)
        
        if bcs.yml == None: raise Exception(f"Recipe {sname} not found.")
        file_downloaded, aborted = perform_actions(bcs)
        on_debug_stop_keyboard_listener(bcs)
        if aborted:
            logger.error(f"Service {service} for {bcs.usr} aborted; run failed.")
            return False
        if file_downloaded and all(entry["result"] == "success" for entry in file_downloaded):
            logger.info(f"Service {service} for {bcs.usr} finished with downloaded file(s) {file_downloaded}.")
            return True
        logger.warning(f"Service {service} for {bcs.usr} finished without a successful download.")
        return False
    except Exception as e:
        logger.exception(f"EXCEPTION in {inspect.currentframe().f_code.co_name}(): {e}")
        logger.error(f"Service {service} for {bcs.usr} not successfully finished.")
        on_debug_stop_keyboard_listener(bcs)
        return False

def perform_actions(bcs):
    """Perform actions from YAML recipe on web elements - helper function for dispatching actions.

    Returns (files_downloaded, aborted). aborted is True when a non-graceful step
    failure (or any other error) stopped the run before all services were processed.
    Every started service run is finalized in the DB, even when the run is aborted.
    """

    files_downloaded = []
    aborted = False

    try:
        with sync_playwright() as p:
            bcs.drv = InitBrowser(p, bcs)
            if bcs.drv is None:
                raise Exception("Failed to initialize browser.")
            bcs.page = bcs.drv.new_page()
            bcs.page.context.clear_cookies()

            # Parse the YAML structure
            services = bcs.yml.get('services', [])

            for service in services:
                    service_name = service.get('serviceName')
                    logger.info(f"Processing Service: {service_name} for {bcs.usr}.")

                    # Initialize the database manager and create a service run table
                    bcs.db = DatabaseManager(DB_FILE)
                    bcs.run_table = bcs.db.create_service_run_table(service_name)
                    service_files = []

                    def run_step(step):
                        """Process one step and record it; on abort, record the failing step first."""
                        try:
                            step_state = process_step(bcs, step)
                        except StepAbortError as e:
                            if e.page_state is not None:
                                bcs.db.insert_page_status(bcs.run_table, e.page_state)
                            raise
                        bcs.db.insert_page_status(bcs.run_table, step_state)
                        return step_state

                    try:
                        # process all steps in the service
                        steps = service.get('steps', [])
                        for step in sorted(steps, key=lambda x: x.get('step', 0)):  # Sort by step number

                            step_state = run_step(step)

                            # Check if the previous step expects a download
                            if check_parameter_in_json(step_state.locator_action, {"action": "expect_download"}):
                                result_value = "success"
                                download = None
                                try:
                                    with bcs.page.expect_download() as download_info:
                                        for nested_step in sorted(step.get("steps", []), key=lambda x: x.get("step", 0)):
                                            run_step(nested_step)
                                    download = download_info.value
                                    filepath = os.path.join(DOWNLOAD_DIR, str(download.suggested_filename))
                                    download.save_as(filepath)
                                except StepAbortError:
                                    raise
                                except Exception as e:
                                        result_value = f"failure: download error {e}"
                                if download is None and result_value != "success":
                                    if step.get("graceful", False):
                                        logger.warning(f"Step {step.get('step', 0)} failed to download (graceful, run continues): {result_value}")
                                    else:
                                        raise StepAbortError(f"Step {step.get('step', 0)} failed to download: {result_value}")
                                if download is not None:
                                    service_files.append({
                                        "url": str(download.url),
                                        "suggested_filename": str(download.suggested_filename),
                                        "result": result_value})
                    finally:
                        # All steps processed (or the run aborted) - finalize the service
                        # run, so the DB always holds a terminal result.
                        bcs.db.finalize_service_run(
                            service_name=service_name,
                            run_table=bcs.run_table,
                            download_info = json.dumps(service_files) if service_files else {},
                            result = "failure" if not service_files or not all(entry["result"] == "success" for entry in service_files) else "success"
                        )
                        # Close the database connection
                        bcs.db.close_connection()

                    files_downloaded.extend(service_files)

            # Close the page after processing all steps
            bcs.page.close()
            bcs.drv.close()

    except StepAbortError as e:
        aborted = True
        logger.error(f"Run aborted: {e}")
    except Exception as e:
        aborted = True
        logger.exception(f"EXCEPTION in {inspect.currentframe().f_code.co_name}(): {e}")
    finally:
        return files_downloaded, aborted

def process_step(bcs, step):
    """ Processes a step by executing a chain of methods """

    def process_argument(arg, bcs):
        """ Processes a single argument:
        - For a string that exactly matches a placeholder (e.g. "{{PASSWORD}}"), return the actual value.
        - For a dictionary, replace any placeholder values (leaving the dict intact).
        - For a list, process its elements recursively.
        - Otherwise, return the argument unchanged.
        """
        if isinstance(arg, str):
            return VARIABLE_MAP[arg](bcs) if arg in VARIABLE_MAP else arg
        elif isinstance(arg, dict):
            new_arg = {}
            for key, value in arg.items():
                new_arg[key] = VARIABLE_MAP[value](bcs) if isinstance(value, str) and value in VARIABLE_MAP else value
            return new_arg
        elif isinstance(arg, list):
            return [process_argument(item, bcs) for item in arg]
        else:
            return arg

    def transform_step_to_json(step):
        """Transforms a step object into JSON with locators and actions."""
        
        if not isinstance(step, dict) or "methods" not in step:
            raise ValueError("Invalid step format: Expected a dictionary with a 'methods' key.")

        transformed_step = {
            "description": step.get("description", ""),
            "locators": [],
            "actions": []
        }

        for method_entry in step["methods"]:
            method_name = method_entry.get("method")
            arguments = method_entry.get("arguments", [])

            if not method_name:
                continue  # Skip invalid methods

            # Categorize as locator or action (just a simple heuristic based on action names)
            if method_name in ["click", "fill", "expect_download", "goto", "close", "content_frame", "first"]:
                transformed_step["actions"] = transformed_step.get("actions", [])
                transformed_step["actions"].append({
                    "action": method_name,
                    "arguments": {k: v for arg in arguments for k, v in arg.items()}
                })
            else: # all other methods are considered locators
                transformed_step["locators"] = transformed_step.get("locators", [])
                transformed_step["locators"].append({
                    "locator": method_name,
                    "arguments": {k: v for arg in arguments for k, v in arg.items()}
                })

        return json.dumps(transformed_step, separators=(",", ":"))


    if not isinstance(step, dict) or "methods" not in step:
        raise ValueError("Invalid step format: Expected a dictionary with a 'methods' key.")

    step_number = step.get("step", 0)
    logger.debug(f"Processing Step {step_number}")
    step_results = {}
    chain_mapping = []  # This will accumulate our mapping entries.
    previous_result = bcs.page  # Starting object.

    page_state = PageState(bcs.service, step_number, bcs.page)
    page_state.set_locator_action(transform_step_to_json(step))

    # A step is "graceful" when its failure must not abort the run:
    # the error is recorded (log + DB) and the run continues with the next step.
    graceful = bool(step.get("graceful", False))

    def fail_step(error_entry):
        """Record a step failure; continue when graceful, otherwise abort the run."""
        step_results.setdefault("error", []).append(error_entry)
        page_state.set_error(step_results)
        if graceful:
            logger.warning(f"Step {step_number} failed (graceful, run continues): {error_entry}")
        else:
            raise StepAbortError(f"Step {step_number} failed: {error_entry}", page_state)

    for method_entry in step["methods"]:
        method_name = method_entry.get("method")
        arguments = method_entry.get("arguments", [])
        processed_args = [process_argument(arg, bcs) for arg in arguments]

        if not method_name:
            fail_step(f"method: {method_name}, message: Method entry missing 'method' key: {method_entry}")
            break # Stop the method chain (graceful failure).

        # Special handling for "expect_download".
        if method_name == "expect_download":
            if "steps" in step and step["steps"]:
                page_state.set_error(step_results)
            else:
                page_state.set_error("error: No nested steps provided for 'expect_download'.")
            break
        # Standard handling of methods
        else:
            method_executor = getattr(previous_result, method_name, None)
            try:
                if method_executor is None:
                    raise AttributeError(f"Method '{method_name}' not found on {type(previous_result).__name__}.")
                if callable(method_executor):
                    if processed_args and all(isinstance(arg, dict) for arg in processed_args):
                        kwargs = {}
                        for d in processed_args:
                            kwargs.update(d)
                        result = method_executor(**kwargs)          # Call the method with keyword arguments.
                    else:
                        result = method_executor(*processed_args)   # Call the method with positional arguments.
                    previous_result = result if result is not None else previous_result
                else:
                    if processed_args:
                        raise TypeError(f"Attribute '{method_name}' is not callable but arguments were provided: {processed_args}")
                    previous_result = method_executor               # Get the value of a property.
            except Exception as e:
                fail_step({"method": method_name, "message": str(e)})
                break # Stop the method chain (graceful failure).
            else:
                page_state.set_error(step_results)

    return page_state

def check_parameter_in_json(json_str, param_dict):
    """Checks if a given key-value pair exists in the JSON structure."""
    
    try:
        data = json.loads(json_str)  # Parse JSON string into a dictionary
        
        # Extract key-value pair from the parameter dictionary
        param_key, param_value = next(iter(param_dict.items()))
        
        # Recursively search for the key-value pair
        def recursive_search(obj):
            if isinstance(obj, dict):
                if param_key in obj and obj[param_key] == param_value:
                    return True
                return any(recursive_search(value) for value in obj.values())
            elif isinstance(obj, list):
                return any(recursive_search(item) for item in obj)
            return False

        return recursive_search(data)

    except json.JSONDecodeError:
        return False  # Return False if the JSON string is invalid
