#!/usr/bin/env bash
# Sync the sanitized production branch (Gitea main) to GitHub main.
# Usage: ./sync_github.sh [tag]  (optional tag is also created on GitHub)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

TAG="${1:-}"

# Always mirror what is actually published on Gitea
git fetch origin --prune

# Paths to keep off the public face (GitHub)
STRIP=( ".kilo" ".vscode" ".private" )

# Rebuild 'public' directly from the published production branch
git checkout -B public origin/main

# Remove private folders from the staging area
git rm -r --cached --ignore-unmatch "${STRIP[@]}"

# If files were removed, amend the tip commit using its existing message & author info
if ! git diff --cached --quiet; then
  git commit --amend --no-edit \
    --author="Stefan S "
fi

# Push sanitized state to GitHub's main branch
git push --force github public:main

# Optional: tag the sanitized tip (hash differs from Gitea main by design)
if [ -n "$TAG" ]; then
  git tag -f "$TAG"
  git push --force github "$TAG"
fi

# Return to dev branch
git checkout dev