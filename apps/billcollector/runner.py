# -*- coding: utf-8 -*-
"""Task runner: executes one task run as a sync Playwright step loop.

M1 item 3a: the standalone task executor. ``run_task(task_id, debug)`` loads
a Task from the DB, preflights the vault with the same semantics as the
production batch entry point (``BillCollector.py``: pinned local API URL,
status must be ``unlocked``), fetches the task's portal credentials, runs the
task's recipe with a persistent per-task browser profile, and records the
Run, PageStatus and Download rows.

Stuck runs pause instead of aborting (M1 chunk C5): a non-graceful step
that still fails after ``MAX_STEP_ATTEMPTS`` attempts (or a failed download)
pauses the run via :mod:`billcollector.pause` (machine-readable context,
versioned control socket, ntfy); a resume re-executes the step, a cancel ends
the run with result=cancelled, a deadline timeout with
result=needs_attention. Graceful steps are single-attempt and never pause.
A ``wait_user`` step (C5.5, decision 19) pauses before execution
(reason=wait_user) and completes on resume - it is consumed, not
re-executed; an optional ``until`` locator must be visible before the step
completes, bounded by the pause deadline (a missed deadline re-pauses with
the same prompt).

The per-run display lifecycle is runner-owned (C6): the run allocates a
display from the configured range (lockfile registry), starts the
Xvfb/x11vnc/websockify child stack, points DISPLAY at that display for the
headful browser launch, records ``Run.display`` / ``Run.novnc_port``, and
reaps the stack + releases the claim in the run teardown.

A shutdown signal (SIGTERM from the daemon, Ctrl+C on the standalone
runner; C7.5) interrupts the run gracefully: the handler raises
RunInterrupted, the teardown reaps the display stack and releases the
claim, and the run ends ``result=interrupted``.
"""

import fcntl
import json
import logging
import os
import signal
import sys
from datetime import datetime

from helpers import CheckRecipe, ServiceObj, VARIABLE_MAP
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from . import collection, config, display, downloads
from .db import Database, now
from .interrupt import RunInterrupted
from .login import is_login, login_options, settle_attempt, validate_login_recipe
from .pagestate import PageState
from .pause import pause_loop
from .redaction import failure_category, failure_record
from .variables import DateContext, expand_argument, validate_variable_recipe
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

# Collection actions have bounded side effects. They execute once per recipe
# step instead of inheriting the generic three-attempt replay loop. An
# operator-driven resume starts a new, explicit invocation after inspection.
_COLLECTION_METHODS = frozenset({"click_until_absent", "download_all"})


def _collection_methods_in(step):
    return {
        entry.get("method") for entry in step.get("methods", [])
        if isinstance(entry, dict)
        and entry.get("method") in _COLLECTION_METHODS
    }


class StepAbortError(Exception):
    """A non-graceful step (or download) failed: abort the remaining steps of
    the run. Carries the PageState of the failing step so it can still be
    recorded in the DB."""

    def __init__(self, message, page_state=None):
        super().__init__(message)
        self.page_state = page_state


class PauseOutcomeAbort(Exception):
    """A paused run was terminated by its outcome (cancel or timeout).

    Carries the terminal outcome that maps to the Run.result value
    (``cancelled`` / ``needs_attention``); the browser is closed by the
    normal run teardown."""

    def __init__(self, outcome):
        super().__init__(f"pause outcome: {outcome}")
        self.outcome = outcome


def _install_signal_handlers() -> None:
    """Turn SIGTERM/SIGINT into a graceful run interruption (C7.5).

    The daemon's shutdown (and a Ctrl+C on the standalone runner) must
    take the run's whole teardown with it - display stack reap, claim
    release, Run finalization - so the handler raises RunInterrupted in
    the main thread instead of letting the OS kill the process in place.
    A signal arriving inside a blocking Playwright call is handled as
    soon as that call returns; a daemon shutdown that outlasts the
    runner's grace period force-kills the runner's whole process group
    instead (orchestrator.shutdown, C7.5)."""

    def _handler(signum, frame):
        raise RunInterrupted(f"received signal {signum}")

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


def step_attempts(graceful: bool) -> int:
    """Attempt budget of one step: graceful steps are single-attempt,
    non-graceful steps re-execute the full method chain up to 3 times."""
    return 1 if graceful else MAX_STEP_ATTEMPTS


