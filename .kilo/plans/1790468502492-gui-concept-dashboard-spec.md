# BillCollector — GUI Concept, Dashboard-First (spec) + M1 Session 1 (execution plan)

**Status:** implementation-ready. Execute **Session 1** in a new implementation session.
**Baseline docs:** this file (GUI concept + dashboard spec, below) and
`.kilo/plans/1790364274061-billcollector-nicegui-daemon-plan.md` (v2 daemon plan — master
for daemon/scheduler/runner; its M1 section defines what Session 1 starts).

---

## Prerequisite — commit + push the working baseline (run before Session 1)

The M0 + fast-track work is uncommitted. Local `playwright` is in sync with Gitea
(`origin/playwright`, 0 ahead / 0 behind); only the working tree needs moving.
**No GitHub remote is configured in this clone** — step 4 needs the GitHub repo URL.
Plan mode cannot run mutating git commands; run this sequence yourself or hand it to an
implementation-capable session.

`BillCollector.py` intermixes M0 (logging) and fast-track (`--service`) hunks inside the
same diff hunks (e.g. the `WebRetriDoc` signature and the first logger change share one
hunk), so it is not split — both milestones go into commit 1.

```bash
# 1) M0 + fast track (all code)
git add .gitignore install_local.sh apps/
git commit -m "M0: drop selenium, logging module, refresh deps (Python 3.12, Playwright 1.63); add NiceGUI manual run UI with per-service filter"

# 2) plans + session config (matches the "Add: Kilo code plans" convention)
git add .kilo/
git commit -m "Add: Kilo plans (daemon v2, ubuntu 24.04 migration, logger, manual run UI, GUI concept)"

# 3) push to Gitea
git push origin playwright

# 4) GitHub (URL needed — remote not configured in this clone)
git remote add github https://github.com/<OWNER>/BillCollector.git
git push github playwright
```

Notes:
- `git add apps/` stages only non-ignored files (`db/`, `browser/`, `Downloads` are
  already in `.gitignore`); verify with `git status` after staging.
- If GitHub's `playwright` branch has diverged, the push is rejected — then
  `git fetch github && git merge github/playwright` (no force-push) and push again.
- If GitHub auth is not set up: `gh auth login` or a PAT in the credential helper.

## Session 1 — M1 kickoff: daemon foundation (DB + config + CLI + app skeleton)

**Scope:** v2 plan M1 items 1, 2, 7 (app skeleton, DB redesign + one-time ini import, CLI).
Runner, orchestrator, scheduler, control socket, auth, and all M2 pages are **next
sessions**. No legacy file is modified.

### Context for the implementer (verified facts)

- Python 3.12 venv at `apps/.venv` with `nicegui==3.17.1`, `fastapi`, `uvicorn`,
  `playwright==1.63.0` installed. **pytest is NOT installed.**
- DB: `apps/db/bc.db` (constants in `helpers/BillCollectorHelpers.py:33-34`). Contains
  legacy tables (`Service`, `PageStatus_*_RunN`) — **additive only, never drop/alter legacy**.
- Working tree holds uncommitted M0 + fast-track changes; the prerequisite section below
  commits + pushes them first, so Session 1 starts from a clean tree.
- Conventions: English comments/docstrings; stdlib `logging` (no `print` hacks);
  sync code; the new package must **not** import legacy `helpers` (keeps the UI process
  free of scraping coupling).
- Run everything with `cwd = apps/` (`python -m billcollector` needs `apps/` on the path).

### Confirmed decisions

1. New package `apps/billcollector/`: `__init__.py`, `__main__.py`, `cli.py`, `config.py`,
   `db.py`, `ui/__init__.py`, `ui/app.py`.
2. Same DB file `apps/db/bc.db`; new tables created additively; WAL + busy_timeout on
   connect.
3. One-time ini import on first `serve` startup: source **`bc_default.ini` only**
   (`bc_test.ini` is the identical debug alias — importing both would duplicate pairs),
   marker `ini_import` in `Settings`; tasks created **disabled**, cron default
   `0 6 1 * *` (1st of month 06:00; safe because disabled), status `idle`.
   **Empty user lists** (`KabelDeutschland=`) mirror the legacy parser
   (`BillCollector.py:188-193`): one task with `user = ""` — the vault link is then
   `f"{service} {user}".strip()` = the service name, exactly as legacy. Expected import
   from the current `bc_default.ini`: **11 tasks** (winSIM ×5 + 6 empty-user services).
   (`Lichtblick` existed only in the removed `[Selenium]` section — correctly excluded.)
