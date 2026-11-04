# Plan-file cleanup — archive consumed plans, refresh stale statuses (2026-11-05)

> Status: DELIVERED (2026-11-05) — T1–T5 done: the 2 consumed plans (options
> analysis, next-up sequencing) archived to `completed/` (closing entry
> appended to next-up) with cross-refs updated (README Active table, doctor
> plan, issue27 plan, open-issues-plans-20261027); issue27 + doctor status
> sections refreshed. T6: single doc-only commit (dev-commits, user-confirmed)
> pushed to Gitea `origin/dev`; no GitHub mirror sync (private path). This
> doc moved to `completed/` in the same commit.

User-gated decision (2026-11-05): full cleanup. Doc-only work; no source
changes, no GitHub mirror sync (`.kilo/plans` is private, never published by
the sync script).

## Verified state (basis for the cleanup)

- Open plans: `recipe-repair-llm-options` (consumed), `next-up-sequencing`
  (consumed), `recipe-doctor-implementation` (active, 4/7 green, status
  stale), `issue27-maintainer-commitments` (active, C5–C7 open, status stale).
- Doctor implementation exists: `apps/billcollector/doctor.py` +
  `tests/test_bc_doctor.py`. Stage 1b: buhl (run 16), datev (18),
  nuernberger (21), winsim (30) green. 1und1 fix committed (`c29d978`) but
  runs 22–25 still paused `step_failed`; freenet_mobilfunk and
  kabeldeutschland not started. No local portal runs since 2026-10-25
  (latest run artifacts: `apps/data/runs/` 22–30).
- C4 DELIVERED 2026-11-02 (Gitea `main` `67b5b38` / GitHub `21ef9f3`), C8
  DELIVERED 2026-11-03 (Gitea `main` `2485719` / GitHub `eb06503`) per the
  archived C4/C8 plan (`completed/1793551618380-...`); issue #24 closed as
  completed 2026-11-03 by the maintainer; issue #26 closed 2026-10-27
  (PR #34). Issue #59 open — adapter boundary accepted 2026-11-04 (comment
  6644532027), awaiting flowcool's engine PR; issue #52 proposal posted
  2026-11-03 (comment 6604836002), awaiting flowcool.
- Working tree clean (only untracked `.private/notes.txt`); dev tip
  `1220e68`.

## Tasks

### T1 — Closing entry in next-up-sequencing (before the move)

In `1792862814701-next-up-sequencing.md`, append a final dated entry
(`Closing (2026-11-05)`, same log style as the existing entries) recording:

- All sequenced work complete: PR chain #30 → #58 delivered, no open PRs on
  the mirror; C1–C3 done; C4/C8 delivered (2026-11-02/03) via the C4/C8
  plan; issue #24 closed 2026-11-03.
- Current next-up snapshot (each item's own plan is the tracker): Stage 1b
  remainder 1und1 / freenet_mobilfunk / kabeldeutschland (doctor plan);
  C5 (F02 design), C6 (F03 design), C7 (F05 conversion, ride the Stage 1b
  portal windows) — issue27 plan; issue #59 engine PR (new pr-review plan
  when the PR arrives); issue #52 (awaiting flowcool response).
- Doc archived to `completed/` as consumed; new sequencing decisions start a
  fresh doc.

### T2 — Move the two consumed plans

- `mv .kilo/plans/1792793307574-recipe-repair-llm-options.md .kilo/plans/completed/`
- `mv .kilo/plans/1792862814701-next-up-sequencing.md .kilo/plans/completed/`

Note: this deviates from the doctor plan's wrap-up rule that tied both moves
to "after all seven are green" — the options doc has no remaining execution
steps (Stage 0 done; Options A/B/D executed or tracked in the doctor plan;
Stage 2/C is explicitly a separate plan). The doctor doc itself still moves
only at all-green.

### T3 — Fix cross-references (README rule: moved files gain the `completed/` prefix at reference sites)

- `.kilo/plans/README.md`:
  - remove the Active-table rows for the two moved files;
  - update the doctor row: 4/7 green, no runs since 2026-10-25, options doc
    archived;
  - update the issue27 row: C1–C4 + C8 done (C4 2026-11-02, C8 2026-11-03),
    C5/C6/C7 remaining.
- `1792819039884-recipe-doctor-implementation.md` (lines 7, 363): options-doc
  reference → `completed/` prefix.
- `1792861675256-issue27-maintainer-commitments.md` (line ~240):
  next-up reference → `completed/` prefix.
- `completed/1793124431799-open-issues-plans-20261027.md` (line 17):
  next-up reference → `completed/` prefix.
- References in `completed/1793551618380-...` to the issue27 plan stay
  unchanged (file not moved).

### T4 — issue27 plan status refresh (stays Active)

- C4 section: Status → done 2026-11-02 (Delivery A of the C4/C8 plan; Gitea
  `main` `67b5b38` / GitHub `21ef9f3`).
- C8 section: Status → done 2026-11-03 (Delivery B; Gitea `main`
  `2485719` / GitHub `eb06503`).
- Related lanes: #24 → CLOSED completed 2026-11-03 (maintainer); #26 →
  closed 2026-10-27 (PR #34 delivered).
- Status section: "C1–C4 and C8 delivered; remaining C5 (F02 recipe-storage
  design), C6 (F03 noVNC access design), C7 (F05 protected-login
  conversion — schedule with the remaining Stage 1b portal windows). Plan
  stays Active until C5–C7 are delivered."

### T5 — Doctor plan status refresh (stays Active)

- Add a dated status entry (2026-11-05) after the 2026-10-25 one: still 4/7
  green; no local portal runs since 2026-10-25 (1und1 last run 25, paused
  `step_failed`); engine moved on main since (C4/C8 result semantics, #57
  incremental keys, #58 ZIP unpack) — per-iteration loop unchanged, but the
  next session re-verifies assumptions against the current tree; options doc
  archived to `completed/`.
- Wrap-up section: note the options doc moved ahead of the all-green
  archival of this doc.

### T6 — Commit + push (dev-commits skill, user confirms)

Single doc-only commit, e.g. `doc: plans — archive consumed plans (options
analysis, next-up sequencing), refresh issue27 + doctor status sections`,
push to Gitea `origin/dev`. No GitHub mirror sync (private path only).

## Validation

- `ls .kilo/plans/` → exactly the 2 active plans + README + `completed/`.
- Repo-wide grep for the two moved filenames without the `completed/` prefix
  → zero reference hits (the files' own paths aside).
- README Active table lists exactly `recipe-doctor-implementation` and
  `issue27-maintainer-commitments`.
- Working tree clean after the commit (`.private/notes.txt` stays untracked).

## Out of scope

- Executing the remaining Stage 1b services (1und1, freenet_mobilfunk,
  kabeldeutschland) — needs portal-access windows, separate sessions.
- C5/C6/C7 design work — separate sessions per the issue27 plan.
- GitHub mirror sync / release work — not triggered by private plan files.
