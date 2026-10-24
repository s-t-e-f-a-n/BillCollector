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
| `1792819039884-recipe-doctor-implementation.md` | Stage 1: offline LLM recipe doctor (`billcollector doctor`) implementation plan + pilot (buhl, datev) — both pilots green 2026-10-24 (runs 16/18, downloads succeeded); extended 2026-10-24 with Stage 1b continuation (remaining 5 services: 1und1, winsim, freenet_mobilfunk, nuernberger via doctor iterations, kabeldeutschland via Option D) |
