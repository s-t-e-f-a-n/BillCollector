# PR #56 review: terminal daemon failures through opt-in ntfy (issue #49)

> Status: VALIDATED (2026-10-31) — S5 green on the exact dev tree: before/after
> proof (21 new tests fail on the pre-integration code, all 49 pass after), PR
> unit 49 OK / 15 subtests, full unit 665 passed / 10 skipped / 83 subtests
> (after the M2 test adaptation), regression VERDICT: PASS (7 scenarios / 8
> PDFs, exit 0), ruff clean, bandit 0 findings on the changed app files;
> deployment validation recorded skip (not deployment-relevant), S5 gate
> passed; S6 docs confirmed (CHANGELOG M1 entry stands under [Unreleased]
> Added, sanitized; README ntfy section renamed + extended), S6 gate passed;
> ready for S7.

## PR metadata

- PR: s-t-e-f-a-n/BillCollector#56 "feat(notify): report terminal daemon
  failures through opt-in ntfy" (flowcool), branch
  `feature/upstream-terminal-notifications-20261030`, head
  `95b11de63548df3e8cb1a94ab8b05e99a9d0bd74`. Two commits in the fetched ref
  (orphaned public tip `e83c8e2` + the feature commit `95b11de`); the real
  content is **5 files +215/−1** against the branch point `e83c8e2`.
  `mergeable_state: clean` (vs base `main` @ `ebf20bb`, the current GitHub
  tip). No PR or issue comments.
- Issue: #49 (flowcool, open) — terminal failure, interruption and attention
  timeout must reach the operator through the existing opt-in ntfy topic;
  fixed account-free messages; success/cancellation silent; notification
  failures never change the collector outcome; no double-send across
  finalization/Stop/shutdown; no SQLite connections in workers.
