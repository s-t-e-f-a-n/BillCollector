# PR #23 review — residual runner exceptions out of retained logs

> Status: AWAITING-DECISION (2026-10-21) — S1 review + S2 plan complete,
> verdict APPROVE; awaiting the user's go for S3 (integration proposal).

## PR metadata

- **Repo**: `s-t-e-f-a-n/BillCollector` (sanitized GitHub mirror) — PR #23
- **Title**: fix: prevent residual runner exceptions from entering retained logs
- **Author**: flowcool (CONTRIBUTOR); open, non-draft; `mergeable_state: clean`
- **Head**: `ce7d470bc55d1265bc97d31c3f8df4d7b951ce54` on
  `fix/residual-runner-log-retention` (fork `flowcool/BillCollector`)
- **Base**: `main` @ `c539b3420d0495ee6c4133e88e3a74e6e98740ad` (= tip of
  `github/main` at review time)
- **Commits above base**: exactly 1 —
  `ce7d470 fix: keep residual runner exceptions out of retained logs`
- **Issue/PR refs**: follow-up to merged PR #17 (redaction / `failure_record`
  policy, fixes issue #10 — the secret-safety goal); the PR body references
  #17 as the prior work. Created 2026-10-21T07:26Z.
- **Fetched as**: inspection-only `refs/pr/23` (never merged into the Gitea
  lineage, never pushed anywhere).
- **Local state at review (S2, 2026-10-21)**:
  - Gitea `dev` = `a306d37` (M4 closeout); working tree clean on `dev`
  - Gitea `main` = `98af41f` (ancestor of `dev`; `dev` is 44 commits ahead)
  - `github/main` = `c539b34` (mirror tip = PR base)
  - `git ls-remote github refs/pull/23/head` = `ce7d470` (unchanged since S1)

## Verdict

**APPROVE** — integrate all four files from the PR head; no maintainer-side
code changes. The only manual merge is the CHANGELOG entry, and the 3-way
apply resolves it cleanly with the entry landing at the top of
`## [Unreleased]` → `### Fixed` per Keep a Changelog ordering (verified on a
scratch worktree of `dev`).

## Verified facts

1. **Merge base** = `c539b34` = tip of `github/main` → the PR is based on the
   current public mirror; no orphaned public-history commits; exactly one
   commit above the base.
2. **Retention mechanism** (what the PR hardens): runner logs to plain
   stdout → orchestrator spawns the runner with `stderr=STDOUT` merged
   (`orchestrator.py:355`) → `_monitor` appends every line to the per-run
   log and, on a positive exit, the last 100 lines to `Run.notes`
   (`orchestrator.py:469-472`). Raw exception text logged by the runner was
   therefore retained on disk and in SQLite.
3. **`failure_record` contract**: `failure_record(method, error=None,
   category=None)` at `redaction.py:74` — fixed-shape dict
   `{method, category[, resolved_count]}`, no message text; category from
   `failure_category` (`redaction.py:54`). Both names are already imported by
   dev's `runner.py:51` (PR #17 work, already in the PR base).
4. **Seven sites replaced** (raw `{e}` / `logger.exception` → `failure_record`):
   `pause.py:86` `scan_elements`, `pause.py:143` pause screenshot,
   `runner.py:153` `get_totp` (OTP re-fetch), `runner.py:500` step screenshot,
   `runner.py:749` `launch_persistent_context`, `runner.py:778` `run_recipe`,
   `runner.py:871` `run_task` (line numbers in the merged-on-dev tree).
5. **No behavior change beyond log content**: every hunk only changes the log
   call inside an existing `except Exception` branch (adding `as e` where
   missing). `RunInterrupted` re-raises, degraded return values (`[]`,
   `{"path": None, "data": None}`, `(files, True, None)`), abort flags, and
   `run_task`'s `return 1` are unchanged.
6. **No shared-interface change**: DB schema, control protocol, recipe
   contract, exit codes, and vault transport untouched (verified against the
   full diff).
