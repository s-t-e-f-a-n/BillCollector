# BillCollector — Daemon, NiceGUI Web UI & Interactive Sessions (v2)

Supersedes `.kilo/plans/1790289661685-billcollector-daemon-webui-plan.md`. Goal unchanged:
turn the cron batch job into a 24/7 daemon whose web UI is its window — recipe-driven task
management, interactive stepping into scraping sessions (CAPTCHAs, cookie banners, recipe
repair), and easier adoption for other users (one instance per operator, DMS-agnostic
document workflow).

Three refinements vs. v1:
1. **UI stack: NiceGUI** (on FastAPI/uvicorn) instead of Jinja2+htmx — no SPA/Node
   toolchain, Python stays the only language, and the hard parts of this UI (live
   dashboard, live screenshots, log streaming) are NiceGUI's native patterns.
2. **Decoupled processes:** the UI process is a pure orchestrator. Each task run is an
   isolated `python -m billcollector run <task_id>` **subprocess** running the **existing
   sync Playwright** code — no async port, zero crash propagation (a Playwright OOM never
   takes down the UI/scheduler), and full OS-level memory reclamation after every run.
3. **Dependency baseline (checked 2026-09-25):** Python 3.12 everywhere (image already
   on 3.12; dev environment migrates to Ubuntu 24.04 in M0). Direct pins:
   `nicegui==3.17.1`, `playwright==1.63.0`, `apscheduler==3.11.3`, `bcrypt==5.0.0`.

## Current state (facts from the code)

- Batch: cron → `BillCollector.sh` → `docker run` → `python3 BillCollector.py <ini> [debug]`
- Playwright is hardcoded (`BillCollector.py:255`); the Selenium half is dead code
- `BillCollectorServices_pw.py` is **fully synchronous**: `retrieve_from_service_with_playwright(
  service, url, user, pwd, otp, debug)`, `process_step`, `PageState.set_interactive_elements(page)`,
  `DatabaseManager` (table-per-run `PageStatus_<service>_RunN`)
- Config: `bc_default.ini` / `bc_test.ini` — `[Playwright]` lines `service=user1, user2`
  (e.g. `winSIM=Stefan, Auto, Brigitte, Eva, Anna`); recipes as YAML in
  `recipes_playwright/` validated by `helpers/BillCollectorCheckRecipe.py` +
  `recipe-pw-schema.yaml`
- Credentials: Vaultwarden, name-based link (`f"{service} {user}".strip()` → vault item)
- State: SQLite `bc.db`; Playwright profile deleted + cookies cleared every run
  (`BillCollectorServices_pw.py:35`, `:405`) → cold start every run
- Image (`Dockerfile_pw`): ubuntu 24.04, Python 3.12, Playwright 1.48.0, **xvfb already
  installed**, non-root user block commented out, `CMD ["/bin/bash"]`
- Dev environment: Ubuntu 20.04 (WSL2) host, system Python 3.8.10; `apps/.venv` created
  by `install_local.sh playwright` from the **system** `python3` (script targets 20.04
  apt package names). No CI (`.github` holds only issue templates).
- `requirements.txt` is a full `pip freeze`; actual direct imports: playwright,
  PyYAML, jsonschema, requests, python-dotenv, nslookup, flatten-json, sshkeyboard
  (SPACE-pause helper); `dotenv==0.9.9` (legacy package, unused) and `websocket-client`
  (no import found) are stale entries
- Debug: VS Code F5 → `bc_test.ini` + SPACE pauses

## Library state (verified on PyPI, 2026-09-25)

| Package | Latest | requires_python | Notes |
|---|---|---|---|
| NiceGUI | 3.17.1 | `>=3.10,<4` | UI framework; FastAPI/uvicorn underneath |
| Playwright | 1.63.0 | `>=3.10` | bundles Chromium 153.0.8010.12; current pin 1.48.0 |
| APScheduler | 3.11.3 | `>=3.8` | 3.x is the current stable line; SQLAlchemy jobstore |
| FastAPI | 0.141.1 | `>=3.10` | NiceGUI dependency |
| uvicorn | 0.54.0 | `>=3.10` | NiceGUI dependency |
| bcrypt | 5.0.0 | `>=3.8` | UI password hashing |

