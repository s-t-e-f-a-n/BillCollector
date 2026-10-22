# PR #22 review — phased login with a durable failure budget

> Status: AWAITING-DECISION (2026-10-22) — S2 plan complete: verdict
> approve with maintainer changes; per-file integration plan and validation
> plan finalized; awaiting user decision.

## PR metadata

- PR: #22 on `s-t-e-f-a-n/BillCollector` (public mirror), open, not draft
- Title: feat: protect phased login attempts with a durable failure budget
- Author: flowcool; created 2026-10-20T19:21:56Z, updated 2026-10-22T22:03:13Z
- Head: `58f569ada20419f7aee3de12f6e0444c8e4b4803`, branch
  `feature/playwright-safe-login-upstream` (flowcool/BillCollector), tree
  `0d4f2ca6abb5945eddba03e43172332692754330` (matches the PR body claim)
- GitHub base ref: `main` (`d2affd2`); merge-base with `github/main`:
  `baa4046` (2026-10-19, ~45 commits / 3 days behind main)
- Issue refs: #20 ("Agree single-attempt login, persistent failure budget
  and explicit unlock"), open. Maintainer agreement comment on issue #20
  posted 2026-10-22T22:03:09Z: all five contract decisions accepted
  (recipe login transaction, separate persistent block, uncertain-submit
  consumption, one-attempt clear, existing pause deadline in v1).
- AI disclosure: Codex implemented + tested; Claude reviewed the fork diff;
  earlier agent/CodeRabbit findings addressed.
- GitHub diff stats (inflated by structure): 86 files, +1499/−15199.
- Real author change (`4508909..58f569a`): 13 files, +1427/−19.

Local state at review time:

| ref | tip |
|---|---|
| Gitea `dev` | `8dcd1d93c3e4b6c53da568fcd843fb881a5a08a4` |
| Gitea `main` | `44ad25cddd76a3ca3ecdef652f7657cca401474d` |
| GitHub `main` | `d2affd259268017e71c535a427e75a6e3f181b23` |

PR #23's chain is DELIVERED (plan in completed/); no parallel pr-review
chain is active.

## Verified facts

- Fetched `refs/pr/22` head `58f569a` from GitHub (re-fetchable; S4
  preflight must re-verify the hash — the author is active).
- The PR branch is a squashed resubmission: commit 1 `4508909`
  "docs: changelog, readme: document the self-hosted daemon and web UI" is
  an orphaned recommit of public-main commit `3b406f0` (same message; tree =
  `3b406f0` tree minus the 71 private files the raw lineage carries but the
  sanitized tip does not). Commit 2 `58f569a` is the squashed feature.
- All 71 deletions in the GitHub diff are private paths (`.kilo/`,
  `.private/`, `.vscode/`, `openwiki/`, `AGENTS.md`, `.openwikiignore`,
  `.github/workflows/openwiki-update.yml`); every one is already absent from
  the current `github/main` tree → comparison artifacts, never applied.
  (No private path is added by the PR head.)
- PR-head `CHANGELOG.md` and `README.md` are the `3b406f0` versions, stale
  vs current main (−53 / −268 lines). The author did not add a CHANGELOG
  entry for the feature → S6 authors one.
