> Documentation for issue #37. The action requires the daemon run-start
> date context (issue #26); without it the action refuses execution.

# Replacement calendars

The daemon supports `replacement_calendar`. Use this action when each
previous-month click replaces the document list. Keep `click_until_absent` for
cumulative lists. The legacy batch runner does not support calendar traversal.

The daemon supplies its existing run-start `DateContext`. The action visits
every month from `DATE_TO` back to `DATE_FROM`, inclusive. It collects the whole
first calendar month even when `DATE_FROM` falls inside it. This proves calendar
coverage. It does not assign a financial date to a notice. Daily execution stays
a task schedule choice. This action does not change cron or the deployed task.

## Recipe contract

Start on `DATE_TO`'s month before this step. The locator must match one visible
calendar root. All action selectors are CSS selectors relative to that root.
The account, year, and month each require one visible element. Text is trimmed.
The year and month use decimal numbers. For named months, supply `month_names`
as twelve distinct strings in January-to-December order.

```yaml
- step: 10
  description: Collect each calendar month in the run window
  methods:
    - method: locator
      arguments:
        - selector: "#calendar"
    - method: replacement_calendar
      arguments:
        - account_id: "synthetic-account"
          account_selector: ".account"
          year_selector: ".year"
          month_selector: ".month"
          previous_selector: ".previous"
          item_selector: ".notice"
          ready_selector: ".ready"
          empty_selector: ".empty"
          max_months: 24
          download_options:
            key_attribute: href
            max_items: 200
            timeout_ms: 120000
            event_window_ms: 1000
```

`account_id` is the expected portal account identity. It is not a password or a
Bitwarden item name. Keep private account values in private recipe configuration.
The selector must identify the active account, not a list of available accounts.

`ready_selector` must prove that the current month's content has finished
loading. A heading which changes before the list is ready is insufficient.
The engine reads identity, readiness, item keys, and the empty marker in one
DOM evaluation. It does not infer completion from a detached control, a row
count, or a short period without DOM changes. Qualify these selectors against
the provider before real use. A portal without a usable readiness signal is
unsupported until its adapter can prove this contract.

An empty month requires one visible `empty_selector` match and no document
controls. Hidden document controls or simultaneous documents and an empty
marker fail. Each nonempty month uses the existing `download_all` action.
Keys must be stable and unique inside that month. Filename collision refusal
still applies across the entire run, including different months.

The engine follows only the offered previous control. It does not create URLs
or execute recipe-supplied JavaScript. The window must fit `max_months` (1–120).
`max_items` counts offered controls across all visited months (1–200), checked
before the next month's downloads. The timeout is one shared browser deadline
(1–600000 ms). Event windows use the existing `download_all` limits. File
persistence is synchronous; an in-progress save cannot be preempted by this
browser deadline. Completion still checks the deadline after saving.

Wrong accounts, unexpected months, missing controls, source drift, exhausted
bounds, and ambiguous content fail the action. Errors do not include observed
account text or provider URLs. Existing persisted documents survive a later
failure. The step runs once under the daemon's collection policy, with no
automatic resend. An operator resume is an explicit new invocation. Inspect
retained downloads and restore the first calendar month before resuming. The
same run retains completed item keys per step, account, key attribute and month.
It skips those keys without clicking or downloading them again. Repeated keys
in different months remain independent. A new run does not inherit this cache;
normal per-task content deduplication still applies after persistence.

## Verification

Install the pinned runtime and development requirements, then install
the matching Chromium build. From the checkout root:

```bash
apps/.venv/bin/python -m pytest tests/test_bc_calendar.py tests/test_bc_collection.py -q
apps/.venv/bin/python -m pytest tests/ -q
apps/.venv/bin/python -m ruff check apps tests
```

The calendar fixture fulfills all browser requests in memory. It uses a fresh
browser context, temporary SQLite database, temporary files, and no consumers.
It never contacts a broker, Bitwarden, Paperless, or a deployed service.

Provider qualification of real portal calendars is not part of this
integration; qualify the recipe selectors against the provider before real use.
