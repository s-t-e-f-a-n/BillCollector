"""Bounded, descending monthly replacement traversal for daemon recipes.

The root contains the account, year, month, readiness proof, and documents.
Selectors are data passed to a fixed reader, never recipe JavaScript. Readiness
must identify completed month content, not a heading that updates before it.
"""

from dataclasses import dataclass
from datetime import date
import time

from playwright.sync_api import Error as PlaywrightError

from .collection import (
    CollectionError, _positive_int, _remaining_ms, _restore_listing,
    _validate_snapshot, download_all,
)


@dataclass(frozen=True)
class CalendarResult:
    months: tuple[tuple[int, int], ...]
    empty_months: tuple[tuple[int, int], ...]
    downloaded: int


# One browser evaluation binds identity and readiness to the same DOM revision.
_READ = """(roots, options) => {
    if (roots.length > 1) return {ambiguous: true};
    const visible = e => {
        const r = e.getBoundingClientRect(), s = getComputedStyle(e);
        return r.width > 0 && r.height > 0 && s.display !== 'none'
            && s.visibility !== 'hidden';
    };
    const root = roots[0];
    if (!root || !visible(root)) return null;
    const one = selector => {
        const nodes = root.querySelectorAll(selector);
        return nodes.length === 1 && visible(nodes[0]) ? nodes[0] : null;
    };
    const text = selector => {
        const node = one(selector);
        return node ? node.textContent.trim() : null;
    };
    const items = [...root.querySelectorAll(options.item_selector)];
    return {
        account: text(options.account_selector),
        year: text(options.year_selector), month: text(options.month_selector),
        ready: !!one(options.ready_selector),
        empty: !!one(options.empty_selector),
        hiddenItems: items.some(e => !visible(e)),
        keys: items.map(e => e.getAttribute(options.download_options.key_attribute))
    };
}"""


def validate_options(options):
    """Validate raw or expanded recipe options without browser access."""
    required = {
        'account_id', 'account_selector', 'year_selector', 'month_selector',
        'previous_selector', 'item_selector', 'empty_selector', 'ready_selector',
        'max_months', 'download_options',
    }
    if not isinstance(options, dict) or not required <= options.keys() <= required | {'month_names'}:
        raise CollectionError('calendar options have missing or unsupported fields')
    for name in required - {'max_months', 'download_options'}:
        if not isinstance(options[name], str) or not options[name].strip():
            raise CollectionError('calendar selectors and account must be non-empty strings')
    _positive_int(options, 'max_months', maximum=120)
    download = options['download_options']
    if not isinstance(download, dict) or set(download) != {
        'key_attribute', 'max_items', 'timeout_ms', 'event_window_ms',
    }:
        raise CollectionError('calendar download options are invalid')
    if not isinstance(download['key_attribute'], str) or not download['key_attribute'].strip():
        raise CollectionError('calendar item key attribute must be non-empty')
    _positive_int(download, 'max_items', maximum=200)
    timeout = _positive_int(download, 'timeout_ms', maximum=600_000)
    event = _positive_int(download, 'event_window_ms', maximum=10_000)
    if event >= timeout:
        raise CollectionError('calendar event window must be less than total timeout')
    names = options.get('month_names')
    if names is not None and (
        not isinstance(names, list) or len(names) != 12
        or any(not isinstance(name, str) or not name.strip() for name in names)
        or len(set(names)) != 12
    ):
        raise CollectionError('calendar month_names must contain twelve unique names')


