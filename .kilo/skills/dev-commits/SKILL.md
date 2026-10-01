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
