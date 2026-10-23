# PR #19 review — bounded Playwright collection actions

> Status: AWAITING-DECISION (2026-10-23) — S3 done: rebase-request comment
> posted on #19 (`6373943417`, 2026-10-23T20:20:28Z, exact text user-
> confirmed as is). Waiting on the author's rebase onto `42d4337` + un-draft
> (Path A per the #18 agreement); when the head moves, a new session re-runs
> S1 on the new head before any integration.

## PR metadata

- PR: #19 on `s-t-e-f-a-n/BillCollector` (public mirror), open, **draft**
  ("draft until the recipe-contract decisions in #18 are confirmed" — the
  decisions are confirmed, un-drafting is the author's move)
- Title: feat: add bounded Playwright collection actions
- Author: flowcool; created 2026-10-20T12:43:19Z, updated 2026-10-23T06:41:27Z
- Head: `13d002cfcda2bf095cbe279dbef64f14d99e783d`, branch
  `feature/playwright-collection-analysis` (flowcool/BillCollector);
  re-verified unchanged by `git ls-remote` 2026-10-23 (S2)
- GitHub base ref: `main` (`42d4337`, the PR #22 delivery mirror); merge-base
  with `github/main`: `baa4046` (2026-10-19)
- Issue refs: #18 ("Agree bounded Playwright collection actions for
  pagination and multi-download"), still open; the PR body says "Closes #18".
  Maintainer agreement comment on issue #18 posted 2026-10-22T22:03:11Z:
  **all five contract decisions accepted** (two actions not one composite;
  required stable `key_attribute`; full per-item event window with runtime
  validation against the explicit deadline before the first side effect;
  duplicate suggested filenames fail before overwrite; implementation
  ownership — a focused PR against the then-current `main`). Sequencing note:
  start with PR #22 first (done, DELIVERED 2026-10-23), then "rebase onto the
  then-current `main` and I'll review it after". The head has **not** been
  rebased since (still on the `baa4046`-era base).
- AI disclosure: Codex implemented and reviewed under the contributor's
  direction; Claude Code and CodeRabbit supplied external review findings,
  each checked against the reviewed SHA before a fix (CONTRIBUTING.md
  disclosure satisfied).
- GitHub diff stats (inflated by the orphaned recommit): 79 files,
  +1933/−15199. Real author change (`4508909..13d002c`): 7 files,
  +1861/−19.
- PR body evidence (claimed at head `13d002c`): `pytest -q` 324 passed,
  3 skipped, 37 subtests passed; Chromium loopback collection suite 25
  passed; `run_regression.py` 7 accounts / 8 files VERDICT PASS; scoped
  ruff, `py_compile`, bandit on the new module + `git diff --check` pass
  (wider bandit: only pre-existing B608/B110 in the legacy runners).

Local state at review time (S1 2026-10-23, re-verified at S2):

| ref | tip |
|---|---|
| Gitea `dev` | `d6a695da56af6359209181df2c514c47bf4e32a0` |
| Gitea `main` | `9d8ebcfea9539e6a107e2502811a928a6cfa6665` |
| GitHub `main` | `42d4337874afb9db0e4a1e491dc0e52df9da656a` |

Cross-PR: no other open PR on the mirror at S2 (only #19); no ordering
dependencies. PR #22 (the #20 contract, which this PR's sequencing waits on)
is DELIVERED (see `completed/1792708132014-pr22-safe-login-review.md`), so
the #18 precondition "rebase onto the then-current main" is actionable now.

## Verdict

**Approve with maintainer changes.**

The implementation matches the agreed #18 contract on all five decisions,
the safety properties in the PR body hold in code, and the test bar (unit
contract suite + opt-in loopback Chromium smoke + the existing regression
command) is the one the maintainer named in #18. Maintainer-side changes:

1. CHANGELOG entry — the author shipped none (see S6).
2. Conflict resolutions — required only on fallback path B (the dev drift
   since the merge base); fully specified below.
3. Optional nit N1 (generalize the nested-guard error message for login
   phases) — user's call at S3.

Blocker before S3: the head is not rebased onto the then-current `main`
(`42d4337`) as the #18 agreement requires. Two paths, user chooses:

- **Path A (recommended, matches #18):** ask the author to rebase onto
  `42d4337` and un-draft. Then the head moved → re-run S1 on the new head
  (failure mode: head moved after S1). Because Gitea `dev` = `main` + two
  doc-only `.kilo/` commits, a rebased head should apply to `dev` with no
  conflicts (S4 preflight re-verifies the pre-images).
- **Path B (fallback):** integrate the reviewed head `13d002c` as-is via the
  manual resolutions in the integration plan below.

## Verified facts

- `refs/pr/19` fetched from GitHub; head `13d002c` matches the remote ref
  (S2 re-check via `git ls-remote`).
- The PR branch is a resubmission on an orphaned sanitized base: commit 1
  `4508909` ("docs: changelog, readme: document the self-hosted daemon and
  web UI") is a recommit of the public lineage that strips the 71 private
  files (`.kilo/`, `.private/`, `.vscode/`, `openwiki/`, `AGENTS.md`,
  `.openwikiignore`, `.github/workflows/openwiki-update.yml`) and rewords
  CHANGELOG/README for the public mirror. `4508909` is **not** an ancestor
  of current `github/main` (`42d4337`) — orphaned after the sanitization
  re-commit, same pattern as PR #22. The 72 deletions in the full-range
  GitHub diff are comparison artifacts (private paths already absent from
  the current `github/main` tree) and are never applied.
- Real author change (`4508909..13d002c`, three commits
  `e535bce` → `5df5d3c` → `13d002c`) touches exactly 7 files, no private
  paths, no CHANGELOG entry.
- Pre-image check vs Gitea `dev` (`d6a695d`):
  - New files, clean apply: `apps/billcollector/collection.py`,
    `tests/test_bc_collection.py`.
  - Diverged (all 5 overlapping files changed on dev since `baa4046`,
    +406/−98 — the safe-login work + docs): `README.md`,
    `apps/BillCollectorServices_pw.py`, `apps/billcollector/recipes.py`,
    `apps/billcollector/runner.py`,
    `apps/recipes_playwright/recipe-pw-schema.yaml`.
  - Empirical `git apply --3way` of the author diff on a scratch dev tree:
    2 files added cleanly, 5 files conflicted (`UU`), 18 conflict-marker
    lines total (README 302/313/325; BillCollectorServices_pw.py
    14/16/18; recipes.py 134/136/138; runner.py 634/636/643 and
    791/796/801; recipe-pw-schema.yaml 47/67/123).
- The PR's `_RunContext` attributes, `collection_actions` parameter,
  `transform_step_to_json` list and the `_process_step` call site all
  auto-merge on the dev tree; only the 5 hunks above conflict (characterized
  in the integration plan).
- No INI keys, `.env` handling, DB schema, control protocol, or exit-code
  changes; no new network exposure (browser-side actions only, loopback in
  tests); no secrets in code, tests, or artifacts.

## Code review findings

`apps/billcollector/collection.py` (new, 453 lines) — the shared
browser-sensitive core, used by both recipe runners:

- `click_until_absent(page, control, options)`: options validated strictly
  (unknown keys rejected; `progress_selector` non-empty string;
  `max_clicks` 1–100; `timeout_ms` 1–120000). Live control state per
  iteration (`absent`/`hidden` = complete; >1 match = fail). Progress proof
  is a visible-count `evaluate_all` (display/visibility/size), so
  page-replacement pagination and virtualized lists — which do not increase
  the visible count — fail closed as contracted. A visible disabled control
  is not completion: the click raises, state is re-checked, and the action
  fails with "not actionable". Hard monotonic deadline bounds the whole
  action; a stall retries at 50 ms until progress or the deadline.
- `download_all(page, context, locator, save_download, options, *,
  completed_keys)`: options validated (unknown keys rejected;
  `key_attribute` non-empty; `max_items` 1–200; `timeout_ms` 1–600000;
  `event_window_ms` 1–10000 and `< timeout_ms`). The initial ordered key
  snapshot must be non-empty, within `max_items`, all non-empty and unique.
  `_require_event_budget` enforces the decision-3 runtime check: before any
  side effect the remaining items × `event_window_ms` must fit under the
  deadline with surplus, and it is re-checked before every item (a slow
  persistence, a slow list restore, or a slow `element_handle` cannot
  consume future event windows). Per item: the list must re-read identical
  to the snapshot (shrink/reorder/replacement fail closed); the element
  handle's key attribute is re-checked immediately before the click; the
  click observes the **full** per-item event window (capped by the total
  deadline) — ending early would mis-attribute a delayed second event to the
  next control; exactly one download is required (0 or ≥2 fail closed);
  popups are captured via the context `page` event with per-popup download
  listeners; a navigation away from the listing is restored with
  `go_back` on the remaining budget; listener/popup/handle cleanup never
  masks the primary error, and `RunInterrupted` always wins over cleanup.
  `completed_keys` implements the contracted operator resume: stable keys
  already persisted for the step are skipped; successful records stay
  committed when a later item fails.

`apps/billcollector/runner.py` (daemon runner):

- `_COLLECTION_METHODS` + `_collection_methods_in(step)`. `_execute_step`:
  collection steps are **single-attempt** (no generic three-attempt replay
  after partial side effects) and rejected when nested
  (`parent_step is not None`) with a `StepAbortError`.
- `_process_step(..., collection_actions=None)`: `validate_collection_chain`
  preflights the whole step before any method executes (a malformed
  collection step fails before an earlier method's side effect);
  `graceful: true` on a collection step is rejected; dispatch requires a
  locator prefix (page-level call fails), exactly one options object, and
  the adapter; `RunInterrupted` re-raised, other exceptions → `fail_step`.
- `_collection_actions(ctx, step)`: runner adapters; `save_download` routes
  through `downloads.track_download` (sha256 dedup + consumer hooks) and
  fails on a suggested filename already saved earlier in the run (decision 4
  — no silent overwrite); completed keys are kept per step identity so a
  resume re-enters with the same set.
- `_execute_step_with_pause`: single-attempt wording for collection steps in
  the pause prompt.

`apps/billcollector/recipes.py`: both actions added to
`_CHAIN_END_METHODS` (chain-replacement validation sees them as terminals).

`apps/BillCollectorServices_pw.py` (legacy batch runner): same terminal
dispatch (locator prefix, one options object, adapter), same preflight and
graceful rejection, `nested=True` flag enforces the no-nesting rule for
`expect_download` children, duplicate-filename guard, and a
`service_aborted` flag so a partial collection finalizes the service run as
`failure` with the persisted files still recorded in `download_info`.

`apps/recipes_playwright/recipe-pw-schema.yaml`: `method` becomes a `oneOf`
(`playwrightMethod` — which now explicitly excludes the two names — plus the
two new method definitions); nested steps under `expect_download` use a new
`nestedStep` definition that forbids the collection methods; an `allOf`
constraint on `step` enforces: a step containing a collection action has
exactly `[locator, collectionAction]`, `graceful` const `false`, and no
nested `steps`. All schema bounds mirror the code constants
(100/120000; 200/600000/10000).

`README.md`: three bullets documenting the contract — sanitized,
public-safe wording, no private details.

`tests/test_bc_collection.py` (new, 999 lines): offline contract suite
(pagination states, disabled control, stall/bound exhaustion, snapshot
validation, budget exhaustion before any click, budget re-checks under slow
persistence/restore/handles, zero/one/multiple download attribution,
changed-list fail-closed, resume skipping persisted keys,
`RunInterrupted` priority, cleanup preservation, schema accept/reject
matrix incl. graceful/nesting/arity violations, runner + legacy dispatch,
legacy partial → failure finalization, single-attempt enforcement,
duplicate-filename collision) plus an opt-in loopback Chromium smoke
(`BILLCOLLECTOR_BROWSER_TESTS=1`, `127.0.0.1` synthetic portal, isolated
profile + temp dirs — no real portal, credential, or external service).

Nits:

- **N1** — After PR #22, `_execute_step(..., parent_step=step["step"],
  single_attempt=True)` is also used for login preparation/submit steps.
  The PR's nested guard (`parent_step is not None`) therefore also rejects
  collection actions inside a login phase, with the message "cannot be
  nested under expect_download" — misleading in the login context. The
  merged schema structurally permits them there (phases/submit reference
  `#/definitions/step`). Fail-closed is acceptable; optional
  maintainer-side change: generalize the message to "cannot be nested under
  expect_download or in login phases".
- **N2** — 50 ms `wait_for_timeout` polling loops (pagination stall, event
  window, snapshot stability) are bounded by the action deadline; no
  unbounded wait.
- **N3** — The PR body's bandit note cites B608/**B110** in the legacy
  runners; the recorded baseline is B608/B104. Re-verify the bandit
  baseline on S5 and record the actual set.
- **N4** — Head not rebased onto the then-current `main` per the #18
  sequencing note (the blocker; see Verdict).

## Risks

- **R1** — Rebase pending: if the author pushes a rebased head, the S4
  preflight hash check fails and S1 re-runs on the new head (never
  integrate an unreviewed head). If path B is chosen, the hash check
  applies to `13d002c`.
- **R2** — Path B manual merges (5 files): the schema merge interacts the
  login `phases`/`submit` properties with the new collection `allOf`;
  mitigated by the specified resolutions plus the schema accept/reject
  matrix in the unit suite on S5.
- **R3** — Behavior outside collection actions: the legacy runner's
  `service_aborted` finalization flag (previously the result was inferred
  from entries only), single-attempt in `_execute_step` limited to
  collection methods, and the pause-prompt wording for collection steps.
  Existing retry/timeout/graceful/download behavior is otherwise preserved.
- **R4** — The loopback browser smoke is opt-in; if the S5 environment lacks
  the venv Chromium, the offline unit suite + full regression must carry the
  validation (record which ran).

## Integration plan

Candidate set: exactly the 7 author files (the 72 deletions in the
full-range diff are comparison artifacts — never applied).

Path A (author rebases onto `42d4337`): all 7 files expected to apply
cleanly on `dev` (dev = main + two doc-only `.kilo/` commits); S4 preflight
re-runs the pre-image checks and the hash check.

Path B (manual resolutions on the reviewed head, as characterized in the
scratch 3-way merge):

| file | action |
|---|---|
| `apps/billcollector/collection.py` | apply from PR head (new) |
| `tests/test_bc_collection.py` | apply from PR head (new) |
| `README.md` | manual: keep the dev text; insert the PR's three bullets after the "Downloads:" bullet (the dev line carries the #22 duplicate-download sentence — keep it) |
| `apps/BillCollectorServices_pw.py` | manual: import union — keep dev's `from billcollector.redaction import failure_category, failure_record, sanitize_url`, add the PR's `from billcollector.interrupt import RunInterrupted`; remaining hunks clean (verify at S4) |
| `apps/billcollector/recipes.py` | manual: `_CHAIN_END_METHODS` union — dev's `login` plus the PR's `click_until_absent`, `download_all` |
| `apps/billcollector/runner.py` | manual ×2: (a) `_execute_step` — keep dev's `single_attempt` parameter, add the PR's `collection_methods` detection + nested guard, `attempts = 1 if (single_attempt or collection_methods) else step_attempts(graceful)`; (b) `_execute_step_with_pause` — keep dev's `failure_record` error computation, adopt the PR's dynamic `attempts`/`noun` prompt |
| `apps/recipes_playwright/recipe-pw-schema.yaml` | manual: keep dev's login `phases`/`submit` properties; point the `steps` items at the PR's `nestedStep` definition; add the PR's `allOf` collection constraint to `step` and the new definitions (`nestedStep`, `method` oneOf, `collectionLocatorMethod`, `collectionActionMethod`, `playwrightMethod`, `clickUntilAbsentMethod`, `downloadAllMethod`) |
| `CHANGELOG.md` | no PR entry — author one in S6 (Keep a Changelog `Added`, sanitized wording) |

## Validation plan (S5)

From the repo root with `apps/.venv/bin/python`, on the exact dirty dev
tree (S4 leaves it uncommitted):

- `apps/.venv/bin/python -m unittest tests.test_bc_collection -v` → all
  offline tests OK (`BrowserCollectionTests` skipped unless the env var is
  set).
- Optional: `BILLCOLLECTOR_BROWSER_TESTS=1 apps/.venv/bin/python -m unittest
  tests.test_bc_collection -v` → +2 loopback browser tests (needs the venv
  Chromium).
- `apps/.venv/bin/python tests/run_regression.py --ini tests/bc_regression.ini`
  → exit 0, 7 scenarios / 8 PDFs, VERDICT: PASS (exit 3 means a real run
  holds the lock — stop it first).
- ruff (F821, E4/E7/E9) + bandit on the changed files → nothing new beyond
  the known baseline (verify N3 and record the actual set).
- The schema accept/reject matrix is covered by the unit suite; the full
  regression re-validates existing recipes through CheckRecipe.

## Deployment validation

Not deployment-relevant: no `Dockerfile`, `.dockerignore`,
`BillCollector.sh`, `install_docker-image.sh`, `deploy_remote.sh`, INI keys,
or `.env` handling changes (Python app code + YAML schema + tests + README
only). Recorded skip; no S5 deployment-process block.

## Out of scope

- Page-replacement pagination and virtualized lists — explicitly outside
  the first #18 contract.
- The Selenium runner (the PR adapts the behavior to the Playwright
  contract; no Selenium changes).
- DB schema, control protocol, exit codes — unchanged.
- The uncommitted `openwiki/` working-tree refresh — private agent context,
  excluded from this PR chain.

## Open questions (S2 gate)

1. **Path A or B?** -> **Confirmed Path A** (2026-10-23): ask the author to
   rebase onto `42d4337` and un-draft (per the #18 note; the #22
   precondition is met), then re-run S1 on the new head. The path-B manual
   resolutions above are retained as the fallback characterization only.
2. **N1:** generalize the nested-guard message for login phases (small
   maintainer-side change), or accept the current message? -> Deferred to
   the S3 proposal (it belongs to the maintainer-side changes list, which
   is finalized when the rebased head is reviewed).
3. ~~If path B: confirm the per-file resolutions above as the S3
   proposal.~~ Moot under Path A.

## S2 gate (2026-10-23)

- Verdict + plan reviewed by the user; Path A confirmed. Plan doc committed
  `edf55a3` (doc-only) to `dev`.
- Next (S3): post the rebase-request PR comment on #19 — exact text
  user-confirmed first (the agent never comments on a PR without the gate).
  Then wait for the author; when the head moves, a new session re-runs S1
  on the new head (head-moved failure mode) before any integration. The
  rebase target stays the then-current `main`; if further deliveries move
  it before the author rebases, the comment's target hash is updated in the
  S1 re-run, not by re-commenting.

## S3 (2026-10-23)

- Rebase-request comment posted on #19 after the user confirmed the exact
  text as is (gate satisfied — the agent never comments without it):
  comment `6373943417`, 2026-10-23T20:20:28Z, posted from `s-t-e-f-a-n` —
  the #18 contract decisions are confirmed, the #20 login contract is
  already integrated into `main`, request to rebase onto the current `main`
  (`42d4337`) and un-draft, maintainer reviews after the rebase.
- Re-verified 2026-10-23 after posting: `refs/pr/19` head still
  `13d002c`, `github/main` still `42d4337` — the comment's target hash
  remains valid.
- N1 (nested-guard message for login phases) stays deferred to the S3
  proposal, which is finalized when the rebased head is reviewed.
- Next: wait for the author (no further action until the head moves or the
  user asks). "continue PR #19" in a new session: head-moved failure mode —
  diff the new head against the reviewed `13d002c`, non-empty → re-run S1 on
  the new head (five-decision re-check + pre-image checks against `dev`),
  update this doc, then S2 again. If `github/main` moves before the rebase,
  the target hash is updated in the S1 re-run, not by re-commenting.
