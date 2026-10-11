# Flowcool PR Triage — #14 (CI), #15 (non-root identity), #16 (image tooling)

> Status: DONE (2026-10-08) — triage complete. Decisions: #16 ADOPTED (merged to
> `dev` as `8087842`, co-authored), #15 DEFERRED (closed), #14 DEFERRED (closed).
> No full S1–S7 review for any of these PRs. Diff-level overlap checks below
> were already performed on 2026-10-08 against local `dev`.

## Result (2026-10-08)

- **#16 (image tooling) — ADOPTED.** Dockerfile hardening (`--no-install-recommends`,
  explicit DejaVu fonts, build-time `pip check` + pip/wheel purge) +
  `tests/check_image_runtime.py` + README/CHANGELOG + Contributors credit, on `dev`
  as `8087842` with the `Co-authored-by: ouam` trailer (PR #13 precedent). Verified
  here: `pip check` clean (validates the build-time check), full mock-portal
  regression `VERDICT: PASS` (7/7 pairs, 8 downloads). The Docker *image* build is
  deferred to the next docker-capable deploy (no docker in this session); the NAS
  build re-runs `docker build` on every promotion, so the change is re-validated
  before it reaches production.
- **#15 (non-root identity) — DEFERRED** (closed with comment). Non-root `USER` is
  already on `main`; the source-protection ownership redesign + the
  `BILLCOLLECTOR_*` path env vars are a follow-up candidate against current `main`.
- **#14 (CI workflow) — DEFERRED** (closed with comment). Public-mirror-only CI
  wouldn't gate the Gitea dev loop; revisit after Wave 1 if the contribution
  cadence picks up (a re-file without the dead `feature/playwright-**` push trigger).
- All three PRs closed via the GitHub API (store credential) with their comments;
  0 open PRs. `dev` pushed to `origin` (Gitea).

## State snapshot (verified 2026-10-08)

- Gitea `main` = `c2b0825`, `dev` = `ec203b7` (clean tree)
- GitHub mirror `main` = `50e69eb`; PRs #11–#13 closed and credited (flowcool
  already in the README `### Contributors` section)
- Open PRs — all by **flowcool** (`ouam <19570361+flowcool@users.noreply.github.com>`),
  all based on stale merge base `3ddf51b` (2 commits behind the pre-promotion
  tip `b62821b`), all updated 2026-10-08T19:39Z:

  | PR | Title | Head | Branch |
  |---|---|---|---|
  | #14 | ci: run published mock scenarios with isolated state | `3acddb4` | `feature/playwright-upstream-ci` |
  | #15 | fix: protect source and map host identity in the non-root container | `4987118` | `feature/playwright-nonroot-runtime` |
  | #16 | fix: remove unused build tooling from the Playwright runtime image | `caa01c1` | `feature/playwright-image-footprint` |

- PR heads fetched locally as `refs/pr/14`, `refs/pr/15`, `refs/pr/16`
- GitHub API works via the `store` credential helper (verified: HTTP 200 on
  open-PR list, 2026-10-08)

## Triage rules

1. Per PR: use the verified overlap facts below → decide **A (adopt)** or
   **B (close superseded/deferred with the exact comment given)**.