def run_result(aborted: bool, files_downloaded: list, pause_outcome=None) -> str:
    """Terminal Run.result of a finished run.

    A pause outcome is terminal in itself: cancel -> ``cancelled``,
    timeout -> ``needs_attention`` (decision: the operator can retry a
    timed-out run manually later). Otherwise the legacy success contract:
    success requires a completed run (no abort) with at least one
    successfully downloaded file."""
    if pause_outcome == "cancel":
        return "cancelled"
    if pause_outcome == "timeout":
        return "needs_attention"
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
        logger.warning("OTP re-fetch failed (%s); using run-start credential",
                       failure_record("get_totp", e))
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
        self.collection_filenames = set()
        self.collection_completed_keys = {}
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
        # Pause state (C5): the pause loop and the Copilot context handler
        # read these off the context.
        self.pause_count = 0
        self.last_pause_context = None
        self.last_pause_deadline = None


def _ensure_logging():
    """Emit logs on plain stdout unless the caller already configured logging
    (the CLI does; the C7 orchestrator will capture this process' stdout)."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(name)s %(levelname)s %(message)s")


def _vault_preflight(task, db):
    """Production vault preflight for one task: the effective (Settings or
    env) API URL, a pinned local target, an ``unlocked`` status, and the
    task's credentials.

    The effective (url, host) pair from ``config.vault_settings`` is
    exported into ``os.environ`` before the vault calls, so the vault
    transport's ``BW_API_HOST`` read (and any other env-only consumer in
    this process) sees the same values the preflight validated. Returns
    the credentials dict; raises VaultAPIError/VaultTransportError on any
    failure (the caller maps that to a failed run)."""
    api_url, api_host = config.vault_settings(db)
    if not api_url:
        raise VaultTransportError(
            "vault API URL is not set (Settings vault_api_url or BW_API_URL)")
    os.environ["BW_API_URL"] = api_url
    os.environ["BW_API_HOST"] = api_host
    pinned_api_url(api_url, VAULT_MAX_ATTEMPTS, VAULT_RETRY_BACKOFF)
    ret, status = bitwarden_api_check_status(api_url)
    if not ret or status != "unlocked":
        raise VaultAPIError(
            f"vault status: {'locked' if ret else 'check failed (success is not true)'}")
    return fetch_credentials(api_url, task["service"], task["user"])


def _start_display_stack(db, run_id, display_number):
    """Start the run's Xvfb/x11vnc/websockify stack (C6.2) and return its
    child Popen list (the run teardown reaps it).

    The per-run VNC auth file is created only when the ``vnc_password``
    setting is non-empty (default: empty -> localhost-only x11vnc, no
    auth). Raises DisplayError when the stack cannot start."""
    password = db.get_setting("vnc_password")
    rfb_auth = None
    if password is not None and str(password).strip():
        rfb_auth = display.rfb_auth_file_for(run_id)
        display.write_rfb_auth(rfb_auth, str(password).strip())
    return display.start_display_stack(display_number, rfb_auth_file=rfb_auth)


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


def _clear_stale_history(profile_dir):
    """Clear the previous run's browsing-history state before launch.

    Workaround for Chromium issue 556160935 ([M152 regression] browser
    process crash after setDownloadBehavior with a persistent profile that
    has download history): with DevTools/CDP attached, a persistent profile
    carrying both ``Default/History`` and the network service's
    ``Default/shared_proto_db`` crashes (SEGV/SIGTRAP) when the first
    download starts. Upstream fix CL 8378127 (DevToolsDownloadManagerDelegate
    forwards SupportsHistoryLoading) targets M154 - this wipe can be removed
    once the pinned Playwright chromium build is >= 154. Clearing the history
    side of that pair avoids it; the history data is not needed by the
    collector. Cookies, login and Preferences are untouched. No-op for fresh
    profiles."""
    default_dir = profile_dir / "Default"
    removed = []
    for name in ("History", "History-journal"):
        path = default_dir / name
        if path.exists():
            try:
                path.unlink()
                removed.append(name)
            except OSError as e:
                logger.warning(f"Could not remove {path}: {e}")
    if removed:
        logger.info(
            f"Cleared stale browsing history before launch: "
            f"{', '.join(removed)}")


def _launch_browser(ctx, p):
    """Launch the persistent per-task browser context (headful on the run's
    allocated display, C6) and open the run's page."""
    profile_dir = config.profile_dir_for(ctx.task["service"], ctx.task["user"])
    _ensure_pdf_preference(profile_dir)
    _clear_stale_history(profile_dir)
    ctx.context = p.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=False,
        args=config.chromium_args(),
    )
    ctx.page = ctx.context.new_page()
    ctx.bcs.page = ctx.page  # the step loop dispatches methods on bcs.page


