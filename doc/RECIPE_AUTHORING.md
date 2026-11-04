# Write and verify a recipe

Use the daemon's [method contract](RECIPE_METHODS.md) and
[phased-login contract](SAFE_LOGIN.md). This guide explains how to use them.
The public implementation is the execution authority. A contract requirement
or an approved PR is not proof that a release already enforces it.

## Link a task to its recipe and vault item

For service `ExampleMobile`, the default file is
`apps/recipes_playwright/recipe-pw__examplemobile.yaml`. Spaces in the service
name become underscores in the filename. The vault item keeps the original
service/account names: service `ExampleMobile`, account `Home` selects
`ExampleMobile Home`. A blank account selects just the service name.
The filename path can also be overridden per task.

Use one service per task recipe. Use a relative `$schema` reference to
`recipe-pw-schema.yaml` for files beside that schema. When a recipe lives
elsewhere, pass the schema explicitly to the validator. Do not commit a
workstation-specific `/home/...` schema path.

## Chain locators and actions

Each step starts from the Page. Methods run in order. A returned locator or
frame becomes the next chain object. An action returning `None` keeps the
previous object. Properties such as `first` take no arguments. A later step
starts from Page again.

```yaml
services:
- serviceName: synthetic
  steps:
  - step: 1
    methods:
    - method: get_by_role
      arguments:
      - role: link
      - name: Invoice
      - exact: true
    - method: first
    - method: click
```