Consequences:
- The modern web stack requires **Python >=3.10** — the 3.8 dev environment is a dead
  end (3.8 has been EOL since Oct 2024). The image (ubuntu 24.04, Python 3.12) already
  matches the target baseline.
- **APScheduler 3.x** (3.11.3) is the current stable line → the "APScheduler 3.x +
  SQLAlchemy jobstore" decision stands.
- Playwright 1.48 → 1.63 spans 15 minor releases: the image must be rebuilt with a fresh
  `playwright install chromium` (Chromium 153).

## Decisions

1. **Daemon** = one long-running process: `python -m billcollector serve` (NiceGUI on
   uvicorn) hosting UI + scheduler + orchestrator. Cron retired in M4.
2. **Process isolation:** the orchestrator spawns each task run as a subprocess
   (`asyncio.create_subprocess_exec`), monitoring it and streaming its stdout to the UI
   (`ui.log`) and to a per-run log file. The UI never imports scraping code.
3. **Sync Playwright stays.** The runner refactors the existing sync logic from
   `BillCollectorServices_pw.py` — no async port (v1's "async port fidelity" risk is
   eliminated). Job lifecycle is async in the UI layer only.
4. **UI stack:** NiceGUI (FastAPI + uvicorn underneath). No Jinja2, no htmx, no custom
   REST API — UI actions run as NiceGUI event handlers. Health = NiceGUI's built-in
   `/_alive`.
5. **Auth:** single operator per instance (confirmed). Session cookie login; bcrypt hash
   in the DB `settings` table, optionally seeded from `.env` on first start, changeable in
   Settings. "User" in this system always means **portal account** (the service+user pair),
   never a login identity. No multi-user/multi-tenancy.
6. **Task** = one `(Service, User)` pair (today: one ini line). Carries: recipe file
   reference, enabled flag, cron schedule, last/next run, status, profile directory.
7. **Source of truth:** redesigned SQLite DB, one-time ini import. **Recipes stay as YAML
   files on disk** (`recipes_playwright/`), git-versioned. Recipes are per-service
   (`recipe-pw__<service>.yaml`), shared by all tasks of that service — the UI makes this
   explicit. Vaultwarden link stays name-based.
8. **Daemon git:** recipe changes made in the UI are auto-committed (toggleable).
9. **Persistent browser profile per task** (`browser/profiles/<service>_<user>/`): never
   auto-deleted, no `clear_cookies()`, resettable via UI. Minimizes cookie banners /
   CAPTCHAs. (This is the per-portal-account isolation; it replaces the expert's
   per-login-identity directories.)
10. **Interaction in paused sessions, two levels:**
    - **Copilot (primary):** live screenshot + numbered element overlays (reusing
      `PageState.set_interactive_elements`); click/fill executed by the runner on demand.
    - **noVNC (fallback):** per-run Xvfb + x11vnc + websockify; noVNC web client embedded
      in the UI via `ui.html` iframe; full mouse/keyboard (drag-and-drop CAPTCHAs).
11. **Pause triggers:** a step fails 3× → status `waiting`; explicit recipe method
    `wait_user(prompt)` for known friction points. **No** CAPTCHA heuristics.
12. **Waiting session:** held 30 min (configurable), then aborted as `needs_attention`;
    profile preserved, manual retry possible.
13. **Notification:** UI badge (live element updates / `ui.timer`) + ntfy push on pauses.
14. **Downloads:** existing folder drop stays (DMS-agnostic) + DB tracking
    (service, task, timestamp, filename, size, sha256) + per-task sha256 dedup +
    post-download hook (`consumers/`, initially empty) executed **inside the runner
    subprocess**.
15. **Concurrency:** default max 1 parallel task (NAS hardware), configurable.
16. **Headful always:** every run's browser targets a virtual display allocated per run
    (file-lock registry, starting at `:99`), started and reaped with the run. noVNC is
    therefore available for any session — running or waiting.