7. **Test** (`tests/test_bc_residual_logs.py`, new, 107 lines): one test /
   7 subtests on the existing `OrchestratorTestBase`
   (`tests/test_bc_orchestrator.py:143`). A real subprocess calls each
   production exception handler and exits 1; both retained outputs (per-run
   log + `Run.notes`) must not contain the synthetic marker
   `synthetic-retention-marker` or `Traceback`, and must contain
   `'method': '<method>'` + `'category': 'other'`. Fully synthetic (`.invalid`
   domains, marker string) — no secrets.
8. **Patched names/signatures all present on dev**: `_fresh_otp`
   (`runner.py:139`), `_record_step` (`:477`), `_run_recipe` (`:732`),
   `_start_display_stack` (`:230`), `_install_signal_handlers` (`:93`),
   `CheckRecipe` (import `:42`), `runner.display` (import `:46`),
   `pause.PageState`, `runner.get_totp` / `runner.VaultAPIError`,
   `_RunContext`, `_vault_preflight` (new `(task, db)` signature — the test
   patches it with a Mock, signature-agnostic).
9. **Apply check against dev `a306d37`** (S2, scratch worktree):
   `git apply --3way` of the full PR diff (all 4 files) exits 0; the merged
   tree passes `py_compile` on all three Python files.
