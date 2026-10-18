---
type: "Reference"
title: "Web UI Pages"
description: One section per page of the BillCollector daemon's NiceGUI web UI - the dashboard, task detail, intervention session, recipe editor, downloads, settings, and login/auth - each with its purpose, the state it shows, and the actions it exposes, plus the shared app shell (lifecycle wiring, session-cookie auth, layout).
tags: [web-ui, nicegui, dashboard, session-page, recipe-editor, settings, auth]
sources:
  - id: openwiki-source-6fa93ea499647a165e750ceb
    resource: repo://apps/billcollector/ui/app.py
  - id: openwiki-source-567a6c368cd7a7d9c8e658a4
    resource: repo://apps/billcollector/ui/dashboard.py
  - id: openwiki-source-e9295a25f061b0f77937eb66
    resource: repo://apps/billcollector/ui/task_detail.py
  - id: openwiki-source-a440d1f475d1f212b81c034c
    resource: repo://apps/billcollector/ui/session.py
  - id: openwiki-source-a218dfd1736f1649124f8ec5
    resource: repo://apps/billcollector/ui/recipes.py
  - id: openwiki-source-40aed95a77c330cc8d938c9a
    resource: repo://apps/billcollector/ui/settings.py
  - id: openwiki-source-58c3d08734ec573678b14253
    resource: repo://apps/billcollector/runner.py
  - id: openwiki-source-23bdbbfe00829612394eb2b1
    resource: repo://apps/billcollector/config.py
---

# Web UI Pages

The daemon's UI is a NiceGUI app started by `python3 -m billcollector serve` (default bind `127.0.0.1:8000`, host overridable via `BC_UI_HOST`). All routes and the auth middleware are registered in `build_app` (`apps/billcollector/ui/app.py`); the daemon lifecycle wiring and the per-page behavior are summarized below. For the run actions' backend (claim, spawn, monitor, finalization), see [Run Lifecycle](../workflows/run-lifecycle.md); for the intervention loop behind the session page, see [Pause, Intervention & Recipe Repair](../workflows/pause-repair.md).

## App shell: wiring, lifecycle, and auth

- **Wiring** (`ui/app.py` `start()`): builds `Database`, `Orchestrator(db)`, and `TaskScheduler(db, orchestrator.start_run)`, registers all routes in `build_app`, then runs NiceGUI headless (`show=False`, no browser pop-up). `build_app` is factored out so the pytest suite can build the exact production wiring against a scratch DB without starting a server.
- **Lifecycle hooks**: startup runs `orchestrator.cleanup_orphans()` (leftover active runs from a previous daemon lifetime are marked `interrupted`) and then `scheduler.start()`; shutdown stops the scheduler **first** (no new job can dispatch while runners are reaped) and then `orchestrator.shutdown()`.
- **Two compatibility shims** (module level in `ui/app.py`): the Vue runtime-compiler workaround exposes `CustomEvent` through `app.config.globalProperties` (the dashboard row-action buttons dispatch DOM `CustomEvent`s from slot templates; without the binding the clicks die with `CustomEvent is not a constructor`), and a wrapper around the engineio ASGI `handle_request` answers 499 (or closes the websocket) when a client disconnects before its request arrives, instead of letting a `KeyError` unwind through the whole middleware stack as a spurious 500.
- **Auth** (`ui/auth.py`, `ui/login.py`): single-operator session-cookie auth. One bcrypt hash in the `Settings` table (`ui_password_hash`); on first start without a hash, `/login` shows a one-time set-password form (minimum 8 characters, both fields must match), and `BC_UI_PASSWORD` seeds the hash instead (a hash set via the UI is never overwritten). The `SessionMiddleware` secret (`session_secret`) is generated once and persisted, so sessions survive daemon restarts. `AuthRedirectMiddleware` sends unauthenticated requests to non-public paths to `/login` (307); public paths are `/login`, `/_alive`, and NiceGUI static (`/_*`). The login form POSTs natively over plain HTTP (no websocket round-trip), and failures bounce back to `/login?error=<code>` with a small closed code set (`too_short`, `mismatch`, `wrong_password`).
- **Health probe**: `/_alive` returns `ok` without authentication - the one path usable by external liveness checks.
- **Layout** (`ui/layout.py`): every protected page renders the same frame via `build_layout` - a header plus a left menu (Dashboard, Downloads, Settings) with the current entry highlighted.
- **Runfiles** (`ui/runfiles.py`): not a page, but a static directory - `config.RUN_DIR` is served at `/runfiles` so step screenshots (`step_N.png`), pause screenshots (`pause_N.png`), and the VNC auth file are reachable from the UI. The prefix is deliberately **not** `/runs`, which is reserved for the session deep-link route.