17. **UI language:** English.
18. **Python baseline 3.12 everywhere:** image already 3.12 (ubuntu 24.04); dev
    environment migrates to Ubuntu 24.04 (WSL2/VM) in M0 and `.venv` is rebuilt from the
    system `python3` (3.12). Direct deps pinned, transitive deps regenerated as a full
    freeze.

## Target architecture

```
[serve process — 24/7, NiceGUI on uvicorn]
  [NiceGUI pages]  [auth middleware]  [live logs: ui.log]
  [Scheduler (APScheduler, persistent jobstore)]
  [Orchestrator: task locks (DB row), global semaphore,
   create_subprocess_exec, stdout→log file+ui.log, exit handling]
        │ spawns, one subprocess per run
[runner subprocess: python -m billcollector run <task_id>  (sync Playwright)]
  [Xvfb :N + x11vnc + websockify — child processes, reaped on exit]
  [step loop / pause loop]  [control socket (unix, JSON)]  [PageState]
  [Vaultwarden] [downloads+dedup+hook] [git committer]
        │
[SQLite WAL bc.db: Task / Run / PageStatus / Download / Settings]  ← shared state bus
```

### Process & IPC design

- **serve process:** `ui.run(port=8000, on_startup=..., on_shutdown=...)`. Startup:
  start APScheduler, kill orphaned runner subprocesses (from `Run.pid`), mark leftover
  `running`/`waiting` runs `interrupted`. Shutdown (SIGTERM): terminate child runners,
  mark their runs `interrupted`.
- **Orchestration (per scheduled or manual run):**
  1. Task enabled? → DB row lock: `UPDATE Task SET status='running' WHERE id=? AND
     status NOT IN ('running','waiting')` (0 rows → skip); global semaphore (default 1).
  2. Allocate display `N` (lockfile registry `<data>/displays/:N.lock`); websockify port
     = `6080 + (N - display_start)`.
  3. `INSERT Run (pid, display, novnc_port, log_path, control_sock, ...)`; spawn
     `python3 -m billcollector run <task_id>` (env inherited: `VAULT_HOST`, `BW_API_URL`, ...).
  4. Stream stdout line-by-line → append to `<data>/logs/run-<id>.log` + push to
     registered `ui.log` elements (page registers on connect, unregisters on disconnect).
  5. On exit: finalize `Run` (result from DB status / exit code; non-zero → `error`,
     traceback tail into `Run.notes`).
- **Runner control socket** (Copilot channel): unix socket at
  `<data>/run-<run_id>.sock`, JSON-line protocol, served by the runner's **main thread
  while in the waiting loop** (between steps, so sync Playwright calls are safe there):
  - `screenshot` → base64 PNG · `elements` → numbered interactive elements (existing
    `PageState.set_interactive_elements` logic) · `click {n}` · `fill {n, text}` ·
    `resume` · `cancel`
  - The UI opens a short-lived connection per request; a `ui.timer` polls
    `screenshot`/`elements` while the session page is open.
- **Running-session live view:** the runner saves a step screenshot to
  `<data>/runs/<run_id>/step_<n>.png` after each step (also the M3 failure-context
  evidence). The UI shows the latest file, refreshed by `ui.timer` (~3 s). This is
  coarser than v1's per-tick WebSocket view — accepted semantic change; full real-time
  control is what noVNC provides.
- **noVNC:** the runner spawns `Xvfb :N`, `x11vnc -display :N -rfbport 5900+N
  -rfbauth <pw file>` (password from settings, per-run file) and `websockify 6080+N
  127.0.0.1:5900+N` as children; all reaped in `finally`. UI iframe:
  `ui.html('<iframe src="http://<host>:6080+N/vnc.html?autoconnect=true" ...>')`.

### Code layout

New Python package `apps/billcollector/`:
- `__main__.py` / `cli.py` — `serve`, `run <task_id> [--debug]` (debug = wait for
  input() before each step; the new F5 workflow)
- `config.py` (`.env` + settings), `db.py` (SQLite WAL, migrations, all tables)
- `scheduler.py` (APScheduler AsyncIOScheduler, persistent jobstore in `bc.db`)
- `orchestrator.py` (spawn/monitor, stdout streaming, semaphore, locks, orphan cleanup)
- `runner.py` (sync step loop refactored from `BillCollectorServices_pw.py`; pause loop +
  control socket; display allocation; step screenshots) + `pagestate.py` (extracted
  `PageState` + element scan)
