import os
import re
import inspect
import sqlite3
import json

from datetime import datetime

from playwright.sync_api import Playwright, sync_playwright, Route, Request, Page

#from apps.helpers.BillCollectorRecipes import CheckRecipe
from helpers import *

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
        self.interactive_elements = None #self.set_interactive_elements(page)
        self.error_status = None
        self.download_info = None
        self.locator_action = None

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
        # Wait for initial page load and an extra delay for dynamic updates.
        page.wait_for_load_state("load")
        page.wait_for_timeout(500)
        
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
        # Run the observer (we ignore its return value).
        page.evaluate(js_observer)
        
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
        elements_data = page.evaluate(js_collect)
        
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

    
    def set_error(self, error_message: str):
        """Sets an error status"""
        self.error_status = error_message

    def set_download_info(self, download_info):
        """Sets the download information"""
        self.download_info = download_info

    def set_locator_action(self, locator_action):
        """Sets the locator action"""
        self.locator_action = locator_action

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
        bcs.yml = CheckRecipe(os.path.join(RECIPES_PLAYWRIGHT_DIR,f"{RECIPES_PLAYWRIGHT_PREFIX}{sname}.yaml"),
            RECIPES_PLAYWRIGHT_SCHEMA_FILE)
        
        if bcs.yml == None: raise Exception(f"Recipe {sname} not found.")
        file_downloaded = perform_actions(bcs)
        if file_downloaded: print(f"Service {service} for {bcs.usr} finished with downloaded file(s) {file_downloaded}.")
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
                    bcs.db = DatabaseManager(DB_FILE)
                    bcs.run_table = bcs.db.create_service_run_table(service_name)

                    steps = service.get('steps', [])
                    for step in sorted(steps, key=lambda x: x.get('step', 0)):  # Sort by step number
                        step_state = process_step(bcs, step)
                      
                        if not step_state.error_status and step_state.download_info != None:
                            exception_occurred = None
                            try:
                                step_state.download_info.value.save_as(os.path.join(
                                                                        DOWNLOAD_DIR, 
                                                                        step_state.download_info.value.suggested_filename))
                            except Exception as e:
                                exception_occurred = f"file failure: {e}"
                                print(f" Error saving file: {exception_occurred}")  # This is needed for debugging!
                            finally:
                                if step_state.download_info.value.failure():
                                    step_state.error_status = f"pw failure: {str(step_state.download_info.value.failure())}"
                                    if exception_occurred:
                                        step_state.error_status += f" | {str(exception_occurred)}"
                                elif exception_occurred:
                                    step_state.error_status = str(exception_occurred)
                                else:
                                    result_value = "success"
                                    file_downloaded.append({
                                        "url": str(step_state.download_info.value.url),
                                        "suggested_filename": str(step_state.download_info.value.suggested_filename),
                                        "result": result_value})
                        # Save the page state to the database
                        bcs.db.insert_page_status(bcs.run_table, step_state)

                    bcs.db.finalize_service_run(
                        service_name=service_name,
                        run_table=bcs.run_table,
                        download_info = json.dumps(file_downloaded) if file_downloaded else {},
                        result = "failure" if not file_downloaded or not all(entry["result"] == "success" for entry in file_downloaded) else "success"
                    )
                    # Close the database connection
                    bcs.db.close_connection()

            # Close the page after processing all steps
            bcs.page.close()
            bcs.drv.close()

    except Exception as e:
        print(f"EXCEPTION in {inspect.currentframe().f_code.co_name}(): {e}")
    else:
        return file_downloaded


