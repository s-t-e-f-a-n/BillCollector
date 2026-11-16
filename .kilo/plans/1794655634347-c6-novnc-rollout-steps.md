# C6 noVNC rollout — step-by-step instructions (user-gated)

> Status: Step 1 done, Step 2 partially validated (2026-11-16) — the C6
> change set (`28b8c32` + `2c5e0a0` + `2197ae8`, plan status `8ef3758`)
> plus the noVNC 2nd-connect fix (`10e21a3` + `422e9f3`) are committed and
> pushed to Gitea `origin/dev` (in sync). NAS live check passed 2026-11-16:
> the noVNC tab shows the live browser and the reconnect repro passed
> (item 5). Remaining Step 2 items: 2 (`docker port` → UI port only),
> 6 (unauthenticated `GET /vnc/…` → 307), 7 (optional ntfy deep link).
> Then Step 3 (deploy skill, user-gated) and Step 4 close-out (archive both
> C6 plans).
>
> History: W1–W3 (code / tests / compose / docs / plan status) completed
> 2026-11-11 and validated (ruff clean; full suite 857 passed / 11 skipped;
> compose YAML valid with the UI port as the only published port).
>
> 2026-11-16: the second-NoVNC-connect failure (x11vnc exited with the last
> viewer; re-entry failed with `1011 Failed to connect to downstream
> server`) is fixed on `dev` with `-forever` — root cause + validation
> (DELIVERED, NAS check passed 2026-11-16):
> `.kilo/plans/completed/1794808344397-novnc-reconnect-root-cause.md`.
> Step 2's validation must include the reconnect repro (item 5).

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
5. **Reconnect repro** (regression check for the x11vnc `-forever` fix):
   from the session page navigate to the dashboard, open the run again —
   the noVNC tab must connect again (before the fix this failed with
   "Failed to connect to downstream server").
6. From a second machine, logged out:
   `curl -sI http://<host>:<UI_PORT>/vnc/6080/` → expect `307` with
   `Location: /login`; an incognito tab on the session page must not
   render the VNC view.
7. (Optional, phone path) open the ntfy deep link over the LAN → the
   noVNC tab works.
8. Report the results back to the session; they are recorded in the
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
