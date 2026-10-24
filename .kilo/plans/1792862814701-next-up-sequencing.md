# Next up: sequencing decision (2026-10-24)

Question: start one of the three active plans now, or wait for a PR generated
from one of the open GitHub issues?

**Decision: do not wait for a PR. Start plan 3 (issue #27 commitments) with C2
and C1 now, then C3; then move to plan 2 Stage 1b.**

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
- Step 3 C3 (F08 contract): next.

## Explicitly not doing

- No blocking wait for flowcool's PRs; when they arrive, they are handled
  through the pr-review skill on their own schedule (independent of this
  order).
- No Option C (in-daemon LLM copilot) — Stage 2, separate plan, per plan 2.

## Validation

Each step validates per its own plan file's acceptance criteria (C1/C2/C3 in
`1792861675256-issue27-maintainer-commitments.md`; Stage 1b in
`1792819039884-recipe-doctor-implementation.md`). Repo gate before each push:
`ruff check apps tests` + full pytest suite; commits via dev-commits with
per-item user confirmation.
