# GHCR release pipeline, published-image quickstart, and recipe overlay volume

Source: `.private/notes.txt` — (1) "User Centric: Immediate Next Steps" (GHCR
pipeline, quickstart docs, mounted recipes volume) and (2) a 4-phase
consumer-platform vision (triaged in W4; no code). User-confirmed scope: the
three next steps + docs + roadmap triage.

## Context (verified against the working tree)

- **No registry exists today.** The only workflow is
  `.github/workflows/openwiki-update.yml`, and it is in the `STRIP` list of
  `.private/sync_github.sh` (lines 14–15), so the public GitHub mirror
  currently has **no** workflow files. Images are always built locally
  (`billcollector:latest`) via `install_docker-image.sh` (NAS) or
  `docker compose up -d --build` (README:210).
- **Dockerfile** (root, 71 lines): `ubuntu:24.04`, amd64-only guard (24–28),
  deliberate layer order — pip/playwright (35–36) before app code (57) for
  BuildKit cache reuse (comment 30–33; README 531–539). `VERSION`/`SOURCE`
  build args (6–7) feed the OCI `LABEL` at **lines 9–13**, i.e. near the top:
  a per-tag `VERSION` would bust the entire build cache. **No `REVISION` arg**
  by design.
- **Recipes**: baked into the image (`Dockerfile:57` copies all of `apps/`,
  including `apps/recipes_playwright/`). `config.RECIPE_DIR` is hardcoded
  (`apps/billcollector/config.py:35`), unlike the other runtime dirs which
  honor `BC_*` env vars (config.py:22–32). `recipe_path_for()` (config.py:117)
  is the single resolution point used by the runner (`runner.py:1097`),
  doctor (`doctor.py:381`), and all UI call sites. Validation is strong
  (`recipes.py:52` `validate_recipe`: JSON Schema draft-07 + login/variable/
  method/notice contract checks). Compose mounts **no** recipes volume
  (`docker-compose.yml:70–79`).
- **Task table**: `recipe_file TEXT` (`db.py:30`) is auto-populated with the
  resolved path at import (`db.py:351`) and at task creation
  (`ui/tasks.py:132`, `ui/onboarding.py:274`). No UI can set a custom value —
  it is a stale snapshot. Runner prefers it: `task["recipe_file"] or
  config.recipe_path_for(...)` (`runner.py:1097`).