- `control.py` (control-socket protocol: server side in runner, client helper for UI/tests)
- `vault.py` (timeouts, retries, clean TOTP handling), `downloads.py` (tracking, dedup,
  hook), `notify.py` (ntfy), `gitcommit.py`
- `ui/` — `app.py` (ui.run, startup/shutdown, middleware), `auth.py` (login page + session
  check), `dashboard.py`, `tasks.py`, `task_detail.py`, `session.py` (Copilot + noVNC
  tabs), `recipes.py`, `downloads.py`, `settings.py`, `onboarding.py`
- `consumers/` (post-download hook slot, empty)

The legacy `BillCollector.py` batch path keeps its current sync Playwright until M4 and
reuses shared `vault.py` / `downloads.py` instead of its own copies (from M0/M1).
`tests/` (pytest) + `tests/mock_portal/` (from M1).

### Data model (SQLite, WAL, busy_timeout set; short writes only)

- `Task(id, service, user, recipe_file, enabled, cron, last_run, next_run, status,
  profile_dir, created_at, updated_at)`
- `Run(id, task_id, pid, display, novnc_port, log_path, control_sock, started_at,
  ended_at, result, pause_reason, pause_deadline_at, notes)`
- `PageStatus(id, run_id, step_number, locator_action, interactive_elements,
  screenshot_path, error)` — **one** table, replacing table-per-run
- `Download(id, run_id, task_id, url, filename, size, sha256, saved_path, created_at,
  duplicate_of_id NULL)`
- `Settings(key TEXT PRIMARY KEY, value TEXT)` — UI password hash, ntfy topic, pause
  deadline, concurrency, git-commit toggle, download folder, `UI_BASE_URL`,
  `display_start` (all runtime-overridable in the UI)
- Writers: orchestrator (Task/Run lifecycle), runner (Run status, PageStatus, Download),
  UI (Task CRUD, Settings). No long cross-process transactions.
- Migration: one-time import of `[Playwright]` sections of `bc_default.ini` /
  `bc_test.ini` → tasks (default: monthly, **disabled until confirmed in the UI**), on
  first daemon start (M1). Legacy tables left as-is (runtime status, not archive).

### Recipe schema extension

- New method `wait_user(prompt)`: pauses the task with a user-visible prompt in the UI.
  Method-chain format otherwise unchanged; `recipe-pw-schema.yaml` extended; `CheckRecipe`
  continues to validate. After resume the current step re-executes from the beginning
  (a `wait_user` step that immediately re-pauses is acceptable by design).

### Execution flow

1. Scheduler (per-task cron) → task enabled? → DB row lock + global semaphore
2. Orchestrator: allocate display, spawn runner subprocess, create `Run` row
3. Runner: start Xvfb + x11vnc + websockify children; `launch_persistent_context(
   user_data_dir=<task profile>)`, headful on `DISPLAY=:N`
4. Execute recipe steps; each step → `PageStatus` row + step screenshot file (reusing
   `PageState` logic); failure → up to 3 attempts (existing per-step timeout)
5. Pause: `Run.status=waiting` + `pause_deadline_at`, ntfy push, UI badge; enter waiting
   loop (service control socket until deadline)
6. User interacts: Copilot (screenshot, element click, fill) or noVNC (full control)
   → `resume` → loop re-executes the current step
7. Deadline exceeded: close context, `needs_attention`, profile preserved
8. Download: track (sha256), dedupe per task (hash already present → skip,
   `duplicate_of_id`), call post-download hook
9. Finalize: `Run.result`, reap display children; orchestrator records exit status
10. Recipe changed via UI → write YAML → schema validation → git commit

### UI pages (NiceGUI)

> The dashboard is specified in detail (and is the GUI concept focus) in
> `.kilo/plans/1790468502492-gui-concept-dashboard-spec.md` — it supersedes the
> dashboard line below.

- **Login:** `@ui.page('/login')`; app-level HTTP middleware on the NiceGUI app
  (Starlette `SessionMiddleware`) redirects all pages except login/static/`/_alive`;
  bcrypt check against `Settings.ui_password_hash`
