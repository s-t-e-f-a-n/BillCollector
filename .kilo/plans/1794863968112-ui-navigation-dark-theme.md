# UI Navigation, Icon Actions & Manual Pause

> The file name predates the 2026-11-16 split: the dark-theme half moved to the
> companion plan `.kilo/plans/1794866943286-ui-dark-theme.md` (ships later).
> Refined 2026-11-17: settings single-Save restructure (N9 rewritten, the
> per-key Saves are gone), the table-column convention (N17),
> run-review reachability (N4/N5 — the session page's ended view was the
> one truly hidden page in the route inventory), and the waiting-state
> **Resume**/enabled-**Stop** (N4/N5 — after NAS validation, the user
> asked for the paused run to be resumable and stoppable directly from
> the row/detail buttons, superseding the locked "waiting → disabled"
> decision).

## Goal

One UI pass on the current light skin (no theme changes):

1. **Navigation** — restructure the left drawer to 5 items; new `/tasks` and
   `/recipes` index pages; menu highlighting on the detail pages.
2. **Icon actions** — all action buttons become icon buttons with hover
   tooltips (mouse-over text); text is kept only where it is functional.
3. **Manual pause** — the SIGUSR1 pause-at-next-step-boundary feature, merged
   in because the running-state Run button morphs into the pause control.
4. **Settings single Save** — the settings page is restructured into grouped
   cards with one Save button for all daemon settings (N9).
5. **Table convention** — one alignment/label/mono convention across all
   tables (N17), used by the new index pages from the start.
6. **Run review** — the dashboard row button and the task-detail run history
   link to any run, live or ended, so the session page's ended view is
   reachable from the UI (N4/N5).

All UI text stays English.

## Locked decisions (planning sessions 2026-11-16)

- **Split**: dark-theme layer (theme.py, `ui.dark_mode`, chrome reskin,
  header icon/version chip/"Daemon active" pill, KPI strip, grey-class
  audit, CodeMirror, login restyle) is a separate follow-up plan, shipped
  after this one. Header stays as-is (plain "BillCollector" label) in this pass.
- **Drawer**: 5 items (order, icons): Dashboard `/` (`dashboard`), Tasks
  `/tasks` (`list`), Recipes `/recipes` (`code`), Downloads `/downloads`
  (`download`), Settings `/settings` (`settings`). Existing light chrome
  (`bg-slate-100`, active `bg-blue-200`) is kept. No other entries: `/login`
  is public, `/onboarding` auto-forced, `/runs/<run_id>` deep-link-only.
- **New pages**: `/tasks` (task index) and `/recipes` (recipe index). The
  wireframe's "Verlauf / Vaultwarden / Logs" entries stay rejected (no such
  pages exist).
- **Icons everywhere possible, minimal text, hover tooltips on every icon
  button** (user decision). Icon set: classic **Material Icons**, which are
  bundled locally in NiceGUI (`nicegui/static/fonts.css`) and therefore
  offline-safe; **Material Symbols are NOT bundled** — do not fetch or vendor
  a Symbols font in this pass (a theme-pass concern if ever wanted).
- **Icon-vs-text rules**:
  - R1 dense row actions (dashboard row, downloads row, session element
    actions, recipe failure-panel "Use"): icon-only + tooltip.
  - R2 page toolbars: icon-only + tooltip, except functional labels
    ("Run (filtered)" keeps its label — the scope depends on the active
    filters).
  - R3 dialogs: Cancel → `close` icon-only + tooltip; the confirm verb keeps
    text only when destructive or nuanced (Reset, "Allow one attempt",
    "Cancel run"); Save/Retry → icon-only + tooltip.
  - R4 onboarding wizard: icon + label (first-run orientation).
  - R5 navigation links (drawer, "Task N:" breadcrumb, "Repair recipe",
    "Recipe"): text kept, icon added where it adds clarity.
  - Data labels stay text: the recipe page's per-task run button shows the
    username + a play icon.
