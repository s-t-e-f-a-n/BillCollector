# Private AI-coding artifacts: Gitea/GitHub boundary strategy

## Delivered

- **Delivered (2026-10-18).** Seven commits `105f30d..c6ff24f` on Gitea `dev`
  (pushed). `STRIP` in `.private/sync_github.sh` covers the 7 private paths (read
  from the working tree at run time); `openwiki/`, `AGENTS.md`, `.openwikiignore`,
  and `.github/workflows/openwiki-update.yml` are versioned private-only;
  `openwiki/.run.json` is gitignored; the deploy and pr-review skills are extended
  to the full private set; the local `openwiki code --update` refresh documents
  the 7-path `STRIP` in `openwiki/operations/deployment.md`. Validation: 7-path
  STRIP dry-run clean in a throwaway worktree; `git ls-files` lists exactly the
  committed set minus `.run.json`. The GitHub mirror is untouched until the next
  promotion (the extended Stage 3 listing check is the gate). Follow-up:
  `.kilo/plans/completed/1792337230912-openwiki-boundary-followup.md` — A: the inert
  workflow secrets were never created (0 secrets / 0 variables on both repos,
  nothing to delete); C: the openwiki usage policy landed in `AGENTS.md`
  (commit `63474d1`).

## Goal

Make the private/public split for local AI-coding artifacts explicit and durable:
everything tied to local agent tooling (plans, skills, wiki, agent policy, refresh
setup) lives in the private Gitea repo and is stripped from the public GitHub
mirror by the existing `sync_github.sh` flow. AI assistance in general stays
openly acknowledged via CONTRIBUTING.md ("AI-assisted code is welcome — declare
it in the PR"); the tooling and procedures stay private.

## Current state (verified 2026-10-18)

- `origin` = Gitea (private, source of truth): `dev` = work, `main` = published.
  `github` = sanitized mirror of Gitea `main` only, built by
  `.private/sync_github.sh` (throwaway worktree, sanitize-by-amend, force-push;
  `STRIP` list is read from the **local working tree** at run time).
- Untracked AI-local artifacts: `openwiki/` (pages + `.claims/` + `INSTRUCTIONS.md`
  brief + `.run.json`), `AGENTS.md` (openwiki-managed block), `.openwikiignore`,
  `.github/workflows/openwiki-update.yml`.
- Pending uncommitted change: `sync_github.sh` STRIP gained `"openwiki"`
  (committed version still has only `.kilo .vscode .private`).
- Public GitHub today: no `AGENTS.md`, no `openwiki`, `.github/` holds only
  `ISSUE_TEMPLATE`, no open PRs -> **nothing has leaked yet**.
- The wiki's own `openwiki/operations/deployment.md:172` already documents the
  intent: "the wiki tree itself ships only in the private copy".
- `.gitignore` does not cover `openwiki/.run.json` (transient openwiki run state).

## Decisions (user-confirmed)

1. `openwiki/` stays **fully private** (whole directory in STRIP; no per-file
   publication of pages).
2. `openwiki-update.yml`: commit to Gitea **and** add to STRIP. It never runs on
   the public repo (it would open public PRs adding the wiki). Wiki refresh is a
   local `openwiki code --update` run.
3. `AGENTS.md`: commit to Gitea **and** add to STRIP (versioned, present in
   worktrees, never published). A short strategic section is added **outside**
   the `OPENWIKI:START/END` managed markers (the openwiki tool rewrites that
   block on local runs; never hand-edit inside the markers).
4. `.openwikiignore`: commit to Gitea + add to STRIP.
5. `openwiki/.run.json`: gitignored (transient; the workflow template also
   `rm -f`s it before committing).

## Tasks

### 1. Finalize the STRIP list — `.private/sync_github.sh:12`

```
STRIP=( ".kilo" ".vscode" ".private" "openwiki" "AGENTS.md" \
        ".openwikiignore" ".github/workflows/openwiki-update.yml" )
```

Keep the existing header comment. Add one comment line noting that STRIP is
read from the local working tree at run time, so the local script must be
current before a sync.

### 2. `.gitignore` — add `openwiki/.run.json`

### 3. `AGENTS.md` — strategic section after the `OPENWIKI:END` marker

Short bullets (3-5), e.g.:
- `openwiki/`, this file, `.openwikiignore`, and
  `.github/workflows/openwiki-update.yml` are private local agent context; they
  must never be published to the GitHub mirror (enforced by STRIP in
  `.private/sync_github.sh`).
- The wiki is refreshed locally with `openwiki code --update`; the GitHub
  Actions workflow is kept in the private repo only as the record of the setup
  and is not published.
- When a wiki page and the code disagree, the code wins; hand-editing generated
  pages only when explicitly asked (consistent with the managed block).
- Detailed openwiki usage policy (consult depth, claims usage, page updates on
  change) is deferred to a follow-up task.

### 4. Commit on `dev` via the dev-commits skill (one concern per commit,
per-item user confirmation)

