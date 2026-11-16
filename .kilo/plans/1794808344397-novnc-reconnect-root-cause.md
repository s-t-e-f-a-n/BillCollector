# NoVNC "second connect" failure — root cause & fix plan

**Status:** root cause established (live A/B proof, 2026-11-16). Fix pending
(S4–S8 below).

**Symptom (NAS, reproducible):** start a service run -> open NoVNC: OK ->
navigate to the dashboard -> open the run again -> NoVNC: no connection.

**Related:** `1794655634347-c6-novnc-rollout-steps.md` (C6 rollout).
**Sessions:** `ses_e1eb13874ffevZcOUGp5bwFzyD` (v5 tunnel repro), the
2026-11-16 session (live proof).

## Root cause

x11vnc exits when the last VNC client disconnects — that is its **default**
behavior (x11vnc 0.9.16 `-help`: "…disconnects, opposite of -forever. This
is the Default."). The C6 display stack starts x11vnc **without `-forever`**
(`apps/billcollector/display.py:250-256`: only `-display -rfbport
-localhost [-rfbauth|-nopw]`), so:

1. viewer opens NoVNC -> websockify dials x11vnc:5900+N -> OK (1st check),
2. user navigates to the dashboard -> the page is torn down -> the noVNC
   WebSocket closes -> that was the only client -> **x11vnc exits**,
3. user re-opens the run -> new noVNC page -> websockify dials 5900+N ->
   **ECONNREFUSED** -> `1011 Failed to connect to downstream server`.

The run itself is unaffected: Xvfb + Chromium keep running, only the VNC
server is gone — matching the NAS symptom exactly. websockify itself stays
up (it dials the downstream per client connection), so once x11vnc keeps
listening no restart logic is needed anywhere.

## Evidence

1. **v5 repro timeline** (2026-11-15 23:10, `/tmp/kilo/tunnel_repro/`):
   viewer A disconnected at 23:10:07; entries B–F all got ECONNREFUSED from
   websockify (`1011`); the x11vnc log ends with "viewer exited" and the
   process was gone.
2. **x11vnc help text:** exit-on-last-disconnect is the documented default;
   `-forever` keeps listening.
3. **Live proof, without `-forever`** (2026-11-16): a probe client
   (`/tmp/kilo/tunnel_repro/probe_exit.py`) completed the RFB handshake
   against the leftover repro x11vnc started with the exact production args
   (`-display :99 -rfbport 5999 -localhost -nopw`), then disconnected ->
   x11vnc (pid 125786) **exited**, nothing listened on 5999 anymore, Xvfb
   :99 stayed alive.
4. **Live A/B proof, with `-forever`** (2026-11-16): same probe against
   `x11vnc -display :98 -rfbport 5998 -localhost -nopw -forever` -> x11vnc
   **survived 12s after the client disconnected**, listener kept.
5. **Single production spawn site:** `display.py:250-256` (tests stub the
   binaries); grep found no other x11vnc invocation in the codebase.

## Side findings (not the production bug)

- The v5 "33B scrambled ServerInit" was the **repro client's parser bug**
  (wrong header field offsets), not an x11vnc/tunnel defect.
- A `-nopw` x11vnc offers only VncAuth(1) but **skips the DES challenge**:
  the 4-byte securityResult comes directly after the type selection, then
  the client must still send the 1-byte ClientInit before the
  FramebufferInit.
- The probe's FramebufferInit width/height parse is still off (probe-side
  quirk, same category as the repro parser bug); irrelevant to the fix.
- WSL2 gotcha (known, handled by `display.py` `_stack_env` at lines
  161-171): x11vnc refuses to start when `WAYLAND_DISPLAY` is exported
  ("Wayland display server detected … Exiting."). Any **manual** x11vnc
  test must strip it: `env -u WAYLAND_DISPLAY XDG_SESSION_TYPE=x11 x11vnc …`.

## Plan (small steps, one per turn — no step needs context from another)

- [x] **S1** Confirm production spawn args + single spawn site
      (`display.py:250-256`).
- [x] **S2** Live proof: x11vnc without `-forever` exits on last-viewer
      disconnect (probe against the leftover :99 stack).
- [x] **S3** Live A/B: x11vnc with `-forever` keeps the listener after the
      viewer disconnects (fresh :98 stack).
- [x] **S4** Fix: add `-forever` to `vnc_args` in
      `display.py` `start_display_stack` (+ update the docstring that
      lists the args).
- [x] **S5** Test: assert `-forever` is in the x11vnc args in
      `tests/test_bc_display.py` (`test_x11vnc_is_started_with_forever`,
      following the `recording_spawn` pattern). Display suite: 20 tests,
      OK (1 env-gated skip).
- [x] **S6** Validate: full suite green — `PYTHONPATH=apps
      apps/.venv/bin/python -m pytest tests/ -q` -> 861 passed, 11
      skipped (env-gated), 142 subtests passed.
- [ ] **S7** NAS validation with the user's exact repro: run a service ->
      NoVNC OK -> dashboard -> re-open the run -> NoVNC still connects.
- [x] **S8** Commit + push to Gitea `origin/dev` (user-gated), update the
      C6 rollout plan doc, tidy the `/tmp/kilo/tunnel_repro/` leftovers.

## Open questions

- **`-shared`:** x11vnc's default is noshared — a second client kicks the
  first. C6 has one viewer, but a noVNC auto-reconnect could briefly
  overlap old and new client. Keep the change minimal (`-forever` only);
  add `-shared` only if S7 shows a flaky first reconnect.
- No other component needs changing: websockify, display
  allocation/release, and `stop_display_stack` (already tolerates dead
  children) are all unaffected.
