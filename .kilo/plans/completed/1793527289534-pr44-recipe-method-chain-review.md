# PR #44 review: validate daemon recipe method chains before runtime access (C3)

> Status: DELIVERED (2026-11-01) — S7 complete: 3 dev commits
> `58d7a4b`/`df634cc`/`26377b0` pushed to `origin/dev`; ff-only promoted to
> Gitea `main` `26377b0`; mirrored to GitHub `main` `4a9bffc` (sanitized,
> STRIP-clean, integrated content verified present). PR #44 closed without
> merge (comment 6559487293, closed_at 2026-11-01T14:46:10Z); no related
> issues (the PR references none). GitHub Discussion summary user-confirmed
> but NOT posted (Discussions API 404 in this environment) — user to post in
> the web UI (exact text recorded in the S7 result section).

## PR metadata

- PR: s-t-e-f-a-n/BillCollector#44 "feat: validate daemon recipe method chains
  before runtime access (C3)" (flowcool), head
  `0b9a57f5bc077a71126a552a69252a3f1998033a` (branch
  `flowcool:feature/upstream-c3-20261028`, fetched to `refs/pr/44`, matches
  `git ls-remote github refs/pull/44/head`). `mergeable: true`,
  `mergeable_state: clean`.
- Base: `main` at `8f4bdd9` (current GitHub tip); merge base with the branch
  lineage: `79d22b1e043a91cba56d6aa59eadac485781c3d9` (an ancestor of the
  current public main). The branch merged public `main` at `3c950d7` (the tip
  before PR #45's public changes) — so PR #45's public delta (launch
  diagnostics, browser-cache entry) is **not** in the PR head.
