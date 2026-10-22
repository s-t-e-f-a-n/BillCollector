---
type: "Roadmap"
title: "Roadmap: Daemon Migration Status"
description: "The public-safe position of the BillCollector migration from cron batch tool to self-hosted daemon: what is live today (daemon as primary mode with scheduler, orchestrator, runner, full UI surface with pause/intervention/repair, regression environment) and what is planned or deliberately open (empty document-consumer hook slot, AI-driven intervention, self-healing), while the deprecated cron batch system keeps running unchanged as the rollback path."
tags: [roadmap, daemon, migration, batch, status, consumers]
sources:
  - id: openwiki-source-f1a62cf42e1bd698b918c396
    resource: repo://apps/billcollector/__init__.py
  - id: openwiki-source-86ee9334c9ad3a8fdac56ec7
    resource: repo://apps/billcollector/cli.py
  - id: openwiki-source-dfcc8c4cc4fff7329bab81ee
    resource: repo://apps/billcollector/consumers/__init__.py
  - id: openwiki-source-35e3e38e10788b572b0291e7
    resource: repo://apps/billcollector/control.py
  - id: openwiki-source-b6ba4edf64def9af03c073a0
    resource: repo://apps/billcollector/db.py
  - id: openwiki-source-8ba0392313087221497ee6d9
    resource: repo://apps/billcollector/downloads.py
  - id: openwiki-source-b9a801c4c55a83765dfae961
    resource: repo://apps/billcollector/notify.py
  - id: openwiki-source-2f5f78f652c3248ce1f2e939
    resource: repo://apps/billcollector/orchestrator.py
  - id: openwiki-source-4c2ea7e60ef9d847ed1916c0
    resource: repo://apps/billcollector/pause.py
  - id: openwiki-source-58c3d08734ec573678b14253
    resource: repo://apps/billcollector/runner.py
  - id: openwiki-source-e150a34f53495808d09ab2c8
    resource: repo://apps/billcollector/scheduler.py
  - id: openwiki-source-6fa93ea499647a165e750ceb
    resource: repo://apps/billcollector/ui/app.py
  - id: openwiki-source-a218dfd1736f1649124f8ec5
    resource: repo://apps/billcollector/ui/recipes.py
  - id: openwiki-source-a440d1f475d1f212b81c034c
    resource: repo://apps/billcollector/ui/session.py
  - id: openwiki-source-40aed95a77c330cc8d938c9a
    resource: repo://apps/billcollector/ui/settings.py
  - id: openwiki-source-cb5ad5bebf6e21b3122ebeda
    resource: repo://BillCollector.sh
  - id: openwiki-source-ca6cb4b1a14fd7969dfae3ec
    resource: repo://CHANGELOG.md
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
generated: { by: "openwiki/0.7.2", at: "2026-10-16T23:42:23.422Z" }
verified:
  - by: openwiki/0.7.2
    at: 2026-10-21T23:26:25.264Z
---

# Roadmap: Daemon Migration Status

