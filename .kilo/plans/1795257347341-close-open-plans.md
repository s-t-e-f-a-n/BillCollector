# Closing Drive: close all four active plans

> Sequencing decision (user, 2026-11-21): **UI first, then portal batch.**
> Phase 1–3 close the two UI plans (dark theme + navigation N16) with zero
> portal access; Phase 4–5 close the doctor + issue-27 plans in batched
> provider access windows. Each phase ends with an explicit archive/housekeeping
> step per `.kilo/plans/README.md` (move to `completed/`, update the README
> table and cross-references, doc-only commit + push).

## Starting state (verified 2026-11-21)

- On `dev`, clean tree; local == `origin/dev` @ `84171e5` (the N16 row-click
  fix `0257613` + test `035f59a` + doc `84171e5` are pushed).
- Full-suite baseline: **880 passed / 11 skipped** (2026-11-19, re-green after
  the row-click fix).
- `theme.py` does not exist yet; `task_list.py` / `recipe_list.py` exist
  (navigation pass landed).
- None of the 7 provider recipes uses the `login` method yet (C7 precondition
  still true).
- Remaining open work per plan:
  - `1794863968112` (UI navigation): only **N16 browser-side verification** —
    row clicks on `/tasks` + dashboard (post-fix), `/recipes` index details
    (evidence badges, overlay badge, no-recipe-file row, polling), settings
    all-or-nothing walk, ntfy push deep link, phone-on-LAN smoke.
  - `1794866943286` (UI dark theme): **entire implementation D1–D7** (fully
    planned; prerequisite — the navigation pass — is implemented and pushed).
  - `1792819039884` (recipe doctor): 4/7 green (buhl, datev, nuernberger,
    winsim). Left: **1und1** (fix `c29d978` committed but runs 22–25 still
    paused — unverified), **freenet_mobilfunk** (not started, overlay case),
    **kabeldeutschland** (not started, Option D re-authoring).
  - `1792861675256` (issue #27): only **C7** left — dashboard UI label
    distinguishing protected vs. legacy login + converting all 7 provider
    recipes to the phased `login` method with real-provider validation.
    Locked in that plan: schedule the conversions with the doctor runs to
    reuse access sessions.

## Phase 1 — Dark-theme implementation (plan `1794866943286`, D1–D6)

Execute the existing plan file's tasks in order, no interleaving:

1. **D1** — new `apps/billcollector/ui/theme.py`: token constants,
   `apply_theme()` (`ui.dark_mode().enable()` + `ui.colors(...)` + one
   `ui.add_head_html` block), `pill`/`card`/`kpi_card` helpers.
2. **D2** — chrome reskin `layout.py` (drawer, header, version chip,
   "Daemon active" pill; all `.mark()` ids kept).
3. **D3** — dashboard KPI strip + the new `next_run_countdown(scheduler, db)`
   helper (raw datetimes; the display-formatted `next_run` is not reusable).
4. **D4** — dark-readability fixes across all pages per the audit list
   (grey-text, fixed light surfaces, failure panel, session card/links,
   error labels), `login.py` restyle, CodeMirror `oneDark`; then re-grep
   `grey-|bg-white|text-black|bg-black|slate-100|slate-50|red-50|amber-100|
   blue-200|blue-700` under `apps/billcollector/ui/` — every remaining hit
   intentional.
5. **D5** — tests: extend `tests/test_bc_ui_dashboard.py` with KPI card
   values (enabled/disabled mix, 30-day download window, next-run countdown
   + `—` case). All existing markers preserved → current suites pass
   unchanged. Targeted UI suites first, then full suite (baseline
   **880/11**), `ruff check` clean.
6. **D6** — CHANGELOG entry (dark UI: tokens, chrome reskin, version chip,
   daemon pill, KPI strip, dark editor, dark login). No `.kilo/plans` paths
   or plan IDs in source or public docs.

Commit via the dev-commits skill (user confirms each item), push `origin/dev`.

## Phase 2 — Deploy to NAS dev deployment + ONE combined browser walk

1. User updates the NAS dev deployment to the dark-theme dev tip (the
   deployment must run the new tip before the walk — a stale image gives
   false N16 results).
2. **One combined walk** covering both verification lists (the skin does not
   affect the functional N16 items, so N16 is verified on the dark skin):
   - **N16 remainder** (`1794863968112`): row click on `/tasks` and the
     dashboard (the row-click fix), `/recipes` index details (verified/
     failing/unverified evidence badges with dates + `/runs/<id>` links,
     overlay badge, no-recipe-file row, ~2 s polling), settings all-or-nothing
     walk (break one field + change a valid one → nothing written, notify
     names the key; fix → all written; git switch via the same Save; password
     card standalone; Vault effective-env hints), ntfy push deep link (a
     manual pause fires the push — no portal failure needed), phone-on-LAN
     smoke (icon buttons tappable, fonts/icons offline).
   - **D7** (`1794866943286`): fresh DB `/login` → `/onboarding` → dashboard;
     every page with dark chrome + drawer highlighting (incl. `/tasks/<id>`,
     `/recipes/<service>`); KPI countdown ticking; hover tooltips (version
     chip, daemon pill, KPI cards); `/tasks` + `/recipes` rows and links;
     recipe editor (CodeMirror oneDark); session page (noVNC iframe
     unaffected); `/downloads`, `/settings`; log pane / step strip /
     screenshot strip readability; Quasar surfaces (q-select, q-dialog,
     q-menu) dark-adapted — fix stragglers with D4-style classes;
     phone-on-LAN smoke.
3. Defect found → fix on `dev` (dev-commits cycle), full suite, redeploy,
   re-walk the affected area only.

## Phase 3 — Close the two UI plans

1. Update both plan files' Status sections (nav plan: "N16 complete, date,
   verified on the dark-skin dev deployment"; dark plan: "D1–D7 done, date").
2. Move both files to `.kilo/plans/completed/`; update
   `.kilo/plans/README.md` (drop both active rows) and cross-references
   (the nav plan's reference to the dark-theme plan gains the `completed/`
   prefix).
3. Doc-only commit + push.
4. **Optional user gate (deploy skill)**: release cycle for the UI work
   (promote `dev` → Gitea `main`, GitHub mirror, optional tag v0.7, optional
   NAS production deploy). The user decides; the drive continues either way.

## Phase 4 — Portal batch: doctor remainder + C7 (plans `1792819039884` +
`1792861675256`)