4. Name normalization `norm(s) = s.strip().lower().replace(" ", "_")`:
   `recipe_file = recipes_playwright/recipe-pw__<norm(service)>.yaml`,
   `profile_dir = browser/profiles/<norm(service)>_<norm(user)>` — but when
   `user = ""` it is `browser/profiles/<norm(service)>` (no trailing underscore)
   (matches the legacy recipe convention at `BillCollectorServices_pw.py:383-384`).
   Task rows keep original ini casing for display; `user = ""` renders as `—` in the UI.
5. CLI: `serve` (port 8000, env override `BC_UI_PORT`) and `run <task_id> [--debug]`.
   `run` validates the task exists, then exits **2** with "runner not implemented yet
   (next M1 session)" — `--debug` accepted, ignored. Unknown task → exit 1.
6. Port 8000 collides with the fast-track `bc_ui.py` (also 8000) — stop the fast-track UI
   while `serve` runs, or use `BC_UI_PORT`.
7. `config.py` is self-contained (paths from package location + env + `apps/.env` via
   python-dotenv); no legacy imports.
8. Tests in `apps/tests/`; pytest is dev-only: `pip install pytest` + new
   `apps/requirements-dev.txt` (do **not** add pytest to the runtime `requirements.txt`).
9. `BC_DB_FILE` env override on the DB path (default `apps/db/bc.db`) — needed for tests.

### Task list (ordered)

1. `apps/.venv/bin/pip install pytest`; create `apps/requirements-dev.txt` (pytest).
2. `apps/billcollector/__init__.py` — package doc, `__version__ = "0.1.0"`.
3. `apps/billcollector/config.py` — frozen dataclass `Config` + `load_config()`:
   `app_dir` (apps/), `db_file` (`BC_DB_FILE`), `data_dir` (`apps/data`, create
   `logs|displays|runs` subdirs), `profiles_dir` (`apps/browser/profiles`), `port`
   (`BC_UI_PORT`, 8000), `max_concurrency` (1), `display_start` (99),
   `pause_deadline_seconds` (1800), `ntfy_topic` (""), `git_commit_enabled` (False),
   `ui_base_url` (""); loads `apps/.env` first (existing convention).
4. `apps/billcollector/db.py`:
   - `SCHEMA_VERSION = 1`; `connect(db_file)` (WAL, `busy_timeout`, `row_factory`);
   - `init_db(cfg) -> import summary` — create tables (idempotent), run one-time import
     when the `ini_import` marker is absent, set `schema_version`;
    - `import_ini(conn, ini_path) -> count` — `configparser` with `optionxform=str`,
      `[Playwright]` section, `service = user1, user2, ...` → one Task per user,
      **empty value → one Task with `user = ""`** (legacy semantics,
      `BillCollector.py:188-193`), `INSERT OR IGNORE` (UNIQUE(service, user));
   - helpers: `get_setting`, `set_setting`, `list_tasks()`.
5. `apps/billcollector/cli.py` + `__main__.py` — argparse subcommands `serve` /
   `run <task_id> [--debug]`; `serve` = `load_config` → `init_db` (log import summary) →
   `ui.app.run_ui(cfg)`.
6. `apps/billcollector/ui/app.py` — placeholder page `/`: "BillCollector — daemon core
   (M1)", labels for DB path, task count (enabled/total), "Scheduler: not started",
   "UI pages: M2"; `app.on_startup`/`on_shutdown` hooks (startup re-checks DB, logs);
   `run_ui(cfg)` = `ui.run(port=cfg.port, host="0.0.0.0", title="BillCollector",
   show=False, reload=False)`. No auth in M1.
7. `apps/tests/conftest.py` (tmp DB via `BC_DB_FILE`, sys.path) + `test_db.py`:
   - schema: all 5 tables + `schema_version` created; `journal_mode == wal`
    - import: fixture ini (multi-user service + empty-user service `Svc=`) → one task per
      user, one task with `user = ""` for the empty-user service; correct `recipe_file`,
      `profile_dir` (no trailing underscore for `user = ""`), `enabled=0`, cron default,
      `status='idle'`
   - idempotency: second `init_db` imports 0, marker set
   - `UNIQUE(service, user)` enforced; `get_setting`/`set_setting` round-trip
8. `apps/tests/test_cli.py`: `run` unknown task → exit 1; known task (tmp DB) → exit 2 +
   "runner not implemented"; missing `task_id` → argparse exit 2; `serve --help` → exit 0.
9. Add `data/` to `.gitignore` for the M1 runtime dir `apps/data/` (`db/`, `browser/`,
   `Downloads`, `.bc_ui_run.json` are already covered by the M0 change).
10. Run the validation below; leave the working tree with new files only.

### Data model (Session 1 DDL — per the dashboard readiness clause below)