- 11 commits, GitHub API reports 119 files +712/−24912. Real content:
  **18 C3 files** (below) + 1 file already on dev (`doc/vault_transport.md`,
  the #48 entry pulled in via the `3c950d7` merge) + ~100 deletions of
  maintainer-private paths (comparison artifact, see Verified fact 2).
- Issue: #27 F08 (product audit, closed completed 2026-10-24) — the C3/F08
  contract agreed in its comment thread (cited: comment 6388757576). The PR
  body does **not** claim "Closes #27"; no "Closes #N" anywhere → S7.5 has no
  related issue to close.
- Created 2026-10-28T08:59:56Z; last updated 2026-10-31T23:12:11Z.
- Local state at review time: Gitea `dev` = `origin/dev` = `31da0dc`, Gitea
  `main` = `origin/main` = `96871d1`, GitHub `main` = `8f4bdd9`. Working tree
  clean.
- AI disclosure present: "AI assistance: Codex assisted implementation,
  reconciliation and verification under operator direction."
- Evidence at the exact head (author-claimed): focused pytest over 11 files →
  311 passed, 1 skipped, 57 subtests; opt-in browser smoke
  (`BILLCOLLECTOR_BROWSER_TESTS=1`, 1 BrowserCollectionTests) → 1 passed;
  ruff 0.17.0 + whitespace clean; bandit 1.9.4 → same 20 signatures as public
  main (4 medium, 16 low), no scan errors. No full-suite claim for this head.

## Verdict

**Approve** — all PR code and tests apply from head without maintainer-side
code changes. Two integration adaptations on `dev` (not PR-content changes):

- `apps/billcollector/runner.py` — **3-way merge** (dev carries PR #45's
  `launch_failure_record` import + launch log line since the PR's base; the
  hunks are disjoint, plain `git apply` of the file would revert dev's PR #45
  lines).
- `CHANGELOG.md` — **manual entry merge**: only the C3 `### Added` entry is
  added to `## [Unreleased]`; the PR's `### Fixed` #48 entry already exists on
  dev (PR #55).

Minor findings (F1–F4) are accepted behavior/diagnostics trade-offs, none
block.

## Verified facts

1. Head stable: `refs/pr/44` = `0b9a57f5...` matches `ls-remote`;
   `mergeable_state: clean`. S4 preflight re-checks via `git ls-remote github
   refs/pull/44/head`.
2. Private-path deletions are fork-behind-base artifacts: current `github/main`
   top level contains no `.kilo/`, `openwiki/`, `.private/`, `.vscode/`,
   `AGENTS.md`, `.openwikiignore`, or workflow files (removed from the public
   main at `cc6630e`, which is in the current main lineage; `.github` holds
   only `ISSUE_TEMPLATE`). The branch's merge base predates that removal, so
   the ~100 deletions in `git diff MB...refs/pr/44` are noise — **never
   applied**.
3. Pre-image check on `dev` (`31da0dc`) for the 19 content files:
   - 14 byte-identical pre-images → clean apply: `doctor.py`, `login.py`,
     `recipes.py`, `variables.py`, `recipe-pw-schema.yaml`,
     `doc/RECIPE_METHODS.md`, `test_bc_collection.py`,
     `test_bc_date_variables.py`, `test_bc_doctor.py`,
     `test_bc_downloads_recovery.py`, `test_bc_login.py`, `test_bc_recipes.py`,
     `test_bc_residual_logs.py`, `test_bc_runner.py`.
   - 2 new files: `apps/billcollector/methods.py` (+202),
     `tests/test_bc_method_validation.py` (+355).
   - `runner.py` DIVERGED: dev vs PR base differ only by PR #45's two hunks
     (`launch_failure_record` import at the redaction import line; launch
     failure log line in `_run_recipe`). Disjoint from all PR #44 hunks
     (imports block, `_UNTIL_LOCATOR_KEYS` removal, `_locator_for` rewrite,
     `_run_task` gate swap).
   - `doc/vault_transport.md` IDENTICAL-TO-HEAD on dev (landed via PR #55) →
     skip.
   - `CHANGELOG.md` DIVERGED (expected): dev already holds the #48 `Fixed`
     entry; PR adds both the C3 `Added` and the #48 `Fixed` entries relative
     to its base.
4. C3/F08 contract (issue #27 F08, P1, reproduced): reject unknown methods,
   invalid argument names/types and unsupported variables **before**
   vault/browser access; report service and step; agree the supported method
   surface first (the implementation derives it by introspecting the pinned
   Playwright 1.63.0 package, not a hand-maintained list); include valid
   legacy and new collection/login recipes in compatibility checks. The
   implementation matches: `validate_method_recipe` introspects
   `playwright.sync_api` signatures/annotations, keeps reserved actions on
   their separate contracts (`login` via `validate_login_recipe`,
   `click_until_absent`/`download_all` via schema + runtime,
   `replacement_calendar` via `calendar.validate_options`), and the new test
   pins all 15 shipped `recipe-pw__*.yaml` (count matches dev) plus the
   `doc/SAFE_LOGIN.md` candidate.
5. Shared-gate wiring on dev (all call sites checked): UI load
   (`ui/recipes.py:163`) and save (`ui/recipes.py:314,344`), doctor proposal
   (`doctor.py:449`) and run start (`runner.py::_run_task`) now use the full
   gate; doctor read (`doctor.py:382`) uses `check_methods=False` so the
   offline repair flow can still read a method-invalid recipe — matching
   "The offline recipe doctor can read a method-invalid recipe for repair. Its
   proposed output, editor saves and runner starts use full validation."
6. `CheckRecipe` (helpers) is retained and still used by the legacy
   `BillCollectorServices_pw.py:184`; only the daemon `runner.py` import is
   removed. No orphaned references.
7. Schema change is scoped to the `playwrightMethod` definition: `arguments`
   gains a `oneOf` second branch (exactly one positional `"Enter"`) and an
   `allOf/if/then` restricting that form to `method: press`. `{"method":
   "click", "arguments": ["Enter"]}` fails; `{"method": "press", "arguments":
   ["Enter", "Enter"]}` fails (maxItems 1 + object-items branch); the
   keyword form `[{"key": "Enter"}]` is unchanged.
8. `calendar.validate_options(None)` raises `CollectionError`, which
   `validate_method_recipe.visit` catches and re-raises with location →
   `replacement_calendar` with missing/extra options is rejected safely.
9. Process check (CONTRIBUTING.md): issue referenced (#27, contract agreed
   before code); intended behavior + verification stated (Summary + Evidence);
   proof shipped at the exact head; AI assistance disclosed (Codex); no
   secrets in code/tests (synthetic markers only); no new network exposure
   (pure validation over the installed package); no shared-interface change
   (no DB schema, control protocol, recipe-contract, or exit-code change —
   C3 is the agreed contract itself; PR body: "No new action, database
   migration, control protocol or exit-code change").

## Code review findings

- **F1 (minor, accepted): diagnostics format change for sanitization.**
  Schema errors change from jsonschema's human-readable `e.message` to
  `<recipe coordinates>: must satisfy <validator> [value]`, and YAML errors
  from the full exception text to `invalid YAML at line X, column Y`.
  Consequence: a `required` violation lists the whole required-properties
  list instead of naming the missing one. Intent is that diagnostics never
  retain argument values (pinned by
  `test_schema_diagnostics_include_only_expected_schema_values` and the
  `synthetic-secret` absence asserts across the new tests). Accepted.
- **F2 (minor): `_locator_for` normalization.** `wait_user` `until` locators
  with `label`/`placeholder` keys now call
  `page.get_by_label(text=...)` / `page.get_by_placeholder(text=...)`
  (previously `label=`/`placeholder=`). Functionally identical in Playwright
  (first parameter is `text`) and validation/execution now share the
  `methods.locator_arguments` mapping — the stated goal. Tests updated to
  pin the normalized kwargs; a real-browser test exercises both keys.
- **F3 (note): `Any` return continuations.** Methods returning `Any`
  (e.g. `evaluate`) permit continuations on every public
  `playwright.sync_api` class; the runtime still checks the actual result.
  Documented in `doc/RECIPE_METHODS.md` and the PR body.
- **F4 (note): ungated real-browser unit test.**
  `test_until_label_and_placeholder_use_real_playwright_arguments` launches
  headless Chromium without the `BILLCOLLECTOR_BROWSER_TESTS` opt-in gate used
  by `test_bc_collection.py`'s browser tests. The regression harness requires
  browsers anyway; S5 verifies it passes on the dev tree.
- **F5 (info): chain semantics.** Per step, `owners` starts at `{Page}`; a
  method must resolve with valid arguments on at least one current owner, and
  the next owners are its static return types (`None` keeps the current
  owner). A method valid on one of several union owners passes — correct for
  `Union`-returning APIs.
- **F6 (info): positional `Enter` special case** applies only to `press`
  (`signature.bind(None, 'Enter')`); the login-submit Enter rule is enforced
  separately in `login.py` (unchanged semantics, better error coordinates).
- **F7 (info): login count check** moved inside the per-top-level-step loop —
  same "second login block rejected" semantics, now with service/step
  coordinates in the error.
- **F8 (info): `_attribute` is `lru_cache(maxsize=None)`** on
  `(class, name)` pairs — bounded by the Playwright API surface, no leak risk.

## Risks

- Stricter validation rejects recipes that previously executed with runtime
  errors (e.g. `click` without `selector` now fails validation — correct per
  `Page.click`'s signature). All 15 shipped recipes, 8 test recipes and the
  SAFE_LOGIN candidate still validate (test-pinned), so no shipped recipe
  breaks.
- The validator depends on the pinned Playwright package's annotations; a pin
  bump requires re-derivation — documented in `doc/RECIPE_METHODS.md`
  ("Re-derive the surface when the pin changes").
- `runner.py` 3-way merge: low risk (disjoint hunks) but must be verified to
  contain **both** dev's `launch_failure_record` changes and the PR's
  `load_recipe`/`locator_arguments` changes before S5.
- `methods.py` imports `playwright.sync_api` at module level, so importing
  `billcollector.recipes` now requires Playwright — true in every runtime
  context on dev (daemon, UI, doctor, tests all run in the Playwright venv).

## Integration plan (S4, per file)

Apply byte-for-byte from `refs/pr/44` (16 files):

| File | Action |
|---|---|
| `apps/billcollector/methods.py` | apply (new) |
| `apps/billcollector/doctor.py` | apply |
| `apps/billcollector/login.py` | apply |
| `apps/billcollector/recipes.py` | apply |
| `apps/billcollector/variables.py` | apply |
| `apps/recipes_playwright/recipe-pw-schema.yaml` | apply |
| `doc/RECIPE_METHODS.md` | apply |
| `tests/test_bc_collection.py` | apply |
| `tests/test_bc_date_variables.py` | apply |
| `tests/test_bc_doctor.py` | apply |
| `tests/test_bc_downloads_recovery.py` | apply |
| `tests/test_bc_login.py` | apply |
| `tests/test_bc_method_validation.py` | apply (new) |
| `tests/test_bc_recipes.py` | apply |
| `tests/test_bc_residual_logs.py` | apply |
| `tests/test_bc_runner.py` | apply |

Manual (2 files):

- `apps/billcollector/runner.py` — 3-way merge: base = PR-base blob
  `5bd6e11`, ours = `dev` `e69374e`, theirs = head `2b59124`. Expected:
  disjoint hunks merge cleanly. Post-merge check: the redaction import line
  still ends with `launch_failure_record`, the launch log line still uses
  `launch_failure_record(e)`, `from .methods import locator_arguments` and
  `from .recipes import load_recipe` present, `_UNTIL_LOCATOR_KEYS` removed,
  `CheckRecipe` import gone.
- `CHANGELOG.md` — insert the C3 `### Added` entry (PR text verbatim) at the
  top of `## [Unreleased] → ### Added`; do **not** re-add the #48 `### Fixed`
  entry (already present from PR #55).

S4 result (2026-11-01):

- Preflight re-run on dev `5f0063f`: head unchanged (`ls-remote` =
  `refs/pr/44` = `0b9a57f5`), tree clean, 14 pre-images re-verified clean,
  2 new files absent, runner.py blob hashes matched (`5bd6e11`/`e69374e`/
  `2b59124`).
- 16 files applied via `git show refs/pr/44:<path>`; `git hash-object` of
  every applied file matches its PR-head blob.
- runner.py 3-way merge (`git merge-file`): one conflict hunk at the import
  block — dev's `launch_failure_record` extension and the PR's new
  `from .recipes import load_recipe` line are adjacent, so the hunk was not
  disjoint after all. Resolution keeps both: `from .redaction import
  failure_category, failure_record, launch_failure_record` + `from .recipes
  import load_recipe` (alphabetical order preserved). Post-merge checks all
  pass (launch log line uses `launch_failure_record(e)`; `locator_arguments`
  + `load_recipe` imports present; `_UNTIL_LOCATOR_KEYS` removed;
  `CheckRecipe` import gone). Diff vs PR head = exactly the two PR #45
  hunks; diff vs dev = 9 insertions / 32 deletions.
- CHANGELOG: C3 entry inserted at the top of `## [Unreleased] → ### Added`
  (blank line after, before the #49 entry); #48 `### Fixed` entry untouched.
- Working tree left dirty (16 modified + 2 untracked) for S5; nothing
  committed except this doc-only update.

Skip (~102 entries): `doc/vault_transport.md` (identical to head), every
`.kilo/`, `openwiki/`, `.private/`, `.vscode/`, `AGENTS.md`,
`.openwikiignore`, `.github/workflows/openwiki-update.yml` deletion
(comparison artifact — never applied).

## Validation plan (S5, on the exact dev tree, repo root, `apps/.venv/bin/python`)

- New tests (pytest-style): `apps/.venv/bin/python -m pytest
  tests/test_bc_method_validation.py -q` → all pass.
- Focused set (author's list): `apps/.venv/bin/python -m pytest
  tests/test_bc_method_validation.py tests/test_bc_recipes.py
  tests/test_bc_runner.py tests/test_bc_login.py tests/test_bc_notify.py
  tests/test_bc_vault_exact.py tests/test_bc_scheduler.py
  tests/test_vault_transport.py tests/test_notice_identity.py
  tests/test_bc_calendar.py tests/test_bc_collection.py -q` → expected
  ~311 passed / 1 skipped / 57 subtests (author's exact-head numbers; S5
  reports actuals).
- Full regression: `apps/.venv/bin/python tests/run_regression.py --ini
  tests/bc_regression.ini` → exit 0, VERDICT: PASS (7 scenarios / 8 PDFs).
- Lint/security on changed files: ruff (F821, E4/E7/E9) + bandit → nothing
  new beyond the known baseline (B608 dynamic SQL table names, B104 UI bind,
  plus the PR #45-recorded config.py B105 + runner B110 pre-existing).
- Post-merge runner.py check (above) before any of the above.

Deployment-process validation: the PR touches no `Dockerfile`,
`.dockerignore`, `BillCollector.sh`, `install_docker-image.sh`,
`deploy_remote.sh`, or runtime configuration → **not deployment-relevant**;
recorded skip **user-confirmed at the S5 gate, 2026-11-01T13:16:36Z**.

S5 result (2026-11-01, on dev `83804b5` + the dirty S4 tree, repo root,
`apps/.venv/bin/python` with `PYTHONPATH=apps`):

- Preflight re-run: head unchanged (`git ls-remote github refs/pull/44/head`
  = `refs/pr/44` = `0b9a57f5`); all 17 applied files' `git hash-object`
  matches their PR-head blobs; runner.py post-merge checks all pass
  (redaction import line ends `launch_failure_record`; launch log line uses
  `launch_failure_record(e)`; `from .methods import locator_arguments` and
  `from .recipes import load_recipe` present; `_UNTIL_LOCATOR_KEYS` and
  `CheckRecipe` absent).
- New module: `pytest tests/test_bc_method_validation.py -q` → 57 passed
  (5.1s).
- Focused author set (11 modules, incl. the ungated real-browser test F4):
  **311 passed, 1 skipped, 57 subtests passed** (219.8s) — exactly the
  author's exact-head numbers.
- Full regression: `run_regression.py --ini tests/bc_regression.ini` →
  **VERDICT: PASS, exit 0** — 7 scenarios / 8 PDFs, every expectation
  matched (testhappy x3 success; testgraceful success with the expected
  graceful step failure; testbadlogin / testempty / testdlfail aborted as
  expected; downloads: exactly the 8 expected files).
- ruff 0.17.0 `--select F821,E4,E7,E9` on the 15 changed Python files →
  All checks passed.
- bandit on the changed app files → 1 Low: B110 try/except/pass at
  `runner.py:985`; verified pre-existing (bare `except Exception:` present
  in both the dev pre-PR blob `e69374e` at line 1008 and the PR-head blob
   `2b59124` at line 985) — nothing new beyond the recorded baseline.

S6 result (2026-11-01, user-confirmed as-is):

- CHANGELOG: the C3 `## [Unreleased] → ### Added` entry stands as applied in
  S4 (verbatim from head `0b9a57f5`, sanitized — no Gitea host, NAS details,
  or private paths; public issue #27 reference only).
- README: 3 maintainer-side edits (user-visible validation gate changed;
  PR author shipped no README change): the recipe-editor bullet (Web UI
  section) and the daemon-editor bullet (recipe concept section) now say
  "schema and method-chain validation"; the schema bullet gains the daemon
  method-chain sentence (installed-Playwright check of method names,
  argument names and types, properties, reserved `wait_user` options;
  unknown methods and unsupported variables rejected before vault or
  browser access; service/step coordinates without argument values; link to
  `doc/RECIPE_METHODS.md`). The `BillCollectorCheckRecipe.py` tip stays
  unchanged — the legacy batch path still uses `CheckRecipe` (Verified fact
  6), so the README statement remains accurate.
- CONTRIBUTING: no change (no contributor-rule change).
- The README edits are part of the integrated content and ship in the S7
  doc commit; the working tree stays dirty until S7.

S7 result (2026-11-01, "continue pr #44" sessions):

- S7.1: the 3 planned commits on `dev` — `58d7a4b` (feat: validator +
  shared-gate wiring + schema `press`/`Enter` form; 7 app files),
  `df634cc` (test: new 355-line 57-case module + focused author-set
  updates; 9 test files), `26377b0` (doc: `doc/RECIPE_METHODS.md`
  contract, README validation note, CHANGELOG C3 entry) — user-confirmed
  per the dev-commits gate, pushed to `origin/dev`.
- S7.2: Gitea `main` ff-only `96871d1..26377b0` + push (no tag, not a
  release).
- S7.3: mirror → GitHub `main` `4a9bffc` (`sync_github.sh`); public gate
  green — tree diff vs Gitea `main` `26377b0` is exactly the 102 stripped
  `openwiki/` files, no private paths at the tip, integrated C3 content
  present (`methods.py`, `test_bc_method_validation.py`,
  `doc/RECIPE_METHODS.md`, CHANGELOG C3 entry at top of `[Unreleased] →
  Added`).
- S7.4: PR #44 closed without merge — comment `6559487293` posted
  2026-11-01T14:45:57Z (mirror flow explained, public commit links
  `58d7a4b`/`df634cc`/`4a9bffc`, maintainer adaptations, validation
  summary, non-blocking notes), closed_at 2026-11-01T14:46:10Z.
- S7.5: N/A — the PR references no issues (no "Closes #N"; issue #27
  already closed completed 2026-10-24).
- S7.6: GitHub Discussion summary user-confirmed; NOT posted (Discussions
  write API 404 in this environment, per the #45/#55 deliveries) — recorded
  below for the manual web-UI post.
- S7.7 (this session): final state re-verified (Gitea `dev` = `main` =
  `origin/dev` = `origin/main` = `26377b0`; GitHub `main` = `4a9bffc`; PR
  closed without merge; no open PRs on the mirror; clean tree). Status:
  DELIVERED. Plan doc archived to `completed/` + README + sequencing refs
  updated (doc-only commit).

Discussion summary (user-confirmed 2026-11-01; for manual web-UI post —
the Discussions write API is unavailable from this environment):

Title: `Update: PR #44 integrated — recipe method-chain validation (C3)`

> What landed on main from the community this round:
>
> - PR #44 (@flowcool): the daemon now validates recipe method chains
>   against the installed Playwright before any vault or browser access —
>   unknown methods, invalid argument names or types, and unsupported
>   variables are rejected with service and step coordinates, without
>   retaining argument values. The full validation gate runs at web-UI
>   recipe load and save, at the offline doctor's proposal, and at runner
>   start (the offline doctor read keeps the reduced check so it can still
>   read a method-invalid recipe for repair). The schema additionally
>   accepts the positional `Enter` argument form for `press` only. All 15
>   shipped recipes plus the `doc/SAFE_LOGIN.md` candidate are pinned by a
>   new 57-case test module.
>
> Maintainer-side adaptations: `runner.py` needed a 3-way merge (main
> already carried the safe launch diagnostics from PR #45 — both changes
> kept, disjoint hunks); CHANGELOG merged only the C3 `Added` entry (the
> PR's `Fixed` entry was already on main from PR #55); short README note
> that the daemon recipe editor performs schema and method-chain
> validation (link to `doc/RECIPE_METHODS.md`).
>
> Validation (exact promoted tree): new module 57/57 passed; the author's
> 11-module focused set 311 passed / 1 skipped / 57 subtests (matching the
> exact-head numbers); full regression harness PASS (7 scenarios / 8 PDFs);
> ruff (F821, E4/E7/E9) clean; no new bandit findings.
>
> Commit:
> https://github.com/s-t-e-f-a-n/BillCollector/commit/4a9bffc46015b1c6e36d0bf16b0de2b8634265cb

## Out of scope

- Other issue #27 findings (F01–F07, F09–F10) and their work packages.
- Playwright pin changes or re-derivation.
- Stage 1b doctor LLM-repair work (separate plan doc).
- GitHub Discussions write API (known 404 in this environment) — the S7
  per-public-update summary is recorded in the S7 result section for a
  manual web-UI post.

## Open questions

None. DELIVERED 2026-11-01 — S7 complete (commits `58d7a4b`/`df634cc`/
`26377b0` → Gitea `main` `26377b0` → GitHub `main` `4a9bffc`; PR closed
without merge 2026-11-01T14:46:10Z; no related issues). The only residual
is the manual web-UI post of the user-confirmed Discussion summary recorded
above.