10. **Process check (CONTRIBUTING.md)**: prior PR/issue referenced ✓
    (#17); intended behavior + verification commands stated ✓; proof shipped
    (new tests + 322-pass full suite + regression VERDICT PASS + Ruff 0.17.0
    clean + Bandit 1.9.4 at the 20-finding baseline) ✓; AI assistance
    disclosed (Codex) ✓; no new network exposure ✓; no secrets in code,
    tests, or artifacts (manual scan: only synthetic markers and `.invalid`
    domains) ✓.
11. **Cross-PR**: independent of #19 (draft, issue #18) and #22 (issue #20)
    — no code or test dependencies; mergeable in any order; smallest of the
    three.

## Code review findings

- `apps/billcollector/pause.py` — import gains `failure_record`; the
  `scan_elements` warning and the pause-screenshot warning now log the safe
  record. Fallbacks unchanged (`return []`; degraded screenshot payload).
- `apps/billcollector/runner.py` — five sites: OTP re-fetch warning keeps the
  `otp_fallback` return; step-screenshot warning keeps `_record_step` flow;
  browser-launch `logger.exception` → `logger.error` with the record (still
  returns the aborted triple); the outer `_run_recipe` handler and the
  `run_task` outer handler move from `logger.exception` to `logger.error` +
  record, keeping `aborted = True` and `return 1`.
- `tests/test_bc_residual_logs.py` — real-subprocess, production-handler
  coverage of all seven sites; asserts absence of marker + `Traceback` and
  presence of the fixed record in both retained outputs; run finalized as
  `failure` and the task back to `idle` after each case.
- `CHANGELOG.md` — one `### Fixed` entry, sanitized wording, no private
  hosts/paths.
- No out-of-scope residuals found in the diff (4 files, 124+/10-).

## Risks

- By-design loss of traceback detail in the retained per-run log and
  `Run.notes` — method + category + surrounding log lines remain; the
  diagnostic intent is the same `failure_record` policy already accepted in
  PR #17.
- The `screenshot` method label is shared by the two screenshot sites, but
  the distinct log messages ("Pause screenshot failed (run continues)" vs
  "Step N screenshot failed (run continues)") keep them unambiguous in the
  run log.
- The stored `~/.git-credentials` GitHub token returns 401 for the REST API
  at S2 time (git protocol works; MCP read works). This does not block
  integration; it only affects S7's PR close, which then falls back to the
  user commenting/closing in the web UI (skill failure mode).

## Integration plan (per file, on Gitea `dev`)

| File | Disposition | Notes |
|---|---|---|
| `apps/billcollector/pause.py` | apply verbatim from `refs/pr/23` | clean pre-image on dev; 2 sites |
| `apps/billcollector/runner.py` | apply via `git apply --3way` | diverged on dev (vault-Settings resolution, `f4fdbd1` — `_vault_preflight(task, db)` + env export in `run_task`); regions are disjoint from the PR's five hunks; 3-way verified clean on a scratch worktree of `a306d37` |
| `tests/test_bc_residual_logs.py` | apply verbatim from `refs/pr/23` | new file; absent on dev |
| `CHANGELOG.md` | apply via `git apply --3way`, then verify | entry lands at the top of `## [Unreleased]` → `### Fixed` (before the `tzdata` entry), dev's existing entries preserved; Keep a Changelog subsection order intact; no further manual edit needed (verified) |

Preflight (S4): on `dev`, clean tree; PR head still `ce7d470`
(`git ls-remote github refs/pull/23/head`); re-run the pre-image checks.
Tree left dirty after apply (S5 validates the exact content before any
commit).

Commits to create (S7, dev-commits, one concern per commit):

1. `fix: runner+pause: keep residual exceptions out of retained logs` —
   `apps/billcollector/pause.py`, `apps/billcollector/runner.py`
2. `test: residual logs: cover all seven runner exception handlers` —
   `tests/test_bc_residual_logs.py`
3. `doc: changelog: [Unreleased] entry for residual exception log redaction` —
   `CHANGELOG.md`

## Validation plan (S5, repo root, `apps/.venv/bin/python`, exact dev tree)

1. PR unit tests:
   `apps/.venv/bin/python -m unittest tests.test_bc_residual_logs -v` →
   1 test, 7 subtests, OK.
2. Full regression:
   `apps/.venv/bin/python tests/run_regression.py --ini tests/bc_regression.ini`
   → exit 0 (7 scenarios / 8 PDFs, `VERDICT: PASS`). Exit codes 1/2/3/4 per
   deploy-skill semantics (exit 3 → a real run holds the lock; stop it first).
3. Lint on changed files: ruff (F821, E4/E7/E9) + bandit on
   `apps/billcollector/runner.py`, `apps/billcollector/pause.py`,
   `tests/test_bc_residual_logs.py` → nothing new beyond the known baseline
   (B608 dynamic SQL table names, B104 UI bind).

## Deployment validation

Not deployment-relevant: the PR touches no `Dockerfile`, `.dockerignore`,
`BillCollector.sh`, `install_docker-image.sh`, `deploy_remote.sh`, and no app
runtime configuration (INI keys / `.env` handling). The full
build/canary/smoke block is skipped per the skill; recorded here so S5's
gate can confirm the recorded skip. (If the tree gains deployment-relevant
changes before promotion, the block must be run on a Docker-capable host
first.)

## Out of scope

- PR #22 (durable login-failure budget, issue #20) and PR #19 (bounded
  collection actions, issue #18) — separate workflow chains.
- Retaining full tracebacks for debugging (deliberately reduced by design).
- Orchestrator-side changes (the retention mechanism is untouched; the
  runner's logged content is the target).
- Posting the PR close comment / closing the PR — S7; currently blocked by
  the 401 GitHub API credential (web-UI fallback).

## Open questions

- None for the verdict.
- Operational: S7's PR close needs a working GitHub API credential or the
  web-UI fallback (stored token 401 at S2; git protocol unaffected).

## Stage log

- **S1 (2026-10-21, session ses_e9f7b7b63ffe1w6zieZyF9nwdR)**: full review —
  mechanism, code, tests, process, cross-PR checks; expected verdict approve.
- **S2 (2026-10-21)**: plan document written; head re-verified `ce7d470`;
  3-way apply re-verified on a scratch worktree of `dev a306d37`
  (all 4 files clean, `py_compile` OK); CHANGELOG landing verified;
  status AWAITING-DECISION.
