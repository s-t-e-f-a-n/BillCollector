# PR #40 review: bounded replacement calendars (issue #37)

> Status: VALIDATED (2026-10-29) — S6 docs user-confirmed as-is (M2
> CHANGELOG entry, README bullet, doc/REPLACEMENT_CALENDARS.md as applied
> in S4); S5 all green on the exact dirty dev tree (companion 57 passed,
> full suite 633, regression PASS, ruff no delta, bandit +39 test-only
> B101, 15/15 recipes validate); deployment validation skip
> user-confirmed at the S5 gate. Next: S7 (commit + push: Gitea dev,
> promote main, mirror, PR close).

## PR metadata

- Author: flowcool; head branch `flowcool:feature/upstream-replacement-calendar-20261026`
- Head hash: `73acc023ba607970435d35ceee002d1064885b3e` (stable at S1;
  `git ls-remote github refs/pull/40/head` matches the local `refs/pr/40`)
- Base: `main` @ `ad18f7a85d70079072ed9b7ffde6bfff22f56c74` (current public
  tip); the branch itself starts from public main `d9362b3` (post-#31)
- Issue refs: #37 (bounded monthly-calendar traversal); integration
  dependency #34 (run-start date context) — already DELIVERED to main
- Created 2026-10-26T14:25:18Z; 1 feature commit; state open, mergeable clean
- Local state at review: Gitea `dev` `929fd41` (clean, == `origin/dev`),
  Gitea `main` `b693517`, GitHub `main` `ad18f7a`

## Verdict

**Approve** — with two maintainer-side doc-wording adaptations (M1, M2) as
S3 decision points. The PR implements the seven acceptance requirements
agreed on issue #37 (2026-10-27 decision) as a dedicated opt-in daemon
`replacement_calendar` action; no schema, control-protocol, exit-code, or
scheduler change; `click_until_absent` and existing `download_all` callers
untouched.

## Verified facts

- Merge base of `refs/pr/40` and `github/main` is `36a8d31` (PR #31 delivery
  test commit). The branch carries the sanitized public tip re-committed as
  `d9362b3` (orphaned public-history commit, skill flag) plus exactly one
  feature commit `73acc02`.
- The `d9362b3` diff vs the merge base is 88 files: the public CHANGELOG
  entry (already present in current `github/main` via the sanitized lineage)
  + 87 pure deletions of private agent-context files (`.kilo/` 49,
  `openwiki/` 32, `.vscode/` 2, `.github` 1, `.private`, `.openwikiignore`,
  `AGENTS.md`) — none present in current `github/main` → all comparison
  artifacts (fork-behind-base noise), skipped. No candidate file under a
  protected path.
- Actual feature content (`d9362b3..73acc02`): 9 files, +816/−11.
- Pre-image check vs Gitea `dev` `929fd41`:
  - clean pre-image (byte-identical to PR base or absent in both):
    `apps/billcollector/collection.py`,
    `apps/recipes_playwright/recipe-pw-schema.yaml`, and the three new files
    `apps/billcollector/calendar.py`, `doc/REPLACEMENT_CALENDARS.md`,
    `tests/test_bc_calendar.py`;
  - diverged (dev moved since `d9362b3` via #32/#33/#34/#35/#42/#39):
    `runner.py`, `BillCollectorServices_pw.py`, `README.md`, `CHANGELOG.md`
    — all PR hunks verified non-overlapping with the dev-side changes
    (see Integration plan).
- #37 acceptance (7 requirements, 2026-10-27 decision) verified point-by-
  point against the code:
  1. `click_until_absent` untouched (paginate path unchanged; `download_all`
     gained only two optional keyword-only params `deadline` /
     `before_download`, both `None`-defaulted, existing callers unaffected);
  2. per-calendar account + year/month binding with readiness + identity
     check — one DOM evaluation (`_READ`) binds account/year/month/readiness/
     items/empty to the same DOM revision; `account_id` mismatch, invalid
     month identity, or drift away from {expected, previous month} fails;
  3. month set from the run-start context + daemon TZ — `_months` derives
     inclusive months from `dates.date_from..dates.today` (the #34
     `DateContext`, whose `today`/`date_from` are plain `date` instances,
     matching the strict `type(...) is date` check); explicit empty months
     counted (`empty_selector`, listed in the result);
  4. offered controls only, bounded pages/items/time, stop on drift — only
     the recipe-declared `previous_selector` is clicked (count must be
     exactly 1); `max_months` ≤ 120 checked before any download;
     `max_items` counts items across months and is checked before the next
     month's downloads; one shared monotonic deadline from
     `download_options.timeout_ms`;
  5. collect before leaving — each month is fully collected
     (`download_all` + post-`guard()`) before the previous control is
     clicked; a per-item `before_download` guard re-verifies identity +
     content stability before every item dispatch;
  6. persisted downloads survive later failure — reuses the #33
     `download_all` persistence contract (staged publication, durable row
     before publication); operator resume is an explicit new invocation that
     skips completed keys scoped per (step, account, key attribute, year,
     month) via `ctx.calendar_completed_keys`;
  7. no scheduler change — `runner.py` only adds the method to
     `_COLLECTION_METHODS`, `transform_step_to_json`'s action list, and
     `_collection_actions`; the legacy batch runner refuses the action
     explicitly (`method_name not in collection_actions` → step failure
     "unavailable in this runner", proven by a test).
- Interface-shape open point from the #37 decision (generic bounded
  traversal vs. dedicated calendar action, not pre-selected): the PR picks
  the dedicated action. Calendar semantics (account identity, month
  binding, explicit empty months, previous-control navigation) are
  calendar-specific; a generic traversal would push them to every caller.
  Within the agreed acceptance surface — acceptable.
- PR body claim "On public main, the daemon has no date context yet. The
  action refuses execution until that prerequisite is integrated": verified
  — `collect_calendar` receives `dates=getattr(getattr(ctx, "bcs", None),
  "date_context", None)` and `_months` raises `CollectionError('calendar
  requires a valid run-start date context')` for `None`. On dev (post-#34)
  the context is supplied at runner.py:1094, so the action is live there.
- Schema mirrors the runtime `validate_options` exactly (10 required
  fields, `additionalProperties: false`, `max_months` 1–120,
  `download_options` reuses the `downloadAllMethod` item schema by `$ref`,
  optional `month_names` of 12 unique names); the method is added to both
  terminal-method enums, the `method` oneOf, the collection-action oneOf,
  and excluded from `playwrightMethod`'s `not: enum`.
- Redaction: Playwright errors are re-raised as
  `CollectionError('calendar browser operation failed') from None` (no DOM
  text, selectors, or provider URLs in the error); canary tests
  (`SENSITIVE-ACCOUNT-CANARY`, `???SENSITIVE-SELECTOR-CANARY`) assert the
  absence of sensitive values in raised errors.
- Process check (CONTRIBUTING.md): issue referenced (#37); intended
  behavior + verification stated; proof shipped (pytest commands + expected
  counts: 56 passed/2 skipped on public main, 57/1 with #34, full candidate
  suite 485 passed/4 skipped); AI assistance disclosed (Codex); no secrets
  in code, tests, or artifacts (all fixtures synthetic, `calendar.invalid`,
  in-memory fulfillments, the fixture asserts `not data.denied` on
  teardown); no new network exposure; shared interface (recipe contract)
  agreed in #37 before code; no DB schema / control protocol / exit-code
  change.

## Code review findings

- `calendar.py` (new, 217 lines): bounded descending traversal; one shared
  deadline; `wait_ready` tolerates "Execution context was destroyed"
  Playwright errors (navigation destroys the context and proves no
  completion) but not closed pages/invalid selectors; ambiguity guards
  (duplicate root, hidden items, keys+empty simultaneously); empty-month
  stability double-check via a second snapshot; item budget decremented by
  the offered key count per month.
- `collection.py`: `COLLECTION_ACTION_METHODS` gains the new method (so
  `validate_terminal_action` treats it as terminal); `download_all`'s
  `deadline` clamps the per-month budget to the calendar's shared deadline
  (`min`), and `before_download()` runs per item after the list-stability
  and per-item key re-checks, before dispatch.
- `runner.py`: closure passes `ctx.page`, `ctx.context`, the recipe
  locator as root, the run's `save_download`, the #34 date context, and the
  step-scoped resume dict (`id(step)`).
- Tests (382 lines, ~20 tests): traversal with equal and decreasing item
  counts (the cumulative-growth proof gap named in the PR body), explicit
  empty month, same-tab document restore, single-month window (no previous
  click), named months (French) + ambiguous root, browser-error redaction,
  five fault injections with committed-file survival + no resend, item and
  month budget refusals, detachment-is-not-success, wrong initial account,
  drift during download, filename-collision contract preserved,
  `RunInterrupted` propagation, operator resume with month-scoped key cache
  (incl. repeated keys across months), batch-runner refusal, TZ-controlled
  inclusive months (`Europe/Zurich`, `DateContext.capture`), pre-browser
  input validation, and five unsafe recipe shapes refused by schema
  validation. No secrets; no external contact.

## Risks

- `runner.py` manual application: three hunks re-anchored over dev's #34
  date wiring and #39 login changes; S4 preflight re-runs the pre-image
  checks and S5 validates the exact tree.
- Strict `type(...) is date` in `_months` would break if #34's `DateContext`
  ever subclasses `date` — it does not today; noted, no action.
- `test_run_start_timezone_controls_inclusive_months` carries a skip reason
  mentioning "upstream date-context PR #34" — runs on dev (the module
  exists); wording is stale post-integration (test comment only, no
  functional impact).
- CHANGELOG entry references "PR #34" (a PR number) where repo convention
  uses issue numbers (#34's issue is #26) — M2.

## Integration plan (S4, on Gitea `dev`)

| File | Action |
|---|---|
| `apps/billcollector/calendar.py` | apply from head (new) |
| `apps/billcollector/collection.py` | apply from head (clean pre-image) |
| `apps/recipes_playwright/recipe-pw-schema.yaml` | apply from head (clean pre-image) |
| `tests/test_bc_calendar.py` | apply from head (new) |
| `doc/REPLACEMENT_CALENDARS.md` | apply from head (new) + M1 currency fix |
| `apps/billcollector/runner.py` | manual: 3 hunks (frozenset, `transform_step_to_json` list, `_collection_actions` closure) — non-overlapping with dev changes |
| `apps/BillCollectorServices_pw.py` | manual: 4 hunks (nested set, graceful set, dispatch set, availability guard) — non-overlapping with dev's top-of-file changes |
| `README.md` | manual: append the replacement-calendar sentence to the Bounded-pagination bullet (dev line 330); adjacent to dev's date-variables bullet, no overlap |
| `CHANGELOG.md` | manual: merge entry into `## [Unreleased] / ### Added` with M2 wording |

Skip: `d9362b3` re-commit content (already present / comparison artifacts,
87 private-file deletions).

M1 (doc currency, maintainer-side): `doc/REPLACEMENT_CALENDARS.md` — the
header note "Integration requires the date-context change in upstream PR
#34. Public main does not yet provide that context" is stale (#34 is on
main); reframe the fork-perspective sentences ("The fork's daemon supports",
"Install the fork's pinned runtime", "This feature is a local fork
implementation") into upstream-perspective wording.

M2 (CHANGELOG wording, maintainer-side): the PR's entry "Opt-in daemon
`replacement_calendar` action for bounded monthly traversal. Requires the
run-start date context from PR #34 and interface agreement in #37." —
rewrite with issue numbers and present tense (e.g. reference issues #37 +
#26; state the action is opt-in and refused by the legacy batch runner).
Final wording confirmed in S6.

## Validation plan (S5, from repo root, venv, on the exact dev tree)

- PR tests: `apps/.venv/bin/python -m pytest tests/test_bc_calendar.py -q`
  → expected all passed (33 test cases after parametrization; the TZ test
  runs, not skips, on dev).
- Companion suite from the PR body: `apps/.venv/bin/python -m pytest
  tests/test_bc_calendar.py tests/test_bc_collection.py -q` → all passed.
- Full regression: `apps/.venv/bin/python tests/run_regression.py --ini
  tests/bc_regression.ini` → exit 0 (7 scenarios / 8 PDFs, VERDICT: PASS).
- ruff (F821, E4/E7/E9) + bandit on the changed files → nothing new beyond
  the known baseline (B608 dynamic SQL table names, B104 UI bind).
- Recipe validation: all bundled recipes still validate against the updated
  `recipe-pw-schema.yaml` (no bundled recipe uses the new action).
- Scope: full block — the action is daemon runtime code (no
  recipe-only reduction applies; it adds a new recipe method).

## Deployment validation

Recorded as **not deployment-relevant**: the PR touches no `Dockerfile`,
`.dockerignore`, `BillCollector.sh`, `install_docker-image.sh`,
`deploy_remote.sh`, Compose service, INI keys, or `.env` handling.
`BillCollectorServices_pw.py` changes are method-set literals + a
guard in step processing (no launch flags, profile, or sandbox behaviour).
New behaviour is opt-in per recipe. User confirmation of this skip is
requested at the S5 gate before S7 may commit/push to `main`.

## Out of scope

- #38 notice identity / revision handling (PR #41, HELD).
- F10/C8 delivery-state exposure (#24 point 2) — the archive side of the
  download contract; the calendar action reuses the existing persistence
  contract as-is.
- Provider qualification of real portal calendars (doc states selectors
  must be qualified before real use).

## Open questions

- New PR #44 (C3: validate daemon recipe method chains before runtime
  access) arrived after the chain addendum; it is a separate sequencing
  decision (no code dependency on #40; regional overlap in the
  method-chain-validation area only, re-checked by #44's own S1).

## Execution log

- 2026-10-29 S3: proposal presented and confirmed **as-is** (user gate
  passed). The S3 proposal restated the S2 integration plan: apply 5 files
  byte-identical from head `73acc02` (incl. `doc/REPLACEMENT_CALENDARS.md`
  + M1), apply the 7 hunks on the 3 diverged files, skip the `d9362b3`
  re-commit, and merge the M2 CHANGELOG entry at the top of Unreleased
  `### Added` (newest-first). S7 commit split confirmed: feat (calendar.py,
  collection.py, runner.py, BillCollectorServices_pw.py,
  recipe-pw-schema.yaml) + test (test_bc_calendar.py) + doc (CHANGELOG,
  README, doc/REPLACEMENT_CALENDARS.md). Head re-verified unchanged
  (`git ls-remote github refs/pull/40/head` == local `refs/pr/40` ==
  `73acc02`).
- 2026-10-29 S4: integration applied. Preflight green on dev `ee6e532`:
  clean tree; remote head == local `refs/pr/40` == `73acc02` (unchanged
  since S1); pre-image re-checks clean (collection.py + schema
  byte-identical to PR base `d9362b3`; calendar.py, test_bc_calendar.py,
  doc/REPLACEMENT_CALENDARS.md absent on dev; the 4 diverged files
  re-confirmed). Applied from PR head, verified byte-identical to head
  (`git hash-object` == `refs/pr/40:` blob): `apps/billcollector/calendar.py`
  (new), `apps/billcollector/collection.py`,
  `apps/recipes_playwright/recipe-pw-schema.yaml`,
  `tests/test_bc_calendar.py` (new), `doc/REPLACEMENT_CALENDARS.md` (new,
  then M1 applied). Hunk patch `git diff d9362b3..refs/pr/40` on
  `runner.py` (3), `BillCollectorServices_pw.py` (4), `README.md` (1)
  applied via `git apply --check` then `git apply`; the added/removed lines
  of each working-tree diff were verified equal to the PR diff. M1: 4
  fork-perspective edits to the new doc (header note, "The fork's daemon"
  sentence, "fork's pinned runtime", final paragraph). M2: the confirmed
   CHANGELOG `### Added` entry (issue #37 / #26, present tense, legacy
   runner refusal) inserted at the top of the Unreleased Added list. Working
   tree left dirty (uncommitted) for S5 to validate the exact content.
   Status: INTEGRATING.
- 2026-10-29 S5: code checks all green on the exact dirty dev tree (S4
  applied, pre-commit; dev doc tip `e89aee8`, head `73acc02` unchanged).
  PR companion suites: `pytest tests/test_bc_calendar.py
  tests/test_bc_collection.py -q` → **57 passed, 1 skipped in 33.71 s**
  (the skip is the pre-existing `BILLCOLLECTOR_BROWSER_TESTS=1`-gated
  loopback Chromium smoke in test_bc_collection.py:860, not a calendar
  test; matches the PR's claimed "57/1 with #34"). Full suite: `pytest
  tests/ -q` → **633 passed, 10 skipped, 53 subtests passed in 469.77 s**
  (dev baseline 600 + the 33 new calendar cases; the 10 skips are
  pre-existing environment-gated skips). Full regression:
  `run_regression.py --ini tests/bc_regression.ini` → **exit 0, VERDICT:
  PASS** (7 scenarios / 8 PDFs, downloads 8/8; the designed failing pairs
  return the expected `BillCollector exit semantics: 1`). Ruff (repo
  `ruff.toml`) on the 5 changed Python files: working-tree finding set is
  **identical to the dev baseline** (40 pre-existing findings, all in
  BillCollectorServices_pw.py; calendar.py, collection.py, runner.py,
  test_bc_calendar.py clean) — nothing new. Bandit on the same files:
  delta vs. baseline is exactly **+39 `B101 assert_used`, all in the new
  `tests/test_bc_calendar.py`** (test-only idiom, synthetic data — same
  pattern as PR #39's +22); the pre-existing B608 (SQL, services) and B110
  (try-except-pass, runner) findings are unchanged. Recipe validation:
  all **15 bundled recipes** pass `recipes.validate_recipe` against the
  updated `recipe-pw-schema.yaml`; **none** uses `replacement_calendar`.
  Deployment validation: recorded skip (not deployment-relevant, see the
  Deployment validation section; the trigger check still holds — the S4
  tree touches no Dockerfile/.dockerignore/BillCollector.sh/
  install_docker-image.sh/deploy_remote.sh/INI keys/.env handling).
- 2026-10-29 S5: gate passed — the recorded deployment-validation skip
  was user-accepted (timestamp 2026-10-29, S5 gate), satisfying the S7
  prerequisite for the exact dirty dev tree (dev `03da883` doc tip;
  integration files uncommitted). Status: VALIDATED. Next: S6
  (documentation).
- 2026-10-29 S6: documentation gate passed — the S6 doc set was
  user-confirmed **as-is**: the M2 CHANGELOG `### Added` entry (issue
  #37 + #26, present tense, opt-in, legacy batch runner refusal) at the
  top of `## [Unreleased]`, the README bounded-pagination bullet sentence
  linking `doc/REPLACEMENT_CALENDARS.md`, and the new
  `doc/REPLACEMENT_CALENDARS.md` (PR head content + the M1
  upstream-perspective reframe applied in S4). CONTRIBUTING.md verified:
  no method-list or contributor-rule change required. No further doc
  edits made; the tree is unchanged since the S6 presentation. Status:
  VALIDATED. Next: S7 (commit + push: Gitea dev, promote main, mirror,
  PR close).
