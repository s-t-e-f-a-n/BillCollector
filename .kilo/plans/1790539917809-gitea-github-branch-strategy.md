# BillCollector — Deployment Strategy: dev + main Branch Flip (Gitea local / GitHub public)

**Status:** COMPLETE (2026-09-27). Recovery executed; worktree script (plus the deterministic-amend fix from regression testing) committed to `dev`; `v0.3` released on both lineages; PR #7 closed; local `public` deleted; `deploy_remote.sh` tag-aware. Sections below are the executed record.

## What happened (2026-09-27 21:32)

- Sync push succeeded: GitHub `main` = `2606c6d` (sanitized `b63524f`), `playwright` branch deleted ✓
- The script's final `git checkout dev` then aborted: after `git rm --cached`, the `.kilo`/`.vscode` files are **untracked in the working tree**, while `dev` tracks them — git refuses to overwrite untracked files whose on-disk content differs from `dev`'s committed content (here: the GUI-concept plan edited with a superseded-banner in this session, plus `kilo.jsonc`).
- Verified state: branch `public`, `git status` = `?? .kilo/` + `?? .vscode/` (entire dirs untracked; includes uncommitted plan edits and the new deployment-strategy plan file).
- **Root cause #2 (design flaw):** the script's "switch away and switch back" design is inherently fragile in the normal planning-session state (uncommitted `.kilo` edits). Fix: build the sanitized state in a **throwaway worktree** — the script never touches the main working tree or the current branch.

## Recovery (run now, from repo root, currently on `public`)

```bash
# 1) Back up the untracked dirs (protect uncommitted plan edits + possible kilo.jsonc drift)
mkdir -p /tmp/kilo/bc-backup
cp -a .kilo /tmp/kilo/bc-backup/kilo
cp -a .vscode /tmp/kilo/bc-backup/vscode

# 2) Force back to dev (overwrites the untracked .kilo/.vscode files with dev's committed versions)
git checkout -f dev

# 3) Restore the files with unique content
cp /tmp/kilo/bc-backup/kilo/plans/1790468502492-gui-concept-dashboard-spec.md .kilo/plans/
cp /tmp/kilo/bc-backup/kilo/plans/1790539917809-gitea-github-branch-strategy.md .kilo/plans/

# 4) Check whether kilo.jsonc had runtime drift (restore only if the diff shows something worth keeping)
diff /tmp/kilo/bc-backup/kilo/kilo.jsonc .kilo/kilo.jsonc || true

# 5) Verify: expect on dev with
#    M .kilo/plans/1790468502492-gui-concept-dashboard-spec.md
#    ?? .kilo/plans/1790539917809-gitea-github-branch-strategy.md
git status --short
```

## Remaining steps (after Recovery)

### 1) Replace `.private/sync_github.sh` with the worktree version

The committed version (on `dev`, `2c42980`) still has the fragile checkout design. Replace the whole file:

```bash
#!/usr/bin/env bash
# Sync the sanitized production branch (Gitea main) to GitHub main.
# Builds the sanitized state in a throwaway worktree; the main working tree
# and the current branch are never touched.
# Usage: ./sync_github.sh [tag]  (optional tag is also created on GitHub)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

TAG="${1:-}"

# Paths to keep off the public face (GitHub)
STRIP=( ".kilo" ".vscode" ".private" )

# Always mirror what is actually published on Gitea
git fetch origin --prune

# Build the sanitized state in a throwaway worktree
WT="$(mktemp -d)"
trap 'git worktree remove --force "$WT" >/dev/null 2>&1 || rm -rf "$WT"; git worktree prune >/dev/null 2>&1 || true' EXIT
git worktree add --detach "$WT" origin/main
cd "$WT"

# Remove private folders from the staging area
git rm -r --cached --ignore-unmatch "${STRIP[@]}"

# If files were removed, amend the tip commit using its existing message & author info
if ! git diff --cached --quiet; then
  git commit --amend --no-edit \
    --author="Stefan S "
fi

# Push sanitized state to GitHub's main branch
git push --force github HEAD:main

# Optional: tag the sanitized tip (hash differs from Gitea main by design)
if [ -n "$TAG" ]; then
  git tag -f "$TAG"
  git push --force github "$TAG"
fi

cd - >/dev/null
```

Notes: same sanitize mechanics as before (rm --cached + amend + force-push), just executed in a throwaway worktree; `HEAD:main` pushes the worktree's HEAD; the trap cleans the worktree on success and failure. The local `public` branch is no longer used by the script.

### 2) Commit to `dev`

```bash
git add .private/sync_github.sh \
  .kilo/plans/1790539917809-gitea-github-branch-strategy.md \
  .kilo/plans/1790468502492-gui-concept-dashboard-spec.md
git commit -m "Fix: sync_github.sh builds in throwaway worktree (never touches working tree); Add: deployment strategy plan"
git push origin dev
```
(If Step 4 of Recovery showed a `kilo.jsonc` drift worth keeping, `git add .kilo/kilo.jsonc` too.)

### 3) Release tag v0.3 (both lineages, same name, different hashes by design)

```bash
git tag -a v0.3 main -m "Release v0.3: Playwright batch system (Python 3.12, Playwright 1.63, M0 complete) - pre-daemon baseline"
git push origin v0.3
bash .private/sync_github.sh v0.3
```

### 4) Cleanup