- **Manual pause merged** (user decision): the machinery follows
  `.kilo/plans/1794763657924-manual-pause-button.md` (runner SIGUSR1 flag,
  `orchestrator.pause_run`, reuse of `pause_loop`); that plan's UI tasks
  (#3/#4, a separate "Pause" button) are superseded by the morphing
  Run/Pause icon buttons below; the plan is marked CONSUMED and archived to
  `completed/` when this plan is implemented.
- **Waiting-state Resume + enabled Stop** (user decision, 2026-11-17, after
  NAS validation): a manually paused run (task `waiting`) can be resumed or
  stopped directly from the dashboard row and the task detail — the morphing
  button morphs back to **Resume** (play_arrow, tooltip "Resume run", enabled)
  and sends the paused run's control socket the protocol `resume` (the
  session page's own path, M3 decision 4); **Stop** is enabled while the run
  is running **or** waiting (the runner process stays alive while paused).
  Supersedes the original N4/N5 spec ("waiting → disabled; resume via the
  session page").
- **Settings single Save** (user decision, 2026-11-17): the settings page
  is restructured into grouped cards (Security / Notifications / Runs /
  Storage & session / Vault / Git); one Save button covers all daemon
  settings with all-or-nothing validation; the UI password keeps its own
  "Change password" action (it needs the confirm field). Supersedes the
  per-key Save buttons (and N9's original per-section icon-Save scope).
- **Table convention** (user decision, 2026-11-17): numeric columns and the
  Actions column are right-aligned, everything else left (timestamps
  included); the service/user pair column is labelled "Task" in every
  table; technical cells (timestamps, cron, SHA, filenames, run ids,
  numbers) render mono via a `mono` column flag consumed by the body
  slots. Applied to the existing dashboard / downloads / task-detail
  step tables and built into the new index pages (N17).
- **Run review reachability** (user decision, 2026-11-17): the session
  page's ended view (result, notes, last pause context read-only, Repair
  recipe link) is reachable from the UI — the dashboard row button becomes
  a generic **View run** (the task's newest run, active or ended) and the
  task-detail run history gains a per-run View run link. No new page: the
  global Runs page ("Verlauf") was reconsidered and stays rejected.
- **Scope** (refined 2026-11-17): the session state machine and the recipe
  editor flow are unchanged. The dashboard table keeps its 8 columns and
  its row shape (only the 4th row button's semantics change: Open session
  -> View run, N4); the settings page structure changes (N9); the tables
  gain alignment/mono classes (N17) without changing their row data.

## Verified environment facts (NiceGUI 3.17.1 in `apps/.venv`)

- `ui.button(text='', icon=...)` is a first-class API (`IconElement`) —
  icon-only buttons are native; `ui.tooltip` "can be placed in another
  element" → `with btn: ui.tooltip("…")` works on any element.
- Classic Material Icons (+ Outlined/Round/Sharp) bundled locally; the icon
  names used below are all in the classic set: play_arrow, pause, stop, edit,
  open_in_browser, add, save, close, refresh, left_click, text_fields,
  keyboard, open_with, check, check_circle, vpn_key, lock_open, restart_alt,
  dashboard, upload_file, link, arrow_back, arrow_forward, done, description,
  build, list, code, download, settings, cancel.
- **Run results** (`orchestrator.py`): `success`, `failure`, `interrupted`,
  `cancelled`, `needs_attention`; only `success`/`failure`/`needs_attention`
  are conclusive evidence about a recipe.
- **Recipes**: `config.RECIPE_DIR = apps/recipes_playwright`,
  `RECIPE_PREFIX = "recipe-pw__"`,
  `recipe_filename_for(service)` = `recipe-pw__<lower, space→_>.yaml`;
  overlay `config.RECIPE_EXTRA_DIR` (`BC_RECIPE_EXTRA_DIR`) shadows per file
  (`recipe_path_for`); `load_recipe(path)` → `(ok, error, text, data)` with
  the full gate (`check_methods=True`) — cheap pure Python per file.
- **DB/scheduler**: `db.list_runs(task_id=None)` (id DESC),
  `db.list_tasks()`; `Task.next_run` is not maintained — the next fire comes
  from the APScheduler job via `dashboard.next_run(scheduler, task_id)`.
- **Test harness**: `pytest.ini` (`addopts = -p nicegui.testing.user_plugin`,
  `main_file = tests/ui_test_main.py`) → browserless `User` simulation; the
  main file builds the production `build_app` wiring against a fresh temp DB;
  tests seed via a direct `Database` handle, log in via the `/login` POST, and
  assert on `.mark()` ids. UI tests find elements by marker or kind — never by
  label text — and trigger the dashboard `rowaction` CustomEvent with a
  literal payload, so the icon swap is test-safe as long as all `.mark()` ids
  are preserved. Recipe-dir tests point `config.RECIPE_DIR` at a per-test temp
  dir (pattern in `test_bc_ui_recipes.py`).
- **q-table column passthrough** (verified 2026-11-17, `nicegui/elements/
  table.py::_normalize_columns`): the given column dicts are merged verbatim
  (`{**defaults, **column}` with empty defaults by default), so Quasar-native
  keys (`align`) and custom keys (the `mono` flag) survive to the client's
  `props.cols` — a body slot can branch on `col.mono`.

## Tasks

### N1 — Drawer (layout.py)

- `MENU_ITEMS` gains the two pages + icons (5 items per the locked order);
  item rows render icon + label; light chrome and the
  `build_layout(active=...)` signature stay. Header unchanged.

### N2 — `/tasks` index (`apps/billcollector/ui/task_list.py`, new)

- `register_task_index(db, scheduler)`; route `/tasks`, title "Tasks";
  `require_auth` + `build_layout(active="Tasks")`.
- One row per Task, DB poll ~2 s (the app's existing regime): **Task**
  (service/user), **Status** (q-badge: running blue / waiting orange /
  idle grey), **Enabled** (yes/no, muted), **Cron** (mono, `—` if null),
  **Last run** (date + result badge: success green / failure red /
  interrupted+cancelled grey, `—` if none — the task's newest Run row via
  `db.list_runs(task_id)`), **Next run** (`dashboard.next_run(scheduler,
  task_id)`). Columns are built with the N17 convention (`table_column`
  helper; mono on Cron / Last run / Next run, everything left-aligned).
- Sorted by service, then user. Whole row links to `/tasks/<task_id>`
  (row-click navigation, same pattern as the dashboard). No run actions, no
  dialogs — actions stay on the dashboard and task detail.
- Empty state: "No tasks yet." + a link to the dashboard (where the Add task
  dialog lives).

### N3 — `/recipes` index (`apps/billcollector/ui/recipe_list.py`, new)

- `register_recipe_index(db)`; route `/recipes`, title "Recipes";
  `require_auth` + `build_layout(active="Recipes")`.
- New helper in `billcollector/recipes.py`: `list_recipe_files()` → list of
  `(service_key, path, overlay)`; glob `RECIPE_PREFIX + "*.yaml"` in
  `config.RECIPE_DIR`, plus `config.RECIPE_EXTRA_DIR` when set (overlay wins
  for the same key, mirroring `recipe_path_for`). `service_key` = filename
  minus prefix/suffix.
- Display name: the Task-table `service` string when some task's
  `service.lower().replace(' ', '_')` equals the key, else the key with
  `_` → space.
- One row per recipe file: service name (row link → `/recipes/<service>`),
  **Tasks** (count for that service, `0` muted — right-aligned mono, the
  N17 convention), overlay badge (amber
  "overlay") when the file comes from `RECIPE_EXTRA_DIR`, **Valid** badge
  (green "valid" / red "invalid"; tooltip = first error line) computed **once
  on page load** via `load_recipe(path)` (full gate), **Last evidence** badge:
  the newest *conclusive* run (`result IN ('success','failure','needs_attention')`)
  across the service's tasks → green "verified" or red "failing" with the date
  (`YYYY-MM-DD`), badge links to `/runs/<run_id>`; no conclusive run → grey
  "unverified". `interrupted`/`cancelled` are never evidence.
- Flagged rows: Task-table services with **no recipe file** (red "no recipe
  file" badge, task count, no link).
- The ~2 s poll refreshes only the evidence column. Validation is deliberately
  not re-run per poll — recipe files change via the editor (which revalidates
  on save) or git; a page refresh revalidates. State this trade-off in the
  module docstring.

### N4 — Dashboard icon actions (dashboard.py)

- `ROW_BODY` slot template: the four text `q-btn`s become icon-only `q-btn`s
  with a `<q-tooltip>` child each:
  - **Run/Pause/Resume (morphing, one button)**:
    `:icon="props.row.status === 'running' ? 'pause' : 'play_arrow'"`;
    dispatches `action: 'pause'` while running, `action: 'resume'` while
    waiting (with `id: props.row.active_run_id` — the run id, not the task
    id, because the resume goes to that run's control socket), else `'run'`
    (with the task id) — same CustomEvent pattern, `.stop` kept; disable:
    running → enabled (pause), idle → enabled unless `login_blocked`,
    waiting → enabled (the paused run is resumed from the row); color stays
    `primary`; tooltip: "Pause at next step boundary" / "Run now" /
    "Run now (login blocked)" / "Resume run".
  - **Stop**: `icon="stop"`, `color="negative"`, tooltip "Stop run",
    enabled while running **or waiting** (the runner process is still alive
    while paused; SIGTERM ends the run as `interrupted`).
  - **Edit**: `icon="edit"`, tooltip "Edit task (cron, enabled)".
  - **View run** (was Open session — run-review reachability, 2026-11-17):
    `icon="open_in_browser"`, tooltip "View run"; enabled whenever the task
    has *any* run (`:disable="!props.row.active_run_id &&
    !props.row.latest_run_id"`); dispatches `action: 'view-run'` with
    `id: props.row.active_run_id || props.row.latest_run_id` — a live run
    opens the live session view, a finished run the ended view (result +
    last pause context + Repair recipe link). `build_rows` gains
    `latest_run_id` (the task's newest Run row id, `None` when the task
    never ran; the `latest` run is already fetched there for the Last run
    cell). The handler branch navigates to `/runs/<id>` and does NOT
    refresh (the page leaves).
- Toolbar: **Run (filtered)** → `icon="play_arrow"` + label kept (functional);
  **Add task** → `icon="add"` icon-only + tooltip "Add task".
- `on_row_action` gains the `pause` branch: `orchestrator.pause_run(task_id)`;
  on False → `ui.notify("no live runner", warning)`; then `refresh()` (same
  immediate-refresh path as Stop). It also gains the `resume` branch: the
  payload `id` is the run id; `db.get_run(id)` + `control_sock_alive(run)`
  (from `ui.session`) — a dead/missing socket degrades to
  `ui.notify("no active pause to resume", warning)`; otherwise
  `asyncio.to_thread(send_action, run["control_sock"], "resume")` (the
  session page's own path, M3 decision 4) with a `ControlError` catch that
  degrades to a notify ("the run ended while resuming"); then `refresh()`.
  The `session` action becomes `view-run`
  (the row payload key `active_run_id` stays; `latest_run_id` is added).
- Update the module docstring, the `ROW_BODY` comment, and the row-action
  comment block in `app.py` (they enumerate the row actions).

### N5 — Task-detail icon actions (task_detail.py)

- **Run now → morphing icon button** (`mark("detail-run")`, `color=primary`):
  icon `play_arrow` idle/waiting / `pause` while running, updated in the ~2 s
  refresh; the click handler branches on the freshly fetched task status
  (idle → `orchestrator.start_run`, running → `orchestrator.pause_run`,
  waiting → the task's active paused run found via `db.list_active_runs()`,
  `control_sock_alive` + `asyncio.to_thread(send_action, run["control_sock"],
  "resume")` — the session page's own path, with the same dead-socket and
  `ControlError` degrade notifies as N4); tooltip element (child) text
  updated in the refresh ("Pause at next step boundary" / "Resume run" /
  "Run now" / "Run now (login blocked)"); enabled while running **and**
  waiting (the morphed states dispatch pause/resume), disabled only while
  `login_blocked`.
- **Stop** → `icon="stop"`, `color="negative"`, tooltip "Stop run"
  (`mark("detail-stop")`), enabled while running **or waiting**.
- **Reset profile** → `icon="restart_alt"`, tooltip "Reset profile"
  (`mark("detail-reset")`); the confirmation dialog keeps its text
  ("Reset" — R3 destructive; Cancel → `close` icon-only + tooltip).
- **Clear login block** → `icon="lock_open"`, tooltip "Clear login block";
  dialog: Cancel → `close` icon-only + tooltip, "Allow one attempt" keeps
  text (R3 nuanced).
- **Recipe** link: text kept + `description` icon (R5); the pause-section
  **Open session** link: text kept + `open_in_browser` icon (unchanged — it
  is the waiting-state intervention entry).
- Run history (run-review reachability, 2026-11-17): each run expansion
  gains a **View run** link — `open_in_browser` icon + text "View run" (a
  navigation link, R5), right-aligned in a row at the top of the expansion
  body, → `/runs/<run_id>` (live view while the run is open, ended view
  after it finishes), `mark("detail-view-run-{run_id}")`. Rendered in
  `render_history` where the expansion is built; no separate refresh logic
  (the history rebuild already tracks the run set).
- Include the morphing button in the enabled/disabled state logic (~line 441)
  — `run_btn` enabled except while login-blocked, `stop_btn` enabled while
  running or waiting; update the module docstring.

### N6 — Recipe-editor icon actions (recipes.py)

- **Validate** → `icon="check_circle"`, tooltip "Validate recipe"
  (`mark("recipe-validate")`). **Save** → `icon="save"`, tooltip "Save
  (validates first)" (`mark("recipe-save")`).
- Per-task **Run now** buttons (after save): `icon="play_arrow"` + the user
  name as the label (data, not a verb).
- Failure-panel **Use** → `icon="check"` icon-only + tooltip "Use this
  candidate's locator" (R1).

### N7 — Session-page icon actions (session.py)

- Element-action buttons (per candidate row): Click → `left_click`, Fill →
  `text_fields`, Press → `keyboard`, Drag → `open_with`; icon-only + tooltip
  (R1), mark ids kept (`session-click`/`session-fill`/`session-drag`/…).
- **Resume** → `icon="play_arrow"` + label; **Cancel** → `icon="cancel"` +
  label "Cancel run" (R3). Cancel dialog: "Go back" → `arrow_back` icon-only +
  tooltip; "Cancel run" keeps text.
- **Repair recipe** links: text kept + `build` icon (R5); the "Task N:"
  breadcrumb link is unchanged.

### N8 — Downloads icon actions (downloads.py)

- Row **Retry delivery** (retryable rows only) → `icon="refresh"` icon-only +
  `q-tooltip` "Retry delivery" (R1). Confirm dialog: Cancel → `close`
  icon-only + tooltip; **Retry** → `icon="refresh"` icon-only + tooltip
  "Retry delivery".

### N9 — Settings restructure: grouped cards + one Save (settings.py)

Rewritten 2026-11-17 (user decision): the page's 10 per-key/per-section
Save buttons are replaced by **one** Save for all daemon settings, and the
fields are grouped into cards. The per-key `set-save-{key}` markers are
removed; the field markers `set-{key}`, the `set-git_commit_enabled` switch
marker, and `set-save-password` are kept.

- **Cards** (six `ui.card`s in a `ui.column`, each with a subtitle title):
  1. **Security** — the two password inputs (New password / Repeat
     password) and the **Change password** button, `icon="vpn_key"` +
     tooltip "Change password" (icon pass R3). Behavior unchanged: min
     length + match validation, `set_password_hash`, clear both fields,
     "Password updated" notify. This is a separate action, NOT covered by
     the single Save (the confirm field makes it its own transaction).
  2. **Notifications** — `ntfy_topic`, `ui_base_url` (their hints move
     under the fields, `text-xs` muted).
  3. **Runs** — `pause_deadline_seconds`, `max_concurrency` (hint: takes
     effect on the next daemon start), `display_start`.
  4. **Storage & session** — `download_dir`, `vnc_password`.
  5. **Vault** — `vault_api_url`, `vault_api_host`; when a field is empty
     the hint shows the currently effective environment value
     (`config.vault_settings(db)`), e.g. "Empty: using BW_API_URL
     environment value (http://…)" — the effective value is re-read on
     page load only.
  6. **Git** — the `git_commit_enabled` switch with its hint.
  - Field row shape: label (`w-48 shrink-0`) + input (`w-72`) + hint line
    below the input (`text-xs`, muted) — the current inline hint after the
    input is dropped.
- **One Save** — a single primary button at the bottom (right-aligned),
  `icon="save"` icon-only + tooltip "Save all settings" (icon pass),
  `mark("set-save")`.
  - Behavior: validate **all** fields with the existing `_validate`
    (the git switch needs no validation). All valid → write every value
    (all `FIELDS` keys + `git_commit_enabled`) and notify "Settings saved".
    Any invalid → write **nothing** (all-or-nothing; supersedes the
    per-field "only the failing field is not written" semantics) and
    notify `invalid: <key>, <key>` (negative, one line, the failing keys'
    names).
  - No dirty tracking — Save is always available and idempotent.
  - `ui_password_hash`, `session_secret`, `onboarding_done` are not part
    of this form (unchanged).
- Update the module docstring (the per-field save description is stale)
  and the `FIELDS` hint texts where they reference per-field saving.

### N10 — Onboarding icons (onboarding.py) — R4: icon + label

- Add icons, keep every label: "Go to the dashboard" (`dashboard`), "Check"
  (`link`), "Save" (`save`), "Import from INI" (`upload_file`), "Add task"
  (`add`), "Back" (`arrow_back`), "Continue" (`arrow_forward`), "Finish
  onboarding" (`done`). Mark ids kept. The login page (native HTML form,
  public) is unchanged.

### N11 — Manual pause machinery (merged from the pause plan)

- `runner.py`: module-level `MANUAL_PAUSE_REQUESTED` flag; SIGUSR1 handler in
  `_install_signal_handlers` (flag-set only, distinct from the SIGTERM/SIGINT
  abort handler); reset in `_run_task`; at the top of the per-step loop in
  `_run_recipe`: if the flag is set → clear it,
  `outcome = pause_loop(ctx, "manual", "Paused manually. Resume to continue at
  the next step.", None, None)`; on `"resume"` → `continue`, else
  `raise PauseOutcomeAbort(outcome)`.
- `orchestrator.py`: `pause_run(task_id) -> bool` (sync) — **SIGUSR1 to the
  runner's pid only** (`proc.send_signal`), never the process group (node
  reserves SIGUSR1 for the V8 inspector); mirrors `stop_run`'s
  `self._processes` lookup and returncode check; returns False without a live
  runner. Update the module docstring's lifecycle list.
- The pause machinery is reused as-is (`pause_loop`: persist → amber `waiting`
  row, ntfy deep link when `ntfy_topic` set, control socket,
  `pause_deadline_seconds`). No pause.py changes expected.
- Edge semantics (document in the tooltip/docstring): flag set after the last
  step → the run completes normally, flag dropped; flag set while a portal
  pause is active → takes effect at the next boundary after resume.
- Outcomes unchanged: resume → continue; cancel → `cancelled`; timeout →
  `needs_attention`.

### N12 — Menu highlighting

- `task_detail.py:149` → `build_layout(active="Tasks")`.
- `recipes.py:160` → `build_layout(active="Recipes")`.
- `session.py` stays `active=""` (not in the menu).

### N13 — Route registration (app.py::build_app)

- Import + `register_task_index(db, scheduler)` before `register_task_detail`;
  `register_recipe_index(db)` before `register_recipe_editor` (exact routes
  before the parameterized ones; no collision, order kept explicit).

### N14 — Tests

- New `tests/test_bc_ui_task_list.py` (mirror `test_bc_ui_dashboard.py`):
  seed idle/running/waiting tasks with runs; assert rows, badges, row-click
  navigation to `/tasks/<id>`, the empty state, and the unauthenticated
  redirect.
- New `tests/test_bc_ui_recipe_list.py` (mirror `test_bc_ui_recipes.py`:
  point `config.RECIPE_DIR` at a per-test temp dir): a valid file + a
  broken-YAML file; tasks with a newest conclusive `success` run, a
  `failure` run, only `interrupted` runs, no runs; one service with tasks but
  no recipe file; set `config.RECIPE_EXTRA_DIR` to assert overlay precedence.
  Assert the valid/invalid badges, the verified/failing/unverified badges with
  dates and `/runs/<id>` links, and the no-recipe-file row.
- `tests/test_bc_ui_dashboard.py`: rowaction `pause` routes to
  `orchestrator.pause_run` (mirror the Stop test); the morphing button's
  enable/disable per status (existing trigger-based pattern); the
  `view-run` action navigates to `/runs/<id>` (mirror the existing
  session-navigation test, renamed); `build_rows` carries `latest_run_id`
  (a task whose only run is finished; a never-run task carries `None`) —
  the existing `active_run_id` row assertions are the pattern. Rowaction
  `resume` (waiting state) lands on the run's control socket: seed the
  waiting run with a `control_sock` (a touched file — `control_sock_alive`
  only checks existence), stub `ui.session.control_client` (the D3.2
  shared-module pattern from `test_bc_ui_session.py`), trigger
  `{"action": "resume", "id": <run id>}` and assert `("resume", {})` was
  recorded with no orchestrator start/stop/pause; the dead-socket variant
  (no `control_sock`) degrades to a notify.
- `tests/test_bc_ui_task_detail.py`: the detail Run button routes to
  `pause_run` while running (mirror the detail-Stop test); the waiting
  state mirrors it — button states (play icon, Run enabled, Stop enabled,
  Reset disabled) and a click that sends `("resume", {})` to the stubbed
  control socket with no orchestrator action; each seeded run renders its
  `detail-view-run-{run_id}` link (absent for a task with no runs).
- `tests/test_bc_ui_settings.py`: rewrite the save paths for the single
  Save (marker `set-save`; the `set-save-{key}` markers are gone):
  - set one field, click `set-save` → written + "Settings saved";
  - **all-or-nothing**: dirty one valid field AND one invalid field,
    click `set-save` → NEITHER is written, the notify names the invalid
    key(s);
  - the git switch now saves via the same `set-save` click (was
    `set-save-git_commit_enabled`);
  - the vault-field tests and the password tests keep their markers
    (`set-{key}`, `set-save-password`) and assertions.
- Pause-plan non-UI tests: `tests/test_bc_runner.py` (flag set before step 2
  → run pauses `waiting` with `pause_reason == "manual"`, resume → continues
  and succeeds; flag after the last step → completes, flag dropped);
  `tests/test_bc_pause.py` (`build_pause_context` with the `manual` reason —
  payload shape); `tests/test_bc_orchestrator.py` (`pause_run` → True and
  SIGUSR1 delivered to the pid only, group path not used; False without a
  live runner).
- All existing `.mark()` ids are preserved EXCEPT the per-key
  `set-save-{key}` markers N9 removes (the settings suite is rewritten per
  above); every other suite must pass unchanged. Where a test asserts a
  label string, switch it to the marker (expected: none — verified the UI
  suites use markers/kinds). The dashboard "Service / User" header rename
  (N17) is safe: tests assert on row data and markers, not header labels —
  re-verify `test_bc_ui_dashboard.py` for any label assertion.
- Run from the repo root: targeted first
   `python -m pytest tests/test_bc_ui_task_list.py tests/test_bc_ui_recipe_list.py tests/test_bc_ui_dashboard.py tests/test_bc_ui_task_detail.py tests/test_bc_ui_recipes.py tests/test_bc_ui_session.py tests/test_bc_ui_settings.py tests/test_bc_ui_onboarding.py tests/test_bc_runner.py tests/test_bc_pause.py tests/test_bc_orchestrator.py -q`
   (there is no `test_bc_ui_downloads.py` — the downloads page has no UI test
   suite; N8's change is presentation-only and covered by N16),
   then the full suite (baseline 2026-11-15 per the pause plan: 859 passed /
   11 skipped). `ruff check` clean on all changed files.

### N15 — Docs

- CHANGELOG entry: icon actions + tooltips across the UI, `/tasks` +
  `/recipes` index pages, manual pause (pause at next step boundary, resume
  via session page), the settings single-Save restructure (grouped cards,
  all-or-nothing validation), the table alignment/label/mono convention,
  and run-review reachability (View run on the dashboard rows and the
  task-detail run history — the session page's ended view).
- Update the row-action documentation (README dashboard section /
  doc/QUICKSTART.md, whichever covers it): icons + tooltips, the Pause
  semantics, the existing Stop note, and the View run button (it now opens
  the newest run, live or ended).
- No `.kilo/plans` paths or plan IDs in source comments or public docs
  (sanitized-mirror rule in `AGENTS.md`).

### N16 — Manual verification (dev daemon)

- Drawer: 5 items, icons, highlighting (including `/tasks/<id>` and
  `/recipes/<service>`).
- `/tasks` and `/recipes`: rows, badges, links, ~2 s polling; `/recipes`
  evidence badges (verified/failing/unverified), overlay badge, no-recipe-file
  row.
- Row icons: hover tooltips on every state; start a run → the Run icon
  becomes the pause icon → click → row turns amber `waiting`; with
  `ntfy_topic` + `ui_base_url` set, the ntfy push arrives with the deep link;
  **while waiting: the row's icon is play again (tooltip "Resume run") and
  Stop is enabled — click Resume on the row → the run continues without
  opening the session page; Stop while waiting → the run ends
  (`interrupted`)**; also session page → Resume → icon back to play; Stop
  (filled rectangle) → run ends; Edit dialog; View run navigates.
- Task detail: morphing Run button (including the waiting-state Resume and
  the enabled Stop while paused), Stop, Reset profile (confirm dialog),
  Clear login block (dialog), Recipe link.
- Recipe editor: Validate/Save icons, per-task run buttons, failure-panel Use
  icons (open via a `?run=<id>` from a step_failed run).
- Session page: Click/Fill/Press/Drag icons + tooltips, Resume/Cancel.
- Downloads retry, onboarding wizard walk (fresh DB), login page unchanged.
- Settings (N9): the six cards; the single Save — break one field (e.g.
  `max_concurrency` = "0") AND change a valid one, Save → nothing changed
  on disk, the notify names the invalid key; fix and Save → all written,
  "Settings saved"; the git switch saves through the same button; the
  password card's Change password still works standalone; the Vault card
  shows the effective env value in the hint while the fields are empty.
- Tables (N17): on dashboard / downloads / task detail (and the new index
  pages) — numeric and Actions columns right-aligned, technical cells
  mono, the service/user column reads "Task" everywhere.
- Run review (N4/N5): start a run and let it finish — the dashboard row's
  View run button then opens the session page's ended view (result card +
  last pause context for a paused run + Repair recipe link for a
  step_failed run); the task-detail run history's View run link does the
  same; a task that never ran shows the View run button disabled.
- Phone-on-LAN smoke: icon buttons tappable (tooltips are desktop-only; R4/R5
  labels cover the first-run and navigation paths on touch); fonts/icons work
  without internet.

### N17 — Table column convention (all tables, 2026-11-17)

One convention instead of per-table ad-hoc choices (user decision 2026-11-17).
Presentation-only: no row data or marker changes, so the existing suites stay
green.

- **Convention** (documented as a short note in `format.py`, referenced from
  each table module):
  - **Alignment**: numeric columns and the Actions column are
    `align: "right"`; everything else (text, badges, timestamps) left.
  - **Labels**: the service/user pair column is **"Task"** in every table
    (the dashboard's "Service / User" is renamed; downloads and N2 already
    use "Task"). "Last run" / "Next run" labels stay.
  - **Mono**: technical cells (timestamps, cron, SHA, filenames, run ids,
    counts) render `font-mono`, carried by a `mono: True` key in the
    column dict (passthrough to `props.cols` verified — see environment
    facts) and applied in the body slots via
    `:class="col.mono ? 'font-mono' : ''"` on the default cell span
    (badge/button cells unaffected).
- **Helper** in `format.py`: `table_column(name, label, *, align=None,
  mono=False) -> dict` building `{"name", "label", "field": name}` plus the
  optional keys; all five column lists are rebuilt with it.
- **Per-table columns** (name — align/mono):
  - Dashboard: Task (left), Status (left, badge), Login (left), Last run
    (left, mono), Next run (left, mono), Session (left), Last download
    (left, mono), Actions (right).
  - Downloads: Task (left), Run (right, mono), Filename (left, mono),
    Size (right, mono), SHA256 (left, mono), Duplicate (left, badge),
    Delivery (left), Date (left, mono), Actions (right).
  - Task-detail steps: Step (right, mono), Action (left, mono), Error
    (left), Screenshot (left).
  - N2 `/tasks`: Task (left), Status (left), Enabled (left), Cron (left,
    mono), Last run (left, mono), Next run (left, mono).
  - N3 `/recipes`: Recipe (left), Tasks (right, mono), Overlay (left),
    Valid (left), Last evidence (left).
- Update the three existing body slots (dashboard `ROW_BODY`, downloads
  `BODY`, task-detail `STEP_BODY`) with the `col.mono` class binding; the
  new index pages' slots are written with it from the start.

## Risks & mitigations

- **q-tooltip on a disabled q-btn**: disabled buttons swallow pointer events
  in Quasar, so tooltips on disabled row buttons may not appear. Acceptable
  (the state is carried by the color badges and the session/next-run
  columns); verify in N16.
- **q-tooltip inside the Vue slot template**: the `ROW_BODY` template is
  runtime-compiled on the client; `q-tooltip` as a `q-btn` child must be
  verified in N16 (fallback: the native `title` attribute on the `q-btn`).
- **Morphing button state**: the icon/disabled/tooltip state must self-heal on
  the ~2 s poll (status changes while the page is open); the click handler
  re-reads the task status, so a stale icon can never dispatch the wrong
  action.
- **Evidence query** must ignore `interrupted`/`cancelled` runs and handle a
  task whose only run is still open (no conclusive run → "unverified").
- **SIGUSR1 to the pid only** — never the process group (the Playwright node
  driver reserves SIGUSR1 for the V8 inspector).
- Display-name mapping (key ↔ Task-table `service`) must handle services with
  spaces/case.
- Pages are per connection (NiceGUI model): the 2 s polls run per open tab —
  the app's existing regime, fine for a NAS.
- The Vue `CustomEvent` workaround and the engineio disconnect wrapper in
  `app.py` are untouched (comments updated only where they enumerate the row
  actions).

## Out of scope (companion plan / later)

- The entire dark-theme layer: see
  `.kilo/plans/1794866943286-ui-dark-theme.md` (design tokens, theme.py,
  `ui.dark_mode`, header/drawer reskin, dashboard KPI strip, dark-readability
  fixes, CodeMirror theme, login restyle).
- Dark-mode toggle; the wireframe's "Verlauf / Vaultwarden / Logs" pages; a
  global logs page; the noVNC client's own UI; i18n; vendored web fonts or
  Material Symbols.
- Mid-step interruption (Stop remains the abort path); pause via API/ntfy/CLI.

## Plan housekeeping (at implementation time)

- Archive `.kilo/plans/1794763657924-manual-pause-button.md` to `completed/`
  (consumed by this plan; its status line is already updated here) and update
  `.kilo/plans/README.md` (this plan, the dark-theme follow-up, the pause-plan
  entry).
