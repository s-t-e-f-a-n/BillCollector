# BillCollector — Single Dockerfile + Non-Root User (aligned with the flowcool fork)

> Status: READY FOR IMPLEMENTATION.
> Implements daemon-plan M0 item 6 (`1790364274061-billcollector-nicegui-daemon-plan.md`,
> "Docker: enable the non-root user … rebuild the image with the new requirements") plus
> the user-requested consolidation: drop the legacy Selenium `Dockerfile`, rename
> `Dockerfile_pw` → `Dockerfile`, adapt all references.

## Goal

1. `Dockerfile_pw` → `Dockerfile` (the only Dockerfile); legacy Selenium `Dockerfile` removed.
2. The image runs as a **non-root user (UID/GID 1000, build-arg overridable)** using the
   hardening patterns from `github.com/flowcool/BillCollector` (their `Dockerfile`,
   cataloged in `1790625192832-flowcool-fork-extensions.md` item A9).
3. All references (scripts, README, deploy skill, live plans, CHANGELOG) adapted.

Repo-only change. The NAS deploy (image rebuild + ownership check + first production
run) is a separate user-gated step via the deploy skill, Stage 5 (see Follow-ups).

## Context (verified facts)

- Fork non-root pattern (fetched from `flowcool/BillCollector` `main`):
  `ARG TARGETARCH` amd64 guard; `ARG APP_UID=1000` / `APP_GID=1000`;
  `ENV HOME=/home/billcollector` (+`PIP_NO_CACHE_DIR=1`); OCI labels
  (`title`/`description`/`source`/`version`/`revision`/`licenses=MIT`) fed by
  `ARG VERSION=dev` / `REVISION=unknown` / `SOURCE`; `mkdir -p /apps/Downloads $HOME` +
  `chown $APP_UID:$APP_GID /apps /apps/Downloads $HOME`; `COPY --chown=… apps/ .`;
  `USER $APP_UID:$APP_GID` (numeric, no `adduser`); `VOLUME ["/apps/Downloads"]`.
- Our `Dockerfile_pw`: ubuntu 24.04, `WORKDIR /apps`, `PLAYWRIGHT_BROWSERS_PATH=/apps/browser`,
  `COPY apps/. .`, `pip3 install -r requirements.txt --break-system-packages`,
  `python3 -m playwright install --with-deps chromium ffmpeg`, apt list incl. `xvfb` + fonts,
  commented-out `adduser`/`USER` block (lines 34-38), unused `ARG VER=unknown`,
  `CMD ["/bin/bash"]` (the batch wrapper `BillCollector.sh` passes the command explicitly).
- `install_docker-image.sh` (runs on the NAS via `deploy_remote.sh`): case
  `selenium|playwright` → `-f Dockerfile_pw`; then on the NAS it replaces `apps/Downloads`
   and `apps/db` with symlinks to the OMV shared folders
   (`CONSUMER_DIR=…/.paperless/_BillCollector_/`, `DB_DIR=…/_BillCollector_/db`)
   — both hardcoded in the script (replaced by env/.env injection, decision 7).
   `BillCollector.sh` bind-mounts exactly those two paths into the container.
- `.env` (deployment machine) currently sets `INSTALL_SCRIPT_ARGS=playwright`
  (`deploy_remote.sh` appends it to the install-script call).
- NAS is **x86_64** (user-confirmed 2026-10-04) → the fork's amd64 guard is adopted.
- Repo is MIT-licensed (`LICENSE`) → the fork's `licenses=MIT` label is accurate.
- `.dockerignore` exists (`**/Downloads`); `apps/` otherwise builds as-is (unchanged behavior).
- The daemon plan M1 will later add `git`, `x11vnc`, `websockify`, `novnc` apt deps and
  change the `CMD` to `serve` — out of scope here.

## Decisions

1. **Adopt (fork-aligned):** `APP_UID`/`APP_GID` args (default 1000), `HOME=/home/billcollector`,
   `PIP_NO_CACHE_DIR=1`, amd64 `TARGETARCH` guard, full OCI label set
   (`SOURCE=https://github.com/s-t-e-f-a-n/BillCollector` — the public mirror, never the
   private Gitea URL), `mkdir + chown` step, `COPY --chown`, numeric `USER`,
   `VOLUME ["/apps/Downloads"]`.
