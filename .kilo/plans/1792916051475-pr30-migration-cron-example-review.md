# PR #30 review — docs: correct the five-field migration cron example

> Status: AWAITING-DECISION (2026-10-25) — S1 review complete, verdict
> approve; awaiting user decision on the S3 integration proposal
> (hunk-level apply + CHANGELOG entry).

## PR metadata

- Author: flowcool
- PR: `s-t-e-f-a-n/BillCollector#30` — "docs: correct the five-field
  migration cron example"
- Head: `3bb2e16cac9aaffee057bc3ff4cb829db6ca49df` (branch
  `docs/upstream-cron-20261024`); re-verified against `git ls-remote
  github refs/pull/30/head` at review time
- Base: public `main` `b4cf023f42b2d265106e1db9bde580d012a451b0`;
  merge-base = base (single commit on top of the main tip; no orphaned
  public-history commits)
- Issue refs: #27 **D08** (product audit item, P1, "Correct the migration
  cron example")
- Local state at review (2026-10-25): `dev` `7edfbde`, `main` `4b336d2`,
  `github/main` `b4cf023`; inspection ref `refs/pr/30`

## Verdict

Approve. One-line documentation correction that matches #27 D08's request
exactly; the PR's evidence was reproduced locally against the venv's
APScheduler; the hunk applies cleanly against current `dev`.

## Verified facts

- The corrected expression `0 6 1,15 * *` parses via
  `CronTrigger.from_crontab` (venv) and fires `2026-11-01T06:00Z` then
  `2026-11-15T06:00Z` from the fixed 2026-10-24 UTC clock — matches the PR
  evidence block's expected values.
- The old expression `0 6 1 1,15 * *` is rejected by the same parser:
  `ValueError: Wrong number of fields; got 6, expected 5`.
- The five-field contract is real: the scheduler builds job triggers with
  `CronTrigger.from_crontab(task["cron"])` (`apps/billcollector/scheduler.py:113`)
  and the UI task dialog validates with the same parser
  (`apps/billcollector/ui/tasks.py:35`) — the old example would have been
  rejected at both job registration and edit-dialog validation.
- The stale six-field example occurs only at the target line (dev
  `README.md:380`); no other occurrences in README/doc/apps/tests.
- Issue #27 D08: "`0 6 1 1,15 * *` has six fields; the UI accepts five. If
  the intention is the 1st and 15th of every month at 06:00, use
  `0 6 1,15 * *` and verify it with the actual parser." — the PR does
  exactly this.
- Process check (CONTRIBUTING.md): issue referenced; intended behavior and
  verification stated (diff + parser evidence with expected `PASS`); AI
  assistance disclosed (Codex, contributor owns the result); no secrets;
  docs-only, no network exposure; no shared-interface change.
- Pre-image vs dev: dev's README diverged from the PR base in other regions
  (TOC + ntfy section around lines 13–207; INI example around lines
  287–300; 22 lines total), but the hunk region (migration section, lines
  377–383 on dev) is byte-identical to the PR base — the one-line hunk
  applies cleanly. A wholesale copy of the PR head's README is not an
  option (it would revert dev's ntfy/INI documentation changes).

## Code review findings

- `README.md` (the only changed file), daemon-migration section, step 2
  "Set the schedules": the example cron changes from the six-field
  `0 6 1 1,15 * *` to the five-field `0 6 1,15 * *`. The surrounding text
  ("a 5-field crontab expression", "for the 1st and 15th at 06:00") becomes
  accurate. No behavior change.

## Risks

- Negligible: docs-only; no code, tests, config, or deployment artifacts
  touched. The only operational risk is the apply step overwriting dev's
  README changes — mitigated by the manual hunk-level application below
  instead of a whole-file copy.

## Integration plan

| File | Action | Notes |
|---|---|---|
| `README.md` | manual (hunk-level) | apply the one-line change to dev's `README.md:380`; do **not** copy the PR head's file (dev's README diverged elsewhere) |
| `CHANGELOG.md` | manual (maintainer side) | PR ships no entry; add one line under `## [Unreleased]` (proposed in S3) |
| (no others) | skip | no other files in the PR diff |

Expected conflicts: none (hunk region untouched on dev).

## Validation plan

S5 (docs-only; repo gate from the repo root on the exact dev tree):

- `ruff check apps tests` → clean (baseline unchanged; no code touched).
- `apps/.venv/bin/python -m pytest` → 451 passed (baseline count
  unchanged; no tests touched).
- No unit tests shipped with the PR; no regression-suite impact (no code
  change).

## Deployment validation

Not deployment-relevant (recorded 2026-10-25): no changes to `Dockerfile`,
`.dockerignore`, `BillCollector.sh`, `install_docker-image.sh`,
`deploy_remote.sh`, INI keys, or `.env` handling. The S5 deployment
validation block is skipped on this basis; the user confirms the recorded
skip at the S5 gate.

## Out of scope

- No scheduler behavior change (claimed by the PR; verified).
- The other batch PRs (#31–#34) are handled in their own chains.
- The #34 contract-doc updates (`doc/RECIPE_METHODS.md`, doctor-prompt
  variable vocabulary, README) stay bundled in #34's S6 per the sequencing
  plan; the cron example line is untouched by that work.

## Open questions

- None blocking. The CHANGELOG entry wording is the S3 decision item.
