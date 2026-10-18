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
| `1790364274061-billcollector-nicegui-daemon-plan.md` | Master daemon plan (v3): M0–M3 done (Wave 1 exit pass complete 2026-10-18; NAS deploy pending), M4 + post-Wave 1 flowcool concessions open |
| `1790468502492-gui-concept-dashboard-spec.md` | GUI concept + dashboard spec — design reference (implemented in M2 D2 + M3 S1) |
