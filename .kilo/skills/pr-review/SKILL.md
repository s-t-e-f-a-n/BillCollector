---
name: pr-review
description: Review and integrate community pull requests for BillCollector (GitHub PRs against s-t-e-f-a-n/BillCollector). Seven user-gated stages, one per session: review, plan, propose or refuse, selective integration on Gitea dev, validate/refine, documentation, commit + push (Gitea first, then GitHub mirror) + PR close. Use for "review PR #N", "continue PR #N", "integrate PR #N", "refuse PR #N", "close PR #N".
---

# BillCollector PR Review (community PRs, Gitea-first integration)

Standing process for GitHub pull requests against `s-t-e-f-a-n/BillCollector`
(the sanitized public mirror). Blueprint: the PR #11 vault-diagnostics review
(`.kilo/plans/1791237156540-pr11-vault-diagnostics-review.md`). Each stage is
a separate session ending in an explicit user gate; the review plan document
(committed to Gitea `dev`) carries the state between sessions. The agent never
applies PR content, pushes, comments on, or closes a PR without the gate
confirmation.

## Invariants (never break)

- `origin` = Gitea (private, source of truth); `github` = sanitized mirror of
  Gitea `main` only. Never merge/fetch between the two repos.
- PR refs are inspection-only: fetched as `refs/pr/N`, never merged into the
  Gitea lineage, never pushed anywhere. Integration is file-level
  application on Gitea `dev`.
- Never apply files under `.kilo/`, `.private/`, `.vscode/` from a PR head.
- All public-facing text (CHANGELOG, README, PR comments) is sanitized: no
  Gitea host, NAS details, or private paths.
- Validation runs on the exact `dev` tree that will be promoted, from the
  repo root with `apps/.venv/bin/python`.
- Commits follow the dev-commits skill (one concern per commit); promotion
  and mirroring follow the deploy skill (ff-only; no tag unless a release is
  decided separately).
- One PR per workflow chain. The review plan document is the single state
  carrier; every stage ends by committing its plan-doc update to `dev`
  (doc-only).

## Review plan document (state carrier)

Path: `.kilo/plans/<epoch-ms>-pr<N>-<slug>-review.md`. First line after the
title:

    > Status: REVIEWING | AWAITING-DECISION | INTEGRATING | VALIDATED |
    > DELIVERED | REJECTED (date) — one-line summary

Sections: PR metadata (author, head hash, base, issue refs, local `dev` /
`main` / `github/main` state at review time), Verdict, Verified facts, Code
review findings, Risks, Integration plan (per file: apply / skip / manual +
expected conflicts), Validation plan (commands + expected results), Out of
scope, Open questions.

## Stage router

- "review PR #N" -> S1 (fresh plan doc, Status: REVIEWING).
- "continue PR #N" -> read the plan doc's Status, route to the next stage.
- "refuse PR #N" -> S3 refusal branch.
- "close PR #N" -> S7 close step (integrated) or the refusal close (refused).

## S1 - Review (session: "review PR #N")

1. Fetch: `git fetch github refs/pull/N/head:refs/pr/N` (re-fetch if the ref
   exists; record the head hash). PR metadata + description via `GET
   https://api.github.com/repos/s-t-e-f-a-n/BillCollector/pulls/N` (Bearer
   token from `~/.git-credentials`, deploy-skill Stage 4 pattern: extract to
   a shell variable, never print).
2. Record local state: `dev`, `main`, `github/main` tips.
3. Merge-base analysis: `git merge-base refs/pr/N github/main`; list the PR
   commits; flag orphaned public-history commits (recommits of sanitized
   tips).
4. Classify every file in `git diff <merge-base>...refs/pr/N`:
   - added/modified public path -> candidate;
   - deleted but already absent from current `github/main` -> comparison
     artifact (fork-behind-base noise), skip;
   - any path under `.kilo/`, `.private/`, `.vscode/` -> flag, never
     auto-apply.
5. Conflict + pre-image check against Gitea `dev`: for each candidate, is the
   `dev` file byte-identical to the PR head (skip), byte-identical to the PR
   base pre-image (hunk applies cleanly), or diverged (needs manual
   adaptation)? Which dev files changed since the merge base (conflict list)?
6. Code review: per file/function, behavior preserved vs changed, with line
   refs; test review (coverage, synthetic markers, no secrets, pinned
   behavior); note out-of-scope residuals explicitly.
7. Process check (CONTRIBUTING.md): issue referenced; intended behavior +
   verification stated; proof shipped (test / regression command + expected
   result); AI assistance disclosed; no secrets in code, tests, or artifacts;
   no new network exposure without review; shared interfaces (DB schema,
   control protocol, recipe contract, exit codes) agreed in the issue before
   code.
8. Cross-PR: list other open PRs; note dependencies/ordering (tests written
   to pass in either merge order are a plus, not a requirement).
9. Gate: findings complete; move to S2.

## S2 - Plan (session: "continue PR #N")

1. Write the review plan document (format above) with: Verdict (approve /
   approve with maintainer changes / refuse), Verified facts, findings,
   risks, per-file integration plan, validation plan.
