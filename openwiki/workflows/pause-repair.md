---
type: concept
title: Pause, Intervention & Recipe Repair
description: The pause loop, versioned control socket, and operator intervention flow for stuck runs - why a non-graceful step or failed download pauses instead of aborting, how the machine-readable context is persisted, and the repair flow through the UI recipe editor.
tags: [pause, intervention, recipe-repair, control-socket, operator, daemon]
sources:
  - id: openwiki-source-34ac71861bffa2962326b678
    resource: repo://apps/BillCollector.py
  - id: openwiki-source-86ee9334c9ad3a8fdac56ec7
    resource: repo://apps/billcollector/cli.py
  - id: openwiki-source-b6ba4edf64def9af03c073a0
    resource: repo://apps/billcollector/db.py
  - id: openwiki-source-6418ec65e2eba9db707a49a3
    resource: repo://apps/billcollector/display.py
  - id: openwiki-source-57d6945f2689dab53a7a6cfe
    resource: repo://apps/billcollector/interrupt.py
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
  - id: openwiki-source-aa0ab29b01ed3aa57cdc6fe4
    resource: repo://apps/billcollector/vault.py
  - id: openwiki-source-fc295667ed75ad936044dfa4
    resource: repo://apps/BillCollectorServices_pw.py
  - id: openwiki-source-528c5488ea5a4fff1964130e
    resource: repo://apps/helpers/BillCollectorHelpers.py
  - id: openwiki-source-cb5ad5bebf6e21b3122ebeda
    resource: repo://BillCollector.sh
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
generated: { by: "openwiki/0.7.3", at: "2026-10-28T00:00:00.000Z" }
---

# Pause, Intervention & Recipe Repair

BillCollector does not abort on a stuck step or a failed download - it pauses the run and hands control to the operator through a versioned control-socket protocol. The pause context is stored on the Run row and becomes the single source of truth for repair.

## Why pauses instead of aborts

Three conditions trigger a pause instead of aborting the entire run:

| Entry point | Reason | Triggered when |
| --- | --- | --- |
| `_execute_step_with_pause` | `step_failed` | a non-graceful step exhausts its `MAX_STEP_ATTEMPTS` (3) attempts |
| `_handle_download_with_pause` | `download_failed` | the `expect_download` window's download fails or times out |
| `_execute_wait_user_step` | `wait_user` | a `wait_user` step pauses **before** execution (one-shot portal interactions such as entering a CAPTCHA) |

The rationale: pausing keeps the rest of the recipe alive and lets the operator fix the root cause (page change, recipe bug, credential issue) without losing the entire run's progress.

## Pause lifecycle

1. **Pause entered** — the runner's main thread blocks serving a versioned Unix control socket (`control_sock_path`, `<run_id>.sock` under `<data>/runs/<run_id>/`).

2. **Context persisted** — `pause.py` builds a machine-readable payload and writes it to the Run row's `pause_*` columns (`pause_reason`, `pause_prompt`, `pause_context`, `pause_deadline_at`). The task is flipped to `waiting` so the scheduler cannot re-trigger the same run.

3. **ntfy deep link** — if `ntfy_topic` is set, an ntfy push notification is sent with a deep link to the session page (`/runs/<run_id>`).

4. **Operator actions** — the operator uses the session page's intervention UI to:
   - **Resume** — re-execute the paused step with a fresh attempt budget (non-graceful steps get 3 attempts again; graceful steps are single-attempt).
   - **Cancel** — end the run with `Run.result = cancelled` and exit code `1`.
   - **Deadline timeout** — if `pause_deadline_seconds` (default 1800 s) is exceeded without action, the run ends with `Run.result = needs_attention`.

5. **Run finalization** — after resume, cancel, or timeout, the runner's teardown finalizes the Run row and flips the task back to `idle`.

## Control-socket protocol v1

The control socket is a Unix domain socket. The operator connects and sends a JSON command:

| Command | Effect |
| --- | --- |
| `{"action": "resume"}` | Re-execute the paused step. |
| `{"action": "cancel"}` | End the run with result `cancelled`. |
| `{"action": "set_element", "element_n": 3, "new_value": "button"}` | Edit the locator of step element 3 (recipe repair). |

The protocol version is declared in `apps/billcollector/control.py` as `PROTOCOL_VERSION = 1`. A version bump requires a doc update on this page and a compatible runner update.

## Recipe repair from a paused run

Opened from the session page with `?run=<run_id>`, the recipe editor preloads the failure panel from the run's pause context:

- Failure screenshot
- Failed step number and error
- Candidate element rows with a "Use" button that rewrites the failed step's locator prefix (`apply_candidate_to_step`) into the existing validate → save → git-commit flow.

Repair changes the recipe YAML file under `apps/recipes_playwright/` and (optionally) commits the change. The next resume of the paused run uses the repaired recipe.

## Known pitfalls

- A consumed `wait_user` step's prompt cannot be re-entered on resume — it is consumed once and forgotten.
- Changing the `pause_deadline_seconds` setting does not affect an already-active pause; it only applies to future pauses.
- The control socket is bound to the runner's subprocess; killing the runner from outside (SIGKILL) prevents the operator from resuming — the run will finalize with `result=needs_attention` or `result=cancelled` depending on timing.
- `pause_context` must remain complete, stable, and small (AI-integration contract, decision 20). Adding fields requires a protocol version bump in `control.py`.

## Verification

- Start a run that hits a non-graceful step failure three times, then use the UI to resume it — the step should re-execute with a fresh budget.
- Start a run with a `wait_user` step, enter a prompt value, then resume — the step should be consumed and the run should continue.
- Start a run that exceeds `pause_deadline_seconds` without operator action — the run should finalize with `result=needs_attention`.