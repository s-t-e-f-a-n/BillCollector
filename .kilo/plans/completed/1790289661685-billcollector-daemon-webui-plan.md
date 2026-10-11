# BillCollector — Daemon, Web UI & Interactive Sessions

> Status: SUPERSEDED by 1790364274061-billcollector-nicegui-daemon-plan.md (v2).

## Goal

Transform BillCollector from a cron batch job into a 24/7 daemon with a web UI as its
"window": recipe-driven tasks are managed in the UI, the user can interactively step into
scraping sessions (CAPTCHAs, cookie banners, recipe repair after website changes), and the
system becomes easier for other users to adopt (onboarding, packaging, DMS-agnostic
document workflow for systems like Paperless-NGX).

## Current state (facts from the code)

- Batch: cron → `BillCollector.sh` → `docker run` → `python3 BillCollector.py <ini> [debug]`
- Playwright is hardcoded (`BillCollector.py:255`); the Selenium half is dead code
- Config: `bc_default.ini` / `bc_test.ini` (service + user list), recipes as YAML in
  `recipes_playwright/` validated with jsonschema (`recipe-pw-schema.yaml`)
- Credentials: Vaultwarden (Bitwarden API), name-based link (`Service User` → vault item)
- State: SQLite `bc.db` — one table `PageStatus_<service>_RunN` per run (unbounded growth)
- The Playwright profile is deleted and cookies cleared on every run
  (`BillCollectorServices_pw.py:35` `shutil.rmtree`, `:405` `clear_cookies()`) →
  every run is a cold start (cookie banners, CAPTCHAs on every run)
- Recipe authoring: `playwright codegen` + translation to YAML
  (`helpers/BillCollectorCreateRecipe_pw.py`)
- Debug: VS Code F5 on `BillCollector.py` → automatically `bc_test.ini` + SPACE pauses
- Recipe steps are method chains (locator methods + `click`/`fill`/`goto`/`expect_download`),
  variables `{{USERNAME}}`/`{{PASSWORD}}`/`{{OTP}}`

## Decisions

1. **Daemon (24/7)** with an internal scheduler; the UI is the window to the daemon.
   Cron is retired in M4.
2. **Stack:** FastAPI (uvicorn) + Jinja2 + htmx. No SPA/Node toolchain. Python stays the
   only language.
3. **Auth:** single user, session cookie, UI behind the existing NPM proxy with HTTPS.
   The UI password is stored in the DB `settings` table (bcrypt hash), optionally seeded
   from `.env` on first start and changeable later via onboarding/settings (no `.env` edit).
   No Vaultwarden SSO.
4. **Task** = one `(Service, User)` pair (today: one ini line). Carries: recipe file
   reference, enabled flag, cron schedule, last/next run, status, profile directory.
5. **Source of truth:** redesigned SQLite DB. One-time import of the ini files.
   **Recipes stay as YAML files on disk** (`recipes_playwright/`), actively versioned in git.
   Vaultwarden link stays name-based.
6. **Daemon git:** recipe changes made in the UI are auto-committed (`git add` + `commit`,
   structured message, toggleable in settings).
7. **Persistent browser profile per task** (`browser/profiles/<service>_<user>/`):
   never deleted automatically, no `clear_cookies()`, resettable via UI.
   Goal: minimize cookie banners and CAPTCHA prompts.
8. **Interaction in paused sessions, two levels:**
   - **Copilot (primary):** live screenshot + numbered element overlays (reusing the
     `PageState.set_interactive_elements` logic); click/fill executed via API by the daemon.
   - **noVNC (fallback):** Xvfb + x11vnc + websockify in the image, noVNC embedded in the UI;
     full mouse/keyboard control (e.g. drag-and-drop CAPTCHAs).
9. **Pause triggers:** a step fails 3× → status `waiting`; explicit recipe method
   `wait_user(prompt)` for known friction points. **No** CAPTCHA heuristics (deliberate).
10. **Waiting session:** held for 30 min (configurable), then aborted as `needs_attention`;
    profile is preserved, manual retry possible.
