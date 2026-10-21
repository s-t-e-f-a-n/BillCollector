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
| `1792384312843-wave1-nas-deploy.md` | Wave 1 NAS deploy: Stages 0–3 done (anchor tag, promotion to `main` `3b406f0`, GitHub mirror); Stage 4 NAS deploy + daemon cutover pending |
| `1792622454541-pr23-residual-logs-review.md` | PR #23 review (residual runner exceptions in retained logs): S1 review + S2 plan done, verdict APPROVE, AWAITING-DECISION |