- **This is the open C5 (F02) commitment** in
  `.kilo/plans/1792861675256-issue27-maintainer-commitments.md` ("recipe
  storage design, status: design not started"). Acceptance from that plan:
  a synthetic UI edit survives container recreation with identical content;
  packaged-update interaction defined; export/restore or durable history
  provided. W2 is the C5 delivery.
- Release culture: trunk-based, tags like `v0.4`/`v0.3` (CHANGELOG);
  `deploy_remote.sh` is tag-aware (`GIT_BRANCH=v*`); `sync_github.sh <tag>`
  force-pushes the **sanitized** tag to GitHub (tag hashes differ from
  Gitea's). GitHub `main` is the contribution target.
- Repo gate: `ruff` + `pytest` (testpaths `tests/`, NiceGUI user-fixture
  plugin; run from repo root with `PYTHONPATH=apps`).

## Work items

### W1 — GHCR publish workflow

1. New `.github/workflows/publish.yml`:
   - Triggers: `push: tags: ["v*"]` (matches the existing tag convention) and
     `workflow_dispatch` (maintainer dry-run).
    - `permissions: { contents: read, packages: write }` — one `packages`
      key only (write implies read; a duplicate key is rejected by GitHub's
      workflow schema, as found in the first live run).
   - Single job on `ubuntu-latest`, `platforms: linux/amd64` only:
     `docker/setup-buildx-action` → `docker/login-action` (registry `ghcr.io`,
     `GITHUB_TOKEN`) → `docker/build-push-action`:
     - `context: .`, `build-args: VERSION=${GITHUB_REF_NAME}`
     - `tags: ghcr.io/s-t-e-f-a-n/billcollector:${{ github.ref_name }}`
       — **pinned tag only; no `latest` alias** (matches the tag-pinned
       deployment culture; the README sample tag is updated per release)
     - `cache-from` / `cache-to`: `type=registry,
       ref=ghcr.io/s-t-e-f-a-n/billcollector/cache:latest, mode=max`
     - tag push: `push: true`; `workflow_dispatch`: `push: false`,
       `load: true` (build verified locally on the runner, nothing published)
2. **Do not** add `publish.yml` to the `STRIP` list in
   `.private/sync_github.sh` — it must exist in the GitHub mirror to run on
   the sanitized tag pushes. The file contains no secrets or private paths
   (only `GITHUB_TOKEN`), so publishing it is safe.
3. `Dockerfile`: move the `LABEL` block (lines 9–13) to the **end** of the
   file (after the final `COPY`/`chown`/`USER`) so a per-tag `VERSION`
   invalidates only the final metadata layer, not the pip/playwright layers.
   Keep the `VERSION`/`SOURCE` args and the amd64 guard. Update the
   layer-order comment (30–33) to mention the label position. No other
   Dockerfile changes — in particular **no new `REVISION`-style arg**.
4. `install_docker-image.sh`: in the NAS bind-target setup (lines 117–157,
   alongside the existing `mkdir`/`chown` of `Downloads`/`db`/`data`/
   `profiles`), also create and `chown` `apps/recipes` — the reference compose
   will mount it (W2) and a missing bind target would be created root-owned,
   breaking in-container recipe saves on the maintainer's own deployment.

User-gated (outside code change, at first release):
- Verify GHCR package visibility is public (account → Packages → default
  visibility, or the package after first push). A private package would break
  the unauthenticated pull in the README.
- First live run: either `workflow_dispatch` for verification or the next
  real `v*` tag push (release flow). The implementer does **not** cut a
  release as part of this plan.

### W2 — Recipe overlay volume (delivers C5/F02)

Semantics: an optional **user recipe layer** that overlays the built-in
recipes. Drop-in (new service) and update (shadow a built-in by same
service) both work; built-ins stay maintainer-owned and update with the
image.

1. `apps/billcollector/config.py`:
   - New `RECIPE_EXTRA_DIR`: read from `BC_RECIPE_EXTRA_DIR` via `_path`-style
     handling; **empty/None when unset** (all existing behavior unchanged).
   - `recipe_path_for(service)` (line 117): if `RECIPE_EXTRA_DIR` is set and
     `<extra>/recipe-pw__<service>.yaml` exists → return the extra path;
     otherwise the built-in path. Same normalization as today
     (lowercase, spaces → underscores).
   - `RECIPE_SCHEMA` stays bound to the built-in `RECIPE_DIR` (the contract is
     core-owned per C3/F08; a schema file in the overlay is ignored).
   - New `recipe_save_path_for(service)`: `RECIPE_EXTRA_DIR` set → the extra
     dir path (even for built-in services → the save shadows the built-in);
     unset → the built-in path (today's behavior).
   - `ensure_dirs()`: create `RECIPE_EXTRA_DIR` when set (non-compose use).
2. `apps/billcollector/recipes.py`: `save_recipe` (line 294) callers in
   `ui/recipes.py` save via `recipe_save_path_for(service)` instead of the
   load path, so a UI edit of a built-in recipe is written into the overlay
   when one is configured.
3. `apps/billcollector/runner.py:1097`: resolve at run time — use the task's
   stored `recipe_file` only when it exists **and** is not the auto-populated
   built-in default for the service; otherwise `recipe_path_for(service)`
   (overlay-aware). (With step 4, new rows are NULL and resolve dynamically,
   so a shadow added after task creation takes effect for existing tasks.)
4. Stop auto-populating `recipe_file`: `db.py:351` (import_ini),
   `ui/onboarding.py:274`, `ui/tasks.py:132` → store `NULL`. Add a small
   idempotent startup reconciliation (e.g. in `db.py` init or `cli.serve`
   startup): rows whose `recipe_file` equals the built-in default path for
   their service are reset to `NULL`. An explicitly stored non-default path
   (manual DB edit) still wins.
5. `docker-compose.yml`: add volume `./apps/recipes:/apps/recipes` (rw — the
   UI editor writes there) and environment `BC_RECIPE_EXTRA_DIR=/apps/recipes`
   to the `billcollector` service.
6. `apps/.env.example`: document optional `BC_RECIPE_EXTRA_DIR`.
7. Docs (public — keep sanitized, no plan references):
   - `README.md:290`: replace "INI files and recipes are still baked into the
     image and need a rebuild" with the overlay story.
   - `doc/QUICKSTART.md:133–137`: the F02 "limits" bullet becomes a supported
     feature; add `apps/recipes` to the `mkdir`/`chown` instructions
     (QUICKSTART lines 29, 44) and explain shadowing + image-upgrade
     interaction + git-checkout history option.
   - `doc/RECIPE_AUTHORING.md`: section "Adding or updating recipes via the
     mounted directory" (naming convention, overlay precedence, save behavior,
     `git_commit_enabled` only makes sense when the mount is a git checkout —
     the image ships without `.git`).
   - Packaged-update interaction (C5 acceptance, documented): built-ins update
     with the image; a user's shadow file persists across upgrades and keeps
     winning until the user updates or deletes it (no auto-merge).
   - Durable history / export (C5 acceptance): the mounted volume is the
     durable store (export = copy the directory); a git checkout mount +
     `git_commit_enabled` gives per-edit history.
8. After delivery: mark **C5 done** in
   `.kilo/plans/1792861675256-issue27-maintainer-commitments.md` (commitments
   status + Status section).

Edge cases to cover in tests:
- Overlay set but empty → built-ins resolve and load as today; saves go to
  the overlay.
- Overlay file present but invalid → structured validation error at run/load
  time (existing contract), service fails loudly, built-in not silently used.
- Service exists in neither dir → same "missing recipe" behavior as today
  (UI warning, run fails before vault/browser access).
- Existing task with stale built-in snapshot + shadow added → shadow wins
  after reconciliation.

### W3 — Docs: published-image quickstart + trust section

1. `README.md` Quick Start: add a **"Run the published image"** path before
   the existing clone-and-build procedure:
   - `docker pull ghcr.io/s-t-e-f-a-n/billcollector:<latest-release-tag>`
   - minimal compose override using `image:` instead of `build:` (no git
     clone needed; the four data dirs + `apps/recipes` + `apps/.env` are
     still created on the host, same chown rules)
   - keep the current clone-and-build flow as the **Build from source** path
     (maintainer/NAS/dev).
   - Note that the sample tag in the docs is updated with each release.
2. `README.md`: short **"Your data stays local"** section (Phase 4.2 of the
   notes): credentials come from the vault at runtime and are never written
   to disk or the image, no telemetry, ntfy pushes are opt-in.
3. `doc/QUICKSTART.md`: pointer to the image-pull alternative in "Prepare a
   fresh checkout"; update "Limits and pending work" per W2.
4. Constraint: public docs must not reference `.kilo/plans` paths or plan IDs
   (GitHub mirror is sanitized; enforced by review, not tooling).

### W4 — Roadmap triage of the 4-phase vision (notes item 2)

No code. Record in the final delivery summary (and in this plan's record) as
the triage of the vision:

| Notes item | Verdict |
|---|---|
| 1.1 NAS app templates / desktop wrapper (Electron/Tauri) | Out of scope — supported path is the compose quickstart; a desktop app is a separate product |
| 1.2 Guided onboarding wizard | **Already implemented** — `/login` + onboarding (vault check, tasks, finish) |
| 1.2 Credential storage in keychain/SQLite vault | Deliberately different — Vaultwarden at runtime, no local credential files; keep as the trust position |
| 1.3 Visual status & health center | **Already implemented** — dashboard, run states, waiting badges, session/Copilot page |
| 2.1 No-code recipe builder / recorder | Out of scope — supported authoring path is recipe contract + UI editor + doctor |
| 2.2 Recipe marketplace / registry + CI dry-test + linter | Linter **already implemented** (schema + method contract, C3/F08); public marketplace out of scope; "most wanted portals" board is a process item (GitHub issue label), no code |
| 3.1 One-click VNC fallback | **Already implemented** — pause subsystem + per-run noVNC + ntfy deep links; open routing/auth design is the separate C6/F03 lane |
| 3.2 Self-healing selectors / VLM drift detection | Out of scope |
| 4.1 Docs for humans (end-user vs contributor paths) | Picked up by W3 (pull-image end-user path vs author/recipe docs) |
| 4.2 Trust & privacy positioning | Picked up by W3 (short "Your data stays local" section) |
| 4.3 Recipe-maintainer governance role | Out of scope — process, no code |

## Ordered execution

1. W2 (code + tests) — largest item; everything else references it in docs.
2. W1 (workflow + Dockerfile label move + install-script recipes dir).
3. W3 (docs).
4. Commit on dev via the dev-commits skill (suggested, user-confirmed per
   item), push to Gitea `origin/dev`; the issue-#27 plan C5 status update
   travels with the W2 commit (plans are versioned dev artifacts).
5. User-gated, at release time (deploy skill flow): first tag push publishes
   the image; verify the GHCR package is public and an unauthenticated
   `docker pull` works; update the README sample tag.

## Validation

- `ruff check` + `pytest` from the repo root (`PYTHONPATH=apps`) — full
  existing suite must stay green (it exercises `recipe_path_for`, task
  creation, and the runner).
- New tests (follow `tests/test_bc_recipes.py` / `tests/test_bc_db.py` /
  `tests/test_bc_runner.py` patterns):
  - overlay precedence: shadow present → extra path; absent → built-in;
    unset env → unchanged behavior (regression guard)
  - save path: overlay set → save lands in overlay dir (created as needed);
    unset → built-in dir
  - schema always resolves from the built-in dir
  - import/creation store NULL `recipe_file`; reconciliation resets
    auto-populated built-in rows; an explicit non-default override still wins
  - runner run-time resolution picks the shadow for an existing task
- `docker build --build-arg VERSION=v0.0-test .` locally: image label
  `org.opencontainers.image.version` is `v0.0-test`; a second build reuses
  the pip/playwright layers (cache check per README 531–539).
- `docker compose config --quiet` after the compose change.
- Workflow YAML: `actionlint` if available, else careful review; first live
  execution is user-gated (dispatch or next tag).

## Risks / notes

- First `docker push` creates the GHCR package; if the account default
  visibility is private, the README pull path breaks until flipped — the
  user-gated verification step catches this.
- Missing host `apps/recipes` → Docker creates it root-owned → editor saves
  fail; the quickstart `mkdir`/`chown` and `install_docker-image.sh` update
  cover the two supported install paths.
- The sanitized GitHub mirror's tag hashes differ from Gitea's — the workflow
  must not assume Gitea commit SHAs or refs (it does not; it only uses the tag
  name).
- Out of scope for this plan: `latest` tag, GitHub Release objects, C6 (F03
  noVNC routing) and C7 (F05 conversions) lanes, everything marked out of
  scope in W4.

## Open questions (non-blocking, decide at implementation)

- Push a `latest` alias on tag push as well? Current decision: **no** (pinned
  tags only).
- First live GHCR publication: `workflow_dispatch` verification now, or wait
  for the next release tag? Recommend the dispatch dry-run during this work,
  real tag at the next release.
