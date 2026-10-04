# BillCollector — Deploy Skills Plan (`dev-commits` + `deploy`)

> Status: DELIVERED (2026-10-01, commits 8be7a8a/e466553) — the skills are now the source of truth and have since diverged from this plan.

**Date:** 2026-10-01
**Extends:** `.kilo/plans/1790539917809-gitea-github-branch-strategy.md` — encodes its "Promotion workflow (standing process)" + decisions as executable project skills.

## Goal

Two project-local Kilo skills that make the deployment lifecycle a standing, repeatable procedure:

1. `.kilo/skills/dev-commits/SKILL.md` — daily: split working-tree changes into logical `dev` commits, **suggest-only**.
2. `.kilo/skills/deploy/SKILL.md` — release lifecycle: regression validation → promote `dev` to Gitea `main` → publish sanitized GitHub mirror (+ release tag) → NAS deploy → rollback. One explicit user gate per stage.

## Context (current model — do not re-derive)

- Remotes: `origin` = Gitea (private, source of truth), `github` = public sanitized mirror of Gitea `main` only.
- Branches: `dev` = daily work, `main` = verified production (ff-only promotion, never commit directly).
- Publish: `.private/sync_github.sh [tag]` builds the sanitized state (strips `.kilo`/`.vscode`/`.private`, amend, force-push) in a throwaway worktree; idempotent; GitHub hashes differ from Gitea by design.
- NAS: `deploy_remote.sh` reads root `.env` (`REMOTE_*`, `INSTALL_SCRIPT`, `GIT_BRANCH`), ssh fetch + reset + install script; rollback = `GIT_BRANCH=vX.Y`.
- Tests: `apps/.venv/bin/python tests/run_regression.py --ini tests/bc_regression.ini` (exit 0 ok · 1 deviation · 2 portal failed · 3 run lock held · 4 `--vault` preflight failed); `--ini tests/bc_regression_happy.ini` = success-only; `--vault` = real Vaultwarden (maintainer dev setup only).
- Local docker runs need the image rebuilt after code changes (`Dockerfile_pw` bakes in `apps/`): `bash install_docker-image.sh playwright`.
- Commit style (recent history): `feat:` / `fix:` / `doc:` / `test:` / `chore:` / `refactor:` + short imperative subject.
- CHANGELOG.md: Keep a Changelog, one section per tag + `[Unreleased]`.

## Decisions

1. **Structure (user-chosen):** hybrid — split at the frequency boundary: daily commit suggestions (`dev-commits`) separate from the coupled release lifecycle (`deploy`). Shared surface between them is only ~3 lines (commit style, "work on `dev`", "never `main`"), so trivial duplication is accepted.
2. **Gates:** every stage ends in an explicit user gate — the agent prepares and proposes, the user decides, the agent executes only after confirmation. Suggest-only is the default for commits; merge/push/tag/deploy/rollback always require explicit per-stage confirmation.
3. **No code re-test before GitHub publish (answers user step 4):** the promotion is `--ff-only`, so Gitea `main`'s tree is bit-identical to the tested `dev` tip, and the mirror only strips folders. The public gate is **verification, not re-test**: hash check on `github main`, tag presence, absence of `.kilo`/`.vscode`/`.private` in the GitHub file listing.
4. **"What else" (user step 5) — included:** release tag + CHANGELOG section move (Stage 2), NAS deploy + post-deploy verification (Stage 4), rollback procedure (Stage 5). All already defined by the standing strategy plan; the skill just makes them executable.
5. **Location:** `.kilo/skills/<name>/SKILL.md` (Kilo discovers `{skill,skills}/<name>/SKILL.md` in project config). `.kilo` is in `STRIP`, so both skills stay private on GitHub automatically.
6. **Commit:** both files are committed to `dev` (like the existing `.kilo/plans`), via a suggested commit — the user decides.

## Implementation

### Task 1 — create `.kilo/skills/dev-commits/SKILL.md`

Exact content:

```markdown
---
name: dev-commits
description: Suggest logical dev commits for BillCollector. Use when the user asks to commit, stage, or tidy working-tree changes on the dev branch. Suggests only - never commits or pushes without explicit per-item confirmation.
---

# BillCollector Dev Commits (suggest-only)

Split working-tree changes on `dev` into small logical commits. This skill only
proposes: it lists files and exact commit messages; the user runs the commits, or
explicitly confirms each item for the agent to run.

## Rules

- Work only on `dev`. If the current branch is not `dev`, stop and report.
- Commit message style (recent history): `feat:`, `fix:`, `doc:`, `test:`,
  `chore:`, `refactor:` + short imperative subject.
- One concern per commit: code (feat/fix/refactor) separate from recipes,
  tests, docs, and `.kilo` plans/tooling.
- Never stage `.env` (root or `apps/`), local `.vscode/` state, or untracked
  build artifacts that are not meant for the repo.
- No amend, no rebase, no push except the final suggested `git push origin dev`.

## Procedure

1. Preflight: `git branch --show-current` (expect `dev`), `git status --short`,
   `git log --oneline origin/dev..HEAD` (note unpushed commits). If the tree is
   clean, say so and stop.
2. Read the diff (`git diff` + untracked files) and group changes into logical
   commits.
3. Output a numbered proposal: per commit, the files to stage + the exact commit
   message. The user approves, edits, or rejects per item.
4. When the user confirms a specific item, run `git add <files>` +
   `git commit -m "..."` for that item only. Never batch-execute all proposed
   commits in one action without per-item confirmation.
5. After all items are committed: verify `git status --short` is clean, then
   propose `git push origin dev`.
```

### Task 2 — create `.kilo/skills/deploy/SKILL.md`

Exact content:

```markdown
---
name: deploy
description: BillCollector release lifecycle - pre-promotion regression validation, promote dev to Gitea main (ff-only), publish the sanitized GitHub mirror (sync_github.sh), release tags, NAS deploy (deploy_remote.sh), rollback. Use for "release", "promote to main", "sync GitHub", "deploy to NAS", "rollback". Commit suggestions live in the dev-commits skill.
---

# BillCollector Deploy (release lifecycle)

Standing process for the deployment strategy
(`.kilo/plans/1790539917809-gitea-github-branch-strategy.md`: "Promotion workflow"
+ decisions). Each stage ends in an explicit user gate: prepare + propose, user
decides, then execute. The agent never merges to `main`, pushes, tags, deploys,
or rolls back without the gate confirmation.

## Invariants (never break)

- `origin` = Gitea (private, source of truth): `dev` = daily work, `main` =
  verified production. `feature/*` branches from `dev` only for large risky
  chunks.
- `github` = sanitized public mirror of Gitea `main` only; hashes differ from
  Gitea by design (sanitize-by-amend). Never merge/fetch between the two repos.
- Never commit directly to `main`; promotion is `--ff-only`.
- `.kilo/`, `.vscode/`, `.private/` must never reach GitHub (`STRIP` in
  `.private/sync_github.sh`).
- `sync_github.sh` works in a throwaway worktree; the main working tree and the
  current branch are never touched. Re-runs are idempotent (committer date
  pinned).
- Release tags: same name on both lineages, different hashes, by design.
- App code is baked into the docker image (`Dockerfile_pw` does `COPY apps/. .`):
  after committing code changes, rebuild with `bash install_docker-image.sh
  playwright` before any docker-based local run.
- `main` reflects the published production state; GitHub `main` intentionally
  lags `dev` until promotion.

## Stage router

- "test the changes" -> Stage 1 only.
- "release vX.Y" / "promote to main" -> Stages 1-3, then Stage 4 if a NAS
  deploy is requested.
- "deploy to NAS" -> Stage 4 only (confirm which Gitea `main` state to run).
- "rollback" -> Stage 5 only.

## Stage 1 - Pre-promotion validation (user runs)

Goal: prove the exact content that is about to be promoted. The regression
harness runs from the working tree (venv), so test on `dev` at the commit that
will be promoted.

1. Confirm: on `dev`, clean tree (`git status --short`), and
   `git log --oneline origin/dev..HEAD` shows only committed work (use the
   dev-commits skill to tidy the tree first if not clean).
2. Suggest the test procedure:
   - Full scope: `apps/.venv/bin/python tests/run_regression.py --ini
     tests/bc_regression.ini` -> expect exit 0. (Exit codes: 1 expectation
     deviated, 2 mock portal failed to start, 3 a real BillCollector run holds
     the run lock -> stop the run first, 4 `--vault` preflight failed.)
   - Success-only quick check: `--ini tests/bc_regression_happy.ini`.
   - Optional, maintainer dev setup only: `--vault` (real Vaultwarden path:
     env, DNS, unlock, sync, per-pair item + TOTP).
   - For docker/NiceGUI/image-touching changes: rebuild
     `bash install_docker-image.sh playwright` + a manual smoke run
     (`./BillCollector.sh apps/bc_default.ini False` or the NiceGUI UI).
3. Wait for the user's results. Full-scope exit 0 = gate passed. Anything else
   -> fix on `dev` (new dev-commits cycle), re-test; never patch on `main`.

## Stage 2 - Promote dev -> Gitea main (user decides)

Only after the Stage 1 gate and an explicit user confirmation.

1. `git checkout main`
2. `git fetch origin --prune`
3. `git merge --ff-only origin/main` (absorb external pushes, e.g. NAS daemon
   recipe commits once the daemon plan M3 lands)
4. `git merge --ff-only dev`
5. `git push origin main`
6. Verify: `git diff main dev` is empty, status clean, on `main`.
7. If this is a release: propose the version (e.g. `v0.4`) and the CHANGELOG.md
   update - move the relevant `## [Unreleased]` bullets under a new
   `## [vX.Y] - <date>` heading (Keep a Changelog, one section per tag). After
   user confirmation: `git tag -a vX.Y main -m "Release vX.Y: <summary>"` and
   `git push origin vX.Y`.

## Stage 3 - Publish to GitHub (mirror + optional tag)

1. `bash .private/sync_github.sh [tag]` - pass the tag only if Stage 2 tagged.
2. Verify (this is the public gate - no code re-test):
   - `git ls-remote github refs/heads/main` -> new hash (differs from Gitea
     main, by design).
   - `git ls-remote github refs/tags` -> tag present (if released).
   - GitHub file listing for `main`: no `.kilo`, `.vscode`, `.private`.
3. No re-test of the code: the ff-only merge guarantees main's tree is identical
   to the tested dev tip, and the mirror only strips folders.

## Stage 4 - NAS deploy (user decides)

1. Root `.env`: `GIT_BRANCH=main` (or the release tag for a pinned deploy).
2. `./deploy_remote.sh` - ssh to the NAS, fetch + reset in `REMOTE_PATH`, run
   `INSTALL_SCRIPT` (image build), prints the new `git log -1`.
3. Verify: the remote commit equals the promoted Gitea `main` tip; the next
   scheduled/manual production run succeeds (DB rows / cron log on the NAS).

## Stage 5 - Rollback (user decides)

1. Pick the last good tag: `git tag -l 'v*'`.
2. Root `.env`: `GIT_BRANCH=vX.Y`; `./deploy_remote.sh`.
3. Verify: remote commit equals the tag's commit; production run OK.
4. Rollback never touches Gitea/GitHub branches. To also remove bad code from
   Gitea `main`: revert on `dev` -> Stage 1 -> Stage 2 (a normal cycle), never
   an edit on `main`.

## Failure modes

- Stage 2 ff-only fails -> `main` diverged (direct commit or non-ff external
  push): stop and report; never force.
- `sync_github.sh` killed mid-run (SIGKILL) -> `git worktree prune` cleans the
  leak.
- Re-running `sync_github.sh` is safe (idempotent) - use it to re-verify.
- Harness exit 3 -> a real run holds `apps/.bc.lock`; stop the running app
  first.
```

### Task 3 — commit the skills (suggested, user decides)

Single commit on `dev`, both files:

```
doc: add Kilo deploy skills (dev-commits suggest-only + release lifecycle)
```

Then `git push origin dev` (suggested, user runs or confirms).

## How to use the skills in daily work

**Loading:** skills are not commands — Kilo loads the right one automatically
when the request matches its description. There is nothing to type. If a skill
does not load, name it explicitly ("use the deploy skill for this"). New or
changed skills appear only after a Kilo restart.

**Mode:** use **code mode** (the default) for both skills. `dev-commits`
executes `git add`/`git commit` after per-item confirmation and `deploy`
executes merges, pushes, and the sync/deploy scripts — all need execute
capability. Plan mode only designs new work and would stop before executing a
stage; ask mode can explain the procedure but not run it. The per-stage user
gates in the skills, not the mode, are the safety mechanism.

### Typical day

| Situation | Say | Skill loads | What happens |
|---|---|---|---|
| Work done, tree dirty | "Suggest commits for the working tree" | `dev-commits` | Numbered file+message proposals; you run the commits (or confirm each item for the agent); ends with a push suggestion |
| Only recipe edits pending | "Suggest commits" | `dev-commits` | Same — recipes are grouped as their own commit |
| Want to check the changes | "Run regression tests on the current dev" | `deploy` (Stage 1) | Agent preflights (branch, clean tree), suggests the harness command; you run it, report the exit code, agent judges the gate |
| Milestone validated | "Release v0.4" | `deploy` (Stages 1–3) | Validation → promotion → GitHub mirror + tag, each stage waiting for your confirmation |
| NAS should run the new state | "Deploy main to the NAS" | `deploy` (Stage 4) | `.env` `GIT_BRANCH` check + `./deploy_remote.sh` suggested; remote commit + next production run verified |
| Production problem | "Roll back to v0.3" | `deploy` (Stage 5) | `GIT_BRANCH=v0.3` + `./deploy_remote.sh` suggested; remote commit verified |

### Full release walkthrough (v0.4)

1. You: **"Release v0.4."**
2. Agent (`deploy`, Stage 1): verifies `dev` + clean tree + unpushed commits,
   suggests `apps/.venv/bin/python tests/run_regression.py --ini
   tests/bc_regression.ini` (plus `--vault` / docker smoke run if relevant).
3. You: run the harness → **exit 0**.
4. Agent: "Stage 1 gate passed. Promotion plan: checkout `main`, ff-only merge,
   `push origin main`. Confirm?"
5. You: **"Yes, and tag v0.4."**
6. Agent runs Stage 2 (only after your yes), verifies `git diff main dev`
   empty, then proposes the CHANGELOG move (`[Unreleased]` → `[v0.4] - <date>`)
   + the tag commands.
7. You: confirm the CHANGELOG edit; agent edits, tags, pushes the tag.
8. Agent: "Stage 3: `bash .private/sync_github.sh v0.4`? Confirm." → runs it →
   verifies new hash on `github main`, tag present, no `.kilo`/`.vscode`/
   `.private` in the GitHub listing.
9. Later, you: **"Deploy to the NAS."** → Stage 4: `GIT_BRANCH=main` confirmed
   in `.env`, `./deploy_remote.sh` run, remote commit + production run checked.

### Rules of thumb

- **One skill per request:** anything about committing → `dev-commits`;
  anything from testing onward → `deploy`. If unsure, name the skill.
- **Gates are yours:** no merge, push, tag, deploy, or rollback without your
  explicit yes. If the agent acts without a gate, stop it and quote the skill's
  invariants.
- **Commits stay suggest-only:** `dev-commits` never commits unprompted; you
  run the commands or confirm per item.
- **Dirty tree + release request:** Stage 1's preflight catches it; let the
  agent run `dev-commits` first, then continue the release.
- **Test on the exact commit:** the harness runs from the working tree, so the
  Stage 1 preflight requires a clean, committed `dev` — what is tested is what
  gets promoted.
- **Skills and scripts change together:** if `sync_github.sh`,
  `deploy_remote.sh`, or the harness exit codes change, update the skill text
  in the same commit.

> Note: this section is the standing usage reference. Publishing it into the
> README's "Development & Deployment" section is a possible follow-up, not part
> of this plan.

## Validation

1. **Format:** both files exist at the exact paths, each with YAML frontmatter
   whose `name` equals the directory name and has a `description`.
2. **Discovery:** restart Kilo in the project root; in a fresh session both
   skills appear in the available skills (skills load at startup only).
3. **Dry run A (dev-commits):** fresh session with a dirty `dev` tree, ask
   "suggest commits". Expect: `dev-commits` loads, numbered file+message
   proposals, no commit executed.
4. **Dry run B (deploy):** fresh session with a clean `dev` tree, ask "release
   v0.4". Expect: `deploy` walks Stage 1 → Stage 2 → Stage 3, stopping at each
   user gate, with the exact commands from the skill.
5. **Privacy:** on the next `bash .private/sync_github.sh` run, the GitHub file
   listing for `main` contains no `.kilo` (skills stay private by `STRIP`).

## Risks

- **Skill/script drift:** if `sync_github.sh`, `deploy_remote.sh`, harness exit
  codes, or the branch model change, the skills must change in the same commit.
- **Advisory only:** gates are enforced by the agent honoring the skill text,
  not by tooling; the invariants are therefore written as hard rules in the
  body.
- **Discovery lag:** new skills appear only after a Kilo restart.

## Out of scope

- CI/CD or auto-deploy (none exists; NAS stays manual per the strategy plan).
- GitHub Releases UI objects (script + tags are the release mechanism).
- Any modification of the scripts themselves — the skills reference them as-is.
- Revisiting the promotion flow when the daemon (plan M3) auto-commits recipe
  changes from the NAS and pushes to `origin/main` — already flagged in the
  strategy plan; Stage 2's `merge --ff-only origin/main` keeps manual
  promotions working until then.