def transform_step_to_json(step):
    """Transforms a step object into JSON with locators and actions.

    Module-level (used by the step loop and by the pause context, which
    needs the failing step's locator-action JSON)."""
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
        if method_name in [
            "click", "fill", "expect_download", "goto", "close",
            "content_frame", "first", "click_until_absent", "download_all",
        ]:
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


def process_argument(arg, bcs):
    """Expand original argument values; credentials remain opaque data."""
    credentials = {key[2:-2]: lambda resolver=resolver: resolver(bcs)
                   for key, resolver in VARIABLE_MAP.items()}
    return expand_argument(arg, credentials, getattr(bcs, "date_context", None))


def _process_step(bcs, step, collection_actions=None):
    """Process a step by executing its method chain (legacy ``process_step``).

    Returns the step's PageState. A graceful step records its failure on the
    PageState and returns; a non-graceful step raises StepAbortError."""

    if not isinstance(step, dict) or "methods" not in step:
        raise ValueError("Invalid step format: Expected a dictionary with a 'methods' key.")

    step_number = step.get("step", 0)
    logger.info(f"Processing Step {step_number}")
    step_results = {}
    previous_result = bcs.page  # Starting object.

    page_state = PageState(bcs.service, step_number, bcs.page)
    page_state.set_locator_action(transform_step_to_json(step))

    # A step is "graceful" when its failure must not abort the run:
    # the error is recorded (log + DB) and the run continues with the next step.
    graceful = bool(step.get("graceful", False))
    methods = step["methods"]
    try:
        collection.validate_collection_chain(methods)
    except collection.CollectionError as e:
        page_state.set_error({"error": [str(e)]})
        raise StepAbortError(f"Step {step_number} failed: {e}", page_state)

    if graceful and any(
        isinstance(entry, dict)
        and entry.get("method") in _COLLECTION_METHODS
        for entry in methods
    ):
        message = "bounded collection actions cannot be graceful"
        page_state.set_error({"error": [message]})
        raise StepAbortError(f"Step {step_number} failed: {message}", page_state)

    def fail_step(error_entry):
        """Record a step failure; continue when graceful, otherwise abort the run."""
        step_results.setdefault("error", []).append(error_entry)
        page_state.set_error(step_results)
        if graceful:
            logger.warning(f"Step {step_number} failed (graceful, run continues): {error_entry}")
        else:
            raise StepAbortError(f"Step {step_number} failed: {error_entry}", page_state)

    for method_index, method_entry in enumerate(methods):
        method_name = method_entry.get("method")
        arguments = method_entry.get("arguments", [])

        if not method_name:
            fail_step(failure_record(None, category="other"))
            break  # Stop the method chain (graceful failure).

        # Special handling for "expect_download".
        if method_name == "expect_download":
            if "steps" in step and step["steps"]:
                page_state.set_error(step_results)
            else:
                page_state.set_error({
                    "error": [failure_record("expect_download", category="download")]
                })
            break
        elif method_name in _COLLECTION_METHODS:
            try:
                collection.validate_terminal_action(
                    methods, method_index, method_name
                )
                processed_args = [process_argument(arg, bcs) for arg in arguments]
                if previous_result is bcs.page:
                    raise ValueError(
                        f"{method_name} requires a locator prefix"
                    )
                if (len(processed_args) != 1
                        or not isinstance(processed_args[0], dict)):
                    raise ValueError(
                        f"{method_name} requires one options object"
                    )
                if collection_actions is None:
                    raise RuntimeError(
                        f"{method_name} is unavailable in this runner"
                    )
                collection_actions[method_name](
                    previous_result, processed_args[0]
                )
            except RunInterrupted:
                raise
            except Exception as e:
                fail_step({"method": method_name, "message": str(e)})
            else:
                page_state.set_error(step_results)
            break
        # Standard handling of methods
        else:
            try:
                processed_args = [process_argument(arg, bcs) for arg in arguments]
                method_executor = getattr(previous_result, method_name, None)
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
            except RunInterrupted:
                raise  # a shutdown signal is not a step failure to retry
            except Exception as e:
                fail_step(failure_record(method_name, e))
                break  # Stop the method chain (graceful failure).
            else:
                page_state.set_error(step_results)

    return page_state