- Created 2026-10-30T20:13:33Z; last updated 2026-10-31T06:34:55Z (before
  this review's fetch).
- Local state at review time: Gitea `dev` = `origin/dev` = `497dbdb`, Gitea
  `main` = `origin/main` = `a75861f`, GitHub `main` = `ebf20bb`. Working tree
  clean.
- AI disclosure present: "AI-assisted focused port and synthetic verification
  under my responsibility. Branch starts directly at public main `e83c8e2`."

## Verdict

**Approve with maintainer changes** — M1 (CHANGELOG structure) and M2
(`tests/test_bc_login.py` post-count adaptation, discovered by the S5 full
unit suite); all PR code and tests apply as-is from head (byte-identical
pre-images on `dev`).

## Verified facts

1. Head stable: fetched `refs/pr/56` = `95b11de6...`; PR `updated_at`
   2026-10-31T06:34:55Z predates the fetch. S4 preflight re-checks via
   `git ls-remote github refs/pull/56/head`.
2. Branch point: the fork starts at the orphaned public tip `e83c8e2` (GitHub
   `main` at the PR #41 delivery; Gitea-side equivalent `74ba171`). `e83c8e2`
   is **not** an ancestor of the current GitHub `main` `ebf20bb` (each mirror
   sync re-pushes the Gitea lineage plus one amended sanitized tip, orphaning
   the previous public tip — same pattern as #53/#54). The GitHub "Files
   changed" view (103 files, +328/−23385; the `e83c8e2`-vs-merge-base part is
   99 files −23384 of STRIPped private content, `openwiki/` et al.) is an
   orphaned-tip STRIP artifact, not PR content. Integration applies the
   5-file delta against `e83c8e2` only.
3. Issue #49 before-claim plausible and S5-verifiable: on the pre-integration
   tree the new `RunNotificationTests::test_failed_crashed_and_early_failed_
   runs_send_once` must fail (no terminal notification path exists in
   `notify.py` / `orchestrator.py` at `e83c8e2`); after integration the PR's
   stated command passes: 49 passed, 15 subtests.
4. Pre-image vs Gitea `dev` `497dbdb` (drifted from the branch point only by
   the PR #54 scheduler fix + plan docs): `notify.py`, `orchestrator.py`,
   `tests/test_bc_notify.py`, `tests/test_bc_orchestrator.py` are
   **byte-identical** to the PR base → hunks apply cleanly. `CHANGELOG.md`
   diverges (PR #53/#54 entries added under `[Unreleased]`) → manual merge.
   Dev files changed since the Gitea branch point `74ba171`: `CHANGELOG.md`,
   `apps/billcollector/scheduler.py`, `apps/billcollector/ui/tasks.py`,
   `tests/test_bc_scheduler.py` — only `CHANGELOG.md` overlaps the PR.
5. Code review (per call site), behavior preserved vs changed:
   - `notify.py` +47: new module constant `_RUN_MESSAGES` (fixed strings for
     `failure` / `interrupted` / `needs_attention`; no portal URL, account,
     document, run id or exception text) and `notify_run_result(db, result,
     *, dispatch=None)` following the existing `notify_login_locked` pattern:
     Settings read on the caller thread (worker receives only immutable
     strings — no SQLite connection), blank/absent topic → no dispatch,
     unknown/success/cancelled result → silent before any Settings read, all
     failures (Settings, dispatch, HTTP) caught and logged as exception class
     name or HTTP status only (endpoint/topic/exception text never logged).
     New `_send_run_result` mirrors `_send_login_locked` (Title
     "BillCollector: run needs attention", Priority 4, Tags warning,
     `NTFY_TIMEOUT`, no retry on non-200). Docstring updated to "pause, login
     lock and daemon run outcomes".
   - `orchestrator.py` +8, three call sites, all through the existing
     `_dispatch_notification` worker:
     (a) `cleanup_orphans` first loop — `interrupted` for each recovered
     orphan row (row then finalized → a second cleanup at the next startup
     cannot re-send; the second, attempt-only loop is untouched).
     (b) `_finalize_run` no-row path (early failure before the Run row
     exists) — `exit_code != 0` → `interrupted` for a signal-killed runner
     (`< 0`) else `failure`; exit 0 stays silent.
     (c) `_finalize_run` row path (every terminal run) —
     `updates.get("result", row["result"])`: runner-finalized rows reuse the
     runner's result (success/cancelled/needs_attention/interrupted/failure),
     crash-finalized rows use the monitor's derived result.
     The two `_finalize_run` paths are mutually exclusive (early return), and
     the orphan cleanup only sees `result IS NULL` rows → single owner per
     terminal outcome, no double-send. `shutdown()` awaits the monitors
     (which call `_finalize_run`) and then gathers `self._notifications`, so
     sends complete before the daemon exits — "including after shutdown"
     holds.
   - Test review: `tests/test_bc_notify.py` +67 (`NotifyRunResultTests`,
     6 methods: fixed payloads once, absent/blank topic never dispatches,
     other results silent + no Settings read, exception text/endpoint
     redaction in logs, HTTP rejection logged without retry, Settings and
     dispatch errors contained). `tests/test_bc_orchestrator.py` +89
     (`RunNotificationTests`, 7 methods: fail/crash/earlyfail send once with
     the fixed payload and release the task, no topic → no send, send error
     does not change result/release and leaks nothing, success silent,
     shutdown sends once, dashboard Stop sends one interruption push, orphan
     recovery notifies only on the first cleanup). All base helpers
     (`_orch(mode, sleep)`, `earlyfail` stub mode, `create_run`,
     `set_setting`) exist in the byte-identical dev tree. No synthetic
     markers, no secrets (`"private secret"` strings are redaction
     assertions only).
6. Process check (CONTRIBUTING.md): issue referenced (#49); intended behavior
   + verification stated in the PR body; proof shipped (before/after pytest
   with expected counts); AI assistance disclosed; no secrets in code/tests;
   no new network exposure (existing `NTFY_HOST` env + `ntfy_topic`
   setting, opt-in); no shared-interface change (no setting, result value,
   exit code, DB schema, control protocol or recipe contract change —
   confirmed in the diff).
7. Cross-PR: open PRs are #55 (vault item identity), #45 (Playwright browser
   cache), #44 (recipe method-chain validation). No file overlap with #56
   besides `CHANGELOG.md` (established per-PR merge pattern). Sequencing:
   batch-2 chain `#53 → #54 → #56 → #55 → #45 → #44` (user-confirmed
   2026-10-30); #53/#54 DELIVERED → #56 is next in order.

## Risks

- Low overall: additive, best-effort notification; run results, slot release,
  exit codes and the daemon's control flow are unchanged; a dead ntfy
  endpoint only adds one logged warning per terminal outcome.
- Missed-notification window (accepted, by design): if the daemon crashes
  after the runner finalized the row but before the monitor's send, that
  outcome is never notified (startup cleanup does not re-send finalized
  rows). Consistent with issue #49's best-effort framing.
- M1 as-shipped breaks the Keep a Changelog structure (a stray top-level
  `## Terminal run notifications (#49)` section before the `[Unreleased]`
  section) → manual placement fix required.

## Integration plan (S4, on Gitea `dev`)

| File | Action | Note |
|---|---|---|
| `apps/billcollector/notify.py` | apply from head | pre-image byte-identical to dev |
| `apps/billcollector/orchestrator.py` | apply from head | pre-image byte-identical to dev |
| `tests/test_bc_notify.py` | apply from head | pre-image byte-identical to dev |
| `tests/test_bc_orchestrator.py` | apply from head | pre-image byte-identical to dev |
| `CHANGELOG.md` | **manual (M1)** | drop the author's top-level `## Terminal run notifications (#49)` section; add under `## [Unreleased] → ### Added` in the house style: `- Terminal daemon run notifications: account-free failure, interruption and attention notices through the existing opt-in ntfy topic. Successful and cancelled runs stay silent, delivery is best-effort, and the monitor sends each terminal notice once. (issue #49)` |
| `tests/test_bc_login.py` | **manual (M2)** | S5 discovery: `test_slow_login_notification_keeps_daemon_loop_responsive` pinned exactly one `requests.post` per path; the `finalize` and `orphan` paths now legitimately send the terminal run notification in addition to the login lock one. Adapted the tail assertions to a path-dependent count (`expected_posts = 2 if path in ("finalize", "orphan") else 1`), the worker-thread check to all workers off-loop, and the call-count assert to match. The loop-responsiveness intent is unchanged for every send. |

Commits (dev-commits, one concern each, proposed in S7):
1. `feat: notify terminal daemon run failures through the opt-in ntfy topic (#49)` — notify.py + orchestrator.py
2. `test: cover terminal run notifications and adapt the slow-login post-count expectations (#49)` — test_bc_notify.py, test_bc_orchestrator.py (from head) + test_bc_login.py (M2)
3. `doc: changelog — terminal run notifications (#49)` — CHANGELOG.md (M1 placement)

## Validation plan (S5, on the exact dev tree, `apps/.venv/bin/python`)

1. Before/after proof: the new `NotifyRunResultTests` / `RunNotificationTests`
   fail on the pre-integration tree, pass after (PR's stated evidence: 49
   passed, 15 subtests).
2. PR unit tests: `apps/.venv/bin/python -m unittest
   tests.test_bc_notify tests.test_bc_orchestrator -v` → all OK.
3. Full unit suite: `apps/.venv/bin/python -m pytest tests/ -q` → all pass.
4. Full regression: `apps/.venv/bin/python tests/run_regression.py --ini
   tests/bc_regression.ini` → exit 0, VERDICT: PASS (7 scenarios / 8 PDFs).
5. `ruff` + `bandit` on the changed files → nothing new beyond the known
   baseline.

### S5 results (2026-10-31, tree = dev `a96fabe` + the 5-file integration)

1. Before-proof: with the PR code files stashed (new tests kept), `unittest
   tests.test_bc_notify tests.test_bc_orchestrator` → 49 run, FAILED
   (failures=8, errors=13) — exactly the 21 new notification tests fail
   (`notify_run_result` absent / no terminal sends); the pre-existing 28 pass.
   After: the same command → 49 OK. The PR's 49-passed / 15-subtests claim
   reproduces.
2. Full unit suite (first run): 2 failed, 663 passed, 10 skipped, 83
   subtests — `test_bc_login.py::test_slow_login_notification_keeps_daemon_
   loop_responsive[finalize|orphan]` pinned exactly one `requests.post` per
   path (the PR's scoped evidence never ran that module). M2 applied →
   re-run: **665 passed, 10 skipped, 83 subtests**.
3. Regression: VERDICT: PASS — 7/7 pairs matched (3× success, 1 graceful,
   1 badlogin failure, 1 empty failure, 1 dlfail failure), 8 expected PDFs,
   exit 0.
4. `ruff check` (repo ruff.toml) on all 5 changed files: all checks passed.
   `bandit` on the changed app files (notify.py, orchestrator.py): 0 findings
   (same as the base versions); the test-file findings are the pre-existing
   `assert` baseline, unchanged.

## Deployment validation

Not deployment-relevant: no `Dockerfile`, `.dockerignore`, `BillCollector.sh`,
`install_docker-image.sh`, `deploy_remote.sh`, INI key or `.env`-handling
change (the `NTFY_HOST` env var and `ntfy_topic` setting pre-date this PR).
Recorded skip on 2026-10-31 (S5); user confirmation at the S5 gate.
Validated tree: dev `a96fabe` + the 5-file integration (working tree).

## S6 documentation (2026-10-31)

- `CHANGELOG.md`: the M1 entry (first item of `[Unreleased] → ### Added`,
  house style, `(issue #49)`) stands as placed in S4 — sanitized, no private
  paths or hosts.
- `README.md` (user-visible behavior changed — a new class of pushes):
  section `### Pause notifications (ntfy)` → `### Notifications (ntfy)`
  (TOC anchor included); the opt-in sentence now covers "a paused run, a
  blocked login, or a terminal run outcome"; one new sentence documents the
  terminal notices (fixed account-free messages, which outcomes send,
  success/cancelled silent, best-effort); both `NTFY_HOST` descriptions now
  read "push server for the ntfy notifications".
- `CONTRIBUTING.md`: no change (no contributor-rule change).
- S6 gate: user confirmed the docs as-is on 2026-10-31; status VALIDATED,
  ready for S7 (code/test/doc commits per the plan above, Gitea first).

## Out of scope

- PRs #55, #45, #44 (later in the batch-2 chain).
- The missed-notification window (best-effort by issue #49's framing).
- Pause and login-lock notification behavior (unchanged).

## Open questions

None at S2.
