# -*- coding: utf-8 -*-
"""Page state capture and interactive-element scan (shared by the daemon
runner and the legacy batch path).

Extracted from ``BillCollectorServices_pw.py`` (M1): the scan logic is
reused unchanged, with one Wave 1 addition - every element carries a
bounding box (``rect`` from ``getBoundingClientRect``), which the Copilot
overlay and the machine-readable pause context need for positioning.

This module intentionally imports nothing from Playwright: the ``page``
argument is any object with a sync ``evaluate`` method, so it stays usable
from the lightweight runner bootstrap.
"""

import logging
import time
from datetime import datetime

from .redaction import sanitize_url

logger = logging.getLogger(__name__)


class PageState:
    """Represents the state of a page at a given time."""

    def __init__(self,
                 service_name: str,
                 step_number: int,
                 page,
                 ):

        self.service_name = service_name
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.step_number = step_number
        #        self.aria_snapshot = page.accessibility.snapshot()
        #        self.dom_status = page.content()
        self.interactive_elements = self.set_interactive_elements(page)
        self.error_status = None
        self.locator_action = None
        self.screenshot_path = None

    def set_error(self, error_message):
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
        - rect: The element's bounding box {"x", "y", "w", "h"} (page pixels,
          origin at the top-left of the viewport) - used to position the
          Copilot overlay and for the pause context.
        - actionTypes: "textbox" elements get ["click", "fill"]; all others get ["click"].
        - id: (optional) The element's static markup id, when present. Metadata
          only: no locator candidate is generated from it.
        - For a link (role "link"), if available, an extra "url" key holds the element's href.

        This function is generic and does not depend on any fixed element. It uses a broad DOM traversal (querySelectorAll("*"))
        and filters out only those elements that are visible and "likely interactive" (based on their tag, onclick attribute, or contenteditable).
        It computes a text value from each element's innerText and its ::before and ::after pseudo-elements.
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
        if not safe_evaluate(page, js_observer):
            return None

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
                const rect = el.getBoundingClientRect();
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
                    inputType: el.tagName.toLowerCase() === "input" ?
                        (el.getAttribute("type") || "text").toLowerCase() : "",
                    value: el.tagName.toLowerCase() === "input" &&
                        ["submit", "button", "reset"].includes(
                            (el.getAttribute("type") || "text").toLowerCase()) ?
                        (el.value || "").toString().trim() : "",
                    labelText: lbl ? lbl.innerText.trim() : "",
                    rect: {x: rect.x, y: rect.y, w: rect.width, h: rect.height}
                };
            });
        }'''
        # Run the observer safely to ensure the DOM is stable.
        elements_data = safe_evaluate(page, js_collect)
        if not elements_data:
            return None

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
            onclick = data["onclick"]
            href = data["href"]
            input_type = data.get("inputType", "")
            value = data.get("value", "")
            label_text = data["labelText"]
            rect = data.get("rect") or {"x": 0, "y": 0, "w": 0, "h": 0}

            if tag == "input" and input_type in ["submit", "button", "reset"]:
                role_val = "button"
            elif tag in ["input", "textarea"]:
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
                accessible_name = (aria_label.strip() or placeholder.strip() or label_text.strip())
            elif tag == "input" and input_type in ["submit", "button", "reset"]:
                accessible_name = aria_label.strip() or value.strip()
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
                if const_name or role_val == "textbox":
                    role_arguments = {"role": role_val}
                    if const_name:
                        role_arguments.update({"name": const_name, "exact": True})
                    candidate_locators.append({
                        "locatorType": "get_by_role",
                        "arguments": role_arguments
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
                    if not role_arg or (not name_arg and role_arg != "textbox"):
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
                    "rect": rect,
                    "actionTypes": actions
                }
                id_attr = data.get("id", "")
                if id_attr:
                    entry["id"] = id_attr
                if role_val == "link" and href.strip():
                    entry["url"] = sanitize_url(href.strip())
                results.append(entry)

        return results
