# PR #53 review: crontab weekday numbering (issue #46)

> Status: INTEGRATING (2026-10-30) — S3 gate passed (M1 confirmed as-is) +
> S4 integration applied (3 files as-is from head `6b41040b` + M1 CHANGELOG
> placement); tree dirty for S5; next S5 validation.

## PR metadata

- PR: s-t-e-f-a-n/BillCollector#53 "fix: use crontab numbering for numeric
  weekdays" (flowcool), branch `fix/upstream-cron-weekdays-20261030`, head
  `6b41040b542618c3b59b98a84765baef54408336`, 1 commit, base `main` @
  `e83c8e2`. 4 files +84/−4. `mergeable_state: clean`.
- Issue: #46 (flowcool, 2026-10-30T20:00:20Z) — numeric Sunday schedules fire
  on Monday because APScheduler 3.11.3 numbers Monday=0; `7` is refused.
- Created 2026-10-30T20:02:59Z (issue 2 minutes before the PR).
- Local state at review time: Gitea `dev` tip `925223f` (= `origin/dev`; PR #41
  plan record only, no public code changes since `main`), Gitea `main`
  `74ba171`, GitHub `main` `e83c8e2`.
- AI disclosure present: "AI-assisted port, review and verification under my
  responsibility."

## Verdict

**Approve with maintainer changes** — one placement fix (M1, CHANGELOG); all
code and tests apply as-is from head.

## Verified facts