2. Status: AWAITING-DECISION. Commit the plan doc to `dev` (doc-only,
   dev-commits gate) and push.
3. Gate: user reviews verdict + plan.

## S3 - Propose or refuse (session: "continue PR #N")

Integrate branch: present the exact proposal — files applied from the PR
head, files skipped (already present/identical), manual conflict resolutions
(usually CHANGELOG), maintainer-side changes with the exact intended diff,
and the commits to create. User confirms as-is, with changes, or declines
(-> refusal branch).

Refusal branch: draft the full PR comment (findings, evidence, what a
revised PR should do). User confirms the text, then chooses: leave open for
revision (comment only) or close without merge (comment + close). Post via
API: `POST .../issues/N/comments`, and if closing `PATCH .../pulls/N`
`{"state":"closed"}`. Status: REJECTED. Doc-only plan commit + push. End.

## S4 - Selective integration (Gitea dev; session: "continue PR #N")

1. Preflight: on `dev`, clean tree; PR head hash unchanged since S1
   (`git ls-remote github refs/pull/N/head`); re-run the pre-image checks.
2. Apply each candidate file's content from `refs/pr/N` to the working tree;
   skip identical files; apply the confirmed maintainer-side changes.
3. CHANGELOG.md: merge the PR's entry (or the authored one) into the existing
   `## [Unreleased]` (Keep a Changelog subsection order: Added / Changed /
   Deprecated / Removed / Fixed / Security) — the manual conflict resolution.
4. Leave the tree dirty (uncommitted): S5 validates the exact content before
   any commit. Status: INTEGRATING.

## S5 - Validate / refine (session: "continue PR #N")

From the repo root, with the venv, on the exact dev tree:

- PR's unit tests: `apps/.venv/bin/python -m unittest tests.<module> -v`
  -> expected count OK.
- Full regression: `apps/.venv/bin/python tests/run_regression.py --ini
  tests/bc_regression.ini` -> exit 0 (7 scenarios / 8 PDFs, VERDICT: PASS).
  Exit codes 1/2/3/4: deploy-skill semantics (exit 3 -> a real run holds the
  lock, stop it first).
- ruff (F821, E4/E7/E9) + bandit on the changed files -> nothing new beyond
  the known baseline (B608 dynamic SQL table names, B104 UI bind).
- Scope adjustments: recipe-only PRs -> CheckRecipe/schema validation +
  regression; Dockerfile/image changes -> rebuild `bash install_docker-image.sh`
  + smoke run (deploy-skill invariant).
- If the harness needs the `Service` table and `apps/db/bc.db` is a 0-byte
  gitignored file: re-initialize the schema via the production DatabaseManager
  (no repo impact).

On failure: diagnose, fix on `dev` (new dev-commits cycle after fixing),
re-run; if a fix would materially change the PR's intent, go to the S3
refusal branch. All green -> Status: VALIDATED.

## S6 - Documentation (session: "continue PR #N")

1. CHANGELOG `## [Unreleased]` entry for the integrated change (sanitized,
   public-safe wording).
2. README / CONTRIBUTING only if user-visible behavior or contributor rules
   changed.
3. Plan doc: record validation results + integration details.
Gate: user confirms the docs.

## S7 - Commit + push: Gitea first, then GitHub (session: "continue PR #N")

1. dev-commits skill: propose the commits (one concern each: code / test /
   doc), per-item confirmation, then `git push origin dev`.
2. Promote (deploy skill Stage 2, user gate): checkout `main`, fetch,
   `merge --ff-only origin/main`, `merge --ff-only dev`, push. No tag unless
   a release is decided separately.
3. Mirror (deploy skill Stage 3): `bash .private/sync_github.sh`; public
   gate: `git ls-remote github refs/heads/main` shows the new hash, GitHub
   `main` listing has no `.kilo` / `.vscode` / `.private`, and the integrated
   content is present.
4. Close the PR (user confirms the exact comment text first): `POST
   .../issues/N/comments` (mirror flow explained, content confirmed in
   place, nits noted) + `PATCH .../pulls/N` `{"state":"closed"}` — closed
   without merge; the change reached GitHub via the mirror, keeping public
   history canonical.
5. Plan doc: Status: DELIVERED with the dev / main / GitHub hashes + close
   timestamp; doc-only commit + push to `dev` (stays private; `.kilo/` never
   reaches GitHub).

## Failure modes

- PR head moved after S1 (author pushed) -> diff the new head against the
  reviewed head; non-empty -> re-run S1 in a new session and update the plan
  doc; never integrate a head that was not reviewed.
- `dev` moved since the review -> re-run the pre-image checks; rebase the
  hunks; record the adaptation in the plan doc.
- ff-only promotion fails -> `main` diverged: stop and report (deploy skill);
  never force.
- `sync_github.sh` killed mid-run -> `git worktree prune` cleans up (deploy
  skill).
- GitHub credential not API-usable -> report it; the user comments/closes in
  the web UI; never guess or retry with other tokens.
- PR touches a shared interface without an agreed issue -> refusal branch.
