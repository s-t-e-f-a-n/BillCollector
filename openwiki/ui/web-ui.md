---
type: Reference
title: Web UI Pages
description: One short section per BillCollector daemon UI page (dashboard, tasks, task detail, recipes, settings, session, log pane, auth): purpose, state, and actions.
tags: [ui, nicegui, dashboard, task-detail, recipes, settings, session, log-pane, auth]
sources:
  - id: openwiki-source-6fa93ea499647a165e750ceb
    resource: repo://apps/billcollector/ui/app.py
  - id: openwiki-source-567a6c368cd7a7d9c8e658a4
    resource: repo://apps/billcollector/ui/dashboard.py
  - id: openwiki-source-e9295a25f061b0f77937eb66
    resource: repo://apps/billcollector/ui/task_detail.py
  - id: openwiki-source-a218dfd1736f1649124f8ec5
    resource: repo://apps/billcollector/ui/recipes.py
  - id: openwiki-source-40aed95a77c330cc8d938c9a
    resource: repo://apps/billcollector/ui/settings.py
  - id: openwiki-source-a440d1f475d1f212b81c034c
    resource: repo://apps/billcollector/ui/session.py
  - id: openwiki-source-1e0d8f9c4d8f4b5a6c7d8e9f
    resource: repo://apps/billcollector/ui/auth.py
  - id: openwiki-source-8ba0392313087221497ee6d9
    resource: repo://apps/billcollector/downloads.py
  - id: openwiki-source-cb5ad5bebf6e21b3122ebeda
    resource: repo://BillCollector.sh
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
generated: { by: "openwiki/0.7.3", at: "2026-10-28T00:00:00.000Z" }
---

# Web UI Pages

The BillCollector daemon serves a NiceGUI-based web interface. Each page is registered in `apps/billcollector/ui/app.py` and guarded by session-cookie authentication (`apps/billcollector/ui/auth.py`). The UI binds to `127.0.0.1:8000` by default (override with `BC_UI_HOST` / `--host` / `--port`).

## Auth (Login) — `/login`

- **Purpose**: Gate access to the daemon UI.
- **State**: On first daemon start, shows a set-password form (the UI password hash is seeded from `BC_UI_PASSWORD` in `apps/.env` if present). Subsequent visits show the login form. No self-registration; the password is set once.
- **Actions**: Submit password → set session cookie (`authenticated=1`, 30-day expiry) → redirect to `/` or the original deep link.
- **Implementation**: `apps/billcollector/ui/auth.py` registers `/login` and wraps all non-public routes with a `BaseHTTPMiddleware` that redirects unauthenticated requests to `/login`.

## Onboarding — `/onboarding`

- **Purpose**: First-start wizard for fresh installs (no password set, or no task enabled).
- **State**: Three-step stepper:
  1. **Vault** — `BW_API_URL` / `BW_API_HOST` inputs with a Check button (same DNS vetting + status check as the run preflight) and Save (writes `vault_api_url` / `vault_api_host` to Settings; empty = env fallback).
  2. **Tasks** — list of INI-imported tasks with enable toggles, Import from INI button (adds missing (service, user) pairs), and a manual New task form.
  3. **Finish** — confirms completion.
- **Actions**: Check vault, Save vault config, enable/disable tasks, Import from INI, create task, Finish.
- **Auto-complete**: Upgraded installs (password hash exists and ≥1 task enabled) skip the wizard on daemon start (`ui_auth.auto_complete_onboarding`).
- **Implementation**: `apps/billcollector/ui/onboarding.py`.

## Dashboard — `/`

