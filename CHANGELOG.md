# Changelog

All notable changes to BillCollector are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

> Note: versions before this file was introduced were reconstructed from the
> git history and the tag dates. From now on, entries are added per PR and the
> section of the next release is finalized at tag time.

## [Unreleased]

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
