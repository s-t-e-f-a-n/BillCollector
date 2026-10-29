"""Bounded Playwright collection actions used by both recipe runners.

The recipe runners supply already-resolved Playwright locators and a small
download persistence adapter.  This module owns the browser-sensitive rules:
live re-querying, stable item identity, progress proof, hard bounds, popup
capture, and restoration after a download navigates away from the listing.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from .interrupt import RunInterrupted

MAX_DOWNLOAD_ITEMS = 200
MAX_PAGINATION_CLICKS = 100
MAX_DOWNLOAD_TIMEOUT_MS = 600_000
MAX_EVENT_WINDOW_MS = 10_000
COLLECTION_LOCATOR_METHODS = frozenset({
    "locator", "get_by_role", "get_by_label", "get_by_text",
    "get_by_title", "get_by_placeholder", "get_by_test_id",
})
COLLECTION_ACTION_METHODS = frozenset({
    "click_until_absent", "download_all", "replacement_calendar",
})

logger = logging.getLogger(__name__)

_READ_KEYS = """(elements, attribute) => elements.map(
    element => element.getAttribute(attribute))"""
_READ_KEY = "(element, attribute) => element.getAttribute(attribute)"
_VISIBLE_COUNT = """elements => elements.filter(element => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
        && rect.width > 0 && rect.height > 0;
}).length"""


class CollectionError(RuntimeError):
    """A bounded collection action could not prove safe completion."""


@dataclass(frozen=True)
class PaginationResult:
    """Observable, non-sensitive result of a pagination action."""

    clicks: int
    visible_items: int


def validate_terminal_action(methods, index, name):
    """Require exactly one page locator followed by one collection action."""
    if len(methods) != 2 or index != 1:
        raise CollectionError(
            f"{name} requires exactly one locator method followed by the action"
        )
    locator_method = methods[0].get("method") if isinstance(methods[0], dict) else None
    if locator_method not in COLLECTION_LOCATOR_METHODS:
        raise CollectionError(
            f"{name} requires a page locator; found {locator_method}"
        )


def validate_collection_chain(methods):
    """Preflight every collection action before any recipe method executes."""
    for index, entry in enumerate(methods):
        if not isinstance(entry, dict):
            continue
        name = entry.get("method")
        if name in COLLECTION_ACTION_METHODS:
            validate_terminal_action(methods, index, name)


def _positive_int(options, name, *, maximum):
    value = options.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CollectionError(f"{name} must be an integer")
    if value < 1 or value > maximum:
        raise CollectionError(f"{name} must be between 1 and {maximum}")
    return value


def _options(options, *, names):
    if not isinstance(options, dict):
        raise CollectionError("action options must be one object")
    unknown = sorted(set(options) - set(names))
    if unknown:
        raise CollectionError(f"unknown action options: {', '.join(unknown)}")
    return options


def _control_state(control):
    """Return ``absent``, ``hidden`` or ``visible`` for one live control."""
    count = control.count()
    if count == 0:
        return "absent"
    if count != 1:
        raise CollectionError(
            f"pagination control matched {count} elements; expected one"
        )
    return "visible" if control.first.is_visible() else "hidden"


def _visible_count(locator):
    return int(locator.evaluate_all(_VISIBLE_COUNT))


def click_until_absent(page, control, options):
    """Click a live pager until it is absent or hidden.

    ``progress_selector`` identifies rows whose visible count must increase
    after every click.  A visible disabled control is not completion:
    Playwright waits for actionability up to ``timeout_ms``.  ``max_clicks``
    is a hard budget for this invocation.
    """
    options = _options(
        options,
        names={"progress_selector", "max_clicks", "timeout_ms"},
    )
    selector = options.get("progress_selector")
    if not isinstance(selector, str) or not selector.strip():
        raise CollectionError("progress_selector must be a non-empty string")
    max_clicks = _positive_int(
        options, "max_clicks", maximum=MAX_PAGINATION_CLICKS
    )
    timeout_ms = _positive_int(options, "timeout_ms", maximum=120_000)
    progress = page.locator(selector)
    clicks = 0
    total_deadline = time.monotonic() + timeout_ms / 1000

    while True:
        state = _control_state(control)
        current = _visible_count(progress)
        if state != "visible":
            return PaginationResult(clicks=clicks, visible_items=current)
        if clicks >= max_clicks:
            raise CollectionError(
                "pagination limit reached while the control remained visible "
                f"after {clicks} clicks"
            )

        before = current
        remaining = _remaining_ms(total_deadline)
        if remaining == 0:
            raise CollectionError(
                f"pagination timeout expired after {clicks} clicks"
            )
        try:
            control.first.click(timeout=remaining)
        except RunInterrupted:
            raise
        except Exception as error:
            if _control_state(control) != "visible":
                return PaginationResult(
                    clicks=clicks, visible_items=_visible_count(progress)
                )
            raise CollectionError(
                "pagination control stayed visible but was not actionable "
                f"after {clicks} clicks"
            ) from error
        clicks += 1

        while True:
            state = _control_state(control)
            current = _visible_count(progress)
            if state != "visible":
                return PaginationResult(clicks=clicks, visible_items=current)
            if current > before:
                break
            if _remaining_ms(total_deadline) == 0:
                raise CollectionError(
                    "pagination made no visible progress "
                    f"before the total timeout after click {clicks}: "
                    f"count stayed at {before}"
                )
            page.wait_for_timeout(50)


def _snapshot(locator, key_attribute):
    keys = locator.evaluate_all(_READ_KEYS, key_attribute)
    return tuple(keys)


def _validate_snapshot(keys, max_items):
    count = len(keys)
    if count == 0:
        raise CollectionError("download list is empty")
    if count > max_items:
        raise CollectionError(
            f"download list has {count} items; recipe limit is {max_items}"
        )
    if any(not isinstance(key, str) or not key.strip() for key in keys):
        raise CollectionError("download list contains an empty item key")
    if len(set(keys)) != count:
        raise CollectionError("download list contains duplicate item keys")


def _restore_listing(page, listing_url, timeout_ms):
    if page.url == listing_url:
        return
    page.go_back(wait_until="domcontentloaded", timeout=timeout_ms)
    if page.url != listing_url:
        raise CollectionError("download listing could not be restored")


def _dispose_best_effort(target):
    """Dispose without replacing a shutdown signal with cleanup failure."""
    try:
        target.dispose()
    except Exception:
        return False
    return True


def _remaining_ms(deadline):
    return max(0, int((deadline - time.monotonic()) * 1000))


def _require_event_budget(deadline, count, index, event_window_ms):
    remaining = _remaining_ms(deadline)
    required = (count - index) * event_window_ms
    if required >= remaining:
        raise CollectionError(
            "download_all timeout_ms must leave more than "
            f"{required} ms for the remaining {count - index} "
            f"event windows after {index} of {count} items; "
            f"only {remaining} ms remain"
        )
    return remaining - required


def _cleanup_preserving(primary_error, description, action):
    """Run cleanup without replacing an exception from the main operation."""
    try:
        action()
    except RunInterrupted:
        raise
    except Exception:
        if primary_error is None:
            raise
        logger.warning(
            "%s failed while preserving the primary collection error",
            description,
            exc_info=True,
        )


def _download_one(page, context, target, save_download, index, count,
                  total_deadline, event_window_ms, *, budget_index=None,
                  budget_count=None):
    listing_url = page.url
    observed = []
    popups = []

    def on_download(download):
        observed.append(download)

    def on_page(new_page):
        popups.append(new_page)
        new_page.on("download", on_download)

    interrupted = False
    primary_error = None
    page.on("download", on_download)
    context.on("page", on_page)
    try:
        if budget_index is None:
            budget_index = index
        if budget_count is None:
            budget_count = count
        click_timeout = _require_event_budget(
            total_deadline, budget_count, budget_index, event_window_ms
        )
        target.click(timeout=click_timeout)
        full_event_deadline = time.monotonic() + event_window_ms / 1000
        deadline = min(total_deadline, full_event_deadline)
        # Observe the full recipe-provided window. Ending shortly after the
        # first event can assign a delayed second event to the next control.
        while time.monotonic() < deadline:
            if len(observed) > 1:
                break
            remaining = max(1, int((deadline - time.monotonic()) * 1000))
            page.wait_for_timeout(min(50, remaining))
        if len(observed) <= 1 and deadline < full_event_deadline:
            raise CollectionError(
                "download_all browser timeout expired during the event window "
                f"for item {index + 1} of {count}"
            )
        if len(observed) != 1:
            raise CollectionError(
                f"download item {index + 1} of {count} produced "
                f"{len(observed)} files; expected one"
            )
        return save_download(observed[0])
    except RunInterrupted:
        interrupted = True
        raise
    except Exception as error:
        primary_error = error
        raise
    finally:
        if interrupted:
            # Browser teardown belongs to the runner after a shutdown signal.
            # Best-effort listener removal must not replace RunInterrupted.
            for emitter, event, callback in (
                (page, "download", on_download),
                (context, "page", on_page),
            ):
                try:
                    emitter.remove_listener(event, callback)
                except Exception:
                    interrupted = True
        else:
            _cleanup_preserving(
                primary_error,
                "page download-listener removal",
                lambda: page.remove_listener("download", on_download),
            )
            _cleanup_preserving(
                primary_error,
                "context page-listener removal",
                lambda: context.remove_listener("page", on_page),
            )
            for popup in popups:
                if not popup.is_closed():
                    _cleanup_preserving(
                        primary_error, "popup close", popup.close
                    )
            if page.url != listing_url:
                def restore_listing():
                    remaining = _remaining_ms(total_deadline)
                    if remaining == 0:
                        raise CollectionError(
                            "download_all browser timeout expired before "
                            "restoring the listing"
                        )
                    _restore_listing(page, listing_url, remaining)

                _cleanup_preserving(
                    primary_error, "listing restoration", restore_listing
                )


def download_all(page, context, locator, save_download, options,
                 *, completed_keys=None, before_download=None, deadline=None):
    """Download every item from one stable, explicitly keyed locator.

    The initial ordered key set is the contract for the whole action.  The
    list is re-read after every click and the selected element handle is
    checked immediately before use, so re-rendering is supported but shrink,
    reorder, replacement and ambiguous controls fail closed.  Successfully
    persisted records remain committed when a later item fails.
    """
    options = _options(
        options,
        names={
            "key_attribute", "max_items", "timeout_ms", "event_window_ms",
        },
    )
    key_attribute = options.get("key_attribute")
    if not isinstance(key_attribute, str) or not key_attribute.strip():
        raise CollectionError("key_attribute must be a non-empty string")
    max_items = _positive_int(
        options, "max_items", maximum=MAX_DOWNLOAD_ITEMS
    )
    timeout_ms = _positive_int(
        options, "timeout_ms", maximum=MAX_DOWNLOAD_TIMEOUT_MS
    )
    event_window_ms = _positive_int(
        options, "event_window_ms", maximum=MAX_EVENT_WINDOW_MS
    )
    if event_window_ms >= timeout_ms:
        raise CollectionError("event_window_ms must be less than timeout_ms")
    total_deadline = time.monotonic() + timeout_ms / 1000
    if deadline is not None:
        total_deadline = min(total_deadline, deadline)

    keys = _snapshot(locator, key_attribute)
    _validate_snapshot(keys, max_items)
    if completed_keys is None:
        completed_keys = set()
    records = []
    count = len(keys)
    pending = [
        (index, key) for index, key in enumerate(keys)
        if key not in completed_keys
    ]
    pending_count = len(pending)
    if pending_count:
        _require_event_budget(
            total_deadline, pending_count, 0, event_window_ms
        )
    for pending_index, (index, expected_key) in enumerate(pending):
        _require_event_budget(
            total_deadline, pending_count, pending_index, event_window_ms
        )
        while _snapshot(locator, key_attribute) != keys:
            if _remaining_ms(total_deadline) == 0:
                raise CollectionError(
                    f"download list changed after {index} of {count} items "
                    "until the browser timeout expired"
                )
            page.wait_for_timeout(50)

        handle_timeout = _require_event_budget(
            total_deadline, pending_count, pending_index, event_window_ms
        )
        target = locator.nth(index).element_handle(
            timeout=handle_timeout
        )
        if target is None:
            raise CollectionError(
                f"download item {index + 1} of {count} disappeared"
            )
        interrupted = False
        primary_error = None
        try:
            if target.evaluate(_READ_KEY, key_attribute) != expected_key:
                raise CollectionError(
                    f"download list changed after {index} of {count} items"
                )
            if before_download is not None:
                before_download()

            def save_completed(download):
                record = save_download(download)
                completed_keys.add(expected_key)
                return record

            records.append(
                _download_one(
                    page,
                    context,
                    target,
                    save_completed,
                    index,
                    count,
                    total_deadline,
                    event_window_ms,
                    budget_index=pending_index,
                    budget_count=pending_count,
                )
            )
        except RunInterrupted:
            interrupted = True
            raise
        except Exception as error:
            primary_error = error
            raise
        finally:
            if interrupted:
                _dispose_best_effort(target)
            else:
                _cleanup_preserving(
                    primary_error, "element-handle disposal", target.dispose
                )
    return records