Use the public API of the pinned Playwright package, not a list of method names
copied from another version. For example, `get_by_label` and
`get_by_placeholder` take a `text` argument. `press` takes `key`, not `value`.
A Page-level `click` requires `selector`; a locator's `click` does not.
The [C3 reference](RECIPE_METHODS.md#2-dispatch-model-the-playwright-surface)
describes the general surface and the five reserved names.

`arguments` is a list of option objects merged into keyword arguments. Prefer
one key per object for ordinary Playwright methods. A collection action uses
one object containing all its required options. Match argument names and types
to the installed API; schema validation alone does not catch every typo in the
current public runner.

## Login, TOTP and variables

Use the standalone `login` action for automatic credential submission. Its
preparation chains end in `fill`; its submit chain ends in `click` or
`press` with `key: Enter`. Choose a success locator unique to the authenticated
state. For password then TOTP, use two phases and different intermediate/final
success markers. The final phase must prove the top-level login success marker.
The [synthetic recipe](examples/recipe-pw__synthetic.yaml) shows this structure.
Legacy `fill`/`click` login sequences do not receive this transaction budget.

An optional TOTP belongs to the portal flow. The vault client permits an item
without TOTP, but a recipe that always fills an OTP field still needs a usable
code. Use a separate recipe or a deliberate manual checkpoint for a genuinely
different portal flow. Never substitute a real TOTP secret into a committed
example.

On the current public baseline, use only exact credential values
`'{{USERNAME}}'`, `'{{PASSWORD}}'` and `'{{OTP}}'`. Do not embed them into a
larger string or rely on arbitrary-depth nested substitution. [PR #34](https://github.com/s-t-e-f-a-n/BillCollector/pull/34) defines
runtime dates and recursive inline expansion; use them only after verifying
that implementation in your installed revision. C3/F08 also adds earlier
method/argument/variable rejection. Until integrated, a successful schema check
is not proof that every method or placeholder will work.

A `wait_user` step pauses before execution and is consumed on resume. Use a
standalone step with a clear prompt. When you add `until`, prefer a tested
`selector` or `role` locator on this baseline; `label`/`placeholder` keyword
normalization is part of the pending validation correction. A manual checkpoint
does not grant automatic retries or count manual submissions in the login budget.

## Pagination, empty lists and downloads

| Need | Action and proof |
|---|---|
| Expand a growing list | `click_until_absent`: exactly one supported page locator then the action; require visible-row count growth through `progress_selector`, `max_clicks` and `timeout_ms`. A visible disabled button is not completion. |
| Download a fixed list | `download_all`: exactly one page locator then the action. Supply a stable non-empty unique `key_attribute`, `max_items`, `timeout_ms` and `event_window_ms`. Prove stable ordering and exactly one download per click. |
| Download one known document | `expect_download` with nested steps that trigger the click. Files pass through download tracking and per-task SHA-256 deduplication. |
| Handle an empty list | Prove the portal's explicit empty state in a synthetic fixture. A collection with no downloads can still finish as `failure` under current run-result semantics. |

For a ZIP transport, add `unpack: pdf` to the `download_all` options object.
The archive must contain exactly one member, including directory entries. The
member must be a regular file with a `.pdf` extension and a `%PDF-` signature.
This checks the transport type; it does not parse or repair the PDF document.
Absolute paths, empty/dot/parent components, backslashes, colons and control
characters are rejected. Safe subdirectories are allowed; only the member's
basename becomes the published filename. Symlinks and other special types,
encryption, unsupported compression, corrupt archives and CRC failures fail
before persistence. Only stored and deflated ZIP members are supported.
The ZIP transport is limited to 32 MiB and the uncompressed member to 64 MiB.
ZIP metadata reads are limited to 256 KiB before the member table is parsed.
The PDF stream is bounded too. The extracted bytes pass unchanged to the normal
save path, hash deduplication and optional notice identity. A rejected archive
saves no record and does not mark its collection key complete. Earlier saved
items remain saved. Without this option, downloads keep their current behavior.
The `unpack` option applies only to `download_all`. It is not supported in
`replacement_calendar.download_options`.

Collection actions cannot be graceful, nested under `expect_download`, or placed
in login phases. They use bounded, single-attempt execution. Later failure does
not undo prior saved records. Resume intentionally after checking partial effects.
For ordinary steps, three attempts can execute the full chain before a pause.
`graceful: true` means one attempt and continuation after a recorded failure.
Use it only for an optional control whose absence you have verified.

The current save path uses the suggested filename in the configured download
directory. A same-name file can be replaced. Test with isolated files; do not
claim collision-safe publication or archive delivery from a download result.

### Opt-in incremental downloads

The daemon supports `incremental: true` in `download_all` options (issue #50).
The default and `incremental: false` keep full acquisition. The legacy batch
runner rejects `incremental: true` before any click; it has no persistent keys.

Opt in only when each `key_attribute` value is stable, unique, and identifies
a notice that the portal never corrects in place. A constant button key or a
changing signed URL is not suitable. Keys do not detect content revisions.
Portals that can correct notices, including Bourse Direct, must fetch originals
and use `notice_identity` instead.

The daemon stores `<key_attribute>=<key>` in the nullable `Download.source_key`
column. Keys are scoped to the task and attribute. Old rows remain NULL; no
backfill occurs. Changing the task or attribute starts a separate key scope.
The download journal retains keys across recovery. Known keys are skipped
without clicking or comparing content. An all-known non-empty list completes
with `Run.result=success` and the explicit log `all items known`. Empty or
invalid lists still fail. No new control-protocol or result field is added.

The schema change is additive. Reverting this feature leaves the nullable
column and existing rows intact; older code can ignore them.

## Test without a real account

Start from a separate checkout. Install the development environment as described
in the README. Run from the repository root:

```bash
apps/.venv/bin/python -m pip install -r apps/requirements-dev.txt
apps/.venv/bin/python -m pytest tests/test_doc_recipe.py -q
```

Expected: the synthetic recipe passes schema/login validation and runs twice
against the loopback mock portal. Each run downloads the invoice and contract.
On the second run the per-task deduplication marks both as duplicates. The check
uses temporary database/profile/download paths, fake credentials and no vault
or archive consumer. The browser adapter runs headless. It does not prove the
Docker display stack, real TOTP fetching, portal account safety or a real
provider's selectors.

For a new recipe, add synthetic cases for session reuse, rejected login,
optional TOTP, changed selectors, empty lists, pagination, partial failure and
multiple PDFs as applicable. The existing `tests/test_bc_login.py` and
`tests/test_bc_collection.py` cover the generic action behavior.

The historical mock regression is a separate batch-engine compatibility check.
Run it in an isolated checkout without `--vault`. On a fresh legacy database,
initialize its schema first:

```bash
PYTHONPATH=apps apps/.venv/bin/python - <<'PY'
from BillCollectorServices_pw import DatabaseManager
from helpers import DB_FILE
manager = DatabaseManager(DB_FILE)
manager.conn.close()
PY
apps/.venv/bin/python tests/run_regression.py --ini tests/bc_regression.ini
```

Expected: `VERDICT: PASS`, seven service/account pairs and eight test downloads
cleaned up. This is not proof of daemon onboarding or a provider's live portal.
