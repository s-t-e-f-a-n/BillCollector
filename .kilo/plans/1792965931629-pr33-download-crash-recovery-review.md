# PR #33 review: recover download publication and consumer delivery after crashes

> Status: VALIDATED (2026-10-25) — S3 decided (M1 + M2(a) applied, manual
> merges confirmed), S4 integrated (all 12 files on dev tree), S5 code checks
> green, deployment skip user-confirmed 2026-10-25T22:44Z, S6 docs confirmed
> (user gate 2026-10-25T22:52Z). Next: S7 (commit + push, PR close).

## PR metadata

- Author: flowcool; head `b675ebe8e83f1affbdbcbbc14b6d253f57237472`
  (branch `fix/download-crash-recovery-upstream-20261025` in flowcool's fork).
  `git ls-remote github refs/pull/33/head` matches the local `refs/pr/33` at
  review time (2026-10-25T21:31Z).
- Base: `main` (PR body: public main `b4cf023f42b2d265106e1db9bde580d012a451b0`;
  GitHub re-synced the base ref to `d9362b3` after the #30/#31 mirror updates).
- Issue refs: #24 (recovery contract, agreed 2026-10-22, comment
  6352296709; lane opened comment 6374719917) and #27 F01 (filename
  collision).
- Prior maintainer review: comment 6394460302 (2026-10-25 06:37Z) approved
  this exact head; S1 here formalizes that review into the pr-review chain.
- Local state at review: `dev` `2ab91c1`, Gitea `main` `5cd1f31`
  (= `origin/main`), `github/main` `d9362b3`.
- Actual PR content: 3 commits above the orphaned base
  (`fbf7e38`, `428eea1`, `b675ebe`); 12 files, +819/−72.

## Merge-base / orphan analysis

- `git merge-base refs/pr/33 github/main` = `71c7d69` — a **raw Gitea
  commit** whose tree still contains the private agent paths (`.kilo/`,
  `openwiki/`, `.private/`, `.vscode/`, `AGENTS.md`, `.openwikiignore`,
  `.github/workflows/openwiki-update.yml`).
- The PR branch carries the **orphaned sanitized commit** `b4cf023f`
  ("doc: collection: document bounded collection actions") — it was public
  main at fork time but was replaced by the re-sanitization that followed the
  #30/#31 deliveries, so it is no longer reachable from `github/main`.
  Flagged per skill; it is not re-applied — its content already exists on
  both dev and the current mirror.
- All 82 `D` entries in the full merge-base diff are these private paths:
  comparison artifacts (absent from current `github/main`), **skip, never
  apply**. No `A`/`M` under any private path.

## Verdict

**Approve.** The #24 contract (all three agreed points) and F01 are
implemented as agreed, with the requested crash-window acceptance proof.
Two nits are recorded as optional maintainer-side changes for S3
(CHANGELOG wording; timeout-setting discoverability). No shared interface
outside the agreed contract: the `Download` schema change (additive
`state`/`staged_path`) is within #24 contract point 1/3; exit codes,
control protocol, and the recipe contract are unchanged (recovery failures
reuse the existing failure exit 1).

## Verified facts

- Issue #24 contract (comment 6352296709): (1) durable row before any
  consumer effect; (2) at-least-once delivery with a stable idempotency key
  (task + sha256); (3) staged publication + atomic rename + startup
  reconciliation (uncommitted staging re-processed or quarantined; published
  orphan row recovered conservatively as consumed). PR implements all three;
  acceptance-proof shape (interrupt before/after publication and commit,
  restart with same task identity, check publications/rows/consumer effects)
  is the shipped test design.