## Route map

| Route | Module | Purpose |
| --- | --- | --- |
| `/login` | `ui/login.py` | Set-password on first start, then login (GET form + POST handler) |
| `/_alive` | `ui/app.py` | Unauthenticated health probe |
| `/` | `ui/dashboard.py` | Task table, filters, run actions, live log |
| `/tasks/<task_id>` | `ui/task_detail.py` | Per-task history, downloads, actions |
| `/runs/<run_id>` | `ui/session.py` | Intervention session (ntfy deep-link target) |
| `/recipes/<service>` | `ui/recipes.py` | Per-service YAML editor, validate/save, repair panel |
| `/downloads` | `ui/downloads.py` | All Download rows, optional task filter |
| `/settings` | `ui/settings.py` | Password and Settings-table fields |
| `/runfiles/…` | `ui/runfiles.py` | Static: screenshots and run artifacts |

## Dashboard (`/`, `ui/dashboard.py`)

The operator's home page.

- **State**: one table row per task - service/user, a color-coded status badge (`running` blue, `waiting` orange with a highlighted row, `idle` grey), last run, the **next cron fire** read live from the APScheduler jobstore (job id `task-<id>`; disabled tasks show `—`), the session link for an active run, and the truncated last-download filename. Toolbar carries the service/status filters and a `[N waiting]` badge. A `ui.timer` polls the DB every ~2 s and refreshes the table and badge.
- **Actions**: per-row **Run now** (works for disabled tasks as a manual one-off; disabled while the task is `running`/`waiting`), per-row **Stop** (enabled only while `running`), and per-row **Edit** (task dialog). The toolbar **Run (filtered)** enqueues all *enabled* tasks in the filtered set - the global semaphore serializes them and skipped tasks are reported in a notify. All run actions call `orchestrator.start_run` / `stop_run`, the same callbacks the scheduler uses.
- **Task management** (`ui/tasks.py`): the toolbar **Add task** button and the row **Edit** button open the same dialog - service, user, cron (default `0 0 1 * *`, validated as a 5-field crontab), and the enabled switch. The per-service recipe file is derived from the service and shown read-only; a missing file warns but does not block creation. Service/user are read-only when editing, and there is **no task deletion** - disabling is the off switch. Every change goes through `db.create_task` / `db.update_task` plus `scheduler.sync_task`.
- **Log pane and step strip**: below the table, the shared `LogPane` (see below) follows the selected run, and a step strip shows the followed run's step screenshot thumbnails (full image on click), loaded via `/runfiles`.

## Task detail (`/tasks/<task_id>`, `ui/task_detail.py`)

- **State**: header with service/user, status badge, enabled/cron, and the recipe file; run history with per-run step rows and screenshot thumbnails (the notes tail, step action, and error are truncated for the table - the full text lives in the run log); the task's downloads (same row builder and body slot as the `/downloads` page); and the live log of the selected run. Polls the DB ~2 s to update badge, button states, the pause section, and history/downloads.
- **Actions**: **Run now** / **Stop** (orchestrator, as on the dashboard), **Reset profile** (confirmation dialog; goes through `db.reset_profile` and is rejected unless the task is `idle`), **Recipe** (to the editor page), and **Open session** while a run is `waiting` (to `/runs/<run_id>`).

## Session (`/runs/<run_id>`, `ui/session.py`)

The operator's intervention page - the ntfy deep-link target. It is a state machine polled from the DB ~2 s, with the state decided by `run_state(run, sock_alive)`: `unknown` (no row), `ended` (a result is set), `waiting` (an open run whose control socket is live - the pause columns survive a resolved pause, so the socket's liveness, not `pause_reason` alone, distinguishes a live pause from a run executing after it), and `running` (open, no active pause).