Preconditions per session: local portal-run setup (display shim for the WSL2
X-socket quirk), real provider accounts, LLM endpoint if available (without
it the `--prompt-file` / `--llm-response` canned path validates the mechanism,
not the judgment). First action of the batch: re-verify the doctor loop's
assumptions against the current tree (the engine moved on main since
2026-10-25 — C4/C8 result semantics, PR #57 incremental keys, PR #58 bounded
ZIP unpack; re-check the doctor CLI contract, pause-context shape, and
`save_recipe` gate).

Per-provider access window = doctor iteration (if the service still needs
one) **+** the C7 protected-login conversion in the same live session (the
issue-27 plan locks this reuse). Order — cheap wins first:

1. **1und1** — re-capture a fresh pause (fix `c29d978` was never re-run;
   runs 22–25 stale) → doctor iteration(s) → green (PDF in Downloads).
   Then convert the recipe to the phased `login` method (`doc/SAFE_LOGIN.md`)
   with a valid final-session proof; preserve session/optional-TOTP/timeout
   behavior; real-provider validation; synthetic tests for no-resubmit and
   persistent-budget behavior.
2. **freenet_mobilfunk** — overlay/consent case: re-enable the commented-out
   consent step as `graceful: true`, iterate; noVNC inspection fallback for
   the iframe banner; watch step 4's frozen Keycloak `state` (re-record the
   login URL if the session is rejected). Then the C7 conversion.
3. **kabeldeutschland** — Option D re-authoring against
   vodafone.de/meinvodafone (codegen helper → YAML translation → validation
   gate → Run-now validation; most labor-intensive service). The doctor is
   expected to answer `fix_type: none` on the old recipe — do not force a
   step edit. Then the C7 conversion.
4. **buhl, datev, nuernberger, winsim** — already green (doctor side done);
   each still needs its C7 conversion (real-provider final-session proof +
   a post-conversion successful run).

Per-iteration loop (doctor plan, unchanged): fresh pause →
`billcollector doctor <service> --from-run <id>` → reviewed diff →
`--apply` → re-run → repeat until success. Never reuse the 2026-10-24 triage
pause contexts as doctor input.

Definition of done (per service): run completes with the PDF downloaded AND
the recipe uses the phased `login` method, validated by a real-provider run
and the synthetic tests, recipe change landed through the validation gate
with the reviewed diff.

Small dev-side C7 piece (no portal needed, can be folded into Phase 1's
commits or done at the batch start): the dashboard "available" label
distinguishes protected (`login` method) vs. legacy login recipes.

## Phase 5 — Close the doctor + issue-27 plans

1. All 7 services green + converted:
   - doctor plan wrap-up: commit any remaining recipe fixes (dev-commits),
     update Status, move to `completed/`.
   - issue-27 plan: update C7 Status (date, commits), Status → all
     commitments delivered, move to `completed/`.
2. Update `.kilo/plans/README.md` (drop both active rows, fix cross-
   references), doc-only commit + push.
3. **Optional user gate (deploy skill)**: release cycle carrying the recipe
   + login-method changes to `main` + mirror.

## Risks & mitigations

- **Stale dev deployment** → false N16 results: verify the deployment runs
  the dev tip (commit check) before the walk.
- **Portal drift between windows** → per-iteration re-capture; the triage
  captures are forensic reference only.
- **C7 conversion risk** → the recipe file is only written through
  `validate_recipe`/`save_recipe`; a failed conversion leaves the working
  legacy recipe in place. Convert one provider per window and re-run before
  the next.
- **Combined-walk assumption** (skin does not change N16 functionality):
  if the reskin regresses a functional N16 item, fix it in Phase 2 before
  closing either plan.
- **No LLM endpoint** → canned-reply path keeps the doctor loop testable.
- **kabeldeutschland** is the long pole of the batch; if its re-authoring
  overruns, the other six can close the plans' per-service checklists first —
  the plans close only when all seven are green (doctor plan's own rule).

## Out of scope (stay separate plans / later)

- Stage 2 (Option C in-daemon copilot) — the doctor plan keeps it separate.
- Dark-mode toggle, vendored web fonts, Material Symbols — dark plan's locked
  out-of-scope.
- Release tagging/notes content decisions — deploy skill gates, not this plan.