Order matters (wiki refresh last, so it documents the final STRIP):

a. `Add: openwiki evidence index (private)` — `openwiki/` (`.run.json` excluded
   by gitignore)
b. `Add: AGENTS.md and .openwikiignore (private agent context)`
c. `Add: openwiki-update workflow (private, stripped from mirror)` —
   `.github/workflows/openwiki-update.yml`
d. `Make: sync_github.sh STRIP covers all AI-local artifacts` —
   `sync_github.sh`, `.gitignore`
e. Local wiki refresh: `openwiki code --update`, then commit
   `docs: refresh openwiki after STRIP change` —
   `openwiki/operations/deployment.md:172` currently documents the old
   4-path STRIP; the refresh corrects it. (If the refresh is unavailable in
   the implementing session, park e and flag the page as stale.)

Then `git push origin dev` (private; the GitHub mirror is unaffected until the
next promotion, because Gitea `main` does not yet contain these files).

### 5. Update the deploy skill — `.kilo/skills/deploy/SKILL.md`

- Invariants (line 22-23): replace "`.kilo/`, `.vscode/`, `.private/` must never
  reach GitHub" with the full private set: `.kilo/`, `.vscode/`, `.private/`,
  `openwiki/`, `AGENTS.md`, `.openwikiignore`,
  `.github/workflows/openwiki-update.yml`.
- Stage 3 verify (line 96): extend "GitHub file listing for `main`: no
  `.kilo`, `.vscode`, `.private`" to the full private set, including "no
  `.github/workflows/` on GitHub".
- Failure modes: add — a sync run with a stale local `sync_github.sh` can leak
  a private path into the pushed tip; the Stage 3 listing check is the safety
  net. On detection: re-run `sync_github.sh` (the amend removes the file from
  the tip); if a release tag points at the leaked tip, remove/re-tag the
  GitHub tag; any history purge is a manual user decision, reported first.

### 6. Update the pr-review skill — `.kilo/skills/pr-review/SKILL.md`

- Line 23: extend "Never apply files under `.kilo/`, `.private/`, `.vscode/`
  from a PR head" with `openwiki/`, `AGENTS.md`, `.openwikiignore`, and
  `.github/workflows/` (maintainer-private agent context; a community PR adding
  them is flagged, not integrated).
- Lines 196: extend the S7 public-gate listing check with the new private
  paths.

## Interaction with the existing deployment workflow

- Everything lands on `dev` first and stays private. No sync is required today:
  Gitea `main` does not yet contain the new files, so the current GitHub tip is
  already clean.
- At the **next promotion** (deploy Stage 2) the new files enter Gitea `main`;
  Stage 3 then runs `sync_github.sh`, whose amended tip strips them. The
  extended Stage 3 listing check is the public gate.
- Optional, outside the repo (user's call, GitHub UI): delete the now-inert
  GitHub repo secrets/vars used by the unpublished workflow
  (`OPENAI_COMPATIBLE_API_KEY`, `OPENWIKI_LANGSMITH_API_KEY`,
  `LANGSMITH_API_KEY`, `OPENAI_COMPATIBLE_BASE_URL`).

## Validation

1. On `dev` after the commits: `git status --short` shows no untracked AI-local
   artifacts; `git ls-files | grep -E 'openwiki/|AGENTS.md|openwikiignore|workflows'`
   lists exactly the committed set minus `openwiki/.run.json`.
2. Strip dry-run (throwaway worktree from the dev tip, read-only with respect to
   branches): apply the STRIP `git rm -r --cached` list, then `git ls-tree -r
   --name-only HEAD` (post-amend staging) must contain none of: `.kilo`,
   `.vscode`, `.private`, `openwiki`, `AGENTS.md`, `.openwikiignore`,
   `.github/workflows/openwiki-update.yml`.
3. After the first post-change promotion + sync: GitHub `main` file listing
   (API) contains none of the private paths; `git ls-remote github` shows the
   new sanitized hash.
4. Wiki: after the refresh, `openwiki/operations/deployment.md` documents the
   7-path STRIP.

## Failure modes

- Stale local `sync_github.sh` at sync time -> private path leaks into the
  public tip. Caught by the Stage 3 listing check; fix per Task 5 (re-run sync,
  re-tag if needed, report before any history purge).
- OpenWiki rewrites the managed `AGENTS.md` block on the next local run ->
  commit the change; never hand-edit inside the markers.
- `openwiki/.run.json` committed by accident -> removed from the index;
  gitignore prevents recurrence.
- Task 4e (wiki refresh) unavailable in the implementing session -> park it;
  the deployment.md page stays stale (private, cosmetic) until the next local
  refresh.

## Out of scope

- The openwiki **usage policy** for local coding (consult depth, claims
  grounding/drift-check, page-update-on-change rules) — follow-up task with the
  four deferred questions from the previous session.
- Publishing any wiki content to the community — rejected in this decision
  round.
- DuckDNS content in the public README — pre-existing public choice, not
  AI-related.