BillCollector is mid-migration: from a cron-driven batch tool to a self-hosted daemon that is now the **primary mode** — a NiceGUI web UI that schedules the runs, watches them live, and lets the operator step in when a portal changes (pause, inspect the page, repair the recipe, resume) ([README.md, "What's Next"](../../README.md#whats-next)). The cron batch system is **deprecated** but keeps running unchanged in the meantime as the rollback path. For the full architecture of both coexisting modes, see [Architecture Overview](overview.md); for operating the daemon, see [Deployment](../operations/deployment.md).

## Live now

- **The daemon is implemented and is the primary mode**, as described in the package docstring of `apps/billcollector/__init__.py` (Wave 1, M1): it turns the cron batch job into a 24/7 daemon — an orchestrator spawns one subprocess per task run (sync Playwright), each run is pausable through a versioned control socket, and a machine-readable pause context is persisted for human (and future AI) intervention. The README states the daemon is the primary mode: it schedules each task on its own cron expression, runs the browser headful on an allocated virtual display (watchable live over noVNC), supervises every run, and pauses for operator help "all without shell access to the daemon."
- **Entrypoint**: `python3 -m billcollector serve` starts the NiceGUI daemon (bound to `127.0.0.1:8000` by default; `--host`/`--port` or `BC_UI_HOST` override both). `cli.py` loads the env, imports the INI files into the Task table on first start, seeds the UI password hash from `BC_UI_PASSWORD`, and auto-completes the onboarding wizard for upgraded installs before serving; `python3 -m billcollector run <task_id>` executes a single task run standalone (cron-style single-shot without the daemon). NiceGUI and Playwright are imported lazily per subcommand.
- **Scheduler**: `apps/billcollector/scheduler.py` mirrors the Task table into an APScheduler `AsyncIOScheduler` with a persistent SQLAlchemy jobstore in the same `bc.db` file — one cron job per enabled task with a cron expression, rebuilt from the Task table at startup (`resync()`, the Task table always wins) and per task change (`sync_task()`).
- **Orchestrator**: `apps/billcollector/orchestrator.py` runs each task run as an isolated `python -m billcollector run` subprocess — the daemon process never imports scraping code, so a runner crash cannot take down the UI/scheduler. It claims the task with a DB row lock, gates spawns with the `max_concurrency` semaphore, streams run output to the per-run log file and the UI live-log subscribers, finalizes Run rows the runner left open, marks orphaned runs `interrupted` at startup, and provides `start_run` (scheduler + "Run now") and `stop_run` (UI "Stop").
- **Runner**: `apps/billcollector/runner.py` executes one task run as a sync Playwright step loop with the same vault preflight semantics as the batch entry point, a persistent per-task browser profile, a per-run Xvfb/x11vnc/websockify display stack, and graceful SIGTERM interruption (`result=interrupted`).
- **Pause and intervention**: a stuck run (a non-graceful step that failed 3 times, a failed download, or an explicit `wait_user` step) pauses instead of aborting. `apps/billcollector/pause.py` builds the machine-readable pause context, persists it on the Run row, flips the task to `waiting`, and serves the versioned control-socket protocol (`apps/billcollector/control.py`, protocol v1: screenshot, elements, context, click, fill, press, drag, resume, cancel) until the operator resumes, cancels, or the pause deadline is exceeded. Every pause pushes an ntfy deep link to the session page (`apps/billcollector/notify.py`, best-effort). The end-to-end run path including the pause states is traced in [Run Lifecycle](../workflows/run-lifecycle.md).
- **Full UI surface** (`apps/billcollector/ui/`, wired in `ui/app.py`): the login page (`/login`) with a set-password form on first start, the first-start onboarding wizard (`/onboarding`: vault check, task list with Import from INI, finish), the dashboard (`/`) with the task table, status filters, waiting badge, per-row Run now / Stop and a live log pane; per-task pages (`/tasks/<task_id>`) with run history, step screenshots, downloads and Run now / Stop / Reset profile; the intervention session page (`/runs/<run_id>`, the ntfy deep-link target) with the Copilot view (live screenshot + numbered element overlay, element actions, Resume / Cancel) and a noVNC tab; the recipe editor (`/recipes/<service>`) with validate and save (optional git auto-commit); the downloads page (`/downloads`); the settings page (`/settings`); the `/runfiles` static directory for step and pause screenshots; and session-cookie authentication. The settings page exposes the daemon Settings fields (`ntfy_topic`, `pause_deadline_seconds`, `max_concurrency`, `git_commit_enabled`, `download_dir`, `display_start`, `ui_base_url`, `vnc_password`, `vault_api_url`/`vault_api_host`) plus the UI password; each field writes its own Settings row on save, so an invalid value only fails that field.
- **Recipe repair from a paused run**: opened with `?run=<run_id>` (the session page's "Repair recipe" link), the recipe editor preloads the failure panel from the run's pause context — failure screenshot, failed step, error, and candidate element rows with a "Use" button that rewrites the failed step's locator prefix (`apply_candidate_to_step`) into the existing validate → save → git-commit flow.
- **Regression environment**: the local regression test environment shipped in [CHANGELOG v0.4](../../CHANGELOG.md) — a mock web portal with scenario sites (happy path with OTP and downloads, bad login, graceful step failure, download failure, empty document list, CAPTCHA-style friction) and a harness (`tests/run_regression.py`) that executes a scope INI through the production scraping engine and verifies per-scenario expectations, including a `--vault` end-to-end mode against a real Vaultwarden.
- **The batch system is deprecated but unchanged and coexists**: `BillCollector.sh` → `apps/BillCollector.py` → `apps/BillCollectorServices_pw.py` still runs under cron; the wrapper now prints a deprecation notice to stderr on every start, but its `flock` double-start guard and `docker run` behavior are unchanged, so it stays the rollback path ("Rollback = re-enable the cron entry"). Both modes share one SQLite file — the legacy batch tables are left as-is in `bc.db` ("runtime status, not an archive", `apps/billcollector/db.py`) — and the README's migration section documents the overlap: the legacy path holds the shared `apps/.bc.lock` run lock while the daemon serializes its own runs per task, with the warning not to let both run the same (service, user) pair at the same time.

## Planned / deliberately open

Every item below is traceable to a public comment, docstring, or CHANGELOG entry — no internal planning documents are referenced.

- **Post-download consumer hook slot (decision 14)** — deliberately empty. `apps/billcollector/consumers/__init__.py` defines the slot: "Initially empty. To add a consumer, append a callable to `CONSUMERS`; it is called as `consume(download: dict)` for every new (non-duplicate) download, inside the runner subprocess so a slow consumer never blocks the UI/scheduler." The hook machinery is live in `apps/billcollector/downloads.py` (per-task sha256 dedup, one invocation per non-duplicate download, consumer failures logged but never breaking the run), but **no document consumer is implemented yet** — downstream handoff to a DMS such as Paperless-ngx still happens via the shared download folder.
- **AI-driven intervention** — the pause context is the "AI-integration contract" (`apps/billcollector/pause.py`): it must stay complete, stable and small, and protocol changes need a version bump in `control.py` plus a doc update. The package docstring describes the persisted context as being for "human (and future AI) intervention" — i.e., AI consumption of the pause context is designed for but not implemented; intervention today is human-in-the-loop.
- **Self-healing / assisted repair** — planned, not implemented. Per-step run tracking in SQLite (the method chain executed, the interactive elements found, the result) is documented as "the foundation for the planned self-healing/assisted-repair features" ([README.md](../../README.md)) and "the foundation for the self-healing idea" ([CHANGELOG 0.1pw](../../CHANGELOG.md)); the README's "What's Next" restates that the recorded step data and the machine-readable pause context are the foundation for it. What exists today is manual, UI-assisted repair of a paused run (see above), not automatic locator repair.

## How to read this page

- "Live" = shipped in the public tree, grounded in code docstrings and CHANGELOG entries.
- "Planned / open" = explicitly named in a public code comment, docstring, or CHANGELOG entry, and not yet implemented.
- The repository follows a trunk-based model: `main` is the verified production state and moves forward only once a milestone has been validated in production, so the "live" list above reflects what is safe to deploy today. See [Development and Deployment](../../README.md#development--deployment) for the release-tag and rollback mechanics.
