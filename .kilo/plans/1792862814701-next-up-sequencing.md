# Next up: sequencing decision (2026-10-24)

Question: start one of the three active plans now, or wait for a PR generated
from one of the open GitHub issues?

**Decision: do not wait for a PR. Start plan 3 (issue #27 commitments) with C2
and C1 now, then C3; then move to plan 2 Stage 1b.**

Superseded in part (2026-10-25): the PRs arrived — flowcool's #30–#34 are
open. The "PR continuation order" section below is the current primary
next-up, interleaved with the remaining Stage 1b work.

## Grounds (verified on dev, 2026-10-24)

- GitHub has **no open PRs** (`s-t-e-f-a-n/BillCollector`, state=open →
  empty). Open issues are #24, #25, #26, #28 (all flowcool). "Waiting for a
  PR" means idling on a deliverable that does not exist yet, on someone else's
  schedule.
- The pending PRs only gate plan 3's **C4** (needs #24/#26 semantics) and
  **C8** (needs #24) — items 4 and 8 in the plan's proposed order. They gate
  nothing that could start now.
- Plan 1 (`1792793307574-recipe-repair-llm-options.md`) is a pre-step options
  analysis with Stage 0 done — a reference document, not an execution target.
- Plan 2's Stage 1 is landed and pushed (doctor subcommand, unit suite,
  buhl/datev pilots green, runs 16/18). **Stage 1b** (remaining 5 services)
  is open and its plan already documents the no-LLM-endpoint fallback
  (canned `--llm-response`, proven in Stage 1).
- Plan 3's C1/C2/C3 have **zero external dependencies** (no portal access, no
  LLM endpoint, no flowcool input). C3 (publish the method contract)
  actively **unblocks flowcool's F08 lane** — doing it now shortens their
  wait, the reverse of blocking on them.
- Plan 3's C7 (protected-login conversion) is explicitly scheduled to bundle
  with the Stage 1b portal-access windows to reuse the sessions.

## Order

0. **Housekeeping first:** commit the pending plan work (untracked
   `1792861675256-issue27-maintainer-commitments.md` + the README line for it)
   via the dev-commits skill — user confirms each suggested commit, push to
   Gitea origin/dev.
1. **C2 (F09):** remove personal example accounts from
   `apps/bc_default.ini` (and `bc_test.ini` if it ships examples); fresh
   import creates no personal tasks; INI import/migration path preserved.
2. **C1 (F04):** `ntfy_topic` default `"billcollector"` → empty (send path
   already no-ops on empty, `notify.py:54-56`); document public ntfy.sh vs.
   the bundled self-hosted compose profile; surface `ui_base_url` in Settings
   with the LAN-reachability explanation.
3. **C3 (F08 contract):** publish the supported method surface (method names,
   argument names/types, supported variables) covering legacy collection
   recipes, `doc/SAFE_LOGIN.md` login recipes, and PR #19 bounded-collection
   actions, without rejecting intentionally supported Playwright calls.
   Posts to issue #27 so flowcool can start F08.
4. **Stage 1b** (plan 2): nuernberger → 1und1 → winsim (cheap wins) →
   freenet_mobilfunk (overlay case) → kabeldeutschland (Option D
   re-authoring, last). Per-service loop per the plan's checklist; fresh
   pause context per iteration. **C7 conversions ride the same portal
   windows.** Start when the user is available for the live portal sessions
   (TOTP/OTP at run time). LLM endpoint is runtime-pluggable; without it the
   canned-response path carries the loop (mechanism validated, judgment is
   manual) — this is the same path Stage 1's green pilots used.
