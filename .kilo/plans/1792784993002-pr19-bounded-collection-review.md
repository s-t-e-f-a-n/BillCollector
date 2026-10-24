# PR #19 review — bounded Playwright collection actions

> Status: DELIVERED (2026-10-24) — S7 done: three commits on dev
> (feat `9820a10` / test `71c7d69` / doc `4b336d2`), promoted ff-only to
> main (`4b336d2`), mirrored to GitHub main (`b4cf023f`, public gate
> passed). PR #19 closed without merge with the #25-routine close comment
> (14:00:16Z); issue #18 closed (criteria met, 14:00:19Z); Announcements
> Discussion #29 posted. Private-trees-in-public-history finding reported,
> deferred by the user. Recipe-doctor WIP stash restored on dev.

## PR metadata

- PR: #19 on `s-t-e-f-a-n/BillCollector` (public mirror), open, **not a
  draft** (un-drafted by the author with the rebase, 2026-10-23T21:48:17Z)
- Title: feat: add bounded Playwright collection actions
- Author: flowcool; created 2026-10-20T12:43:19Z, updated 2026-10-23T21:48:17Z
- Head (S1 re-run 2026-10-24): `49bbda5231a43984cc967a98f2794719cecf60a0`,
  branch `feature/playwright-collection-analysis` (flowcool/BillCollector);
  verified by `git ls-remote` 2026-10-24 and the GitHub API. **Moved from the
  reviewed `13d002cfcda2bf095cbe279dbef64f14d99e783d`** (non-fast-forward
  rebase; `refs/pr/19` force-updated locally). Four author commits on the new
  base: `4162e6f` (feat: prototype bounded Playwright collections) →
  `cbeef51` (fix: address collection analysis reviews) → `3468172` (fix:
  resume partial Playwright collections safely) → `49bbda5` (fix: compute
  collection options after lazy argument processing — **new in the rebase**).
- GitHub base ref: `main` (`42d4337`); merge-base with `github/main`:
  `42d4337` — a clean rebase onto exactly the requested target; the old
  orphaned sanitized recommit `4508909` is no longer in the PR history
  (the new lineage continues the canonical public main).
- Issue refs: #18 ("Agree bounded Playwright collection actions for
  pagination and multi-download"), still open; the PR body says "Closes #18".
  Maintainer agreement comment on issue #18 posted 2026-10-22T22:03:11Z:
  **all five contract decisions accepted** (two actions not one composite;
  required stable `key_attribute`; full per-item event window with runtime
  validation against the explicit deadline before the first side effect;
  duplicate suggested filenames fail before overwrite; implementation
  ownership — a focused PR against the then-current `main`). Sequencing note:
  start with PR #22 first (done, DELIVERED 2026-10-23), then "rebase onto the
  then-current `main` and I'll review it after" — **done**: rebased onto
  `42d4337` + un-drafted 2026-10-23T21:48:17Z.
- AI disclosure: Codex implemented and reviewed under the contributor's
  direction; Claude Code and CodeRabbit supplied external review findings,
  each checked against the reviewed SHA before a fix (CONTRIBUTING.md
  disclosure satisfied). The new rebase commit `49bbda5` additionally carries
  `Co-Authored-By: Claude Sonnet 5.5` + a `Claude-Session` link — disclosure
  remains satisfied.
- GitHub diff stats (now exact, no orphaned recommit): 7 files,
  +1863/−19 (4 commits, per the GitHub API).
- PR body: unchanged by the rebase. Its Evidence section still cites the
  old head `13d002c` (324 passed, 3 skipped, 37 subtests; Chromium loopback
  25 passed; `run_regression.py` 7 accounts / 8 files VERDICT PASS; scoped
  ruff, `py_compile`, bandit; wider bandit B608/B110) — S5 re-establishes the
  evidence on the new tree. The "draft until the #18 decisions are confirmed"
  line is stale body text (the PR is un-drafted).

Local state (S1 re-run 2026-10-24):

| ref | tip |
|---|---|
| Gitea `dev` | `c555df8212fac08f5a120493017051ce060f3f26` |
| Gitea `main` | `9d8ebcfea9539e6a107e2502811a928a6cfa6665` |
| GitHub `main` | `42d4337874afb9db0e4a1e491dc0e52df9da656a` |

