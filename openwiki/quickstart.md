---
type: "Reference"
title: "Quickstart & Task Routing"
description: "Thirty-second orientation for an agent in the BillCollector repository: the two coexisting operating modes (cron batch engine vs NiceGUI daemon), the four run-and-verify commands with their expected outcomes, the task-routing table that maps each change to the wiki page to read or update, and the hard rules from CONTRIBUTING.md."
tags: [quickstart, task-routing, batch-engine, nicegui-daemon, verification, contributing]
sources:
  - id: openwiki-source-34ac71861bffa2962326b678
    resource: repo://apps/BillCollector.py
  - id: openwiki-source-86ee9334c9ad3a8fdac56ec7
    resource: repo://apps/billcollector/cli.py
  - id: openwiki-source-58c3d08734ec573678b14253
    resource: repo://apps/billcollector/runner.py
  - id: openwiki-source-d310a615e529c21567d5f4fa
    resource: repo://apps/requirements-dev.txt
  - id: openwiki-source-cb5ad5bebf6e21b3122ebeda
    resource: repo://BillCollector.sh
  - id: openwiki-source-f317ee207e1653d2033c81a4
    resource: repo://CONTRIBUTING.md
  - id: openwiki-source-9cc8d292f87ef9f0570b35d9
    resource: repo://install_local.sh
  - id: openwiki-source-e44eab9a26f9187df819fc2a
    resource: repo://pytest.ini
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
generated: { by: "openwiki/0.7.2", at: "2026-10-18T05:11:23.466Z" }
---


# Quickstart & Task Routing

You have a task for BillCollector. This page orients you in 30 seconds — what the two operating modes are and where each lives — then points you at the commands to run and verify anything, the routing table for "which page do I read / update", and the hard rules the repository enforces.

## Two operating modes

BillCollector has two modes that coexist in one repository and one SQLite file (`apps/db/bc.db`):

1. **Batch mode (cron)** — a one-shot, headless collection run: `BillCollector.sh` (flock guard + `docker run` of `billcollector:latest`) -> `apps/BillCollector.py` -> `apps/BillCollectorServices_pw.py`, with Playwright-driven headless Chromium and legacy per-run tables in the DB. This is the production-cron path.
2. **Daemon mode** — a long-running NiceGUI server plus isolated runner subprocesses: `python3 -m billcollector serve` (UI on port 8000, scheduler, orchestrator) and `python3 -m billcollector run <task_id>` (one task run in its own process). Everything lives in `apps/billcollector/`, including the pause/intervention subsystem.

Both modes share the data layer, the vault client, the recipe files, and the helpers. Before touching anything, read [Architecture Overview](architecture/overview.md) for the component map and top-level invariants, then route with the table below.

## Run and verify

Four commands cover install, run, and verification. Every command states its expected outcome; all are grounded in [README.md](../README.md) and [CONTRIBUTING.md](../CONTRIBUTING.md).

### 1. Local setup (one time)

From the repository root:

```bash
bash install_local.sh playwright
```

**Expected result:** a Python virtual environment at `apps/.venv` with the pinned dependencies from `apps/requirements.txt`, Playwright's Chromium + ffmpeg installed into the repository-local `apps/browser/`, and the Chrome system dependencies installed. The script prints the re-activation command (`cd apps && source .venv/bin/activate`). It is tested on Ubuntu 24.04 LTS and WSL2 and requires root/sudo.

### 2. One batch run

Docker path (the production cron path): after configuring `apps/.env` from `.env.example` (at minimum `BW_API_URL`) and building the image once with `./install_docker-image.sh` (produces `billcollector:latest`), from the repository root:

```bash
./BillCollector.sh bc_default.ini
```

**Expected result:** exit `0` with every service/user pair of the INI run headless, documents stored in `apps/Downloads`, and step-by-step records in `apps/db/bc.db`. Exit `1` if any service/user pair fails (a failed pair aborts only itself, the rest continue) or if the vault preflight fails; a second concurrent start is rejected immediately by the `flock` guard on `apps/.bc.lock`.

Local headed debug (no Docker), from `apps/`:

```bash
python3 BillCollector.py bc_test.ini debug
```

**Expected result:** Chromium runs headed so you can watch the run; every step is recorded in `apps/db/bc.db` together with the interactive elements found on the page — use those records to identify and fix failing steps.

### 3. One daemon run

From `apps/`:

```bash
python3 -m billcollector serve
```

**Expected result:** the daemon binds `127.0.0.1:8000` (host overridable via `BC_UI_HOST`). The first start shows a set-password form; afterwards you sign in with that password. On first start the INI `[Playwright]` sections are imported into the Task table, and the dashboard lists the tasks. Run actions (Run now / Stop) go through the orchestrator, which spawns `python3 -m billcollector run <task_id>` as an isolated subprocess:

```bash
python3 -m billcollector run <task_id>
```

