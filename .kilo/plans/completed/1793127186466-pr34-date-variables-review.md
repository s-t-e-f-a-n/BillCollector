# PR #34 review: daemon runtime date variables (issue #26)

> Status: DELIVERED (2026-10-27) — S7 complete 2026-10-27T21:25Z: Gitea
> `main` = `dev` = `53a5dff` (ff-only promotion); GitHub mirror `main`
> `6bb3348` (sanitized, verified up-to-date); PR #34 closed without merge
> (close comment 6453946786, 2026-10-27T21:25:24Z); issue #26 closed as
> delivered (comment 6453947542, 2026-10-27T21:25:26Z); Discussion
> summary deferred (write API unreachable — draft recorded, user posts
> manually in the web UI).

## PR metadata

- Author: flowcool; head `e1d3787b179eed6359cf1d2b5afb4e469fe3e253` (branch
  `feature/playwright-date-variables` in flowcool's fork). The head is a merge
  commit with parents `7c80191` (the feature branch) and `d9362b3` (the
  reconciled `upstream/main`). `git ls-remote github refs/pull/34/head`
  matches the local `refs/pr/34` at review time (verified 2026-10-27).
- Base: the PR's base ref points at current public `main` `93bfcc8`, but the
  branch content is reconciled to the earlier public tip `d9362b3` (PR body:
  "Reconciled with current public `main` at `d9362b3`"). `d9362b3` is not
  reachable from current `github/main` (the mirror re-sanitized and rewrote
  hashes after the #33/#32 deliveries). GitHub `mergeable_state: dirty` —
  expected, `main` moved after the fork point; handled by file-level
  application in S4.
- Issue ref: #26 (daemon date-variable contract, confirmed 2026-10-24,
  comment 6385845191; proposal + the 17 accepted cases at 6376677460).
- Local state at review: `dev` = `origin/dev` = `bf284bb`; Gitea `main` =
  `origin/main` = `bde713c`; `github/main` = `93bfcc8`.
- Actual PR content: the change set against its true base `d9362b3` is 20
  files (17 M, 3 A), no private paths. Because the head's second parent is
  `d9362b3`, the change set is exactly `git diff d9362b3...refs/pr/34` with no
  orphaned-upstream noise.
- Cross-PR: open PRs at review time are #34, #35, #39, #40, #41, #42 (all
  flowcool, all target `main`). #34 is the head of the sequencing chain
  #34 → #35 → #42 → #39 → #40 (#41 held on the #38 archive decision).
  Shared-file overlap with the later PRs is regional (`runner.py`, `db.py`,
  `config.py`, README/CHANGELOG), not hunk-level; each later S1 re-runs the
  pre-image check against current dev.

## Merge-base / base analysis

- `git merge-base refs/pr/34 github/main` = `36a8d31` — older than the PR's
  true reconciliation base; the mirror rewrites hashes on each sync, so the
  raw merge base is not the content base.
