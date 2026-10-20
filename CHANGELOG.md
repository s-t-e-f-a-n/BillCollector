# Changelog

All notable changes to BillCollector are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

> Note: versions before this file was introduced were reconstructed from the
> git history and the tag dates. From now on, entries are added per PR and the
> section of the next release is finalized at tag time.

## [Unreleased]

### Added

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
  command line (e.g., from cron) without the daemon.
- Pytest suite covering the daemon modules and the UI pages (dev-only, not
  part of the docker image) and a ruff lint setup for the maintained source.

### Changed

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
   builds. `deploy_remote.sh` forwards the two variables to the NAS.
- The shared foundation (database, vault client, page-state recording,
  downloads, notifications, control protocol) was extracted into the
  `apps/billcollector/` package, which the batch entry points
  (`BillCollector.py`, `BillCollectorServices_pw.py`) now import as well; the
  cron-driven batch path is unchanged.
- The single-service manual run UI (`apps/bc_ui.py`, added in v0.3) is
  replaced by the daemon web UI.

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