- **Dashboard:** `ui.table` of tasks (status, last/next run) + "N waiting" badge via
  live element updates / `ui.timer` DB poll
- **Task detail:** create (service, user, recipe, schedule), enable/disable, run now,
  profile reset, history, per-run step results (`PageStatus` + step screenshots),
  downloads, live run log (`ui.log`)
- **Session view:** Copilot tab (`ui.image` with base64 src + absolutely-positioned
  numbered overlay divs via `ui.element`; action bar: element select/fill, resume,
  cancel) · noVNC tab (`ui.html` iframe). Interactive only while `waiting`;
  `running` = read-only latest step screenshot
- **Recipe editor:** `ui.editor` (CodeMirror) YAML + step-tree view + validation via
  `CheckRecipe`; save = file write + validation + git commit. On failed step: failure
  context (screenshot at failure, expected locator, candidate elements → pick/edit →
  save → commit)
- **Downloads** (dedup status) · **Settings** (password, ntfy topic, pause deadline,
  concurrency, git-commit toggle, download folder, display start) · **Onboarding**

### Docker / deployment

- Image `billcollector:latest` becomes long-running: `CMD ["python3", "-m",
  "billcollector", "serve"]`; **non-root user enabled** (M0), adds `git`, `x11vnc`,
  `websockify`, noVNC web client (apt `novnc`) in M1
- Volumes: `Downloads`, `db` (+ `data/` for logs, displays, run artifacts),
  `browser/profiles`, git repo (recipes + commits), `.env`
- Ports: 8000 (UI) + websockify range `6080..6080+max_concurrency-1` — both via NPM with
  HTTPS; per-display path routing (`/novnc/<display>/` → `127.0.0.1:6080+N`)
- Config: `apps/.env` (existing `VAULT_HOST`, `BW_API_URL`) + new vars (`UI_BASE_URL`,
  ntfy topic, pause deadline, concurrency, git-commit toggle, optional UI password seed,
  session secret); runtime-overridable settings in the `Settings` table
- `BillCollector.sh` + cron stay operational until M4

## Milestones

> **Fast track (2026-09-26):** a minimal manual start/stop UI is being delivered before
> M1, as a carve-out: `.kilo/plans/1790465908381-nicegui-manual-run-ui.md` — one
> standalone `apps/bc_ui.py` (subprocess supervisor for `BillCollector.py`) plus an
> additive `--service` flag on the batch entry point. It previews M2's "run now"
> behavior; when M1/M2 land, `bc_ui.py` is absorbed into `billcollector/ui/` and the
> `--service` filter becomes the runner's task selection.

### M0 — Stabilize the batch system + modernize dependencies (cron keeps running)

0. **Host & dependency refresh (prerequisite; 0.1 is a user host operation)**
   1. *(user)* Migrate the dev environment to **Ubuntu 24.04** (WSL2:
      `wsl --install -d Ubuntu-24.04`, or a VM). Copy repo + runtime data over
      (`apps/db`, `apps/Downloads`, `apps/browser`, `apps/recipes_playwright`, `.env`).
      Note: Ubuntu 20.04 is EOL.
   2. `install_local.sh`: drop the selenium branch; update the apt dep list to 24.04
      names (align with `Dockerfile_pw`: `libasound2t64`, `fonts-unifont`,
      `fonts-ubuntu`); venv keeps being created from the system `python3` (3.12 on
      24.04).
   3. Rewrite `requirements.txt` with direct pins: `playwright==1.63.0` plus PyYAML,
      jsonschema, requests, python-dotenv, nslookup, flatten-json, sshkeyboard (latest),
      and new `nicegui==3.17.1`, `apscheduler==3.11.3`, `bcrypt==5.0.0`, `sqlalchemy`;
      remove `selenium`, stale `dotenv==0.9.9`, unused `websocket-client`; regenerate
      the full freeze (`pip freeze`) on 3.12.
   4. Recreate `apps/.venv`; `PLAYWRIGHT_BROWSERS_PATH=$(pwd)/browser playwright install
      chromium ffmpeg` (Chromium 153).
   5. Verify the batch path on the new pins: production cron run, F5 debug
      (`bc_test.ini`), `BillCollectorCheckRecipe.py` over all recipes (Playwright
      1.48 → 1.63 drift check).