def _collection_actions(ctx, step=None):
    """Runner adapters for the shared bounded collection actions."""

    collection_filenames = getattr(ctx, "collection_filenames", None)
    if collection_filenames is None:
        collection_filenames = set()
        ctx.collection_filenames = collection_filenames
    collection_filenames.update(
        entry["suggested_filename"]
        for entry in getattr(ctx, "files_downloaded", ())
        if entry.get("result") == "success"
    )
    completed_by_step = getattr(ctx, "collection_completed_keys", None)
    if completed_by_step is None:
        completed_by_step = {}
        ctx.collection_completed_keys = completed_by_step
    completed_keys = completed_by_step.setdefault(id(step), set())

    def paginate(locator, options):
        return collection.click_until_absent(ctx.page, locator, options)

    def save_download(download):
        filename = str(download.suggested_filename)
        if filename in collection_filenames:
            raise collection.CollectionError(
                "collection produced a duplicate suggested filename"
            )
        record = downloads.track_download(
            download, ctx.run_id, ctx.task, ctx.db
        )
        collection_filenames.add(filename)
        ctx.files_downloaded.append({
            "url": record["url"],
            "suggested_filename": record["filename"],
            "result": "success",
        })
        return record

    def download(locator, options):
        return collection.download_all(
            ctx.page,
            ctx.context,
            locator,
            save_download,
            options,
            completed_keys=completed_keys,
        )

    return {
        "click_until_absent": paginate,
        "download_all": download,
    }


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
    except RunInterrupted:
        raise  # a shutdown signal is not a screenshot failure to degrade around
    except Exception as e:
        logger.warning("Step %s screenshot failed (run continues): %s",
                       step.get("step", 0), failure_record("screenshot", e))
    ctx.db.insert_page_status(
        ctx.run_id,
        state.step_number,
        locator_action=state.locator_action,
        interactive_elements=state.interactive_elements,
        screenshot_path=screenshot_path,
        error=state.error_status,
    )


def _execute_step(ctx, step, parent_step=None, single_attempt=False):
    """Execute one step (top-level or nested) with its attempt budget.

    Records exactly one PageStatus row for the step (its final outcome).
    Raises StepAbortError when a non-graceful step exhausts its attempts."""
    graceful = bool(step.get("graceful", False))
    collection_methods = _collection_methods_in(step)
    if parent_step is not None and collection_methods:
        raise StepAbortError(
            "bounded collection actions cannot be nested under "
            "expect_download or in login phases"
        )
    attempts = 1 if single_attempt or collection_methods else step_attempts(graceful)
    step_number = step.get("step", 0)

    _debug_wait(ctx, step)

    state = None
    for attempt in range(1, attempts + 1):
        try:
            state = _process_step(
                ctx.bcs, step, collection_actions=_collection_actions(ctx, step)
            )
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


def _step_prompt(step, what):
    """Human-readable pause prompt generated from the step description."""
    step_number = step.get("step", 0)
    description = step.get("description", "") or "(no description)"
    return f"Step {step_number}: {description} - {what}"


def _wait_user_method(step):
    """The ``wait_user`` method entry of a step (C5.5), or None when the
    step has no wait_user (the normal step path)."""
    for method_entry in step.get("methods", []):
        if isinstance(method_entry, dict) and method_entry.get("method") == "wait_user":
            return method_entry
    return None


