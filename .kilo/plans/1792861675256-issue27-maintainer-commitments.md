# Issue #27 maintainer commitments (product audit triage)

Goal: track the maintainer-side work committed in the triage reply to GitHub
issue #27 ("Product audit", closed 2026-10-24, triage decision in comment
6387035799). The audit issue is closed as a triage issue; each accepted item
tracks here (or in its existing lane) until delivered. flowcool's handed-over
items (F07, D08, fixtures, docs, F01, F08-after-contract) are tracked in
their own PRs, not here.

## Verified context (dev, 2026-10-24)

All P1 findings re-verified against dev. The audit baseline is public main
`42d43378`; dev has since moved (daemon UI, bounded collection PR #19,
phased login PR #22), but every finding below still reproduces or still holds
on dev.

- F02: `docker-compose.yml:64-73` mounts Downloads/db/data/profiles but not
  recipes; the UI editor saves under `/apps/recipes_playwright` (container
  writable layer). Git auto-commit assumes a checkout; the image copies
  `apps/` without `.git`.
- F03: `docker-compose.yml:63` publishes `6080-6095` without a loopback host
  binding; `config.py:56` `vnc_password` defaults to `""`; `display.py`
  runs `x11vnc -localhost -nopw` behind websockify.
- F04: `config.py:54` `ntfy_topic` defaults to `"billcollector"`;
  `notify.py:21` `NTFY_HOST` defaults to `https://ntfy.sh`; `notify.py:54-56`
  already skips the pause push when the topic is empty (the gap is the
  pre-filled default, not the send path). `config.py:53` `ui_base_url`
  defaults to loopback `http://127.0.0.1:8000`. The self-hosted ntfy compose
  profile (`docker-compose.yml:84-99`) already exists.
- F05: phased-login contract delivered on dev (`doc/SAFE_LOGIN.md`, commit
  `9d8ebcf`); none of the 7 provider recipes in `apps/recipes_playwright/`
  uses the `login` method; dashboard "available" label does not distinguish
  protected vs. legacy login.
- F06: `runner.py:133-148` `run_result` — aborted -> `failure`; completed
  with no downloads -> `failure` (explicit legacy contract).
- F08: `recipes.py:28` `validate_recipe` — schema allows any method string;
  login-specific validation only.
- F09: `apps/bc_default.ini` ships 7 providers / 11 tasks (winsim x5 users +
  kabeldeutschland, datev, buhl, nuernberger, 1und1, freenet_mobilfunk).
- F10: consumer extension slot empty; `track_download` calls consumers
  before the Download row insert, catches failures, continues.
- F01: `downloads.py` unchanged since the audit baseline; `track_download`
  saves `suggested_filename` before the hash check.

## Commitments (what I keep)

### C1 — F04: notification opt-in default (P1, small)

- Change the `ntfy_topic` default from `"billcollector"` to empty: a fresh
  installation sends nothing until the operator sets a topic in Settings.
  The send path already no-ops on empty topic (`notify.py:54-56`), so this is
  a default + docs change, not a new code path.
- Document public ntfy.sh vs. the bundled self-hosted profile (the compose
  header already covers the two-line switch).
- Deep-link base URL: `ui_base_url` must be settable to a reachable
  LAN-absolute address for real deployments; keep loopback as the safe
  default and surface it in Settings with an explanation.
- Acceptance (from the issue): no notification leaves a fresh installation
  before an explicit choice; installation-specific destination; minimal
  payload; a user-triggered test notification is a follow-up item (Settings
  "Send test push").
- Status: not started.

### C2 — F09: shipped default INI (P1, small)

- Remove the personal example accounts from `apps/bc_default.ini` (and
  `bc_test.ini` if it ships examples). Fresh import creates no personal
  tasks; keep the INI import/migration path working for existing users.
- Acceptance (from the issue): fresh installation starts with no personal
  example tasks; demos explicit and synthetic; deliberate INI migration for
  existing users preserved; clear first-account action and missing-
  configuration visibility before offering scheduled execution (the
  first-account wizard itself is U01, stage 2).
- Status: not started.

### C3 — F08: method contract (P1, unblocks flowcool)

- Publish the supported method surface: method names, argument names/types,
  and the supported variables, as part of the recipe-repair work (see
  `.kilo/plans/1792819039884-recipe-doctor-implementation.md` for the
  surrounding repair/doctor context).
- The contract must cover the valid legacy collection recipes, the login
  recipes (`doc/SAFE_LOGIN.md`), and the bounded collection actions (PR #19)
  without rejecting intentionally supported Playwright calls.
- flowcool implements the `validate_recipe` hardening + tests (F08) against
  the published contract.
- Acceptance (from the issue): reject unknown methods, invalid argument
  names/types and unsupported variables before vault/browser access; report
  the service and step; compatibility checks include valid legacy and new
  collection/login recipes.
- Status: not started.

### C4 — F06: result semantics contract (P1, contract-first)

- Draft the result contract: distinguish proved empty / duplicates-only /
  new documents / partial collection / failed collection, so a healthy empty
  collection is not a `failure` and an arbitrary no-download run is not
  automatically healthy.
- Coordinate with #24 (crash recovery / publication) and #26 (date variables
  / collection window) so one coherent semantics covers the collection
  window and the publication semantics; no implementation before the
  contract is agreed on the issue.
- Then implement: UI, notifications and CLI/exit semantics updated
  consistently, with compatibility tests.
- Status: not started; waits for the #24/#26 lanes to settle the shared
  semantics.

### C5 — F02: recipe storage design (P1, design first)

- Decide: bind-mounted recipes volume (packaged updates vs. local edits),
  export/restore, durable recipe history, and the git auto-commit story
  (hide or explain it when no usable checkout exists — the image has no
  `.git`).
- Acceptance (from the issue): a synthetic UI edit survives container
  recreation with identical content; packaged-update interaction defined;
  export/restore or durable history provided.
- Blocks U09 (guided repair with revert) — the audit explicitly says resolve
  F02 first.
- Status: design not started.

### C6 — F03: noVNC access path (P1, design first)

- Specify one supported routing/authentication design: published port
  binding (loopback-only host bind + reverse proxy on the NAS) vs.
  authentication through the UI session; document reverse-proxy/TLS
  requirements.
- Acceptance (from the issue): an unauthenticated client cannot view or
  control a live browser through any published path; authenticated
  intervention remains usable.
- Changes the reference Compose deployment (`docker-compose.yml:63`); needs
  the deployment-process validation (deploy skill) before NAS rollout.
- Status: design not started.

### C7 — F05: protected-login conversion (P1, slow)

- UI: distinguish protected vs. legacy login recipes on the dashboard (the
  "available" label can be mistaken for a verified login/session state).
- Conversions: convert each of the 7 provider recipes to the phased `login`
  method only with a valid final-session proof and appropriate MFA phases —
  real-provider validation with my accounts (flowcool may prepare structure
  and fixtures, not claim real-provider validation). Preserve existing
  session, optional-TOTP and timeout behavior; synthetic tests for no-
  resubmit and persistent-budget behavior.
- Overlaps the recipe-doctor stage 1b pilot work (same recipes, same portal
  access windows) — schedule the conversions together with the doctor runs
  to reuse the access sessions.
- Status: not started; needs portal access windows per provider.

### C8 — F10: archive confirmation (after #24)

- Complete #24 first (crash recovery, publication, consumer delivery —
  flowcool's implementation lane). Then expose downloaded / pending delivery
  / delivered / failed delivery states, using the agreed stable idempotency
  key and safe retries; a plain consume-folder integration states what it can
  prove when no ingestion callback exists. No competing implementation.
- Status: waiting on #24.

## Handed over to flowcool (tracked in their PRs, not here)

- F07 onboarding toggle closure + multi-control acceptance test.
- D08 README cron example fix (`0 6 1 1,15 * *` at `README.md:378`).
- Acceptance fixtures: synthetic multi-account setup, persistence/restart
  checks.
- Docs: D02 tested quick start, D05 troubleshooting, D07 recipe author
  reference.
- F01 collision-safe storage, together with the #24 implementation.
- F08 validation + tests, once C3 publishes the method contract.

## Related lanes

- #24 crash recovery (flowcool implementation PR pending) — F01 + F10 ride
  on it.
- #26 date variables / collection window (flowcool PR pending) — overlaps
  C4.
- #28 Chromium sandbox (flowcool, contract accepted 2026-10-24, upstream PR
  pending).
- #25 publication routine (tracking; decision 2026-10-24: stays open until
  the next public delivery runs the S7 routine end-to-end, then close with a
  comment pointing at the demonstrated delivery and its Discussion).

## Proposed order

1. C2 (F09) — small, independent, shipped-default fix.
2. C1 (F04) — small, unsafe-default fix.
3. C3 (method contract) — unblocks flowcool's F08 work.
4. C4 (F06 contract) — needs the #24/#26 context; draft once they settle.
5. C5 (F02 design) — unblocks U09.
6. C6 (F03 design) — security; NAS deployment impact.
7. C7 (F05) — slow; bundle with doctor stage 1b portal windows.
8. C8 (F10) — after #24 lands.

After P1: my top stage-2 picks are U04 (mobile navigation) and U05
(downloads as document access). Remaining backlog accepted in triage:
U01-U03, U06-U11, D01-D07, D09, O02-O08 (each spins out as its own issue
when picked up). O01 stays deferred per #21.

## Status

- Plan created 2026-10-24; triage decision posted on issue #27
  (comment 6387035799); nothing implemented yet.
