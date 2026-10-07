# Plan: deployment process improvement - layer cache reuse on NAS builds

> Status: DONE (2026-10-07) - fixes 1 + 2 applied on `dev` and validated on
> the NAS (user-confirmed). Fix 3 (digest pin) deferred, see below.

## Question

Why does `deploy_remote.sh` (driving `install_docker-image.sh` on the NAS)
rebuild the BillCollector image completely on every deploy instead of
reusing unchanged BuildKit layers?

## Verdict (recorded 2026-10-07, session ses_ee7e3bec6ffe7jhFkSmhViPIuw)

The `--build-arg REVISION="$(git rev-parse --short HEAD)"` in
`install_docker-image.sh:107` invalidates the BuildKit cache of every `RUN`
step on every deploy.

### Causal chain

1. `install_docker-image.sh:106-108` - the only dynamic input to the build
   is `REVISION`, derived from the checkout's HEAD:
   ```bash
   build_image --build-arg APP_UID="$APP_UID" --build-arg APP_GID="$APP_GID" \
       --build-arg REVISION="$(git -C "$SCRIPT_DIR" rev-parse --short HEAD)" \
       -t "$IMAGE_NAME" "$SCRIPT_DIR"
   ```
2. `Dockerfile:7` declares `ARG REVISION=unknown` at stage level; it is used
   only in the `org.opencontainers.image.revision` LABEL (`Dockerfile:14`).
   The intent was labeling, not cache-busting.
3. BuildKit behavior (verified in the `moby/buildkit` source):
   - `frontend/dockerfile/dockerfile2llb/convert.go`, `dispatchArg()`: every
     `ARG` with a value is added to the stage state env
     (`d.state.AddEnv(arg.Key, *arg.Value)`) regardless of where (or whether)
     it is used.
   - `client/llb/exec.go`, `ExecOp.Marshal()`: the state env is written into
     the op as `pb.Meta.Env`.
   - `solver/llbsolver/ops/exec.go`, `ExecOp.CacheMap()`: the cache digest is
     computed over the entire serialized `pb.ExecOp`, including `Meta.Env`.
   => `REVISION=abc1234` vs `REVISION=def5678` -> a different cache key for
   every `RUN` op. Matches Docker's cache-invalidation docs: "Build arguments
   do result in cache invalidation."
4. Cascade: the first `RUN` (`apt-get install python3`, `Dockerfile:28`)
   misses -> new state chain ID -> `COPY apps/. .` (`Dockerfile:33`),
   `pip3 install`, `playwright install chromium ffmpeg`, the fonts `RUN` and
   the `chown` `RUN` all miss too. Only `FROM ubuntu:24.04` is reused
   (resolved from the local image store; the script uses neither `--pull`
   nor `--no-cache`).

### Why it happens "each time"

Every deploy checks out a new `main` tip (deploy Stage 2 promotion advances
`main` before Stage 5 runs), so `git reset --hard origin/main` on the NAS
lands a new commit every time - even doc-only commits (plan records,
changelogs). The expensive steps that re-run are exactly the network-bound
ones: `pip3 install -r requirements.txt` and `playwright install --with-deps
chromium ffmpeg` (multi-GB browser download + apt deps).

### What it is *not*

- **Not the `.dockerignore`/build context**: BuildKit hashes `COPY` inputs by
  file content; mtime is explicitly ignored, so `git reset --hard` touching
  mtimes is harmless.
- **Not the base image being re-pulled**: `ubuntu:24.04` stays local.
- **Not `--no-cache`**: not present in the script.
- Caveat: this assumes the NAS builds with **BuildKit** (evidence:
  "transferring context" progress in the deploy log, PR #12's canary check
  requiring BuildKit). With the classic builder (`DOCKER_BUILDKIT=0`) a
  LABEL-only ARG would *not* invalidate; a full rebuild on a back-to-back
  re-deploy of the *same* commit would mean the BuildKit cache itself was
  lost (`docker builder prune`, Docker reinstall/upgrade, or a different
  buildx builder).

## Improvement plan

### 1. Stop feeding a changing value through a Dockerfile `ARG` (primary fix)

