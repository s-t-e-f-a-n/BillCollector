# Plan audit: status/relationship updates + concessions merge

**Goal:** bring all `.kilo/plans/` files in line with the actual state (M0/M1/M2 done,
M3 in progress with the live Wave 1 exit pass pending), merge the Discussion #8
concessions plan into the master daemon plan, delete the now-redundant concessions
file, and refresh the plans README. No source code is touched.

## Audit result (verified against the plan files + git, 2026-10-17)

| File | Self-declared | Actual state | Stale? |
|---|---|---|---|
| `1790364274061-…nicegui-daemon-plan.md` (master) | M2 "in progress"; M1 status frozen at C1–C4 (2026-10-10); M3 has no status line | M0/M1/M2 **done**; M3 **in progress** (S1/S2 done 2026-10-15; S3 guide done 2026-10-16, live pass pending); M4 open | yes |
| `1791705823133-m2-ui-core-plan.md` | progress records only | **Delivered** — D6.4 exit pass complete 2026-10-14, suite 253/253, ruff clean | yes (no top status; belongs in `completed/`) |
| `1791829791901-m2-d64-exit-pass-guide.md` | "exit pass complete" (review log) | **Delivered** — pass 2026-10-14 complete; two findings stay open in its review log (#1 thumbnail width, deferred cosmetic; #11 display-lock leak, fix candidate recorded) | no (belongs in `completed/`) |
| `1791998985158-m3-interactive-sessions-plan.md` | S1.1–S2.4 done, S3.1–S3.5 done, "live pass is run by the operator" | matches | no (only M2 cross-refs gain a prefix if moved) |
| `1792126455141-m3-wave1-exit-pass-guide.md` | "No passes recorded yet — the guide is being written in S3.1–S3.5" | guide is **complete** (S3.5 done 2026-10-16); live pass pending | yes (that one sentence) |
| `1790468502492-gui-concept-dashboard-spec.md` | "Session 1 delivered; the dashboard spec is implemented in M2" | fully implemented (M2 D2 done; M3 S1 session view done 2026-10-15) — design reference | status line stale |
| `1792189620000-flowcool-concessions-realization.md` | DRAFT; cites `1792185181020-discussion-8-flowcool-reply.md` as "commitments source (completed)" | that referenced reply plan **no longer exists on disk** (never committed; only the concessions file is untracked in git) | merge + delete |
| `README.md` | Active table lists 3 plans, "M2 in progress, M3/M4 open"; omits both M3 files + the concessions plan | stale | yes (rewrite) |

## Decisions (default = recommendation; confirm at review)

- **D1 — Concessions destination: the master daemon plan.** New milestone section
  `### Post-Wave 1 — flowcool concessions (Discussion #8)` after M4. Rationale: A and B
  are daemon features (recipe contract / DB schema + task state) that follow Wave 1; the
  master plan owns the milestone sequence. The M3 plan is scoped to interactive sessions
  (wrong home); a new file is excluded by the request.
- **D2 — Move the two delivered M2 plans to `completed/`** (the README rule: delivered
  plans move there and references gain the `completed/` prefix). The two open M2 findings
  stay tracked in the guide's review log; moving does not close them.
- **D3 — GUI spec stays at the root** as a design reference (the README defines the root
  as "current execution plans and open references"); only its status line is updated.
  Alternative: move it to `completed/` like the M2 files.
- **D4 — Fix the dangling commitments reference.** The reply-plan file
  `1792185181020-discussion-8-flowcool-reply.md` is gone; the commitments source becomes
  the posted reply itself: **Gitea Discussion #8 (Roadmap), comment 18930306, 2026-10-16**.
- **D5 — Naming constraint (user, 2026-10-16):** "flowcool" must not appear in **file
  names** or **commit messages**. Every file created/renamed in this task uses a neutral
  name; when these changes are committed later (dev-commits skill), the suggested
  message avoids the name, e.g. `doc: plans: audit plan status, add post-Wave 1
  concessions section, retire the concessions plan`. Prose inside plan files keeps the
  accurate attribution ("reply to flowcool") — only names and commit messages are
  constrained.

## Ordered task list

0. **Delete this plan's predecessor** (renamed per D5, plan mode could not `mv`/`rm`):
   `rm .kilo/plans/1792189245102-plan-audit-and-flowcool-merge.md` — its content is
   fully superseded by this file.

1. **Move the delivered M2 plans** (D2):
   `mv .kilo/plans/1791705823133-m2-ui-core-plan.md .kilo/plans/completed/`
   `mv .kilo/plans/1791829791901-m2-d64-exit-pass-guide.md .kilo/plans/completed/`

2. **Master plan** (`1790364274061-billcollector-nicegui-daemon-plan.md`):
   - Wave 1 scope (lines 119–120): "M0 is done (status below); M4 … is the follow-up
     wave." → "M0, M1 and M2 are done (status below); M3 is in progress (the live Wave 1
     exit pass is pending); M4 (adoption for other users) and the post-Wave 1 flowcool
     concessions are the follow-ups."
   - M1: replace the bullet at lines 737–739 ("Remaining M1 chunks: **C6, C7** … M2 UI
     pages follow.") with:
     "- **M1 complete (2026-10-11):** C5.1–C7.5 committed + pushed to `origin/dev`;
     C7.6 exit validation done; full unit suite 155/155 green. The C5 → C7 section below
     is the historical execution record; M2 followed (done 2026-10-14)."
   - M2 section (lines 1165–1166): "Execution plan (in progress):
     `.kilo/plans/1791705823133-…`" → "Execution plan — **done (2026-10-14)**:
     `.kilo/plans/completed/1791705823133-m2-ui-core-plan.md` (chunks D1–D6); D6.4 exit
     pass guide: `.kilo/plans/completed/1791829791901-m2-d64-exit-pass-guide.md`."
   - Fast-track note (line 466): add the `completed/` prefix to the M2 plan path.
   - M3 section: insert after the heading:
     "> **Status (2026-10-16):** S1 (session view) + S2 (recipe repair flow) done and
     committed (2026-10-15); S3 Wave 1 exit pass — operator guide complete (2026-10-16),
     **live pass pending** (operator-driven, recorded in the guide's review log).
     Execution plan: `.kilo/plans/1791998985158-m3-interactive-sessions-plan.md`;
     exit pass guide: `.kilo/plans/1792126455141-m3-wave1-exit-pass-guide.md`."
   - Insert the new section below **after the M4 section** (exact text to paste):
     → see "Section to insert" at the end of this plan.

3. **M3 plan** (`1791998985158-m3-interactive-sessions-plan.md`): lines 5–6 — add the
   `completed/` prefix to the M2 plan and the M2 D6.4 guide paths.

4. **M3 Wave 1 exit pass guide** (`1792126455141-m3-wave1-exit-pass-guide.md`):
   - lines 10 and 546: add the `completed/` prefix to the M2 D6.4 guide path.
   - review log (lines 18–19): "the guide is being written in S3.1–S3.5" → "the guide is
     complete (S3.5 done 2026-10-16)".

5. **M2 plan header** (`completed/1791705823133-…`): insert after the title:
   "**Status: DONE (2026-10-14).** D1–D6.4 complete; D6.4 exit pass complete (steps
   0–11); suite 253/253 green, ruff clean. Moved to `completed/` per the plans README
   rule."

6. **M2 D6.4 guide header** (`completed/1791829791901-…`): insert after the title:
   "**Status: exit pass complete (2026-10-14).** Open review-log findings stay tracked
   here: #1 (dashboard step-strip thumbnail width — deferred, cosmetic) and #11 (SIGKILL
   display-lock leak — fix candidate recorded)."
   Also: line 303 — add the `completed/` prefix to the M2 plan path (both files moved
   together, so the written path changes).

7. **GUI spec** (`1790468502492-…`, stays at root per D3): status block (lines 3–5) →
   "**Status:** Session 1 delivered (M1, done 2026-10-11); the dashboard spec is
   implemented (M2 D2, done 2026-10-14) and the session view is built (M3 S1, done
   2026-10-15) — design reference only."

8. **Delete the concessions plan:**
   `rm .kilo/plans/1792189620000-flowcool-concessions-realization.md`
   (untracked in git — no history impact). Its content moves in task 2's new section,
   with the one correction from D4 (commitments source).

9. **README.md** (plans index) — replace the Active table:

   | File | Role |
   |---|---|
   | `1790364274061-billcollector-nicegui-daemon-plan.md` | Master daemon plan (v3): M0/M1/M2 done, M3 in progress (live Wave 1 exit pass pending), M4 + post-Wave 1 flowcool concessions open |
   | `1791998985158-m3-interactive-sessions-plan.md` | M3 execution plan: S1/S2 done, S3 exit pass in progress |
   | `1792126455141-m3-wave1-exit-pass-guide.md` | M3 Wave 1 exit pass operator guide (complete; live pass pending) |
   | `1790468502492-gui-concept-dashboard-spec.md` | GUI concept + dashboard spec — design reference (implemented in M2 D2 + M3 S1) |

## Section to insert (master plan, after the M4 section)

```markdown
### Post-Wave 1 — flowcool concessions (Discussion #8)

> **Status: PLANNED — gated on Flo's issues.** The 2026-10-16 reply to flowcool
> (Gitea Discussion #8, Roadmap, comment 18930306) committed to the two **daemon**
> features below (unpublished work, not the public batch variant) plus the deployment
> timeline (item C). Per the process confirmed with Flo, each feature is agreed in an
> issue he opens before code (A touches the recipe contract; B touches the task state /
> DB schema — both shared interfaces per CONTRIBUTING). This section locks the confirmed
> architecture so realization can start once the issues land.

**A — Date variables in recipes.** Fixed set: `{{TODAY}}`, `{{DATE_FROM}}`,
`{{DATE_TO}}`, day offsets (`{{DATE-7d}}`); usable in `goto` URLs and `fill` arguments;
timezone from the daemon's locale.

**B — Login-failure lock.** (1) single-attempt-with-pause for login steps;
(2) per-task consecutive-failure counter → auto-disable after N + ntfy notify;
(3) UI "clear" action to re-enable.

**C — Deploy timeline (PS: "2–3 more days").** Not a feature: the in-progress daemon
deployment (Wave 1 exit = the M3 Wave 1 exit pass + the NAS deploy via the deploy
skill). No new work beyond finishing that.

**Confirmed decisions**

- **B — login-failure identification = explicit recipe flag.** A step marked
  `login: true` is a login step: it gets single-attempt-with-pause semantics, and
  **only** its failure feeds the consecutive-failure counter. Non-login failures
  never increment it.
- **A + B are daemon features.** Recipes stay static YAML: variables expand at run time
  and are never written back into the recipe file.
- **B storage = additive Task columns** (follow the existing `_migrate` pattern,
  `apps/billcollector/db.py:104-115`): `consecutive_failures INTEGER NOT NULL DEFAULT 0`
  and `disabled_reason TEXT` (NULL = not auto-disabled; `'login_failures'` = locked).

**A — date variables**

Integration point (current mechanism):
- `VARIABLE_MAP` — `apps/helpers/BillCollectorHelpers.py:100`
  (`{{USERNAME}}`/`{{PASSWORD}}`/`{{OTP}}`); extended at `apps/billcollector/runner.py:161`
  (`{{OTP}}` → fresh TOTP).
- Substitution — `apps/billcollector/runner.py:338-355` (`process_argument`): replaces a
  string **only when it exactly equals** a map key. An embedded token
  (`...?from={{DATE_FROM}}`) is **not** substituted today.

Change:
1. Extend `process_argument` to resolve **embedded** `{{...}}` tokens in any string
   argument (and string values in argument dicts) via a regex pass — not just exact-key
   matches. This is what makes dates usable inside `goto` URLs.
2. Add date resolution: `{{TODAY}}`, `{{DATE_FROM}}`, `{{DATE_TO}}`, and the day-offset
   pattern `{{DATE±Nd}}` (today ± N days), resolved at substitution time from the run
   date in the daemon's timezone.
3. Scope: string arguments generally (covers `goto` URLs and `fill` values, as promised).
   No recipe-schema change (arguments already accept arbitrary strings).

Open contract details (finalize in Flo's issue): output date format (recommend ISO
`YYYY-MM-DD`); precise `{{DATE_FROM}}`/`{{DATE_TO}}` semantics (recommend: named
day-offsets, or drop them in favor of the `{{DATE±Nd}}` set); timezone source (recommend:
a daemon setting, else local system time).

**B — login-failure lock**

B1 — login steps: single-attempt-with-pause.
- Recipe: a step may carry `login: true` (add to
  `apps/recipes_playwright/recipe-pw-schema.yaml`).
- Runner: a `login` step runs **once** (no 3x retry — `runner.py:67,111-113`) and, on
  failure, **pauses** (task → `waiting`, ntfy deep link, interactive session) instead of
  aborting/retrying. This is a third step mode: today graceful = single-attempt/no-pause,
  non-graceful = 3-attempt/pause.
- When a login step fails, the runner marks its Run row: additive Run column
  `login_failed INTEGER NOT NULL DEFAULT 0` (set to 1).

B2 — consecutive-failure counter + auto-disable.
- On run finalization (the runner's own finalize path knows result + `login_failed`):
  - result `success` → `consecutive_failures = 0`.
  - else if `login_failed = 1` and result in {`failure`, `needs_attention`} →
    `consecutive_failures += 1`; when it reaches N (setting
    `login_fail_lock_threshold`, default **2** — below the broker's 3-strike lockout) →
    set `enabled = 0`, `disabled_reason = 'login_failures'`, and push ntfy (new
    `notify_disabled` in `apps/billcollector/notify.py`, deep link to the task page).
  - `cancelled` (operator-controlled) and non-login failures do **not** increment.
- **Refuse to run:** `Orchestrator.start_run` (`orchestrator.py:286`) re-reads the task
  and refuses (log + return None) when `disabled_reason` is set — the robust guard
  (works even before the APScheduler job is removed). The `enabled=0` task's cron job is
  removed on the next `sync_task`/`resync` (`scheduler.py:101-120`) as cleanup.

B3 — UI "clear" action.
- Task-detail page: a "Clear login lock" action (visible when
  `disabled_reason = 'login_failures'`) that sets `enabled = 1`,
  `disabled_reason = NULL`, `consecutive_failures = 0`, and calls
  `scheduler.sync_task(task_id)` to re-add the cron job. Add in
  `apps/billcollector/ui/task_detail.py` next to the existing "Reset profile" action
  (`ui/task_detail.py:193`).

Open contract details (finalize in Flo's issue): N default + global vs per-task
(recommend global setting, default 2); the exact terminal-state → increment mapping
(recommend: increment on `failure`/`needs_attention` with `login_failed`, reset on
`success`, ignore `cancelled`); whether "clear" also resets the profile (recommend: no —
re-enable only).

**Ordered task list (realization, once Flo's issues land)**

1. **(A)** Extend `process_argument` to embedded `{{...}}` resolution; add the date
   tokens + a timezone source. Tests: unit tests for exact, embedded, offset, and
   timezone substitution.
2. **(B1)** Add `login` to the recipe schema; implement single-attempt-with-pause for
   login steps; set `Run.login_failed`. Tests: a login step failing once → pause (not 3
   attempts); non-login steps unchanged.
3. **(B2)** Additive migration (`Task.consecutive_failures`, `Task.disabled_reason`,
   `Run.login_failed`); finalize counter logic (increment/reset/auto-disable) +
   `login_fail_lock_threshold` + `notify_disabled`; guard `start_run` to refuse
   auto-disabled tasks. Tests: N-1 failures → still runs; Nth → disabled + notified +
   `start_run` refuses; a success resets the counter.
4. **(B3)** UI "Clear login lock" action + scheduler re-sync. Test: clear re-enables,
   resets the counter, re-adds the cron job.
5. **(C)** No new work — finish the daemon deployment (M3 Wave 1 exit pass) to honor
   the "2–3 days" timeline.

**Validation**

- Each task ships with tests per CONTRIBUTING "Proof" (unit/regression).
- Full regression: `apps/.venv/bin/python tests/run_regression.py --ini tests/bc_regression.ini`.
- Manual B (the broker case): a task whose login step fails on 2 consecutive scheduled
  runs auto-disables, pushes ntfy, refuses further runs, and re-enables on the UI clear
  action.
- Manual A: a recipe with `goto("...?from={{DATE-7d}}&to={{TODAY}}")` substitutes the
  correct run-date values.

**Open questions (finalize in Flo's issues; recommendations above)**

- A: date output format; `DATE_FROM`/`DATE_TO` semantics; timezone source.
- B: N default + scope; terminal-state → increment mapping; whether "clear" resets the
  profile.
```

## Validation (after all edits)

- `ls .kilo/plans/ .kilo/plans/completed/` — the two M2 files under `completed/`, the
  concessions file gone, the master/M3/spec files at root, and no plan file name
  containing "flowcool" except the pre-existing `1792189620000-…` one until task 8 runs.
- `grep -rn "1791705823133\|1791829791901" .kilo/plans/` — every occurrence outside
  `completed/` carries the `completed/` prefix; none bare.
- `grep -rn "1792189620000\|1792185181020" .kilo/plans/` — **zero** occurrences
  (concessions file deleted; the dangling reply-plan reference is replaced by the Gitea
  comment).
- `grep -n "Post-Wave 1" .kilo/plans/1790364274061-billcollector-nicegui-daemon-plan.md`
  — the section is present with A/B/C + ordered task list + validation.
- `git status --short` — only `.kilo/plans/` paths changed; no source files.

## Notes

- No commit is part of this task. When the user commits later (dev-commits skill),
  follow D5 — the suggested message wording above.
- Kilo plan references stay out of public sources (sync_github.sh sanitizes the mirror;
  `.kilo/` is not published) — no constraint change.