1. Remove the Selenium half (code side): `BillCollectorServices.py`,
   `recipes_selenium/`, `chrome-linux64*`/`chromedriver-linux64*`, `[Selenium]` ini
   sections, `test_selenium.py` (requirements/Dockerfile side done in 0.3)
2. Error propagation: a failed step aborts the run (respecting `graceful`), result
   recorded in the DB
3. Vaultwarden client: timeouts + 3× retry; replace the "No TOTP" magic string
   (`BillCollector.py:89`) with status handling
4. flock against duplicate runs (`apps/.bc.lock`)
5. `logging` module instead of the `print = logging.debug` hack; `RotatingFileHandler`
   for `bc.log` **plus plain stdout** (stdout is what M1 streams to the UI); remove the
   `os.chdir` side effect. **No DB schema change in M0.**
6. Docker: enable the non-root user (bind-mount ownership for Downloads/db/profiles);
   rebuild the image with the new requirements

**Exit:** cron run completes unchanged on Python 3.12 + Playwright 1.63; a broken step
is visible in log + DB as an abort; a double start is rejected.

### M0 step 0 — Manual execution guide (host + Python environment)

Steps to be executed by hand (verified against the old dev host on 2026-09-25:
Windows 11 25H2 — `wsl --install` works without elevation; WSL2; default distro
`ubuntu` = 20.04.6; no local crontab — the production cron runs on the remote NAS).
The old 20.04 distro is left untouched the whole time; the new environment is
purely additive.

**0.1 — Install the Ubuntu 24.04 WSL distro** (Windows PowerShell)

```powershell
# Catalog name on this machine is "Ubuntu" (= Ubuntu 24.04 LTS from the
# Microsoft Store). "Ubuntu-24.04" is NOT a valid catalog name here (verified).
wsl --install -d Ubuntu --no-launch

# First boot: create the user (keep the same name as before, e.g. "stefan")
wsl -d Ubuntu

# Verify: must show VERSION="24.04" (Noble)
wsl -d Ubuntu cat /etc/os-release
```

If `Ubuntu` ever resolved to 22.04 instead, install the Store app
"Ubuntu 24.04" manually.

**0.1b — Copy repo + runtime data** (inside the new distro)

```bash
sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip git
python3 --version            # expect Python 3.12.x (system python3 on 24.04)
mkdir -p ~/projects
cp -a /mnt/wsl/ubuntu/home/stefan/projects/BillCollector ~/projects/
cd ~/projects/BillCollector
rm -rf apps/.venv apps/__pycache__ apps/helpers/__pycache__
```

Notes:
- Keep the path `/home/stefan/projects/BillCollector` — the recipe `$schema`
  lines contain this absolute path.
- The copy includes the current uncommitted working-tree changes
  (`doc/TODO.txt`, `doc/BillCollector.drawio`, `install_docker-image.sh`,
  `.kilo/`, `.vscode/settings.json`) — they move along with the repo.
- `apps/browser/profile` + `profile.ref` are copied; the old
  `chromium-1140` / `ffmpeg-1010` browser dirs belong to Playwright 1.48 and can
  be deleted once the new ones are installed.
- Point VS Code at the new distro (WSL integration) and select `apps/.venv` as
  the interpreter for the F5 workflow.

**0.2 — `install_local.sh`** (in the new distro)

- Delete the `install_selenium()` function and the `selenium` branch of the
  final dispatch (usage becomes `bash install_local.sh playwright`).
- In `install_playwright()`'s apt list, replace the 20.04 package names with
  the 24.04 names (align with `Dockerfile_pw`):
  - `libasound2` → `libasound2t64`
  - `ttf-unifont` → `fonts-unifont`
  - `ttf-ubuntu-font-family` → `fonts-ubuntu`
- Header comment: "tested on Ubuntu 20.04 LTS and WSL2" → "tested on Ubuntu
  24.04 LTS and WSL2".
- The venv is still created from the system `python3` (3.12 on 24.04) — no
  change.

