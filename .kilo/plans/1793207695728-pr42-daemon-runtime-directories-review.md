# PR #42 review: fix — defer legacy database directory creation to database open

> Status: VALIDATED (2026-10-28) — S5 gate passed: all code checks green,
> deployment-validation skip user-accepted; S6 docs confirmed as-is; next S7.

## PR metadata

- PR: `s-t-e-f-a-n/BillCollector#42` "fix: avoid creating the legacy database
  directory on runner import" (not draft).
- Author: flowcool; head branch `fix/daemon-runtime-directories`.
- Head hash: `0efaec90a5effffd1cd554d3a6c220f7a3e7a2ae` (fetched as
  `refs/pr/42`; `git ls-remote github refs/pull/42/head` identical at review
  time 2026-10-28).
- Fork base: `93bfcc852a7ad36edbd3a9bbd359f5aead36cfb6` — the sanitized
  post-#32 GitHub `main` tip (see below; issue #43 cites it as the public
  main where the bug was observed).
- GitHub base ref at review time: `main` @ `484048d`.
- Issue refs: #43 (bug report with acceptance criteria; "Closes #43").
- Local state at review time (2026-10-28): dev `db4b0dd`, Gitea `main`
  `75b885b`, `github/main` `484048d`. `mergeable_state: clean`; created
  2026-10-27T14:20:33Z.
- Chain position: head of the 2026-10-27 addendum order
  #34 → #35 → #42 → #39 → #40 (#41 held on #38); #34 DELIVERED 2026-10-27,
  #35 DELIVERED 2026-10-28.

## Mirror / fork structure (why the merge-base diff misleads)

- `sync_github.sh` amends only the tip commit of Gitea `main` (strips the
  STRIP paths, pins the committer date) and force-pushes it to GitHub
  `main`. Ancestor commits keep their Gitea hashes — with private files
  still in their trees.
- `git merge-base refs/pr/42 github/main` = `6a99a5c`, an unsanitized Gitea
  ancestor whose tree contains `.kilo/`, `.private/`, `openwiki/`,
  `AGENTS.md`, `.vscode/`, `.openwikiignore`,
  `.github/workflows/openwiki-update.yml`.
- The PR's parent commit `93bfcc85` ("doc: plans — PR #32: S6 docs
  confirmed as-is …") is the **amended/sanitized version of Gitea commit
  `bde713c`** (same message; identical non-private tree; STRIP paths
  removed). It was the GitHub `main` tip at the PR #32 delivery (S7 record:
  "GitHub 93bfcc8"). A later force-push replaced it on the public branch
  with the raw Gitea ancestor `bde713c`, leaving `93bfcc85` orphaned.
