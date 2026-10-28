# PR #39 review: input-triggered protected login submissions (issue #36)

> Status: DELIVERED (2026-10-28) — S7 complete: Gitea `main` `b693517`
> (ff-only from `2a6e462`), GitHub `main` `ad18f7a`; PR #39 closed without
> merge (comment 6481319827, 2026-10-28T21:38:49Z), issue #36 closed as
> completed (comment 6481326228, 2026-10-28T21:39:09Z); per-public-update
> Discussion summary omitted at user request (2026-10-28).

## PR metadata

- Author: flowcool; head `0053ec605374849da495d862b78391811e59c899` (branch
  `feature/upstream-input-submit-20261026` in flowcool's fork).
  `git ls-remote github refs/pull/39/head` = local `refs/pr/39` at review
  time (verified 2026-10-28).
- Base: the PR body states the branch "starts directly from public `main` at
  `d9362b3b68d7f9aa54b070c5f8a86708102e1cff`". `d9362b3` is an ancestor of the
  head (verified `git merge-base --is-ancestor`), so the true change set is
  exactly `git diff d9362b3...refs/pr/39`.
- Issue ref: #36 (open) — "Agree protected login submission triggered by
  field input", a request-for-agreement on the recipe interface (follow-up to
  #20's delivered phased-login contract). Source implementation:
  flowcool/BillCollector#62.
- Local state at review: `dev` = `origin/dev` = `5bf7ca2`; Gitea `main` =
  `origin/main` = `2a6e462`; `github/main` = `c2fb7f8`. Working tree clean.
- Cross-PR: open PRs are #39, #40 (calendars), #41 (notice/PDF revisions),
  #44 (C3 recipe method-chain validation). The #34 sequencing chain was
  `#34 → #35 → #42 → #39 → #40` (#41 held on the #38 archive decision);
  #34/#35/#42 are now delivered, so #39 is the head of the remaining chain.
  #44 is newer and independent (no ordering dependency on #39; both touch
  recipe validation but in disjoint regions — #44 is C3 runtime method-chain
  validation, #39 is the login submit terminal).

## Merge-base / base analysis

- `git merge-base refs/pr/39 github/main` = `36a8d31` ("test: onboarding —
  multi-control switch independence acceptance (PR #31, issue #27 F07)") —
  older than the PR's true base; the mirror rewrites hashes on each sync, so
  the raw merge base is not the content base (same situation as #34).
- Diffing against the raw merge base `36a8d31...refs/pr/39` shows 91 files:
  the 3 real files **plus** 87 deletions of maintainer-private paths
  (`.kilo/`, `.private/`, `openwiki/`, `AGENTS.md`, `.vscode/`,
  `.github/workflows/`) and a spurious `CHANGELOG.md` `+5` (the PR #31
  onboarding entry). Both the private deletions and the CHANGELOG delta are
  fork-behind-base comparison artifacts, **not** part of the PR's
  contribution.
- Against the true base `d9362b3...refs/pr/39` the change set is exactly **3
  files, 1 commit**:
  - `M apps/billcollector/login.py` (+1/-1)
  - `M doc/SAFE_LOGIN.md` (+32/-2)
  - `M tests/test_bc_login.py` (+159/-2)
  - commit `0053ec6` "feat: allow input-triggered protected login
    submissions"
- No private paths, no comparison artifacts, no orphaned public-history
  commits. The PR author never touched `CHANGELOG.md`.

## Verdict

**Approve.** The #36 input-triggered-login extension is implemented exactly as
the issue proposed: a single validation change that admits `fill` as a
terminal login-phase `submit` action, riding the pre-existing durable-attempt /
session-proof / settle execution path in `runner._execute_login` (which is
unchanged by this PR). The execution invariants are verified to hold
(reserve-before-dispatch, fill-once with no replay on resume, final
session-proof-gated success, durable interruption), and 4 new tests plus 1
parametrization prove them directly against `runner._execute_login`. No
database, control-protocol, or exit-code change. Two maintainer-side items ride
the delivery (neither changes the PR's code logic): (1) the PR ships no
CHANGELOG entry, so the maintainer authors the `### Added` line; (2) the
recipe-contract sign-off on issue #36 is this review's decision (S3).

## Verified facts

- Issue #36 contract (the proposed bounded extension): permit a locator chain
  ending in `fill` as the explicit `submit` action of a login phase; keep
  preparation limited to non-submitting fills; the existing transaction
  reserves its durable attempt before executing the declared submit action
  (including direct entry at a later phase); resolve the credential/code only
  when that action runs; no automatic extra click, OTP replay, or retry; the
  same final authenticated marker proves success; preserve current failure
  limits, settlement, explicit clear, phase skipping, timeouts and
  optional-TOTP fallback; no database, control-protocol, or exit-code change.
  The PR body's "Coordination and ownership" and `SAFE_LOGIN.md` both frame
  this as a local candidate pending maintainer agreement.
- `apps/billcollector/login.py:81` (the only code change):
  `_action(phase.get("submit"), {"click", "press"})` →
  `_action(phase.get("submit"), {"click", "press", "fill"})`. The `_action`
  helper (`login.py:30-42`) enforces Enter-arguments only for a `press`
  terminal, so a `fill` terminal is a normal locator+fill chain. Correct and
  minimal.
- `apps/billcollector/runner.py` `_execute_login` (`runner.py:799-867`,
  **unchanged by the PR**) already supplies every guarantee the contract
  needs:
  - Reserve before dispatch: `db.reserve_login_attempt(...)` at `runner.py:834-842`
    runs **before** `_execute_step(ctx, phase["submit"], ...)` at `:843`.
  - Fill once / no replay: dispatch uses `single_attempt=True` (`:843`); the
    post-failure resume loop (`:858-867`) only re-checks `proven(...)` and never
    re-dispatches the submit action.
  - Final session-proof gates success: the final phase requires
    `proven(options["timeout_ms"])` (`:845-846`); `proven()` requires the
    success locator to be visible **and** `db.login_succeeded` (`:804-811`).
  - Durable interruption: `RunInterrupted` is re-raised (`:849-850`) so the
    reservation persists; `settle_attempt` settles once on the way out
    (`:856-857`).
  - So the 1-line validation change unlocks an already-correct execution
    path rather than adding new logic.
- Security: admitting `fill` to the accepted submit terminals broadens the
  accepted recipe surface but is bounded. A non-submitting fill placed in
  `submit` merely consumes one durable attempt and pauses ("Login not proven.
  Complete it manually…"); the final session proof still gates success, so
  there is no bypass — the worst case is a consumed attempt plus a pause prompt.
- Pre-image check against `dev` (true base `d9362b3`): all three files are
  **byte-identical to the PR base** (`git diff --quiet dev d9362b3 -- <f>`
  clean for `login.py`, `SAFE_LOGIN.md`, `test_bc_login.py`); the `:81` hunk
  context is present in `dev`. Clean apply, no manual merge, no dev-side
  additions to preserve.
- Tests (`tests/test_bc_login.py`): 4 new test functions + 1 new
  parametrization on an existing test, all driving `runner._execute_login`
  directly:
  - `test_input_triggered_login_submits_once_and_supports_direct_otp`
    (`start_at_otp` ×2): a two-phase login where each credential fill submits
    the phase. A second `Database` connection proves the reservation was
    committed (login_failures=1, login_pending_run_id=run) **before** the
    portal's `input` handler observes the submission; one submission (no
    replay), fresh OTP (`get_totp` called once), settles to
    login_failures=0 / pending=None.
  - `test_input_triggered_login_existing_session_skips_all_input`: an already
    visible success locator skips all input (no submissions, no OTP, no fill).
  - `test_input_triggered_login_resume_waits_for_final_proof_without_replay`
    (rejected / not-finalized): resume waits for the final authenticated marker
    without re-filling or resetting the budget before proof.
  - `test_input_triggered_login_interruption_is_durable_before_and_after_fill`
    (before / after fill): the reservation is durable across the interrupt
    (`login_pending_run_id == run` during `_execute_step`), and monitor
    recovery finalizes the run to locked + unclaimable.
  - These map 1:1 to the issue #36 acceptance list.
- `doc/SAFE_LOGIN.md`: states the extension is a local candidate for #36 with
  maintainer agreement pending; updates the submit-chain rule to include a
  terminal `fill`; adds the input-triggered OTP YAML example and four
  test-evidence rows. Transparent and accurate.
- No secrets in the PR diff: every credential/test value is synthetic
  (`synthetic-password`, `123456`, `stale-code`, `synthetic` vault item,
  `http://127.0.0.1:1`). No new network exposure.
- PR process check (CONTRIBUTING.md): issue #36 referenced; intended behaviour
  + verification commands + expected results in the body (`pytest
  tests/test_bc_login.py -q` → 62 passed; full suite 461 passed / 3 skipped /
  53 subtests **claimed reused** from the identical-tree commit
  `625a6b677f4a1870a28d512644934dd1f99e37ea` — re-run on the exact dev tree in
  S5); AI assistance disclosed (Codex); no secrets; no new network exposure;
  the one shared-interface change (the login recipe-contract extension) was
  requested in #36 before code.
- The PR ships **no** CHANGELOG entry: the `CHANGELOG.md` delta seen in the
  raw-merge-base diff is the PR #31 onboarding entry (already present in dev at
  `CHANGELOG.md:268`), i.e. fork-behind-base noise. The maintainer authors the
  #39 entry.

## Code review findings

- `apps/billcollector/login.py`: the single change admits `fill` as a terminal
  submit action. No other validation path is touched; `press` still requires
  Enter; `phases`/`steps`/`submit` exclusivity and the final-phase success rule
  are unchanged.
- `apps/billcollector/runner.py` (unchanged): see Verified facts — the
  reserve-before / single-attempt / proof-gated / durable-interruption logic is
  pre-existing and action-agnostic, which is why the validation unlock is
  sufficient.
- `tests/test_bc_login.py`: high-quality, isolated (synthetic page + second
  SQLite connection), directly exercising the real `_execute_login` path;
  covers the direct-OTP, existing-session, resume-no-replay, and
  before/after-fill interruption cases. No secrets, no real provider contact.
- `doc/SAFE_LOGIN.md`: contract doc updated consistently with the code and
  explicitly flagged as a pending-agreement candidate.

## Risks

- Low. Minimal diff, pre-existing and already-tested execution path, no schema /
  control-protocol / exit-code change.
- The only behavioural broadening is the accepted submit-terminal set (adds
  `fill`). A misconfigured non-submitting fill in `submit` costs one durable
  attempt and pauses — no bypass (final session proof still gates success).
- The full-suite result in the PR body is a reuse of a prior identical-tree run
  (not a fresh run on this head); S5 re-runs the unit + full + regression suite
  on the exact integrated dev tree before any commit/promotion.
- If the author pushes a new head, S1 must re-run on the new head (failure
  mode); the current head `0053ec6` is the reviewed one.

## Integration plan (S4, Gitea dev)

| File | Action | Note |
|---|---|---|
| `apps/billcollector/login.py` | apply PR head | clean apply (dev == base `d9362b3`); the 1-line submit-terminal change |
| `tests/test_bc_login.py` | apply PR head | clean apply; 4 new tests + 1 parametrization |
| `doc/SAFE_LOGIN.md` | apply PR head | clean apply; extension + example + test-evidence rows |
| `CHANGELOG.md` | manual (maintainer-authored) | the PR ships no entry; author a `### Added` line for input-triggered login submissions (issue #36) at the top of the `[Unreleased]` Added list (draft below) |

Proposed CHANGELOG entry (maintainer-authored, sanitized; confirm at S3):

```text
- Input-triggered protected login submissions (issue #36): a login phase
  `submit` chain may now end with `fill`, for portals that submit when a
  password or OTP field is filled. The durable attempt is reserved before that
  terminal fill, the fill runs once (resume only re-verifies), and the final
  authenticated marker still proves success. No database, control-protocol, or
  exit-code change.
```

No other maintainer-side code/doc changes are needed — `SAFE_LOGIN.md` already
carries the contract text and the PR's code is applied as-is.

## Validation plan (S5)

Code checks — from the repo root with `apps/.venv/bin/python` on the exact
integrated dev tree:

- PR unit suite: `apps/.venv/bin/python -m pytest tests/test_bc_login.py -q`
  → expected **62 passed** (the PR's claimed count; re-run on the integrated
  dev tree).
- Full pytest: `apps/.venv/bin/python -m pytest tests/ -q` → all pass (dev
  baseline + the 4 new tests + the 1 new parametrization adds cases;
  environment skips allowed).
- Regression: `apps/.venv/bin/python tests/run_regression.py --ini
  tests/bc_regression.ini` → exit 0, 7 scenarios / 8 PDFs, `VERDICT: PASS`
  (exit 3 → a real run holds the lock, stop it first).
- `ruff check apps tests` → nothing new beyond the known baseline.
- bandit on the changed Python files (`apps/billcollector/login.py`,
  `tests/test_bc_login.py`) → nothing new beyond the known baseline (the new
  test-code LOW idioms, synthetic data).

Deployment-process validation — **not deployment-relevant** (recorded skip, not
silent): the PR changes no `Dockerfile`, `.dockerignore`, `BillCollector.sh`,
`install_docker-image.sh`, `deploy_remote.sh`, and no app runtime
configuration (INI keys / `.env` handling). Only a Python validation module
(`login.py`), a contract doc (`SAFE_LOGIN.md`), and tests. The S5 code-check
block above is the only validation required; **no NAS deployment block**, so
S7 does not require the deployment-validation prerequisite.

## Deployment validation

Not triggered — see the Deployment-process validation note in the Validation
plan. No host, build, canary, or smoke results to record.

## Out of scope

- Monthly notice navigation and Paperless delivery — explicitly excluded in
  issue #36 and the PR body.
- Real-provider validation — none is claimed; the issue's Bourse Direct
  observations are source-based, and the PR uses isolated synthetic fixtures
  only.
- The PR #40 / #41 / #44 deliveries — separate chains.
- A deploy of this tree to the NAS `main` — a separate user request.

## Open questions

- None. (The #36 recipe-contract sign-off was given at the S3 gate
  2026-10-28; the CHANGELOG subsection was confirmed as `### Added`,
  newest-first.)

## Execution log

- 2026-10-28 S1: review complete (findings above). Head `0053ec6` fetched
  and verified stable; true base `d9362b3` (PR starts from public `main` at
  that hash); merge base `36a8d31` classified as mirror-hash artifact; the
  raw-merge-base 91-file diff decomposed into the 3 real files + 88
  fork-behind-base comparison artifacts; pre-image checks clean on all three
  files.
- 2026-10-28 S2: plan doc written, verdict **approve** (maintainer-side
  change: authored CHANGELOG `### Added` entry only). Status:
  AWAITING-DECISION.
- 2026-10-28 S3: gate passed — proposal confirmed **as-is**: apply the 3 PR
  files from head `0053ec6` (`login.py` +1/−1, `SAFE_LOGIN.md` +32/−2,
  `tests/test_bc_login.py` +159/−2) as-is, no files skipped, one manual
  resolution (maintainer-authored CHANGELOG `### Added` entry at the top of
  the Unreleased Added list, newest-first, same subsection as the #20
  phased-login entry), no other maintainer-side changes. S7 commit split:
  feat commit (`login.py` + `SAFE_LOGIN.md`) + test commit
  (`tests/test_bc_login.py`) + doc commit (CHANGELOG). Head re-verified
  unchanged (`git ls-remote github refs/pull/39/head` == local `refs/pr/39`
  == `0053ec6`); pre-image re-checks clean on dev `c2bd066`. Status:
  INTEGRATING.
- 2026-10-28 S4: integration applied. Preflight green on dev `c2bd066`:
  clean tree; remote head == local `refs/pr/39` == `0053ec6` (unchanged
  since S1); pre-image re-checks clean (all three files byte-identical to
  PR base `d9362b3`). Applied from PR head: `apps/billcollector/login.py`
  (+1/−1), `doc/SAFE_LOGIN.md` (+32/−2), `tests/test_bc_login.py`
  (+159/−2) — all three verified byte-identical to head (`git diff
  refs/pr/39 -- <files>` empty). Maintainer-side: CHANGELOG `### Added`
  entry inserted at the top of the Unreleased Added list (confirmed draft,
  sanitized). Working tree left dirty (uncommitted) for S5 to validate the
  exact content. Status: INTEGRATING.
- 2026-10-28 S5: code checks all green on the exact dirty dev tree (S4
  applied, pre-commit). PR unit suite: `pytest tests/test_bc_login.py -q` →
  **62 passed in 182.84 s** (the PR's claimed count, re-run on the
  integrated dev tree). Full suite: `pytest tests/ -q` → **600 passed,
  10 skipped, 53 subtests passed in 433.81 s** (dev baseline 592 + the 8 new
  cases: the 4 new test functions are parametrized 2/1/2/2 plus the 1 new
  parametrization on an existing test). Full regression:
  `run_regression.py --ini tests/bc_regression.ini` → **exit 0, VERDICT:
  PASS** (7 scenarios / 8 PDFs, downloads 8/8; the designed failing pairs
  return the expected `BillCollector exit semantics: 1`). Ruff (repo
  `ruff.toml`) on the 2 changed Python files: **All checks passed** on both
  the working tree and the HEAD-dev baseline — nothing new. Bandit on the
  same files: working tree 165 Low / 0 Med / 0 High vs. baseline 143 Low /
  0 / 0 — the delta is exactly +22 `B101 assert_used` in the new test code
  (synthetic data, test-only idioms); the pre-existing `B603`/`B404` legacy
  findings are unchanged. Deployment validation: recorded skip (not
  deployment-relevant, see the Validation plan). S5 gate pending.
- 2026-10-28 S5: gate passed — the recorded deployment-validation skip was
  user-accepted (timestamp 2026-10-28, S5 gate), satisfying the S7
  prerequisite for the exact dirty dev tree (dev `81c16c6` doc tip;
  integration files uncommitted). Status: VALIDATED. Next: S6
  (documentation).
- 2026-10-28 S6: docs authored and confirmed **as-is**. CHANGELOG `###
  Added` entry (the confirmed S3 draft) was applied in S4 and re-verified on
  the dirty tree: top of the Unreleased Added list, newest-first, sanitized
  wording, public issue ref only. README: no change (the phased-login
  paragraph at `README.md:277` describes blocking behaviour and points to
  `doc/SAFE_LOGIN.md` for the contract — still accurate; the
  submit-terminal extension is documented in `SAFE_LOGIN.md` itself).
  CONTRIBUTING: no change (no contributor-rule changes). `SAFE_LOGIN.md`
  ships as-is from the PR head in the feature commit. Status: VALIDATED.
  Next: S7 (commit + push: 3 commits feat/test/doc, Gitea dev, ff-only
  promotion, GitHub mirror, gated PR/issue close + Discussion summary).
- 2026-10-28 S7: complete. S7.1: three dev-commits (user-confirmed,
  dev-commits), pushed to origin/dev — `b6fa862` feat (login.py +1/−1,
  SAFE_LOGIN.md +32/−2), `bbd5169` test (test_bc_login.py +159/−2),
  `b693517` doc (CHANGELOG +7). S7.2: ff-only promotion `2a6e462` →
  `b693517` on Gitea `main` (user gate passed; not a release — no tag);
  `git diff main dev` empty. S7.3: `sync_github.sh` → GitHub `main`
  `ad18f7a`; public gate green (new hash; no STRIP paths at root; `.github`
  = `ISSUE_TEMPLATE` only, no `workflows/`; integrated content present —
  all 3 PR files + the CHANGELOG entry on `github/main`). S7.4: PR #39 close
  comment 6481319827 (text user-confirmed), PR closed **without merge**
  2026-10-28T21:38:49Z. S7.5: issue #36 close comment 6481326228 (text
  user-confirmed), issue closed as **completed** 2026-10-28T21:39:09Z — all
  acceptance criteria met (the 4 shipped tests map 1:1 to the #36 acceptance
  list). S7.6: per-public-update Discussion summary text user-confirmed; the
  Discussion write API is unavailable from this environment (404, same as the
  2026-10-25 finding) — handed to the user for manual web-UI posting. S7.7:
  Status: DELIVERED. Gitea `dev`/`main` `b693517`, GitHub `main` `ad18f7a`.
  Plan doc archived to `completed/`, cross-references updated. Next chain
  head: PR #40.

## S7 execution record (2026-10-28)

**S7.0 prerequisite:** dev = origin/dev = `5054c2a` at S7 start (the S6 plan
doc tip); working tree = the S4-validated integration (`git diff 5054c2a --
apps/ tests/ doc/` = the 3 PR files, login.py +1/−1, SAFE_LOGIN.md +32/−2,
test_bc_login.py +159/−2, byte-identical to head `0053ec6` per the S4 log) +
the maintainer-authored CHANGELOG `### Added` entry (+7); PR head still
`0053ec6` (unchanged since S1); deployment validation = recorded skip (not
deployment-relevant), user-confirmed at the S5 gate (2026-10-28) — the
trigger check still holds (the CHANGELOG entry is doc-only).

**S7.1 dev-commits (user-confirmed 2026-10-28):** the S3-confirmed three-way
split, pushed to origin/dev:
- `b6fa862` `feat: input-triggered protected login submissions (issue #36)` —
  `apps/billcollector/login.py` (+1/−1), `doc/SAFE_LOGIN.md` (+32/−2).
- `bbd5169` `test: input-triggered protected login submissions (issue #36)` —
  `tests/test_bc_login.py` (+159/−2).
- `b693517` `doc: CHANGELOG — input-triggered protected login submissions
  (issue #36)` — `CHANGELOG.md` (+7).

**S7.2 promotion (user gate passed 2026-10-28):** ff-only `dev` → Gitea
`main` `2a6e462` → `b693517`, pushed. Verified: `git diff main dev` empty,
tree clean, on `main`. Not a release — no tag, no CHANGELOG finalization.

**S7.3 mirror (deploy stage 3):** `sync_github.sh` → GitHub `main`
`ad18f7a` (sanitize-by-amend, forced push by design). Public gate: new hash
confirmed; root listing has no `.kilo` / `.vscode` / `.private` / `openwiki`
/ `AGENTS.md` / `.openwikiignore`; `.github` contains `ISSUE_TEMPLATE` only
(no `workflows/`); integrated content present (all 3 PR files + the
maintainer-authored CHANGELOG entry on `github/main`).

**S7.4 PR close (text user-confirmed 2026-10-28):** comment
https://github.com/s-t-e-f-a-n/BillCollector/pull/39#issuecomment-6481319827
(mirror flow, landed content with the public commit links, no code
adaptations, validation summary, non-blocking nit on the reused full-suite
result); PR #39 closed **without merge** at 2026-10-28T21:38:49Z.

**S7.5 issue close (text user-confirmed 2026-10-28):** comment
https://github.com/s-t-e-f-a-n/BillCollector/issues/36#issuecomment-6481326228;
issue #36 closed as **completed** at 2026-10-28T21:39:09Z. Acceptance
criteria met — the four shipped tests map 1:1 to the #36 acceptance list
(Verified facts).

**S7.6 per-public-update Discussion summary (publication routine, issue
#25):** text user-confirmed; the Discussion write API returns 404 from this
environment (2026-10-25 finding) — the user posts it in the web UI manually
(text handed over in the S7 session). Omitted (2026-10-28): the user
instructed to omit the Discussion step for PR #39 — the manual posting is
withdrawn and no Discussion is posted for this delivery.

**S7.7:** Status: DELIVERED. Gitea `dev`/`main` `b693517`, GitHub `main`
`ad18f7a`, PR #39 closed 2026-10-28T21:38:49Z, issue #36 closed
   2026-10-28T21:39:09Z. Plan doc archived to `completed/`, cross-references
   updated. Next chain head: PR #40.
- 2026-10-28 S7.6: user instructed to omit the per-public-update Discussion
  summary for PR #39 (the last remaining S7 item) — recorded as omitted, no
  manual web-UI posting. Nothing further outstanding for PR #39.
