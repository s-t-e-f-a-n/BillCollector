# BillCollector — Plan Files Audit: Legacy vs Active

**Date:** 2026-10-04 · **Scope:** the 11 files in `.kilo/plans/`
**Method:** each file's stated goal + explicit status markers, cross-checked
against git history, CHANGELOG (v0.3 / v0.4), and the current tree.

## Result

**Active (2)**

| File | Why active |
|---|---|
| `1790364274061-billcollector-nicegui-daemon-plan.md` | Master daemon plan (v2). M0 done (selenium drop, logging, deps, manual-run UI, regression env); **M1-M4 not started** — no `billcollector/` package or daemon artifacts in `apps/`. |
| `1790468502492-gui-concept-dashboard-spec.md` | "implementation-ready. Execute Session 1 in a new implementation session." Session 1 = M1 kickoff (DB + config + CLI + app skeleton). Its prerequisites (baseline commits `bf5669c`, `b63524f`) were executed. Also the detailed dashboard spec the v2 plan defers to. |

**Legacy (9)**

| File | Verdict | Evidence |
|---|---|---|
| `1790289661685-billcollector-daemon-webui-plan.md` | **Superseded** | v2 plan header: "Supersedes `.kilo/plans/1790289661685-...`". (v1 stack FastAPI/Jinja2/htmx; v2 = NiceGUI.) |
| `1790371260966-ubuntu-2404-wsl-migration.md` | **Done** | Remainder plan header: migration "done and verified (2026-09-26)" — distro, Python 3.12.3, fresh venv, CheckRecipe green. |
| `1790380374270-ubuntu-2404-migration-remainder.md` | **Delivered (v0.3)** | Content = "Restore the Playwright Batch Path (M0 step 1)". Selenium removal shipped in `bf5669c`; CHANGELOG v0.3 "Removed: Selenium support". |
| `1790462762560-logger-replace-prints.md` | **Delivered (v0.3)** | CHANGELOG v0.3 "Logging reworked on the `logging` module: rotating `bc.log` (5 MB x 5 backups) plus plain stdout". |
| `1790465908381-nicegui-manual-run-ui.md` | **Delivered (v0.3)** | CHANGELOG v0.3 "NiceGUI manual run UI (`apps/bc_ui.py`) ... `--service <NAME>` filter"; `apps/bc_ui.py` present in tree. |
| `1790539917809-gitea-github-branch-strategy.md` | **Complete (executed record)** | Header: "Status: COMPLETE (2026-09-27) ... Sections below are the executed record." Still cross-referenced by `.kilo/skills/deploy/SKILL.md` as the strategy source ("Promotion workflow" + decisions) — keep, don't delete. |
| `1790625192832-flowcool-fork-extensions.md` | **Consumed input** | One-time analysis catalog ("Input for ... daemon-plan v2", verdict per fork extension). Not referenced by the v2 plan (verdicts applied during the v2 edit or still pending manual incorporation — either way it is not an executable to-do; the v2 plan is the master). |
| `1790714158680-local-regression-test-web-service.md` | **Delivered — Layer A (v0.4)** | Layer A (mock portal + harness, `tests/`) shipped in v0.4 (CHANGELOG v0.4, files in tree). Layer B scenario execution is explicitly deferred to daemon milestones M1/M3 and owned there, not by this plan. |
| `1790891025465-deploy-skills-plan.md` | **Delivered (2026-10-01), header stale** | Both skills committed (`8be7a8a`, `e466553`) and the deploy skill has since **diverged** from the plan (release-notes stage + changelog-ordering fix, `f27719e`). The skills are now the source of truth; the header still reads "READY FOR IMPLEMENTATION". |

## Suggested follow-up (implementation session)

Add a one-line status banner under the H1 of each of the 9 legacy files
(precedent: `1790380374270` already carries one), e.g.:

- `> Status: SUPERSEDED by 1790364274061-billcollector-nicegui-daemon-plan.md (v2).`
- `> Status: DONE (2026-09-26) — verified; retained for the record.`
- `> Status: DELIVERED in v0.3 (commit bf5669c) — retained for the record.`
- `> Status: DELIVERED in v0.4 (tag v0.4) — Layer A; Layer B execution lands with daemon M1/M3.`
- `> Status: COMPLETE (2026-09-27) — executed record; the standing process now lives in .kilo/skills/deploy/SKILL.md.`
- `> Status: DELIVERED (2026-10-01, commits 8be7a8a/e466553) — the skills are now the source of truth and have since diverged from this plan.`
- `> Status: CONSUMED — one-time input for the v2 daemon plan; no further action.`

Do **not** move or archive the files (they are small, git keeps them, and the
deploy skill + daemon plan cross-reference them by path).

**Validation:** `git diff --stat` shows exactly 9 files, header-line-only
changes; re-read the two active files' cross-references (daemon v2 →
`1790468502492`, deploy skill → `1790539917809`) still resolve.

**Suggested commit (per dev-commits skill, suggest-only):**
`doc: plans: add status banners to delivered/superseded plan files`
