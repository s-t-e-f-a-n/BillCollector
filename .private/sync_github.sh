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

# Pin the committer date to the source commit so the amend is deterministic:
# re-running the script must not rewrite GitHub main to a new hash.
export GIT_COMMITTER_DATE="$(git log -1 --format=%ct HEAD)"

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