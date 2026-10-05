---
name: deploy
description: BillCollector release lifecycle - pre-promotion regression validation, promote dev to Gitea main (ff-only), publish the sanitized GitHub mirror (sync_github.sh), release tags, release notes (user opt-in + review gate), NAS deploy (deploy_remote.sh), rollback. Use for "release", "promote to main", "sync GitHub", "release notes", "deploy to NAS", "rollback". Commit suggestions live in the dev-commits skill.
---

# BillCollector Deploy (release lifecycle)

Standing process for the deployment strategy
(`.kilo/plans/1790539917809-gitea-github-branch-strategy.md`: "Promotion workflow"
+ decisions). Each stage ends in an explicit user gate: prepare + propose, user
decides, then execute. The agent never merges to `main`, pushes, tags, deploys,
rolls back, or publishes release notes without the gate confirmation.

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
- Release notes (Release objects on Gitea/GitHub) are never created
  automatically: the user opts in, reviews the full suggested body, and only
  then does the agent post it.
- App code is baked into the docker image (`Dockerfile` does `COPY apps/. .`):
  after committing code changes, rebuild with `bash install_docker-image.sh`
  before any docker-based local run.
- `main` reflects the published production state; GitHub `main` intentionally
  lags `dev` until promotion.

## Stage router

- "test the changes" -> Stage 1 only.
- "release vX.Y" / "promote to main" -> Stages 1-3; Stage 4 (release notes)
  only if the user opts in; Stage 5 if a NAS deploy is requested.
- "create release notes" -> Stage 4 only (requires the tag on both lineages).
- "deploy to NAS" -> Stage 5 only (confirm which Gitea `main` state to run).
- "rollback" -> Stage 6 only.

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
      `bash install_docker-image.sh` + a manual smoke run
     (`./BillCollector.sh apps/bc_default.ini False` or the NiceGUI UI).
3. Wait for the user's results. Full-scope exit 0 = gate passed. Anything else
   -> fix on `dev` (new dev-commits cycle), re-test; never patch on `main`.

## Stage 2 - Promote dev -> Gitea main (user decides)

Only after the Stage 1 gate and an explicit user confirmation.

If this is a release: first finalize CHANGELOG.md on `dev` - move the relevant
`## [Unreleased]` bullets under a new `## [vX.Y] - <date>` heading (Keep a
Changelog, one section per tag) and commit + push it to `dev` (doc-only, no
re-test). Steps 1-6 then carry it to `main`, so the tag in step 7 includes it.

1. `git checkout main`
2. `git fetch origin --prune`
3. `git merge --ff-only origin/main` (absorb external pushes, e.g. NAS daemon
   recipe commits once the daemon plan M3 lands)
4. `git merge --ff-only dev`
5. `git push origin main`
6. Verify: `git diff main dev` is empty, status clean, on `main`.
7. If this is a release: propose the version (e.g. `v0.4`). After user
   confirmation: `git tag -a vX.Y main -m "Release vX.Y: <summary>"` and
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

## Stage 4 - Release notes (user decides, review gate)

Attach a Release object (notes page) to the existing tag on Gitea and GitHub.
Stages 2-3 create the tags; this stage only adds the notes. Never run as part
of "release vX.Y" automatically - the user must explicitly opt in, and no API
call happens before the user has reviewed the suggested body.

1. Draft: take the public CHANGELOG `## [vX.Y]` section verbatim (it is
   sanitized - add no private URLs, hosts, or tooling). Present the full
   suggested body plus the exact API actions for both repos and wait for the
   user's review.
2. Only after explicit confirmation, create on both lineages (same body):
   - Gitea: `POST <origin base>/api/v1/repos/stefan/BillCollector/releases`
     with `{tag_name, name, body}`. The stored `~/.git-credentials` secret for
     the Gitea host is an account password -> Basic auth (`curl -u user:pass`);
     Bearer fails with 401.
   - GitHub: `POST https://api.github.com/repos/s-t-e-f-a-n/BillCollector/releases`
     with `{tag_name, name, body}`. The stored secret is a token -> Bearer.
   - Extract secrets into shell variables only (never print them); strip both
     the `https://` prefix and the trailing `@host` (a wrong suffix -> 401).
   - Build the JSON payload in a temp file (e.g. `/tmp/kilo`), send with
     `curl -d @file`, delete the temp files afterwards.
3. Verify: `GET .../releases/tags/vX.Y` on each API -> 200 with the right tag
   and body; `git ls-remote` shows both tags unchanged.
4. Fallback: a credential that is not API-usable -> report it and let the user
   create the release in the web UI; never guess or retry with other tokens.

## Stage 5 - NAS deploy (user decides)

1. Root `.env`: `GIT_BRANCH=main` (or the release tag for a pinned deploy);
   `CONSUMER_DIR` + `DB_DIR` set (forwarded to the NAS install script; if
   empty there, a `.env` next to the script on the NAS is used instead).
2. `./deploy_remote.sh` - ssh to the NAS, fetch + reset in `REMOTE_PATH`, run
   `INSTALL_SCRIPT` (image build), prints the new `git log -1`.
3. Verify: the remote commit equals the promoted Gitea `main` tip; the next
   scheduled/manual production run succeeds (DB rows / cron log on the NAS).

## Stage 6 - Rollback (user decides)

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