**0.3 — `requirements.txt`** (in the new distro)

Replace the file with these direct pins:

```
playwright==1.63.0
nicegui==3.17.1
apscheduler==3.11.3
bcrypt==5.0.0
sqlalchemy
PyYAML
jsonschema
requests
python-dotenv
nslookup
flatten-json
sshkeyboard
```

(Removed vs. today: `selenium`, stale `dotenv==0.9.9`, unused `websocket-client`;
their transitive deps drop out automatically in step 0.4.)

**0.4 — Recreate the venv + Playwright browsers** (in the new distro)

```bash
cd ~/projects/BillCollector/apps
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
PLAYWRIGHT_BROWSERS_PATH=$(pwd)/browser .venv/bin/playwright install chromium ffmpeg
.venv/bin/pip freeze > requirements.txt    # full freeze on 3.12
```

Installs Chromium 153 (new `browser/chromium-*` dir); afterwards the old
`chromium-1140` / `ffmpeg-1010` dirs can be deleted.

**0.5 — Verify the batch path**

```bash
cd ~/projects/BillCollector/apps
.venv/bin/python --version                        # 3.12.x
.venv/bin/playwright --version                    # 1.63.0
for f in recipes_playwright/recipe-pw__*.yaml; do
    .venv/bin/python helpers/BillCollectorCheckRecipe.py "$f" || echo "FAILED: $f"
done                                              # all 7 recipes must pass
```

- F5 debug (`bc_test.ini`, SPACE pauses) from VS Code on the new distro — hits
  the real portals, so time it deliberately (Playwright 1.48 → 1.63 drift check).
- Production cron (remote NAS): rebuild the image with the new requirements
  (`deploy_remote.sh` or `install_docker-image.sh playwright` on the NAS), then
  the next monthly cron run must complete unchanged.

**Cleanup (after everything is verified):** the old distro `ubuntu` (20.04) can
be removed from Windows: `wsl --unregister ubuntu` — destructive (deletes its
ext4 volume), only after the new environment works and all runtime data is
safely over.

### M1 — Daemon core (no UI pages yet — CLI + control socket only)

1. NiceGUI app skeleton (`serve`, port 8000, startup/shutdown hooks); extend `.env`
   config (`nicegui==3.17.1`, `apscheduler==3.11.3`, `bcrypt==5.0.0` already installed
   via M0 step 0.3)
2. DB redesign (Task/Run/PageStatus/Download/Settings, WAL) + one-time ini import
3. Runner: sync Playwright logic refactored from `BillCollectorServices_pw.py`; pausable
   (control socket), persistent per-task profile, no profile deletion / cookie clears;
   step screenshots; display allocation + Xvfb/x11vnc/websockify child management
   (image apt deps `git`, `x11vnc`, `websockify`, `novnc` added with this milestone)
4. Orchestrator + APScheduler: per-task cron, persistent jobstore, global semaphore
   (default 1), DB row locks; stdout streaming to log file
5. Pause triggers (3× failure, `wait_user`) + 30-min hold + ntfy push + DB status
6. Download tracking + deduplication + post-download hook
7. CLI: `python -m billcollector serve` / `python -m billcollector run <task_id>`;
   legacy `BillCollector.py` stays the batch entry point until M4

**Exit:** daemon runs tasks on schedule; on the mock portal: pause → ntfy → resume via
control-socket test client → download tracked; profile accumulation verifiable (cookie
banner only on the 1st run).

### M2 — UI core

1. Login + session cookie (bcrypt), auth middleware
2. Dashboard: task table + "N waiting" badge
3. Task management: create, enable/disable, run now, profile reset, history, downloads,
   live log (`ui.log`)
4. Recipe editor: YAML + step tree + validation via `CheckRecipe`; save = file write +
   validation + git commit
5. Downloads page, settings page, ini import

**Exit:** full task lifecycle operable from the UI against the mock portal; recipe
edit → save → validation → git commit works.

### M3 — Interactive sessions

1. Copilot UI on the control socket: live screenshot + numbered overlays, click/fill,
   resume; read-only running view (step screenshots)
