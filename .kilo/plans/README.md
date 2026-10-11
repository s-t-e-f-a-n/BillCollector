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
| `1790364274061-billcollector-nicegui-daemon-plan.md` | Master daemon plan (v3): M0/M1 done, M2 in progress, M3/M4 open |
| `1791705823133-m2-ui-core-plan.md` | M2 execution plan (chunks D1–D6, in progress) |
| `1790468502492-gui-concept-dashboard-spec.md` | GUI concept + dashboard spec — reference for M2 (D2) and M3 (session view) |