def _wait_user_args(step, method):
    """(prompt, until) of a wait_user method entry.

    The prompt falls back to the generated step prompt (a wait_user without
    an explicit prompt still pauses with something the operator can act on);
    until defaults to None (complete immediately on resume)."""
    prompt = None
    until = None
    for arg in method.get("arguments", []) or []:
        if isinstance(arg, dict):
            if "prompt" in arg:
                prompt = arg["prompt"]
            if "until" in arg:
                until = arg["until"]
    if prompt is None:
        prompt = _step_prompt(step, "waiting for the operator")
    return prompt, until


# The until-locator mapping (C5.5): the first key present in the until dict
# selects the Playwright locator method; the whole dict is passed through as
# keyword arguments (same shape as the recipe's locator methods, e.g.
# {"role": "link", "name": "My account"}).
_UNTIL_LOCATOR_KEYS = (
    ("role", "get_by_role"),
    ("test_id", "get_by_test_id"),
    ("placeholder", "get_by_placeholder"),
    ("label", "get_by_label"),
    ("text", "get_by_text"),
    ("selector", "locator"),
)


def _locator_for(page, until):
    """Build a Playwright locator from a wait_user ``until`` dict.

    Raises ValueError when the dict does not map to a known locator method -
    a recipe authoring error that must surface before the operator is asked."""
    if not isinstance(until, dict):
        raise ValueError(f"wait_user 'until' must be a locator dict, got: {until!r}")
    for key, method_name in _UNTIL_LOCATOR_KEYS:
        if key in until:
            method = getattr(page, method_name, None)
            if method is None:
                raise ValueError(f"no {method_name!r} locator method on the page")
            return method(**until)
    raise ValueError(
        f"wait_user 'until' has no recognized locator key: {sorted(until)}")


def _execute_wait_user_step(ctx, step, method):
    """C5.5: a wait_user step pauses before execution (reason=wait_user) and
    completes on resume - it is consumed, not re-executed (decision 19: a
    consumed CAPTCHA code cannot be re-entered). With an ``until`` locator
    the step completes only once the locator is visible, bounded by the pause
    deadline; a missed deadline re-pauses with the same prompt. Cancel and
    timeout abort the run with their terminal outcome."""
    prompt, until = _wait_user_args(step, method)
    bcs = getattr(ctx, "bcs", None)
    # Pause prompts are retained in Run/notifications. Expand dates while
    # keeping credential tokens literal, as in the existing pause flow.
    prompt = expand_argument(prompt, None, getattr(bcs, "date_context", None))
    until = process_argument(until, bcs)
    try:
        until_locator = None if until is None else _locator_for(ctx.page, until)
    except ValueError as e:
        raise StepAbortError(
            f"Step {step.get('step', 0)} has an invalid wait_user 'until': {e}")
    while True:
        outcome = pause_loop(ctx, "wait_user", prompt,
                              transform_step_to_json(step), None,
                              step.get("step", 0))
        if outcome != "resume":
            raise PauseOutcomeAbort(outcome)
        if until_locator is None:
            break
        # The until check is bounded by the (fresh) pause deadline of the
        # pause that was just resumed.
        remaining_ms = max(
            (ctx.last_pause_deadline - datetime.now()).total_seconds() * 1000, 0)
        try:
            until_locator.wait_for(state="visible", timeout=remaining_ms)
        except PlaywrightTimeoutError:
            continue  # deadline exceeded: re-pause with the same prompt
        break
    state = PageState(ctx.bcs.service, step.get("step", 0), ctx.page)
    state.set_locator_action(transform_step_to_json(step))
    state.set_error({})  # completed: no error, like a clean step success
    _record_step(ctx, state, step)
    return state


def _execute_step_with_pause(ctx, step):
    """Execute one top-level step under the C5 pause loop.

    A non-graceful step that exhausts its attempts (StepAbortError) pauses
    the run (reason=step_failed): a resume re-executes the step from the
    beginning with a fresh attempt budget; cancel and timeout abort the run
    with their terminal outcome. Graceful steps never pause (their failure
    is recorded and the run continues)."""
    while True:
        try:
            return _execute_step(ctx, step)
        except StepAbortError as e:
            if e.page_state is not None:
                step_action_json = e.page_state.locator_action
                error = e.page_state.error_status
            else:
                step_action_json = transform_step_to_json(step)
                method = next((entry.get("method") for entry in step.get("methods", [])
                               if entry.get("method")), None)
                error = {"error": [failure_record(method, category="other")]}
            attempts = 1 if _collection_methods_in(step) else MAX_STEP_ATTEMPTS
            noun = "attempt" if attempts == 1 else "attempts"
            prompt = _step_prompt(step, f"failed after {attempts} {noun}. "
                                       "Fix the page (or repair the recipe), then resume.")
            outcome = pause_loop(ctx, "step_failed", prompt, step_action_json, error,
                                 step.get("step", 0))
            if outcome == "resume":
                continue
            raise PauseOutcomeAbort(outcome) from e


