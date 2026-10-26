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
| `1792793307574-recipe-repair-llm-options.md` | Public service recipe recovery — LLM-assisted repair options analysis (pre-step); Stage 0 triage done 2026-10-24, all 7 services classified |
| `1792819039884-recipe-doctor-implementation.md` | Stage 1: offline LLM recipe doctor (`billcollector doctor`) implementation plan + pilot (buhl, datev) — both pilots green 2026-10-24 (runs 16/18, downloads succeeded); Stage 1b in progress (2026-10-25): 4/7 green (buhl, datev, nuernberger, winsim), remaining 1und1 (in progress), freenet_mobilfunk (not started), kabeldeutschland (Option D re-authoring) |
| `1792861675256-issue27-maintainer-commitments.md` | Issue #27 product-audit triage (closed 2026-10-24): maintainer-side commitments C1-C8 (F04, F09, F08 contract, F06 contract, F02, F03, F05, F10) with acceptance criteria, dependencies and proposed order |
  | `1792862814701-next-up-sequencing.md` | Next-up sequencing decision (2026-10-24), superseded in part (2026-10-25): C1–C3 done and pushed; current primary next-up is the PR continuation order #30 → #31 → #33 → #32 → #34 (one pr-review chain at a time), interleaved with Stage 1b portal sessions (next: 1und1); PR #30 + #31 DELIVERED 2026-10-25, PR #33 DELIVERED 2026-10-26, PR #32 DELIVERED 2026-10-26 (Gitea `main` `bde713c` / GitHub `93bfcc8`), next PR chain: #34 |
