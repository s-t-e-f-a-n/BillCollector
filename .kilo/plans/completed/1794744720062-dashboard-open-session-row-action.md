# Dashboard — per-row "Open session" action (option C)

> Status: DELIVERED (2026-11-15) — W1–W4 in place (code + tests); ruff +
> full pytest green, review approved; manual check passed (the user
> confirmed the action in both run states). UI-only change, single file
> (`apps/billcollector/ui/dashboard.py`) + one test file. Label decided:
> **"Open session"** (not "Session") to match the task-detail link and avoid
> colliding with the dashboard's existing "Session" column.

Source: the user chose **option C** from the four dashboard options presented
in the prior session (make the step-strip label a link / a persistent
followed-run link / **a per-row Session button in the Actions column** / the
task-detail run-history link). C is the most discoverable: an action like the
existing Run now / Stop / Edit buttons, enabled only while the row is
`running`/`waiting`, resolving the row's active run id from
`db.list_active_runs()`.

## Verified context (dev tree, 2026-11-15)

- **Actions column + row-action plumbing** (`dashboard.py:91-110`, `ROW_BODY`):
  the table body slot renders, per row, a `q-btn` for **Run now**
  (`dashboard.py:98-100`), **Stop** (`:101-103`), and **Edit** (`:104-105`).
  Each button dispatches a **bubbling** `CustomEvent('rowaction', {detail:
  {action, id, task}})` with `.stop` (so a click never also triggers the
  row's task-detail navigation). `table.on("rowaction", on_row_action,
  js_handler="(event) => emit(event.detail)")` (`dashboard.py:416-417`) lands
  the bare `detail` payload on the server.
- **Handler** (`on_row_action`, `dashboard.py:379-407`): branches on
  `detail["action"]` for `run` / `stop` / `edit`, then calls `refresh()`.
  `edit` already `return`s early (it opens a dialog).
- **Navigation precedent**: `on_row_click` (`dashboard.py:331-338`) uses
  `ui.navigate.to(f"/tasks/{row['id']}")` (same-tab). The task-detail pause
  card already offers exactly this action as a **`ui.link("Open session",
  f"/runs/{run['id']}")`** (`task_detail.py:281-283`). The session page is
  registered at `/runs/{run_id}` (`session.py:267`) and its header is
  `ui.label(f"Run {run_id}")` (`session.py:279`).
- **Run-id source** (`db.list_active_runs()`, `db.py:421-425`): all runs with
  `result IS NULL`, ordered `id ASC`. Each row carries `task_id`. The
  orchestrator's claim keeps at most one live run per task, so the map
  task_id → newest active run id is well-defined.
- **Row dict** (`build_rows`, `dashboard.py:167-198`): one dict per task with
  `id, service, user, task, status, login_blocked, login, last_run, next_run,
  session, last_download`. Extra dict keys are **not** rendered as cells (the
  body slot only renders `COLUMNS` fields), so adding a key is safe. `status`
  is one of `idle`/`running`/`waiting` (`STATUSES`, `dashboard.py:50`).
- **Existing "Session" column** (`COLUMNS`, `dashboard.py:64`; `_session_cell`,
  `dashboard.py:144-154`): shows profile present / last used / last reset.
  This is why the button label is "Open session", not "Session".
- **Test harness** (`tests/test_bc_ui_dashboard.py`): `_seed` (`:68-91`)
  creates `svc-a/user1` idle (a finished run + download), `svc-b/user1`
  running (an active run, `seed["run_running"]`, `result IS NULL`), and
  `svc-a/user2` waiting (a paused active run). Row-action tests trigger
  `rowaction` on `user.find(kind=ui.table)` and `_wait`/`should_see` for the
  effect (`:324-358`). The row-click navigation test
  (`test_row_click_navigates_to_the_task_detail`, `:247-255`) is the
  `should_see(<target page text>, retries=10)` precedent for a navigation
  assertion.

## Design

Add a per-row **Open session** button to the dashboard Actions column that
navigates to the run's session page (`/runs/<run_id>`), enabled only while the
row is `running`/`waiting`.

- The row's **active run id** is resolved server-side in `build_rows` and
  carried on the row dict as `active_run_id` (the slot template cannot query
  the DB). It is the newest `result IS NULL` run for the task, else `None`.
- The button reuses the existing **`rowaction` CustomEvent** plumbing (not a
  plain anchor), so it is consistent with Run now / Stop / Edit and testable
  the same way.
- The handler navigates **same-tab** via `ui.navigate.to(f"/runs/{run_id}")`
  — the same mechanism `on_row_click` uses for `/tasks/<id>`, and the same
  destination the ntfy deep link and the task-detail "Open session" link
  target. The session page is a full intervention page (Copilot + noVNC), so
  it takes over the tab; the operator returns via the browser back button or
  the layout nav.

## Work items

### W1 — `build_rows`: carry the active run id

`apps/billcollector/ui/dashboard.py`, `build_rows` (`:167`):

1. Before the row loop, build `active_by_task` from `db.list_active_runs()`:
   iterate in order and set `active_by_task[run["task_id"]] = run["id"]`
   (the `id ASC` order means the last write per task is the newest active
   run).
2. In each appended row dict, add
   `"active_run_id": active_by_task.get(task["id"])` (so `None` when the task
   has no live run).

### W2 — `ROW_BODY`: the Open session button

`apps/billcollector/ui/dashboard.py`, `ROW_BODY` actions span (`:97-106`):
add a fourth `q-btn` after **Edit**:

```
<q-btn size="sm" label="Open session"
       :disable="!(props.row.status === 'running' || props.row.status === 'waiting') || !props.row.active_run_id"
       @click.stop="$event.currentTarget.dispatchEvent(new CustomEvent('rowaction', {detail: {action: 'session', id: props.row.active_run_id, task: props.row.task}, bubbles: true}))"/>