- The PR head's second parent is `d9362b3` ("doc: CHANGELOG — onboarding
  switch independence fix (PR #31, issue #27 F07)") = the public main tip
  when the PR was cut. `git merge-base d9362b3 refs/pr/34` = `d9362b3` (it is
  an ancestor of the head). The PR's own change set is therefore exactly
  `git diff d9362b3...refs/pr/34` — 20 files, no private paths, no comparison
  artifacts.
- No orphaned private-path commits: none of the 20 files is under `.kilo/`,
  `.private/`, `.vscode/`, `openwiki/`, `AGENTS.md`, `.openwikiignore`, or
  `.github/workflows/`.

## Verdict

**Approve.** The #26 date-variable contract is implemented exactly as agreed
(the 17 accepted cases each have an executable proof in
`tests/test_bc_date_variables.py`), plus the timezone follow-up the PR body
flags for a fresh review: the image no longer imposes `Europe/Berlin`,
Compose forwards the user-selected `TZ` (UTC for unset/empty), and cron
scheduling + calendar dates share one zone via `daemon_timezone()`.
`Task.date_window_days` is an additive migration (default 90 inclusive days)
— the agreed shared-interface change from #26. The Run-now start-date
override is memory-only (it never enters task/run records, argv, environment,
or replay files). No secrets; no new network exposure; AI assistance
disclosed. Two maintainer-side adaptations ride the delivery (not changes to
the PR's code logic): the CHANGELOG `### Added` merge, and the S6 contract-doc
bundle (`doc/RECIPE_METHODS.md` date-variable section + the `doctor.py`
prompt placeholder vocabulary).

## Verified facts

- Issue #26 contract (confirmed 2026-10-24, comment 6385845191):
  `{{TODAY}}`, `{{DATE_TO}}`, `{{DATE_FROM}}`, `{{TODAY±Nd}}` expand inside
  any method-argument string (including nested lists/dicts); dict keys
  unchanged; credentials stay opaque (single-pass, never re-parsed);
  `DATE_TO = TODAY`, `DATE_FROM = TODAY - (window - 1)`; output default
  `YYYY-MM-DD` with a restricted format suffix; dates bounded 0001-01-01 to
  9999-12-31; unknown/malformed/overflow fail before browser or vault access;
  one instant is captured before launch and stays fixed through retries and
  interactive resume. The PR body maps all 17 accepted cases to named tests.
- `apps/billcollector/variables.py` (new, 186 lines): `daemon_timezone()`
  (TZ from the environment, UTC fallback, invalid zone → ValueError),
  `validate_window()` (strict positive int), `parse_override()` (strict
  `YYYY-MM-DD`, no future date), `DateContext.capture()`/`.resolve()` (window
  math + offset bounds + format), `expand_argument()` (recursive single-pass,
  opaque credentials, optional-TOTP `None` preserved for exact tokens),
  `validate_variable_recipe()` (shared UI/run-start syntax validation). Errors
  carry location + category only, never recipe values or credential data.
  Faithful to the contract (checked against the 17-case table).
- Pre-image check against dev (PR base `d9362b3`):
  - byte-identical to base (hunks apply cleanly) — 11 files: `.env.example`,
    `Dockerfile`, `apps/.env.example`, `apps/billcollector/cli.py`,
    `orchestrator.py`, `recipes.py`, `scheduler.py`, `ui/task_detail.py`,
    `ui/tasks.py`, `tests/test_bc_ui_dashboard.py`,
    `tests/test_bc_ui_task_detail.py`.
  - new (absent in dev and in the base) — 3 files:
    `apps/billcollector/variables.py`, `tests/test_bc_date_variables.py`,
    `tests/test_bc_timezone_config.py`.
  - diverged (hunks verified **non-overlapping** with dev's changes since the
    base) — 6 files: `runner.py`, `db.py`, `docker-compose.yml`,
    `tests/test_bc_residual_logs.py`, `README.md`, `CHANGELOG.md` (detail
    below).
- The six diverged files — both sides, non-overlapping:
  - `runner.py`: dev #33/#32 added `import sqlite3` + `chromium_sandbox=True`
    (`_launch_browser`) + the `recover_downloads` block in `_run_task` (after
    the "task not found" check); the PR adds the `from .variables import …`
    line, a module-level `process_argument()`, date expansion in
    `_execute_wait_user_step` + `_execute_login`, the `date_from=None` kwarg on
    `run_task`/`_run_task`, the `DateContext.capture` +
    `validate_variable_recipe` block (after the login-contract validation), and
    `ctx.bcs.date_context = dates`. All in distinct regions; keep both.
  - `db.py`: dev #33 added the Download `state`/`staged_path` columns +
    migration + `insert_download`/`set_download_state`/`pending_downloads`; the
    PR adds the `from .variables import validate_window` line, the Task
    `date_window_days` column + migration entry, and `create_task`/`update_task`
    validation. Disjoint tables/regions; keep both.
  - `docker-compose.yml`: dev #32 added `security_opt: seccomp` after `init:`;
    the PR adds `TZ: ${TZ:-UTC}` to `environment:`. Different keys; keep both.
  - `tests/test_bc_residual_logs.py`: dev #33 added `task_db.path`/
    `get_setting`/`list_downloads` mock wiring after `task_db = Mock()`; the PR
    adds `"date_window_days": 90` to the `get_task.return_value` dict. Adjacent
    lines, no hunk overlap; keep both.
  - `README.md`: dev #32/#33 added the sandbox header paragraph + the
    Downloads-page recovery link; the PR rewrites the root `.env` variable
    list (step 4, adds `TZ`) + adds the "Daemon date variables" recipe-contract
    bullet. Separate regions; keep both.
  - `CHANGELOG.md`: both sides insert into `### Added` at the top of the list —
    the one true region-level conflict. Merge: keep dev's #32/#33 entries and
    the PR's two entries (date variables + timezone) together in `### Added`.
- Timezone behaviour changes (the "fresh review" the PR requests): `Dockerfile`
  drops `ENV TZ="Europe/Berlin"` (UTC when absent); `scheduler.py` `TaskScheduler`
  captures `daemon_timezone()` and passes it to `AsyncIOScheduler` +
  `CronTrigger.from_crontab(..., timezone=…)`; Compose forwards
  `TZ: ${TZ:-UTC}`. Blast radius: existing installations that relied on the
  Berlin default must now select a zone explicitly (documented in the PR body
  + README).
- No secrets in the PR diff: all test data is synthetic; the only `secret` /
  `password` matches are assertions verifying values do NOT leak
  (`assert secret not in repr(...) + caplog.text`,
  `page.locator('#password').input_value() == secret` on a synthetic portal).
  No new network exposure (the Compose change adds a `TZ` variable, not an
  exposure; the Dockerfile only removes a default).
- PR process check (CONTRIBUTING.md): one focused change; targets `main`;
  issue #26 opened before code with the confirmed contract; intended behaviour
  + verification commands + expected results in the PR body (pytest counts,
  actual-image checks, ruff/bandit); proof shipped (two new test modules
  mapping the 17 cases + regression reuse); AI assistance disclosed ("Codex
  under the contributor's direction"); no secrets; no new network exposure; the
  one shared-interface change (`Task.date_window_days`, additive) was agreed in
  #26 before code.

## Code review findings

- `apps/billcollector/variables.py` (new): as above. `expand_argument`'s
  single-pass + opaque-credential handling is the core contract point and is
  correct (a credential value containing `{{…}}` delimiters is never
  re-parsed; an exact-token credential returns the resolver value directly,
  preserving optional-TOTP `None`).
- `apps/billcollector/runner.py`: `process_argument` now routes through
  `expand_argument` with a credential resolver map + the run's `DateContext`;
  `_run_task` captures the date context once and validates the whole recipe
  before display/vault/browser setup (fail-fast per contract). The `date_from`
  override is a keyword-only, memory-only parameter threaded
  `run_task` → `_run_task` → `DateContext.capture`.
- `apps/billcollector/db.py`: `date_window_days` additive column (default 90)
  with a guarded, idempotent `PRAGMA table_info` migration (matching dev's
  existing migration style); `create_task`/`update_task` call `validate_window`.
- `apps/billcollector/scheduler.py`: one shared zone for all cron triggers
  (`daemon_timezone()`); behaviour change as noted above.
- `cli.py` / `orchestrator.py` / `recipes.py` / `ui/tasks.py` /
  `ui/task_detail.py`: wire the new field through save / run / detail (the
  Run-now start-date input, the add-task date-window field, shared recipe
  validation). Clean pre-images.
- `Dockerfile` / `docker-compose.yml` / `.env.example` / `apps/.env.example`:
  the TZ configuration surface (image default removed, Compose forward,
  documented examples).
- `tests/test_bc_date_variables.py` (new): maps all 17 accepted cases; also the
  pre-launch-failure guards (invalid window/zone/recovery/overflow fail before
  resources), the dispatch-pipe memory-only proof
  (`test_dispatch_override_uses_pipe_only_and_is_not_replayed`), and the
  credential-opacity assertions (secret absent from records/capsys).
- `tests/test_bc_timezone_config.py` (new): Compose resolution, shell
  precedence, invalid-zone rejection, `apps/.env` edge cases (skipped without a
  docker image), UTC defaults, DST boundary.
- `tests/test_bc_ui_dashboard.py` / `tests/test_bc_ui_task_detail.py`: the
  add-task dialog sets `date_window_days` (30) and the task-detail recovery
  input dispatches once with `date_from`, clears the form, and a second run
  dispatches with `None` (window resets to 90).

## Risks

- **Cron timezone semantics change (primary behaviour risk):** without a
  selected Compose `TZ`, schedules now use UTC instead of the image's former
  `Europe/Berlin`. Existing installations must set `TZ` explicitly to keep
  their previous local time. This is the agreed #26 contract, but it is a real
  behaviour change for current users — the S6 docs + the S7 close comment must
  state it plainly.
- **Additive schema column:** `Task.date_window_days` remains after a source
  rollback (two-way door per the PR's "Merge Danger"); a DB downgrade needs a
  separate backup/recovery decision. Low risk (additive, default 90, guarded
  migration).
- **dev has diverged from the PR base in 6 files;** the merges are manual but
  the hunks are verified non-overlapping (S4 re-checks pre-images; the
  CHANGELOG `### Added` merge is the one region-level conflict).
- If the author pushes a new head, S1 must re-run on the new head (failure
  mode); the current head `e1d3787` is the reviewed one.

## Integration plan (S4, Gitea dev)

| File | Action | Note |
|---|---|---|
| `.env.example` | apply PR head | base-identical |
| `Dockerfile` | apply PR head | base-identical (Berlin default removed) |
| `apps/.env.example` | apply PR head | base-identical |
| `apps/billcollector/cli.py` | apply PR head | base-identical |
| `apps/billcollector/orchestrator.py` | apply PR head | base-identical |
| `apps/billcollector/recipes.py` | apply PR head | base-identical |
| `apps/billcollector/scheduler.py` | apply PR head | base-identical (cron zone) |
| `apps/billcollector/ui/task_detail.py` | apply PR head | base-identical |
| `apps/billcollector/ui/tasks.py` | apply PR head | base-identical |
| `tests/test_bc_ui_dashboard.py` | apply PR head | base-identical |
| `tests/test_bc_ui_task_detail.py` | apply PR head | base-identical |
| `apps/billcollector/variables.py` | apply PR head (new) | |
| `tests/test_bc_date_variables.py` | apply PR head (new) | |
| `tests/test_bc_timezone_config.py` | apply PR head (new) | |
| `apps/billcollector/runner.py` | manual | apply the PR hunks to dev's current content, **keeping** dev's #33 `import sqlite3` + `recover_downloads` block and #32 `chromium_sandbox=True` (hunks verified non-overlapping) |
| `apps/billcollector/db.py` | manual | apply the PR `date_window_days` hunks to dev's current content, **keeping** dev's #33 Download `state`/`staged_path` migration + methods |
| `docker-compose.yml` | manual | apply the PR `TZ: ${TZ:-UTC}` line, **keeping** dev's #32 `security_opt: seccomp` |
| `tests/test_bc_residual_logs.py` | manual | apply the PR `"date_window_days": 90` dict entry, **keeping** dev's #33 `task_db` mock wiring |
| `README.md` | manual | apply the PR step-4 `TZ` list + the "Daemon date variables" bullet, **keeping** dev's #32 sandbox header + #33 Downloads recovery link |
| `CHANGELOG.md` | manual | merge the PR's two `### Added` entries with dev's #32/#33 entries (Keep a Changelog order) |

Optional maintainer-side changes (S3 decision) — the S6 contract-doc bundle
(agreed in the sequencing decision to ride #34's delivery):

- M1: `doc/RECIPE_METHODS.md` — add a date-variable section (the #26
  vocabulary: `{{TODAY}}`/`{{DATE_TO}}`/`{{DATE_FROM}}`/`{{TODAY±Nd}}`, the
  window default, `TZ`/UTC, the format suffix, the bounds, the
  fail-before-resources rule) alongside the existing `{{USERNAME}}`/
  `{{PASSWORD}}`/`{{OTP}}` table (~L224). Doc-only.
- M2: `apps/billcollector/doctor.py` (~L265) — extend the prompt's
  "Placeholders {{USERNAME}} {{PASSWORD}} {{OTP}} must be kept verbatim" to
  also name the date variables so the recipe-doctor LLM preserves/expands them
  correctly. Code (prompt string) but behaviour-neutral for the runner.
- The README contract bullet is already in the PR (applied above), so no
  separate README maintainer change is needed.

Both M1/M2 are additive and behaviour-preserving; if the user declines either,
the PR head content is kept as-is and the doc gap is recorded as a follow-up.

## S3 execution record

S3 ran 2026-10-27 on a clean `dev` tree (`2d95626`, a doc-only move from the
S1 state `bf284bb` — the plan doc itself). Pre-flight re-verified before the
gate:

- PR head unchanged: `e1d3787b179eed6359cf1d2b5afb4e469fe3e253`
  (`git ls-remote github refs/pull/34/head` = local `refs/pr/34`).
- Pre-image classification re-run on all 20 files against current dev:
  identical to S1 (11 base-identical, 3 new, 6 diverged).
- All six manual-merge landing sites re-checked against current dev content
  (hunk contexts present; the dev #32/#33 additions confirmed in their own
  disjoint regions).

Gate result: the user confirmed the proposal **as-is** (2026-10-27):

- A: 14 files applied from the PR head (11 base-identical + 3 new).
- B: 6 keep-both merges — `runner.py` (9 hunks, keeping dev's
  `import sqlite3` / `chromium_sandbox=True` / `recover_downloads` block),
  `db.py` (4 hunks, keeping dev's Download `state`/`staged_path` migration +
  methods), `docker-compose.yml` (`TZ: ${TZ:-UTC}`, keeping
  `security_opt: seccomp`), `tests/test_bc_residual_logs.py`
  (`"date_window_days": 90`, keeping dev's `task_db` mock wiring),
  `README.md` (step-4 `TZ` list + "Daemon date variables" bullet, keeping
  dev's sandbox header + Downloads recovery link), `CHANGELOG.md` (the PR's
  two `### Added` entries on top of dev's #32/#33 entries; the exact merged
  section was shown and confirmed in the proposal).
- C: maintainer-side changes — M1a (new `### Date variables (issue #26)`
  subsection in `doc/RECIPE_METHODS.md` under `## 4. Variables`), M1b
  (replacement of the stale pre-#26 exact-match/F08 sentence in the same
  file), M2 (the `doctor.py` prompt extension naming the date variables and
  forbidding literal-date substitution). Exact intended diffs recorded in
  the S3 session proposal; all three confirmed.
- D: commits to create in S7 — (1) `feat: daemon date variables and timezone
  configuration (issue #26)` (variables.py, runner.py, db.py, scheduler.py,
  cli.py, orchestrator.py, recipes.py, ui/tasks.py, ui/task_detail.py,
  Dockerfile, docker-compose.yml, .env.example, apps/.env.example),
  (2) `test: date-variable and timezone suites (issue #26)`
  (test_bc_date_variables.py, test_bc_timezone_config.py,
  test_bc_ui_dashboard.py, test_bc_ui_task_detail.py,
  test_bc_residual_logs.py), (3) `doc: date-variable contract (issue #26)`
  (README.md, CHANGELOG.md, doc/RECIPE_METHODS.md),
  (4) `fix: recipe-doctor prompt preserves date variables (issue #26)`
  (doctor.py).

Next: S4 applies the files to the working tree (left uncommitted), S5
validates the exact tree (code checks + the triggered deployment-process
block on the NAS), then S6/S7.

## S4 execution record

S4 ran 2026-10-27 from `dev` = `bc1950d` (clean). Preflight: PR head
unchanged at `e1d3787b179eed6359cf1d2b5afb4e469fe3e253`; pre-image
re-check on all 20 files identical to S1/S3 (11 base-identical, 3 new,
6 diverged).

Application:

- 14 as-is files restored from `refs/pr/34` (worktree, unstaged).
- `runner.py`, `db.py`, `test_bc_residual_logs.py`, `README.md`: the PR's
  per-file hunks applied with `git apply` to dev's current content (all four
  passed `git apply --check` first) — dev's #32/#33 additions untouched.
- `docker-compose.yml`: the PR hunk did not context-match because dev's
  `security_opt: seccomp` block (added in #32) sits inside its context; the
  intended change (the `TZ: ${TZ:-UTC}` line + comment at the top of
  `environment:`) was applied manually at the same unambiguous position.
- `CHANGELOG.md`: merged by hand exactly as proposed (the PR's two `###
  Added` entries on top of dev's #32/#33 entries, Keep a Changelog order).
- M1a + M1b in `doc/RECIPE_METHODS.md` and M2 in `apps/billcollector/doctor.py`
  applied exactly as the confirmed intended diffs.

Verification (on the dirty tree, before any commit):

- All 14 as-is files blob-identical to the PR head (`git show
  refs/pr/34:<f> | cmp -s - <f>`).
- The four `git apply`-patched files: the worktree delta vs `dev` equals
  the PR's change set for that file, line for line (added/removed lines
  compared) — the keep-both content is exactly dev + PR.
- `docker-compose.yml` and `CHANGELOG.md` diffs reviewed: the `TZ` pair
  above `BC_UI_HOST` with `security_opt` intact; the two `### Added`
  entries prepended, dev's entries unchanged.
- `doctor.py` diff matches the confirmed M2 text; `doc/RECIPE_METHODS.md`
  shows +37/−6 (the M1b sentence replacement + the M1a subsection).

Tree left dirty and uncommitted (22 files: 19 modified + 3 new); S5
validates this exact content.

## S5 execution record — code checks (2026-10-27T19:40Z)

On the exact integrated dev tree (dev tip `2b90ab8` doc-only + the 22 dirty
files from S4), from the repo root with `apps/.venv/bin/python`:

- PR's new suites: `pytest tests/test_bc_date_variables.py
  tests/test_bc_timezone_config.py -q` -> **60 passed, 8 skipped** (the
  docker-image-dependent timezone cases skip without a docker image, as
  designed).
- Full pytest: `pytest tests/ -q` -> **589 passed, 10 skipped, 53 subtests
  passed**. Delta fully accounted for: 528 (dev baseline recorded at the
  #32 delivery) + 60 (the two new modules) + 1 (a new test function the PR
  adds in `tests/test_bc_ui_task_detail.py`) = 589; skips 2 + 8 = 10.
- Regression: `tests/run_regression.py --ini tests/bc_regression.ini` ->
  exit 0, **7 scenarios / 8 PDFs, VERDICT: PASS — all expectations matched**
  (badlogin / empty / dlfail fail as expected; downloads exactly the 8
  expected files).
- `ruff check apps tests` -> **All checks passed** (matches the #30/#31/#32
  baseline).
- bandit on the 15 changed Python files (12 existing at the dev-HEAD
  baseline + 3 new): the 2 pre-existing MEDIUM findings are **identical to
  the dev-HEAD baseline — zero new, zero gone**; every new finding is a LOW
  test-code idiom in the new/modified test files (B101 assert +67, B105 +3,
  B106 +1, B404 +1, B603 +2 — synthetic test data, fixed-argument
  `subprocess.run` calls without shell, 0 High).
- Code checks: **all green**.

Deployment-process validation — prerequisites (S5 gate):

- Trigger fires (the Dockerfile TZ default is removed, compose `TZ`
  runtime config, `.env` examples) — the full block is required on the NAS.
- `bash -n` on changed shell scripts: **n/a** — the PR changes no shell
  script (recorded, not skipped silently).
- The NAS fetches from Gitea (`deploy_remote.sh`: fetch + reset in
  `REMOTE_PATH`, `GIT_BRANCH`), so the exact tree must first be committed +
  pushed to `origin/dev` — the 4 S3-confirmed commits (the tree is
  currently dirty per S4). **Resolved:** the 4 commits were created and
  pushed to `origin/dev` as `dc0ef7f` (see S3 execution record D).
- Access finding (2026-10-27T19:40Z): `ssh root@192.168.1.99` from this
  session is refused (`Permission denied (publickey,password)`) — as at the
  #32 S5; the block needs either (a) restored key authorization on the NAS
  before the agent runs it, or (b) the user running it on the NAS console.
  **Resolved:** the user added the dedicated key on the NAS and the
  authentication was made permanent via a `~/.ssh/config` entry (the
  dedicated `id_ed25519_billcollector_nas` is now presented for the NAS
  host, so a plain `ssh root@192.168.1.99` works without `-i`).
- Smoke-run verification plan (TZ-specific): the scheduler logs no zone of
  its own, so the block verifies `daemon_timezone()` inside the built image
  (unset/empty `TZ` -> UTC; selected `TZ` -> the zone; invalid `TZ` ->
  startup failure) via a `python3 -c` in the container, plus the compose
  smoke showing the resolved `TZ` in the container environment with the
  daemon up and the scheduler started.

## Validation plan (S5)

Code checks — from the repo root with `apps/.venv/bin/python` on the exact
integrated dev tree:

- PR unit suites: `apps/.venv/bin/python -m pytest
  tests/test_bc_date_variables.py tests/test_bc_timezone_config.py -q` → all
  pass (the PR reports 522 passed / 3 skipped / 53 subtests on its own head;
  on the integrated dev tree the two new modules stand on their own).
- Full pytest: `apps/.venv/bin/python -m pytest tests/ -q` → all pass (dev
  baseline 528 recorded at the #32 delivery + the new PR tests; environment
  skips allowed).
- Regression: `apps/.venv/bin/python tests/run_regression.py --ini
  tests/bc_regression.ini` → exit 0, 7 scenarios / 8 PDFs, `VERDICT: PASS`
  (exit 3 → a real run holds the lock, stop it first).
- `ruff check apps tests` → nothing new beyond the known baseline.
- bandit on the changed files → nothing new beyond the known baseline.

Deployment-process validation — **trigger fires** (the PR changes `Dockerfile`
(TZ default removed), `docker-compose.yml` (TZ runtime config), and the
`.env` examples / handling). Per the skill, run the full block on the NAS
(Docker-capable deploy host), scheduled to the NAS window:

- `bash -n` on changed shell scripts → n/a (the PR changes no shell script;
  record that).
- From the exact dev tree on the NAS: `bash install_docker-image.sh` → build
  succeeds.
- `python3 tests/check_docker_context.py` → `Docker context: 18 private
  canaries excluded, 5 source files retained` (the TZ change adds/removes no
  context files; expectation unchanged from the #32 delivery).
- Smoke run the way the deploy runs it (`BillCollector.sh` on the NAS): the
  service comes up **with** the TZ config in place and the Berlin default
  removed; verify the daemon resolves the zone (UTC or the selected one) and
  cron scheduling picks it up; then stop it.
- Record host, validated tree hash, and every result in this doc's Deployment
  validation section; the user confirms the result before S6/S7 proceed.

## Deployment validation

Executed 2026-10-27 (20:30–21:45 UTC) on the NAS (`solg`, 192.168.1.99) —
the canonical deploy host — from the exact dev tree, agent via SSH (the S5
gate run mode), with the service left running afterwards (the S5 gate
service-state decision):

- Validated tree: `origin/dev` = `dc0ef7f9dfde6bde1c4c7016b5243c0e22ed8adf`
  (the 4 S3-confirmed commits, pushed before the run). The NAS repo
  (`/srv/disk-by-label/Docker/docker-recipes/BillCollector`) was
  fetch + `reset --hard` to that hash; PR head unchanged at `e1d3787`
  throughout. (Note: an interrupted earlier `deploy_remote.sh` attempt had
  left the NAS repo at `origin/main` `bde713c` with the build killed
  mid-run; the reset to `dc0ef7f` re-established the exact dev tree before
  this block.)
- `bash -n` on changed shell scripts: **n/a** — the PR changes no shell
  script (recorded, not skipped silently).
- Build: `bash install_docker-image.sh playwright` with `CONSUMER_DIR` /
  `DB_DIR` forwarded from the deploy `.env` (the canonical deploy path —
  `deploy_remote.sh`'s remote side) -> **Build successful**, image
  `billcollector:latest` =
  `sha256:23d8db51cdf3b12db7be73ee2abf30d0bb199cc725b738591c2f5130479f2d2d`;
  mount setup completed (the `apps/Downloads` / `apps/db` symlinks and the
  `apps/data` / `apps/browser/profiles` chown ran without error).
- Canary: `python3 tests/check_docker_context.py` -> **`Docker context:
  18 private canaries excluded, 5 source files retained`** (expectation
  unchanged from the #32 delivery; the TZ change adds/removes no context
  files).
- TZ verification in the built image (`python3 -c` on
  `billcollector.variables.daemon_timezone`, the scheduler's zone source):
  - unset/empty `TZ` -> **`UTC`**, exit 0 — the image no longer imposes
    Europe/Berlin.
  - `TZ=Europe/Berlin` -> **`Europe/Berlin`**, exit 0.
  - `TZ=Not/AZone` -> **`ValueError: timezone: invalid TZ`**, exit 1 — an
    invalid zone fails before the daemon serves.
- Compose smoke (the daemon's deploy shape, `docker compose up -d` with
  `TZ=Europe/Berlin` — the install's previous effective zone, now explicit
  instead of image-baked): the `billcollector` container recreated on the
  dev image -> **healthy**; container env `TZ=Europe/Berlin`;
  `daemon_timezone()` inside the running container -> `Europe/Berlin`;
  logs: `serve starting on 0.0.0.0:8000 (ini import created 0 task(s),
  total 11)`, `Scheduler started (0 job(s))`, `serve started: scheduler
  running, 0 orphan run(s) interrupted` — no errors or tracebacks.
- End state: **the service is left running on the dev tree** per the S5
  gate — the NAS now serves the #34 dev build with the zone explicit in
  the container env. (A future `docker compose up` without a `TZ` source
  would resolve the UTC default, per the #26 contract; keeping this
  install on Berlin across recreations means keeping `TZ` in the project
  `.env` or environment — flagged for the S7 close comment.)

## S6 execution record — documentation (2026-10-27)

- CHANGELOG: the PR's two `### Added` entries were in place since S4
  (user-confirmed at the S3 gate, sanitized). S6 resolves the open cron-TZ
  question: a new `### Changed` entry (top of the section, `8249c67`) states
  that the image no longer sets a `TZ` default (previously
  `Europe/Berlin`), that the zone is selected through the shell or root
  `.env` with a UTC fallback, and that existing installations relying on
  the Berlin default must set `TZ` explicitly and recreate the daemon. The
  PR's `### Added` entries are unchanged.
- README / CONTRIBUTING: no change — README step 4 already documents the TZ
  precedence, the UTC default, "the image imposes no timezone", and the
  post-change recreation step; the "Daemon date variables" bullet and the
  `doc/RECIPE_METHODS.md` section (M1) + `doctor.py` prompt (M2) were
  committed with the S4 delivery. No contributor-rule change.
- Gate: the user confirmed the S6 docs as-is (2026-10-27): the CHANGELOG
  `### Changed` entry, no README/CONTRIBUTING change, 3 doc-only commits.
- Commits: `b59df45` (plans: S5 gate VALIDATED flip), `8249c67` (CHANGELOG
  `### Changed` entry), plus the commit carrying this record; all pushed to
  `origin/dev`.
- S7 note: the code/test/doc delivery commits (`cfb7875` / `99c0f2e` /
  `9c00d83` / `dc0ef7f`) are already on `origin/dev` from the S5 deployment
  prerequisite, so S7's remaining steps are the Gitea `main` promotion
  (ff-only, user gate), the GitHub mirror, the PR #34 close comment + close,
  the issue #26 closure comment + close, and the per-public-update
  Discussion summary — each public text user-confirmed first.

## S7 execution record (2026-10-27, 21:11–21:26Z)

- S7.0 prereq: dev = origin/dev = `53a5dff`, clean tree. The tree moved
  after the S5 confirmation by 4 doc-only commits (`447b23e` / `b59df45`
  plans, `8249c67` the S6-gated CHANGELOG entry, `53a5dff` plans) — the
  Dockerfile COPYs only `apps/requirements.txt` + `apps/`, so the image
  built from `53a5dff` is byte-identical to the validated `dc0ef7f`
  image; PR #33/#32 precedent (doc-only move since the confirmation, no
  re-validation required). PR head still `e1d3787` (unchanged since S1).
- S7.1 dev-commits: nothing new — the 4 S3-confirmed commits
  (`cfb7875` / `99c0f2e` / `9c00d83` / `dc0ef7f`) were already on
  origin/dev (created during S5, since the NAS fetch needed the committed
  tree); the plan-doc/CHANGELOG commits followed.
- S7.2 promote (user gate; executed in the earlier interrupted "continue
  PR #34" session at 2026-10-27T21:08Z): `main` `bde713c` → `53a5dff`
  ff-only, pushed to origin/main; `git diff main dev` empty; no tag (not
  a release). Re-verified this session: main = origin/main = dev =
  origin/dev = `53a5dff`.
- S7.3 mirror (user gate): `sync_github.sh` re-run — the deterministic
  amend reproduces GitHub `main` `6bb3348` (already pushed by the earlier
  session before its interruption; the push reports up-to-date). Public
  gate verified this session: new hash via ls-remote; root listing has no
  `.kilo` / `.vscode` / `.private` / `openwiki` / `AGENTS.md` /
  `.openwikiignore` and `.github/` holds only `ISSUE_TEMPLATE`; all
  integrated #34 content present (variables.py, both new test modules,
  CHANGELOG entries, README bullet, the Berlin-default-free Dockerfile,
  compose `TZ`, the RECIPE_METHODS section, the doctor prompt).
- S7.4 PR #34 close (text user-confirmed as-is 2026-10-27T21:22Z): close
  comment **6453946786**; closed without merge at 2026-10-27T21:25:24Z
  (the change reached GitHub via the mirror, keeping public history
  canonical).
- S7.5 issue #26 (user decision: close as delivered): comment
  **6453947542**; closed at 2026-10-27T21:25:26Z.
- S7.6 Discussion summary: **deferred** (Discussion write API not
  reachable from this environment — confirmed 2026-10-25; same handling
  as PR #32/#33). The user-confirmed draft below is for manual posting in
  the web UI.
- Plan doc: Status DELIVERED; doc-only commit + push to dev; the review
  doc then archived to `completed/` with the cross-references (plans
  README, sequencing) updated.

Discussion summary draft (manual posting, user-confirmed
2026-10-27T21:22Z):

> **Public update: daemon date variables + timezone selection (PR #34,
> issue #26)**
>
> `main` now expands `{{TODAY}}`, `{{DATE_TO}}`, `{{DATE_FROM}}`, and
> `{{TODAY±Nd}}` inside any recipe method-argument string (single pass;
> credentials stay opaque), with a per-task `date_window_days` (default 90
> inclusive days), `YYYY-MM-DD` output with a restricted format suffix,
> hard date bounds, and fail-before-resources validation; the Run-now
> start-date override is memory-only. The image no longer imposes a
> timezone — the zone is selected via `TZ` (shell or root `.env`, UTC
> fallback) and is shared by cron scheduling and calendar dates.
> Integrated from PR #34 (flowcool) via the mirror at 6bb3348;
> maintainer-side additions were the `doc/RECIPE_METHODS.md`
> date-variable section and the recipe-doctor prompt extension.
> Validated: full test suite (589 passed) + regression PASS; image build,
> Docker-context canary (18/5), TZ contract checks (3/3), and compose
> smoke all green on the deploy host. Note for existing installations: set
> `TZ` explicitly if you relied on the previous `Europe/Berlin` default,
> then recreate the daemon.

## Out of scope

- The remaining #24 lane (F10/C8 delivery-state exposure) — maintainer work
  after #34 lands, not part of this PR.
- C4 (F06 result-semantics contract) — draftable after #34 lands.
- The #38 archive-delegation decision (gates PR #41) — separate.
- The Stage 1b recipe-doctor portal conversions — separate; they ride the
  user's portal windows.
- A deploy of this tree to the NAS `main` — a separate user request (the S5
  NAS run validates the dev tree, not a promotion).

## Open questions

- ~~M1/M2 (S6 contract-doc bundle)~~ — resolved at the S3 gate (2026-10-27):
  M1a + M1b + M2 all confirmed as-is.
- ~~The cron-TZ behaviour change~~ — resolved at the S6 gate (2026-10-27):
  the CHANGELOG `### Changed` entry (`8249c67`) states the Berlin default
  removal and the "set `TZ` explicitly" requirement for existing
  installations; README step 4 carries the precedence + recreation note.
  The S7 PR-close comment must repeat the note for the PR's audience.
- ~~S5 gate~~ — confirmed by the user 2026-10-27 (code checks + the NAS
  deployment-validation block all green, record in the Deployment
  validation section; agent via SSH on `origin/dev` `dc0ef7f`, service left
  running on the dev tree).
- ~~S7 gate~~ — confirmed by the user 2026-10-27 (mirror re-run gate
  21:14Z; the PR close comment, the issue #26 close comment, and the
  Discussion draft all confirmed as-is 21:22Z; #26 closed as delivered;
  Discussion deferred per the API limitation — draft recorded, user posts
  manually). S7 complete — DELIVERED.
