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

logger = logging.getLogger(__name__)

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

class PageState:
    """Represents the state of a page at a given time."""
    def __init__(self, 
                 service_name: str,
                 step_number: int,
                 page: Page, 
                 ):
        
        self.service_name = service_name
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.step_number = step_number
#        self.aria_snapshot = page.accessibility.snapshot()
#        self.dom_status = page.content()
        self.interactive_elements = self.set_interactive_elements(page)
        self.error_status = None
        self.locator_action = None
    
    def set_error(self, error_message: str):
        """Sets an error status"""
        self.error_status = error_message

    def set_locator_action(self, locator_action):
        """Sets the locator action with the help of transform_step_to_json()"""
        self.locator_action = locator_action

    def set_interactive_elements(self, page):
        """
        Waits for the page to load and gives the DOM time to update dynamically (using a MutationObserver),
        then recursively scans the entire DOM for interactive elements and returns a deduplicated list of locator entries.
        
        Each locator entry is a dictionary containing:
        - role: A generic role such as "button", "link", "textbox", "combobox", "label", "generic interactive", or "unknown".
        - name: The non-empty text used by the locator.
        - locator: A dictionary with:
                • locatorType: One of "get_by_label", "get_by_title", "get_by_role", or "get_by_text".
                • arguments: A dictionary with key arguments (e.g. {"text": "...", "exact": True} for text-based locators or
                {"role": <role>, "name": <name>, "exact": True} for get_by_role).
        - actionTypes: "textbox" elements get ["click", "fill"]; all others get ["click"].
        - For a link (role "link"), if available, an extra "url" key holds the element’s href.
        
        This function is generic and does not depend on any fixed element. It uses a broad DOM traversal (querySelectorAll("*"))
        and filters out only those elements that are visible and "likely interactive" (based on their tag, onclick attribute, or contenteditable). 
        It computes a text value from each element’s innerText and its ::before and ::after pseudo-elements.
        """

        def safe_evaluate(page, script, max_attempts=3):
            """Attempts to evaluate JavaScript on the page, retrying if necessary."""
            for attempt in range(1, max_attempts + 1):
                try:
                    return page.evaluate(script)  # Try evaluating
                except Exception as e:
                    logger.debug(f"Attempt {attempt}: Evaluation failed - {e}")
                    time.sleep(1)  # Short delay before retrying
            logger.warning("All attempts failed.")
            return None  # Return None if evaluation consistently fails

        # Use a MutationObserver to allow dynamic injection to occur.
        js_observer = r'''async () => {
            const observerTime = 3000; // wait for 3 seconds
            await new Promise(resolve => {
                const observer = new MutationObserver(() => {});
                observer.observe(document.body, { childList: true, subtree: true });
                setTimeout(() => { observer.disconnect(); resolve(); }, observerTime);
            });
            return true;
        }'''
        # Run the observer safely to ensure the DOM is stable.
        if not safe_evaluate(page, js_observer): return None
        
        # Now, scan the entire DOM for "likely interactive" elements.
        # We consider an element interactive if:
        #   - Its tag is one of: button, a, input, textarea, select, summary, label
        #   - OR it has an onclick attribute
        #   - OR it is contenteditable.
        js_collect = r'''() => {
            const interactiveTags = ["button", "a", "input", "textarea", "select", "summary", "label"];
            const isInteractive = el => {
                const tag = el.tagName.toLowerCase();
                return interactiveTags.includes(tag) ||
                    el.hasAttribute("onclick") ||
                    (el.getAttribute("contenteditable") && el.getAttribute("contenteditable").toLowerCase() === "true");
            };
            // Get all elements in the DOM.
            const allEls = Array.from(document.querySelectorAll("*"));
            // Filter: only visible and likely interactive.
            const visibleInteractive = allEls.filter(el => {
                const style = window.getComputedStyle(el);
                if (!style || style.display === "none" || style.visibility === "hidden") return false;
                return isInteractive(el);
            });
            // For each element, collect useful properties.
            const cleanContent = str => {
                if (!str || str === "none") return "";
                return str.replace(/^["']|["']$/g, "").trim();
            };
            return visibleInteractive.map(el => {
                const lbl = el.id ? document.querySelector('label[for="' + el.id + '"]') : null;
                const beforeContent = window.getComputedStyle(el, "::before").getPropertyValue("content");
                const afterContent = window.getComputedStyle(el, "::after").getPropertyValue("content");
                const computedText = [cleanContent(beforeContent), el.innerText.trim(), cleanContent(afterContent)]
                                    .filter(Boolean).join(" ").trim();
                return {
                    tag: el.tagName.toLowerCase(),
                    innerText: el.innerText.trim(),
                    computedText: computedText,
                    ariaLabel: el.getAttribute("aria-label") || "",
                    title: el.getAttribute("title") || "",
                    placeholder: el.getAttribute("placeholder") || "",
                    id: el.getAttribute("id") || "",
                    onclick: el.getAttribute("onclick") || "",
                    contenteditable: (el.getAttribute("contenteditable") || "").toLowerCase() === "true",
                    href: el.tagName.toLowerCase() === "a" ? (el.getAttribute("href") || "").trim() : "",
                    value: (el.value || "").toString().trim(),
                    labelText: lbl ? lbl.innerText.trim() : ""
                };
            });
        }'''
        # Run the observer safely to ensure the DOM is stable.
        elements_data = safe_evaluate(page, js_collect)
        if not elements_data: return None

        results = []
        seen = set()
        
        # Map each element's tag to a generic role.
        for data in elements_data:
            tag = data["tag"]
            inner_text = data["innerText"]
            computed_text = data.get("computedText", "")
            aria_label = data["ariaLabel"]
            title_attr = data["title"]
            placeholder = data["placeholder"]
            elm_id = data["id"]
            onclick = data["onclick"]
            contenteditable_flag = data["contenteditable"]
            href = data["href"]
            value = data["value"]
            label_text = data["labelText"]
            
            if tag in ["input", "textarea"]:
                role_val = "textbox"
            elif tag == "select":
                role_val = "combobox"
            elif tag == "button" or tag == "summary":
                # Note: summary is an interactive element and we map it to "button".
                role_val = "button"
            elif tag == "a":
                role_val = "link"
            elif tag == "label":
                role_val = "label"
            elif onclick:
                role_val = "generic interactive"
            else:
                role_val = "unknown"
            
            # Compute an accessible name.
            if role_val == "textbox":
                accessible_name = (aria_label.strip() or placeholder.strip() or value.strip() or label_text.strip())
            else:
                accessible_name = aria_label.strip()
            
            candidate_locators = []
            
            # Candidate #1: use get_by_label.
            if accessible_name:
                candidate_locators.append({
                    "locatorType": "get_by_label",
                    "arguments": {"text": accessible_name, "exact": True}
                })
            # Candidate #2: use get_by_title.
            if title_attr.strip():
                candidate_locators.append({
                    "locatorType": "get_by_title",
                    "arguments": {"text": title_attr.strip(), "exact": True}
                })
            # Candidate #3: use get_by_role.
            if role_val in ["button", "link", "textbox", "combobox", "label", "generic interactive"]:
                const_name = accessible_name if accessible_name else inner_text.strip()
                if const_name:
                    candidate_locators.append({
                        "locatorType": "get_by_role",
                        "arguments": {"role": role_val, "name": const_name, "exact": True}
                    })
            # Candidate #4: use get_by_text.
            let_text = computed_text.strip() if computed_text.strip() else inner_text.strip()
            if let_text:
                candidate_locators.append({
                    "locatorType": "get_by_text",
                    "arguments": {"text": let_text, "exact": True}
                })
            
            # Deduplicate locator candidates using a generated key.
            for candidate in candidate_locators:
                if candidate["locatorType"] in ["get_by_label", "get_by_title", "get_by_text"]:
                    text_arg = candidate["arguments"].get("text", "").strip()
                    if not text_arg:
                        continue
                    key = f"{candidate['locatorType']}:{text_arg}:exact={candidate['arguments'].get('exact', False)}"
                elif candidate["locatorType"] == "get_by_role":
                    role_arg = candidate["arguments"].get("role", "").strip()
                    name_arg = candidate["arguments"].get("name", "").strip()
                    if not role_arg or not name_arg:
                        continue
                    key = f"get_by_role:{role_arg}:{name_arg}:exact={candidate['arguments'].get('exact', False)}"
                else:
                    continue
                if key in seen:
                    continue
                seen.add(key)
                if candidate["locatorType"] == "get_by_role":
                    final_name = candidate["arguments"].get("name", "").strip() or role_val
                else:
                    final_name = candidate["arguments"].get("text", "").strip()
                if not final_name:
                    continue
                actions = ["click", "fill"] if role_val == "textbox" else ["click"]
                entry = {
                    "role": role_val,
                    "name": final_name,
                    "locator": candidate,
                    "actionTypes": actions
                }
                if role_val == "link" and href.strip():
                    entry["url"] = href.strip()
                results.append(entry)
        
        return results

