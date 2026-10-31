# Changelog

All notable changes to BillCollector are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

> Note: versions before this file was introduced were reconstructed from the
> git history and the tag dates. From now on, entries are added per PR and the
> section of the next release is finalized at tag time.

## [Unreleased]

### Added

- Terminal daemon run notifications: account-free failure, interruption and
  attention notices through the existing opt-in ntfy topic. Successful and
  cancelled runs stay silent, delivery is best-effort, and the monitor sends
  each terminal notice once. (issue #49)
- Opt-in daemon `notice_identity` with source-scoped PDF revision tracking,
  nullable Download identity columns, and pinned pypdf. Original PDFs are kept.
  (issue #38)
- Opt-in daemon `replacement_calendar` action for bounded monthly
  replacement-calendar traversal (issue #37). Months come from the run-start
  date context (issue #26). The legacy batch runner refuses the action.

- Input-triggered protected login submissions (issue #36): a login phase
  `submit` chain may now end with `fill`, for portals that submit when a
  password or OTP field is filled. The durable attempt is reserved before that
  terminal fill, the fill runs once (resume only re-verifies), and the final
  authenticated marker still proves success. No database, control-protocol, or
  exit-code change.

- Daemon runtime date variables and inline, recursive single-pass argument
  substitution (issue #26). Recipe save and run start share syntax validation.
  Tasks have an additive `date_window_days` setting (90 inclusive days by
  default); dates and cron scheduling use `TZ` with UTC fallback. Task-detail
  Run now supports a memory-only start-date override with no restart replay.
  The legacy batch substitution is unchanged.

- Timezone configuration reaches the daemon through Compose: root `.env`
  or exported `TZ` selects the zone, with UTC for unset or empty values.
  The image no longer imposes Europe/Berlin, so direct execution can also
  use `TZ` from `apps/.env`. Runtime environment values take precedence.

- Required Chromium sandbox in daemon and batch browser launches, a pinned
  Playwright seccomp profile for Compose, and isolated sandbox/download/profile
  qualification. Unsupported sandbox setup fails without an unsandboxed retry.
- Crash recovery for daemon downloads (issue #24): stage files, commit the
  Download row before publication, then deliver consumers with a stable
  task/hash idempotency key. Runner startup reconciles pending publications
  and deliveries. Same-task duplicates retain audit rows without another
  file publication. Filename collisions preserve both documents (original
  portal name retained in metadata).
- Self-hosted daemon with a NiceGUI web UI: `python3 -m billcollector serve`
  (binds `127.0.0.1:8000` by default; `--host`/`--port` or `BC_UI_HOST`
  override). On the first start it imports the `[Playwright]` sections of
  `bc_default.ini`/`bc_test.ini` as tasks (each (service, user) pair becomes
  one task, initially disabled with a default monthly cron) and shows a
  set-password form (or seeds the password from `BC_UI_PASSWORD` in
  `apps/.env`).
- Per-task cron scheduling: the Task table in `bc.db` is the source of truth;
  the daemon rebuilds its scheduler jobs from it on every start, and a missed
  run coalesces into a single catch-up run.
- Dashboard: all tasks with their status, last/next run, and latest download,
  a live log pane, Run now / Stop actions, and a `waiting` badge for paused
  runs; per-task run history with step records, step screenshots, and
  downloads; a session page (`/runs/<id>`) for one live run - while the run is
  paused it offers a "Copilot" view (screenshot, numbered interactive
  elements, click/fill/press/drag, Resume / Cancel) and a noVNC tab showing
  the actual browser window, plus a Repair link into the recipe editor for
  step failures.
- Recipe editor (`/recipes/<service>`) with schema validation and an optional
  git auto-commit for UI edits; a downloads page; a settings page (UI
  password, ntfy topic, pause deadline, max concurrency, download directory,
  UI base URL, VNC password, git auto-commit).
- Pause subsystem: a non-graceful step that still fails after 3 attempts, a
  failed download, or an explicit `wait_user` recipe step pauses the run (the
  task shows `waiting`) instead of aborting - it stores a machine-readable
  pause context on the run, pushes an ntfy notification with a deep link to
  the session page, and waits until the operator resumes or cancels, or the
  pause deadline passes (default 1800 s, configurable in Settings).
- New recipe method `wait_user`: an explicit pause point with an optional
  `prompt` and an optional `until` locator (the pause completes when that
  element appears, or on resume).
- ntfy push notifications for pause events (`ntfy_topic` setting; `NTFY_HOST`
  environment variable, default `https://ntfy.sh`).
- `python3 -m billcollector run <task_id>`: execute a single task run from the
  command line (e.g., from cron) without the daemon. The run executes on an
  allocated Xvfb display (viewable over noVNC on the run's websockify port);
  `--debug` adds a press-Enter pause before every step (the F5 debug
  workflow).
- Pytest suite covering the daemon modules and the UI pages (dev-only, not
  part of the docker image) and a ruff lint setup for the maintained source.
- First-start onboarding wizard (`/onboarding`): a three-step stepper - the
  vault API URL (+ optional host) with a **Check** button (the same DNS
  vetting + status check the run preflight makes) and **Save** (new Settings
  keys `vault_api_url` / `vault_api_host`; empty allowed = environment
  fallback; skipping is allowed but flagged), the task list (per-task enable
  toggles, an **Import from INI** button that adds only the (service, user)
  pairs missing from the Task table - including ones the user deleted - and a
  manual **New task** form), and a **Finish** step. While active, every
  authenticated page redirects to it; upgraded installs (a password hash
  exists and at least one task is enabled) are auto-completed on daemon start.
- Docker Compose stack (`docker-compose.yml`) for the daemon: builds from the
  root `Dockerfile`, UI port `${BC_UI_PORT:-8766}`, the per-run noVNC live
  view (websockify range `6080-6095`), `host.docker.internal:host-gateway` to
  reach host-local services, and an optional self-hosted ntfy behind the
  `ntfy` compose profile.
- Vault API configuration in the UI: new Settings fields `vault_api_url` /
  `vault_api_host` (settings page and the wizard's vault step); a non-empty
  Settings value wins over the `BW_API_URL` / `BW_API_HOST` environment, so a
  wrong vault URL can be fixed from the browser even with a read-only
  `apps/.env` mount (the runner exports the effective values into the
  environment before the vault calls; empty values keep the legacy env-only
  behavior).
- Phased login protection for task runs (issue #20, contract in
  [doc/SAFE_LOGIN.md](doc/SAFE_LOGIN.md)): a new recipe method `login` with an
  explicit success locator and, for multi-factor portals, ordered `phases`
  (each `steps` + `submit` + `success`; the last phase must prove the final
  success locator). The runner skips the block when the success locator is
  already visible (a live session), reserves one attempt of a persistent
  failure budget before the first submission, submits each phase exactly
  once, and consumes the reserved attempt without retry when a submission's
  outcome is uncertain.
- Persistent login failure budget per task (additive Task columns
  `login_failures`, `login_failure_limit`, `login_locked`,
  `login_cycle_active`, `login_pending_run_id`; existing databases are
  migrated in place). Reaching the limit (default 2, configurable per task
  and per recipe) locks the task: scheduled, manual and CLI runs are refused
  until an explicit clear, a crash or restart settles an in-flight attempt
  (the orphan cleanup consumes it), and a successful session proof resets the
  budget.
- Login state in the Web UI: a Login column on the dashboard (available /
  pending / blocked; the bulk run skips blocked tasks and Run now is
  disabled while blocked), the budget state on the task detail page
  (unproven attempts / limit), and a "Clear login block" button (idle +
  locked only, confirm dialog) that grants exactly one further attempt while
  preserving the profile and schedule.
- An ntfy notification when a task's login is locked (existing `ntfy_topic`
  transport; task id and failure count, a deep link to the task detail when
  the UI base URL is set).
- Bounded Playwright collection actions (issue #18): two new terminal
  recipe methods that take one page locator plus one options object -
  `click_until_absent` drives a cumulative "load more" control until it is
  absent or hidden (every click must increase the visible progress count;
  `max_clicks` 1-100, `timeout_ms` 1-120000; page-replacement pagination and
  virtualized lists fail closed), and `download_all` downloads every item of
  a stable ordered list (non-empty unique `key_attribute` per item, exactly
  one download per click observed over a full per-item `event_window_ms`
  window, `max_items` 1-200, `timeout_ms` 1-600000, with the per-item event
  budget re-validated against the deadline before every click). Collection
  steps are single-attempt (no automatic retry after partial side effects),
  cannot be nested under `expect_download` or marked `graceful: true`, and
  an operator resume of `download_all` skips the item keys already persisted
  for the step; a suggested filename already saved earlier in the run fails
  instead of being overwritten.
- Contributor guides (issue #27, D02/D05/D07): `doc/QUICKSTART.md` (tested
  daemon setup with a local first-check procedure), `doc/TROUBLESHOOTING.md`
  (symptom guide), and `doc/RECIPE_AUTHORING.md` (recipe author guide with a
  credential-free synthetic example,
  `doc/examples/recipe-pw__synthetic.yaml`). An automated test
  (`tests/test_doc_recipe.py`) runs the guide's recipe end-to-end against the
  bundled mock portal so the documented steps stay verified.

### Changed

- The Docker image no longer sets a default `TZ` (previously
  `Europe/Berlin`). Daemon calendar dates and cron schedules now use the
  zone selected through the shell or the root `.env` (see the timezone
  entry under `### Added`), defaulting to `UTC` when unset or empty.
  Existing installations that relied on the image's Berlin default must
  set `TZ` explicitly to keep their previous local dates and schedules;
  after changing the setting, recreate the daemon with
  `docker compose up -d billcollector` and check the task schedules.
- Deploys now reuse the BuildKit layer cache: the changing `REVISION` build
  arg (its value is part of the cache key of every `RUN` step, so it
  invalidated the whole cache on every deploy) is gone from
  `install_docker-image.sh`, and the `Dockerfile` installs the Python
  dependencies and the Playwright browser before copying the application
  code. A code-only deploy re-runs just the final `COPY` + `chown`; a
  doc-only deploy builds all-`CACHED`.
- The docker image now runs as a non-root user (UID/GID 1000, overridable via
  the `APP_UID`/`APP_GID` build args) with container hardening aligned to the
  flowcool fork: OCI image labels, `VOLUME /apps/Downloads`, dedicated `HOME`,
  amd64 build guard. `install_docker-image.sh` no longer takes an engine
  argument (the legacy `playwright` value is still tolerated) and sets the
  ownership of the Downloads/db mount targets for the non-root user. Its
  mount targets are no longer hardcoded: `CONSUMER_DIR`/`DB_DIR` are read from
  the environment or a `.env` file next to the script (validated before the
  build), and `SKIP_MOUNT_SETUP=1` skips the mount step for local image
   builds. `deploy_remote.sh` forwards the two variables to the NAS. It also
  creates and chowns the daemon compose bind paths (`apps/data`,
  `apps/browser/profiles`) so the first `docker compose up` does not create
  them root-owned and the non-root daemon cannot write into them.
- The shared foundation (database, vault client, page-state recording,
  downloads, notifications, control protocol) was extracted into the
  `apps/billcollector/` package, which the batch entry points
  (`BillCollector.py`, `BillCollectorServices_pw.py`) now import as well; the
  cron-driven batch path is unchanged.
- The single-service manual run UI (`apps/bc_ui.py`, added in v0.3) is
  replaced by the daemon web UI.
- README restructured around the daemon as the primary Quick Start (clone,
  `apps/.env`, `docker compose up -d --build`, set the password, walk the
  wizard, first task); new sections for daemon mode (env vars, container
  semantics), UI usage per page, cron-to-daemon migration, and the F5 debug
  workflow; the legacy batch section is now marked deprecated.
- Concurrent executions of one task are now refused by a per-task file lock
  held for the duration of the run (`task-locks/` under the data dir, never
  unlinked): a second CLI or daemon start of the same task stops before
  touching the recipe, the vault, or a display. Task claiming is guarded in
  the database (locked or pending login tasks are refused, and a rejected
  contender cannot release a task another active run still owns).

### Deprecated

- The cron-driven batch mode (`BillCollector.sh` + cron, a headless
  `docker run` per cron tick) is superseded by the daemon (per-task
  scheduling, live supervision, pause-and-step-in) and marked deprecated in
  the README. The wrapper keeps working as the rollback path (its flock and
  `docker run` behavior is unchanged); it now prints a deprecation notice to
  stderr on every start.

### Removed

- Legacy Selenium `Dockerfile`; `Dockerfile_pw` renamed to `Dockerfile` (the
  single Playwright/Chromium image).
- The `org.opencontainers.image.revision` OCI image label (fed by the
  `REVISION` build arg); the deployed commit is recorded in the deploy log
  instead (`deploy_remote.sh` prints `git log -1`).
- The inert `.commit_id` file, its `.gitattributes` `export-subst` hook, and
  the `Commit-ID` print block in `BillCollector.sh`. The substitution only ran
  on `git archive`, which the deploy never uses (it fetches + resets), so the
  committed value was always stale; the deployed commit stays visible in the
  deploy log.
- `doc/TODO.txt` (stale scratch notes).
- `apps/bc_ui.py` - the v0.3 single-service manual run UI, replaced by the
  daemon web UI.

### Fixed

- Load the persistent scheduler job store while paused, rebuild it from Task,
  then resume (#47). Disabled or deleted tasks cannot fire stale overdue jobs.

- Parse numeric cron weekdays with crontab numbering (0/7 Sunday, 1 Monday)
  in both the task editor and scheduler (#46). Invalid stored schedules are
  skipped with their task id. Ambiguous legacy forms `1/2`, `mon-5`, `01` and
  `*/02` are rejected; use named weekdays before rolling back to an older
  binary.

- Keep residual daemon exception messages and tracebacks out of per-run logs
  and SQLite notes. Retain fixed method/category diagnostics for scan, OTP,
  screenshot, browser-launch and unexpected runner failures.

- Pinned `tzdata` in `apps/requirements.txt` so the Python dependency check in
  the image build passes.
- Avoid recommended development packages in the initial Python APT install,
  keeping DejaVu fonts explicit to preserve browser/UI font fallback.
- Check Python dependencies at build time and remove pip/wheel installers from
  the final image while preserving local virtual environments.

- Vault request diagnostics retain HTTP status and retry information without
  logging response bodies, request URLs or raw network exceptions. A locked or
  failing vault status is logged as its parsed state only.
- `setup_logging` silences the `urllib3` logger in every entry point: its DEBUG
  records contain request URLs with private vault item names.
- Exclude local credentials, logs, browser sessions and other runtime artifacts
  from Docker build contexts; retain example configuration and source fixtures.
  Check: `python3 tests/check_docker_context.py` (Docker with BuildKit).
- **Breaking:** the image no longer contains `apps/.env`. `BillCollector.sh`
  mounts it read-only at `/apps/.env`; a direct `docker run`, compose file or
  scheduler must add the same mount.
- Validate and pin the actual local vault API target, bypass ambient proxies and
  refuse redirects while preserving the existing request retries and TOTP handling.
- **Breaking:** `BW_API_URL` must be a plain-HTTP URL resolving only to loopback or
  private addresses; HTTPS and public targets are refused. `VAULT_HOST` is no
  longer used. See [doc/vault_transport.md](doc/vault_transport.md).
- The CLI debug switch (`BillCollector.py` 2nd positional argument) now honors
  its value: `debug`/`True`/`1` turn debug mode on, `False`/`0`/`no`/`off` keep
  it off. The previous presence-only check forced debug on for any value, so the
  documented `BillCollector.sh <ini> False` smoke run unexpectedly ran headed
  with debug logging.
- Retained browser evidence is now secret-safe in the Playwright runner and
  the legacy batch path (issue #10): input values are no longer used as
  locator names for editable fields (role-only candidates for unlabelled
  textboxes), the static label of submit/button/reset inputs is kept as the
  button name, link/download/page URLs are stored without query strings,
  fragments, path parameters or user info (`blob:`/`filesystem:` keep their
  sanitized inner URL), and step failures record the step, method and a
  fixed failure category (download failures additionally log the exception
  type) instead of raw exception text.
- README daemon-migration section: the example cron for the 1st and 15th
  at 06:00 had six fields (`0 6 1 1,15 * *`) and was rejected by the
  five-field parser used by the scheduler and the UI; corrected to
  `0 6 1,15 * *` (issue #27, D08).

- Onboarding task switches are independent: toggling a switch now updates
  only its own task's enabled state and scheduler registration (previously
  every switch read the last-created switch's value, so in a multi-task
  setup enabling one task could leave it disabled) (issue #27, F07).
- Bundled recipe `$schema` references and the recipe generator now use the
  recipe-relative `recipe-pw-schema.yaml` instead of a workstation-absolute
  path (editor/contributor only; runtime recipe behavior is unchanged).

- Runner import no longer creates the legacy `apps/db` directory (issue #43):
  the directory is now created when the legacy database is first opened, so
  an unwritable application tree no longer raises `PermissionError` at
  import. Legacy first-use creation and the daemon's configured runtime
  directories are unchanged.

## [v0.4] - 2026-10-02

### Added

- Local regression test environment (`tests/`): a mock web portal with
  scenario sites (happy path with OTP and downloads, bad login, graceful step
  failure, download failure, empty document list, CAPTCHA-style friction) and
  a harness (`tests/run_regression.py`) that executes a scope INI through the
  production scraping engine and verifies per-scenario expectations (engine
  return value, DB rows, downloaded files, exit semantics), including a
  `--vault` end-to-end mode against the real Vaultwarden.

### Changed

- Vaultwarden API client hardened: explicit 10 s timeout per request, 3
  attempts with backoff on transient failures, final 4xx responses reported
  as a status-carrying error; the "No TOTP" magic string is replaced by a
  proper 400-status check (no TOTP is now an expected condition, not an error).
- `deploy_remote.sh` is tag-aware: point `GIT_BRANCH` at a release tag for a
  one-command NAS rollback.

### Fixed

- Error propagation: a failed step now aborts the service/user pair's run
  (respecting `graceful`), every started service run is always finalized in
  the DB, the remaining services still run, and the process exits with code 1
  if any pair failed.
- Duplicate runs are rejected: a `flock` guard in `BillCollector.py` and
  `BillCollector.sh` (`apps/.bc.lock`) so overlapping cron starts, a UI run
  plus a manual run, or two manual runs can no longer collide.

## [v0.3] - 2026-09-27

### Added

- NiceGUI manual run UI (`apps/bc_ui.py`): start/stop the run of a single
  service from the browser and watch its output live; new `--service <NAME>`
  filter for `BillCollector.py` (the call format `<ini> [debug]` used by cron
  stays compatible).

### Changed

- Logging reworked on the `logging` module: rotating `bc.log`
  (5 MB x 5 backups) plus plain stdout, replacing the print-based logging.
- Dependencies refreshed: Python 3.12, Playwright 1.63.

### Removed

- Selenium support (browser driver, recipe format, install paths) - Playwright
  is the only browser automation engine.

## [0.1pw] - 2025-07-10

First release with Playwright support; Selenium and Playwright run side by
side, selected per ini section.

### Added

- Playwright support in parallel with Selenium: the ini file gains per-library
  sections (`[Selenium]` / `[Playwright]`), the new `BillCollectorServices_pw.py`
  engine, and the first Playwright recipe (`recipe-pw__winsim`); all Selenium
  recipes were renamed with a `recipe-se__` prefix.
- Step-by-step run tracking in SQLite (`apps/db/bc.db`): every step's method
  chain and the interactive elements found on the page are recorded - the
  foundation for the self-healing idea.
- Full recipe creation workflow: `BillCollectorCreateRecipe_pw.py` generates a
  YAML recipe from `playwright codegen` output.
- New Playwright recipes: 1und1, Buhl, DATEV, KabelDeutschland, Nuernberger.
- `Dockerfile_pw` (Ubuntu 24.04, Playwright Chromium + ffmpeg) and
  `install_docker-image.sh playwright`.
- `install_local.sh` updated for Playwright/Chromium.
- `deploy_remote.sh`: SSH into the remote host, run `git fetch`, and build the
  docker image.
- Repository block diagram (`doc/BillCollector_Repo.svg`).

### Changed

- `install_local.sh` and `install_docker-image.sh` take the automation engine
  as an argument (`selenium|playwright`).
- Deployment improved; the container now exposes a `db` volume.

### Fixed

- `1und1` recipe: adapted to the login page's changed placeholder text.

## [selenium-final] - 2025-04-15

Last Selenium-only release. The Selenium stack was frozen at this tag; all
subsequent development went into Playwright.

### Added

- Selenium `switch_to` methods for iFrame handling.
- New recipe: Freenet Mobilfunk.
- `.commit_id` file to track the deployed commit ID.

### Changed

- `bitwarden_api_check_status`: improved error checks.
- `buhl` recipe: adapted to the website's changed cookie consent dialogue
  (shadow DOM).
- Dockerfile improved by avoiding bash script injection.

### Fixed

- Faulty `BillCollector.sh` corrected.

## [v0.1] - 2025-03-23

First public release.

### Added

- BillCollector core: Selenium-based document retrieval from web service
  portals, Vaultwarden integration via the Bitwarden API, YAML recipe format
  with JSON schema (`bc-recipe-schema.yaml`).
- Initial recipe set: 1und1, Buhl, DATEV, KabelDeutschland, Lichtblick,
  Nuernberger, winSIM.
- Docker image and installation scripts (`install_docker-image.sh`,
  `install_local.sh`), cron wrapper `BillCollector.sh`.
- README, issue templates (bug report, feature request).