2. **Keep (ours):** ubuntu 24.04, `TZ=Europe/Berlin` (not the fork's Zurich),
   `PLAYWRIGHT_BROWSERS_PATH`, the pip + `playwright install --with-deps chromium ffmpeg`
   steps, the xvfb/fonts apt list, `CMD ["/bin/bash"]` (daemon plan flips it in M1/M4).
   The existing unused `ARG VER=unknown` is replaced by `VERSION`/`REVISION`.
3. **Do not copy from the fork:** chrome-for-testing install, the fork's apt list
   (Selenium-oriented), the fork's `CMD`.
4. **`install_docker-image.sh`:** no engine argument. The single build becomes
   `docker build -t "$IMAGE_NAME" --build-arg REVISION="$(git rev-parse --short HEAD)" .`
   (feeds the `org.opencontainers.image.revision` label). **Back-compat:** an optional
   positional argument is still accepted and must be empty or the legacy value
   `playwright` (the deployment `.env` passes it); any other value → usage error.
5. **Bind-mount ownership (non-root prerequisite, NAS side):** after the symlink step,
   `chown` the symlink targets to `$APP_UID:$APP_GID` (`1000:1000`): `$CONSUMER_DIR`
   (dir only — the container creates world-readable files, umask 022, so paperless can
   read them) and `$DB_DIR` **recursively** (covers `bc.db` + journal files, currently
   root-owned). A chown failure exits non-zero with a clear message (fail at deploy time,
   not at cron time). The script already modifies those shared folders, so it assumes
   sufficient NAS privileges.
 6. **Mount targets are injected, not hardcoded (user request, 2026-10-05):**
   `CONSUMER_DIR`/`DB_DIR` resolve in the order env var → `.env` next to the
   script (plain KEY=VALUE parse — no `source`/eval, no override of set vars,
   only the keys the script reads are exported) → error. Before building, both
   must be non-empty, absolute, existing directories (fail at deploy time, not
   cron time — and no `rm -rf`/dangling-symlink on a misconfigured machine).
   `SKIP_MOUNT_SETUP=1` skips the whole mount step (local image builds;
   `apps/Downloads` + `apps/db` left untouched). `deploy_remote.sh` forwards
   both vars into the ssh session (empty = unset → NAS-side `.env` fallback);
    it never forwards `SKIP_MOUNT_SETUP` (a local-build knob that would silently
    skip the NAS mount setup). The mount step + build context operate on the
    script's own directory (works from any CWD), and a real, non-empty
    `apps/Downloads`/`apps/db` is never replaced (dev-machine data guard).
    Testing found two inherited bugs, fixed: `chown -r` is not a valid GNU flag
    (→ `chown -R`; the recursive db chown always failed before) and the mount
    step was CWD-relative (`pushd apps`), not script-relative.
 7. **Reference updates:** `README.md`, `.env.example`, `.kilo/skills/deploy/SKILL.md`
   (live skill), the live daemon plan, `CHANGELOG.md` (new `Unreleased` entry).
   **Not touched:** historical CHANGELOG sections, other plan files (dated records),
   `.kilo/worktrees/*` (separate checkouts — sync via git, never edited by hand).

## Tasks

1. **`git rm Dockerfile`** (legacy Selenium) and **`git mv Dockerfile_pw Dockerfile`**.
2. **Rewrite `Dockerfile`** (playwright variant + alignment), in layer order:
   - `FROM ubuntu:24.04`; `ARG TARGETARCH`; `ARG APP_UID=1000`; `ARG APP_GID=1000`;
     `ARG VERSION=dev`; `ARG REVISION=unknown`;
     `ARG SOURCE=https://github.com/s-t-e-f-a-n/BillCollector`
   - `LABEL org.opencontainers.image.*` block (title `BillCollector`, description
     "Collect documents from web portals using Playwright recipes", source/version/
     revision/licenses=MIT)
   - `ENV TZ="Europe/Berlin" HOME="/home/billcollector" PYTHONDONTWRITEBYTECODE=1
     PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1`; `WORKDIR /apps`;
     `ENV PLAYWRIGHT_BROWSERS_PATH=/apps/browser`
   - apt step 1 (python3 python3-pip) with the amd64 guard first:
     `if [[ "${TARGETARCH:-amd64}" != "amd64" ]]; then echo "BillCollector image builds
     for linux/amd64 only" >&2; exit 1; fi` (guard the whole build, not just one step)
   - `COPY apps/. .` → `pip3 install -r requirements.txt --break-system-packages` →
     `python3 -m playwright install --with-deps chromium ffmpeg` (existing order)
   - apt step 2 (xvfb + fonts list, unchanged)
   - `RUN mkdir -p /apps/Downloads "$HOME" && chown ${APP_UID}:${APP_GID} /apps
     /apps/Downloads "$HOME"`
   - `COPY --chown=${APP_UID}:${APP_GID} apps/ .` — note: with the existing
     `COPY apps/. .` already in place, restructure to the fork's two-COPY shape is NOT
     required; instead keep a single `COPY apps/. .` **with** `--chown=${APP_UID}:${APP_GID}`
     and keep the `mkdir`/`chown` step for `/apps/Downloads` + `$HOME` (the COPY target
     `/apps` gets its ownership from the later `chown`). Simplest correct form: keep the
     current single `COPY apps/. .`, add `--chown`, keep the mkdir/chown RUN.
   - `USER ${APP_UID}:${APP_GID}`; `VOLUME ["/apps/Downloads"]`; `CMD ["/bin/bash"]`
   - Remove the old commented-out `adduser`/`USER` block and `ARG VER=unknown`.
3. **`install_docker-image.sh`:**
    - Replace the `selenium|playwright` case with the optional-arg back-compat check
      (empty or `playwright`; else usage error, exit 1) and the single
      `build_image --build-arg APP_UID=… --build-arg APP_GID=… --build-arg
      REVISION="$(git rev-parse --short HEAD)" -t "$IMAGE_NAME" "$SCRIPT_DIR"`
      (script dir as build context; APP_UID/APP_GID keep image user in sync with
      the host-side chown).
    - After the `ln -s` block: `chown ${APP_UID}:${APP_GID} "$CONSUMER_DIR"` and
      `chown -R ${APP_UID}:${APP_GID} "$DB_DIR"` (note: `-R`, not `-r` — the
      original `-r` was never a valid GNU flag) with a clear error + `exit 1` on
      failure (wrap in `if ! chown …; then echo "[ERROR] …" >&2; exit 1; fi`).
    - Update the header comment (no engine selection anymore).
    - Replace the hardcoded `CONSUMER_DIR`/`DB_DIR` with env/.env resolution
      + pre-build validation + `SKIP_MOUNT_SETUP=1` + the non-empty-dir data
      guard, all script-dir-relative (decision 6).
4. **`README.md`** (~lines 153-155): `./install_docker-image.sh` without `playwright`;
   drop the "(Playwright/Chromium variant)" qualifier (it is now the only variant);
   mention the image runs as non-root user (UID/GID 1000).
5. **`.env.example`:** `INSTALL_SCRIPT_ARGS=` — keep the line, value empty, comment:
   "no arguments needed (kept for back-compat with older .env files passing `playwright`)".
6. **`.kilo/skills/deploy/SKILL.md`:** line ~31 invariant → "App code is baked into the
   docker image (`Dockerfile` does `COPY apps/. .`): … rebuild with `bash
   install_docker-image.sh` …"; line ~64 (Stage 1) → `bash install_docker-image.sh`.
7. **`CHANGELOG.md`** under `## [Unreleased]`:
   - `### Changed`: image now runs as a non-root user (UID/GID 1000, build-arg
     overridable) with container-hardening aligned to the flowcool fork (OCI image
     labels, `VOLUME /apps/Downloads`, `HOME`, amd64 guard); `install_docker-image.sh`
     no longer takes an engine argument (legacy `playwright` value still tolerated) and
     sets ownership of the Downloads/db mount targets for the non-root user.
   - `### Removed`: legacy Selenium `Dockerfile`; `Dockerfile_pw` renamed to `Dockerfile`.
8. **Daemon plan** (`.kilo/plans/1790364274061-billcollector-nicegui-daemon-plan.md`,
   live master):
   - "Current state" image bullet (~line 64): `Dockerfile_pw` → `Dockerfile`; note
     non-root user (UID/GID 1000) is now in the Dockerfile.
   - M0 item 6 line (~474-489): rename references to `Dockerfile`; "(requirements/
     Dockerfile side done in 0.3)" stays historically correct as written.
   - M0 status: item 6 → "partially done: non-root user (UID/GID 1000) + single
     `Dockerfile` landed; NAS image rebuild + mount-ownership verification pending at
     the next NAS deploy"; step 0.5 wording unchanged (cron still pending).
   - Docker/deployment section: "non-root user enabled (M0)" → mark done; apt deps for
     M1 (`git`, `x11vnc`, …) still pending.
   - M0 step 0.2 (~line 582) and step 0.5 (~line 637): `Dockerfile_pw` → `Dockerfile`,
     `install_docker-image.sh playwright` → `install_docker-image.sh`.