def _execute_login(ctx, step):
    """One durable transaction; each phase submits once, resume only verifies."""
    options = login_options(step)
    locator = _locator_for(ctx.page, process_argument(options["success"], ctx.bcs))

    def proven(timeout):
        try:
            locator.wait_for(state="visible", timeout=timeout)
        except PlaywrightTimeoutError:
            return False
        if not ctx.db.login_succeeded(ctx.task["id"], ctx.run_id):
            raise StepAbortError("Another run owns the unresolved login attempt")
        return True

    if proven(options["session_timeout_ms"]):
        return
    phases = options["phases"]
    start = 0
    # Find the latest completed phase before dispatching any credentials.
    for index in range(len(phases) - 2, -1, -1):
        try:
            _locator_for(ctx.page, process_argument(phases[index]["success"], ctx.bcs)).wait_for(
                state="visible", timeout=options["session_timeout_ms"])
            start = index + 1
            break
        except PlaywrightTimeoutError:
            pass
    reserved = False
    try:
        for index in range(start, len(phases)):
            phase = phases[index]
            final = index == len(phases) - 1
            marker = _locator_for(ctx.page, process_argument(phase["success"], ctx.bcs))
            for preparation in phase.get("steps", []):
                _execute_step(ctx, preparation, parent_step=step["step"], single_attempt=True)
            if not reserved:
                if not ctx.db.reserve_login_attempt(ctx.task["id"], ctx.run_id,
                                                    options["max_failures"]):
                    from .notify import notify_login_locked
                    task = ctx.db.get_task(ctx.task["id"])
                    if task["login_locked"]:
                        notify_login_locked(ctx.db, task)
                    raise StepAbortError("Login attempt refused; check the task login block")
                reserved = True
            _execute_step(ctx, phase["submit"], parent_step=step["step"], single_attempt=True)
            if final:
                if proven(options["timeout_ms"]):
                    return
            else:
                marker.wait_for(state="visible", timeout=options["timeout_ms"])
    except RunInterrupted:
        raise
    except Exception as e:
        if not reserved:
            raise  # Preparation failed before any submission was reserved.
        # Never retry an uncertain phase, including a locator or DB error.
        logger.warning("Login submission has no success proof (%s)", type(e).__name__)
    if settle_attempt(ctx.db, ctx.task["id"], ctx.run_id):
        raise StepAbortError("Login attempt limit reached; task blocked")
    while True:
        outcome = pause_loop(
            ctx, "login_failed",
            "Login not proven. Complete it manually, then resume to verify. "
            "Resume never submits again. Manual submissions are not counted.",
            None, "login_not_proven", step["step"])
        if outcome != "resume":
            raise PauseOutcomeAbort(outcome)
        if proven(options["timeout_ms"]):
            return