- Pre-image check against dev (PR base `b4cf023f`):
  - byte-identical to base (hunks apply cleanly): `apps/billcollector/consumers/__init__.py`,
    `apps/billcollector/db.py`, `apps/billcollector/downloads.py`,
    `apps/billcollector/runner.py`, `apps/billcollector/ui/app.py`,
    `tests/test_bc_downloads.py`, `tests/test_bc_residual_logs.py`
  - new on PR: `doc/DOWNLOAD_RECOVERY.md`, `tests/test_bc_downloads_recovery.py`
  - diverged (hunks verified non-overlapping): `apps/billcollector/config.py`
    (dev C1 changed the `ntfy_topic` line adjacent to the PR's new
    `download_recovery_timeout_seconds` row), `README.md` (PR changes exactly
    the Downloads bullet, dev README.md:251, byte-identical pre-image line;
    dev's C1/C2/#30 README changes are in other regions), `CHANGELOG.md`
    (PR: Unreleased/Added entry; dev: Unreleased/Fixed entries for D08+F07).
- All referenced helpers exist on dev: `runner.run_task` (runner.py:993),
  `runner._run_task` (:1012), `CheckRecipe` (runner.py:43 via helpers),
  `_vault_preflight` (runner.py:223), `Database.path` (db.py:93),
  `get_setting` fallback to `config.DEFAULT_SETTINGS` (db.py:417-422, so the
  "300" default is live without a Settings row), `list_downloads` SELECT *
  (db.py:407), `config.APP_DIR` (config.py:13), `downloads` already imported
  in runner (runner.py:47). `Downloads` is gitignored (.gitignore:11).
- No secrets in the PR diff (only synthetic test markers
  `synthetic-secret`/`fixture.invalid`, which the sanitization assertions
  depend on). No new network exposure (local `python -m` subprocess only;
  consumer slot still empty).
- PR process check (CONTRIBUTING.md): issue-first; shared-interface schema
  change agreed in #24 before code; intended behaviour + verification commands
  + expected results in the PR body; proof shipped (unit/full/ruff/bandit/mock
  harness, observed results at head); AI assistance disclosed (Codex
  reconciled, contributor owns behaviour); exit codes/contracts stated
  unchanged.

## Code review findings

- `downloads.py` (core rewrite):
  - Publication lock: `fcntl.flock` on `<output>/.billcollector/publication.lock`
    serializes publication/recovery across runner processes and daemon
    startup (Linux-only, matching the deployment target).
  - Journal: `<output>/.billcollector/<sha256(db-path)[:16]>/<uuid>/` with
    `document` + fsynced `manifest.json`; the db-path identity namespace
    stops one database from adopting another's staging when output dirs are
    shared.
  - `track_download`: recover under the lock first → validate filename (plain
    basename; `""`/`"."`/`".."`/`".billcollector"`/paths rejected, new
    ValueError failure mode for exotic portal filenames) → save to staging +
    fsync → sha256 → same-task repeat: audit row with `duplicate_of_id`,
    original `saved_path`, no publication, no delivery → collision:
    `{stem}-{uuid4}{suffix}` path, portal name retained in `filename` (F01) →
    manifest → insert row `state=staged` → `_publish` (checksum re-check,
    atomic rename, dir fsyncs, `state=published`) → `_deliver` (per-consumer
    checksum guard, `idempotency_key=<task_id>:<sha256>`, `state=consumed`
    only after all consumers succeed; failures leave the row published and
    the journal for retry) → journal cleanup when consumed.
  - Conservative adoption: a committed manifest whose published file matches
    but whose row is missing recovers a `consumed` row (no replay of unknown
    consumer effects); unknown/invalid staging → `quarantine/` (retained,
    never published); a pre-existing unmanaged file is adopted as consumed
    only on exact name+sha match with no row claiming it (legacy path
    compat, no cross-task, no consumer replay).
  - `recover_downloads`: current `download_dir` plus parents retained in
    pending rows (covers a changed download dir); per-target lock.
  - `recover_downloads_in_subprocess`: timeout setting validated positive
    integer (invalid/missing/`<=0` → RuntimeError, no child spawned); child
    `sys.executable -m billcollector.downloads <db-path>` with
    `cwd=config.APP_DIR`, output discarded, timeout kills+reaps the child;
    nonzero exit reports the code only — no command, output, or path leaks.
    Child: own `Database` connection, `sys.exit(1)` on any exception,
    `close()` in finally.
- `db.py`: additive schema (`state TEXT NOT NULL DEFAULT 'consumed'`,
  `staged_path TEXT`), idempotent `PRAGMA table_info` + `ALTER TABLE`
  migration (historical rows → consumed, no replay); `insert_download`
  keyword-only `state`/`staged_path`; new `set_download_state`,
  `pending_downloads`. ALTER SQL built from a fixed dict (known B608
  baseline pattern).
- `consumers/__init__.py`: docstring-only contract update (at-least-once,
  stable key, committed row before consumers); `CONSUMERS` still empty.
- `runner.py`: `recover_downloads(db)` in `_run_task` after the task lookup,
  before the login-blocked check, recipe validation, display, vault, and
  browser; `OSError/ValueError/sqlite3.Error` → `failure_record`
  (sanitized category) + exit 1 (existing failure code).
- `ui/app.py`: `start()` runs `recover_downloads_in_subprocess(db)` before
  Orchestrator/scheduler; the RuntimeError propagates and stops the daemon.
- `config.py`: `download_recovery_timeout_seconds: "300"` default row.
- Tests:
  - `tests/test_bc_downloads_recovery.py` (new, 30 tests, 6+5+4+3+2
    parametrized): six crash boundaries via real `os.fork()` +
    `os._exit(73)` at insert/rename/state/consumer boundaries; post-recovery
    assertions: exactly one published file, one canonical row, all rows
    consumed, one stable key, delivery count 2 only for the after-consumer
    boundary. Plus: cross-task same-name/same-hash collisions keep separate
    paths/keys; runner-start recovery runs before the portal (vault/display/
    recipe untouched, exit 1 on invalid recipe); published file without row
    adopted without redelivery (RunInterrupted + row-deletion simulation);
    partial save quarantined; new content never overwrites an existing
    file; unmanaged exact match adopted as consumed; legacy-schema migration
    idempotent and non-replaying; filename-escape rejection; changed pending
    file fails checksum before delivery (stays published); old output root
    not required once consumed; real subprocess daemon-startup reconciliation
    via `ui_app.start`; timeout kills/reaps a lock-blocked child and allows
    retry; invalid timeouts prevent the child start; child exit codes report
    without child output; runner SQLite recovery failure stops before the
    portal, keeps logs sanitized, and closes the DB.
  - `tests/test_bc_downloads.py`: +2 (consumer observes committed row +
    stable key; failed consumer retried after DB reopen with the same key).
  - `tests/test_bc_residual_logs.py`: task-source mock gains
    `path`/`get_setting`/`list_downloads` (recovery now runs inside
    `run_task`); side effects land in gitignored `apps/Downloads`.
- `doc/DOWNLOAD_RECOVERY.md`: protocol, recovery, timeout, migration/
  rollback, and verification sections are consistent with the code (checked
  line-by-line).

## Risks

- `fcntl.flock` and `os.fork()` tests are Linux-only — consistent with the
  Docker/NAS deployment target.
- The recovery child re-imports the working-tree package
  (`cwd=APP_DIR`, `-m billcollector.downloads`): fine in the image
  (`/apps`) and on dev; a partial in-place upgrade (new code, old rows) is
  the supported direction — the PR body documents the real-data rollback
  procedure (stop runners, keep backups, settle pending rows with the newer
  binary first).
- A startup timeout can interrupt a consumer after its external effect;
  replay uses the same stable key (documented at-least-once consequence).
- dev has diverged from the PR base in 3 files; merges are manual but the
  hunks are verified non-overlapping (S4 re-checks pre-images).
- If the author pushes a new head, S1 must re-run on the new head (failure
  mode); the current head is the reviewed/approved one.

## Integration plan (S4, Gitea dev)

| File | Action | Note |
|---|---|---|
| `apps/billcollector/consumers/__init__.py` | apply PR head | base-identical |
| `apps/billcollector/db.py` | apply PR head | base-identical |
| `apps/billcollector/downloads.py` | apply PR head | base-identical |
| `apps/billcollector/runner.py` | apply PR head | base-identical |
| `apps/billcollector/ui/app.py` | apply PR head | base-identical |
| `tests/test_bc_downloads.py` | apply PR head | base-identical |
| `tests/test_bc_downloads_recovery.py` | apply (new) | |
| `tests/test_bc_residual_logs.py` | apply PR head | base-identical |
| `doc/DOWNLOAD_RECOVERY.md` | apply (new) | |
| `apps/billcollector/config.py` | manual | add the `download_recovery_timeout_seconds` row to dev's current content (keep dev's C1 `ntfy_topic` opt-in line) |
| `README.md` | manual | apply the one-line Downloads-bullet change to dev's current README (dev README.md:251) |
| `CHANGELOG.md` | manual | merge the PR's Unreleased/Added entry into dev's `## [Unreleased]` (Keep a Changelog order; entry first in `### Added`) |

