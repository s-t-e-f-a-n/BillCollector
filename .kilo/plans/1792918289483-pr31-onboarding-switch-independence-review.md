# PR #31 review — fix: keep onboarding task switches independent

> Status: AWAITING-DECISION (2026-10-25) — S1 review + S2 plan complete;
> verdict **approve**; awaiting user review of verdict + integration plan
> (S2 gate) and the plan-doc commit.

## PR metadata

- Author: flowcool
- PR: `s-t-e-f-a-n/BillCollector#31` — "fix: keep onboarding task switches
  independent"
- Head: `9d1ec9d22cbdd0b5b61844e6b8c6e2bc956c45e1` (branch
  `fix/upstream-onboarding-20261024`); re-verified against `git ls-remote
  github refs/pull/31/head` at review time (unchanged)
- Base: public `main` `b4cf023f42b2d265106e1db9bde580d012a451b0` (= Gitea
  `4b336d2`, the sanitized re-commit of the PR #19 delivery); merge-base
  with `github/main` is `71c7d697` — a pre-sanitization public commit. The
  PR is a **single commit** `9d1ec9d` on top of `b4cf023`. The API's
  `changed_files`/`deletions` (86 files / 18237 deletions) is a
  sanitized-history comparison artifact: `b4cf023`'s tree drops the private
  files (`openwiki/`, doctor tests, …) that `71c7d697` still carries — not
  PR content.
- Issue refs: #27 **F07** — "onboarding toggle closure + multi-control
  acceptance test" (handed over to flowcool, tracked in their PRs)
- Local state at review (2026-10-25): `dev` `588ff58`, `main` `84a9d8b`,
  `github/main` `41294731df`; inspection ref `refs/pr/31`
- Pre-existing public comment: maintainer-account approval
  (6394460111, 2026-10-25 06:37Z) — "29 passed, ruff clean, approved, no
  changes requested"; consistent with this review, recorded for the record.

## Verdict

**Approve.** One-line late-binding-closure fix that is exactly F07's closure
part; the acceptance test is exactly F07's multi-control part. Both changed
files are byte-identical between `dev` and the PR base pre-image, so both
apply as clean file-level copies. No shared interface, no deployment
relevance, no secrets.

## Verified facts

- Bug mechanism (verified in dev `apps/billcollector/ui/onboarding.py:181-223`):
  `render_tasks()` creates one `ui.switch` and one `on_toggle` closure per
  task. `task_id` is captured at definition time (default argument), but
  `toggle` is a free variable — late binding: after the loop ends, every
  callback reads the **last-created** switch's value. Toggling task N's
  switch writes task N's row with the last task's switch value (PR body:
  "enabling the first reads the second switch's `False` value and leaves the
  first task disabled in SQLite").
- The fix (`onboarding.py:209`) adds the `toggle=toggle` default-argument
  capture, so each callback keeps its own widget. Verified: nothing else in
  the callback changes (`db.get_task` → `db.update_task(task_id, enabled=…)`
  → `scheduler.sync_task(task_id)` → notify). Re-renders (INI import, add
  task) recreate widgets and closures together, so the fix holds there too.
- The test (`tests/test_bc_ui_onboarding.py`, +40 lines,
  `test_task_switches_are_independent`) covers F07's acceptance criteria:
  two disabled tasks, enabling the first leaves the second untouched (fails
  pre-fix), per-task scheduler sync call order `[first, second, first]`,
  reloaded controls reflect the persisted DB, and a fresh process reopens
  the persisted database and rebuilds scheduler jobs with only the enabled
  task scheduled.
- Every test API assumption verified against dev source: `Database.path`
  (`db.py:93`), `create_task(service, user, enabled=, cron=)` (`db.py:140`),
  `update_task(task_id, **fields)` (`db.py:162`), `TaskScheduler.resync`
  (`scheduler.py:93`), `sync_task` (`scheduler.py:101`), the `.scheduler`
  property (`scheduler.py:68-71`), job id `task-<id>` (`scheduler.py:35-37`).
- APScheduler behavior verified in the venv (2026-10-25): `resync()` on a
  not-started `AsyncIOScheduler` queues jobs and
  `scheduler.get_jobs()` returns them — one enabled + one disabled task
  yields `['task-1']`. The fresh-process assertion
  (`[j.id for j in scheduler.scheduler.get_jobs()]==['task-'+second]`) is
  sound.
- Pre-image check (2026-10-25, dev `588ff58`): dev's `onboarding.py` and
  `tests/test_bc_ui_onboarding.py` are byte-identical to the PR base
  (`b4cf023`) versions → both hunks apply cleanly; dev differs from the PR
  head in exactly these two changes and nothing else.
- F07 in the commitments plan ("Handed over to flowcool"): "onboarding
  toggle closure + multi-control acceptance test" — the PR ships both halves.
- Process check (CONTRIBUTING.md): issue referenced (F07 of #27); intended
  behavior + verification stated; proof shipped (exact pytest command on the
  two test files, expected 29 passed, Python 3.12.13 / pytest 9.1.1 /
  NiceGUI 3.17.1 pinned); AI assistance disclosed (Codex extracted the fix;
  contributor owns behavior and proof); no secrets in the diff; no new
  network exposure (the subprocess is the local same interpreter against a
  temp DB); no shared interface touched (UI-internal callback binding; no DB
  schema, control protocol, recipe contract, or exit-code change).
- Test hygiene: temp SQLite via the `BC_UI_TEST_DB` main-file fixture,
  synthetic accounts (u1/u2), `monkeypatch` auto-restore, `timeout=15` on
  the subprocess, `PYTHONPATH=apps` per the environment convention; no real
  vault, provider, notification, or deployment.

## Code review findings

- `apps/billcollector/ui/onboarding.py:209` — the one-line signature change
  (add `toggle=toggle`). Correct, minimal, behavior-preserving apart from
  the bug. Non-blocking nit: `enabled = int(bool(toggle.value))` — a NiceGUI
  switch value is already bool; the `bool()` is a no-op but harmless.
- `tests/test_bc_ui_onboarding.py` — one new test, +40 lines. Non-blocking
  nits: the fresh-process check is the heaviest part (one extra interpreter
  start, ~1–2 s) but it is the only way to cover the daemon-restart path
  in-process tests cannot; the `synced == [first, second, first]` assertion
  pins exact call order (deterministic — one `sync_task` per toggle).

## Risks

- Negligible: one-line UI callback binding + a self-contained test. No
  schema, shared interface, config, or deployment artifact touched. The
  subprocess test depends on `sys.executable` + `PYTHONPATH=apps` resolving
  the venv — S5 verifies on the exact tree.

## Integration plan

| File | Action | Notes |
|---|---|---|
| `apps/billcollector/ui/onboarding.py` | apply from PR head | pre-image byte-identical to dev; the one-line change |
| `tests/test_bc_ui_onboarding.py` | apply from PR head | pre-image byte-identical to dev; the +40-line test |
| `CHANGELOG.md` | manual (maintainer side) | the PR ships no entry; add one bullet under `## [Unreleased]` → `### Fixed` (wording below, S3 confirms) |
| (no others) | skip | no other files in the PR diff |

Candidate CHANGELOG wording (S3 decision item):

- Onboarding task switches are independent: toggling a switch now updates
  only its own task's enabled state and scheduler registration (previously
  every switch read the last-created switch's value, so in a multi-task
  setup enabling one task could leave it disabled) (issue #27, F07).

Expected conflicts: none (both pre-images byte-identical).

## Validation plan

S5, from the repo root with the venv, on the exact dev tree:

- PR unit tests: `apps/.venv/bin/python -m pytest -q
  tests/test_bc_ui_onboarding.py tests/test_bc_scheduler.py` → 29 passed
  (the PR's claim).
- Full suite: `PYTHONPATH=apps apps/.venv/bin/python -m pytest -q` → 454
  passed (453 baseline from the PR #30 chain + the one new test).
- Full regression: `apps/.venv/bin/python tests/run_regression.py --ini
  tests/bc_regression.ini` → exit 0 (7 scenarios / 8 PDFs, VERDICT: PASS).
- ruff (F821, E4/E7/E9) + bandit on the two changed files → nothing new
  beyond the known baseline.

## Deployment validation

Not deployment-relevant (recorded 2026-10-25): no changes to `Dockerfile`,
`.dockerignore`, compose, `BillCollector.sh`, `install_docker-image.sh`,
`deploy_remote.sh`, INI keys, or `.env` handling. The S5 deployment block is
skipped on this basis; the user confirms the recorded skip at the S5 gate.

## Stage log

- S1 (2026-10-25): fetched `refs/pr/31` (head `9d1ec9d`, unchanged per
  `ls-remote`); merge-base analysis (base `71c7d697`; API diff stats
  identified as the sanitized-history artifact, real PR diff = 2 files /
  +41 −1); pre-image checks byte-identical; code + test review; test API
  assumptions verified against `db.py`/`scheduler.py` and the venv's
  APScheduler; process check passed; cross-PR: no file overlap with #32–#34
  (`onboarding.py` / `tests/test_bc_ui_onboarding.py` are not in their
  shared regions).
- S2 (2026-10-25): this doc written; verdict approve; Status
  AWAITING-DECISION; user gate on verdict + plan.

## Out of scope

- No scheduler implementation change (claimed by the PR; verified —
  `scheduler.py` is untouched by the PR diff).
- The other batch PRs (#32–#34) are handled in their own chains; #33's
  `runner.py`/`db.py`/`config.py` regions do not intersect this PR.

## Open questions

- None blocking. The CHANGELOG bullet wording is the S3 decision item.