`dev` moved 9 commits since S2 (`d6a695d` → `c555df8`): plan docs, the
pr-review skill publication routine, an `apps/requirements.txt` dep bump
(aiohttp 3.14.3→3.14.4, certifi 2026.7.22→2026.10.19), and an openwiki
refresh — **none touch the 7 candidate files** (verified per file below).

Cross-PR: only #19 is open on the mirror (re-checked 2026-10-24); no
ordering dependencies.

## Verdict

**Approve with maintainer changes** (unchanged by the S1 re-run).

The implementation matches the agreed #18 contract on all five decisions,
the safety properties in the PR body hold in code, and the test bar (unit
contract suite + opt-in loopback Chromium smoke + the existing regression
command) is the one the maintainer named in #18. The S1 re-run on the new
head `49bbda5` confirms: the contract core is byte-identical to the
reviewed head, the rebase carried the author hunks faithfully, and the one
new change (the 2-line `processed_args` fix) is correct and required.
Maintainer-side changes:

1. CHANGELOG entry — the author shipped none (see S6).
2. Conflict resolutions — **not needed**: the rebased head applies to `dev`
   with zero conflicts (verified empirically, S1 re-run). The path-B manual
   resolutions below are retained as the documented fallback only.
3. Optional nit N1 (generalize the nested-guard error message for login
   phases) — user's call at S3.

The former blocker (rebase onto the then-current `main`) is resolved:
Path A was executed by the author (rebase onto `42d4337` + un-draft), and
the S1 re-run found the rebase clean with no adaptation beyond the 2-line
fix. Path B remains only as the documented fallback characterization.

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

S1 re-run (2026-10-24, new head `49bbda5`) — verified facts:

- `refs/pr/19` force-updated to `49bbda5` (non-fast-forward: rebased
  lineage); `git ls-remote` and the GitHub API agree on the head.
- `github/main` still `42d4337` — the rebase-request comment's target hash
  remains valid; no re-comment needed.
- `git merge-base 49bbda5 github/main` = `42d4337`; `github/main` is an
  ancestor of the new head → clean rebase onto exactly the requested target.
- The head-to-head delta (`13d002c` → `49bbda5`) decomposes exactly into:
  the main-side changes (`baa4046` → `42d4337`, the PR #22 safe-login
  delivery + docs) + a faithful carry of the reviewed author hunks + the new
  2-line fix commit `49bbda5` (verified hunk-by-hunk via diff-of-diffs on
  the 5 overlapping files).
- `apps/billcollector/collection.py` and `tests/test_bc_collection.py` are
  **byte-identical** to the reviewed head (empty diff).
- `README.md`: the three contract bullets are textually identical; the
  indentation was normalized to the new main's list level (6 → 5 leading
  spaces, consistent with the sibling bullets in both heads).
- The 5 overlapping files carry the same author hunks as reviewed, correctly
  rebased onto main's restructures: `_CHAIN_END_METHODS` is now
  `"expect_download", "wait_user", "login", "click_until_absent",
  "download_all"`; the attempts line is now
  `1 if single_attempt or collection_methods else step_attempts(graceful)`;
  `fail_step`/`expect_download` context uses main's `failure_record`/
  `sanitize_url` forms.