Optional maintainer-side changes (S3 decision):

- M1 (nit): CHANGELOG entry "Filename collisions preserve earlier files."
  → "…preserve both documents (original portal name retained in metadata)."
  to match the behaviour and the PR body. **Applied 2026-10-25 (S3 gate,
  user confirmed).**
- M2 (nit): `download_recovery_timeout_seconds` is not surfaced on the
  Settings page nor in the README Settings bullet; the doc says "set a
  positive integer" without saying where. Options: (a) no UI change, clarify
  in `doc/DOWNLOAD_RECOVERY.md` that it is a Settings-table (advanced/DB
  level) key; (b) add a Settings UI field (larger, beyond PR scope).
  Default proposal: (a). **Resolved (a) 2026-10-25 (S3 gate, user
  confirmed); the Recovery section of `doc/DOWNLOAD_RECOVERY.md` now names
  it a Settings-table key not shown on the Settings page.**

## S3/S4/S5 execution record (2026-10-25)

- S3 gate: user confirmed the integration proposal as-is (9 PR-head files +
  the 3 manual merges), M1, and M2(a).
- S4 preflight: on `dev` `02b09d3`, `git ls-remote github
  refs/pull/33/head` = `b675ebe8` (unchanged since S1); all 9 already-applied
  working-tree files verified byte-identical to `refs/pr/33` (7 via `git
  diff`, 2 untracked via `git show` + `diff`).
