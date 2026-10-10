# -*- coding: utf-8 -*-
"""Task runner: executes one task run as a sync Playwright step loop.

M1 item 3a: the standalone task executor. ``run_task(task_id, debug)`` loads
a Task from the DB, preflights the vault with the same semantics as the
production batch entry point (``BillCollector.py``: pinned local API URL,
status must be ``unlocked``), fetches the task's portal credentials, runs the
task's recipe with a persistent per-task browser profile, and records the
Run, PageStatus and Download rows.

Deliberate chunk boundaries (later milestone chunks):
- No pause subsystem yet (C5): a non-graceful step that still fails after
  ``MAX_STEP_ATTEMPTS`` attempts aborts the run with result=failure.
  Graceful steps are single-attempt (one recorded failure, run continues).
- No display management yet (C6): the browser is headful and needs DISPLAY
  from the environment (validation runs under ``xvfb-run -a``).
"""

import json
import logging
import sys

from helpers import CheckRecipe, ServiceObj, VARIABLE_MAP
from playwright.sync_api import sync_playwright

from . import config, downloads
from .db import Database, now
from .pagestate import PageState
from .vault import (
    VAULT_MAX_ATTEMPTS,
    VAULT_RETRY_BACKOFF,
    VaultAPIError,
    bitwarden_api_check_status,
    fetch_credentials,
    get_json_property_value,
    get_totp,
)
from vault_transport import VaultTransportError, pinned_api_url

logger = logging.getLogger("billcollector.runner")

# Attempt budget of one non-graceful step: the full method chain re-executes
# up to this many times before the run aborts (result=failure). Graceful
# steps are single-attempt (retry non-graceful steps only).
MAX_STEP_ATTEMPTS = 3


class StepAbortError(Exception):
    """A non-graceful step (or download) failed: abort the remaining steps of
    the run. Carries the PageState of the failing step so it can still be
    recorded in the DB."""

    def __init__(self, message, page_state=None):
        super().__init__(message)
        self.page_state = page_state


def step_attempts(graceful: bool) -> int:
    """Attempt budget of one step: graceful steps are single-attempt,
    non-graceful steps re-execute the full method chain up to 3 times."""
    return 1 if graceful else MAX_STEP_ATTEMPTS


def run_result(aborted: bool, files_downloaded: list) -> str:
    """Terminal Run.result of a finished run.

    Mirrors the legacy success contract: success requires a completed run
    (no abort) with at least one successfully downloaded file."""
    if aborted:
        return "failure"
    if not files_downloaded:
        return "failure"
    if not all(entry["result"] == "success" for entry in files_downloaded):
        return "failure"
    return "success"


def _fresh_otp(bcs):
    """{{OTP}} resolution: re-fetch the item's current TOTP from the vault.

    TOTP codes are only accepted for the current +/-1 time window; a code
    fetched at run start can go stale before the recipe submits it (a
    graceful step failing up front burns its 30 s actionability timeout and
    pushes the OTP submission past the code's validity). The placeholder
    therefore resolves a fresh code at substitution time. Falls back to the
    run-start credential when the item has no TOTP or the fetch fails.
    """
    try:
        totp_item = get_totp(f"{bcs.api_url}/object/totp/{bcs.vault_item_name}")
    except VaultAPIError as e:
        logger.warning(f"OTP re-fetch failed ({e}); using run-start credential")
        return bcs.otp_fallback
    if totp_item is None:
        return bcs.otp_fallback
    value = get_json_property_value(totp_item, "data_data")
    return value if value is not None else bcs.otp_fallback


# The runner's variable map: like helpers.VARIABLE_MAP, but {{OTP}} resolves
# a fresh TOTP at substitution time (see _fresh_otp).
VARIABLE_MAP = {**VARIABLE_MAP, "{{OTP}}": _fresh_otp}


class _RunContext:
    """Mutable state shared by the step loop of one run."""

    def __init__(self, task, run_id, db, debug, credentials, api_url):
        self.task = task
        self.run_id = run_id
        self.db = db
        self.debug = debug
        self.eof_noticed = False
        self.files_downloaded = []
        self.context = None
        self.page = None
        self.bcs = ServiceObj(
            service=task["service"],
            usr=credentials["user"],
            pwd=credentials["password"],
            otp=credentials["otp"],
            dbg=debug,
            dld=str(downloads.download_dir(db)),
        )
        # Extra attributes used by _fresh_otp at substitution time.
        self.bcs.api_url = api_url
        self.bcs.vault_item_name = f"{task['service']} {task['user']}".strip()
        self.bcs.otp_fallback = credentials["otp"]