1. Head stable: `git ls-remote github refs/pull/53/head` = `6b41040b...` =
   fetched `refs/pr/53`. Single commit on merge-base `e83c8e2` (= current
   GitHub `main`); no orphaned public-history commits (unlike #40/#41).
2. Issue #46 before-claim verified live on the pinned APScheduler 3.11.3:
   `CronTrigger.from_crontab("0 0 * * 0")` → next fire Monday 2026-11-02;
   `0 0 * * 7` → rejected ("the last value (7) is higher than the maximum
   value (6)").
3. Pre-image: all 4 PR files byte-identical between Gitea `dev` and the PR
   base `e83c8e2` → hunks apply cleanly. Dev drift since the merge base is
   only private agent-context paths (`.kilo/`, `.private/`, `.vscode/`,
   `openwiki/`, `AGENTS.md`, `.openwikiignore`, `.github/workflows/`) — zero
   overlap with the PR's paths.
4. `CronTrigger.from_crontab` has exactly two call sites in the codebase
   (`scheduler.py:116` in `_add_job_for`, `ui/tasks.py:37` in `_valid_cron`);
   the PR converts both to the shared `cron_trigger` → the issue's "one parser
   for UI validation and scheduler construction" acceptance is fully covered.
5. All five #46 acceptance points are covered: single parser; 0/7 = Sunday and
   1 = Monday; lists, ascending ranges and steps keep cron numbering; named
   weekdays retain the pinned parser's behavior; an invalid stored expression
   skips only that task while the others start.
6. The documented ambiguous rejections (`1/2`, `mon-5`, `01`, `*/02`) are
   implemented by the weekday regex and covered by the UI-level test
   (`test_ui_and_scheduler_share_numeric_weekday_validation`).
7. `ZoneInfo("Europe/Zurich")` resolves in `apps/.venv` (pinned tzdata), so the
   new Europe/Zurich test runs on the standard gate.
8. The PR's full-suite count (708 passed) was measured on the candidate head,
   not on dev — S5 re-runs everything on the exact dev tree.

## Code review findings

`apps/billcollector/scheduler.py` — new `cron_trigger(expression, timezone)`:

- Splits the five-field expression; the weekday field is processed per item:
  items without digits (named) pass through unchanged; numeric items must
  fullmatch `(\*|[0-7](?:-[0-7])?)(?:/([1-9][0-9]*))?` and are converted to
  named days via `names[day]` (0/7 → "sun"), so APScheduler's Monday=0 never
  sees a numeric weekday.
- Guards: non-5-field → ValueError; `*` → 0..6; ranges must ascend; a step on
  a single day is refused (`1/2`); step `0`/`02` and `8` are refused by the
  regex; unicode-digit input fails the regex → refused (safe).
- `dict.fromkeys` dedupes (`0,7` → `sun`); the rebuilt field is joined back
  before `CronTrigger.from_crontab`; all other fields keep the pinned parser.
- `_add_job_for` wraps trigger construction in try/except ValueError →
  `logger.error("Task %s not scheduled: invalid cron (%s)", task["id"], exc)`
  and returns; the other tasks still schedule. The log carries the task id and
  a fixed/field-level exception message — no cron expression, no secret.
- Behavior change: previously an invalid stored cron raised inside `resync()`
  and propagated out of `start()` (daemon start failure); now that task is
  skipped with an error log — exactly #46 acceptance point 5.

`apps/billcollector/ui/tasks.py` — `_valid_cron` now calls the same
`cron_trigger`; the editor gate and the scheduler share one parser.

`tests/test_bc_scheduler.py` — new `CronWeekdayTests` (3 methods, 15 subtests:
Sunday equality of `0`/`7`/`sun`/`0,7` from a Friday start in
Europe/Zurich; ranges/lists/steps numbering from a Sunday start; five
rejections) + one module-level pytest function for UI/scheduler parity (valid
set + the four documented ambiguous rejections). Every subtest expectation was
traced against the implementation — consistent.

`CHANGELOG.md` — see M1 in the Integration plan.

Nit (no action): the new tests are appended after the
`if __name__ == "__main__": unittest.main()` guard — they do not run under
direct script invocation, but they do under pytest (the repo gate).

## Risks

- Stored numeric weekday schedules shift their fire day after the upgrade
  (they ran one day off under APScheduler's Monday=0). The CHANGELOG entry
  tells users to review numeric schedules before upgrade and to use named
  weekdays when rolling back to an older binary. Accepted: the fix restores
  the documented crontab semantics the UI already advertises.
- Named pass-through depends on the pinned APScheduler (3.11.3) named-day
  parsing; a future upgrade that changed it would be caught by the parity
  test.
- Issue #46 opened 2 minutes before the PR (no maintainer pre-agreement
  comment). The issue body itself specifies the full expected behavior, the
  fix matches the documented crontab semantics, and no shared interface (DB
  schema, control protocol, recipe contract, exit codes) changes. Accepted
  with a note.

## Integration plan (S3/S4, Gitea dev)

| File | Action |
|---|---|
| `apps/billcollector/scheduler.py` | apply as-is from `refs/pr/53` (+42/−1) |
| `apps/billcollector/ui/tasks.py` | apply as-is from `refs/pr/53` (+2/−3) |
| `tests/test_bc_scheduler.py` | apply as-is from `refs/pr/53` (+34) |
| `CHANGELOG.md` | manual (M1): move the PR entry text into the existing `### Fixed` subsection of `## [Unreleased]` (prepended); drop the PR's new `### Fixed` header inserted above `### Added` (Keep a Changelog order + duplicate header) |

No other maintainer-side changes. Expected S4 tree: 4 dirty files.

M1 entry text (from the PR, kept verbatim):

> - Parse numeric cron weekdays with crontab numbering (0/7 Sunday, 1 Monday)
>   in both the task editor and scheduler (#46). Invalid stored schedules are
>   skipped with their task id. Ambiguous legacy forms `1/2`, `mon-5`, `01` and
>   `*/02` are rejected; use named weekdays before rolling back to an older
>   binary.

## Validation plan (S5, exact dev tree, repo root, venv)

- PR tests: `apps/.venv/bin/python -m pytest tests/test_bc_scheduler.py
  tests/test_bc_ui_task_detail.py -q` → expected 24 passed, 15 subtests (the
  PR's claim).
- Full unit: `apps/.venv/bin/python -m pytest tests/ -q --tb=short` → all
  green (dev baseline 647 + the new tests; S5 records the actual count).
- Full regression: `apps/.venv/bin/python tests/run_regression.py --ini
  tests/bc_regression.ini` → exit 0 (7 scenarios / 8 PDFs, VERDICT: PASS).
- ruff (F821, E4/E7/E9) + bandit on the changed files → nothing new beyond the
  baseline (four known medium-or-higher signatures on the apps tree; B608/B104
  baseline).

## Deployment validation

Not deployment-relevant: the PR touches only `scheduler.py`, `ui/tasks.py`,
tests, and CHANGELOG — no `Dockerfile`, `.dockerignore`, `BillCollector.sh`,
`install_docker-image.sh`, `deploy_remote.sh`, no INI keys or `.env` handling.
Block skipped; recorded here + user-confirmed at the S5 gate.

## Out of scope

- Persistent job-store startup ordering (issue #47, PR #54 — next in the
  chain; #53 deliberately leaves numeric parsing out of that change).
- The legacy cron-driven batch path (OS cron, deprecated).
- Numeric parsing of the non-weekday fields (minute/hour/day-of-month/month
  keep the pinned parser; only the weekday field was ambiguous).

## Open questions

- None. S3 gate passed 2026-10-30 (M1 confirmed as-is).

## Execution record

- S1+S2 (2026-10-30, "continue last sessions" session): plan doc created,
  verdict approve with M1; commit `8c9a17d` (plan doc + sequencing + README),
  pushed to `origin/dev`.
- S3 (2026-10-30, same session): user confirmed the proposal as-is — M1
  CHANGELOG placement accepted, no changes to the as-is file set.
- S4 (2026-10-30, same session): preflight green on dev `8c9a17d` (clean
  tree; head `6b41040b` unchanged via `git ls-remote`; pre-image re-check:
  all 4 files still dev-identical to the PR base). Applied:
  `scheduler.py` / `ui/tasks.py` / `test_bc_scheduler.py` as-is from
  `refs/pr/53` (verified byte-identical to head), CHANGELOG M1 — entry
  text verbatim into the existing `### Fixed` subsection (prepended), the
  PR's duplicate `### Fixed`-above-`### Added` insertion dropped. Tree left
  dirty (4 files) for S5; no commit of the integrated content.
