# PR #12 Review — fix: exclude private runtime artifacts from Docker builds

> Status: INTEGRATING (2026-10-07) — S3 confirmed as-is (R1 breaking change
> accepted); S4 selective integration applied to the `dev` working tree
> (uncommitted, awaiting S5 validation).

Repo `s-t-e-f-a-n/BillCollector`, PR by **flowcool**, head `ac70217`
(6 commits: 5 PR content + orphaned `38ff01b`), base `main` (`04b7525` at
review time), no issue reference (bug fix, no shared interface touched).
Review date 2026-10-07 (S1), against local Gitea state `dev` = `56f2fcf` /
`main` = `be3dbbc`, public mirror `github/main` = `04b7525`. Head unchanged
since the 2026-10-05 snapshot (`ac70217`).

## Verdict

**Approve with maintainer changes.** The changes are correct, minimal, and
well proven (synthetic canary check with a negative control). The only manual
work is the CHANGELOG merge (dev's `[Unreleased]` has PR #11 entries) and
README hunk 2. Everything else either applies cleanly or is already on `dev`.
One maintainer call is needed: accept the disclosed breaking change (the image
no longer contains `apps/.env`).

## Verified facts

- Merge base is `2f6952e` (4 commits behind `github/main`). The PR's first
  commit `38ff01b` ("doc: add CONTRIBUTING.md") is the **orphaned Oct-4
  sanitized public tip** — a recommit of Gitea `4456d75` (established in the
  PR #11 plan). Its 18 "removed" files (all `.kilo/*`,
  `.private/sync_github.sh`, `.vscode/*`) are a comparison artifact: present
  at the merge base (the mirror sanitizes only the amended tip, older public
  commits still carry the trees), absent at the PR head, absent from current
  `github/main` tip. Not PR intent; never applied from a PR head anyway.
- Real PR content is 6 files: `.dockerignore` (1 → 19 lines),
  `BillCollector.sh` (+7/−1), `tests/check_docker_context.py` (+61, new),
  `CHANGELOG.md` (+9), `README.md` (+8/−1), `CONTRIBUTING.md` (+72, from the
  orphaned commit).
- `CONTRIBUTING.md` in the PR is **byte-identical** to Gitea `dev` (commit
  `4456d75`), and the README "Contribute code … CONTRIBUTING.md" pointer line
  (line 59) already exists in `dev` byte-identically. Both merge as no-ops.
- Pre-image checks against Gitea `dev`: `.dockerignore`, `BillCollector.sh`
  and `tests/check_docker_context.py` (absent) are byte-identical to the PR
  base → hunks apply cleanly. `CHANGELOG.md` and `README.md` diverged on
  `dev` (PR #11 + single-Dockerfile work) → manual adaptation.
- Log rotation is real on `dev`: `setup_logging` uses
  `logging.handlers.RotatingFileHandler` with `backup_count=5` on
  `apps/bc.log` (apps/helpers/BillCollectorHelpers.py:66-80) → the
  `**/*.log.*` exclusion is justified, not speculative.
- dev's Dockerfile does `COPY --chown=${APP_UID}:${APP_GID} apps/. .`
  (Dockerfile:33) — only `apps/` enters the image; the `.dockerignore`
  patterns additionally shrink context transfer and protect root-level
  artifacts (root `.env`, `.git/config`) under a worst-case `COPY . /`,
  which is exactly the Dockerfile the check script models.
- dotenv path is consistent: the app calls `load_dotenv()` with no path
  (apps/BillCollector.py:275), CWD `/apps` in the container → the
  wrapper's read-only bind at `/apps/.env` is picked up; a file bind
  preserves python-dotenv quoting/interpolation (vs `-e` env passing).
  dev's Dockerfile has no `.env` reference, so nothing in-image depends on
  the previously baked file.
- The new `.dockerignore` covers every pattern of dev's `.gitignore` 1:1
  (`.env`, `.venv`, `.code`, `chrome*`, `.pytest*`, `__pycache__`, `*.bak`,
  `*.log`, `*.html` + `!tests/mock_portal/templates/*.html`, `Downloads`,
  `browser/`, `db/`, `.bc_ui_run.json`, `.bc.lock`) plus `.git`, `**/.env.*`
  and `**/*.log.*`. Negation order is correct and parent directories of
  negated paths are not excluded, so the negations are effective.
- The PR head still carries `Dockerfile_pw` (removed on `dev` by the
  single-Dockerfile consolidation); it is not in the PR diff → no action.
- Process (CONTRIBUTING.md): intended behavior + verification stated; proof
  shipped (check command, expected output, negative control against the
  previous `.dockerignore`); AI assistance declared ("under Florent's review
  and responsibility"); no secrets (synthetic sentinel canaries, "no real
  vault or production state"); no new network exposure (`FROM scratch`, no
  registry contact); no shared interface (DB schema, control protocol, recipe
  contract, exit codes) touched. Gaps: no issue referenced (a fix, not a
  feature — minor); the orphaned `38ff01b` muddies "one focused change" but
  is a no-op on `dev`.

## Code review findings

1. **`.dockerignore`** — denylist of 19 lines (see Verified facts). Residual
   gap class: a *new* artifact type not on the list would still enter the
   context; the author explicitly offers an allowlist model (`*` then
   `!apps/…`) as a separate PR. Accepted here; noted as risk R2.
2. **`BillCollector.sh`** — pre-flight guard (`-f` + `-r` on
   `$SCRIPT_DIR/apps/.env`, error to stderr, exit 1) then
   `-v "$SCRIPT_DIR/apps/.env:/apps/.env:ro"`. Fail-fast replaces the old
   behavior (run starts, image's baked `.env` used — the very bug being
   fixed). New lines properly quoted; existing unquoted `$SCRIPT_DIR` lines
   left as-is (style-consistent). No other wrapper behavior changed.
3. **`tests/check_docker_context.py`** (61 lines) — scratch context in a
   tempdir: copies the *real* `.dockerignore`, writes a worst-case Dockerfile
   (`FROM scratch` / `COPY . /`), creates 19 synthetic canary files
   (contents = sentinel string `SYNTHETIC_PRIVATE_CONTEXT_CANARY`, no real
   data) and 5 retained sources, builds with
   `docker build --quiet --output type=local,dest=…` (BuildKit local
   exporter — no registry), then asserts retained files exist and excluded
   ones do not (both directions). Fails loudly with docker's stderr on build
   failure; `--dockerignore` flag enables the A/B negative control. Canary
   paths all map to real artifacts (`apps/.env`, `apps/bc.log.1`,
   `.bc.lock`, `.bc_ui_run.json`, `recipes_playwright/.code/`,
   `db/bc.db`, browser `Cookies`, `Downloads`, `.venv`, `__pycache__`,
   nested `.env`, root `.env`, `.git/config`, `*.bak`, page-dump `*.html`,
   `chrome-linux64`, `.pytest_cache`). Requires Docker with BuildKit —
   **not available on this dev machine** (risk R4).
4. **`CHANGELOG.md`** — two bullets under a new `### Fixed`: the exclusion
   fix (with check command) and the **Breaking** note (image without
   `apps/.env`; wrapper mounts it ro; direct `docker run`/compose/scheduler
   must add the same mount). Wording accurate.
5. **`README.md`** — hunk 1 (CONTRIBUTING pointer) already on `dev` (skip);
   hunk 2 adds the `.env` mount bullet after `cp .env.example .env`
   (context matches `dev` line 174; apply).
6. **`BillCollector.py` / helpers / recipes** — untouched by the PR; no
   behavior change beyond the wrapper and build context.

## Risks

- **R1 (disclosed breaking change):** the image no longer contains
  `apps/.env`; direct `docker run`, third-party compose files and schedulers
  must mount it read-only at `/apps/.env`. v0.x, Unreleased — acceptable,
  but a maintainer call (open question).
- **R2:** the denylist model leaves a residual gap class for future artifact
  types; the allowlist alternative is offered by the author as a separate PR.
- **R3:** the PR head moved after the "final combined integration proof"
  (that 5-PR proof used head `922b2f9`; `ac70217` adds the rotated-log
  canaries and `.git/config`/root-`.env` canaries). The combined proof does
  not cover the `ac70217` delta; the author's second follow-up verification
  (19 canaries) does. S5 revalidates on the exact dev tree regardless.
- **R4:** the context check needs a Docker host with BuildKit; this dev
  machine has none. S5 must run it on a Docker host (NAS, where
  `install_docker-image.sh` runs).

## Integration plan (Gitea `dev`, selective — S4)

1. Apply `.dockerignore` from `refs/pr/12` (replaces the 1-line file with
   the 19-line file).
2. Apply the `BillCollector.sh` hunk from `refs/pr/12` (guard + ro bind);
   pre-image byte-identical → clean.
3. Add `tests/check_docker_context.py` from `refs/pr/12`.
4. `CHANGELOG.md` (manual): append the PR's two bullets to the **existing**
   `### Fixed` under `## [Unreleased]` (which holds the two PR #11 bullets);
   Keep a Changelog subsection order unchanged. This is the manual conflict
   resolution.
5. `README.md` (manual): apply only hunk 2 (the `.env` mount bullet after
   `cp .env.example .env`); hunk 1 is a no-op.
6. Skip: `CONTRIBUTING.md` (byte-identical on `dev`), all `.kilo/*` /
   `.private/sync_github.sh` / `.vscode/*` deletions (fork-behind-base
   noise; never applied from a PR head), `Dockerfile_pw` (not in the PR
   diff).
7. Preflight (per skill): clean tree on `dev`; PR head hash still `ac70217`
   (`git ls-remote github refs/pull/12/head`); re-run pre-image checks.

## Validation plan (S5, repo root, venv, exact dev tree)

1. `bash -n BillCollector.sh` → no errors.
2. `apps/.venv/bin/python tests/run_regression.py --ini
   tests/bc_regression.ini` → exit 0, 7 scenarios / 8 PDFs, `VERDICT: PASS`.
   (If `apps/db/bc.db` is the 0-byte gitignored file: re-initialize the
   schema via the production `DatabaseManager` first — no repo impact, per
   the PR #11 precedent.)
3. **On a Docker host with BuildKit** (risk R4):
   `apps/.venv/bin/python tests/check_docker_context.py` → expect
   `Docker context: 19 private canaries excluded, 5 source files retained`.
   Negative control: same check against the previous 1-line `.dockerignore`
   → `RuntimeError: Private runtime artifact entered build: apps/.env`
   (or `apps/bc.log.1`).
4. ruff (`F821`, `E4/E7/E9`) + bandit on `tests/check_docker_context.py`
   (and the changed shell file via `bash -n`) → nothing new beyond the known
   baseline (B608 dynamic SQL table names, B104 UI bind). The check script
   uses list-form `subprocess.run` (no B603); a B404-class flag on the
   docker subprocess is expected and baseline-equivalent.
5. No recipe/schema/Dockerfile changes in this PR → no CheckRecipe or image
   rebuild step beyond 3 (the image rebuild itself happens at the deploy
   stage, deploy skill).

## Out of scope

- PRs #13, #14, #15, #16 (separate reviews; #16 is in the same
  image-hygiene area — Dockerfile build tooling — but no file overlap with
  #12's candidates); the allowlist `.dockerignore` model (author offers it as
  a separate PR); issue #10 (DOM/SQLite retention).

## Open questions

- Accept the breaking change (R1) as-is for the next release? (maintainer
  call at the S3 gate) — **resolved 2026-10-07 (S3): accepted as-is.**
- S5 Docker-host location for the context check — **resolved 2026-10-07
  (S3): NAS, at deploy time** (Stage 5 of the deploy skill, where
  `install_docker-image.sh` runs).

## Stage log

### S3 (2026-10-07) — proposal confirmed as-is

User confirmed the exact proposal: apply items 1-3 byte-exact from
`refs/pr/12`, manual merges 4-5 (CHANGELOG append to the existing
`### Fixed` under `## [Unreleased]`; README hunk 2 only), skips as listed.
R1 accepted as-is. NAS operational follow-up recorded: the NAS-side cron
entry that launches the container (outside this repo) must gain
`-v <REMOTE_PATH>/apps/.env:/apps/.env:ro` at the next Stage 5 deploy.
S5 Docker host confirmed: NAS at deploy time (this dev machine has no
docker).

### S4 (2026-10-07) — selective integration executed

Preflight re-verified on `dev` @ `bf1a4a4` (clean tree; +1 doc-only commit
since review — pre-image checks re-run, all hold): PR head still
`ac70217`, merge base `2f6952e`.

- `.dockerignore`, `BillCollector.sh`, `tests/check_docker_context.py`
  applied byte-exact from `refs/pr/12` (verified by diff); modes
  644/755/644.
- `CHANGELOG.md`: PR's two bullets appended to the existing `### Fixed`
  under `## [Unreleased]` (verified byte-identical to the PR text).
- `README.md`: hunk 2 inserted after `- \`cp .env.example .env\``
  (verified byte-identical to the PR text); hunk 1 skipped (already on
  dev).
- Skipped: `CONTRIBUTING.md` (byte-identical on dev), `.kilo/*` /
  `.private/sync_github.sh` / `.vscode/*` deletions, `Dockerfile_pw`.

Working tree left dirty (uncommitted) for S5 validation of the exact
content.