2. noVNC: per-run display stack (already in M1 image deps), embedded noVNC iframe on
   the session page
3. Failure context in the recipe editor: step screenshot, expected locator, candidate
   elements → pick/edit → save (→ git commit)
4. `wait_user` method in schema + runner
5. Git auto-commit structured messages: `recipe(<service>): <summary>`

**Exit (mock portal, E2E):** cookie banner → Copilot click; CAPTCHA code typed via
Copilot; drag CAPTCHA via noVNC; recipe repair after a "changed website" → changed YAML +
commit visible in `git log`.

### M4 — Adoption for other users

1. Onboarding wizard (first start: set password, vault config, ini import, first task)
2. Docker Compose package (BillCollector, optional ntfy)
3. README/docs: daemon mode, UI usage, recipe authoring, cron→daemon migration; new F5
   debug workflow (`python -m billcollector run <task_id> --debug`)
4. Mark `BillCollector.sh` / cron as deprecated

**Exit:** a new user sets up the stack from the docs and collects a document from the
mock portal — without shell access to the daemon.

## Validation

- **M0:** production cron run; F5 debug (`bc_test.ini`); `BillCollectorCheckRecipe.py`
  over all remaining recipes
- **M1:** pytest (DB migration/import, orchestrator spawn/kill/orphan-cleanup, runner
  pause/resume via control-socket client, Vaultwarden client); integration test against
  the mock portal (headful under Xvfb)
- **M2:** NiceGUI built-in pytest UI tests (`nicegui.testing`: `Screen`/`User`) for login,
  task CRUD, recipe save; schema tests incl. `wait_user`
- **M3:** E2E on the mock portal: Copilot flows (banner, code entry), noVNC flow (drag),
  recipe repair + `git log` check
- **Mock portal:** `tests/mock_portal/` — small **FastAPI** app (separate fixture,
  unaffected by the NiceGUI choice): cookie banner, login, fake CAPTCHA (displayed
  6-digit code), drag-and-drop CAPTCHA, document download

## Risks

- **Playwright 1.48 → 1.63 drift (batch path):** sync API is stable, but 15 minor
  releases — verify in M0 step 0.5 (cron + F5 + CheckRecipe) before any runner work.
- **Dev OS migration (M0):** 20.04 → 24.04 means copying runtime data
  (db/Downloads/browser/.env) and re-downloading the Playwright browsers; do it before
  any M0 code work. 20.04 is EOL — staying on it is not an option.
- **Subprocess lifecycle:** orphan runners after `kill -9` of the serve process →
  startup cleanup via `Run.pid`; display leaks → `finally` in runner + startup cleanup;
  zombies → reaped by the asyncio transport.
- **SQLite multi-writer:** WAL + busy_timeout; writers split by table (see data model);
  keep writes short.
- **Control-socket protocol correctness:** covered by M1 integration tests (pause →
  screenshot → click → resume → completion on the mock portal).
- **Live-view granularity:** running sessions show step-granular screenshots, not
  per-tick frames — documented UX behavior; noVNC is the real-time path.
- **Chrome/Xvfb + persistent profiles:** pin Playwright/Chromium versions in the image.
- **NAS resources:** concurrency default 1; profiles open only for running tasks; one
  Xvfb display per session; `ui.log` buffer capped (full log in the file).
- **Git auto-commit:** repo as bind mount, single user → conflicts unlikely; toggle.
- **Vaultwarden API:** "No TOTP" text matching replaced in M0; status checks idempotent.
- **CAPTCHA detection:** no heuristics by design — only `wait_user` + auto-pause after
  3× failure. No "CAPTCHAs are solved automatically" promise in the docs.
- **Non-root switch (M0):** bind-mount ownership (Downloads, db, profiles, data) must be
  adjusted for the new user.

## Out of scope

- Multi-user / multi-tenancy (single login per instance — confirmed; expert's
  per-login-identity directories rejected; per-portal-account isolation is the
  per-task browser profile)
- Custom REST/external API surface (UI-only; health via built-in `/_alive`)
- E-mail / SMTP notification
- Paperless REST API upload (post-download hook only; later consumer)
- `playwright codegen` in the UI (stays a VS Code dev workflow)