11. **Notification:** UI badge (polling/WebSocket) + ntfy push on pauses. E-mail: out of scope.
12. **Downloads:** existing folder drop stays (DMS-agnostic) + DB tracking
    (service, task, timestamp, filename, size, sha256) + deduplication (same hash)
    + post-download hook (later Paperless API consumer, without core changes).
13. **Concurrency:** default max 1 parallel task (NAS hardware), configurable.
14. **UI language:** English (public project).
15. **Test fixture:** local mock portal (cookie banner, login, fake CAPTCHA with a displayed
    code, drag CAPTCHA, document download) for M1–M3.
16. **Headful always:** every task browser runs under Xvfb (virtual display). noVNC is
    therefore available for any session — running or waiting. Copilot screenshots stay
    Playwright-native (`page.screenshot()`).

## Target architecture

```
[Scheduler (APScheduler, persistent jobstore)]
        │
[Task queue (global semaphore, per-task locks)]
        │
[TaskRunner (Playwright, pausable)]  ←→  [Waiting sessions (in memory)]
        │                                            │
[Vaultwarden client]  [Download tracker]      [Copilot API / WebSocket]
        │                                            │
[SQLite: Task/Run/PageStatus/Download]      [noVNC (Xvfb + x11vnc)]
        │
[FastAPI + htmx UI]        [ntfy client]      [Git committer]
```

### Code layout

- New Python package `apps/billcollector/` (daemon core):
  - `cli.py` / `__main__.py` (`serve`, `run <task>`)
  - `config.py` (`.env` + settings), `db.py` (SQLite WAL, migrations, Task/Run/PageStatus/Download)
  - `scheduler.py` (APScheduler, persistent jobstore)
  - `runner.py` (pausable task runner, Playwright, per-task profiles) +
    `pagestate.py` (element scan logic extracted from `BillCollectorServices_pw.py`)
  - `vault.py` (Vaultwarden client: timeouts, retries, clean TOTP handling)
  - `downloads.py` (tracking, dedup, post-download hook), `notify.py` (ntfy), `gitcommit.py`
  - `api/` (FastAPI routes), `web/` (Jinja templates + htmx + static), `consumers/` (hook slot, empty)
- The step-execution logic in `BillCollectorServices_pw.py`
  (`transform_step_to_json`, `process_step`, `PageState`) is **ported to async** in
  `billcollector/runner.py` / `pagestate.py` for the daemon. The legacy `BillCollector.py`
  batch path keeps its current sync Playwright until M4 and reuses the shared `vault.py` /
  `downloads.py` modules instead of its own copies.
- `tests/` (pytest) + `tests/mock_portal/` (mock portal, from M1)

### Data model (SQLite, WAL mode, daemon = sole writer)

- `Task(id, service, user, recipe_file, enabled, cron, last_run, next_run, status, profile_dir, created_at, updated_at)`
- `Run(id, task_id, started_at, ended_at, result, pause_reason, notes)`
- `PageStatus(id, run_id, step_number, locator_action, interactive_elements, error)` —
  **one** table, replacing the table-per-run structure
- `Download(id, run_id, task_id, url, filename, size, sha256, saved_path, created_at, duplicate_of_id NULL)`
- `Settings(key TEXT PRIMARY KEY, value TEXT)` — UI password hash, ntfy topic, pause
  deadline, concurrency, git-commit toggle, download folder, `UI_BASE_URL`
  (all overridable at runtime in the UI)
- Migration: one-time import of `bc_default.ini` / `bc_test.ini` (section `[Playwright]`) →
  tasks (default: monthly, disabled until confirmed in the UI), performed on first daemon
  start (M1). The legacy `Service` / `PageStatus_*` tables are left as-is (the DB is runtime
  status, not an archive).

### Recipe schema extension

- New method `wait_user(prompt)`: pauses the task with a user-visible prompt in the UI.
- The method-chain format otherwise stays unchanged; `recipe-pw-schema.yaml` is extended
  with the method; `CheckRecipe` continues to validate.