def retrieve_from_service_with_playwright(service, url, user, pwd, otp, debug):
    """Retrieve file from service - main function - Playwright variant    """

    bcs = ServiceObj(service=service, usr=user, pwd=pwd, otp=otp, dbg=debug, dld=DOWNLOAD_DIR)
    if not os.path.exists(bcs.dld):
        os.makedirs(bcs.dld)
    
    on_debug_start_keyboard_listener(bcs)
    try:
        sname = service.lower().replace(" ", "_")
        bcs.yml = CheckRecipe(os.path.join(RECIPES_PLAYWRIGHT_DIR,f"{RECIPES_PLAYWRIGHT_PREFIX}{sname}.yaml"),
            RECIPES_PLAYWRIGHT_SCHEMA_FILE)
        
        if bcs.yml == None: raise Exception(f"Recipe {sname} not found.")
        file_downloaded = perform_actions(bcs)
        if file_downloaded:
            logger.info(f"Service {service} for {bcs.usr} finished with downloaded file(s) {file_downloaded}.")
        else:
            logger.warning(f"Service {service} for {bcs.usr} finished without a file downloaded.")
        on_debug_stop_keyboard_listener(bcs)
        return True
    except Exception as e:
        logger.exception(f"EXCEPTION in {inspect.currentframe().f_code.co_name}(): {e}")
        logger.error(f"Service {service} for {bcs.usr} not successfully finished.")
        on_debug_stop_keyboard_listener(bcs)
        return False

