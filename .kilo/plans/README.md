# Kilo plan files

Layout (since 2026-10-11):

- **Root** (this directory): active plans — current execution plans and open
  references.
- **`completed/`**: delivered, done, superseded, or consumed plans — retained for
  the record, not for execution.

Rule: when a plan is fully delivered (or superseded/consumed), move it to
`completed/` and update its cross-references. References use `.kilo/plans/...`
paths, so a moved file gains the `completed/` prefix.

## Active

| File | Role |
|---|---|
| `1792819039884-recipe-doctor-implementation.md` | Stage 1: offline LLM recipe doctor (`billcollector doctor`) implementation plan + pilot (buhl, datev) — both pilots green 2026-10-24 (runs 16/18, downloads succeeded); Stage 1b (2026-10-25): 4/7 green (buhl, datev, nuernberger, winsim), remaining 1und1 (fix committed `c29d978`, runs 22–25 still paused `step_failed`), freenet_mobilfunk + kabeldeutschland not started; no local portal runs since 2026-10-25; options doc archived to `completed/` 2026-11-05 |
| `1792861675256-issue27-maintainer-commitments.md` | Issue #27 product-audit triage (closed 2026-10-24): maintainer-side commitments C1-C8 (F04, F09, F08 contract, F06 contract, F02, F03, F05, F10) — C1–C4 + C8 done (C4 2026-11-02, C8 2026-11-03), C5/C6/C7 remaining |
