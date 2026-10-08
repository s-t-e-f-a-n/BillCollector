# Contributing to BillCollector

Thank you for your interest in contributing. There are two ways:

- **Recipes** — the YAML browser automation for a web portal you use. The
  lowest barrier to entry, no code required: see
  [Configure BillCollector](README.md#configuration) in the README, and share
  your recipes.
- **Code** — bug fixes, features, test coverage, and tooling.

## How development works

BillCollector is trunk-based with release tags:

- **`main`** is the latest branch of the public repository: the state the
  project publishes. You branch from it and target your PRs at it.
- **Release tags** (e.g. `v0.4`) mark validated releases.
- GitHub Actions runs offline unit checks and the published mock-portal
  scenarios with fresh private state. It uses no vault or provider credentials.
  Local and maintainer production validation remain separate requirements.

Open an **issue** before starting a feature — and always before touching a
shared interface (see [Shared interfaces](#shared-interfaces) below).

## Rules

### Ownership

- You own the behaviour of the work item you take on: the issue defines the
  behaviour, its acceptance tests, and its operational/security constraints.
  "Done" in your lane means those acceptance criteria pass.
- The maintainer owns the architecture, the daemon, and the UI, and keeps the
  final word on architecture. Architecture decisions are recorded in the issue.

### Shared interfaces

- The database schema, the control protocol, the recipe contract, and the exit
  codes are shared interfaces. A change to any of them is agreed in an issue
  before code; a PR that touches one references that issue.

### Pull requests

- Small PRs: one focused change per PR.
- Target `main` — the latest branch of the public repository.
- The PR states the intended behaviour and how to verify it: the command to
  run and the expected result.

### Proof

- Every PR ships with a test or check that proves the behaviour: a regression
  scenario, a unit test, a schema validation, or a documented manual run.

### Security

- No secrets in logs, tests, or artifacts (recipes, config samples, test data,
  screenshots).
- No new network exposure (ports, services, outbound endpoints) without review.

### AI-assisted code

- AI-assisted code is welcome. Declare it in the PR. You remain responsible
  for it: correct, properly licensed, defensible in review.

## Local development

- `bash install_local.sh playwright` sets up the Python environment and
  Chromium (see the README for debugging).
- Verify your change from the repository root:

  ```bash
  apps/.venv/bin/python tests/run_ci_regression.py
  ```

The isolated runner copies tracked inputs plus untracked, non-ignored files,
initializes an empty tracking database, and reuses browser binaries only.
Chromium is taken from `PLAYWRIGHT_BROWSERS_PATH` when set, else from
`apps/browser` (`install_local.sh`), else Playwright's default cache.
The bundled mock recipes use loopback port 8787.
