# PR #54 review: rebuild persistent jobs before scheduler resume (issue #47)

> Status: AWAITING-DECISION (2026-10-30) — S1+S2 done: verdict approve with
> maintainer changes (M1, CHANGELOG placement); code/tests apply as-is. S2 gate
> passed 2026-10-30 (verdict + doc-only commit confirmed); S3 proposal next.

## PR metadata

- PR: s-t-e-f-a-n/BillCollector#54 "fix: rebuild persistent jobs before
  scheduler resume" (flowcool), branch `fix/upstream-persistent-jobstore-20261030`,
  head `7f6cb02f3c39869403d526372201f5940b6f8743`. Two commits in the fetched
  ref (orphaned public tip `e83c8e2` + the fix commit `7f6cb02`); the real
  content is **3 files +42/−4** against the branch point `e83c8e2`.
  `mergeable_state: clean` (vs base `main` @ `a24668a`).
- Issue: #47 (flowcool, 2026-10-30T20:00:47Z) — `TaskScheduler.start()` runs
  the startup resync before APScheduler loads its persistent SQLAlchemy job
  store, so cached jobs of disabled/deleted tasks survive and can fire.
- Created 2026-10-30T20:04:42Z (issue 4 minutes before the PR).
- Local state at review time: Gitea `dev` tip `35b4e18` (= `origin/dev`; PR #53
  plan record only, no code since `main`), Gitea `main` `fa1ade5`, GitHub `main`
  `a24668a`.
- AI disclosure present: "AI-assisted focused port, source review and synthetic
  verification under my responsibility."

## Verdict

**Approve with maintainer changes** — one placement fix (M1, CHANGELOG); all
code and tests apply as-is from head.

## Verified facts

1. Head stable: fetched `refs/pr/54` = `7f6cb02f...`; PR `updated_at`
   2026-10-30T22:39:18Z predates the fetch. S4 preflight re-checks via
   `git ls-remote github refs/pull/54/head`.
2. Branch point: the fork starts at the orphaned public tip `e83c8e2` (GitHub
   `main` at the PR #41 delivery). `e83c8e2` is **not** an ancestor of the
   current GitHub `main` `a24668a` (each mirror sync re-pushes the Gitea
   lineage plus one amended sanitized tip, orphaning the previous public tip).
   The GitHub "Files changed" view (101 files, +155/−23388, showing deletions of
   `.kilo/`, `openwiki/`, `AGENTS.md`, …) is an orphaned-tip STRIP artifact,
   not PR content — the same pattern as #45's 103-file diff. Integration
   applies the 3-file delta against `e83c8e2` only.
3. Issue #47 before-claim verified against the pinned APScheduler 3.11.3: in
   the old `start()`, `resync()` ran **before** `_scheduler.start()`, so
   `get_jobs()` saw an empty in-memory table; the persistent
   `apscheduler_jobs` rows are loaded by the jobstore **at** scheduler start,
   i.e. after the rebuild → stale jobs of disabled/deleted tasks survived.
   `next_run_time` is a `Float(25)` UTC timestamp in the pinned jobstore, so
   the test's `UPDATE apscheduler_jobs SET next_run_time=0` is a valid
   overdue state (not an ISO-string parse hazard).
4. Pre-image vs Gitea `dev` (drifted from `e83c8e2` by the PR #53 weekday
   fix): `scheduler.py` diverges in regions PR #54 does not touch (`import re`,
   module-level `cron_trigger()`, the `_add_job_for` try/except wrapper);
   `tests/test_bc_scheduler.py` diverges in the imports and the trailing
   `CronWeekdayTests` block. `git apply --check` of both PR hunks on a scratch
   worktree of `dev` → **clean, no 3way needed**.
5. The new test uses the public `scheduler` property (present on
   `TaskScheduler`) — `fresh.scheduler.get_jobs()` is valid; stub recording
   callback, temporary SQLite DB, no real collection. The callback-routing
   subtlety is correct: the fresh constructor re-points the module-global
   `_run_callback`, so a stale fire would land in the test's `calls` list, not
   the base `self.calls`.