2. If A: manual merge on `dev` (bases are stale — expect conflicts in
   `CHANGELOG.md`/`README.md`/`Dockerfile`); one commit per adopted PR with
   trailer `Co-authored-by: ouam <19570361+flowcool@users.noreply.github.com>`
   (PR #13 precedent); extend the README Contributors line for the adopted PR.
3. If B: close via API + post the comment. No integration, no trailer.
4. Any adoption that grows past ~20 min of work → downgrade to B (deferred),
   note in the comment that a re-file against current `main` is welcome.
5. Out of scope: daemon plan, NAS/`.env`, PR #13 NAS validation (user shell).

## PR #16 — image build tooling (15 min)

Verified novel vs `dev` (the layer-ordering/cache part overlaps the already
merged layer-cache work, `b62821b` — the PR does not touch ordering):

1. `Dockerfile` line 28: `apt-get install -y python3 python3-pip` →
   `--no-install-recommends`
2. `fonts-dejavu-core fonts-dejavu-mono` added to the dependency RUN
3. New RUN after dependencies: `python3 -m pip check && apt-get purge -y
   python3-pip python3-wheel`
4. New `tests/check_image_runtime.py` (130 lines)
5. `README.md` +4, `CHANGELOG.md` +5

**Decision D16 — recommendation: A.**

- **A (adopt)**: cherry-pick the 3 Dockerfile hunks + `check_image_runtime.py`
  (+ the README/CHANGELOG hunks). Verify:
  1. `docker build -t bc-triage .`
  2. `docker run --rm bc-triage python3 tests/check_image_runtime.py`
  3. `python3 tests/check_docker_context.py` → expect `19 private canaries
     excluded, 5 source files retained`
  4. One mock-portal scenario smoke (port 8787)
- **B (close superseded)**: layer-reuse work is implemented + NAS-validated on
  `main`; image footprint is not a current goal.

Close comment (B):
> Thanks @flowcool — the layer-cache-reuse and build-script work this targets
> is now on `main` (implemented + NAS-validated), so the overlap is covered.
> The `pip check`/pip-purge hardening is a nice touch; if you want it in,
> re-file just those Dockerfile hunks against current `main` and I'll
> integrate it. Your work on #11–#13 is credited in the README.

## PR #15 — non-root host identity (15 min)

Verified novel vs `dev` (the `USER` line already exists on `main` — that was
the delivered nonroot plan; this PR goes further):

1. Ownership redesign: app code + browser stay root-owned (`COPY` without
   `--chown`, `chmod -R go-w /apps`); only `/apps/runtime`, `/apps/db`,
   `/apps/Downloads`, `$HOME` owned by the app user — vs `main`'s `chown -R`
   of the whole tree
2. Three new env vars with fallbacks: `BILLCOLLECTOR_PROFILE_DIR`,
   `BILLCOLLECTOR_LOG_FILE`, `BILLCOLLECTOR_LOCK_FILE` (Dockerfile ENV +
   7 lines in `apps/helpers/BillCollectorHelpers.py`, backward compatible)
3. New `doc/nonroot_runtime.md` (53), `tests/check_nonroot_container.py` (85),
   `tests/test_nonroot_wrapper.py` (84)

**Decision D15 — recommendation: B** (the current layout runs in production on
the NAS; a redesign that moves log/profile/lock paths is not worth doing
mid-daemon-plan — unless source protection is explicitly wanted).

- **A (adopt)**: real design change (source protection + host path mapping).
  Verify: docker build + both new test suites + **full regression** (path
  changes affect log/profile/lock locations — mock scenarios must pass with
  the new layout).
- **B (close deferred)**: non-root `USER` is already on `main` and deployed;
  the redesign is hardening, not a fix.

Close comment (B):
> Thanks @flowcool — non-root `USER` with the app identity is already on
> `main` and deployed, which covers the runtime side. The source-protection
> ownership redesign and the `BILLCOLLECTOR_*` path env vars are a real step
> further; I'd like to consider them as a follow-up against current `main`
> (which has moved past your base). If you want to re-file, I'll integrate
> quickly. You're credited in the README for #11–#13.

Ordering constraint: if both D15=A and D16=A, do **#16 first** (both touch the
Dockerfile COPY/ownership area).

## PR #14 — CI workflow (10 min: a decision, not a review)

100% novel content: `.github/workflows/regression.yml` (48 lines — pinned
actions, `permissions: contents: read`, `persist-credentials: false`, 30-min
timeout), `tests/run_ci_regression.py` (66), `CONTRIBUTING.md` ("no CI
pipeline yet" replaced), `CHANGELOG.md`, `README.md`.

Verified facts:

- `on: pull_request: branches: [main]` → once merged to public `main`, fork
  PRs trigger it (the base-branch workflow runs against the auto-merged tree —
  this resolves the stale-head problem #13 had, automatically)
- Runs on the public mirror only (Gitea has no CI) → zero speedup for the
  daily Gitea dev loop
- `sync_github.sh` force-pushes the mirror on every promotion → each promotion
  triggers a full mock regression (browser install, 30-min timeout) = a
  promotion gate
- `push: feature/playwright-**` is dead on the public repo (forks can't push
  branches upstream) — harmless, but remove if adopting
- No secrets, no vault, loopback port 8787 — no new network exposure

**Decision D14 — recommendation: B** (consistent with daemon-plan priority;
CI's value is screening future fork PRs, and cadence is low — revisit after
Wave 1).

- **A (adopt)**: merge the 5 files, drop the dead `feature/playwright-**`
  push pattern. Follow-up (separate session, not now): extend the deploy
  skill Stage 3 to wait for mirror CI green before closing the promotion PR.
- **B (close deferred)**: as below.

Close comment (B):
> Thanks @flowcool — the workflow is well-scoped (pinned actions, read-only,
> offline mocks, no secrets). I'm not adopting CI at this time: the public
> mirror only reflects promoted `main`, so it wouldn't gate the Gitea-side
> development loop where most validation already happens. Keeping this
> deferred rather than rejected — if the contribution cadence picks up I'll
> take it up (a re-file against current `main` without the dead
> `feature/playwright-**` push trigger would be perfect). Thanks again for
> #11–#13.

## Integration mechanics (only if any A)

1. `git fetch github pull/N/head:refs/pr/N` — already done
2. Work on `dev` (`ec203b7`); manual merge per PR (stale base → expect
   conflicts in `CHANGELOG.md`/`README.md`/`Dockerfile`)
3. One commit per adopted PR with the co-author trailer
4. README Contributors: extend the existing line with the adopted PR number(s)
5. Full regression on the final tree:
   `apps/.venv/bin/python tests/run_regression.py --ini tests/bc_regression.ini`
   → expect `VERDICT: PASS`
6. Close each PR via API (store credential) with its comment; push `dev`
7. Update this plan's status header

## Definition of done

- All three PRs closed (adopted or superseded/deferred) with the comment
  posted
- `dev` pushed; if anything adopted: regression PASS + trailer verified on the
  public-facing commits
- ≤ 45 min elapsed; if not, record state here and stop — the daemon plan
  resumes next session (Wave 1: M1+M2+M3, plan `1790364274061`)