def perform_actions(bcs):
    """Perform actions from YAML recipe on web elements - helper function for dispatching actions"""
    
    files_downloaded = []

    try:
        with sync_playwright() as p:
            bcs.drv = InitBrowser(p, bcs)
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

                    # process all steps in the service
                    steps = service.get('steps', [])
                    for step in sorted(steps, key=lambda x: x.get('step', 0)):  # Sort by step number

                        step_state = process_step(bcs, step)
                        bcs.db.insert_page_status(bcs.run_table, step_state)

                        # Check if the previous step expects a download
                        if check_parameter_in_json(step_state.locator_action, {"action": "expect_download"}):
                            result_value = "success"
                            download_info = None
                            download = None
                            try:
                                with bcs.page.expect_download() as di:
                                    download_info = di
                                    for nested_step in sorted(step["steps"], key=lambda x: x.get("step", 0)):
                                        step_state = process_step(bcs, nested_step)
                                        bcs.db.insert_page_status(bcs.run_table, step_state)
                                download = download_info.value
                                filepath = os.path.join(DOWNLOAD_DIR, str(download_info.value.suggested_filename))
                                download.save_as(filepath)
                            except Exception as e:
                                    result_value = f"failure: download error {e}"
                            finally:
                                if download:
                                    files_downloaded.append({
                                        "url": str(download.url),
                                        "suggested_filename": str(download.suggested_filename),
                                        "result": result_value})

                    # All steps processed, finalize the service run
                    bcs.db.finalize_service_run(
                        service_name=service_name,
                        run_table=bcs.run_table,
                        download_info = json.dumps(files_downloaded) if files_downloaded else {},
                        result = "failure" if not files_downloaded or not all(entry["result"] == "success" for entry in files_downloaded) else "success"
                    )
                    # Close the database connection
                    bcs.db.close_connection()

            # Close the page after processing all steps
            bcs.page.close()
            bcs.drv.close()

    except Exception as e:
        logger.exception(f"EXCEPTION in {inspect.currentframe().f_code.co_name}(): {e}")
    finally:
        return files_downloaded

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

    for method_entry in step["methods"]:
        method_name = method_entry.get("method")
        arguments = method_entry.get("arguments", [])
        processed_args = [process_argument(arg, bcs) for arg in arguments]

        if not method_name:
            step_results.setdefault("error", []).append(f"method: {method_name}, message: Method entry missing 'method' key: {method_entry}")
            continue # Skip to the next method entry.

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
                step_results.setdefault("error", []).append({"method": method_name, "message": str(e)})
            finally:
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
