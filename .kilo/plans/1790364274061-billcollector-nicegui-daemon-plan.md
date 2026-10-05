# BillCollector — Daemon, NiceGUI Web UI & Interactive Sessions (v3)

Supersedes `.kilo/plans/1790289661685-billcollector-daemon-webui-plan.md`.
Goal (sharpened in v3): turn the cron batch job into a 24/7 daemon whose web UI is its
window — recipe-driven task management, interactive stepping into scraping sessions,
and easier adoption for other users (one instance per operator, DMS-agnostic document
workflow).

**User-friendliness objective (v3):** the daemon makes BillCollector as easy to operate
as possible: the robot does the routine work, and at every friction point it stops with
a clear "here is what happened — here is what you need to do" screen that a human
resolves from the browser (desktop or phone) — no shell access, no YAML needed for the
common case.

**First development wave (v3):** the three current complicating circumstances, each
supported by human interaction within the daemon + web UI environment:
1. websites often change their DOM and the path to the documents' download area,
2. sudden ads or cookie-request forms jump into the way of the user / BillCollector,
3. CAPTCHAs are difficult to circumvent for a robot like BillCollector.
The architecture must stay open for future ML / LLM-based AI support to automate tasks —
**human interaction is still required** (human-in-the-loop is a permanent design gate,
see "Intervention architecture"). AI implementation itself is out of Wave 1 scope.