9. **Commit** per the dev-commits skill (suggested: one logical unit —
   `feat: single Dockerfile with non-root user (UID/GID 1000), aligned with the flowcool
   fork` — doc updates included or as a second doc commit; the skill decides).

## Validation (local, no NAS needed)

1. `bash -n install_docker-image.sh` — syntax.
2. `bash install_docker-image.sh` and `bash install_docker-image.sh playwright` →
    build succeeds (on the NAS, with `CONSUMER_DIR`/`DB_DIR` resolvable);
    `bash install_docker-image.sh selenium` → usage error, exit 1.
    **Local build:** `SKIP_MOUNT_SETUP=1 bash install_docker-image.sh` builds without
    touching `apps/` (the old chown-guard approach is superseded by strict
    pre-build validation: without resolvable, existing targets the script exits 1
    before building, so a misconfigured machine can neither build-then-fail nor
    replace real `apps/Downloads`/`apps/db` data with dangling symlinks).
3. `docker run --rm billcollector:latest id` → `uid=1000 gid=1000`.
4. `docker run --rm billcollector:latest ls -ldn /apps /apps/Downloads` → owned `1000 1000`.
5. `docker image inspect billcollector:latest --format '{{.Config.User}}'` → `1000:1000`.
6. `docker run --rm billcollector:latest python3 -m playwright --version` → `1.63.0`
   (pip env + bundled browser intact under non-root).