- Pre-image check vs Gitea `dev` (`8dcd1d9`):
  - New files (absent in dev): `apps/billcollector/login.py`,
    `doc/SAFE_LOGIN.md`, `tests/test_bc_login.py`.
  - Clean pre-image (hunks apply as-is): `notify.py`, `orchestrator.py`,
    `recipes.py`, `ui/dashboard.py`, `ui/task_detail.py`,
    `recipe-pw-schema.yaml`, `tests/conftest.py`, `tests/test_bc_ui_task_detail.py`.
  - Diverged: `db.py`, `runner.py`. Empirical `git apply --3way` of the
    author diff on the dev tree: `runner.py` auto-merges (the only context
    clash is the import block, where dev added the redaction import);
    `db.py` produces exactly one mechanical conflict — both sides insert
    methods at the same spot after `claim_task_run` (dev's
    `import_ini(..., force=False)` vs the PR's new login methods).
    Resolution keeps both.
- Dev moved since the PR base by the M3/M4 work (daemon, onboarding wizard,
  compose, vault Settings, redaction, residual logs). Of the PR's 13 files
  only `db.py` and `runner.py` were also touched by dev in the overlap
  window (see above).
- Both runner entry paths (daemon spawn via `cli.py run` and direct CLI)
  pass through the new `run_task` flock wrapper. `BC_PROFILE_ROOT` (new
  conftest env var) and `ui_base_url` (notification link) are existing
  config/settings keys. `NTFY_TIMEOUT = 10` already exists in notify.py.
- `apps/.venv` has pytest 9.1.1; nicegui + playwright importable.

## Code review findings

New module `apps/billcollector/login.py` (122 lines, validation only):
one top-level login block per recipe; explicit single success locator with a
per-locator-kind allowed-option set; ordered phases (steps/submit/success,
last phase must prove the final success locator); preparation limited to
locator chains ending in `fill`; submit chains end in `click` or
`press(Enter)`; positive-integer limits with defaults
(`max_failures=2`, `timeout_ms=10000`, `session_timeout_ms=1000`); rejects
nested/graceful login, unknown arguments, mixed shorthand/phases.
`settle_attempt` settles at most once and notifies only on the transition
to blocked. No existing behavior changed.

`db.py`: five additive `Task` columns (`login_failures`,
`login_failure_limit` default 2, `login_locked`, `login_cycle_active`,
`login_pending_run_id`) with an ALTER-based migration and a conservative
cycle-preservation UPDATE for old candidates (a stored limit of 1 or any
prior failure/lock keeps the cycle active until session proof).
`claim_task_run` refuses locked or pending tasks. New methods:
`release_task_run` (guarded by `NOT EXISTS` active Run so a rejected
contender cannot release another runner's task), `reserve_login_attempt`
(atomic; the effective limit is `MIN(stored, recipe)` so raising the recipe
limit mid-cycle grants nothing), `settle_login_attempt` (idempotent; locks
at the limit), `login_succeeded` (only the owning run that is still
unfinalized can reset), `clear_login_lock` (idle + locked only; grants
exactly one attempt; preserves enabled/cron/profile).

`notify.py`: new `notify_login_locked` (best-effort ntfy push; topic from
settings; deep link only when `ui_base_url` is set; message carries task id
and failure count, no portal errors or secrets) and `_send_login_locked`
(10 s timeout; logs the exception type name only). Dispatch off the daemon
event loop via the orchestrator; synchronous in the runner process. Existing
notification paths untouched.

`orchestrator.py`: `_dispatch_notification` sends via `asyncio.to_thread`,
retains jobs until `shutdown()` awaits them. `cleanup_orphans` settles
interrupted rows and adds a second pass for tasks whose pending run row is
already finalized (crash window between finalization and settlement),
skipping runs whose pid is still alive. `shutdown`, `_finalize_run` (both
row and no-row paths) and the start_run cancel/spawn-failure paths use
`release_task_run` instead of unconditional `set_task_status(idle)`.

`runner.py`: `run_task` is now a flock wrapper (`DATA_DIR/task-locks/
task-<id>.lock`, `LOCK_EX | LOCK_NB`, file never unlinked) around the
renamed `_run_task`; admission refuses a blocked or pending task before
recipe/vault/display access and re-validates the login contract at run
start. Login steps route to `_execute_login`: a visible success locator
skips the whole block and resets the budget via session proof; a resume
scan finds the latest completed phase before any credential dispatch; one
durable reservation precedes the first submit; each phase submits exactly
once; an uncertain submit (any exception, including locator/DB errors)
consumes the reserved attempt without retry; settlement happens once on
every finalization path; a pause/resume loop only verifies the final proof
and never re-submits. Direct CLI runs now also set the task to running
after `create_run`.

`recipes.py`: `validate_recipe` runs `validate_login_recipe` after schema
validation (contract errors fail before vault/browser use); `_step_entry`
includes `submit` and `phases` in the recipe tree shown in the UI;
`_CHAIN_END_METHODS` gains `login`.

UI: dashboard gains a Login column (blocked / pending / available),
Run-now is disabled and bulk run skips blocked tasks; task detail gains the
login state label (state + unproven attempts / limit), disables Run while
blocked, and adds a "Clear login block" button (confirm dialog, enabled
only when idle and blocked).

`recipe-pw-schema.yaml`: additive `phases` (minItems 1; items require
submit+success, no additional properties) and `submit` on the step
definition; `success` is a loose object — the strict option set is enforced
in `login.py`.

`doc/SAFE_LOGIN.md` (new, 169 lines): contract, candidate recipe example,
persistence/recovery semantics, requirement-to-test map (27 rows),
boundaries and rollback. States the contract is a candidate "not approved
for deployment" and that "Stefan has not agreed the recipe or database
interface" — stale after the 2026-10-22 agreement; S6 should fix that
sentence on integration. Also discloses an early fork-stage test incident
where the default public ntfy transport was contacted (delivery unknown;
subsequent runs force isolated paths and mock/deny the transport).

Tests: `tests/test_bc_login.py` (new, 710 lines) — DB-level (double
migration, durable budget across connections, idempotent settlement,
concurrent reservation, limit-raise refusal, prior-candidate migration),
runner-level against a real loopback HTTP portal and headless chromium
(one submit per phase, resume never resubmits, threshold block + clear
grants one attempt, session skip + reset, two-phase counts one transaction
across 4 parameterizations, interruption between phases keeps one durable
attempt, ambiguous submit consumes, preparation failure consumes nothing),
daemon-level (orphan cleanup settles + keeps lock, monitor finalization
cannot remove the lock, blocked manual/scheduled admission never spawns,
slow mocked notification keeps four daemon lifecycle paths responsive),
process-level (subprocess crash after reservation recovers without replay,
crash between finalization and settlement recovers, concurrent direct entry
stops before execution), contract negative tests, notification mocked once
per block, base-URL link behavior, plus 3 UI tests in
`test_bc_ui_task_detail.py` (clear grants one attempt and preserves config;
clear unavailable while active; pending distinct from blocked).

`tests/conftest.py`: env vars now forced instead of setdefault
(`BC_DB_FILE`, `BC_PROFILE_ROOT` added — both existing config keys), and an
autouse fixture denies non-loopback `socket.connect`/`connect_ex` for every
test and restores SIGINT/SIGTERM handlers per test. This hardens the whole
suite, not just the new tests — the S5 full-suite run covers it.

Test/security review: no secrets in code, tests, or artifacts (synthetic
credentials only); loopback-only sockets plus a notification-mock guardrail
(double safety after the disclosed ntfy incident); defaults, limit
semantics, and clear behavior are pinned by tests; no new network exposure
(reuses the existing `NTFY_HOST` transport pattern); no exit-code changes.

## Process check (CONTRIBUTING.md)

- Issue referenced: yes, #20, in the PR body and SAFE_LOGIN.md.
- Shared interfaces (DB schema, recipe contract): agreed in issue #20 on
  2026-10-22 (all five decisions). Note: the code was written before the
  agreement, but the PR was explicitly submitted as pending agreement;
  agreement is now in place before integration.
- Intended behavior + verification stated: yes (PR body, SAFE_LOGIN.md,
  requirement-to-test map).
- Proof shipped: pytest suite claim (357 passed, 2 skipped, 37 subtests on
  the fork), ruff 0.1.17.0 clean, bandit 1.9.4 at the 16-finding baseline
  with nothing in changed files, earlier credential-free historical
  regression passed. S5 re-runs everything on the dev tree.
- AI assistance disclosed: yes (Codex + Claude review).
- No secrets; no new network exposure; one focused change per PR: yes.

## Cross-PR

Open PRs: #19 (flowcool, "add bounded Playwright collection actions",
79 files) and #22. File overlap with #19: `recipes.py`, `runner.py`,
`recipe-pw-schema.yaml`. Whichever integrates second must re-run the
pre-image checks at its S4 preflight (dev moved); no correctness
dependency on merge order. #22 is the active chain.

## Risks

1. `db.py` mechanical conflict (method insertion point) — resolution keeps
   dev's `import_ini(force=...)` signature plus the PR's new login methods;
   trivial but must be eyeballed in S4.
2. `conftest.py` env forcing + socket guard affects every test — S5 must
   run the full suite, not only the PR tests.
3. The fork base is 3 days behind dev (M3/M4 work). Textual auto-merge
   covers `runner.py`; interaction risk with the new redaction/vault
   Settings code paths is low (the PR does not touch `_fresh_otp` /
   `_vault_preflight`) but the full regression is the proof.
4. `doc/SAFE_LOGIN.md` carries the now-stale "not agreed" sentence — S6
   updates it.
5. The author is active; the head hash must be re-verified at S4 preflight.
6. Deployment: the PR touches no Dockerfile, compose, install/deploy
   scripts, INI keys, or `.env` handling. New runtime state is a
   `task-locks/` directory under the existing data dir plus the additive
   Task columns. S5 records "not deployment-relevant" unless the user
   decides otherwise.

## Verdict

**Approve with maintainer changes.**

- The implementation matches the contract agreed in issue #20 on
  2026-10-22 (single-attempt login transaction, durable failure budget,
  uncertain-submit consumption, one-attempt clear, existing pause deadline in
  v1).
- No existing behavior changed outside the login-protection scope; the new
  runtime state is additive (five `Task` columns, `task-locks/` dir under the
  existing data dir).
- The test suite is comprehensive (DB / runner / daemon / process levels,
  27-row requirement-to-test map) and the CONTRIBUTING process check passes.
- The four maintainer-side changes below are integration-side adaptations;
  none changes the PR's intent:
  1. Manual resolution of the single `db.py` conflict (keep dev's
     `import_ini(..., force=False)` signature plus the PR's login methods).
  2. `doc/SAFE_LOGIN.md`: update the stale "Stefan has not agreed the recipe
     or database interface" sentence to reflect the 2026-10-22 agreement.
  3. CHANGELOG entry authored by the maintainer in S6 (the author added
     none; the PR-head `CHANGELOG.md` is stale and is skipped).
  4. Skip the stale PR-head `README.md` (dev version stays).

## Integration plan

Apply from the PR head (`refs/pr/22`), file by file:

| File | Action | Note |
|---|---|---|
| `apps/billcollector/login.py` | apply | new; no conflict |
| `apps/billcollector/db.py` | manual | one mechanical conflict after `claim_task_run` (dev's `import_ini(..., force=False)` vs the PR's login methods) — keep both, eyeball in S4 |
| `apps/billcollector/runner.py` | apply | auto-merges; verify the import block (dev redaction import + PR login import) |
| `apps/billcollector/notify.py` | apply | clean pre-image |
| `apps/billcollector/orchestrator.py` | apply | clean pre-image |
| `apps/billcollector/recipes.py` | apply | clean pre-image |
| `apps/billcollector/ui/dashboard.py` | apply | clean pre-image |
| `apps/billcollector/ui/task_detail.py` | apply | clean pre-image |
| `apps/recipes_playwright/recipe-pw-schema.yaml` | apply | clean pre-image; additive `phases` / `submit` |
| `doc/SAFE_LOGIN.md` | apply + maintainer edit | stale "not agreed" sentence updated (recorded in S6) |
| `tests/conftest.py` | apply | clean pre-image; forced env vars + socket guard affect the whole suite |
| `tests/test_bc_login.py` | apply | new |
| `tests/test_bc_ui_task_detail.py` | apply | clean pre-image |

Skip (dev versions stay):

- `CHANGELOG.md` — stale in the PR head (−53 lines vs dev); maintainer
  authors the entry in S6.
- `README.md` — stale in the PR head (−268 lines vs dev).
- The 71 private-path deletions — comparison artifacts, already absent from
  the current `github/main`.

Commits to create in S7 (dev-commits, one concern each):

1. `feat:` code — `login.py`, `db.py`, `runner.py`, `notify.py`,
   `orchestrator.py`, `recipes.py`, `ui/dashboard.py`, `ui/task_detail.py`,
   `apps/recipes_playwright/recipe-pw-schema.yaml`.
2. `test:` tests — `tests/test_bc_login.py`, `tests/conftest.py`,
   `tests/test_bc_ui_task_detail.py`.
3. `doc:` docs — `doc/SAFE_LOGIN.md` (with the maintainer edit) +
   `CHANGELOG.md` entry.

## Validation plan

Run on the exact dev tree that will be promoted, from the repo root:

1. PR unit tests:
   `LC_ALL=C apps/.venv/bin/python -m pytest tests/test_bc_login.py -v`
   -> all pass (DB-level, runner-level against the loopback portal +
   headless chromium, daemon-level, process-level; runner tests need
   playwright chromium, present in the venv).
2. Full suite (the `conftest.py` change affects every test — risk #2):
   `LC_ALL=C apps/.venv/bin/python -m pytest tests/ -q` -> 0 failures.
   Fork claim: 357 passed, 2 skipped, 37 subtests; counts on the dev tree
   may differ slightly — any new failure is diagnosed before promotion.
3. End-to-end regression:
   `apps/.venv/bin/python tests/run_regression.py --ini
   tests/bc_regression.ini` -> exit 0, VERDICT: PASS (7 scenarios / 8 PDFs).
   Exit codes follow the deploy-skill semantics (exit 3 = a real run holds
   the lock; stop it first).
4. Lint / security on the changed files:
   ruff (F821, E4/E7/E9) + bandit -> nothing new beyond the known baseline
   (B608 dynamic SQL table names, B104 UI bind).
5. Deployment-process validation: **not triggered** — the PR touches no
   Dockerfile, compose, install/deploy scripts, INI keys, or `.env`
   handling (risk #6). The skip is recorded with the user confirmation at
   S5.

## Deployment validation

Not triggered at S1 (no deployment-relevant files). To be recorded with the
user-confirmed skip (or run) at S5.

## Out of scope

- Deployment to the NAS (separate decision after integration, per the
  issue #20 agreement).
- The 71 private-path deletions and the stale CHANGELOG/README in the PR
  head (comparison artifacts; dev versions stay).
- PR #19 (separate chain).
- The pre-existing state of the public GitHub history (older commits carry
  private files because the mirror amends the tip only). Not introduced or
  changed by this PR.

## Open questions

All resolved at S2:

1. S6 CHANGELOG entry: authored by the maintainer (the author added none).
   -> Confirmed: the maintainer authors it in S6.
2. `doc/SAFE_LOGIN.md` "Stefan has not agreed" sentence: update on
   integration, or leave to the author?
   -> Resolved: the maintainer updates it on integration (S4 apply, recorded
   in S6); the closing PR comment notes it.
3. Ordering with PR #19: #22 proceeds first (it is the active chain); #19
   re-runs pre-image checks if integrated later. -> Confirmed.