Refinements vs. v2:
1. **Wave 1 framing** — M1+M2+M3, with the three friction flows as acceptance criteria
   (the mock portal's Layer B sites are the acceptance fixture, delivered in v0.4).
2. **Intervention architecture** — every pause carries a machine-readable context and is
   resolved through a stable, versioned action protocol. The web UI is the first client;
   a future AI assistant is a second client of the same protocol, gated by human approval.
3. **Corrections & additions** — `wait_user` resume semantics (v2's "re-pause is
   acceptable" was a trap; now: complete-on-resume + optional `until` verification
   locator, the AI-friendliest variant); the 3× step retry is explicitly new runner
   behavior (the batch engine has no retry); the element scan gains bounding boxes
   (needed for the overlay + the AI context); the protocol gains `context` / `press` /
   `drag` actions; ntfy pushes carry a deep link to the session page.

Carried over from v1/v2 (unchanged):
- **UI stack: NiceGUI** (on FastAPI/uvicorn) instead of Jinja2+htmx — no SPA/Node
  toolchain, Python stays the only language, and the hard parts of this UI (live
  dashboard, live screenshots, log streaming) are NiceGUI's native patterns.
- **Decoupled processes:** the UI process is a pure orchestrator. Each task run is an
  isolated `python -m billcollector run <task_id>` **subprocess** running the **existing
  sync Playwright** code — no async port, zero crash propagation (a Playwright OOM never
  takes down the UI/scheduler), and full OS-level memory reclamation after every run.
- **Dependency baseline (checked 2026-09-25):** Python 3.12 everywhere (image already
  on 3.12; dev environment migrates to Ubuntu 24.04 in M0). Direct pins:
  `nicegui==3.17.1`, `playwright==1.63.0`, `apscheduler==3.11.3`, `bcrypt==5.0.0`.

## Current state (facts from the code)

- Batch: cron → `BillCollector.sh` → `docker run` → `python3 BillCollector.py <ini> [debug]`
- Playwright is the only automation path (`BillCollector.py:255`); the Selenium half
  was removed in M0
- `BillCollectorServices_pw.py` is **fully synchronous**: `retrieve_from_service_with_playwright(
  service, url, user, pwd, otp, debug)`, `process_step`, `PageState.set_interactive_elements(page)`,
  `DatabaseManager` (table-per-run `PageStatus_<service>_RunN`)
- Config: `bc_default.ini` / `bc_test.ini` — `[Playwright]` lines `service=user1, user2`
  (e.g. `winSIM=Stefan, Auto, Brigitte, Eva, Anna`); recipes as YAML in
  `recipes_playwright/` validated by `helpers/BillCollectorCheckRecipe.py` +
  `recipe-pw-schema.yaml`
- Credentials: Vaultwarden, name-based link (`f"{service} {user}".strip()` → vault item)
- State: SQLite `bc.db`; Playwright profile deleted + cookies cleared every run
  (`BillCollectorServices_pw.py:46`, `:434`) → cold start every run
- Image (`Dockerfile`): ubuntu 24.04, Python 3.12, **xvfb already installed**,
  **non-root user (UID/GID 1000) in the Dockerfile**, `CMD ["/bin/bash"]`; the
  deployed NAS image was rebuilt from the current requirements on 2026-10-05
  (Playwright 1.63.0) — M0 item 6 done
- Dev environment: Ubuntu 24.04 (WSL2) host, system Python 3.12 (migrated in M0 step 0
  — see M0 status below); `apps/.venv` created by `install_local.sh playwright` from
  the **system** `python3` (24.04 apt package names). No CI (`.github` holds only issue
  templates).
- `requirements.txt` is a full `pip freeze` regenerated on 3.12 (M0 step 0.4): direct
  pins playwright 1.63.0, nicegui 3.17.1, apscheduler 3.11.3, bcrypt 5.0.0, sqlalchemy
  plus PyYAML, jsonschema, requests, python-dotenv, nslookup, flatten-json, sshkeyboard
  (SPACE-pause helper); `selenium`, stale `dotenv`, unused `websocket-client` removed
- Debug: VS Code F5 → `bc_test.ini` + SPACE pauses
- **Batch engine has no retry:** a failed step aborts the run on the first failure
  (`fail_step` in `BillCollectorServices_pw.py:592-599`); the 3×-retry-then-pause is
  **new daemon-runner behavior**, not existing
- **Element scan has no coordinates:** `PageState.set_interactive_elements`
  (`BillCollectorServices_pw.py:179-380`) returns role/name/candidate-locator per
  element but **no bounding boxes** — the Copilot overlay and the machine-readable
  pause context both need `getBoundingClientRect()` added
- **Regression environment delivered (v0.4):** `tests/` — mock portal (FastAPI, port
  8787) with Layer A sites (happy/graceful/badlogin/empty/dlfail) and **Layer B
  friction sites** (`waituser`: displayed 6-digit code · `captchadrag`: slider ·
  `autopause`: "I am not a robot" interstitial), `POST /admin/<site>/mutate|reset` for
  the "changed website" drill; Layer B recipes
  (`recipe-pw__testwaituser|testcaptchadrag|testautopause.yaml`) use the `wait_user`
  method (free-form schema — already validates); `tests/scenarios.py` = single source
  of truth. Layer B execution is deferred to the daemon runner = **Wave 1**. See
  `.kilo/plans/1790714158680-local-regression-test-web-service.md` (DELIVERED, all
  validation green incl. vault e2e)
- **Fast-track manual run UI delivered:** `apps/bc_ui.py` — minimal NiceGUI subprocess
  supervisor (start/stop + live log); absorbed into `billcollector/ui/` in M2

## Library state (verified on PyPI, 2026-09-25)

| Package | Latest | requires_python | Notes |
|---|---|---|---|
| NiceGUI | 3.17.1 | `>=3.10,<4` | UI framework; FastAPI/uvicorn underneath |
| Playwright | 1.63.0 | `>=3.10` | bundles Chromium 153.0.8010.12; requirements pin 1.63.0, deployed NAS image still 1.48.0 |
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

## Wave 1 — objective and acceptance

**Scope:** M1 (daemon core) + M2 (UI core) + M3 (interactive sessions). M0 is
done (status below); M4 (adoption for other users) is the follow-up wave.
Wave 1's focus is the three current complicating circumstances, each made operable by a
human from the web UI:

| # | Friction | How Wave 1 handles it (human interaction) |
|---|---|---|
| 1 | Site changed its DOM / path to the download area | The step's locator fails → 3 attempts → pause with **failure context** (screenshot at failure, expected locator, candidate elements). **One-off:** human clicks the real element (Copilot) or navigates (noVNC) → resume → run finishes. **Permanent (repair):** from the pause, the recipe step is fixed — pick a candidate element or edit the step, validate, save, git commit → the next run passes unattended. |
| 2 | Sudden ads / cookie-request forms in the way | **Prevention:** persistent per-task profile → banner only on the 1st run (known banners can additionally be encoded as `graceful` steps, the existing pattern). **Reaction:** the overlay blocks the expected step → same pause flow; the overlay is visible in the screenshot; human dismisses it (Copilot click or noVNC) → resume. No auto-dismiss heuristics. |
| 3 | CAPTCHAs | **No detection heuristics** — three explicit paths: (a) displayed code: recipe `wait_user(prompt)` → pause → human reads the code from the screenshot, types it via Copilot `fill` (or noVNC), presses Verify on the page → resume (optional `until` check verifies). (b) drag/slider: `wait_user(prompt)` → human drags via Copilot `drag` or noVNC → resume. (c) unknown challenge: the 3×-failure **auto-pause** is the generic safety net — the human sees the challenge in the screenshot and acts. |

**AI-readiness (Wave 1 scope line):** Wave 1 implements the **architecture, not the AI**:
a stable versioned intervention protocol, a machine-readable pause context, and the
human-approval gate (below). No ML/LLM code, no model calls, no API keys. A future
assistant plugs in as a **second client of the same protocol**; its actions are
*proposals* the operator approves in the UI before the runner executes them — human
interaction stays required by construction, not by convention.

**Acceptance (all on the mock portal, Layer B — the delivered fixture):**
1. `testautopause`: 3× step failure → `waiting` + ntfy (deep link) → human clicks "I am
   not a robot" via Copilot → resume → step re-executes → download tracked.
2. `testwaituser`: `wait_user` pause with prompt → human types the displayed 6-digit code
   via Copilot `fill` + clicks "Verify" on the page → resume → download.
3. `testcaptchadrag`: `wait_user` pause → human drags the slider via Copilot `drag` or
   noVNC → resume → download.
4. Persistent profile: `testhappy` run 1 shows the banner (graceful step succeeds); run 2
   (same task) has the banner absent; login re-runs (session cookie expired).
5. Download dedup: two `testhappy` runs → run 2's downloads deduped by sha256.
6. "Changed website" drill: `POST /admin/happy/mutate` renames "Log in" → run pauses at
   the login step with failure context → repair in the recipe UI (candidate picker or
   YAML) → validate + save + git commit (visible in `git log`) → re-run succeeds →
   `POST /admin/happy/reset`.

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
    - **Copilot (primary):** live screenshot + numbered element overlays positioned by
      bounding boxes (reusing `PageState.set_interactive_elements`, extended — see
      "Current state"); click/fill/press/drag executed by the runner on demand;
      mobile-first (the phone is a first-class intervention device).
    - **noVNC (fallback):** per-run Xvfb + x11vnc + websockify; noVNC web client embedded
      in the UI via `ui.html` iframe; full mouse/keyboard for anything Copilot cannot
      express.
11. **Pause triggers:** a step fails 3× → status `waiting`; explicit recipe method
    `wait_user(prompt[, until])` for known friction points. **No** CAPTCHA heuristics.
    The 3× retry is new runner behavior (the batch engine aborts on first failure):
    the runner re-executes the step's method chain up to 3 times — `expect_download`
    nested steps included — before pausing.
12. **Waiting session:** held 30 min (configurable), then aborted as `needs_attention`;
    profile preserved, manual retry possible.
13. **Notification:** UI badge (live element updates / `ui.timer`) + ntfy push on pauses,
    with a **deep link** to the session page (`<UI_BASE_URL>/runs/<run_id>`) — the
    operator can act from a phone without opening the dashboard first.
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
19. **`wait_user` resume semantics (v3 correction, user-confirmed):** on resume the
    `wait_user` step **completes** (it is consumed, not re-executed — v2's "re-pause is
    acceptable" would trap the operator, since a consumed CAPTCHA code cannot be
    re-entered). Optional `until` locator argument: before completing, the runner polls
    the page for that locator, bounded by the pause deadline; found → complete,
    deadline exceeded → re-pause with the same prompt. Without `until`: complete
    immediately; subsequent recipe steps verify the action (failure there pauses again
    with fresh context). This is the most AI-friendliest variant: the `until` check is
    the objective "did the action work" signal that future AI proposals will be checked
    against.
20. **Intervention protocol + pause context are a stable, versioned contract** — the
    mechanism that keeps the architecture open for future ML/LLM support (see
    "Intervention architecture"). The runner is client-agnostic: it executes explicit
    action requests; Wave 1 has exactly one client (the human web UI). No AI code in
    Wave 1.
21. **Operator reach:** every pause pushes ntfy with the session deep link (decision 13);
    the Copilot session view is mobile-first; the candidate-element recipe repair is the
    primary no-YAML fix path.

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
    `PageState.set_interactive_elements` logic **+ bounding boxes**) · `context` → full
    machine-readable pause payload (below) · `click {n}` · `fill {n, text}` ·
    `press {key}` · `drag {n, dx, dy}` (relative mouse drag from element n — slider
    CAPTCHAs on the phone path) · `resume` · `cancel`
  - The UI opens a short-lived connection per request; a `ui.timer` polls
    `screenshot`/`elements` while the session page is open.