6. `ui/app.py:142` calls `scheduler.start()` unguarded; the old code also
   propagated `resync()` failures out of `start()` (daemon startup failure) →
   failure-path semantics unchanged; the new code additionally shuts down the
   owned scheduler on failure (issue #47: "Shutdown the owned scheduler if
   resync fails").
7. No shared-interface change: no DB schema migration (the
   `apscheduler_jobs` table is APScheduler's own cache, structure unchanged),
   no control protocol, no recipe contract, no exit codes. The issue states
   "Task data remains authoritative; no schema change"; the PR implements
   exactly that.
8. Cross-PR: open PRs #44, #45, #55, #56 (all flowcool, batch 2, same base).
   None touches `scheduler.py` or `test_bc_scheduler.py` (heads checked against
   the merge base). Only shared file is CHANGELOG (manual merge regardless).
   Sequencing doc: #54 is next in the batch-2 chain, after #53.
9. The PR's test-count claim (10 passed) matches the head file: 6
   `JobSyncTests` + 4 `PersistenceTests`.

## Code review findings

`apps/billcollector/scheduler.py`:

- `start()`: now `_scheduler.start(paused=True)` → `resync()` in a try/except
  (on failure: `shutdown(wait=False)` + re-raise) → `resume()`. The persistent
  jobstore loads at scheduler start, **before** the rebuild, while paused —
  nothing can fire mid-rebuild — and the rebuild drops the loaded stale jobs.
  Docstring ("Re-sync all jobs from the Task table and start the scheduler.")
  remains accurate.
- `resync()`: `for job in list(get_jobs()): job.remove()` →
  `remove_all_jobs()`. Removes every job from memory **and** the store
  (deletes all `apscheduler_jobs` rows). This also fixes the
  resync-when-not-started path: the old code removed only in-memory jobs, so
  persisted rows survived a not-started `resync()` (the existing
  `PersistenceTests` passed trivially there); the new one actually clears the
  store.
- Unchanged: `stop()`, `sync_task()`, `_add_job_for()`, `_remove_job()`,
  `_task_job` target, module docstring.

`tests/test_bc_scheduler.py` — new
`PersistenceTests.test_start_drops_persisted_disabled_and_deleted_jobs_before_firing`:
creates two enabled cron tasks, one start/stop cycle (jobs persist), disables
one + deletes the other, forces the persisted rows overdue
(`next_run_time=0`), then runs a fresh `TaskScheduler` with a recording
callback through a real `start()` and asserts: in-memory job list empty, store
row count 0, and no callback invocation after a short sleep. Deterministic,
isolated (temp SQLite, stub callback), and mirrors the issue's reproduction 1:1.

`CHANGELOG.md` — see M1.

Nit (no action): the `asyncio.sleep(0.01)` after resume — the primary
assertions (jobs empty, store empty) do not depend on timing; `calls == []`
is a belt-and-braces firing check.

## Risks

- A `resync()` failure during `start()` now shuts down the scheduler it
  started before propagating — strictly cleaner than before; daemon startup
  still fails (unchanged semantics at `ui/app.py:142`).
- `remove_all_jobs()` drops **all** store rows, including any row not tied to
  a Task (orphaned rows) — that is the module docstring's intent ("The
  jobstore is a cache — the Task table always wins").
- Issue #47 opened 4 minutes before the PR (no maintainer pre-agreement
  comment). The issue body itself specifies the full expected behavior ("Load
  the job store while paused, rebuild it from Task, then resume. Task remains
  authoritative. Shutdown the owned scheduler if resync fails. No
  task/schema migration or change to configured cron semantics."), and the PR
  implements it exactly. Accepted with a note (same pattern as #46).

## Integration plan (S3/S4, Gitea dev)

| File | Action |
|---|---|
| `apps/billcollector/scheduler.py` | apply as-is from `refs/pr/54` (+8/−4) |
| `tests/test_bc_scheduler.py` | apply as-is from `refs/pr/54` (+29) |
| `CHANGELOG.md` | manual (M1): move the PR entry text into the existing `### Fixed` subsection of `## [Unreleased]` (prepended); drop the PR's new `### Fixed` header inserted above `### Added` (Keep a Changelog order + duplicate header) |

Critical: apply the 3-file delta against `e83c8e2`
(`git diff e83c8e2..refs/pr/54`), **not** the 101-file merge-base diff (which
"deletes" maintainer-private paths on the dev side).

No other maintainer-side changes. Expected S4 tree: 3 dirty files.

M1 entry text (from the PR, kept verbatim):

> - Load the persistent scheduler job store while paused, rebuild it from Task,
>   then resume (#47). Disabled or deleted tasks cannot fire stale overdue
>   jobs.

## Validation plan (S5, exact dev tree, repo root, venv)

- PR tests: `apps/.venv/bin/python -m pytest tests/test_bc_scheduler.py -q`
  → expected 10 passed (the PR's claim).
- Before/after proof: the new test must **fail** against the pre-integration
  dev `scheduler.py` (S5 records it on a scratch worktree — proves the fix,
  not just the test).
- Full unit: `apps/.venv/bin/python -m pytest tests/ -q --tb=short` → all
  green (dev baseline 651 passed / 10 skipped / 68 subtests per the PR #53 S5
  record + the 1 new test; S5 records the actual count).
- Full regression: `apps/.venv/bin/python tests/run_regression.py --ini
  tests/bc_regression.ini` → exit 0 (7 scenarios / 8 PDFs, VERDICT: PASS).
- ruff (F821, E4/E7/E9) + bandit on the changed files → nothing new beyond the
  known baseline (B608 dynamic SQL table names, B104 UI bind).

## Deployment validation

Not deployment-relevant: the PR touches only `scheduler.py`, tests, and
CHANGELOG — no `Dockerfile`, `.dockerignore`, `BillCollector.sh`,
`install_docker-image.sh`, `deploy_remote.sh`, no INI keys or `.env`
handling. Block skipped; recorded here + user-confirmed at the S5 gate.

## Out of scope

- Numeric weekday parsing (delivered in #46/PR #53; issue #47 keeps it
  separate explicitly).
- The legacy cron-driven batch path (OS cron, deprecated).
- APScheduler upgrades / non-persistent jobstore setups (pinned 3.11.3, single
  default jobstore).

## Open questions

- None. S2 gate passed 2026-10-30 (verdict approve with M1 confirmed,
  doc-only commit + push approved).

## Execution record

- S1+S2 (2026-10-30, "continue pr 54" session): no prior plan doc existed
  (PR #53 had just been DELIVERED) → fresh S1 review. Head fetched to
  `refs/pr/54` (`7f6cb02f...`); merge-base analysis untangled the orphaned-tip
  base (`e83c8e2`, not an ancestor of `a24668a`); real content = 3 files;
  pre-image check green (hunks apply cleanly on `dev` scratch worktree);
  issue #47 before-claim verified against pinned APScheduler 3.11.3
  (`Float(25)` next_run_time);   cross-PR check: no scheduler overlap with
  #44/#45/#55/#56. Verdict: approve with M1. Plan doc created
  (Status: AWAITING-DECISION); S2 gate passed — doc-only commit (plan doc +
  README + sequencing) pushed to `origin/dev`; the commit hash is recorded in
  the S3 entry.