```sql
Task(id INTEGER PK, service TEXT, user TEXT, recipe_file TEXT, enabled INTEGER,
     cron TEXT, last_run TEXT, next_run TEXT, status TEXT, profile_dir TEXT,
     profile_reset_at TEXT, created_at TEXT, updated_at TEXT,
     UNIQUE(service, user));
Run(id INTEGER PK, task_id INTEGER, pid INTEGER, display INTEGER, novnc_port INTEGER,
     log_path TEXT, control_sock TEXT, started_at TEXT, ended_at TEXT, result TEXT,
     pause_reason TEXT, pause_deadline_at TEXT, notes TEXT);
PageStatus(id INTEGER PK, run_id INTEGER, step_number INTEGER, locator_action TEXT,
     interactive_elements TEXT, screenshot_path TEXT, error TEXT);
Download(id INTEGER PK, run_id INTEGER, task_id INTEGER, url TEXT, filename TEXT,
     size INTEGER, sha256 TEXT, saved_path TEXT, created_at TEXT, duplicate_of_id INTEGER);
Settings(key TEXT PRIMARY KEY, value TEXT);
```

Timestamps: ISO local, `timespec="seconds"`. `status` ∈ `idle/running/waiting/
finished/error/needs_attention`.

### Out of scope (Session 1)

Runner, orchestrator, scheduler, control socket, display/Xvfb, auth, any M2 page,
Docker/`.env` additions beyond reading, mock portal, edits to any legacy file
(`BillCollector.py`, `bc_ui.py`, `BillCollectorServices_pw.py`, `helpers/`, inis),
commits.

### Risks

- Port 8000 double-bind with `bc_ui.py` (see decision 6).
- WAL switch on the existing `bc.db`: persistent pragma, safe; legacy local runs
  coexist. NAS cron runs on a different machine — unaffected.
- Import runs against the real `bc.db` during the smoke test: creates only disabled
  tasks + 2 Settings rows; reversible by deleting the `ini_import` marker + `Task` rows.
- `nicegui` first import is slow — normal, not an error.

### Validation / exit criteria

1. `cd apps && .venv/bin/python -m pytest tests/ -v` — all green.
2. `cd apps && .venv/bin/python -m billcollector serve` → `http://localhost:8000` shows
   the placeholder with the real task count; `/_alive` → 200; SIGTERM → clean shutdown.
3. After first start: `bc.db` has **11 tasks** (winSIM ×5 + 6 empty-user services with
   `user = ''`), all `enabled=0`; `Settings` has `schema_version` + `ini_import`; a
   second `serve` logs "import skipped (already imported)".
4. Legacy untouched: `cd apps && .venv/bin/python BillCollector.py` → usage message;
   `git status` shows only the new files from the task list.

---

## Reference — GUI concept (all pages)

Stack per v2: NiceGUI on FastAPI/uvicorn, Python-only, event handlers (no REST).
Auth: single operator, session-cookie login, bcrypt, app-level middleware. Live data:
orchestrator stdout pump (per run) + `ui.timer` DB poll.

| Page | Concept |
|---|---|
| **Dashboard** | Operator's home page. Fully specified below. |
| **Task detail** | Per (service, user): run history, step results + screenshots, downloads, **profile reset** (session reset), live log, recipe shortcut |
| **Session view** | Copilot tab (screenshot + numbered overlays, click/fill, resume/cancel) + noVNC tab; interactive while `waiting`, read-only step screenshots while `running` (M3) |
| **Recipe editor** | YAML + step tree, `CheckRecipe` validation, save = write + validate + git commit; failure context (M3) |
| **Downloads** | Per-task dedup status, sha256, saved path |
| **Settings** | Password, ntfy topic, pause deadline, concurrency, git-commit toggle, download folder, display start |
| **Onboarding** | First-start wizard (M4) |

### Session model (precise definition)

- A **session** = the persistent Chromium profile directory
  `browser/profiles/<service>_<user>/` (Playwright `launch_persistent_context`
  `user_data_dir`), one per portal account, shared by all runs of that task.
- **Created** on the account's first run (including the `always_open_pdf_externally`
  `Preferences` write that `BillCollectorServices_pw.py:31-42` does today — but only at
  creation, not every run).
- **Never auto-deleted** (replaces the `shutil.rmtree` at `BillCollectorServices_pw.py:37-38`),
  **no `clear_cookies()`** (replaces `BillCollectorServices_pw.py:410`).
- **Resettable via UI** (task detail): delete profile dir, record
  `Task.profile_reset_at`, next run cold-starts.
- **Expiry handling (no heuristics):** if the portal logged the account out, recipe
  steps fail → 3 attempts → run `waiting` → operator re-logs-in via Copilot/noVNC →
  resume → session persists again.