- Close stale GitHub PR #7 (web UI, or `gh pr close 7`).
- Delete the obsolete local scratch branch: `git branch -D public`.
- (Optional) Make `deploy_remote.sh` tag-aware for rollbacks — replace the fetch/reset block (lines 46–56) with a POSIX-safe case (remote shell may be `sh`, so no `[[ ]]`):

```bash
  echo '[INFO] Fetching latest repository updates...'
  case "${GIT_BRANCH}" in
    v*)
      if ! git fetch --tags origin; then
        echo "[ERROR] Git fetch of tags failed."
        exit 1
      fi
      if ! git reset --hard "${GIT_BRANCH}"; then
        echo "[ERROR] Git reset to ${GIT_BRANCH} failed."
        exit 1
      fi
      ;;
    *)
      if ! git fetch origin "${GIT_BRANCH}"; then
        echo "[ERROR] Git fetch from ${GIT_BRANCH} failed."
        exit 1
      fi
      if ! git reset --hard "origin/${GIT_BRANCH}"; then
        echo "[ERROR] Git reset to ${GIT_BRANCH} failed."
        exit 1
      fi
      ;;
  esac
```

  Rollback on the NAS then = set `GIT_BRANCH=v0.3` in `.env` and run `deploy_remote.sh`.

### 5) Promotion workflow (standing process — README/AGENTS.md if desired)

```bash
# daily: work + push to dev
git checkout dev && ... && git commit && git push origin dev

# after milestone validation (production cron run / F5 / CheckRecipe):
git checkout main && git fetch origin --prune \
  && git merge --ff-only origin/main   # absorb any daemon/other pushes first
  && git merge --ff-only dev \
  && git push origin main
bash .private/sync_github.sh [tag]     # publish to GitHub (+optional release tag)

# NAS: GIT_BRANCH=main (or a tag to roll back), run deploy_remote.sh
```

- The script fix + plans ride on `dev` until the next promotion (dev tooling/docs, not NAS runtime code).
- Note: once the daemon auto-commits recipe changes (v2 plan M3, from the NAS clone), pushes to `origin/main` will come from the NAS — the `fetch` + `merge --ff-only origin/main` step keeps manual promotions working. Revisit the promotion flow then.
- `feature/*` short-lived branches from `dev` only for large risky chunks (e.g. M3 interactive sessions); small fixes go straight to `dev`.

## Decisions (agreed with user — unchanged)

1. **Trunk-based + release tags** (GitHub-Flow variant, per Gemini's recommendation as chosen by the user). No Git Flow.
2. **Gitea `dev`** = daily work. **Gitea `main`** = verified production state; the **NAS deploys from `main`**. Promotion = `git merge --ff-only dev` after milestone validation. **Never commit directly to `main`** — fast-forward-only snapshot line.
3. **GitHub `main`** = sanitized mirror of Gitea `main` (script builds from `origin/main`, fetched fresh each run) → GitHub reflects the published production state, not in-flight dev.
4. **Release tags:** Gitea-lineage tags on `main` for NAS rollback; optionally the same tag name on the sanitized GitHub tip — **hashes differ by design** (amend); never merge/fetch between the two repos.
5. Old Selenium main tip `807671e` = tag `selenium-final` (done).
6. `.private/sync_github.sh` committed to `dev` (done) — survives fresh clones; stripped from GitHub via `STRIP`.

## Validation

1. After Recovery: on `dev`, `git status --short` shows only the intended entries (banner-edited plan modified, new plan untracked, optionally `kilo.jsonc`).
2. **Regression test for both bugs:** with uncommitted `.kilo` edits present (the post-Recovery state qualifies), run `bash .private/sync_github.sh` twice from `dev` → completes, stays on `dev`, `git status` identical before/after, GitHub `main` unchanged (idempotent), `git worktree list` shows only the main worktree.
3. `git ls-remote github` → `main` = `2606c6d`, tag `v0.3` (after step 3), **no** `playwright`.
4. `git ls-remote origin` → `main` = `b63524f`, `dev` ahead, tags `selenium-final` + `v0.3`, **no** `playwright`.
5. GitHub web: default branch `main` shows the Playwright code; file listing has no `.kilo` / `.vscode` / `.private`.
6. NAS: `deploy_remote.sh` fetches `origin/main`, builds image — content identical to what the NAS runs today. Next monthly cron completes unchanged.
7. (Cheap, optional) `BillCollectorCheckRecipe.py` over all 7 recipes — no code changed, sanity only.

## Risks / notes

- Worktree leak on SIGKILL of the script: trap covers normal failure; `git worktree prune` is the safety net for the rest.
- Recovery's `git checkout -f dev` overwrites untracked `.kilo`/`.vscode` files with `dev`'s committed versions — the `/tmp/kilo/bc-backup` backup holds any unique content; delete it only after confirming everything is restored.
- The script no longer uses the local `public` branch — it is deleted in cleanup to avoid confusion.
- Force-push to `github main` rewrites public main history — accepted; old history survives via `v0.1`/`v0.2` tags.
- Gitea `main` and GitHub `main` have **different hashes** (sanitize-by-amend). Never merge or fetch between the two repos.
- GitHub intentionally **lags** `dev` until promotion — that is the point of the model; don't point the script at `dev`.
- `main` is fast-forward-only; a direct commit on it makes `merge --ff-only` fail loudly (good).

## Out of scope

- GitHub Releases UI objects (the sync script + tags are the release mechanism).
- CI/CD (none exists; NAS deploys stay manual).
- Any CI-triggered auto-deploy.
