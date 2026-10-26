# Recipe method contract

The supported method surface of the daemon recipe runner. This is the
contract that recipe validation hardening (finding F08 of the product
audit, issue #27) implements against: validation must reject unknown
methods, invalid argument names/types and unsupported variables before
vault or browser access, without rejecting intentionally supported
Playwright calls.

Evidence: the dispatch loop in `apps/billcollector/runner.py`
(`_process_step`), the reserved-method handlers in `runner.py` and
`apps/billcollector/login.py`, the bounded collection actions in
`apps/billcollector/collection.py`, the schema
`apps/recipes_playwright/recipe-pw-schema.yaml`, and the shipped recipes
in `apps/recipes_playwright/`.

## 1. Document and step shape

The recipe document is validated by `apps/recipes_playwright/recipe-pw-
schema.yaml` (jsonschema, Draft 7):

```yaml
services:
  - serviceName: <string, required>     # one service per task recipe
    description: <string, optional>
    steps: [<step>, ...]                # required, executed in step-number order
```

A step:

```yaml
- step: <integer, required>             # ordering key (steps sort by it)
  description: <string, optional>       # shown in logs, pause prompts, UI
  graceful: <boolean, optional>         # true: failure is recorded, run continues
  methods: [<method entry>, ...]        # the executed method chain
  steps: [<nested step>, ...]           # only under expect_download and in login preparation
  submit: <step>                        # login only
  phases: [<phase>, ...]                # login only
```

A method entry:

```yaml
- method: <string, required>            # a Playwright method name or a reserved name
  arguments: [{<key>: <value>}, ...]    # optional; list of single-key dicts
```

Argument value types (schema): string, boolean, number, object, null.
The `arguments` list is the recipe's uniform argument form: each element
is one key/value pair. At execution the runner merges the elements into
keyword arguments (when every element is a dict) or passes them
positionally (otherwise); the merged kwargs are what the Playwright
method receives.

## 2. Dispatch model (the Playwright surface)

The runner walks a step's `methods` in order. The chain starts on the
`Page`; each method is resolved by attribute lookup on the current chain
object (`getattr(previous_result, method_name)`):

- a callable is invoked with the processed arguments; if it returns a
  value the chain continues on that value (e.g. a locator), otherwise on
  the same object;
- a non-callable attribute is read as a property (no arguments allowed).

Therefore the supported Playwright surface is the **public API of the
pinned Playwright version** (`playwright==1.63.0`, `apps/requirements.txt`)
reachable through the chain that starts on a `Page`: the public
methods and properties of `playwright.sync_api.Page`, and of every type
a chain call can return - `Locator`, `Frame`, `FrameLocator` and
`ElementHandle` - each of whose own calls may continue the chain (the
shipped test recipes use `locator` -> `content_frame` -> `get_by_label`
-> `click`, which moves the chain onto a `Frame`). This is open by
design: a locator chain such as `get_by_role` -> `first` -> `filter` ->
`get_by_label` -> `click` is valid, and new Playwright API added by a
version bump stays supported automatically.

Five method names are **reserved**: the runner intercepts them before
Playwright dispatch and they are never passed to the browser API:
`login`, `wait_user`, `expect_download`, `click_until_absent`,
`download_all`. Their exact contracts are in section 3.

A method name that is neither reserved nor a public attribute of the
chain object's type fails at execution with `Method '<name>' not found
on <type>`. Validation (F08) must reject such names **before** vault
and browser access, deriving the allowlist by introspecting the pinned
Playwright package (not a hand-maintained list), so intentionally
supported Playwright calls are never rejected. Re-derive when the pin
changes.

Methods the shipped recipes actually use (compatibility baseline,
section 5): `click`, `close`, `fill`, `first`, `goto`, `locator`,
`get_by_role`, `get_by_label`, `get_by_text`, `get_by_title`,
`get_by_placeholder`, `get_by_test_id`, `press`, `content_frame`,
`expect_download`, plus `wait_user` (test recipes) and `login` (the
safe-login candidate).

## 3. Reserved methods

### `login` (phased login, contract in doc/SAFE_LOGIN.md)

Standalone: a step whose single method is `login`, non-graceful,
top-level only (not nested under `expect_download`), at most one per
task recipe.

Arguments: one flat options object (list of single-key dicts with
unique keys):

| key | type / constraint | required |
|---|---|---|
| `success` | locator dict, see below | yes |
| `max_failures` | integer >= 1 (default 2) | no |
| `timeout_ms` | integer >= 1 (default 10000) | no |
| `session_timeout_ms` | integer >= 1 (default 1000) | no |

`success` is a locator dict with exactly one locator key - `role`,
`test_id`, `placeholder`, `label`, `text` or `selector` - whose value is
a non-empty string. Allowed extra keys: `exact` (all locator keys except
`selector` and `test_id`) and, for `role`: `name`, `checked`, `disabled`,
`expanded`, `include_hidden`, `level`, `pressed`, `selected`.

Structure: the step carries either the single-phase shorthand
(`steps` preparation + `submit`) or `phases` (a list of `{steps?,
submit, success}`; the last phase's `success` must equal the login
`success`; `phases` cannot mix with top-level `steps`/`submit`).
Preparation steps are locator chains ending in `fill`; `submit` is a
locator chain ending in `click` or `press` (argument `key: Enter`, or
the positional single-argument form `"Enter"`). The non-terminal
methods of these chains are restricted to the locator set
(`login.py::LOCATORS`): `locator`, `get_by_role`, `get_by_text`,
`get_by_label`, `get_by_test_id`, `get_by_placeholder`,
`get_by_alt_text`, `get_by_title`, `first`, `last`, `nth`, `filter`,
`content_frame` - narrower than the general Playwright surface of
section 2. Execution semantics (budget, pause/resume, blocking) are
defined in doc/SAFE_LOGIN.md.

### `wait_user`

Step-level: when any method of a step is `wait_user`, the whole step is
the wait (no other methods of the step execute). The step pauses before
execution (pause reason `wait_user`) and is consumed on resume - never
re-executed (a consumed CAPTCHA code cannot be re-entered).

Arguments (all optional):

| key | type / constraint |
|---|---|
| `prompt` | string; the pause prompt (default: the generated step prompt) |
| `until` | locator dict, see below |

`until`: the first key present selects the Playwright locator - `role`
-> `get_by_role`, `test_id` -> `get_by_test_id`, `placeholder` ->
`get_by_placeholder`, `label` -> `get_by_label`, `text` -> `get_by_text`,
`selector` -> `locator` - and the whole dict is passed as its kwargs.
With `until`, the step completes only once the locator is visible,
bounded by the pause deadline; a missed deadline re-pauses with the same
prompt.

### `expect_download`

Marks the step as a download step; no arguments. The step's method chain
executes up to the `expect_download` entry, then the step's nested
`steps` execute inside a `page.expect_download()` window; every
downloaded file goes through download tracking (sha256, per-task dedup,
consumer hook). A nested-step failure pauses the run (reason
`download_failed`) with a resume retry; cancel/timeout abort.

Constraint: bounded collection actions (`click_until_absent`,
`download_all`) cannot appear nested under `expect_download` or in
login phases.

### `click_until_absent` (bounded collection, PR #19)

Chain shape is exactly two methods: one page locator, then the action.
The locator must be one of: `locator`, `get_by_role`, `get_by_label`,
`get_by_text`, `get_by_title`, `get_by_placeholder`, `get_by_test_id`.

Arguments: exactly one object:

| key | type / constraint | required |
|---|---|---|
| `progress_selector` | non-empty string (CSS selector of the rows whose visible count must grow) | yes |
| `max_clicks` | integer 1..100 | yes |
| `timeout_ms` | integer 1..120000 | yes |

Semantics: clicks the live control while it is visible; after every
click the visible count of `progress_selector` must increase; a visible
disabled control is not completion (Playwright actionability wait);
fails closed when the click budget or total timeout is exhausted or the
control matches more than one element. Non-graceful, single attempt,
cannot be nested.

### `download_all` (bounded collection, PR #19)

Chain shape is exactly two methods: one page locator from the same seven
methods, then the action.

Arguments: exactly one object:

| key | type / constraint | required |
|---|---|---|
| `key_attribute` | non-empty string (HTML attribute holding the stable item key) | yes |
| `max_items` | integer 1..200 | yes |
| `timeout_ms` | integer 1..600000 | yes |
| `event_window_ms` | integer 1..10000, and < `timeout_ms` | yes |

Semantics: the initial ordered key snapshot is the contract for the
whole action; the list is re-read after every click and the selected
element re-checked before use - shrink, reorder, replacement, duplicate
or empty keys, and ambiguous controls fail closed. Exactly one file per
click within the event window; popups are captured and closed; the
listing is restored after a navigating download. Persisted records stay
committed when a later item fails. Non-graceful, single attempt, cannot
be nested.

## 4. Variables

Supported placeholders (exact-string substitution of argument values,
recursing into nested dicts and lists; every other string passes
through unchanged):

| placeholder | resolution |
|---|---|
| `{{USERNAME}}` | the task's username from the vault item |
| `{{PASSWORD}}` | the task's password from the vault item |
| `{{OTP}}` | a fresh TOTP fetched from the vault **at substitution time** (TOTP codes go stale; fallback: the run-start credential when the item has no TOTP or the fetch fails) |

Substitution is exact-match on the whole value: a string is substituted
only when it equals a placeholder exactly, so a longer string containing
a placeholder is not substituted. Validation (F08) must therefore reject
any `{{...}}` sequence other than the three supported placeholders -
including one embedded in a longer string, which would otherwise reach
the portal unchanged.

## 5. Validation requirements (F08)

Gate: the daemon runner already validates the recipe before display
allocation, vault preflight and browser launch (`CheckRecipe` schema
check + `validate_login_recipe` in `runner.py::_run_task`); the UI
validates on load and on save (`apps/billcollector/recipes.py`). The
hardening lands in these same gates (`validate_recipe` / the schema /
`validate_login_recipe`), so a rejected recipe never reaches vault or
browser access.

Already enforced by the existing gates (keep): the schema rejects
unknown top-level keys, missing `serviceName`/`steps`/`step`, non-
integer step numbers, wrong argument value types, the collection
action chain shape (exactly `[page-locator, action]`, `graceful:
false`, no nested `steps`), the collection action argument names,
types and ranges (section 3 tables), and the `phases` block shape;
`validate_login_recipe` rejects a non-standalone, nested or
multi-per-recipe `login`, `submit`/`phases` outside a login block, the
login locator-chain terminal rules, and all section-3 `login`
argument violations.

F08 must additionally reject, before vault/browser access:

- a `method` name that is not a reserved name (section 3) and not a
  public attribute of the chain object's type in the pinned Playwright
  version (allowlist by introspection, section 2) - for ordinary
  steps; for login chains, a non-terminal method outside the section-3
  locator set;
- `wait_user` argument violations: unknown argument names, and an
  `until` that is not a locator dict or has no recognized locator key
  (today silently ignored or failing only at execution);
- unsupported variables (any `{{...}}` sequence other than section 4,
  including one embedded in a longer string).

Report: every validation error must name the service (`serviceName`)
and the step (`step` number) - plus the method name where applicable -
so an operator or contributor can fix the recipe from the message
alone.

Compatibility: the hardening must keep validating, unchanged, the seven
shipped provider recipes (`1und1`, `buhl`, `datev`,
`freenet_mobilfunk`, `kabeldeutschland`, `nuernberger`, `winsim`), the
eight test recipes (`test*`), and the doc/SAFE_LOGIN.md candidate
recipe.

## 6. Versioning and change control

- The Playwright surface is pinned by `apps/requirements.txt`
  (`playwright==1.63.0`); the introspected allowlist is only as valid as
  the pin. A pin bump is a contract change: re-derive the surface and
  re-run the compatibility baseline.
- Adding a reserved method is a contract change: extend this document,
  the schema, the dispatch loop and `validate_recipe` in one change.
- This document describes the daemon runner only; the historical batch
  runner is unchanged by it.