- **Purpose**: Overview of all tasks and their status; entry point for run actions.
- **State**: Task table with filters (enabled/disabled, status), per-row badge for `waiting` (paused runs), last run / next run timestamps, latest download link, Run now / Stop / Edit buttons, and a live log pane (WebSocket) showing the most recent run's output.
- **Actions**:
  - **Run now** → calls `orchestrator.start_run(task_id)` (same callback the scheduler uses).
  - **Stop** → calls `orchestrator.stop_run(task_id)` (SIGTERM the runner's process group, SIGKILL after `STOP_TIMEOUT=10s`).
  - **Edit** → opens the recipe editor at `/recipes/<service>`.
  - Clicking the `waiting` badge or a recent run → deep-links to `/runs/<run_id>` (session page).
- **Implementation**: `apps/billcollector/ui/dashboard.py`.

## Task Detail — `/tasks/<task_id>`

- **Purpose**: Per-task run history, step records, screenshots, and downloads.
- **State**: Tabs for Runs (chronological list with result, duration, download count), Steps (the selected run's step-by-step `PageStatus` rows with locator-action JSON, error, and step screenshot), and Downloads (per-run files with sha256, size, path).
- **Actions**: Run now / Stop (same as dashboard), Reset profile (deletes the per-task browser profile directory, forcing a fresh login on next run).
- **Implementation**: `apps/billcollector/ui/task_detail.py`.

## Session (Intervention) — `/runs/<run_id>`

- **Purpose**: The ntfy deep-link target for a paused run; shows the Copilot view and noVNC live browser.
- **State**: Two tabs:
  - **Copilot** — failure screenshot (base64-embedded), numbered interactive element overlay, element actions (click/fill/press/drag via the control socket), Resume / Cancel buttons.
  - **noVNC** — websockify iframe pointing at the runner's `novnc_port` (live browser view).
- **Actions**:
  - **Resume** → sends `{"action": "resume"}` over the run's control socket.
  - **Cancel** → sends `{"action": "cancel"}`.
  - **Repair recipe** → link to `/recipes/<service>?run=<run_id>` (preloads failure context).
  - **Element actions** (Copilot tab) → sends `{"action": "set_element", "element_n": N, "new_value": ...}` for locator repair.
- **Implementation**: `apps/billcollector/ui/session.py`.

## Recipe Editor — `/recipes/<service>`

- **Purpose**: Edit the YAML recipe for one portal (service).
- **State**: Loads `recipe-pw__<service>.yaml` from `apps/recipes_playwright/`, validates against `recipe-pw-schema.yaml`. On save, validates in-process with `recipes.validate_recipe`, writes atomically, and optionally git-commits (if `git_commit_enabled` Setting is true).
- **Actions**: Validate, Save, git auto-commit (optional).
- **Repair mode**: When opened with `?run=<run_id>`, the editor preloads the failure panel (screenshot, failed step, error, candidate elements with "Use" buttons that rewrite the failed step's locator via `apply_candidate_to_step`).
- **Implementation**: `apps/billcollector/ui/recipes.py`.

## Settings — `/settings`

- **Purpose**: Configure daemon runtime parameters.
- **State**: Each field writes its own Settings row on save (invalid value fails only that field). Fields:
  - `ntfy_topic` — push topic (empty disables).
  - `pause_deadline_seconds` — pause timeout (default 1800).
  - `max_concurrency` — global runner semaphore (default 1).
  - `git_commit_enabled` — auto-commit recipe edits.
  - `download_dir` — root download directory (runner + batch share).
  - `display_start` / `display_count` — Xvfb display range.
  - `ui_base_url` — base URL for generated deep links.
  - `vnc_password` — x11vnc password (empty = localhost-only, no auth).
  - `vault_api_url` / `vault_api_host` — override `BW_API_URL` / `BW_API_HOST` (Settings wins over env).
  - UI password — change the login password (hash stored in Settings).
- **Actions**: Save individual field, change password.
- **Implementation**: `apps/billcollector/ui/settings.py`.

## Downloads — `/downloads`

- **Purpose**: Browse all downloaded files across tasks/runs.
- **State**: Table of `Download` rows with task, run, filename, size, sha256, saved path, and created timestamp. Deduplication is per-task by sha256.
- **Actions**: Open/save file (served from `download_dir`).
- **Implementation**: `apps/billcollector/ui/downloads.py`.

## Runfiles (Static) — `/runfiles/<run_id>/...`

- **Purpose**: Serve step screenshots and pause screenshots for the UI (dashboard, task detail, session).
- **State**: Static file mount of `config.RUN_DIR` (typically `apps/data/runs/`). Distinct from the `/runs/<run_id>` deep-link route.
- **Implementation**: `apps/billcollector/ui/runfiles.py` registered in `app.py` as `static_files`.

## Log Pane (Live)

- **Purpose**: Real-time run output on the dashboard and session page.
- **State**: WebSocket subscribers receive each line of the runner's stdout as it is streamed by the orchestrator's monitor. The log path is recorded on the Run row (`Run.log_path`).
- **Implementation**: `apps/billcollector/ui/logpane.py` + monitor in `orchestrator.py`.

## Verification

- `python3 -m billcollector serve` → first start shows set-password form; afterwards login works and dashboard lists INI-imported tasks.
- Navigate `/onboarding` → check vault step, import tasks, finish.
- From dashboard: Run now a task → task goes `running` → session page shows Copilot/noVNC during pause → Resume/Cancel/Repair all work.
- Edit a recipe → validate + save (+ optional git commit) → next run uses new recipe.
- Change Settings fields → each saves independently, invalid values fail only that field.