# C6 noVNC rollout — step-by-step instructions (user-gated)

> Status: PENDING (2026-11-14) — instructions for the remaining C6 steps,
> after W1–W3 (code / tests / compose / docs / plan status) were completed
> 2026-11-11 and validated (ruff clean; full suite 857 passed / 11 skipped;
> compose YAML valid with the UI port as the only published port). The
> complete C6 change set sits uncommitted on `dev`.

Source: the Validation section of
`.kilo/plans/1794427909584-c6-novnc-access-path.md` (the user-gated gates)
and the C6 commitment in
`.kilo/plans/1792861675256-issue27-maintainer-commitments.md` (deployment-
process validation before the NAS rollout).

Scope: from the current `dev` tree state to C6 live on the NAS. Steps 1 and
3 are drivable from the dev session; step 2 needs a Docker host (NAS or dev
box).

## Step 1 — commit + push C6 to Gitea `dev` (dev session drives)

1. In the session say "commit" — the dev-commits skill proposes logical
   commits, each user-confirmed. Expected shape:
   - `feat: vncproxy — session-gated noVNC live view on the UI port`
     (`apps/billcollector/vncproxy.py`, `ui/app.py`, `ui/session.py`,
     `display.py`, `config.py`, `ui/settings.py`,
     `tests/test_bc_vncproxy.py`, `tests/test_bc_display.py`,
     `tests/test_bc_ui_session.py`)
   - `docs: noVNC ports no longer published` (`docker-compose.yml`,
     `README.md`, `doc/QUICKSTART.md`, `doc/TROUBLESHOOTING.md`,
     `CHANGELOG.md`)
   - `doc: plans — C6 marked done (issue #27) + rollout instructions`
     (the `.kilo/plans` files)
2. Push to `origin/dev` (Gitea).

## Step 2 — live validation on a Docker host (user-gated: NAS or dev box)

The WSL2 dev host has no Docker, so this runs on the NAS or another
Docker-capable machine.

1. Update the host to the new `dev` commit;
   `docker compose up -d --build billcollector`.
2. `docker port <container>` → expect **only** the UI port
   (`${BC_UI_PORT:-8766}:8000`); no `6080-6095`.
3. Log in at `http://<host>:<BC_UI_PORT>/login`; trigger a mock-portal run
   (**Run now**, e.g. the winsim task).
4. Session page → **noVNC tab**: it must show the live browser while the
   run is alive.
5. From a second machine, logged out:
   `curl -sI http://<host>:<UI_PORT>/vnc/6080/` → expect `307` with
   `Location: /login`; an incognito tab on the session page must not
   render the VNC view.
6. (Optional, phone path) open the ntfy deep link over the LAN → the
   noVNC tab works.
7. Report the results back to the session; they are recorded in the
   C6 plan's Validation section.

## Step 3 — release + NAS rollout (deploy skill, user-gated)

1. In the session say "release" or "deploy to NAS" — the deploy skill runs:
   pre-promotion regression validation, ff-only promote `dev` → Gitea
   `main`, publish the sanitized GitHub mirror (`sync_github.sh`), tag +
   release notes (user opt-in + review gate), then `deploy_remote.sh` to
   the NAS.
2. If the NAS uses a **custom** compose file: drop the old
   `6080-6095:6080-6095` line (the reference compose no longer publishes
   it; the CHANGELOG entry instructs this). An image upgrade without the
   compose update is fail-safe: the old publishes point at the now-
   loopback-bound websockify and are unreachable.

## Step 4 — close-out

1. After a good rollout, archive the C6 plan to `.kilo/plans/completed/`
   and update its cross-references (plan-file convention).
2. C7 (F05 protected-login conversion) is the only open commitment — a
   separate lane, needs per-provider portal access windows.