- New fix commit `49bbda5` (+2 lines, one per runner) — verified against the
  pre-fix rebase state `3468172`: after the rebase, `processed_args` was
  computed only in the **standard** branch (main's lazy per-method
  `process_argument` evaluation, the PR #22 restructure), while the
  collection-terminal branch still referenced it — i.e. it would reuse the
  previous loop iteration's value (for a `[locator, action]` step, the
  locator's `[]`), so **every collection step would have failed with
  "requires one options object"** at runtime. The fix recomputes
  `processed_args` from the action's own `arguments` inside the terminal
  branch, after `validate_terminal_action` and before the arity check —
  correct placement in both `runner.py` and `BillCollectorServices_pw.py`.
- Pre-image vs current `dev` (`c555df8`): all 5 overlapping files are
  **byte-identical** between `dev` and `42d4337` (the 9-commit dev drift
  touched only plan docs, the skill, `requirements.txt`, openwiki); the two
  new files are absent from `dev`. Empirical `git apply --3way` of the full
  author diff (`42d4337..49bbda5`) on a scratch `dev` worktree: **all 7
  files applied cleanly, zero conflict markers**.
- No INI keys, `.env` handling, DB schema, control protocol, or exit-code
  changes in the re-run delta; no new network exposure; no secrets (the only
  content not covered by the original S1 review is the 2-line fix).

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

New in the rebase — `49bbda5` "fix: compute collection options after lazy
argument processing" (+2 lines):

- `apps/billcollector/runner.py` `_process_step` terminal branch and
  `apps/BillCollectorServices_pw.py` `process_step` terminal branch each gain
  `processed_args = [process_argument(arg, bcs) for arg in arguments]`
  directly after `validate_terminal_action(...)`, before the locator-prefix
  and options-arity checks.
- Behavior: unchanged from the reviewed head for every input (the reviewed
  head computed the same expression for the same `arguments` at the top of
  the loop; the rebase moved the computation into the standard branch only).
  The fix restores the reviewed semantics on the rebased tree — without it,
  the terminal branch would dispatch a stale (previous-iteration) value.
- Contract impact: none — options validation, deadline, event window, and
  dedup behavior are all in `collection.py` / the adapters, untouched.

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

- **N1** (still open at the new head) — After PR #22,
  `_execute_step(..., parent_step=step["step"], single_attempt=True)` is
  also used for login preparation/submit steps. The PR's nested guard
  (`parent_step is not None`) therefore also rejects collection actions
  inside a login phase, with the message "cannot be nested under
  expect_download" — misleading in the login context (verified unchanged at
  `49bbda5`: `runner.py` guard + `BillCollectorServices_pw.py` `run_step
  (nested=True)`). The merged schema structurally permits them there
  (phases/submit reference `#/definitions/step`). Fail-closed is
  acceptable; optional maintainer-side change: generalize the message to
  "cannot be nested under expect_download or in login phases".
- **N2** — 50 ms `wait_for_timeout` polling loops (pagination stall, event
  window, snapshot stability) are bounded by the action deadline; no
  unbounded wait.
- **N3** — The PR body's bandit note cites B608/**B110** in the legacy
  runners; the recorded baseline is B608/B104. Re-verify the bandit
  baseline on S5 and record the actual set.
- **N4** — ~~Head not rebased onto the then-current `main` per the #18
  sequencing note.~~ Resolved 2026-10-23: rebased onto `42d4337` +
  un-drafted; S1 re-run confirmed the rebase clean.

## Risks

- **R1** — Head-moved risk now applies to `49bbda5`: if the author pushes
  again before S4, the S4 preflight hash check fails and S1 re-runs on the
  new head (never integrate an unreviewed head).
- **R2** — ~~Path B manual merges (5 files).~~ Moot under the executed Path A
  (clean apply verified); the specified manual resolutions remain the
  documented fallback if the tree ever diverges again.
