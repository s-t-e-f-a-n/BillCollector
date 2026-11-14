# C6 — F03: noVNC access path (design first)

> Status: W1–W3 complete (2026-11-11) — code, tests, compose and docs are in
> place and the C6 tests pass (ruff + pytest). The live check and the
> deployment-process validation (deploy skill) remain the user-gated gates
> before the NAS rollout. Delivery of C6 in
> `.kilo/plans/1792861675256-issue27-maintainer-commitments.md` is marked
> done.

Source: the C6 commitment in
`.kilo/plans/1792861675256-issue27-maintainer-commitments.md` (F03 from
GitHub issue #27, closed as triage 2026-10-24): "Specify one supported
routing/authentication design: published port binding (loopback-only host
bind + reverse proxy on the NAS) vs. authentication through the UI session;
document reverse-proxy/TLS requirements." Acceptance: "an unauthenticated
client cannot view or control a live browser through any published path;
authenticated intervention remains usable."

## Verified context (dev tree, 2026-11-11)

- **The hole.** `docker-compose.yml:73` publishes
  `"6080-6095:6080-6095"` on **all host interfaces**. Inside the container
  the per-run stack (`display.py`) runs `websockify <port>
  127.0.0.1:5900+N` — positional port form, so websockify binds
  **0.0.0.0** — serving the apt noVNC web client (`--web /usr/share/novnc`)
  and proxying RFB to `x11vnc -display :N -rfbport 5900+N -localhost
  -nopw` (the `vnc_password` Setting defaults to empty, `config.py:79`).
  While any run is alive, **every client on the LAN** can open
  `http://<nas>:608X/vnc.html?autoconnect=true` and get a live,
  fully-controllable view of the portal browser (entered credentials
  included). No credential anywhere in that path.
- **The iframe depends on the exposure.** The session page's noVNC tab
  (`ui/session.py`, M3 decision 6) builds the iframe `src` *client-side*
  from `window.location.hostname` + the run's `novnc_port`
  (`NOVNC_SRC_SCRIPT`) — it works precisely because the ports are
  published on all interfaces.
- **The ntfy deep link is safe.** It targets the session page
  (`<ui_base_url>/runs/<id>`, `notify.py`) which is auth-gated; the hole
  is the iframe inside it plus any direct port hit.
- **Other exposed surfaces.** The README published-image compose snippet
  (`README.md:261`) publishes the same range; host execution
  (`install_local.sh`, no Docker) runs the same `websockify` 0.0.0.0 bind
  on the dev host.
- **The app already has the right auth model.** Single-operator bcrypt
  password + signed Starlette session cookie with a persisted secret
  (`ui/auth.py`); every non-public path redirects to `/login`
  (`AuthRedirectMiddleware`), and each page re-checks via `require_auth`.
  Note: the middleware **passes websocket scopes through untouched** — a
  new WS route must check the session itself.
- **Proxying is feasible with zero new dependencies.** `websockets==17.1`
  is a direct pinned dep (`apps/requirements.txt`); the daemon can open a
  WS client to the in-container websockify and pump bytes.
- **noVNC client is path-aware.** Verified against the apt-shipped client
  (`/usr/share/novnc/app/ui.js`): the WebSocket URL is
  `ws(s)://host:port/<path>` where `path` (default `websockify`, no
  leading slash), `host` and `port` are read from the page's **query
  string first** (`initSetting` → `WebUtil.getConfigVar`), falling back to
  the page origin. So a client served at
  `/vnc/6080/vnc.html?path=vnc/6080/websockify` connects its WS to the
  same origin — the session cookie rides the upgrade automatically.
- **The quickstart already anticipates this design.**
  `doc/QUICKSTART.md:104`: the loopback UI-only override "deliberately
  leaves that channel unpublished while its deployment design is under
  review."

## Design decision: authenticate through the UI session

Chosen: **no noVNC ports are published; the daemon serves the noVNC live
view at `/vnc/<port>/` on the UI port, gated by the existing UI session.**
This is the "authentication through the UI session" option from C6.

Rejected: loopback-only host bind + reverse proxy on the NAS.

- The acceptance ("unauthenticated client cannot view or control a live
  browser through **any** published path") would rest on the operator's
  proxy configuration (auth + TLS + WebSocket upgrade) instead of being
  enforced in code — a misconfigured proxy re-opens the hole.
- The phone intervention path (M3 decision 5: the phone is a first-class
  intervention device; ntfy deep link → session page → noVNC tab) would
  need, per deployment, a proxy, TLS, a second credential (RFB password or
  basic auth), and a per-deployment base-URL setting for the iframe.
- It keeps two published port ranges and two credentials where one
  suffices.

### Mechanism

1. **Daemon noVNC proxy** — new `apps/billcollector/vncproxy.py`,
   registered from `build_app` (`ui/app.py`):
   - `GET /vnc/{port}/` and `GET /vnc/{port}/{path:path}` — serve the noVNC
     web client from `NOVNC_WEB_DIR` (`/usr/share/novnc`), path-mapped with
     a traversal guard (resolved path must stay inside the client dir);
     `/vnc/{port}/` → `vnc.html`. Non-public path → the existing
     `AuthRedirectMiddleware` 307s unauthenticated requests to `/login`;
     no client files are served unauthenticated.
   - `WS /vnc/{port}/websockify` — the tunnel. The auth middleware does
     not cover websocket scopes, so the route checks the session itself:
     read the `session` cookie from the upgrade request headers
     (`scope["headers"]`), validate it with the persisted `session_secret`
     (Starlette `Session`), require `authenticated` — else reject the
     handshake (403/close 1008). On success, open
     `websockets.connect("ws://127.0.0.1:{port}/websockify")` and pump
     bytes both directions (two tasks) until either side closes, then close
     both.
   - **Port allowlist**: `{port}` must be inside
     `6080 .. 6080 + display_count - 1` (Settings range) **and** equal the
     `novnc_port` of a Run row whose `result IS NULL` (a live run);
     otherwise 404. The display stack is runner-owned and reaped with the
     run, so a dead port would fail to connect anyway — the row check keeps
     the surface explicit and stops in-container port probing.
2. **Session page** (`ui/session.py`): the noVNC tab iframe becomes a
   same-origin, server-side `src`:
   `/vnc/{port}/vnc.html?autoconnect=true&path=vnc/{port}/websockify`.
   Delete `NOVNC_SRC_SCRIPT` (the client-side `window.location.hostname`
   hack) — one URL shape for localhost and LAN/phone operators, and the
   session cookie is attached to the page, the asset requests, and the WS
   upgrade by the browser itself.
3. **`display.py`**: websockify binds explicitly to loopback —
   `websockify 127.0.0.1:{port} 127.0.0.1:5900+N` (defense in depth for
   host execution and non-compose deployments; the daemon's own tunnel
   uses the same loopback and is unaffected). x11vnc stays
   `-localhost` + the existing per-run auth-file wiring.
4. **`docker-compose.yml`**: remove `- "6080-6095:6080-6095"` from
   `ports`; the UI port is the **only** published port. Header comment
   updated: the per-run live view is served by the daemon at
   `/vnc/<port>/` on the UI port, authenticated by the UI session; no
   noVNC ports are published.
5. **`vnc_password`**: kept, role re-scoped. It stays the optional
   **second layer** (x11vnc RFB auth) for non-standard deployments that
   deliberately publish the websockify ports (e.g. a dedicated VNC client
   on the host with a loopback publish). The supported path is the UI
   session. Settings field description and the `config.py` comment
   updated accordingly.

### Resulting security properties (acceptance mapping)

- **Unauthenticated client cannot view or control a live browser through
  any published path.** The only published port is the UI port; every HTTP
  path is session-gated (middleware + page re-checks), the noVNC client
  files are served only behind that gate, and the WS upgrade is
  independently session-checked. No other container ports are published.
- **Authenticated intervention remains usable.** Operator logs in →
  dashboard → session page (the ntfy deep link, unchanged) → Copilot
  actions + noVNC tab, all on the UI origin. Localhost, LAN, and phone
  operators get the same URL shape; the WSL2 dev flow (Windows browser via
  localhost forwarding) is unchanged because the noVNC tab now lives on
  the same port as the UI.
- The UI port's own trust model (LAN reachability + session auth, optional
  operator-side TLS in front of the UI port) is **unchanged** — C6 removes
  the second, unauthenticated exposure; it does not re-scope the UI.

### Docs (public, sanitized — no plan references)

- `docker-compose.yml` header (above).
- `README.md`: the published-image compose snippet drops the
  `6080-6095:6080-6095` line (~261); the "noVNC live view websockify ports
  `6080-6095`" port bullet (~342) becomes "no separate noVNC ports: the
  per-run live view is served by the daemon at `/vnc/<port>/` on the UI
  port, authenticated by the UI session"; the dev-mode note
  (`http://localhost:<websockify port>/vnc.html`, ~545) points at the
  session page's noVNC tab (the port still appears in the log line for
  reference).
