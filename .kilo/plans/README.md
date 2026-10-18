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
| `1790364274061-billcollector-nicegui-daemon-plan.md` | Master daemon plan (v3): M0/M1/M2 done, M3 in progress (live Wave 1 exit pass pending), M4 + post-Wave 1 flowcool concessions open |
| `1791998985158-m3-interactive-sessions-plan.md` | M3 execution plan: S1/S2 done, S3 exit pass in progress |
| `1792126455141-m3-wave1-exit-pass-guide.md` | M3 Wave 1 exit pass operator guide (complete; live pass pending) |
| `1790468502492-gui-concept-dashboard-spec.md` | GUI concept + dashboard spec — design reference (implemented in M2 D2 + M3 S1) |