def _ensure_logging():
    """Emit logs on plain stdout unless the caller already configured logging
    (the CLI does; the C7 orchestrator will capture this process' stdout)."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(name)s %(levelname)s %(message)s")


def _vault_preflight(task):
    """Production vault preflight for one task: pinned local API URL, an
    ``unlocked`` status, and the task's credentials.

    Returns the credentials dict; raises VaultAPIError/VaultTransportError
    on any failure (the caller maps that to a failed run)."""
    api_url = config.env("BW_API_URL")
    if not api_url:
        raise VaultTransportError("BW_API_URL is not set")
    pinned_api_url(api_url, VAULT_MAX_ATTEMPTS, VAULT_RETRY_BACKOFF)
    ret, status = bitwarden_api_check_status(api_url)
    if not ret or status != "unlocked":
        raise VaultAPIError(
            f"vault status: {'locked' if ret else 'check failed (success is not true)'}")
    return fetch_credentials(api_url, task["service"], task["user"])


def _ensure_pdf_preference(profile_dir):
    """Create the profile's Default/Preferences with the PDF-external
    preference when missing - the legacy ``init_browser_profile`` preference
    write without the deletion (the per-task profile is persistent, never
    wiped, and cookies survive between runs)."""
    default_dir = profile_dir / "Default"
    default_dir.mkdir(parents=True, exist_ok=True)
    prefs = default_dir / "Preferences"
    if not prefs.exists():
        content = {"plugins": {"always_open_pdf_externally": True}}
        prefs.write_text(json.dumps(content, indent=2), encoding="utf-8")


def _launch_browser(ctx, p):
    """Launch the persistent per-task browser context (headful; DISPLAY must
    come from the environment) and open the run's page."""
    profile_dir = config.profile_dir_for(ctx.task["service"], ctx.task["user"])
    _ensure_pdf_preference(profile_dir)
    ctx.context = p.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=False,
        args=config.chromium_args(),
    )
    ctx.page = ctx.context.new_page()
    ctx.bcs.page = ctx.page  # the step loop dispatches methods on bcs.page