- **Protocol versioning:** the first JSON field of every message is `v` (starts at 1).
  The protocol is the AI-integration contract — changes need a version bump and a doc
  update (`doc/`), and the `context` payload must stay complete and small enough to ship
  over a socket.

### Intervention architecture (human-in-the-loop, AI-open)

Every friction point is an **intervention**: the runner gets stuck, persists a
structured pause with machine-readable context, and yields into the waiting loop. The
intervention is resolved by explicit actions and a final `resume`. In Wave 1 the only
action source is the human via the web UI (Copilot / noVNC). The architecture is built
so a future ML/LLM assistant becomes a **second action source without touching the
runner**:

1. **Stable intervention protocol** — the control-socket JSON protocol above:
   versioned, documented, client-agnostic.
2. **Machine-readable pause context** — the `context` response; also persisted in
   `Run.pause_context` per pause. This is exactly the input an LLM/ML system would
   consume:
   - `reason` ∈ `step_failed | wait_user | download_failed`
   - `prompt` (human-readable; from `wait_user` or generated from the step description)
   - `url`, `page_title`, `error`
   - `step` (the failing step's JSON: description, locator chain, actions)
   - `screenshot` (path + base64)
   - `elements[]` — numbered: `role`, `name`, `rect {x, y, w, h}` (bounding box),
     candidate `locator`, `actionTypes`, optional `url`
   - `page_text` — visible page text, truncated (≈20 KB)
   - `deadline_at`
3. **Human-in-the-loop is a permanent gate.** The runner executes only explicit action
   requests from a client; the protocol has no "auto" mode. Wave 1: all actions
   originate from the human UI. Future (out of scope): an assistant may *propose*
   actions or recipe edits; proposals surface in the UI and execute only after the
   operator approves — the runner's execution path is identical either way. The
   `wait_user` `until` check (decision 19) is the objective "did it work" signal that
   makes such proposals checkable.
4. **No heuristics, no AI in Wave 1** — the runner never detects CAPTCHAs or banners
   and never calls a model. Openness is concrete and testable: protocol + context
   contract + approval gate, all exercised by the Wave 1 E2E scenarios.

The element scan (`PageState.set_interactive_elements`) gains **bounding boxes**
(`getBoundingClientRect`) in Wave 1 — required for overlay placement and for the
context's `rect` fields; the scan's existing role/name/locator-candidate logic is
reused unchanged.
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
  ended_at, result, pause_reason, pause_prompt, pause_context, pause_deadline_at,
  notes)` — `pause_context` = the machine-readable intervention context JSON (see
  "Intervention architecture"). Note: the dashboard-spec Session 1 DDL
  (`1790468502492-gui-concept-dashboard-spec.md`, not yet implemented) gains these two
  columns when that session runs.
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

### Recipe schema extension — `wait_user`

- New method `wait_user(prompt)` with an optional second argument `until` (a locator
  argument in the same shape as the other locator methods, e.g.
  `{"role": "link", "name": "My account"}`):
  - **Pause:** the runner pauses with the operator-visible prompt (UI banner + ntfy push
    with deep link).
  - **Resume semantics (decision 19):** the `wait_user` step **completes** on resume —
    it is consumed, not re-executed.
  - **With `until`:** before completing, the runner polls the page for the locator,
    bounded by the pause deadline. Found → step completes (objective success check for
    the human's — and later the AI's — action). Deadline exceeded → the pause repeats
    with the same prompt.
  - **Without `until`:** completes immediately on resume; subsequent recipe steps verify
    the action (a failed verification fails 3× and pauses again with fresh context).
- Method-chain format otherwise unchanged. The schema **stays free-form** (`method` is a
  string — `wait_user` already validates today; no method enum, keeping future methods
  trivial). `CheckRecipe` continues to validate; the known methods are documented in the
  recipe-authoring docs (M4).

### Execution flow

1. Scheduler (per-task cron) → task enabled? → DB row lock + global semaphore
2. Orchestrator: allocate display, spawn runner subprocess, create `Run` row
3. Runner: start Xvfb + x11vnc + websockify children; `launch_persistent_context(
   user_data_dir=<task profile>)`, headful on `DISPLAY=:N`
4. Execute recipe steps; each step → `PageStatus` row + step screenshot file (reusing
   `PageState` logic); failure → up to 3 attempts (existing per-step timeout)
5. Pause: `Run.status=waiting` + `pause_prompt` + `pause_context` (machine-readable,
   see "Intervention architecture") + `pause_deadline_at`; ntfy push with session deep
   link; UI badge; enter waiting loop (serve the control socket until deadline)
6. User interacts: Copilot (screenshot, element click/fill/press/drag) or noVNC (full
   control) → `resume` → failed step: re-executed from the beginning; `wait_user` step:
   completed (with the `until` check when present)
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
- **Session view** (the core user-friendliness page): layout = **"what to do" first**
  (pause prompt banner), then the screenshot with numbered overlays positioned by
  bounding boxes, then the action bar (element select → click/fill/press/drag, resume,
  cancel). Mobile-first: the Copilot tab works on a phone (screenshot + tap-to-act) —
  the ntfy deep link lands here. noVNC tab (`ui.html` iframe) = full mouse/keyboard
  fallback. Interactive while `waiting`; `running` = read-only latest step screenshot +
  noVNC observation. "Repair recipe" button on failure pauses → recipe editor with the
  failure context preloaded
- **Recipe editor:** `ui.editor` (CodeMirror) YAML + step-tree view + validation via
  `CheckRecipe`; save = file write + validation + git commit. On failed step: failure
  context (screenshot at failure, expected locator, candidate elements) — the
  **candidate picker (no YAML required) is the primary repair path**; raw YAML editing
  is the advanced path. After saving a repair: "run now" is one click away
- **Downloads** (dedup status) · **Settings** (password, ntfy topic, pause deadline,
  concurrency, git-commit toggle, download folder, display start) · **Onboarding**

### Docker / deployment

- Image `billcollector:latest` becomes long-running: `CMD ["python3", "-m",
  "billcollector", "serve"]`; **non-root user enabled** (M0, done: UID/GID 1000 in
  the `Dockerfile`); adds `git`, `x11vnc`, `websockify`, noVNC web client (apt
  `novnc`) in M1 (pending)
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
       names (align with `Dockerfile`: `libasound2t64`, `fonts-unifont`,
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

**Status (verified against the repo 2026-09-29; NAS deploy verified 2026-10-05):**

- **Step 0 (host + dependencies) — done.** Dev host is Ubuntu 24.04.5 / Python 3.12.3;
  `install_local.sh` updated (selenium branch removed, 24.04 apt names, header updated);
  `requirements.txt` is a full freeze on 3.12 (`playwright==1.63.0`, `nicegui==3.17.1`,
  `apscheduler==3.11.3`, `bcrypt==5.0.0`, `sqlalchemy`; selenium/dotenv/websocket-client
  removed); venv recreated on 3.12; Playwright 1.63.0 + Chromium (browser dir
  `chromium-1243`) + ffmpeg installed, old 1.48 browser dirs deleted. `CheckRecipe`
  passes all 7 recipes on the new pins (verified 2026-09-29).
- **Items 1–5 — done** (commits `bf5669c`, `c30be69`, `fce5c65`, `2c6c7a1`): selenium
  code removed; logging module with `RotatingFileHandler` for `bc.log` plus plain stdout
  (no `os.chdir` side effect); Vaultwarden timeouts + 3× retry, "No TOTP" magic string
  replaced with status handling; flock duplicate-run guard in `BillCollector.py` +
  `BillCollector.sh`; error propagation — a failed service/user pair aborts only that
  pair's run, remaining services continue, the service run is always finalized in the DB,
  and the process exits 1 if any pair failed.
- **Item 6 (Docker) — done.** Non-root user (UID/GID 1000) + single `Dockerfile`
  landed (legacy Selenium Dockerfile removed, `Dockerfile_pw` renamed); NAS image
  rebuilt + mount ownership verified on the 2026-10-05 NAS deploy
  (`deploy_remote.sh` → `install_docker-image.sh`, production checks green).
- **Step 0.5 verification — partial.** CheckRecipe: 7/7 pass. Production run on the
  NAS: green on the rebuilt image (2026-10-05 deploy). F5 debug (`bc_test.ini`) on
  the new distro: not yet run (hits the real portals — optional drift check).
- **Exit criteria:** "double start is rejected" implemented (flock); "a broken step is
  visible in log + DB as an abort" implemented, not yet seen in a real run; "cron run
  completes unchanged on 3.12 + 1.63" verified on the NAS (2026-10-05 deploy
  production run green). **M0 complete** — Wave 1 (M1–M3) is next.

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
   the 24.04 names (align with `Dockerfile`):
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
   (`deploy_remote.sh` or `install_docker-image.sh` on the NAS), then
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
   (versioned control socket: screenshot/elements/context/click/fill/press/drag/resume/
   cancel), persistent per-task profile, no profile deletion / cookie clears; step
   screenshots; **step retry 3× before pause (new runner behavior)**;
   `wait_user(prompt[, until])` method; element scan + bounding boxes; pause context
   persisted (`Run.pause_prompt` / `Run.pause_context`); display allocation +
   Xvfb/x11vnc/websockify child management (image apt deps `git`, `x11vnc`,
   `websockify`, `novnc` added with this milestone)
4. Orchestrator + APScheduler: per-task cron, persistent jobstore, global semaphore
   (default 1), DB row locks; stdout streaming to log file
5. Pause triggers (`step_failed` after 3× retry, `wait_user`) + 30-min hold + ntfy push
   with session deep link + DB status
6. Download tracking + deduplication + post-download hook
7. CLI: `python -m billcollector serve` / `python -m billcollector run <task_id>`;
   legacy `BillCollector.py` stays the batch entry point until M4

**Exit:** daemon runs tasks on schedule; on the mock portal: `testautopause` — 3× step
failure → `waiting` → resume via the control-socket test client → step re-executes →
download tracked; `testwaituser` — `wait_user` pause/resume (complete-on-resume
semantics; `until` check when given); profile accumulation verifiable (cookie banner
only on the 1st run).

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

1. Copilot UI on the control socket: screenshot + numbered overlays (bounding boxes),
   click/fill/press/drag, resume; "what to do" layout; mobile-first; read-only running
   view (step screenshots)
2. noVNC: per-run display stack (already in M1 image deps), embedded noVNC iframe on
   the session page
3. Recipe repair flow: failure context (step screenshot, expected locator, candidate
   elements) → candidate picker (primary path, no YAML) or YAML edit (advanced) →
   validate → save → git commit → "run now"
4. `wait_user(prompt[, until])` in runner + recipe docs (schema stays free-form)
5. Git auto-commit structured messages: `recipe(<service>): <summary>`

**Exit (mock portal, E2E — the Wave 1 acceptance set):** `testautopause` (3× → pause →
Copilot click "I am not a robot" → resume); `testwaituser` (CAPTCHA code typed via
Copilot `fill` + "Verify" click → resume); `testcaptchadrag` (slider via Copilot `drag`
or noVNC → resume); persistent profile (banner only on run 1); download dedup (run 2);
"changed website" drill (`/admin/happy/mutate` → pause with failure context → repair via
candidate picker → commit visible in `git log` → re-run green → `/admin/happy/reset`).

**Wave 1 exit** = the M3 exit above: all three friction points (DOM change,
ads/cookie forms, CAPTCHAs) are demonstrable end-to-end by a human from the web UI, and
the AI-open architecture (versioned intervention protocol + machine-readable pause
context + human-approval gate) is in place and exercised.

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
- **M3 / Wave 1 acceptance:** E2E on the mock portal — the six Wave 1 acceptance
  scenarios above (autopause, waituser, captchadrag, persistent profile, dedup,
  changed-website repair drill) incl. `git log` check of the repair commit
- **Mock portal:** `tests/mock_portal/` — **delivered (v0.4)** FastAPI app (separate
  fixture, unaffected by the NiceGUI choice): Layer A sites + Layer B friction sites
  (cookie banner, login, displayed 6-digit code, drag CAPTCHA, "I am not a robot"
  challenge, document download) + `POST /admin/<site>/mutate|reset` for the repair
  drill. No second mock portal should be built.

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
  3× failure; a human resolves (Copilot/noVNC). No "CAPTCHAs are solved automatically"
  promise in the docs; future AI assistance stays behind the human-approval gate.
- **Intervention protocol stability:** it is the future AI-integration contract — keep
  the `context` payload complete, stable, and small; changes need a version bump + doc
  update.
- **3× retry cost:** failing steps wait out Playwright's per-attempt timeout (default
  30 s) → a `step_failed` pause costs ~90 s+ of retries before the human is asked (the
  regression plan already notes this for `testautopause`). Acceptable: the human is
  asked once, with full context, not three times.
- **Non-root switch (M0):** bind-mount ownership (Downloads, db, profiles, data) must be
  adjusted for the new user.

## Out of scope

- **ML/LLM implementation** (assistant, action proposals, auto-repair, CAPTCHA
  solving) — Wave 1 delivers the open architecture only (versioned intervention
  protocol + machine-readable pause context + human-approval gate, all exercised by
  the E2E scenarios); the assistant itself is a future wave, and its actions will
  still require human approval
- Multi-user / multi-tenancy (single login per instance — confirmed; expert's
  per-login-identity directories rejected; per-portal-account isolation is the
  per-task browser profile)
- Custom REST/external API surface (UI-only; health via built-in `/_alive`; the
  control socket is an internal unix socket, not an API)
- E-mail / SMTP notification
- Paperless REST API upload (post-download hook only; later consumer)
- `playwright codegen` in the UI (stays a VS Code dev workflow)