5. **Stays deferred by design (no action now):** C4 (draft once #24/#26
   settle), C5 (F02 design), C6 (F03 design), C8 (after #24 lands).

## Status (2026-10-24)

- Step 0 housekeeping: done (plan files committed and pushed).
- Step 1 C2 (F09): done and pushed (`09fb199` + plan update `5324051`).
- Step 2 C1 (F04): done — code, Settings hints, README section, opt-in test;
  gate green (ruff + pytest 451 passed); committed and pushed per the
  dev-commits cycle.
- Step 3 C3 (F08 contract): done 2026-10-24 — the draft
  `doc/RECIPE_METHODS.md` was verified line-by-line against runner/login/
  collection/recipes/schema sources and the 15 shipped recipes; four
  accuracy fixes applied (Frame/FrameLocator chain types, the
  login-chain locator set, exact-match variable substitution, the
  existing-gates vs. F08-additions split); gate green (ruff + pytest
  451 passed); published as commit `5745e59` and posted to issue #27
  (comment 6388757576) so flowcool can start F08.
- Next: Step 4 Stage 1b — start when the user is available for the live
  portal sessions; C7 conversions ride the same windows.

## PR continuation order (2026-10-25)

Question: in which sequence do we continue the five open community PRs?
(All flowcool, all based on public `main` `b4cf023`, all
`mergeable_state: clean`; none depends on another's code.)

**Decision: #30 → #31 → #33 → #32 → #34, one pr-review chain at a time,
interleaved with the remaining Stage 1b portal sessions.**

### Grounds

- No code dependency between the PRs (same base, disjoint contracts:
  #30 docs D08/#27, #31 onboarding F07/#27, #32 sandbox #28, #33 download
  recovery #24 + F01/#27, #34 date variables #26). Shared-file overlap is
  regional, not hunk-level: `runner.py` (#32 launch flags / #33 startup
  recovery / #34 date expansion), `db.py` (#33 `Download` migration / #34
  `Task.date_window_days`), `config.py` (#32, #33), `README.md` +
  `CHANGELOG.md` (#30–#34), `tests/test_bc_residual_logs.py` (#33, #34).
  Dev has already diverged from `b4cf023`, so every S1 re-runs the
  pre-image check against current dev; the skill's divergence handling
  covers it.
- **#30 + #31 first** — the cheapest full S1–S7 run. The #25 publication
  routine (S7 close comment + related-issue closure + Discussion summary)
  has not yet been exercised in a delivery; running it on a one-line docs
  PR and a one-line fix PR validates the pipeline end-to-end at minimal
  risk before the heavy reviews start.
- **#33 before #32** — the only true downstream unblocks in the batch:
  #33 lands #24 → **C8 (F10)** can be scheduled; #33 + #34 land #24/#26 →
  **C4 (F06)** can be drafted. And #33's S5 is fully local (unit +
  regression + ruff; no Dockerfile/compose/install-script/INI/.env
  changes — the new `download_recovery_timeout_seconds` is a Settings row
  with a default, so record "not deployment-relevant" with that judgment
  in the plan doc) — it cannot stall on an external host.
- **#32 fourth** — the only PR with a hard external gate: S5 fires the
  full deployment-validation block (docker build + canary check + smoke
  run) on a Docker-capable host (the NAS). Schedule its S5 to the NAS
  window. **Swap rule:** if the NAS is free and the user prefers the
  deployment-qualified PR before the large #33 review, swap #32 and #33 —
  no code dependency makes the swap safe.
- **#34 last** — it extends the shared recipe-contract interface (agreed
  in #26, cited in the PR body, so the S1 process check passes) and
  changes cron-TZ semantics (no `TZ` → agreed UTC fallback instead of the
  host timezone). After it lands, `doc/RECIPE_METHODS.md` (C3), the
  doctor-prompt variable vocabulary, and the README each need one
  contract-doc update — bundle them into #34's S6 against the final dev
  tree so the contract docs are revised once, not per earlier PR. The
  kabeldeutschland Option D re-author (the last Stage 1b item) can
  optionally use the date variables once #34 is on dev.

### Per-PR notes (input to each S1)

| PR | Scope | Weight / gate | Watch in S1 |
|---|---|---|---|
| #30 | README cron example (D08) | trivial; docs-only validation | README migration-section pre-image |
| #31 | onboarding.py closure fix + test (F07) | small | `onboarding.py` pre-image (dev's C1/C2 touched other files) |
| #33 | downloads.py rewrite, db/config, recovery in runner + ui/app, `doc/DOWNLOAD_RECOVERY.md`, 373-line crash tests (#24, F01) | large; S5 fully local | unblocks C8; `runner.py`/`db.py`/`config.py` regions; CHANGELOG + README merges |
| #32 | sandbox flags in daemon + batch launchers, `docker/`, `.gitattributes`, 15 files (#28) | large; S5 needs the NAS Docker host | S5 trigger fires (docker/ + runtime config); `BillCollectorServices_pw.py` legacy path; record host + validated tree hash |
| #34 | date variables, `Task.date_window_days`, Run-now pipe, scheduler TZ (#26) | large; contract + TZ behavior change | interface agreed in #26; `test_bc_residual_logs.py` hunks adapt on top of #33 |

### Interleave with Stage 1b

- PR sessions need no portal; Stage 1b iterations need live TOTP/OTP.
  Advance the PR stages in the non-portal sessions.
- Stage 1b stands at 4/7 (buhl, datev, nuernberger, winsim green and
  committed). Next portal session: **1und1** (fixes committed; runs 22–25
  still pause → fresh pause + doctor iteration per plan 2's loop), then
  freenet_mobilfunk, then kabeldeutschland (Option D re-authoring). C7
  conversions ride the same portal windows.
- After #33 lands: C8 can be scheduled. After #33 + #34: C4 can be
  drafted. Neither blocks this PR order.

### Status (2026-10-25)

- PRs #30–#34 open since 2026-10-24; order decided above.
- PR #30 DELIVERED 2026-10-25 (S1–S7 in one chain): hunk applied +
  CHANGELOG entry, Gitea `main` `84a9d8b`, GitHub `main` `41294731df`,
  PR closed without merge; the #25 publication routine ran end-to-end
  (Discussion summary skipped by user — small fix).
- PR #31 DELIVERED 2026-10-25: S1+S2 verdict approve (byte-identical
  pre-images), S4 both files applied + CHANGELOG entry, S5 green (unit 29
  / full 454 / regression PASS / ruff + bandit baseline; deployment skip
  recorded + user-confirmed), S7 — commits `7a0ad6b` + `36a8d31` +
  `5cd1f31`, Gitea `main` = `5cd1f31`, GitHub `main` = `d9362b3`, PR
  closed without merge (comment 6399102074, 14:49:55Z). The Discussion
  summary is pending user creation in the web UI (Discussion write API not
  usable from this environment; exact text recorded in the review doc,
  now in `completed/`).
- PR #33 S1+S2 done 2026-10-25 ("proceed with pr #33" session):
  review plan doc `1792965931629-pr33-download-crash-recovery-review.md`
  written, verdict approve (head `b675ebe` unchanged), 3 diverged files with
  non-overlapping hunks, two nits as S3 decision points, deployment
  validation recorded as not deployment-relevant — Status:
  AWAITING-DECISION. Next: S3 (propose/refuse gate), then S4–S7.
- The 1und1 portal iteration remains independent and can run in a live
  session at any time.

## Explicitly not doing

- No idling on the PRs: since 2026-10-25 they are handled through the
  pr-review skill in the order above, interleaved with Stage 1b rather
  than waiting for either to finish.
- No Option C (in-daemon LLM copilot) — Stage 2, separate plan, per plan 2.

## Validation

Each step validates per its own plan file's acceptance criteria (C1/C2/C3 in
`1792861675256-issue27-maintainer-commitments.md`; Stage 1b in
`1792819039884-recipe-doctor-implementation.md`). Repo gate before each push:
`ruff check apps tests` + full pytest suite; commits via dev-commits with
per-item user confirmation.