- **R3** — Behavior outside collection actions: the legacy runner's
  `service_aborted` finalization flag (previously the result was inferred
  from entries only), single-attempt in `_execute_step` (now combined with
  main's `single_attempt` for login phases: `1 if single_attempt or
  collection_methods else step_attempts(graceful)`), and the pause-prompt
  wording for collection steps. Existing retry/timeout/graceful/download
  behavior is otherwise preserved; the `processed_args` fix restores the
  reviewed semantics for the terminal branch.
- **R4** — ~~The loopback browser smoke is opt-in; if the S5 environment
  lacks the venv Chromium, the offline unit suite + full regression must
  carry the validation (record which ran).~~ Resolved (S5, 2026-10-24):
  venv Chromium 1243 was present; the loopback smoke ran and passed. The PR
  body's evidence numbers are re-established on the new tree (see S5
  section).

## Integration plan

Candidate set: exactly the 7 author files (no private paths; the full-range
diff is the author change itself after the clean rebase).

Path A — **executed and verified (S1 re-run 2026-10-24)**: all 7 files apply
to `dev` cleanly (empirical `git apply --3way`, zero conflicts):

| file | action |
|---|---|
| `apps/billcollector/collection.py` | apply from PR head (new) |
| `tests/test_bc_collection.py` | apply from PR head (new) |
| `README.md` | apply from PR head (clean) |
| `apps/BillCollectorServices_pw.py` | apply from PR head (clean) |
| `apps/billcollector/recipes.py` | apply from PR head (clean) |
| `apps/billcollector/runner.py` | apply from PR head (clean) |
| `apps/recipes_playwright/recipe-pw-schema.yaml` | apply from PR head (clean) |
| `CHANGELOG.md` | no PR entry — author one in S6 (Keep a Changelog `Added`, sanitized wording) |

S4 preflight re-runs the hash check (`refs/pr/19` = `49bbda5`), the
`github/main` check (`42d4337`), and the pre-image checks, then applies
each file's content from `refs/pr/19`.

Path B (manual resolutions on the reviewed head `13d002c`, as characterized
in the scratch 3-way merge — documented fallback only, not planned):

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

1. ~~**Path A or B?**~~ -> **Resolved**: Path A executed by the author
   (2026-10-23) and verified clean by the S1 re-run (2026-10-24). The
   path-B manual resolutions above are the documented fallback only.
2. ~~**N1:** generalize the nested-guard message for login phases?~~ ->
   **Accepted** (S3 gate, 2026-10-24): the one-line message generalization
   in `runner.py` is part of the confirmed proposal.
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
- Issue #18 still open (the PR's "Closes #18"): sequencing-milestone
  comment posted after user confirmation — comment `6374211209`,
  2026-10-23T20:35:11Z, from `s-t-e-f-a-n`: the #20 login contract
  (PR #22) is integrated into `main`, the rebase request is on PR #19,
  review follows the head move.
- N1 (nested-guard message for login phases) stays deferred to the S3
  proposal, which is finalized when the rebased head is reviewed.
- Next: wait for the author (no further action until the head moves or the
  user asks). "continue PR #19" in a new session: head-moved failure mode —
  diff the new head against the reviewed `13d002c`, non-empty → re-run S1 on
  the new head (five-decision re-check + pre-image checks against `dev`),
  update this doc, then S2 again. If `github/main` moves before the rebase,
  the target hash is updated in the S1 re-run, not by re-commenting.

## S1 re-run (2026-10-24) — head moved

- Trigger: "continue PR #19" — `git ls-remote github refs/pull/19/head`
  shows `49bbda5` (was `13d002c`); non-fast-forward (rebased lineage),
  `refs/pr/19` force-updated. GitHub API: open, **un-drafted**, base
  `main` @ `42d4337`, updated 2026-10-23T21:48:17Z, 7 files +1863/−19,
  4 commits, mergeable clean.
- `github/main` still `42d4337` — the comment's target hash remains valid;
  no re-comment.
- Diff vs the reviewed head: main-side changes + faithful author carry +
  the new 2-line fix commit `49bbda5` (verified hunk-by-hunk; see Verified
  facts / Code review findings above). Five-decision contract re-check:
  all five hold (core files byte-identical to the reviewed head; decision 5
  — focused PR against the then-current `main` — now literally met).
- Pre-image vs `dev` (`c555df8`): all 5 overlapping files byte-identical to
  the PR base; empirical `git apply --3way` of the full author diff on a
  scratch `dev` worktree → 7/7 files clean, zero conflict markers.
- Process check: issue ref #18 present; AI disclosure satisfied (PR body +
  new commit trailers); no secrets in the delta; no new network exposure;
  shared interface (recipe contract) agreed in #18 before code.
- Cross-PR: only #19 open; no dependencies.

## S2 gate (2026-10-24, re-run)

- Updated plan doc reflects the S1 re-run; verdict unchanged (approve with
  maintainer changes); Path A verified clean → S3 proposal will be the
  clean-apply integration (no manual resolutions) plus the N1 decision.
- Awaiting the user's review of the updated findings; on confirmation the
  doc-only commit + push happen (dev-commits gate), then S3.
- **Passed** (2026-10-24): user confirmed "Commit + push"; doc-only commit
  `33c172e` on `dev`. The "continue" that followed routed to S3.

## S3 (2026-10-24) — integration proposal confirmed

- State re-verified at S3 entry: `refs/pr/19` head still `49bbda5`
  (`git ls-remote`), `dev` = `origin/dev` = `33c172e`; working tree carries
  the unrelated recipe-doctor WIP (7 files, **no overlap** with the 7
  candidates).
- Proposal presented: apply all 7 files from the PR head (clean apply, no
  skips, no manual resolutions), maintainer-side changes = N1 one-liner +
  the authored CHANGELOG entry (S6), three-commit structure (feat / test /
  doc) as listed below.
- **Gate passed (2026-10-24): user confirmed the proposal as-is, incl. N1.**
  - N1: `runner.py` nested-guard message → "bounded collection actions
    cannot be nested under expect_download or in login phases" (one line;
    verified call sites `runner.py:836,846` pass `parent_step` for login
    preparation/submit; the legacy runner's message stays — its
    `nested=True` only ever comes from `expect_download`).
  - CHANGELOG entry (authored, S6) — appended to `## [Unreleased] →
    ### Added`:
    > Bounded Playwright collection actions (issue #18): two new terminal
    > recipe methods that take one page locator plus one options object -
    > `click_until_absent` drives a cumulative "load more" control until it
    > is absent or hidden (every click must increase the visible progress
    > count; `max_clicks` 1-100, `timeout_ms` 1-120000; page-replacement
    > pagination and virtualized lists fail closed), and `download_all`
    > downloads every item of a stable ordered list (non-empty unique
    > `key_attribute` per item, exactly one download per click observed over
    > a full per-item `event_window_ms` window, `max_items` 1-200,
    > `timeout_ms` 1-600000, with the per-item event budget re-validated
    > against the deadline before every click). Collection steps are
    > single-attempt (no automatic retry after partial side effects), cannot
    > be nested under `expect_download` or marked `graceful: true`, and an
    > operator resume of `download_all` skips the item keys already
    > persisted for the step; a suggested filename already saved earlier in
    > the run fails instead of being overwritten.
  - Commit structure (S7, dev-commits):
    1. `feat: recipes: add bounded Playwright collection actions` —
       `collection.py`, `runner.py`, `BillCollectorServices_pw.py`,
       `recipes.py`, `recipe-pw-schema.yaml` (+ N1 line)
    2. `test: collection: add contract suite and loopback browser smoke` —
       `tests/test_bc_collection.py`
    3. `doc: collection: document bounded collection actions (changelog,
       readme)` — `README.md`, `CHANGELOG.md`
- S4 preflight plan (next session): `git stash -u` the recipe-doctor WIP
  (zero file overlap → pop is conflict-free), then hash check
  (`refs/pr/19` = `49bbda5`), `github/main` check (`42d4337`), re-run the
   pre-image checks, apply the 7 files from `refs/pr/19`, add the N1
   one-liner, leave the tree dirty (uncommitted) for S5. After S5/S7,
   `git stash pop` the WIP.

## S5 (2026-10-24) — validation on the exact tree

- Tree verified at S5 entry: on `dev` (`9e85c13`), the 6 candidate files
  are byte-identical to the `refs/pr/19` head `49bbda5` (re-verified per
  file); `runner.py` = PR head + exactly the N1 one-liner; WIP still
  stashed (`stash@{0}`); `git ls-remote` head unchanged. `apps/data/` is
  untracked local runtime state — left out of the tree and out of scope.
- Unit suite: `PYTHONPATH=apps apps/.venv/bin/python -m unittest
  tests.test_bc_collection -v` → **25 tests, OK** (1 skip = the opt-in
  browser smoke).
- Loopback Chromium smoke: with `BILLCOLLECTOR_BROWSER_TESTS=1` →
  `BrowserCollectionTests.test_paginate_then_download_from_loopback_portal`
  **OK** (6.9s; venv Chromium 1243) — R4 resolved.
- Full regression: `PYTHONPATH=apps apps/.venv/bin/python
  tests/run_regression.py --ini tests/bc_regression.ini` → **exit 0,
  7 scenarios / 8 PDFs, VERDICT: PASS** (testhappy user1/2/3 +
  testgraceful success; testbadlogin/testempty/testdlfail failure as
  expected; "exactly the 8 expected file(s)").
- ruff (`apps/.venv/bin/ruff check --select F821,E4,E7,E9`) on
  `collection.py`, `runner.py`, `BillCollectorServices_pw.py`,
  `recipes.py`, `test_bc_collection.py`: 3 findings — E402 (:161), E711
  (:182), E701 (:182), all in `BillCollectorServices_pw.py` — all
  pre-existing (identical findings on the pre-PR baseline versions,
  line-shifted only). **Nothing new from the PR.**
- bandit 1.9.4 on the same files: B608 (`BillCollectorServices_pw.py:124`,
  dynamic SQL table name) + B110 (`runner.py:987`, try/except/pass in the
  browser-close cleanup) — both pre-existing (identical statements at
  baseline lines 122/861). **Nothing new from the PR.**
- **N3 resolved**: the actual bandit set on the changed files is
  B608/B110 — the PR body's note was accurate; the previously recorded
  "B104 UI bind" baseline no longer exists (full `apps/` scan finds no
  B104 anywhere; the UI binds via PySimpleGUI `ui.run`, not a flaggable
  socket bind).
- Deployment-process validation: recorded skip stands (not
  deployment-relevant — Python app code + YAML schema + tests + README
  only).
- **Gate passed (2026-10-24): user confirmed VALIDATED.** Next session:
  S6 documentation (CHANGELOG `## [Unreleased]` entry with the S3-confirmed
  wording; README already carries the PR's bullets), then S7 (three
  commits per the S3 structure + push, promote, mirror, PR close) — and
  `git stash pop` the recipe-doctor WIP after S7.

## S6 (2026-10-24) — documentation

- CHANGELOG.md: the S3-confirmed entry appended to `## [Unreleased] →
  ### Added` (after the login-lock ntfy entry). Verified pure addition
  (`git diff` — no existing line touched; one earlier edit had re-indented
  the preceding entry and was corrected before the gate). Sanitized,
  public-safe wording (no private hosts/paths).
- README.md: no S6 change — the PR's three contract bullets were applied
  in S4 (byte-identical to the PR head, `README.md:307-309`).
- CONTRIBUTING.md: no change — contributor rules unaffected.
- Validation standing: S5 validated the exact 7-file code tree; the S6
  change is doc-only (CHANGELOG), so no re-validation is required before
  S7.
- **Gate passed (2026-10-24): user confirmed the docs.** Next session: S7
  (preflight hash checks, three commits per the S3 structure, push dev,
  promote ff-only, mirror + public gate, PR close with the user-confirmed
  comment, Status: DELIVERED) — and `git stash pop` the recipe-doctor WIP
  after S7.

## S7 (2026-10-24) — commit + push, promote, mirror, close

- Steps 1–3 (previous session, re-verified 2026-10-24): the S3-structured
  commits on `dev` — feat `9820a10` / test `71c7d69` / doc `4b336d2` —
  pushed to `origin/dev`; `main` promoted ff-only to `4b336d2` and pushed;
  mirror sync → GitHub `main` = `b4cf023f` (sanitized tip amend by
  `sync_github.sh`).
- Public gate (re-verified): `git ls-remote github refs/heads/main` =
  `b4cf023f`; the root listing carries no `.kilo` / `.private` / `.vscode`
  / `openwiki` / `AGENTS.md` / `.openwikiignore` / `.github/workflows`
  (the `.github` dir holds `ISSUE_TEMPLATE` only);
  `apps/billcollector/collection.py` is present on public `main` with the
  validated content.
- Step 4 (PR close, user gate 2026-10-24): close comment `6385109938`
  posted on #19 (mirror flow explained; public commit links `9820a10` /
  `71c7d69` / `b4cf023f` on `github/main`; maintainer-side adaptations =
  the N1 line + the CHANGELOG entry; validation result summarized; no open
  nits) per the #25 publication routine; PR closed without merge at
  2026-10-24T14:00:16Z — the change reached GitHub via the mirror, keeping
  public history canonical.
- Step 5 (related issue, user gate): issue #18 acceptance criteria met
  (both actions landed; loopback-only proof + regression passing) — comment
  `6385110362` posted with the public commit links; closed at
  2026-10-24T14:00:19Z (state_reason: completed).
- Step 6 (per-public-update summary, user gate): Announcements Discussion
  #29 posted (https://github.com/s-t-e-f-a-n/BillCollector/discussions/29;
  category node `DIC_kwDOOF013s4CoYir`; repo discussions use the
  `createDiscussion` mutation — `newDiscussion` is the team variant).
- Finding (2026-10-24): `sync_github.sh` sanitizes only the tip commit, so
  every older commit on GitHub `main` carries the private trees (`.kilo/`,
  `.private/`, `openwiki/`, `AGENTS.md`, `.openwikiignore`,
  `.github/workflows/openwiki-update.yml`) in its tree. Confirmed on the
  pre-sync Gitea-main commit `9d8ebcf` and on today's `930891d` —
  pre-existing, not introduced by this delivery. Reported to the user with
  the fix option (full-history sanitization rewrite + force-push of GitHub
  `main`); the user deferred the decision to a separate follow-up.
- Step 7: Status DELIVERED. dev = `4b336d2` + this doc commit; main =
  `4b336d2`; GitHub main = `b4cf023f`. Recipe-doctor WIP stash popped on
  dev.