- Drop `--build-arg REVISION` from `install_docker-image.sh` (and the
  `ARG REVISION` + LABEL line from the `Dockerfile`); or
- Keep the label without cache impact:
  `docker buildx build --metadata org.opencontainers.image.revision="$REV"` -
  metadata overrides are applied at export time and do not participate in
  the cache key (needs buildx >= 0.10 on the NAS).

### 2. Reorder the Dockerfile (defense in depth)

Move the expensive, rarely-changing steps before the app code `COPY`:

```dockerfile
COPY apps/requirements.txt .
RUN pip3 install -r requirements.txt --break-system-packages
RUN python3 -m playwright install --with-deps chromium ffmpeg
COPY --chown=${APP_UID}:${APP_GID} apps/. .
```

Then a code-only deploy re-runs just `COPY` + the final `chown` (seconds),
and a doc-only commit (with fix 1) is an all-`CACHED` build.

### 3. Optional hygiene

Pin the base image by digest (`ubuntu:24.04@sha256:...`) so a base tag
update can never silently force a full rebuild.

## Implementation record (2026-10-07, on `dev`)

- **Fix 1 - drop option (a) applied.** `--build-arg REVISION` removed from
  `install_docker-image.sh`; `ARG REVISION` and the
  `org.opencontainers.image.revision` LABEL line removed from the
  `Dockerfile`. The `--metadata` alternative (option b) was **not** used: it
  requires a recent docker CLI/buildx on the NAS (version unverified), and
  the deployed commit is already recorded in every deploy log
  (`deploy_remote.sh` prints `git log -1`), so the image label added no
  traceability value. Revisit if the NAS docker version is confirmed
  modern and the label is wanted back.
- **Fix 2 - applied.** New `Dockerfile` step order:
  `apt python3/pip` -> `COPY apps/requirements.txt` -> `pip3 install` ->
  `playwright install` -> `apt fonts/libs` -> `COPY apps/.` -> `mkdir` +
  `chown`. A code-only deploy now re-runs just the final `COPY` + `chown`;
  a doc-only deploy (with fix 1) should be all-`CACHED`.
- **Fix 3 - deferred.** No digest pin in this change: it is optional
  hygiene, and pinning an unverified digest without a local Docker host to
  test against is riskier than leaving `ubuntu:24.04` floating. Do it the
  next time the base image is deliberately updated.

## Verification (on the NAS)

> Validated (2026-10-07): user ran the NAS validation and confirmed it
> passed. (The dev machine has no Docker; all build-behavior proof happened
> on the NAS.)

1. ~~Before the fix (reproduce): A/B two builds differing only in `REVISION`
   - the second re-executes every `RUN` while `COPY`'s own inputs are
   unchanged.~~ (superseded - the build arg no longer exists)
2. **After fix 1** (user): on the NAS with the `dev` tree checked out
   (`GIT_BRANCH=dev` or manual checkout), run `./install_docker-image.sh`
   twice back-to-back (or `./deploy_remote.sh` twice) without any commit in
   between -> the first build after the Dockerfile change is a full build,
   the second must show **all steps `CACHED`** (only `FROM` resolves).
3. **After fix 2** (user): make a code-only change under `apps/` (commit it,
   re-deploy) -> only the final `COPY` + `chown` steps re-execute; a
   requirements.txt change re-runs `pip3 install` and the steps after it
   (`playwright install`, fonts `apt-get`, final `COPY` + `chown`), but not
   the python3 `apt-get` step or the base image.

## Process integration

The `pr-review` skill now carries an explicit S5 deployment-process
validation gate (image build + canary check + smoke run on the exact dev
tree, on a Docker-capable host, user-confirmed) that must be passed before
S7 may commit and push to `main`. Deployment-behavior changes are therefore
proven on the dev basis before promotion (SKILL.md: S5 "Deployment-process
validation", S7 prerequisite 0).

## Out of scope

- The NAS cron `.env` mount follow-up (R1, PR #12) - separate deploy-stage
  work.
- The `archive.ubuntu.com:80` apt failure observed 2026-10-07 - NAS-side
  network/firewall incident, not a deployment-process defect.
- Release tags / release notes - deploy-skill territory.
