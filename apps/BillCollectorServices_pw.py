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
            interactive_elements JSON,
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
            locator_args, interactive_elements, result
        ) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            page_state.service_name,
            page_state.step_number,
            page_state.action,
            json.dumps(page_state.action_args),
            page_state.locator,
            json.dumps(page_state.locator_args),
            json.dumps(page_state.interactive_elements),  # Stores interactive elements
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
#        self.aria_snapshot = page.accessibility.snapshot()
#        self.dom_status = page.content()
        self.interactive_elements = self.set_interactive_elements(page)
        self.error_status = None
        self.download_info = None

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
                locator_object = locator_object.first if hasattr(locator_object, 'first') else locator_object  # Handle first() if available
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