- **Recipes are per-service (shared):** a recipe file is keyed by service
  (`recipe-pw__<service>.yaml`) and shared by all tasks of that service (same portal flow,
  different credentials). Editing a recipe in the UI affects every task of that service;
  the UI must make this explicit.

### Execution flow

1. Scheduler (per-task cron) → task enabled? → task lock + global semaphore
2. `launch_persistent_context(user_data_dir=<task profile>)` under Xvfb — profile reset only via UI
3. Execute recipe steps; each step → `PageStatus` row (reusing the `PageState` logic
   from `BillCollectorServices_pw.py`)
4. Step failure: up to 3 attempts (existing per-step timeout) → then pause
5. Pause: DB status `waiting` + session kept in memory, ntfy push, UI badge, 30-min deadline
6. User interacts: Copilot (screenshot, element click, text entry) or noVNC (full control)
   → "Resume"
7. Deadline exceeded: close session, status `needs_attention`, profile preserved
8. Download: track (sha256), dedupe (hash already present for the task → skip,
   set `duplicate_of_id`), call post-download hook
9. Finalize run (result in DB); recipe changed via UI → write YAML, schema validation, git commit

### Runner & pause mechanism

- The **daemon** runner uses **async Playwright** (`async_playwright`); each task run is an
  asyncio task. (The M0 batch path keeps today's sync Playwright unchanged.)
- A run is a step loop. Between steps it checks a per-run `asyncio.Event`:
  - **Pause** = set status `waiting`, keep the browser context + page alive, then
    `await pause_event.wait(timeout=<pause deadline>)`.
  - **Resume** = the API handler sets `pause_event`; the loop re-executes the failed step
    from the beginning.
  - **Timeout** = `wait()` returns at the deadline; the run closes the context and sets
    `needs_attention`.
- **Copilot actions** (click/fill) are executed directly by the async API on the shared live
  context (`await locator.click()` / `await locator.fill()`) — safe because everything runs
  on the single asyncio event loop. Screenshots are `await page.screenshot()` per WebSocket tick.
- **noVNC** is independent: it drives the Xvfb display directly (x11vnc), not via Playwright.
- **Xvfb display allocation:** one virtual display per concurrent session (e.g. `:99`, `:100`),
  started/stopped with the session.

### Edge cases & semantics

- **Daemon restart during a run:** all `running` / `waiting` runs are marked `interrupted`
  at startup (manual retry via UI; browser profile preserved).
- **Pause granularity:** pause happens **between** steps. After resume, the current step is
  re-executed from the beginning (never mid-step). User interaction while `waiting` does not
  advance the step.
- **Copilot view:** running session = read-only live view; interactive (click/fill/resume)
  only in status `waiting` — prevents races between step execution and user input.
- **Deduplication:** permanent per task by sha256 (repeat run with the same document → skip,
  set `duplicate_of_id`); no time window.
- **Post-download hook:** simple callback interface in the `consumers/` package
  (`consume(download, task)`), initially empty — no plugin system.
- **Git commit:** only the changed recipe file is committed; identity from the existing git
  config, fallback `BillCollector Daemon <daemon@billcollector.local>`; git failure → warning
  in the log, the file write is not rolled back.
- **ntfy:** title `BillCollector: <service> <user> waiting`, body = reason + UI link
  (new env var `UI_BASE_URL`).
- **noVNC security:** x11vnc with password (`-rfbauth`) + NPM host with HTTPS/basic auth.
- **Python versions:** image target 3.12 (Ubuntu 24.04); code must also run in the local
  dev venv (3.8) → prefer 3.8-compatible version pins (APScheduler 3.x, pydantic v2).
- **Vault item name:** stays `f"{service} {user}".strip()` (current behavior); a task with an
  empty user → name = service.

### API (FastAPI)

- `/api/auth/login`, `/api/auth/logout`, `/api/health`
- `/api/tasks` (CRUD), `/api/tasks/{id}/run`, `/api/tasks/{id}/reset-profile`,
  `/api/tasks/{id}/runs`, `/api/tasks/{id}/downloads`
- `/api/recipes` (list/detail), `/api/recipes/{name}` (GET/PUT with schema validation)
- `/api/sessions` (waiting sessions), `/api/sessions/{run_id}/screenshot`,
  `/api/sessions/{run_id}/elements`, `/api/sessions/{run_id}/click`,
  `/api/sessions/{run_id}/fill`, `/api/sessions/{run_id}/resume`,
  `/api/sessions/{run_id}/cancel`
- `/api/downloads`, `/api/settings`, `/api/config/import-ini`
- WebSocket: session live view (screenshot + elements on change), dashboard badge

### UI pages

Login · Dashboard (task table: status, last/next run, waiting badge) ·
Task detail (history, per-run step results from `PageStatus`, downloads, actions) ·
Session view (Copilot: screenshot + overlays + action bar; noVNC tab) · Recipe editor
(YAML + step tree + validation; on failed step: failure context with candidate elements) ·
Downloads (dedup status) ·
Settings (password, ntfy topic, pause deadline, concurrency, git-commit toggle, download folder) ·
Onboarding

### Docker / deployment

- Image `billcollector:latest` becomes a long-running service (uvicorn; plus Xvfb, x11vnc,
  websockify, `git` for auto-commits; **non-root user**)
- Volumes: `Downloads`, `db`, `browser/profiles`, git repo (recipes + commits), `.env`
- Ports: 8000 (UI) + noVNC (websockify) — both via NPM with HTTPS
- Config: the daemon reads `apps/.env` (existing `VAULT_HOST`, `BW_API_URL`) plus new vars
  (`UI_BASE_URL`, ntfy topic, pause deadline, concurrency, git-commit toggle, optional
  UI password seed); runtime-overridable settings live in the `settings` table
- `BillCollector.sh` + cron stay operational until M4 (M0 stabilizes them)

## Milestones

### M0 — Stabilize the batch system (cron keeps running during development)

1. Remove the Selenium half: `BillCollectorServices.py`, `recipes_selenium/`,
   `chrome-linux64*` / `chromedriver-linux64*` (repo + Dockerfile), `[Selenium]` sections
   from `bc_default.ini` / `bc_test.ini`, `selenium` from `requirements.txt`, `test_selenium.py`
2. Error propagation: a failed step aborts the run (respecting the `graceful` flag),
   result recorded in the DB instead of silently continuing
3. Vaultwarden client: timeouts + retry (3×) for all API calls; replace the "No TOTP"
   magic string (`BillCollector.py:89`) with proper status handling
4. flock against duplicate runs (lock file `apps/.bc.lock`)
5. `logging` module instead of the `print = logging.debug` hack; `RotatingFileHandler`
   for `bc.log`; remove the `os.chdir` side effect in `latest_download_file()` (absolute paths).
   **No DB schema change in M0** — the batch path keeps writing to the existing
   table-per-run structure unchanged; the single-table `PageStatus` redesign lands in M1's `db.py`.
6. Docker: enable the non-root user (Dockerfile, commented-out block)

**Exit:** the existing cron run completes unchanged; a deliberately broken step is visible
in log + DB as an abort; a double start is rejected.

### M1 — Daemon core

1. FastAPI app skeleton (uvicorn); extend `.env` config (optional UI password seed, ntfy
   topic, pause deadline, concurrency, git-commit toggle, `UI_BASE_URL`)
2. DB redesign (Task/Run/PageStatus/Download, WAL) + one-time ini import
3. TaskRunner: Playwright logic refactored from `BillCollectorServices_pw.py`, pausable
   (pause/resume API), persistent per-task profile, no profile deletion / cookie clears
4. APScheduler: per-task cron, persistent jobstore, global semaphore (default 1),
   per-task locks
5. Pause triggers (3× failure, `wait_user`) + 30-min hold + ntfy push + DB status
6. Download tracking + deduplication + post-download hook
7. CLI: `python -m billcollector serve` / `python -m billcollector run <task>`;
   the legacy `BillCollector.py` stays the batch entry point until M4

**Exit:** the daemon runs tasks on schedule; on the mock portal: pause → ntfy → resume →
download tracked; profile accumulation verifiable (cookie banner appears only on the 1st run).

### M2 — UI core

1. Login + session cookie (bcrypt)
2. Dashboard: task table (status, last/next run, "N waiting" badge via WebSocket/polling)
3. Task management: create (service, user, recipe, schedule), enable/disable, run now,
   profile reset, history, downloads
4. Recipe editor: YAML editor + step-tree view + validation via `CheckRecipe`;
   save = file write + validation + git commit
5. Downloads page (dedup status), settings page, ini import

**Exit:** the full task lifecycle is operable from the UI against the mock portal;
recipe edit → save → validation → git commit works.

### M3 — Interactive sessions

1. Copilot: WebSocket live view (screenshot + numbered element overlays from the
   `PageState` logic), click/fill actions, resume
2. noVNC: Xvfb + x11vnc + websockify in the image, embedded noVNC view on the session page
3. Failure context in the recipe editor: screenshot at failure time, expected locator,
   candidate elements → pick/edit → save (→ git commit)
4. Git auto-commit on recipe changes (structured message: `recipe(<service>): <summary>`)
5. `wait_user` method in schema + runner

**Exit (mock portal, E2E):** cookie banner → Copilot click; CAPTCHA code typed via Copilot;
drag CAPTCHA via noVNC; recipe repair after a "changed website" → changed YAML +
commit visible in `git log`.

### M4 — Adoption for other users

1. Onboarding wizard (first start: set password, vault config, ini import, create first task)
2. Docker Compose package (BillCollector, optional ntfy)
3. README/docs update: daemon mode, UI usage, recipe authoring; cron→daemon migration guide
4. Mark `BillCollector.sh` / cron as deprecated

**Exit:** a new user sets up the stack from the docs and collects a document from the mock
portal — without shell access to the daemon.

## Validation

- **M0:** production cron run; debug via F5 (`bc_test.ini`); `BillCollectorCheckRecipe.py`
  over all remaining recipes
- **M1:** pytest (DB migration/import, scheduler, Vaultwarden client, pause/resume);
  integration test against the mock portal (headful under Xvfb)
- **M2:** Playwright UI tests (login, task CRUD, recipe save); schema tests incl. `wait_user`
- **M3:** E2E on the mock portal: Copilot flows (banner, code entry), noVNC flow (drag),
  recipe repair + `git log` check
- **Mock portal:** `tests/mock_portal/` — small FastAPI app: cookie banner, login,
  fake CAPTCHA (displayed 6-digit code), drag-and-drop CAPTCHA, document download

## Risks

- **CAPTCHA detection:** no heuristics by design — only `wait_user` + auto-pause after 3×
  failure. No "CAPTCHAs are solved automatically" promise in the docs.
- **SQLite concurrency:** WAL + daemon as sole writer; UI is read-mostly.
- **Chrome/Xvfb + persistent profiles:** pin Playwright/Chromium versions in the image.
- **Async port fidelity:** porting `process_step` to async must preserve current semantics —
  `VARIABLE_MAP` placeholder substitution, nested `expect_download` blocks, `first()`
  chaining, per-step `PageStatus` recording. Verify against the mock portal that the async
  runner behaves identically to the batch path.
- **NAS resources:** concurrency default 1; profiles open only for running tasks;
  one Xvfb display per session.
- **Git auto-commit:** repo as bind mount, single user → conflicts unlikely; toggle in settings.
- **Vaultwarden API:** the fragile "No TOTP" text matching is replaced in M0; status checks
  stay idempotent.
- **Non-root switch (M0):** bind-mount ownership (Downloads, db, profiles) must be adjusted
  for the new user.

## Out of scope

- E-mail / SMTP notification (later optional add-on)
- Paperless REST API upload (post-download hook only; later consumer)
- Multi-user / multi-tenancy (single user per instance)
- `playwright codegen` in the UI (advanced; stays a VS Code dev workflow)