- `doc/QUICKSTART.md`: the "UI password … does not configure the separate
  noVNC channel … under review" paragraph (~104) becomes "the UI session
  authenticates the noVNC live view too — there is no separate channel";
  the loopback-override note (~72) keeps working as-is (it never published
  the range); the "Limits and pending work" bullet (~150, "separate noVNC
  routing/authentication design remains maintainer-owned") is removed.
- `doc/TROUBLESHOOTING.md`: the "UI works but noVNC does not" row (~19)
  rewrites to: the noVNC tab is served on the UI port under the UI session
  — check the login state and that the run is still alive (the display
  stack is reaped with the run); the "do not publish the range" advice
  drops (there is no range to publish).
- `apps/.env.example` / settings docs: `vnc_password` role note (optional
  second layer for non-standard published-port deployments).
- `CHANGELOG.md` (Unreleased): the noVNC websockify ports are no longer
  published; the per-run live view is served through the authenticated UI
  at `/vnc/<port>/`; `vnc_password` re-scoped.

## Work items

### W1 — code (proxy + session page + display bind)

1. `apps/billcollector/vncproxy.py` per the mechanism above (static
   client serving + WS tunnel + session check + allowlist).
2. `ui/app.py`: register the proxy in `build_app`.
3. `ui/session.py`: same-origin iframe `src`; delete `NOVNC_SRC_SCRIPT`
   and its registration; keep the `novnc_port is None` hint.
4. `display.py`: loopback websockify bind; update the module docstring and
   the `start_display_stack` docstring.
5. Tests (existing patterns: `tests/test_bc_ui_session.py` user-fixture,
   `tests/test_bc_display.py` fake-binaries, `tests/test_bc_ui_app.py`
   app-build):
   - Proxy HTTP: unauthenticated `GET /vnc/6080/` → 307 `/login`;
     authenticated → 200 `vnc.html`; traversal (`../`) → 404; port outside
     the Settings range → 404; in-range port with no live Run row → 404.
   - Proxy WS: unauthenticated upgrade rejected; authenticated upgrade
     tunnels bytes both ways against a stub upstream (local
     `websockets.serve` on an in-range test port with a seeded live Run
     row) and closes when the upstream closes.
   - Session page: the iframe `src` is
     `/vnc/<port>/vnc.html?autoconnect=true&path=vnc/<port>/websockify`
     (update the `session-novnc` assertions; delete the
     `test_novnc_src_script_*` tests).
   - Display: the websockify args carry the `127.0.0.1:` listen bind
     (update the existing arg assertions).

### W2 — compose + docs

`docker-compose.yml` (port removal + header), `README.md`,
`doc/QUICKSTART.md`, `doc/TROUBLESHOOTING.md`, `apps/.env.example`,
`CHANGELOG.md` per the Docs section.

### W3 — plan status

Mark C6 done in
`.kilo/plans/1792861675256-issue27-maintainer-commitments.md` (C6 Status +
the Status section: remaining = C7 only).

## Validation

- `ruff check` + `pytest` from the repo root (`PYTHONPATH=apps`) — full
  suite green (the session-page and display tests are updated, not
  bypassed).
- `docker compose config --quiet` after the compose change.
- Live check (user-gated, dev): `docker compose up` + a mock-portal run —
  the noVNC tab loads under a logged-in session, shows the live browser,
  and is unreachable without login (direct `GET /vnc/…` → redirect; WS
  upgrade rejected).
- **Deployment-process validation (deploy skill) before NAS rollout** —
  required by the C6 note in the issue-#27 plan; the NAS deployment path
  is the reference `docker-compose.yml` (`install_docker-image.sh` builds
  the image, `docker compose up` starts the container), so the compose
  change is the rollout vehicle.

## Risks / notes

- **NiceGUI + WS routing**: the new `/vnc/{port}/websockify` route is
  distinct from the Socket.IO mount (`/socket.io`); the existing
  engineio disconnect-tolerance wrapper (app.py) is unaffected. Verified
  in the live check.
- **noVNC `path` parameter**: supported since noVNC 0.6 (verified in the
  apt-shipped client on noble); the value must **not** carry a leading
  slash (the client does `url += '/' + path`).
- **Existing deployments**: an image upgrade without a compose update
  leaves the old `6080-6095` publishes pointing at a now-loopback-bound
  websockify — unreachable from the LAN, i.e. fail-safe. The CHANGELOG
  entry tells operators to drop the old port lines from custom compose
  files.
- **Per-run port churn is unchanged**: displays are allocated from the
  Settings range exactly as today; only the network path to them changed.
- Out of scope: TLS for the UI port (operator concern, pre-existing),
  C7 (F05 protected-login conversion), and the in-daemon copilot (Stage 2
  of the recipe-doctor lane).