**Expected result:** one standalone task run — display allocation, vault preflight, recipe validation, step loop — with the `Run` row finalized in the DB. Exit `0` on success, exit `1` on any run failure (missing task, invalid recipe, display, vault, or step failure).

### 4. The regression harness

The self-contained test environment drives the **production** scraping engine against a local mock portal instead of real web services. From the repository root:

```bash
apps/.venv/bin/python tests/run_regression.py --ini tests/bc_regression.ini
```

**Expected result:** exit `0` — all per-pair expectations matched (engine return value, DB rows, downloaded files, exit semantics). This is the command [CONTRIBUTING.md](../CONTRIBUTING.md) names for verifying a change. Exit codes: `1` at least one expectation deviated · `2` the mock portal could not be started · `3` a real BillCollector run holds the run lock · `4` the `--vault` preflight failed. Useful options: `--ini tests/bc_regression_happy.ini` (success-only scope) and `--vault` (end-to-end mode against a real, provisioned Vaultwarden; the default mode needs no vault).

The pytest suite (`apps/.venv/bin/python -m pytest tests/ -q`, expected: exit `0`, all tests pass) and the Docker build-context canary check live on [Testing and Verification](testing/verification.md) with their exact expected results.

## Task routing

| Task | Read first | Also update |
| --- | --- | --- |
| Change a recipe (YAML automation for a portal) | [Recipe System](concepts/recipes.md) | Only if the **recipe contract** itself changes: [Shared Interfaces](architecture/shared-interfaces.md) — and open an issue first |
| Change the DB schema | [Shared Interfaces](architecture/shared-interfaces.md), [Architecture Overview](architecture/overview.md) | Open an issue first, then [Shared Interfaces](architecture/shared-interfaces.md), [Architecture Overview](architecture/overview.md), and [Testing and Verification](testing/verification.md) (the harness reads the batch tables back) |
| Touch the pause/control flow | [Pause, Intervention & Recipe Repair](workflows/pause-repair.md), [Shared Interfaces](architecture/shared-interfaces.md) (control protocol), [Run Lifecycle](workflows/run-lifecycle.md) | [Pause, Intervention & Recipe Repair](workflows/pause-repair.md); [Shared Interfaces](architecture/shared-interfaces.md) if the protocol changes; [Run Lifecycle](workflows/run-lifecycle.md) |
| Change a UI page | [Web UI Pages](ui/web-ui.md) | [Web UI Pages](ui/web-ui.md) |
| Change the Docker image | [Development and Deployment](operations/deployment.md), [Testing and Verification](testing/verification.md) (context check) | [Development and Deployment](operations/deployment.md); run `python3 tests/check_docker_context.py` (expected: `Docker context: 19 private canaries excluded, 5 source files retained`) |

## Hard repo rules

From [CONTRIBUTING.md](../CONTRIBUTING.md) — these are enforced, not style advice:

- **Shared-interface change needs an issue.** The database schema, the control protocol, the recipe contract, and the process exit codes are shared interfaces. A change to any of them is agreed in an issue before code, and the PR that touches one references that issue. Open an issue before starting a feature — and always before touching a shared interface.
- **Tests prove the PR.** There is no CI pipeline; changes are validated in the local regression test environment and in production runs. Every PR ships with a test or check that proves the behaviour (a regression scenario, a unit test, a schema validation, or a documented manual run) and states the command to run and the expected result.
- **No secrets.** Nothing secret in logs, tests, or artifacts — recipes, config samples, test data, screenshots. No new network exposure (ports, services, outbound endpoints) without review.
- **Small PRs, trunk-based.** One focused change per PR, targeting `main` (the published production state; release tags mark validated releases). AI-assisted code is welcome — declare it in the PR and own it in review.

## Where to go next

- [Architecture Overview](architecture/overview.md) — the two modes, shared components, and top-level invariants.
- [Shared Interfaces (Contracts)](architecture/shared-interfaces.md) — the four contracts a PR must not break without an issue.
- [Roadmap: Daemon Migration Status](architecture/roadmap.md) — what is live and what is deliberately open.
- [Recipe System](concepts/recipes.md) — anatomy and mechanics of the YAML recipes.
- [Vault Transport and Security](concepts/vault-transport.md) — how BillCollector reaches the local `bw serve` API, and what it refuses.
- [Run Lifecycle](workflows/run-lifecycle.md) — scheduling, locking, and step recording end to end in both modes.
- [Pause, Intervention & Recipe Repair](workflows/pause-repair.md) — the runner's pause subsystem and the repair workflow.
- [Web UI Pages](ui/web-ui.md) — one section per UI page: purpose, state, actions.
- [Testing and Verification](testing/verification.md) — every check with its exact command and expected result.
- [Development and Deployment](operations/deployment.md) — the install, image-build, and remote-deploy scripts.