- Consequently `git diff 6a99a5c...refs/pr/42` shows 89 deleted private-file
  entries (20,449 deletions, 0 insertions) — pure STRIP artifacts of the
  orphaned parent commit. All sit under the STRIP list and all are absent
  from the current `github/main` tip tree (`484048d`). These are fork-based
  comparison artifacts, not PR changes: **skipped, never applied** (same
  classification as the earlier PR #14–#16 / #35 findings).
- The real PR content is `git diff 93bfcc85...refs/pr/42`: **3 files,
  +90/−1** — 1 line removed in the shared helper import, 4 lines added in
  the legacy `DatabaseManager`, 1 new 86-line test module.

## Verdict

**Approve**, no maintainer-side code changes required.

Grounds:

- The bug is real and verified in the dev tree: `runner.py:44` imports
  `helpers`, whose import executes `os.makedirs(DB_DIR, exist_ok=True)`
  (`BillCollectorHelpers.py:36`) on the legacy app-relative path, before any
  `BC_*`-redirected runtime path is used. An unwritable application tree
  raises `PermissionError` at import (issue #43, reproduced by the author
  under UID 1003:1000 with network disabled).
- The fix is minimal and preserves legacy semantics: directory creation moves
  from shared helper import to `DatabaseManager.__init__` (parent of
  `db_name`, only when `dirname` is non-empty), i.e. first open of the
  legacy database — the exact behavior issue #43 asks to keep.
- All runtime (daemon) paths already create their own directories from the
  configured paths (`config.ensure_dirs()` at `db.py:98`, `runner.py:996`,
  `cli.py:80`), so the redirected layout is fully covered without the
  import-time side effect.
- No shared-interface change: no DB schema, control protocol, recipe
  contract, or exit-code change (verified; the `Service` table DDL and the
  runner's return codes are untouched).
- Process check passes: issue referenced (#43, with acceptance criteria);
  intended behavior + verification stated; proof shipped (focused `pytest
  tests/test_bc_runtime_paths.py -q` → expected `2 passed`; full suite
  `529 passed, 3 skipped, 53 subtests passed` on the fork; Ruff 0.17.1
  passes; Bandit 1.9.4 no new findings); AI assistance disclosed; no
  secrets (synthetic state only, env scrubbed of `BC_*`/`BW_*` in the tests);
  no new network exposure.
- Cross-PR: #40 also touches `apps/BillCollectorServices_pw.py`, but the
  chain order puts #42 first — no conflict for this PR; #40's own S1/S4 must
  re-run its pre-image checks against the post-#42 tree.

## Verified facts

1. Import chain: `apps/billcollector/runner.py:44`
   (`from helpers import CheckRecipe, ServiceObj, VARIABLE_MAP`) — every
   `billcollector run` imports the helper module and therefore executed the
   legacy `os.makedirs` before the fix.
2. The only legacy open of `apps/db/bc.db` is
   `apps/BillCollectorServices_pw.py:227`
   (`bcs.db = DatabaseManager(DB_FILE)` inside `perform_actions`); the
   helper's `DB_DIR`/`DB_FILE` constants have no other consumers in `apps/`
   (daemon code uses `billcollector.config` instead).
3. `DatabaseManager` is instantiated nowhere else in `apps/` (grep
   `DatabaseManager(` → `BillCollectorServices_pw.py:227` only); the
   daemon-side `Database` wrapper (`billcollector/db.py:97-98`) calls
   `config.ensure_dirs()` before connecting.
4. `os.path.dirname(db_name)` guard: a bare filename (empty dirname) skips
   `makedirs` and lets SQLite create the file in the CWD — no behavior
   regression for relative names.
5. The PR's tests assert the exact issue #43 acceptance surface: unwritable
   app tree (mode `0555`) + configured runtime dirs → runner reaches
   "task 999999 not found" (rc 1, `runner.py:1023`) without `PermissionError`
   and without creating `apps/db`; runtime `db/bc.db` + `profiles`, `output`,
   `logs`, `displays`, `runs` exist under the configured root. Second test:
   legacy defaults unchanged, `apps/db` absent after import, created on
   `DatabaseManager` first open, `Service` table present.
6. `tests/run_regression.py:351` (`db_snapshot()`) connects directly to
   `apps/db/bc.db` before the first scenario; it already required a
   pre-initialized legacy DB before this fix (a fresh clone has no `bc.db`
   and no `Service` table even with the directory present) — the PR changes
   no material precondition (see Risks R1).
7. `tests/check_image_runtime.py:127-129` opens `DatabaseManager(DB_FILE)` —
   covered by the new first-open creation.
8. Repo tooling: `pytest` is available in `apps/.venv/bin` and the repo root
   carries `pytest.ini`, so the pytest-style test module (uses the `tmp_path`
   fixture) fits the repo test setup; it is **not** discoverable by
   `python -m unittest` (module-level functions, not `TestCase`).
9. PR head `0efaec90` is byte-stable: fetched ref and remote head identical
   at review time.

## Code review findings

Per file (all against the dev tree):

- `apps/helpers/BillCollectorHelpers.py` (−1): removes the import-time
  `os.makedirs(DB_DIR, exist_ok=True)`. Behavior change: importing the helper
  no longer creates `apps/db`. No other import-time side effect is affected
  (`PLAYWRIGHT_BROWSERS_PATH` env set remains).
- `apps/BillCollectorServices_pw.py` (+4, in `DatabaseManager.__init__`):
  creates the parent directory of `db_name` before `sqlite3.connect`.
  Idempotent (`exist_ok=True`); the per-service re-instantiation at
  `BillCollectorServices_pw.py:227` re-runs it harmlessly.
- `tests/test_bc_runtime_paths.py` (+86, new): two subprocess-isolated
  pytest tests; `copy_apps` excludes `.venv`, `browser`, `data`, `db`,
  `Downloads`, `__pycache__`, `.env`, `*.log`, `.bc.lock` (no secrets or
  heavy state copied); `environment()` strips inherited `BC_*`/`BW_*` vars
  (no real vault endpoint); 30 s timeouts bound the subprocess runs.

Nits (non-blocking, noted for the S7 close comment):

- N1: each test copies the full `apps/` tree (2 copies per suite run) —
  acceptable cost for the import-isolation the test needs.
- N2: the `0555` unwritability simulation is ineffective under root (root
  bypasses directory permissions); the suite must run as a non-root user —
  true on the dev host and in the non-root container.

## Risks

- R1 (low): regression harness first snapshot (`run_regression.py:351`)
  assumes an initialized legacy DB — unchanged precondition, but a fresh
  clone now also lacks the `apps/db` directory (it was created at import
  before). Both states fail the same snapshot (`no such table: Service` vs
  `unable to open database file`); S5 verifies on the initialized dev tree.
- R2 (low): test 1's `0555` chmod is a no-op under root (see N2) — the test
  would silently pass for the wrong reason only if run as root; the dev
  suite runs as the user, and the S5 run records the uid.
- R3 (low): subprocess import chain includes Playwright; author reports the
  runs fit the 30 s timeout; S5 re-verifies on this host.
- R4 (managed): #40 (later in the chain) modifies the same
  `BillCollectorServices_pw.py`; integrating #42 first keeps this PR's
  pre-image clean; #40's chain re-checks its pre-image then.

## Integration plan (S4, on Gitea dev)

Preflight: on `dev`, clean tree; `git ls-remote github refs/pull/42/head`
still `0efaec90a5effffd1cd554d3a6c220f7a3e7a2ae`; re-run pre-image checks.

| File | Action | Expected conflicts |
|---|---|---|
| `apps/helpers/BillCollectorHelpers.py` | apply PR head (−1) | none (dev byte-identical to pre-image) |
| `apps/BillCollectorServices_pw.py` | apply PR head (+4) | none (dev byte-identical to pre-image) |
| `tests/test_bc_runtime_paths.py` | apply PR head (new, as-is) | none (absent in dev) |
| 89 deleted private/STRIP paths (orphan-commit artifacts) | **skip — never apply** | — |
| `CHANGELOG.md` | authored by maintainer in S6 (PR ships no entry) | — |

No manual conflict resolutions expected. Tree left dirty after S4 for S5.

## Validation plan (S5, exact dev tree, repo root, `apps/.venv/bin/python`)

- PR tests: `apps/.venv/bin/python -m pytest tests/test_bc_runtime_paths.py
  -q` → expected `2 passed` (pytest, not unittest — see Verified fact 8).
- Full suite: `apps/.venv/bin/python -m pytest tests/ -q` → expected all
  passed (dev-tree count; the PR's fork-based count `529` is not the
  expectation on dev).
- Full regression: `apps/.venv/bin/python tests/run_regression.py --ini
  tests/bc_regression.ini` → exit 0 (7 scenarios / 8 PDFs, VERDICT: PASS).
  Exit codes per deploy-skill semantics (exit 3 → a real run holds the
  lock; stop it first).
- Static: `ruff check` (F821, E4/E7/E9) + `bandit` on the two changed
  `apps/` files + the new test module → nothing new beyond the known
  baseline (B608 dynamic SQL table names, B104 UI bind).
- Record the running uid for the `0555` test (R2).

## Deployment validation (S5)

**Not deployment-relevant** — the PR touches none of `Dockerfile`,
`.dockerignore`, `BillCollector.sh`, `install_docker-image.sh`,
`deploy_remote.sh`, or app runtime configuration (INI keys / `.env`
handling). The runner-import change has no container-build or startup-path
effect (the container runtime UID already owns the writable paths it uses).
Skip recorded 2026-10-28 alongside the green code checks; **user-confirmed
2026-10-28 at the S5 gate** — S6/S7 unblocked.

## Out of scope

- The 89 deleted private/STRIP file entries (orphan-commit artifacts; see
  Mirror / fork structure).
- Any DB schema, control protocol, recipe contract, or exit-code change
  (declared unchanged by the PR; verified).
- Issue #43 acceptance criteria beyond the two shipped tests (all four are
  covered by them).
- Deployment-process validation (not deployment-relevant, above).

## Open questions

- None.

## Execution log

- 2026-10-28 S1: review complete (findings above). Head `0efaec90` fetched
  and verified stable; merge base `6a99a5c`; orphan parent `93bfcc85`
  classified; pre-image checks clean on both modified files.
- 2026-10-28 S2: plan doc written, verdict **approve** (no maintainer-side
  changes). Status: AWAITING-DECISION.
- 2026-10-28 S3: gate passed — proposal confirmed **as-is**: apply the 3 PR
  files from head `0efaec90` (`BillCollectorHelpers.py` −1,
  `BillCollectorServices_pw.py` +4, `tests/test_bc_runtime_paths.py` +86
  as-is), skip the 89 STRIP/orphan artifacts, no manual conflict
  resolutions, no maintainer-side changes. Commit split: fix commit + test
  commit (S7), CHANGELOG authored in S6. Head re-verified unchanged;
  pre-image   re-checked clean on dev `287d4dc`. Status: INTEGRATING.
- 2026-10-28 S4: integration applied. Preflight green on dev
  `e1eee39`: clean tree; remote head == local `refs/pr/42` ==
  `0efaec90` (unchanged since S1); pre-image re-checks clean (both
  modified files byte-identical to PR base; test module absent in dev).
  Applied from PR head: `BillCollectorHelpers.py` (−1),
  `BillCollectorServices_pw.py` (+4), `tests/test_bc_runtime_paths.py`
  (+86, new) — all three verified byte-identical to head (+90/−1). No
  maintainer-side changes; no CHANGELOG merge (PR ships no entry;
  authored in S6). Tree left dirty for S5. Status: INTEGRATING.
- 2026-10-28 S5: code checks all green on the exact dirty dev tree (S4
  applied, pre-commit). PR tests: `pytest tests/test_bc_runtime_paths.py
  -q` → **2 passed in 1.99 s** (uid 1000 / stefan, non-root — the `0555`
  unwritable simulation is effective; R2 mitigated). Full suite:
  `pytest tests/ -q` → **592 passed, 10 skipped, 53 subtests passed**
  (PR #35 baseline 590 + the 2 new tests). Full regression:
  `run_regression.py --ini tests/bc_regression.ini` → **exit 0, VERDICT:
  PASS** (7 scenarios / 8 PDFs, downloads 8/8). Ruff (F821, E4/E7/E9) on
  the 3 files: 9 findings, identical to the pre-change baseline (all
  legacy code, none in the PR hunks) — nothing new. Bandit: legacy files
  = known B608 only; the new test module adds 11 test-only findings
  (8 assert, 3 subprocess) — no runtime findings.   Deployment
  validation: recorded skip (not deployment-relevant, above).
- 2026-10-28 S5: gate passed — deployment-validation skip user-accepted
  (timestamp 2026-10-28, S5 gate). Status: VALIDATED. Next: S6 (CHANGELOG
  entry, authored by maintainer).
- 2026-10-28 S6: CHANGELOG `## [Unreleased]` → `### Fixed` entry authored by
  maintainer (PR ships no entry); README/CONTRIBUTING unchanged (README
  mentions `apps/db` only as a volume/setup path — no import-time creation
  claim; no contributor-rule change); sanitization re-checked (no private
  paths/hosts). PR head still `0efaec90`. Gate passed — docs confirmed
  as-is. The first S6 record commit (`40d6aae`, already pushed) accidentally
  included the staged S4 code files; re-split on user approval into the
  S3-confirmed split — `f8e16c7` fix commit (2 `apps/` files, +4/−1),
  `550ef80` test commit (new test module, +86), then this doc commit — and
  force-pushed `origin/dev` (private Gitea; `main` unaffected). Working
  tree: only CHANGELOG dirty (uncommitted for S7). Next: S7 (commit + push
  Gitea first, then GitHub mirror, PR close, issue #43 closure, Discussion
  summary).
