# Manual pause — "Pause" row action (dashboard + task detail)

> Status: PENDING (2026-11-15) — planned; not started. Independent lane;
> implement on `dev` after the C6 noVNC rollout closes (or whenever the user
> schedules it). Motivation context: the C6 rollout step 2 #6 (ntfy deep
> link) needs a pausing run to verify; a manual pause makes the whole
> pause → ntfy deep link → noVNC → resume loop testable on demand.

## Motivation

- Intervention is currently only possible when the portal itself triggers a
  pause (`step_failed` / `login_failed` / `download_failed` / `wait_user`).
  A run stuck on a page the runner does not recognize can only be killed
  (Stop) — there is no non-destructive lever.
- A manual pause gives the operator: pause → intervene via the noVNC tab on
  the session page → resume (or cancel), without losing the run.
- It makes the pause/intervention loop deterministically testable (manual
  test of the C6 rollout step 2 #6, and future regression tests).

## Design (decided)

1. **Triggers** — a "Pause" button on the dashboard row (`ROW_BODY`,
   next to Stop) and on the task detail page (next to Stop,
   task_detail.py:174). Both enabled only while the run status is
   `running` — never `waiting` (an already-paused run is controlled via
   the existing session-page resume/cancel controls).
2. **Wake-up channel** — `orchestrator.pause_run(task_id)` sends
   **SIGUSR1 to the runner's pid only** (`proc.send_signal`), not the
   process group: the group contains the Playwright node driver, and node
   reserves SIGUSR1 for the V8 inspector. Mirrors `stop_run`
   (orchestrator.py:279) — same `self._processes` lookup and
   returncode check — but signal-and-return: no wait, no SIGKILL
   escalation. Sync method (nothing to await); returns False when the
   task has no live runner.
3. **Runner side** — `_install_signal_handlers` (runner.py:114) gains a
   SIGUSR1 handler that sets a module-level flag (flag-set only; safe
   whenever a signal lands, even inside a blocking Playwright call).
   The flag is reset at run start in `_run_task`. The step loop in
   `_run_recipe` (runner.py:1010) checks the flag at the top of each
   iteration, before the login / wait_user / regular dispatch.
4. **Effect semantics** — pause at the **next step boundary**.
   Mid-step interruption is out of scope (an in-flight Playwright call or
   download cannot be unwound safely; that is what Stop is for). Edge
   cases:
   - flag set after the last step: the run completes normally, flag
     dropped (document this in the button's tooltip/docstring);
   - flag set while a portal pause is active: it takes effect at the next
     boundary after resume — harmless (button disabled while `waiting`
     makes this a narrow residual race that at worst re-pauses).
5. **Reuse the pause machinery as-is** — call
   `pause_loop(ctx, "manual", <prompt>, None, None)` (pause.py:252). It
   already: persists the pause (`persist_pause` → Run pause fields, task
   status, row turns amber `waiting`), pushes ntfy with the
   `<ui_base_url>/runs/<id>` deep link (`notify_pause`; only when
   `ntfy_topic` is set), serves the control socket (resume/cancel +
   element actions from the session page), and enforces
   `pause_deadline_seconds`. No pause.py changes expected.
6. **Outcomes** — existing mapping, unchanged: resume → continue at the
   next step (no re-execution — nothing failed); cancel → run result
   `cancelled`; timeout → run result `needs_attention`
   (`PauseOutcomeAbort` + `derive_outcome`, runner.py:181-184).

## Tasks

1. `apps/billcollector/runner.py`
   - Module-level `MANUAL_PAUSE_REQUESTED` flag; SIGUSR1 handler in
     `_install_signal_handlers` sets it (docstring: flag-set only,
     distinct from the SIGTERM/SIGINT abort handler); reset it in
     `_run_task` after the handlers install.
   - `_run_recipe`: at the top of the per-step loop, if the flag is set:
     clear it, `outcome = pause_loop(ctx, "manual", "Paused manually.
     Resume to continue at the next step.", None, None)`; on
     `"resume"` → `continue`, else `raise PauseOutcomeAbort(outcome)`.
2. `apps/billcollector/orchestrator.py`
   - `pause_run(task_id) -> bool` (sync) as decided above; update the
     module docstring's lifecycle list.
3. `apps/billcollector/ui/dashboard.py`
   - `ROW_BODY`: Pause button between Stop and Edit,
     `:disable="props.row.status !== 'running'"`, dispatching
     `{action: 'pause', id: props.row.id, task: props.row.task}`.
   - `on_row_action`: `pause` branch → `orchestrator.pause_run(task_id)`;
     on False → `ui.notify("no live runner", warning)`; then `refresh()`
     (same immediate-refresh path as Stop). Update the comments.
4. `apps/billcollector/ui/task_detail.py`
   - Pause button beside Stop (`.mark("detail-pause")`), handler calling
     `orchestrator.pause_run(task_id)` (mirror the detail Stop,
     task_detail.py:201-202); include it in the enabled/disabled state
     logic (~line 441). Update the module docstring.
5. Tests
   - `tests/test_bc_runner.py`: flag set before step 2 (fake recipe/ctx)
     → run pauses (Run row `waiting`, `pause_reason == "manual"`),
     resume → run continues and succeeds; flag set after the last step →
     run completes, flag dropped.
   - `tests/test_bc_pause.py`: `build_pause_context` with the manual
     reason (`step_action_json=None`, `error=None`) — payload shape
     (mostly covered; assert the `manual` reason path).
   - `tests/test_bc_orchestrator.py`: `pause_run` → True and SIGUSR1
     delivered to the pid only (fake proc records the signal; assert the
     group signal path is not used); False without a live runner.
   - `tests/test_bc_ui_dashboard.py`: rowaction `pause` routes to
     `pause_run` (mirror `test_stop_calls_stop_run`, line 347); button
     disabled while `waiting`.
   - `tests/test_bc_ui_task_detail.py`: detail Pause routes to
     `pause_run` (mirror `test_detail_stop_routes_to_stop_run`, line 214).
6. Docs — CHANGELOG entry (user-visible feature); one line next to the
   documented Stop behaviour (README dashboard section /
   doc/QUICKSTART.md, whichever covers row actions).
7. Commits via the dev-commits flow (user-confirmed per item):
   `feat: dashboard + task detail — manual pause row action (SIGUSR1,
   pause at next step boundary)`, `test: manual pause — runner boundary,
   orchestrator signal, UI routing`, `doc: manual pause — changelog +
   row action docs`.

## Validation

- `ruff check` clean on all changed files.
- Targeted suites: test_bc_runner, test_bc_pause, test_bc_orchestrator,
  test_bc_ui_dashboard, test_bc_ui_task_detail.
- Full suite (baseline 2026-11-15: 859 passed / 11 skipped).
- Manual (user-gated, NAS or dev box with a display): start a winsim run
  → Pause (dashboard row, then task detail) → row turns amber `waiting`
  + pause banner on the detail page; with `ntfy_topic` + `ui_base_url`
  set, the ntfy push arrives with the deep link → tap on the phone →
  session page → resume from the session page → run continues; also
  cancel → run ends `cancelled`. This manual pass doubles as the C6
  rollout step 2 #6 (ntfy deep link) validation.

## Out of scope

- Mid-step interruption (Stop remains the abort path).
- Pause via API / ntfy / CLI.
- Changes to the session page's resume/cancel or element-action controls
  (the existing ControlServer path is reused unchanged).