- S4 completed: 3 manual merges applied exactly as planned —
  `config.py` (timeout row after `download_dir`, dev C1 `ntfy_topic`
  opt-in block kept), `README.md:251` (Downloads bullet), `CHANGELOG.md`
  (Added entry, M1 wording). Tree left dirty for S5.
- S5 code checks (repo root, `apps/.venv/bin/python`, exact integrated tree):
  - PR unit suites `pytest tests/test_bc_downloads.py
    tests/test_bc_downloads_recovery.py -q` → **36 passed** (PR count).
  - Full `pytest tests/ -q` → **487 passed, 2 skipped (environment), 0
    failed**.
  - Regression `tests/run_regression.py --ini tests/bc_regression.ini` →
    **exit 0, 7 scenarios / 8 PDFs, VERDICT: PASS**.
  - `ruff check apps tests` → **All checks passed**.
  - bandit on the changed files vs the dev HEAD baseline (line numbers
    stripped): **identical finding sets** (B105 `vnc_password` empty string,
    B608 x2 fixed-dict SQL in `db.py`, B110 try/except/pass in `runner.py`).
    Documented exception: the new `tests/test_bc_downloads_recovery.py`
    carries 43 B101 `assert_used` — pytest-idiom asserts in test code only
    (no production impact; the reviewed PR head is kept as-is, so the tree
    stays byte-faithful to the reviewed content).
- S5 gate: deployment-skip judgment **user-confirmed 2026-10-25T22:44Z**
  (no Dockerfile/script/INI/.env changes; the new key is a Settings-table
  default with no env/INI surface). Status: VALIDATED.

## S6 documentation record (2026-10-25)