7. `docker image inspect billcollector:latest --format '{{index .Config.Labels
   "org.opencontainers.image.revision"}}'` → the short HEAD SHA.
8. Repo sweep: `Dockerfile_pw` appears nowhere outside dated plan files
   (`.kilo/plans/17902*`, `17903*`, `17906*`, `17908*`) and `.kilo/worktrees/*`.
9. Regression harness is venv-based (no docker) → no re-run required; steps 2-7 are the
   deploy-skill "image-touching change" smoke.

## Risks / failure modes

- **NAS chown rights:** if `REMOTE_USER` cannot chown the OMV shared folders, the
  deploy fails loudly (intended) → fix by granting rights or pre-chowning, then
  re-deploy (deploy skill Stage 6 for rollback).
- **Shared-folder UID mapping (OMV/CIFS):** files created by UID 1000 must stay readable
  by paperless-ngx (umask 022 → world-readable; verify at the first production run).
- **Root-owned `bc.db` on the NAS:** fixed by the recursive chown at install time; if the
  DB is busy (a run in progress) chown of the file still succeeds (metadata only).
- **amd64 guard on ARM dev machines** (e.g. M-series WSL2): builds fail with a clear
  message. Accepted (NAS + current dev box are x86_64).
- **`.env` still passes `INSTALL_SCRIPT_ARGS=playwright`:** tolerated by the script
  (back-compat); the deployment-machine `.env` should still be cleaned up (Follow-ups).
- **Local build context:** `apps/browser`, `apps/.venv`, `apps/db` are not in
  `.dockerignore` (pre-existing; `Downloads` is). Out of scope; a follow-up
  `.dockerignore` extension is recommended (keeps local builds fast and avoids baking
  dev data into the image).

## Follow-ups (explicitly out of scope here)

1. Deployment-machine `.env`: set `INSTALL_SCRIPT_ARGS=` to empty (optional; the script
   tolerates the legacy value).
2. **NAS deploy = deploy skill Stage 5** (user gate): promote per Stages 1-3, then
   `GIT_BRANCH=main` + `./deploy_remote.sh`. Verify on the NAS: remote commit matches,
   `docker run --rm billcollector:latest id` → uid 1000, one manual production run
   (`./BillCollector.sh apps/bc_default.ini False`) succeeds (DB rows + download lands
   in the paperless folder), then the next monthly cron run is unchanged. This closes
   daemon-plan M0 item 6 + the pending v0.4 NAS deploy.
3. M1 (daemon plan): add `git`, `x11vnc`, `websockify`, `novnc` apt deps; the non-root
   user then also owns the future `browser/profiles/` + `data/` volumes (daemon plan
   "Docker / deployment" section) — the `APP_UID`/`APP_GID` build args already cover
   that.
4. Optional: extend `.dockerignore` (`browser/`, `.venv/`, `db/`, `*.log`,
   `__pycache__/`).