- **Isolation:** profiles are never shared across accounts (the per-origin single-login
  state would otherwise overwrite sibling accounts' logins).

### Confirmed decisions (concept interview 2026-09-27)

1. Session granularity: **one persistent session per portal account (service, user)** —
   chosen over per-service so every account keeps its login (CAPTCHA/cookie-banner
   minimisation for all).
2. Dashboard rows are **per (service, user)** — 1:1 with the Task model and its sessions.
3. **Group convenience via filter** (service filter), not group rows.
4. **Two-pane dashboard**: task table on top, live log panel below.
5. **Row set**: service/user · status · last run · next run · session (facts only) ·
   last download (filename, truncated) · actions.
6. **No session-validity flag** — facts only; validity proven by a successful run or user
   interaction.
7. Build follows M1 → M2; no "dashboard-lite" on the legacy batch loop.

## Reference — Dashboard specification

### Layout

```
[toolbar]  service filter ▾   status filter ▾        [N waiting]  [Run (filtered)]
[table]    one row per (service, user) task
[log pane] live stdout + step progress of the selected run
```

### Task table

| Column | Content |
|---|---|
| Service / User | portal account |
| Status | `idle / running / waiting / finished / error / needs_attention`, color-coded, live |
| Last run | timestamp + result (success / failed step / stopped / needs_attention) |
| Next run | from task cron (`—` if disabled) |
| Session | profile present + **last used** date (+ last reset, if ever reset) — facts only |
| Last download | most recent filename for the task, **truncated** if long + date; `—` if none |
| Actions | **Run now** · **Stop** (only while running) · row click → task detail page |

- Sort: `running` / `waiting` rows first, then by service, user.
- `waiting` rows highlighted; toolbar badge counts them.

### Filters & group actions

- **Service filter:** `All` + one option per service (the "group" selector).
- **Status filter:** `All` + each status.
- **Run (filtered):** enqueues all **enabled** tasks in the filtered set; global
  semaphore (default 1) serializes — same behavior as today's per-service batch run.
- **Row Run now** works for disabled tasks too (manual one-off; schedule unchanged).
- **Stop:** SIGTERM the run's process group, escalate to SIGKILL after 10 s (same
  semantics as `bc_ui.py:stop_run`).

### Log pane

- Follows the **selected run**: default = currently running run (most recent, if
  several), else most recently finished run; selecting a row re-points the pane.
- Streams that run's subprocess stdout (orchestrator pump), capped (~2000 lines).
- **Step progress:** `step 4 of 12` from the run's `PageStatus` rows + current step name.
- `waiting` run: pause reason + deadline countdown + **Open session** button
  (→ session view at M3; → task detail until then).

### Live updates

- `ui.timer` (~2 s) DB poll: statuses, last/next run, waiting badge, session/last-
  download columns (WAL reads).
- Log lines pushed from the orchestrator pump to connected pages (fast-track `pages`
  broadcast pattern, `bc_ui.py:62-66`).

### Navigation

- Row click → **task detail** (history, step results, downloads, profile reset, recipe
  shortcut, live log). Waiting badge/row → **session view** (M3).

## Reference — M1/M2 impact on the v2 plan

- **Data model addition:** `Task.profile_reset_at` (in the Session 1 DDL above).
- **M1 exit criteria — dashboard-readiness clause:** M1 is not done until the dashboard
  can read everything it displays (Task/Run/Download/PageStatus rows per spec;
  per-task subprocess spawn/stop; per-run stdout stream; persistent per-task profile).
- **M2:** implement dashboard per spec; absorb `bc_ui.py` into
  `billcollector/ui/dashboard.py` (its `.bc_ui_run.json` orphan handling is superseded
  by the orchestrator's `Run.pid` startup cleanup); the `--service` flag becomes
  task-selection at the CLI, not the UI's run granularity.
- The v2 plan's "UI pages" dashboard line is superseded by this spec.

## Reference — Fast-track stopgap (`apps/bc_ui.py`)

Unchanged until M2. Known gaps vs. the concept: per-service rows (all users in one
process), no session state, no DB, single ini scope. It previews run/stop + live log.

## Reference — Out of scope (concept)

- Session-validity heuristics — by design
- Per-tick live browser frames (step-granular; noVNC is the real-time path)
- Multi-user / multi-tenancy
- "Dashboard-lite" on the legacy batch loop
- Any change to the v2 plan's scheduler, runner, or milestone ordering

## Reference — Validation (concept-level, later sessions)

- **M1 (foundation):** on the mock portal, two consecutive runs of the same account —
  the second shows the session was reused (no login step / no cookie banner); all
  dashboard-consumed DB rows exist per the readiness clause.
- **M2 (NiceGUI pytest, `nicegui.testing`):** table renders one row per (service, user);
  service filter narrows to the group; Run (filtered) enqueues N runs and serializes;
  log pane follows the running run with step progress; Stop kills the process group;
  last-download column shows the newest filename truncated; disabled task accepts row
  Run now; row click navigates.
- **E2E (mock portal):** run → idle → running → finished; second run reuses the session;
  forced expiry → `waiting` + badge → Copilot re-login → resume → finished.