def _months(dates, maximum):
    if (dates is None or type(dates.date_from) is not date
            or type(dates.today) is not date or dates.date_from > dates.today):
        raise CollectionError('calendar requires a valid run-start date context')
    first = dates.date_from.year * 12 + dates.date_from.month - 1
    last = dates.today.year * 12 + dates.today.month - 1
    if last - first + 1 > maximum:
        raise CollectionError('calendar month limit cannot cover the date window')
    return tuple((index // 12, index % 12 + 1) for index in range(last, first - 1, -1))


def collect_calendar(page, context, root, save_download, options, *, dates,
                     completed_by_month=None):
    """Collect complete months intersecting the existing run-start window.

    Start on DATE_TO's month. Click only the offered previous control. Every
    browser wait shares one deadline. Item allowance counts offered controls
    across months and is checked before dispatch. Persistence retains the
    existing download_all contract and cannot be preempted while saving a file.
    """
    validate_options(options)
    if completed_by_month is None:
        completed_by_month = {}
    months = _months(dates, options['max_months'])
    download = options['download_options']
    deadline = time.monotonic() + download['timeout_ms'] / 1000
    remaining_items = download['max_items']
    empty_months = []
    downloaded = 0

    def remaining():
        value = _remaining_ms(deadline)
        if value == 0:
            raise CollectionError('calendar total timeout expired')
        return value

    def snapshot():
        remaining()
        return root.evaluate_all(_READ, options)

    def identity(state):
        if state is None:
            return None
        if state.get('ambiguous'):
            raise CollectionError('calendar root is ambiguous')
        if state['account'] is not None and state['account'] != options['account_id']:
            raise CollectionError('calendar account identity changed')
        if None in (state['account'], state['year'], state['month']):
            return None
        try:
            month = (options['month_names'].index(state['month']) + 1
                     if 'month_names' in options else int(state['month']))
            year = int(state['year'])
            date(year, month, 1)
        except (ValueError, TypeError):
            raise CollectionError('calendar month identity is invalid') from None
        return year, month

    def wait_ready(expected, previous=None):
        while True:
            remaining()
            try:
                state = snapshot()
            except PlaywrightError as error:
                # Navigation can destroy the evaluation context. It proves no
                # completion. Closed pages and invalid selectors fail below.
                if 'Execution context was destroyed' not in str(error):
                    raise
                state = None
            observed = identity(state)
            if observed is not None and observed not in {expected, previous}:
                raise CollectionError('calendar month identity drifted')
            if observed == expected and state['ready']:
                if state['hiddenItems'] or (state['keys'] and state['empty']):
                    raise CollectionError('calendar content is ambiguous')
                if state['keys'] or state['empty']:
                    return state
            page.wait_for_timeout(min(50, remaining()))

    try:
        for index, month in enumerate(months):
            state = wait_ready(month, months[index - 1] if index else None)
            keys = tuple(state['keys'])
            if keys:
                _validate_snapshot(keys, remaining_items)
                listing_url = page.url

                def guard():
                    current = wait_ready(month)
                    if (identity(current) != month or current != state):
                        raise CollectionError('calendar content changed during collection')

                def save_checked(download):
                    # A same-tab document can start a download away from the
                    # listing. Restore first, then bind persistence to the
                    # verified account/month. The shared collector's finally
                    # sees the restored URL and does not navigate back twice.
                    if page.url != listing_url:
                        _restore_listing(page, listing_url, remaining())
                    guard()
                    return save_download(download)

                per_month = dict(download, max_items=remaining_items, timeout_ms=remaining())
                records = download_all(
                    page, context, root.locator(options['item_selector']),
                    save_checked, per_month, before_download=guard, deadline=deadline,
                    completed_keys=completed_by_month.setdefault(
                        (options['account_id'], download['key_attribute'], *month), set()
                    ),
                )
                downloaded += len(records)
                remaining_items -= len(keys)
                guard()
            else:
                empty_months.append(month)
                if snapshot() != state:
                    raise CollectionError('empty calendar identity changed')
            if index + 1 < len(months):
                control = root.locator(options['previous_selector'])
                if control.count() != 1:
                    raise CollectionError('calendar previous control is missing or ambiguous')
                control.click(timeout=remaining())
        remaining()
        return CalendarResult(months, tuple(empty_months), downloaded)
    except PlaywrightError:
        # Playwright errors can include DOM text, selectors and provider URLs.
        raise CollectionError('calendar browser operation failed') from None