def _handle_download_with_pause(ctx, step):
    """The expect_download handler under the C5 pause loop
    (reason=download_failed); a resume retries the download."""
    while True:
        try:
            _handle_download(ctx, step)
            return
        except StepAbortError as e:
            prompt = _step_prompt(step, "the download failed. "
                                       "Fix the page (or repair the recipe), then resume.")
            if e.page_state is not None:
                error = e.page_state.error_status
            else:
                error = {"error": [failure_record(
                    "expect_download", category="download")]}
            outcome = pause_loop(ctx, "download_failed", prompt,
                                  transform_step_to_json(step), error,
                                  step.get("step", 0))
            if outcome == "resume":
                continue
            raise PauseOutcomeAbort(outcome) from e


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
    except RunInterrupted:
        raise  # a shutdown signal is not a download error to pause on
    except StepAbortError:
        raise
    except Exception as e:
        category = failure_category("expect_download", e)
        result_value = f"failure: download ({category})"
        logger.warning("Download failed with %s", type(e).__name__)
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

    Returns (files_downloaded, aborted, pause_outcome); pause_outcome is
    None or the terminal outcome of a cancel/timeout pause (C5.4). Every
    started run leaves the browser closed, even on abort."""
    files_downloaded = []
    aborted = False
    pause_outcome = None
    with sync_playwright() as p:
        try:
            _launch_browser(ctx, p)
        except RunInterrupted:
            raise  # a shutdown signal is not a launch failure to abort on
        except Exception as e:
            logger.error("Browser launch failed: %s", failure_record("launch_persistent_context", e))
            return files_downloaded, True, None
        try:
            services = recipe.get("services", [])
            for service in services:
                service_name = service.get("serviceName")
                logger.info(f"Processing Service: {service_name} for {ctx.bcs.usr}.")
                for step in sorted(service.get("steps", []), key=lambda x: x.get("step", 0)):
                    if is_login(step):
                        _execute_login(ctx, step)
                        continue
                    wait_method = _wait_user_method(step)
                    if wait_method is not None:
                        # C5.5: a wait_user step pauses before execution and
                        # completes on resume (consumed, not re-executed).
                        _execute_wait_user_step(ctx, step, wait_method)
                        continue
                    step_state = _execute_step_with_pause(ctx, step)
                    # Check if the step expects a download
                    if check_parameter_in_json(step_state.locator_action, {"action": "expect_download"}):
                        _handle_download_with_pause(ctx, step)
        except PauseOutcomeAbort as e:
            aborted = True
            pause_outcome = e.outcome
            logger.error(f"Run aborted by pause outcome: {e.outcome}")
        except StepAbortError as e:
            aborted = True
            logger.error(f"Run aborted: {e}")
        except RunInterrupted:
            raise  # a shutdown signal ends the run interrupted, not failed
        except Exception as e:
            aborted = True
            logger.error("Unexpected recipe error: run aborted: %s", failure_record("run_recipe", e))
        finally:
            for closer in (ctx.page.close, ctx.context.close):
                try:
                    closer()
                except RunInterrupted:
                    raise  # a shutdown signal during the close still ends the run interrupted
                except Exception:
                    pass
    files_downloaded = ctx.files_downloaded
    return files_downloaded, aborted, pause_outcome


def run_task(task_id: int, debug: bool = False, *, date_from=None) -> int:
    """Serialize all runner entries, including direct CLI invocations.

    A process-held lock survives neither crash nor SIGKILL, and must never be
    unlinked (a new inode could allow another runner to pass the same lock).
    """
    config.load_env()
    config.ensure_dirs()
    lock_dir = config.DATA_DIR / "task-locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    with (lock_dir / f"task-{int(task_id)}.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("runner: task already has an active runner", file=sys.stderr)
            return 1
        if date_from is None:
            return _run_task(task_id, debug)
        return _run_task(task_id, debug, date_from=date_from)


def _run_task(task_id: int, debug: bool = False, *, date_from=None) -> int:
    """Execute one task run (sync Playwright step loop).

    Returns the process exit code: 0 on success, 1 on a run failure
    (display, vault preflight, recipe error, or step failure)."""
    config.load_env()
    _ensure_logging()
    _install_signal_handlers()

    db = Database()
    try:
        task = db.get_task(task_id)
        if task is None:
            print(f"runner: task {task_id} not found", file=sys.stderr)
            return 1

        if task["login_locked"] or task["login_pending_run_id"] is not None:
            print("runner: task login is blocked or unresolved; no run started", file=sys.stderr)
            return 1

        recipe_file = task["recipe_file"] or str(config.recipe_path_for(task["service"]))
        recipe = CheckRecipe(recipe_file, str(config.RECIPE_SCHEMA))
        if recipe is None:
            print(f"runner: recipe {recipe_file} not found or invalid", file=sys.stderr)
            return 1
        try:
            validate_login_recipe(recipe)
        except ValueError as e:
            print(f"runner: invalid login contract: {e}", file=sys.stderr)
            return 1

        try:
            dates = DateContext.capture(task["date_window_days"], date_from)
            validate_variable_recipe(recipe, dates)
        except ValueError as e:
            print(f"runner: invalid variable contract: {e}", file=sys.stderr)
            return 1

        # C6: the runner owns the per-run display: claim a display from the
        # configured range before the Run row exists (the row records it),
        # start the Xvfb/x11vnc/websockify stack, and point DISPLAY at it
        # for the headful browser launch.
        try:
            display_number, websockify_port = display.allocate_display(db)
        except display.DisplayError as e:
            print(f"runner: cannot allocate a display for task {task_id}: {e}",
                  file=sys.stderr)
            return 1

        result = "failure"
        files = []
        # The effective vault API values (Settings win over env) are exported
        # into the process environment before any vault call, so the vault
        # transport's BW_API_HOST read and the run context's TOTP re-fetch
        # both see them; empty values keep the legacy env-only behavior.
        api_url, api_host = config.vault_settings(db)
        os.environ["BW_API_URL"] = api_url
        os.environ["BW_API_HOST"] = api_host
        children = None
        run_id = None
        try:
            # The row records this process' pid so the orchestrator (C7.2)
            # can match the spawned subprocess to the row it created, and
            # the startup orphan cleanup (C7.4) can check whether the pid
            # is alive. It is created inside the release scope below so a
            # shutdown signal (C7.5) in any window after the display claim
            # still releases the display and finalizes the row.
            run_id = db.create_run(task_id, pid=os.getpid(),
                                   display=display_number,
                                   novnc_port=websockify_port)
            db.set_task_status(task_id, "running")
            try:
                children = _start_display_stack(db, run_id, display_number)
                os.environ["DISPLAY"] = f":{display_number}"
                credentials = _vault_preflight(task, db)
                ctx = _RunContext(task, run_id, db, debug, credentials, api_url)
                ctx.bcs.date_context = dates
                files, aborted, pause_outcome = _run_recipe(ctx, recipe)
                result = run_result(aborted, files, pause_outcome)
            except RunInterrupted:
                # A shutdown signal (SIGTERM/SIGINT) reached the run: the
                # teardown below reaps the display stack and finalizes the
                # row with the interruption result.
                result = "interrupted"
                logger.warning(f"Task {task_id} run {run_id} interrupted by shutdown signal")
            except (VaultAPIError, VaultTransportError) as e:
                # A vault-preflight failure: one clear stderr line, distinct
                # from a step failure (which the step loop logs on stdout).
                print(f"runner: vault preflight failed for task {task_id}: {e}",
                      file=sys.stderr)
            except display.DisplayError as e:
                # A display-stack failure (binary missing, Xvfb refusing the
                # display): one clear stderr line, like a vault-preflight
                # failure.
                print(f"runner: display stack failed for task {task_id}: {e}",
                      file=sys.stderr)
            except Exception as e:
                logger.error("Task %s run %s aborted by an unexpected error: %s",
                             task_id, run_id, failure_record("run_task", e))
            finally:
                # The display stack is reaped and the row finalized with
                # the run, so a finished run never leaks the stack or
                # leaves the row open.
                if children is not None:
                    display.stop_display_stack(children)
                # The run row always ends with a terminal result, even when
                # the vault preflight or an unexpected error stopped the
                # run before the step loop ran.
                db.update_run(run_id, result=result, ended_at=now())
                settle_attempt(db, task_id, run_id)
                # A finished run releases the task: the 'waiting' status
                # set by a pause is terminal here (resume, cancel and
                # timeout all end the run), so the task goes back to idle
                # and the scheduler's row lock can claim it again.
                db.release_task_run(task_id)
        finally:
            # The claim is released with the run, so a finished (or
            # interrupted) run never leaks a display - even when the
            # shutdown signal arrived before the Run row existed.
            display.release_display(display_number)
        if result == "success":
            logger.info(f"Task {task_id} run {run_id} finished with downloaded file(s) {files}.")
            return 0
        logger.error(f"Task {task_id} run {run_id} failed (result={result}, downloads={files}).")
        return 1
    except RunInterrupted:
        # Interrupted before the Run row existed (early pre-checks, or the
        # row creation itself): there is nothing to finalize; the display
        # release above already ran when the claim had happened, and the
        # orchestrator's no-row path releases the claim (C7.2).
        logger.warning(f"Task {task_id} interrupted before the run started")
        return 1
    finally:
        db.close()