- Preflight: dev `d715ad0` (doc-only commit over the S5-validated tree —
  `git show --stat d715ad0` touches only this plan doc, so the integrated
  12-file tree is byte-unchanged since the S5 validation); PR head still
  `b675ebe8` per `git ls-remote github refs/pull/33/head`.
- CHANGELOG.md: the `## [Unreleased]` / `### Added` entry is at the top of
  the section, sanitized wording, M1 phrasing ("preserve both documents
  (original portal name retained in metadata)"). No other CHANGELOG changes.
- README.md: only the one-line Downloads-bullet change (README.md:251) —
  appends the `doc/DOWNLOAD_RECOVERY.md` link for staged publication,
  recovery and the at-least-once consumer contract. CONTRIBUTING.md
  unchanged (no contributor-rule change).
- doc/DOWNLOAD_RECOVERY.md: new public doc, 100 lines; sanitized (no Gitea
  host, NAS details, or private paths); M2(a) wording present (the
  `download_recovery_timeout_seconds` key named as an advanced Settings-table
  key, not shown on the Settings page); content consistent with the code
  (checked line-by-line in S1).
- Private-marker sweep over the full pending diff (12 files, incl. the 2
  untracked): no Gitea/NAS/`.kilo`/`.private`/openwiki/local-path hits.
- S6 gate: **docs user-confirmed 2026-10-25T22:52Z**. Next: S7 (commit +
  push on dev, promotion + mirror, PR/issue close, Discussion summary).

## Validation plan (S5, fully local)

From the repo root with `apps/.venv/bin/python` (Python 3.12.3) on the exact
integrated dev tree:

- PR unit suites: `apps/.venv/bin/python -m pytest tests/test_bc_downloads.py
  tests/test_bc_downloads_recovery.py -q` → expected 36 passed (PR's count on
  the same file content).
- Full pytest: `apps/.venv/bin/python -m pytest tests/ -q` → all pass
  (dev baseline 454 + 30 new; environment skips allowed).
- Regression: `apps/.venv/bin/python tests/run_regression.py --ini
  tests/bc_regression.ini` → exit 0, 7 scenarios / 8 PDFs, `VERDICT: PASS`
  (exit 3 → a real run holds the lock, stop it first).
- `ruff check apps tests` + bandit on the changed files → nothing new beyond
  the known baseline (B608 fixed-dict SQL, B104 UI bind, subprocess nosec
  markers justified in-line).
- If the harness needs the `Service` table and `apps/db/bc.db` is a 0-byte
  gitignored file: re-initialize via the production DatabaseManager (no repo
  impact).

## Deployment validation

- Trigger check: the PR touches no `Dockerfile`, `.dockerignore`,
  `BillCollector.sh`, `install_docker-image.sh`, `deploy_remote.sh`, compose
  file, INI file, or `.env` handling. The new runtime key is a
  `DEFAULT_SETTINGS` row with a default (no env/INI surface).
- Decision: **not deployment-relevant — skip the Docker build/canary/smoke
  block** (judgment recorded here per the continuation-order plan).
- **User confirmation of the recorded skip: 2026-10-25T22:44Z** (S5 gate) —
  S7 may proceed to promotion on the exact tree validated above.

## Out of scope

- Consumer implementations (F10/C8 lane — schedulable after #33 lands).
- Result-semantics contract C4 (needs #33 + #34).
- Legacy batch tracker path (stated unchanged; `BillCollectorServices_pw`
  untouched).
- Power-loss semantics and external writers that bypass the publication lock
  (explicitly excluded by the PR body).
- Settings-UI exposure of the timeout key (M2, S3).

## Open questions

- ~~S3: M1 / M2 decisions~~ — resolved 2026-10-25: M1 applied, M2(a) applied.
- ~~S5: confirm the recorded deployment-skip judgment~~ — confirmed
  2026-10-25T22:44Z.
- ~~S6: confirm the docs~~ — confirmed 2026-10-25T22:52Z.
- S7: close comment for PR #33 and the related-issue closure comment for #24
  (acceptance criteria met → close); #27 stays as-is (already closed).
