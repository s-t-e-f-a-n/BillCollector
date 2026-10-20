# Plan cleanup — finalize: cross-ref fixes, commit, push to Gitea dev

> Status: DELIVERED (2026-10-20) — the 3 plan-file moves to `completed/`,
> the 2 moved-path cross-ref fixes, and the wave1-nas-deploy position refresh
> committed and pushed to Gitea `dev`.
> Continues session ses_ea4fbee95fferz82XIskWdiqf3 (plan-file cleanup), which staged the
> moves and reference updates but stopped before committing.

## State (verified 2026-10-20)

Working tree (uncommitted; staged in the previous session):

- 3 staged renames → `.kilo/plans/completed/`:
  - `1790468502492-gui-concept-dashboard-spec.md`
  - `1792360635843-m3-wave1-closeout.md`
  - `1792521924834-pr17-evidence-selfhealing-refinement.md`
- 3 modified docs:
  - `1790364274061-billcollector-nicegui-daemon-plan.md` — 2 refs gain the
    `completed/` prefix (L361, L419) + DDL fact correction ("not yet implemented" →
    "delivered in M1, 2026-10-11")
  - `1792384312843-wave1-nas-deploy.md` — "Current position" replaced with the verified
    2026-10-20 status (Stages 0–3 done; Stage 4 open)
  - `README.md` — Active table: GUI-spec row replaced by the wave1-nas-deploy row

Both active plans were checked and are current: daemon plan M0–M3 done (M3 status
2026-10-18), M4 + post-Wave 1 open, no PR-#17-related staleness; wave1-nas-deploy
position matches the verified remote state.

## Convention (resolves the previous session's open question)

Documented in `completed/1792360635843` (closeout, step 4) and `README.md`:
full-path references (`.kilo/plans/...`) must resolve; when a file moves, its
references gain the `completed/` prefix — **even inside `completed/` files**.
Bare short names in historical docs and frozen command/script records are NOT
rewritten.

Full audit of all 59 `.kilo/plans/...` path references in the plans tree found
exactly **2** stale full-path references, both fixed in this task:

| # | File (line) | Old | New |
|---|---|---|---|
| 1 | `completed/1792521924834-pr17-evidence-selfhealing-refinement.md` (L11) | `` `.kilo/plans/1792475813001-pr17-browser-evidence-redaction-review.md` `` | `` `.kilo/plans/completed/1792475813001-pr17-browser-evidence-redaction-review.md` `` |
| 2 | `completed/1791705823133-m2-ui-core-plan.md` (L8) | `` `.kilo/plans/1790468502492-gui-concept-dashboard-spec.md` `` | `` `.kilo/plans/completed/1790468502492-gui-concept-dashboard-spec.md` `` |

Note on #1: `1792475813001` was created directly in `completed/` (commit `a3849a2`),
so the reference was stale since creation — not caused by this move. Fixing it is part
of "update its cross-references" for the moved doc.

Left stale by design (frozen command records, not cross-refs):
`completed/1790539917809-gitea-github-branch-strategy.md` L24/L31/L93 (2026-10-12
recovery/commit script), plus the `mv`/`rm` command records in `1792189245102`
(L48, L52–53, L105) and `1792337230912` (L125–126).

## Tasks (ordered)

1. **Apply the two one-line reference fixes** above (exact old→new strings).
2. **Update this plan file**: set Status to DELIVERED (2026-10-20) and record the
   delivery (moves + ref fixes + position refresh committed and pushed to Gitea
   `dev`) in this header block. Do not embed the commit's own SHA (repo pattern:
   delivery notes name the work, not their own SHA — see `6c668ab`).
3. **Pre-commit sanity** (all read-only; halt and report if any deviation):
   - `git status --short` shows exactly: 3 renames (the refinement one as `RM`),
     ` M` for daemon plan, wave1-nas-deploy, README, and
     `completed/1791705823133-m2-ui-core-plan.md`, plus `??` this plan file — all
     under `.kilo/plans/`, nothing else.
   - Reference audit: every `.kilo/plans/...` path reference resolves to an existing
     file except the 3 frozen lines in `1790539917809` (L24, L31, L93).
   - `grep -rn "1790468502492\|1792360635843\|1792521924834" .kilo/plans/*.md`
     (active root docs only) → only the 2 `completed/`-prefixed hits in the daemon
     plan.
   - README Active table lists exactly the 2 root files.
4. **Propose the commit** per the dev-commits skill (suggest only; wait for the
   user's explicit confirmation):
   - Message: `doc: plans: retire the GUI spec, the M3 Wave 1 closeout, and the pr17 refinement plan; fix moved-path cross-refs; refresh the wave1-nas-deploy position`
   - Content: the 3 renames + 4 modified docs + this plan file (8 paths, all under
     `.kilo/plans/`).
5. **Commit + push** (after user confirmation): `git add` the 8 paths, commit,
   `git push origin dev` (Gitea). Do NOT touch the GitHub mirror — `.kilo` is in the
   `STRIP` list of `.private/sync_github.sh`; the mirror is refreshed only at the next
   promotion (out of scope).

## Validation (after push)

- `git status --short` → clean.
- `git ls-remote origin refs/heads/dev` == `git rev-parse dev`.
- Re-run the reference audit → only the 3 frozen command-record lines stale.
- `ls .kilo/plans/*.md` → exactly the 2 active plans + README.

## Risks / failure modes

- Tree drifted since the previous session (other session touched `.kilo/plans/`) →
  re-audit before committing; if it deviates from the recorded state, halt and report.
- Commit would include paths outside `.kilo/plans/` → do not commit; unstage and report.
- Push rejected (remote moved) → `git fetch` and inspect first; report to the user.
  No rebase, no force-push without explicit instruction.

## Out of scope

- GitHub mirror sync (next promotion only).
- wave1-nas-deploy Stage 4 (NAS deploy + daemon cutover) — separate user-gated work.
- Deep review of the daemon master plan — milestone statuses verified current; nothing
  stale found.
