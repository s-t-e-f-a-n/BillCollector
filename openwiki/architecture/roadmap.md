---
type: "Roadmap"
title: "Roadmap: Daemon Migration Status"
description: "The public-safe position of the BillCollector migration from cron batch tool to self-hosted daemon: what is live today (daemon with scheduler, orchestrator, runner, full UI surface with pause/intervention/repair, regression environment) and what is planned or deliberately open (empty document-consumer hook slot, self-healing), while the batch system keeps running unchanged."
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
    at: 2026-10-18T05:11:23.466Z
---

# Roadmap: Daemon Migration Status

BillCollector is mid-migration: from a cron-driven batch tool towards a self-hosted daemon — a NiceGUI web UI that schedules the runs, watches them live, and lets the operator step in when a portal changes (pause, inspect the page, repair the recipe, resume) ([README.md, "What's Next"](../../README.md)). The batch system keeps running unchanged in the meantime. For the full architecture of both coexisting modes, see [Architecture Overview](overview.md); for operating the daemon, see [Deployment](../operations/deployment.md).

## Live now

- **The daemon is implemented** as described in the package docstring of `apps/billcollector/__init__.py` (Wave 1, M1): it turns the cron batch job into a 24/7 daemon — an orchestrator spawns one subprocess per task run (sync Playwright), each run is pausable through a versioned control socket, and a machine-readable pause context is persisted for human (and future AI) intervention.
- **Entrypoint**: `python3 -m billcollector serve` starts the NiceGUI daemon (default port 8000). `cli.py` loads the env, imports the INI files into the Task table on first start, seeds the UI password from `BC_UI_PASSWORD`, and serves; `python3 -m billcollector run <task_id>` executes a single task run standalone.
- **Scheduler**: `apps/billcollector/scheduler.py` mirrors the Task table into an APScheduler `AsyncIOScheduler` with a persistent SQLAlchemy jobstore in the same `bc.db` file — one cron job per enabled task with a cron expression, rebuilt from the Task table at startup (`resync()`, the Task table always wins) and per task change (`sync_task()`).
- **Orchestrator**: `apps/billcollector/orchestrator.py` runs each task run as an isolated `python -m billcollector run` subprocess — the daemon process never imports scraping code, so a runner crash cannot take down the UI/scheduler. It claims the task with a DB row lock, gates spawns with the `max_concurrency` semaphore, streams run output to the per-run log file and the UI live-log subscribers, finalizes Run rows the runner left open, marks orphaned runs `interrupted` at startup, and provides `start_run` (scheduler + "Run now") and `stop_run` (UI "Stop").
- **Runner**: `apps/billcollector/runner.py` executes one task run as a sync Playwright step loop with the same vault preflight semantics as the batch entry point, a persistent per-task browser profile, a per-run Xvfb/x11vnc/websockify display stack, and graceful SIGTERM interruption (`result=interrupted`).
- **Pause and intervention**: a stuck run (a non-graceful step that failed 3 times, a failed download, or an explicit `wait_user` step) pauses instead of aborting. `apps/billcollector/pause.py` builds the machine-readable pause context, persists it on the Run row, flips the task to `waiting`, and serves the versioned control-socket protocol (`apps/billcollector/control.py`, protocol v1: screenshot, elements, context, click, fill, press, drag, resume, cancel) until the operator resumes, cancels, or the pause deadline is exceeded. Every pause pushes an ntfy deep link to the session page (`apps/billcollector/notify.py`, best-effort).
- **Full UI surface** (`apps/billcollector/ui/`, wired in `ui/app.py`): the dashboard (`/`) with the task table, status filters, waiting badge, per-row Run now / Stop and a live log pane; per-task pages (`/tasks/<task_id>`) with run history, step screenshots, downloads and Run now / Stop / Reset profile; the intervention session page (`/runs/<run_id>`, the ntfy deep-link target) with the Copilot view (live screenshot + numbered element overlay, element actions, Resume / Cancel) and a noVNC tab; the recipe editor (`/recipes/<service>`) with validate and save (optional git auto-commit); the downloads page (`/downloads`); the settings page (`/settings`: password, ntfy topic, concurrency, pause deadline, download dir, VNC password, ...); and session-cookie authentication with a set-password form on first start. Details: [Web UI](../ui/web-ui.md), [Pause and Repair](../workflows/pause-repair.md).
- **Recipe repair from a paused run**: opened with `?run=<run_id>` (the session page's "Repair recipe" link), the recipe editor preloads the failure panel from the run's pause context — failure screenshot, failed step, error, and candidate element rows with a "Use" button that rewrites the failed step's locator prefix (`apply_candidate_to_step`) into the existing validate → save → git-commit flow.
- **Regression environment**: the local regression test environment shipped in [CHANGELOG v0.4](../../CHANGELOG.md) — a mock web portal with scenario sites (happy path with OTP and downloads, bad login, graceful step failure, download failure, empty document list, CAPTCHA-style friction) and a harness (`tests/run_regression.py`) that executes a scope INI through the production scraping engine and verifies per-scenario expectations, including a `--vault` end-to-end mode against a real Vaultwarden.
- **The batch system is unchanged and coexists**: `BillCollector.sh` → `apps/BillCollector.py` → `apps/BillCollectorServices_pw.py` still runs under cron with its own `flock` guard and exit-code semantics, and both modes share one SQLite file — the legacy batch tables are left as-is in `bc.db` ("runtime status, not an archive", `apps/billcollector/db.py`).

## Planned / deliberately open

Every item below is traceable to a public comment, docstring, or CHANGELOG entry — no internal planning documents are referenced.

- **Post-download consumer hook slot (decision 14)** — deliberately empty. `apps/billcollector/consumers/__init__.py` defines the slot: "Initially empty. To add a consumer, append a callable to `CONSUMERS`; it is called as `consume(download: dict)` for every new (non-duplicate) download, inside the runner subprocess so a slow consumer never blocks the UI/scheduler." The hook machinery is live in `apps/billcollector/downloads.py` (per-task sha256 dedup, one invocation per non-duplicate download, consumer failures logged but never breaking the run), but **no document consumer is implemented yet** — downstream handoff to a DMS such as Paperless-ngx still happens via the shared download folder.
- **AI-driven intervention** — the pause context is the "AI-integration contract" (`apps/billcollector/pause.py`): it must stay complete, stable and small, and protocol changes need a version bump in `control.py` plus a doc update. The package docstring describes the persisted context as being for "human (and future AI) intervention" — i.e., AI consumption of the pause context is designed for but not implemented; intervention today is human-in-the-loop.
- **Self-healing / assisted repair** — planned, not implemented. Per-step run tracking in SQLite (the method chain executed, the interactive elements found, the result) is documented as "the foundation for the planned self-healing/assisted-repair features" ([README.md](../../README.md)) and "the foundation for the self-healing idea" ([CHANGELOG 0.1pw](../../CHANGELOG.md)). What exists today is manual, UI-assisted repair of a paused run (see above), not automatic locator repair.

## How to read this page

- "Live" = shipped in the public tree, grounded in code docstrings and CHANGELOG entries.
- "Planned / open" = explicitly named in a public code comment, docstring, or CHANGELOG entry, and not yet implemented.
- The repository follows a trunk-based model: `main` is the verified production state and moves forward only once a milestone has been validated in production, so the "live" list above reflects what is safe to deploy today. See [Development and Deployment](../../README.md) for the release-tag and rollback mechanics.
