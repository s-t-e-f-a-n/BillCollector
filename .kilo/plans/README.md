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
| `1792861675256-issue27-maintainer-commitments.md` | Issue #27 product-audit triage (closed 2026-10-24): maintainer-side commitments C1-C8 (F04, F09, F08 contract, F06 contract, F02, F03, F05, F10) — C1–C6 + C8 done (C4 2026-11-02, C8 2026-11-03, C5 2026-11-09, C6 2026-11-11, C6 released as v0.6 2026-11-16), C7 remaining |
| `1794863968112-ui-navigation-dark-theme.md` | UI navigation, icon actions & manual pause pass (refined 2026-11-17): 5-item drawer, `/tasks` + `/recipes` index pages, icon actions with hover tooltips, manual pause (SIGUSR1, pause at next step boundary, morphing Run/Pause buttons), settings single-Save restructure, table alignment/label/mono convention, run-review reachability (View run) — implementation + tests + docs green 2026-11-17, full suite re-green 2026-11-18 (880/11); pushed to Gitea `origin/dev` (nav pass `cee453b`..`2cf2503`, waiting-state Resume/Stop, stable row-position fix `e9f6671`); N16 manual verification in progress on the NAS dev deployment. Consumed `completed/1794763657924-manual-pause-button.md` (marked CONSUMED 2026-11-17) |
| `1794866943286-ui-dark-theme.md` | UI dark-theme polish (follow-up, ships after the navigation pass): design tokens, `theme.py`, `ui.dark_mode`, chrome reskin, header icon / version chip / "Daemon active" pill, dashboard KPI strip, dark-readability audit, CodeMirror dark theme, login restyle — PLANNED (reconstructed 2026-11-17); its prerequisite (the navigation pass) is implemented and pushed, N16 verification in progress |