```

- Label **Open session** (no `color`, consistent with the neutral **Edit**
  button; the color is a minor style choice and can be `positive` if a
  distinct "observe" tint is wanted).
- `:disable` is `running`/`waiting` **and** a non-null `active_run_id` — a
  strict superset of the spec's "enabled only when running/waiting", which
  also prevents a dead click in the transient window where the status flips
  but the Run row is not yet/any longer active.

Update the `ROW_BODY` comment block (`:69-90`) to name the fourth action.

### W3 — `on_row_action`: the session branch

`apps/billcollector/ui/dashboard.py`, `on_row_action` (`:379`): add a branch
before the trailing `refresh()`:

```
elif detail.get("action") == "session":
    run_id = detail.get("id")
    if run_id is None:
        ui.notify(f"{detail.get('task')}: no active run", type="warning")
        return
    ui.navigate.to(f"/runs/{run_id}")
    return
```

- `return` (do **not** fall through to `refresh()`): the navigation leaves the
  page.
- The `None` guard covers the edge where the status still reads active but the
  Run row was just finalized; it is a warning, not an exception, and
  self-heals on the next ~2 s poll.

Update the `on_row_action` docstring (and the module docstring, `:1-32`) to
mention the **Open session** row action.

### W4 — tests

`tests/test_bc_ui_dashboard.py`:

1. **Run-id resolution** (goes through the real render path via the table
   rows, no scheduler needed):
   ```
   rows = {r["id"]: r for r in _table_rows(user)}
   assert rows[seed["running"]]["active_run_id"] == seed["run_running"]
   assert rows[seed["waiting"]]["active_run_id"] is not None
   assert rows[seed["idle"]]["active_run_id"] is None
   ```
   (The waiting run id is the newest `result IS NULL` run of that task, so
   `is not None` pins it without needing the seed to expose the inline-created
   run id; optionally fetch it via `testdb.list_active_runs()` to assert the
   exact id.)
2. **Navigation** (the rowaction → session-page contract, mirroring
   `test_row_click_navigates_to_the_task_detail`):
   ```
   user.find(kind=ui.table).trigger(
       "rowaction",
       {"action": "session", "id": seed["run_running"], "task": "svc-b / user1"})
   await user.should_see(f"Run {seed['run_running']}", retries=10)
   ```
   (The session page header `ui.label(f"Run {run_id}")` is the assertion
   target; `run_running` is `result IS NULL` with no pause, so it renders the
   running state.)

## Validation

- From the repo root (`PYTHONPATH=apps`): `ruff check` and `pytest` — the full
  suite green (the dashboard tests are extended, not bypassed).
- **Manual check (user, both run states)** — per the project's UI-change flow:
  start a run and confirm the **Open session** button appears enabled for the
  `running` row and, after a pause, for the `waiting` row; clicking either
  lands on `/runs/<run_id>` (session page). Confirm the button is disabled for
  `idle` rows and that a click never also navigates the row to the task
  detail (`.stop` is preserved).

## Risks / notes

- **Transient status ↔ run-id mismatch**: a `running`/`waiting` row whose Run
  row is momentarily absent (finalizing) renders an enabled-but-guarded
  button; the handler's `None` guard warns and the ~2 s poll corrects it. No
  crash, no dead end.
- **`active_run_id` is not a `COLUMNS` field**, so it is never rendered as a
  cell — it is carried on the row object solely for the button.
- **Same-tab navigation** leaves the dashboard (the log pane / step strip are
  gone until the user returns). This matches the ntfy deep link and the
  task-detail "Open session" link; a new-tab (`ui.open`) variant would be a
  one-line change to the handler if the operator prefers to keep the dashboard
  visible.
- **Label collision resolved**: the button is "Open session" (decided),
  distinct from the "Session" column.

## Out of scope

Options **A** (step-strip label link), **B** (persistent followed-run link),
and **D** (task-detail run-history link to ended runs) from the same
discussion — not requested here. The session page itself, auth, and the
row-action plumbing are unchanged.