def process_argument(arg, bcs):
    """
    Processes a single argument:
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

def process_step(bcs, step):
    """
    Processes a step by executing a chain of methods (starting on bcs.page) and simultaneously 
    builds a mapping of the method chain for later comparison.
    
    Features:
      • Uses process_argument() to handle placeholder replacement.
      • Calls methods with keyword arguments when all processed args are dictionaries; otherwise, positional.
      • Chains the result to update the "current" context for subsequent calls.
      • Special-cases "expect_download" using a context manager.
      • Builds a chain mapping where each mapping entry (if applicable) includes a locator part (with its type and arguments)
        and an action part (with its action type(s) and arguments).
    
    The final result is a dictionary that includes both an "executions" log and a "chainMapping".
    
    :param bcs: A service object (with attributes like page, usr, pwd, otp, etc.).
    :param step: A dictionary representing a step (must include a "methods" key; nested steps may be present).
    :return: A dictionary summarizing execution status and the chain mapping.
    """
    if not isinstance(step, dict) or "methods" not in step:
        raise ValueError("Invalid step format: Expected a dictionary with a 'methods' key.")

    step_number = step.get("step", 0)
    print(f"Processing Step {step_number}")
    step_results = {}
    chain_mapping = []  # This will accumulate our mapping entries.
    previous_result = bcs.page  # Starting object.
    current_mapping_entry = None  # Holds the most recent locator mapping to attach actions to.

    # Define sets for locator and action methods.
    LOCATOR_METHODS = {"locator", "get_by_role", "get_by_text", "get_by_label", "get_by_title"}
    ACTION_METHODS = {"click", "fill", "goto"}

    page_state = PageState(bcs.service, step_number, bcs.page)
    
    for method_entry in step["methods"]:
        method_name = method_entry.get("method")
        arguments = method_entry.get("arguments", [])
        processed_args = [process_argument(arg, bcs) for arg in arguments]

        try:
            if not method_name:
                raise ValueError(f"Method entry missing 'method' key: {method_entry}")
        except Exception as e:
            step_results.setdefault("error", []).append({"method": method_name, "message": str(e)})
            continue # Skip to the next method entry.

        # Special handling for "expect_download".
        if method_name == "expect_download":
            mapping_entry = {"actionTypes": ["expect_download"]}
            try:
                with previous_result.expect_download() as download_info:
                    previous_result = download_info
                    # Process any nested steps within the download context.
                    if "steps" in step and step["steps"]:
                        for nested_step in sorted(step["steps"], key=lambda x: x.get("step", 0)):
                            page_state = process_step(bcs, nested_step)
                            bcs.db.insert_page_status(bcs.run_table, page_state)
                        page_state.set_download_info(download_info)
                    else:
                        raise ValueError("No nested steps provided for 'expect_download'.")
            except Exception as e:
                step_results.setdefault("error", []).append({"method": method_name, "message": str(e)})
#            chain_mapping.append(mapping_entry)
#            current_mapping_entry = None
            continue  # Skip normal processing for this method.

        # --- Build the chain mapping ---
        #
        # TODO: HIDE CREDENTIALS!!!!!!!!!!!!!!
        #
        if method_name in LOCATOR_METHODS:
            # It's a locator method; create a new mapping entry.
            mapping_entry = {}
            if processed_args and all(isinstance(arg, dict) for arg in processed_args):
                merged_args = {}
                for d in processed_args:
                    merged_args.update(d)
                mapping_entry["locator"] = {"locatorType": method_name, "arguments": merged_args}
                if "role" in merged_args:
                    mapping_entry["role"] = merged_args["role"]
                if "name" in merged_args:
                    mapping_entry["name"] = merged_args["name"]
            else:
                mapping_entry["locator"] = {"locatorType": method_name, "arguments": processed_args}
            current_mapping_entry = mapping_entry  # Set current mapping entry to attach following action.
            chain_mapping.append(mapping_entry)
        elif method_name in ACTION_METHODS:
            # It's an action method; update the most recent locator mapping entry.
            if current_mapping_entry is None:
                current_mapping_entry = {}
                chain_mapping.append(current_mapping_entry)
            if "actionTypes" not in current_mapping_entry:
                current_mapping_entry["actionTypes"] = []
            current_mapping_entry["actionTypes"].append(method_name)
            if processed_args:
                if all(isinstance(arg, dict) for arg in processed_args):
                    action_args = {}
                    for d in processed_args:
                        action_args.update(d)
                    current_mapping_entry["actionArguments"] = action_args
                else:
                    current_mapping_entry["actionArguments"] = processed_args
        else:
            # For any other (non-locator, non-action) method, add a separate mapping entry.
            mapping_entry = {method_name: {"arguments": processed_args}}
            chain_mapping.append(mapping_entry)
        # --- End chain mapping build ---

        # Retrieve the attribute (method or property) from the current context.
        method_executor = getattr(previous_result, method_name, None)
        try:
            if method_executor is None:
                raise AttributeError(f"Method '{method_name}' not found on {type(previous_result).__name__}.")
            if callable(method_executor):
                if processed_args and all(isinstance(arg, dict) for arg in processed_args):
                    kwargs = {}
                    for d in processed_args:
                        kwargs.update(d)
                    result = method_executor(**kwargs)
                else:
                    result = method_executor(*processed_args)
                previous_result = result if result is not None else previous_result
            else:
                if processed_args:
                    raise TypeError(f"Attribute '{method_name}' is not callable but arguments were provided: {processed_args}")
                previous_result = method_executor
        except Exception as e:
            step_results.setdefault("error", []).append({"method": method_name, "message": str(e)})
            continue

    page_state.set_locator_action(chain_mapping)
    page_state.set_error(step_results)
    return page_state