def _process_step(bcs, step):
    """Process a step by executing its method chain (legacy ``process_step``).

    Returns the step's PageState. A graceful step records its failure on the
    PageState and returns; a non-graceful step raises StepAbortError."""

    def process_argument(arg, bcs):
        """Processes a single argument:
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
            else:  # all other methods are considered locators
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
            break  # Stop the method chain (graceful failure).

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
                break  # Stop the method chain (graceful failure).
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


def _debug_wait(ctx, step):
    """Debug pause before a step: wait on stdin with the step as prompt.
    A closed stdin (EOF) logs once and continues without pausing."""
    if not ctx.debug:
        return
    prompt = (f"Step {step.get('step', 0)}: {step.get('description', '')} "
              "[press Enter to continue]")
    try:
        input(prompt)
    except EOFError:
        if not ctx.eof_noticed:
            logger.info("Debug wait: stdin closed; continuing without pausing.")
            ctx.eof_noticed = True


def _record_step(ctx, state, step, parent_step=None):
    """Record the one PageStatus row of a step (its final outcome) plus a step
    screenshot; a screenshot failure never aborts the run.

    Top-level steps take ``step_{n}.png``; nested steps (inside an
    expect_download window) take ``step_{parent}_{n}.png`` so two nested
    steps numbered 1 never overwrite each other or a top-level screenshot."""
    screenshot_path = None
    try:
        target_dir = config.RUN_DIR / str(ctx.run_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        if parent_step is not None:
            name = f"step_{parent_step}_{step.get('step', 0)}"
        else:
            name = f"step_{step.get('step', 0)}"
        path = target_dir / f"{name}.png"
        ctx.page.screenshot(path=str(path))
        screenshot_path = str(path)
    except Exception as e:
        logger.warning(f"Step {step.get('step', 0)} screenshot failed (run continues): {e}")
    ctx.db.insert_page_status(
        ctx.run_id,
        state.step_number,
        locator_action=state.locator_action,
        interactive_elements=state.interactive_elements,
        screenshot_path=screenshot_path,
        error=state.error_status,
    )


def _execute_step(ctx, step, parent_step=None):
    """Execute one step (top-level or nested) with its attempt budget.

    Records exactly one PageStatus row for the step (its final outcome).
    Raises StepAbortError when a non-graceful step exhausts its attempts."""
    graceful = bool(step.get("graceful", False))
    attempts = step_attempts(graceful)
    step_number = step.get("step", 0)

    _debug_wait(ctx, step)

    state = None
    for attempt in range(1, attempts + 1):
        try:
            state = _process_step(ctx.bcs, step)
        except StepAbortError as e:
            if attempt < attempts:
                logger.warning(f"Step {step_number} failed "
                               f"(attempt {attempt}/{attempts}, retrying): {e}")
                continue
            if e.page_state is not None:
                _record_step(ctx, e.page_state, step, parent_step)
            raise
        # Returned: a clean success or a recorded graceful failure. Graceful
        # steps are single-attempt - never retried.
        break

    if state is not None:
        _record_step(ctx, state, step, parent_step)
    return state


def _handle_download(ctx, step):
    """Nested-step expect_download handling (legacy semantics) with download
    tracking: every downloaded file goes through downloads.track_download
    (sha256, per-task dedup, consumer hook)."""
    step_number = step.get("step", 0)
    graceful = bool(step.get("graceful", False))
    result_value = "success"
    record = None
    try:
        with ctx.page.expect_download() as download_info:
            for nested_step in sorted(step.get("steps", []), key=lambda x: x.get("step", 0)):
                _execute_step(ctx, nested_step, parent_step=step_number)
        download = download_info.value
        record = downloads.track_download(download, ctx.run_id, ctx.task, ctx.db)
    except StepAbortError:
        raise
    except Exception as e:
        result_value = f"failure: download error {e}"
    if record is None and result_value != "success":
        if graceful:
            logger.warning(f"Step {step_number} failed to download "
                           f"(graceful, run continues): {result_value}")
        else:
            raise StepAbortError(f"Step {step_number} failed to download: {result_value}")
    if record is not None:
        ctx.files_downloaded.append({
            "url": record["url"],
            "suggested_filename": record["filename"],
            "result": result_value,
        })


def _run_recipe(ctx, recipe):
    """Run the recipe's step loop in a headful persistent browser context.

    Returns (files_downloaded, aborted). Every started run leaves the browser
    closed, even on abort."""
    files_downloaded = []
    aborted = False
    with sync_playwright() as p:
        try:
            _launch_browser(ctx, p)
        except Exception as e:
            logger.exception(f"Browser launch failed: {e}")
            return files_downloaded, True
        try:
            services = recipe.get("services", [])
            for service in services:
                service_name = service.get("serviceName")
                logger.info(f"Processing Service: {service_name} for {ctx.bcs.usr}.")
                for step in sorted(service.get("steps", []), key=lambda x: x.get("step", 0)):
                    step_state = _execute_step(ctx, step)
                    # Check if the step expects a download
                    if check_parameter_in_json(step_state.locator_action, {"action": "expect_download"}):
                        _handle_download(ctx, step)
        except StepAbortError as e:
            aborted = True
            logger.error(f"Run aborted: {e}")
        except Exception:
            aborted = True
            logger.exception("EXCEPTION in _run_recipe(): run aborted")
        finally:
            for closer in (ctx.page.close, ctx.context.close):
                try:
                    closer()
                except Exception:
                    pass
    files_downloaded = ctx.files_downloaded
    return files_downloaded, aborted


def run_task(task_id: int, debug: bool = False) -> int:
    """Execute one task run (sync Playwright step loop).

    Returns the process exit code: 0 on success, 1 on a run failure
    (vault preflight, recipe error, or step failure)."""
    config.load_env()
    _ensure_logging()

    db = Database()
    try:
        task = db.get_task(task_id)
        if task is None:
            print(f"runner: task {task_id} not found", file=sys.stderr)
            return 1

        recipe_file = task["recipe_file"] or str(config.recipe_path_for(task["service"]))
        recipe = CheckRecipe(recipe_file, str(config.RECIPE_SCHEMA))
        if recipe is None:
            print(f"runner: recipe {recipe_file} not found or invalid", file=sys.stderr)
            return 1

        run_id = db.create_run(task_id)
        result = "failure"
        files = []
        api_url = config.env("BW_API_URL")
        try:
            credentials = _vault_preflight(task)
            ctx = _RunContext(task, run_id, db, debug, credentials, api_url)
            files, aborted = _run_recipe(ctx, recipe)
            result = run_result(aborted, files)
        except (VaultAPIError, VaultTransportError) as e:
            # A vault-preflight failure: one clear stderr line, distinct from
            # a step failure (which the step loop logs on stdout).
            print(f"runner: vault preflight failed for task {task_id}: {e}", file=sys.stderr)
        except Exception:
            logger.exception(f"Task {task_id} run {run_id} aborted by an unexpected error")
        finally:
            # The run row always ends with a terminal result, even when the
            # vault preflight or an unexpected error stopped the run before
            # the step loop ran.
            db.update_run(run_id, result=result, ended_at=now())
        if result == "success":
            logger.info(f"Task {task_id} run {run_id} finished with downloaded file(s) {files}.")
            return 0
        logger.error(f"Task {task_id} run {run_id} failed (result={result}, downloads={files}).")
        return 1
    finally:
        db.close()