- **`waiting`**: the pause banner (reason, prompt, deadline countdown) and two tabs. The **Copilot** view (active by default) shows the live screenshot with a numbered element overlay (percent-positioned badges), the element select (`n · role · name`), an action bar limited to the element's `actionTypes` (click / fill / press / drag), **Resume**, and **Cancel** (confirmation dialog -> the protocol `cancel`). The screenshot and elements are fetched on page load, re-fetched every ~5 s, and immediately after every action; an empty element list renders a hint pointing at noVNC instead of an error. The **noVNC** tab embeds the run's websockify port as a full-size iframe whose `src` is built client-side from `window.location.hostname` (one URL works for a localhost and a LAN operator; x11vnc is `-localhost`, and the RFB password is entered in noVNC's own prompt, never in the URL).
- **`running`**: read-only observation - the step-screenshot strip (fills in live as new `PageStatus` rows land) and the noVNC tab.
- **`ended`**: the result (`success` / `failure` / `interrupted` / `cancelled` / `needs_attention`) and, when `pause_context` is set, the last pause context read-only. No noVNC - the display stack is reaped.
- **Repair recipe**: offered for a `step_failed` pause, both while the run is `waiting` and after it has ended; it links to `/recipes/<service>?run=<run_id>` with the failure panel preloaded (see below).
- Every control-socket request opens a short-lived `ControlClient` and runs in a worker thread - the blocking socket call never sits on the UI event loop.

## Recipe editor (`/recipes/<service>`, `ui/recipes.py`)

A CodeMirror YAML editor for the per-service recipe file (shared by all tasks of the service, shown with the service's task list).

- **State**: the recipe text plus a read-only step-tree sidebar (re-parsed on edit; a broken YAML document is marked instead of rendered).
- **Actions**: **Validate** (inline result via `recipes.validate_recipe`, re-run on save) and **Save** = validate -> `save_recipe` (atomic temp file + `os.replace`) -> `git_commit` with the message `recipe(<service>): <summary>` when `git_commit_enabled` (the summary is the first changed service description, else "edited via UI"). After a successful save the page offers **Run now** per task of the service. The auto-commit stages exactly the recipe file (never `git add -A`), so unrelated dirty files are never swept in.
- **Repair mode** (`?run=<run_id>`, the session page's Repair recipe link): the editor preloads a **failure panel** from the run's `pause_context` - the failure screenshot, the failed step (number, description, expected locator chain, error), and candidate rows each with a **Use** button. **Use** replaces the failed step's locator prefix with the candidate's locator (`apply_candidate_to_step` in `apps/billcollector/recipes.py`) and reloads the editor with the rewritten YAML; the operator then fine-tunes through the normal Validate -> Save -> git-commit flow. The picker is disabled (with a hint) for a non-`step_failed` pause, a missing/corrupt context, a context without a step number, or a step the replacement cannot apply to (no locator prefix, nested `expect_download` step).

## Downloads (`/downloads`, `ui/downloads.py`)

Lists every Download row (task service/user, run, filename, size, truncated sha256, the duplicate badge, date) newest first, with an optional task filter. Read-only - download management is not part of this surface. The row builder and body slot are shared with the task detail page's downloads section, so both views render the same columns.

## Settings (`/settings`, `ui/settings.py`)

Edits the daemon settings stored in the `Settings` table.

- **State**: the UI password fields (change; minimum 8, both must match) and one row per daemon setting: `ntfy_topic`, `pause_deadline_seconds`, `max_concurrency` (hint: takes effect on the next daemon start - the semaphore is built at construction), `display_start`, `download_dir`, `ui_base_url`, `vnc_password`, plus the `git_commit_enabled` switch.
- **Actions**: each field writes its own `Settings` row on its own **Save** button (a notify confirms), so a field that fails validation (non-integer, non-positive, or empty where required) is the only one not written. The layering these values participate in (code defaults -> `apps/.env` -> `BC_*` env vars -> `Settings` table) is documented in [Development and Deployment](../operations/deployment.md).

## Log pane (shared, `ui/logpane.py`)

`LogPane` is the `ui.log` element shared by the dashboard and the task detail: it shows a run's log file content once, then follows the orchestrator's live stdout lines for the followed run only (registered via `orchestrator.add_log_subscriber`), keeping at most ~2000 lines. It is re-pointed at the run it should follow on every poll, so a run started via Run now after the page loaded streams live too.

## Verification

- `python3 -m billcollector serve` - the daemon binds port 8000; first start shows the set-password form, and after signing in the dashboard lists the INI-imported tasks with the left menu (Dashboard, Downloads, Settings).
- `curl http://127.0.0.1:8000/_alive` - returns `ok` without authentication.
- The pytest suite (`apps/.venv/bin/python -m pytest tests/ -q`, expected: exit `0`) builds the production `build_app` wiring against a scratch DB with the NiceGUI `User` fixture - see [Testing and Verification](../testing/verification.md).

## Related pages

- [Run Lifecycle](../workflows/run-lifecycle.md) - what the run actions trigger behind the scenes.
- [Pause, Intervention & Recipe Repair](../workflows/pause-repair.md) - the pause loop and repair workflow the session page drives.
- [Architecture Overview](../architecture/overview.md) - the two operating modes and the shared components.
- [Shared Interfaces](../architecture/shared-interfaces.md) - the control protocol and schema contracts the UI reads.
