# BillCollector — Local Test Web Service (Regression Test Environment) (v3)

> Status: DELIVERED in v0.4 (tag v0.4) — Layer A; Layer B execution lands with daemon M1/M3.

Changes vs v2:
1. **English UI labels** throughout (mock portal, recipes, download filenames) — consistent
   with the daemon plan's "UI language: English" decision.
2. **Alignment with the nicegui-daemon plan**
   (`.kilo/plans/1790364274061-billcollector-nicegui-daemon-plan.md`): that plan already
   foresees a mock portal — `tests/mock_portal/` (repo root), "small FastAPI app: cookie
   banner, login, fake CAPTCHA (displayed 6-digit code), drag-and-drop CAPTCHA, document
   download" (its "Validation" section) — needed from its M1–M3. **This plan implements
   that mock portal now, as a superset**, so one fixture serves both:
   - **Layer A (runnable now):** all current scraping-engine features, driven by a
     standalone harness against `retrieve_from_service_with_playwright()`
     (`BillCollectorServices_pw.py:382`).
   - **Layer B (runnable from daemon M1/M3):** scenarios the daemon runner adds —
     `wait_user`, 3×-failure auto-pause + resume, CAPTCHA code entry (Copilot), drag
     CAPTCHA (noVNC), persistent-profile behavior (cookie banner only on 1st run),
     download dedup, "changed website" repair drill. The mock's Layer B capabilities
     ship now; scenario execution lands with the daemon milestones. The daemon plan's
     mock-portal bullet is thereby implemented early / superseded.

Goal: a local web service emulating realistic bill portals so that all implemented — and
foreseen — scraping features of BillCollector can be run as a regression test load; the
standing test environment for future BillCollector development.

## Decisions

- **Scenario = service = site = recipe (1:1)**, mirroring production: the recipe is
  resolved purely by service name (`BillCollectorServices_pw.py:396-398`), the goto URL is
  fixed inside the recipe. The **user is only a dimension for testing user
  differentiation** within a scenario.
- **No real person names.** Users are short descriptive keywords when they carry test
  semantics (`wrongpass`, `nodocts`, `dlerror`), otherwise `userN`.
- **Location: repo-root `tests/`** (aligns with the daemon plan's `tests/` +
  `tests/mock_portal/`), not `apps/tests/`. Recipes stay in
  `apps/recipes_playwright/` (fixed by `RECIPES_PLAYWRIGHT_DIR`).
- **Harness:** standalone script (no pytest dependency yet); the daemon plan's M1 pytest
  suite can wrap it later.
- **Vault layer: covered by an opt-in e2e mode, not by the self-contained harness.**
  The default harness mode never touches Vaultwarden (credentials/URL from
  `scenarios.py`), so it stays CI-able. A `--vault` mode runs the same scenarios
  through the real production vault path (DNS local-IP check, status/unlock, sync,
  per-pair item + TOTP fetch, vault-derived URL) against the real LAN Vaultwarden —
  dev host only, not CI. (The earlier "DNS check cannot be satisfied locally"
  rationale only holds for loopback: `127.0.0.1` is not in the accepted `10.` /
  `172.16-31.` / `192.168.` ranges, `BillCollector.py:38-48`; the real LAN vault
  resolves to a local IP, so the check passes on the dev host.)

## Architecture

- **One mock web process** (FastAPI + Jinja2 — already in `requirements.txt`, no new
  dependencies) hosts **one site per scenario** under its own path base:
  `http://127.0.0.1:8787/<site>/...` (port default, `--port` override, 127.0.0.1 only).
  Layer A sites: `happy, graceful, badlogin, empty, dlfail` · Layer B sites:
  `waituser, captchadrag, autopause`.
- **Cookie model (drives the persistent-profile scenarios):**
  - `consent` cookie: `Path=/<site>/`, `Max-Age=31536000` → persists in the task's
    browser profile across runs → **cookie banner only on the 1st run** (daemon M1 exit
    criterion).
  - login session cookie: `Path=/<site>/`, session-scoped (no Max-Age) → gone when the
    browser closes → re-login on every run, even with a persistent profile.
  Each site is isolated by cookie `Path`; each batch run also starts with a fresh profile
  and cleared cookies (`BillCollectorServices_pw.py:35,405`).
- **`tests/scenarios.py` = single source of truth** (site registry, per-user data,
  credentials, expectations), imported by both the mock portal and the harness.
- **INI = test scope selector** (same format as `bc_default.ini`): which service/user
  pairs run. Custom scope = editing the lists.

## Layer A scenarios (runnable now — batch engine)

| service (site) | users | path (recipe) | server behavior | expected outcome |
|---|---|---|---|---|
| `testhappy` | `user1, user2, user3` | full happy path (below) | complete per-user data: 2 "Invoice dated …" rows + 1 "Contract info_…" row per user | success, 2 downloads per user (6 files) |
| `testgraceful` | `user1` | happy path + one `graceful: true` step targeting "Bonus document" | "Bonus document" is **never rendered** | success; step recorded as graceful error in DB, run continues, 2 downloads |
| `testbadlogin` | `wrongpass` | full path | login always rejected → re-render with "Login failed" | abort at OTP step (not found), 0 files |
| `testempty` | `nodocts` | full path | login OK; invoice page renders an **empty** table | abort at `get_by_text "Invoice dated"` (no match), 0 files |
| `testdlfail` | `dlerror` | full path | login OK, 1 row; download endpoint returns **HTTP 500** | abort at `expect_download` (timeout), 0 files |

**User differentiation** (the only dimension where the user matters) is tested by
`testhappy`: three users, same site/recipe, different credentials and per-user document
data/filenames. Failure scenarios use one user each; failure semantics live in the
scenario (site switch), not the user.

## Layer B scenarios (daemon runner, M1–M3 — mock ships ready)

| service (site) | users | scenario | expected daemon-runner behavior | milestone |
|---|---|---|---|---|
| `testwaituser` | `user1` | after OTP: page shows a random 6-digit code; recipe step `wait_user("Type the 6-digit code shown on the page, then press Verify")`; operator types code + "Verify" via Copilot or noVNC | pause → operator interacts → resume → verification passes → dashboard → download | M3 (`wait_user` method, Copilot) |
| `testcaptchadrag` | `user1` | after OTP: slider widget "Drag the slider to verify" (JS; complete drag → verified → dashboard); recipe step `wait_user("Drag the slider all the way to the right")` | pause → **noVNC** drag → resume → dashboard → download | M3 (noVNC, drag CAPTCHA) |
| `testautopause` | `user1` | after OTP: page shows button "I am not a robot"; recipe step `get_by_role button "Verified" → click`, but "Verified" only appears after the operator clicks "I am not a robot" | 3 step attempts fail → status `waiting` → operator clicks "I am not a robot" via Copilot → resume → step re-executes → dashboard → download | M1 (3× pause, control socket) |
| (behavior on `testhappy`) | any | **persistent profile, two runs:** run 1 fresh profile → banner present, consent step succeeds; run 2 same task profile → consent cookie persisted → banner absent, consent step (graceful) skips, login re-runs (session cookie expired) | "cookie banner only on the 1st run" verifiable | M1 (persistent per-task profile) |
| (behavior on `testhappy`) | any | **download dedup:** two runs serve byte-identical PDFs → 2nd run's downloads share sha256 with the 1st | `Download` rows recorded, 2nd run deduped (`duplicate_of_id`) | M1 (download tracking) |
| (any site) | any | **"changed website" repair drill:** `POST /admin/<site>/mutate` renames e.g. the "Log in" button → run fails at that step → recipe repaired in UI → re-run succeeds | failure context (screenshot, candidates) → YAML edit → git commit visible in `git log` | M3 (recipe editor) |

Layer B recipes are schema-valid today (`method` is a free-form string in
`recipe-pw-schema.yaml`) but are **not** part of any Layer A INI — executed by the batch
engine they abort deterministically (unknown method / no pause semantics).

## Feature coverage matrix

| Feature | covered by |
|---|---|
| `goto` (all production recipes) | first step of every recipe |
| consent banner (buhl, 1und1, kabeldeutschland) | "Reject" button (GET form) on landing; **graceful** (absent on persistent-profile run 2) |
| CSS `locator(selector)` (winsim, kabeldeutschland) | `#user-id` input |
| locator chain: `get_by_role` main → element (datev) | login form wrapped in `<main>` |
| `get_by_label` (winsim, buhl, datev, freenet) | "E-mail address" input, OTP input, "Close popup" |
| `get_by_role` textbox/button/link + `first` (buhl, 1und1, winsim, freenet, nuernberger) | login fields, "Log in", nav links, invoice rows |
| `get_by_placeholder` (1und1, nuernberger) | "e.g. myusername" input |
| `get_by_title` (winsim, 1und1) | password input `title="Password"` |
| `get_by_test_id` (1und1) | password input `data-testid="password-input"` |
| `get_by_text` + `first` (winsim, freenet, nuernberger) | "Invoice dated …" rows, "Contract info_…" row |
| `press` "Tab" (buhl) | after alias field |
| `expect_download`, incl. **two downloads per run** (all; nuernberger ×2) | `/…/download/…` with `Content-Disposition: attachment`, byte-stable PDFs |
| `content_frame` (freenet, currently commented-out SP consent) | iframe popup with "Close popup" |
| `close` (all) | last step of every recipe |
| `{{USERNAME}}` / `{{PASSWORD}}` / `{{OTP}}` (all / all / datev) | login + OTP forms |
| cookie-session login (all real services) | session cookie set at login, required on `/dashboard`+ |
| **`graceful` step flag (schema, untested today)** | `testgraceful` |
| **failed pair → skip, continue, exit 1 (`BillCollector.py:256-268`, untested today)** | `testbadlogin` / `testempty` / `testdlfail` in the full-scope INI |
| **`wait_user` recipe method (daemon M3)** | `testwaituser`, `testcaptchadrag` |
| **3×-failure auto-pause + resume (daemon M1)** | `testautopause` |
| **fake CAPTCHA, displayed 6-digit code (daemon mock spec)** | `testwaituser` |
| **drag-and-drop CAPTCHA (daemon mock spec)** | `testcaptchadrag` |
| **persistent profile / banner skip (daemon M1)** | `testhappy` run 1+2 |
| **download sha256 dedup (daemon M1)** | `testhappy` run 1+2 |
| **changed-website repair drill (daemon M3)** | admin mutate/reset endpoints |

## Recipes (eight files in `apps/recipes_playwright/`)

`recipe-pw__testhappy.yaml` — the full flow (all Layer A recipes are this flow with their
site's goto path; `testgraceful` adds the graceful step):

1. `goto http://127.0.0.1:8787/happy/`
2. `get_by_role` button "Reject" → `click` (**`graceful: true`** — absent when the consent cookie persists)
3. `get_by_role` main → `get_by_role` textbox "E-mail address" → `click` → `fill {{USERNAME}}`
4. `locator "#user-id"` → `click` → `fill {{USERNAME}}`
5. `get_by_placeholder` "e.g. myusername" → `fill {{USERNAME}}` → `press "Tab"`
6. `get_by_title` "Password" → `fill {{PASSWORD}}`
7. `get_by_test_id` "password-input" → `fill {{PASSWORD}}`
8. `get_by_role` button "Log in" → `click` (POST → 302 `/otp`)
9. `get_by_label` "6-digit code" → `fill {{OTP}}`; `get_by_role` button "Check and log in" → `click` (POST → 302 `/dashboard`)
10. `locator "iframe#popup-frame"` → `content_frame` → `get_by_label` "Close popup" → `click`
11. `get_by_role` link "My account" → `click`; `get_by_role` link "Invoices" (exact) → `click`
12. `get_by_text` "Invoice dated" → `first` → `click`
13. `expect_download` → nested: `get_by_role` link "Invoice" (exact) → `first` → `click`
14. `expect_download` → nested: `get_by_text` "Contract info_" → `first` → `click`
15. `close`

- `testgraceful`: + step between 12 and 13: `get_by_text` "Bonus document" (exact) →
  `click`, `graceful: true` (site never renders it).
- `testbadlogin` / `testempty` / `testdlfail`: same flow; the failure is triggered by the
  **server**, not the recipe; steps after the divergence stay in the recipe for
  completeness/validity.
- Layer B: `recipe-pw__testwaituser.yaml`, `recipe-pw__testcaptchadrag.yaml`,
  `recipe-pw__testautopause.yaml` — happy steps 1–9, then the scenario's friction step
  (`wait_user` / `wait_user` / `get_by_role button "Verified" → click`), then dashboard →
  invoices → one download → `close`.

## Mock portal design (`tests/mock_portal/`)

Run: `python3 -m tests.mock_portal --port 8787` from the repo root.

- **Site registry** in `scenarios.py`: per site — user data (invoice rows, document
  names), scenario switches (`reject_login`, `empty_docs`, `download_500`,
  `hide_bonus`, `captcha_code`, `captcha_drag`, `challenge`).
- **Routes** (parameterized by `/{site}/…`, shared Jinja2 templates):
  - `GET /{site}/` — consent banner (GET form, submit button "Reject"; hidden when the
    `consent` cookie is present) + login form.
  - `POST /{site}/login` — validates the five fields against `scenarios.py`
    (or rejects entirely when `reject_login`); success → session cookie +
    `consent`-aware state → 302 `/otp`; failure → 200 re-render with
    "Login failed".
   - `POST /{site}/otp` — validates the `{{OTP}}` value → 302 to the site's next stage
     (`/dashboard` or the scenario page); failure → re-render. Accepts the static test
     OTP (`123456`, self-contained mode) **or** a valid TOTP (RFC 6238, SHA-1, 6 digits,
     30 s period, ±1 window) computed from the user's `totp_secret` in `scenarios.py`
     (vault e2e mode; stdlib `hmac`/`base64`/`struct`, no new dependency).
  - `GET /{site}/popup` — iframe document: labeled button "Close popup" (removes the
    iframe via `onclick`).
  - `GET /{site}/dashboard` — session-protected (else 302 `/login`); iframe
    `#popup-frame` + link "My account" → `/account`.
  - `GET /{site}/account` — link "Invoices" → `/invoices`.
  - `GET /{site}/invoices` — per-user rows: "Invoice dated <date>" (each with exact link
    "Invoice"), "Contract info_<user> (PDF)" row, "Bonus document" link only where not
    `hide_bonus`; empty table for `empty`.
  - `GET /{site}/download/<doc>` — **byte-stable** minimal PDF
    (deterministic content, no timestamps → stable sha256 for the dedup scenario),
    `Content-Type: application/pdf`,
    `Content-Disposition: attachment; filename="invoice_<site>_<user>_1.pdf"` /
    `"contract_info_<site>_<user>.pdf"` (site prefix prevents collisions in the shared
    Downloads dir); HTTP 500 for `dlfail`.
  - Layer B pages: `GET /{site}/verify` (random 6-digit code shown + input
    placeholder "verification code" + button "Verify"; POST validates the code),
    `GET /{site}/drag` (JS slider; complete drag → verified), `GET /{site}/challenge`
    (button "I am not a robot" → JS swaps in button "Verified" → click → dashboard).
  - `GET /health` — `{"ok": true}` (readiness poll).
  - **Admin (repair drill):** `POST /admin/<site>/mutate` (JSON, e.g. rename the
    "Log in" button label) and `POST /admin/<site>/reset` — in-memory per-site
    overrides.
- **Login form fields (one per locator type):** `#user-id` (CSS),
  `<label for>` "E-mail address", placeholder "e.g. myusername", `title="Password"`,
  `data-testid="password-input"`; submit button "Log in". Form wrapped in `<main>`.

## Test INI (scope selectors, Layer A only)

`tests/bc_regression.ini` (full scope — mixed outcomes, BillCollector exit code 1):

```ini
[Playwright]
testhappy=user1, user2, user3
testgraceful=user1
testbadlogin=wrongpass
testempty=nodocts
testdlfail=dlerror
```

`tests/bc_regression_happy.ini` (success-only scope — all pairs succeed, exit code 0):

```ini
[Playwright]
testhappy=user1, user2, user3
testgraceful=user1
```

Layer B services are deliberately absent — they are executed by the daemon runner in
M1–M3, not by this harness.

## Harness (`tests/run_regression.py`, Layer A)

Run from the repo root: `python3 tests/run_regression.py --ini tests/bc_regression.ini
[--keep-downloads] [--port 8787] [--vault]`

**`--vault` (e2e mode, dev host only):** mirrors `WebRetriDoc`
(`BillCollector.py:191-255`) instead of sourcing credentials from `scenarios.py`.
Once per run: `load_dotenv(apps/.env)`, `is_domain_local_ip(VAULT_HOST)`,
`bitwarden_api_check_status(BW_API_URL)` (must be `unlocked`), `POST /sync` — any
preflight failure → exit 4 (missing `VAULT_HOST`/`BW_API_URL` included). Per pair:
`GET /object/item/<service> <user>` (username, password, **URI — the goto URL comes
from the vault item**, `BillCollector.py:248`) + `GET /object/totp/<service> <user>`
(400 = no TOTP → `None`), reusing the production client functions imported from
`BillCollector.py` (no duplicated vault code; after daemon M0 extracts `vault.py`,
switch this one import). A missing vault item kills the run via the client's
`sys.exit(1)`, exactly like production. Because the vault URIs bake in port 8787,
`--vault` requires the default port (the harness errors on a non-default `--port`).
All existing per-pair assertions apply unchanged.

1. **Concurrency guard:** non-blocking exclusive `fcntl.flock` on `apps/.bc.lock`
   (`helpers/BillCollectorHelpers.py:46`); abort with a clear error if a real
   BillCollector run holds it (shared browser profile + Downloads dir + DB).
2. Start the mock portal as a **subprocess**; poll `/health` (timeout 30 s); failure →
   exit 2.
3. Snapshot: `apps/Downloads` file set + latest `Service` run numbers per service name
   in `apps/db/bc.db`. Before the snapshot, sweep the scope's own expected filenames
   from `apps/Downloads` if a prior manual / interrupted run left them behind, so the
   new-files check counts this run's downloads (test files only, run lock held).
4. Read the INI with `configparser` (same format and loop order as `WebRetriDoc`,
   `BillCollector.py:224-260`); per (service, user) pair: call
   `retrieve_from_service_with_playwright(service, url, user, pwd, otp, False)`; on
   `False` → **skip and continue** (WebRetriDoc semantics). Default mode: credentials
   and URL from `scenarios.py`. `--vault` mode: the preflight above, then credentials /
   URL / TOTP from the vault item (see the `--vault` note).
5. Per pair, assert against `scenarios.py` expectations: return value, `Service` row
   `result` (success/failure) in the pair's new run table, and — for `testgraceful` —
   exactly one `PageStatus` row whose `result` JSON carries the graceful step error.
6. After all pairs: new files in Downloads == union of expected downloads (and only
   those); **skip-continue proof** — in the full scope, pairs after the first failing
   pair (`testempty`, `testdlfail`) actually ran; BillCollector exit semantics
   (`1` if any pair failed else `0`) as in `BillCollector.py:266-268`.
7. Print per-pair summary table (expected vs actual, files, DB result) + verdict.
   **exit 0 iff every expectation matched**, else 1.
8. `finally`: terminate the mock subprocess; delete downloaded test files unless
   `--keep-downloads`.

## Files (all new; zero production code changes)

- `tests/mock_portal/` — FastAPI app (`__init__.py`, `__main__.py`, `app.py`,
  `templates/`)
- `tests/scenarios.py` — site registry, per-user data, credentials, TOTP secrets
  (vault e2e), expectations
- `tests/run_regression.py` — Layer A harness (incl. `--vault` e2e mode)
- `tests/bc_regression.ini`, `tests/bc_regression_happy.ini` — scope selectors
- `apps/recipes_playwright/recipe-pw__testhappy.yaml`, `recipe-pw__testgraceful.yaml`,
  `recipe-pw__testbadlogin.yaml`, `recipe-pw__testempty.yaml`,
  `recipe-pw__testdlfail.yaml`, `recipe-pw__testwaituser.yaml`,
  `recipe-pw__testcaptchadrag.yaml`, `recipe-pw__testautopause.yaml`

The `--vault` e2e mode touches only already-existing test files (`tests/scenarios.py`,
`tests/run_regression.py`, `tests/mock_portal/app.py`).

No changes to: `BillCollector.py`, `BillCollectorServices_pw.py`, `helpers/*`, existing
recipes, the schema, `requirements.txt`.

## Relationship to the daemon plan

- Implements the daemon plan's `tests/mock_portal/` early (ahead of M1), as a superset of
  its spec (cookie banner, login, fake CAPTCHA code, drag CAPTCHA, download — plus the
  Layer A failure scenarios and the admin mutate endpoint).
- Daemon milestones consume it directly: M1 exit ("pause → ntfy → resume via
  control-socket test client → download tracked; profile accumulation verifiable") and
  M3 exit ("cookie banner → Copilot click; CAPTCHA code typed via Copilot; drag CAPTCHA
  via noVNC; recipe repair after a changed website") run against these same sites.
- The daemon plan's mock-portal validation bullet is superseded by this plan; no second
  mock portal should be built in M1.
- The daemon plan's M1 "Vaultwarden client" pytest reuses the same real-vault items and
  mock portal as the `--vault` e2e mode (items stay the shared fixture — do not duplicate
  them); client-level tests (retry, 400-TOTP, locked state) use stubs, not the real
  vault. After M0 extracts the shared `vault.py`, the harness `--vault` import switches
  from `BillCollector` to `vault.py` (one line).

## Constraints / non-goals

- No **vault emulation** in the self-contained mode (no fake Vaultwarden API — the
  DNS local-IP check would need a hostname resolving to a non-loopback local IP, which
  is host-specific and CI-hostile); the vault layer is covered by the real-vault
  `--vault` e2e mode instead. Client-level vault tests (retry, 400-TOTP, locked state)
  belong to the daemon plan's M1 pytest with stubs.
- Layer B scenario **execution** is not part of this implementation — it lands with the
  daemon runner (M1: autopause/profile/dedup; M3: waituser/CAPTCHAs/repair). This plan
  ships the mock capabilities + Layer B recipes, schema-validated.
- No CI integration implemented yet — it is designed and deferred under
  "GitHub / Gitea automation" (implement when that section's trigger conditions hold);
  until then the environment is a manual command, wireable into cron/daemon.
- DB rows for the test services accumulate in `apps/db/bc.db` (distinguishable by
  `service_name`); cleanup out of scope.
- Failing steps wait out Playwright's default 30 s timeout, so the three Layer A abort
  scenarios are slow by design (realistic); total full-scope run is a few minutes.
  (Layer B `testautopause` additionally costs 3×30 s of retries before the pause —
  daemon semantics.)

## Failure modes

- Port 8787 occupied → mock bind fails, readiness poll times out → harness exit 2 with a
  clear message (`--port` override).
- **Vault e2e (`--vault`):** `VAULT_HOST`/`BW_API_URL` missing in `apps/.env` → exit 4
  before anything runs; DNS check fails (unresolvable / non-local IP) → exit 4; vault
  locked → status check fails → exit 4; sync fails → exit 4; missing vault item → the
  production client's `sys.exit(1)` kills the run (production semantics); non-default
  `--port` with `--vault` → harness error (vault URIs bake in port 8787).
- Chromium missing in a fresh env → `playwright install chromium` (done by
  `install_local.sh`); harness surfaces the browser launch error.
- Mock crash mid-run → pair assertions fail loudly; subprocess always reaped in
  `finally`.
- Engine regression (e.g. broken locator dispatch) → affected pair's actual outcome
  deviates from expectation → harness exit 1 with the per-pair diff.
- Admin-mutated site left dirty → next Layer A run fails unexpectedly; `reset`
  endpoint + harness may reset all sites at start (implementation detail: reset on
  startup).

## Validation plan

1. `python3 apps/helpers/BillCollectorCheckRecipe.py <recipe>` → all eight recipes valid
   (incl. the Layer B ones with `wait_user`).
2. Standalone mock check: start `python3 -m tests.mock_portal`, manually click through
   the `happy` site as `user1` in a real browser (consent → login → OTP → popup → nav →
   PDFs open); manually verify the `waituser` (code), `captchadrag` (slider), and
   `autopause` (challenge) pages work in a browser.
3. Full scope: `python3 tests/run_regression.py --ini tests/bc_regression.ini` → all five
   Layer A scenarios behave as expected (graceful DB record, aborts, skip-continue),
   exit 0.
4. Success scope: `--ini tests/bc_regression_happy.ini` → all success, exit 0.
5. Negative control (dev-time check): rename one template label (e.g. "Log in") or use
   `/admin/…/mutate` → harness must report the deviation and exit 1 → reset/revert.
6. Layer B execution validation happens in the daemon plan's M1/M3 (pytest integration
   against this same mock portal).
7. **Vault e2e (dev host, real Vaultwarden, after the one-time item setup under
   "Vault e2e mode"):** `--ini tests/bc_regression_happy.ini --vault` → 4/4 pairs PASS,
   exit 0 (proves the mock accepted the real rotating TOTP); `--ini
   tests/bc_regression.ini --vault` → all seven pairs as expected, BillCollector exit
   semantics 1, exit 0 — the `testbadlogin` item deliberately has **no** TOTP, so the
   `get_totp` 400 path (`BillCollector.py:122-128`) is exercised; preflight negative:
   `apps/.env` moved aside → exit 4. The self-contained scopes (steps 3/4) must stay
   green and must not contact the vault.

## Validation status (first full check, 2026-09-30)

The environment was validated end-to-end on the dev host (Ubuntu 24.04, Python 3.12.3,
venv `apps/.venv`, Playwright 1.63.0 + Chromium). All steps of the Validation plan that
are runnable without the daemon runner passed; no code changes were needed.

- **Step 1 — recipe validation: PASS.** `BillCollectorCheckRecipe.py` (with
  `PYTHONPATH=apps`) validates all eight recipes against `recipe-pw-schema.yaml`,
  including the three Layer B ones whose friction step uses the free-form `wait_user`
  method.
- **Step 2 — standalone mock check: PASS (40/40 HTTP contract checks).** Driven by a
  throwaway `requests` script (redirects not followed, so 302 + `Location` + `Set-Cookie`
  are asserted directly): health + unknown-site 404; consent 302 sets `consent` with
  `Path=/happy/` + `Max-Age=31536000` and the banner disappears on the next landing;
  login 302 sets session-scoped `session_<site>` (no `Max-Age`); wrong-password re-render
  with "Login failed"; OTP wrong/right; session-protected dashboard/account/invoices with
  per-user rows + per-user filenames; byte-stable PDFs (identical sha256 across two
  downloads); `empty` (no rows), `dlfail` (download 500), `graceful` (no "Bonus document"),
  `badlogin` (registry password accepted); cookie `Path` isolation across sites; Layer B
  pages render (`verify` shows a 6-digit code + form, `drag` slider, `challenge` robot
  button); admin mutate/reset round-trip.
- **Step 3 — full scope: PASS.** `python3 tests/run_regression.py --ini
  tests/bc_regression.ini` → all seven pairs matched expectations: `testhappy` user1–3
  success (2 downloads each), `testgraceful` success with exactly one graceful-error
  `PageStatus` row (step 15 "Bonus document" 30 s timeout, run continued), `testbadlogin`
  / `testempty` / `testdlfail` each abort at the expected step (OTP fill / invoice row /
  download) with `Service` result `failure`; exactly the 8 expected files appeared in
  `apps/Downloads`; skip-and-continue held (every pair produced its own new `Service`
  run); BillCollector exit semantics reported as `1`. `VERDICT: PASS`, harness exit 0;
  the 8 test files were removed afterwards.
- **Step 4 — success scope: PASS.** `--ini tests/bc_regression_happy.ini` → 4/4 pairs
  success, `VERDICT: PASS`, harness exit 0.
- **Step 5 — negative control: PASS.** Renaming the login button label ("Log in" →
  "Sign in") made the engine abort at step 8 (`get_by_role button "Log in"` not found);
  the harness reported the return-value, DB-result and missing-download deviations and
  exited 1. The label was reverted and confirmed.
- **Step 6 (failure modes): PASS.** Port 8787 occupied → mock exits at startup, harness
  exits 2 with a clear message. `apps/.bc.lock` held by another process → harness exits
  3 ("another BillCollector run is in progress") before touching anything.

**Step 7 (vault e2e): PASS (2026-10-01).** The `--vault` mode, the mock's TOTP
acceptance and the seven one-time vault items (created in the real LAN Vaultwarden,
`vault.solg.duckdns.org`, API at `solg.fritz.box:8087`) are implemented and validated:

- **TOTP implementation:** all six RFC 6238 SHA-1 test vectors (30 s period, 6 digits)
  match at fixed `now`, incl. ±1-window acceptance.
- **Happy scope:** `--ini tests/bc_regression_happy.ini --vault` → 4/4 pairs PASS,
  exactly the 8 expected files, BillCollector exit semantics 0, harness exit 0 — the
  mock accepted the real rotating TOTP from the vault items.
- **Full scope:** `--ini tests/bc_regression.ini --vault` → all seven pairs matched
  (3 happy success, graceful success + exactly one graceful-error row, badlogin /
  empty / dlfail failure), BillCollector exit semantics 1, harness exit 0. The
  `testbadlogin` item deliberately has **no** TOTP: the `get_totp` 400 path
  (`BillCollector.py:122-128`) fired ("No TOTP for this vault item, continuing
  without OTP") and the pair still aborts at the OTP step (step 9) — with `otp=None`
  the engine's `fill` fails immediately (TypeError) instead of after the 30 s locator
  timeout of the self-contained mode; the outcome (False / failure, 0 files) is
  identical. That fill edge is unreachable in production (items without TOTP carry
  no `{{OTP}}` recipe step), so the engine stayed unchanged (zero production code
  changes, as planned).
- **Preflight negative:** `apps/.env` moved aside → "VAULT_HOST and BW_API_URL"
  error, harness exit 4 before anything runs; `.env` restored.
- **Self-contained scopes stayed green** after the `--vault` work (happy scope re-run:
  4/4 PASS, exit 0, no vault contact).

One harness fix during validation: the new-files download check miscounted when a
prior manual run had left the expected test files behind in `apps/Downloads` (they
were then not "new"). The harness now sweeps the scope's own expected filenames
before the run (`sweep_stale_downloads` in `run_regression.py`; test files only,
run lock held).

**Open (deferred to the daemon plan by design):** Layer B scenario execution
(`testwaituser` / `testcaptchadrag` / `testautopause`) and the daemon-runner behaviors
(persistent-profile banner-skip, download sha256 dedup, 3×-failure auto-pause, changed-website
repair drill) land in daemon M1–M3 against this same mock; the mock's Layer B capabilities
and the Layer B recipes are validated and ready. A real-browser click-through of the three
Layer B friction pages (code entry, slider drag, robot click) is part of M3.

## Usage in development (procedures)

The regression environment is the **acceptance fixture for the scraping-engine surface**:
recipe → Playwright locator dispatch → step / DB / download semantics. Any engine behavior
worth having should have a `(site, user)` scenario in `tests/scenarios.py` plus an
`EXPECTATIONS` entry; the INI scopes select which scenarios run, and the harness asserts
them. It covers `BillCollectorServices_pw.py`, `helpers/*`, `BillCollector.py` (pair loop +
exit semantics), the recipe schema, and the test recipes — and, via the `--vault` e2e mode
(dev host only), the vault layer (`BillCollector.py:51-131,194-251`: DNS check, status,
sync, item/TOTP fetch). It does **not** cover: real-portal behavior, the daemon UI/runner.

**Standard commands (from the repo root):**

- Recipe validation: `PYTHONPATH=apps apps/.venv/bin/python apps/helpers/BillCollectorCheckRecipe.py <recipe.yaml>`
- Success scope (~4.5 min, exit 0 when green): `apps/.venv/bin/python tests/run_regression.py --ini tests/bc_regression_happy.ini`
- Full scope (~8.5 min, exit 0 when green; reports BillCollector exit semantics = 1 because
  the failure scenarios are intentional): `apps/.venv/bin/python tests/run_regression.py --ini tests/bc_regression.ini`
- Harness self-test (negative control — only when `tests/` itself changed): temporarily
  mutate one template label or one `EXPECTATIONS` value → the run must go red with exit 1 →
  revert.
- Vault e2e (dev host only, real Vaultwarden, not CI-able):
  `apps/.venv/bin/python tests/run_regression.py --ini tests/bc_regression_happy.ini --vault`
  (success scope, exit 0) / `--ini tests/bc_regression.ini --vault` (full scope; reports
  BillCollector exit semantics = 1).

**Manual run (single pair, headed — visual follow):**

To watch one (service, user) pair step through the recipe in a real browser window (recipe
debugging, visual verification), run the mock in one terminal and the production engine,
headed, in another (both from the repo root):

```bash
# terminal 1: mock
apps/.venv/bin/python -m tests.mock_portal --port 8787
# terminal 2: single pair, headed
PYTHONPATH=apps apps/.venv/bin/python -c "
from BillCollectorServices_pw import retrieve_from_service_with_playwright
ok = retrieve_from_service_with_playwright('testhappy', 'http://127.0.0.1:8787/happy/', 'user1', 'user1-pass', '123456', True)
print('result:', ok)
"
```

- Last argument `True` = debug mode: headed Chromium + the **space bar pauses/resumes** the
  run (`on_debug_start_keyboard_listener`, `BillCollectorHelpers.py:145`) — step through the
  recipe action by action. `False` = headless, as in the harness.
- Credentials come from `CREDENTIALS` in `tests/scenarios.py`; the URL is the site's path
  base (`testhappy` → `/happy/`).
- This is a real engine run: new `Service` row in `apps/db/bc.db`, PDFs in
  `apps/Downloads`, shared browser profile. The raw function does **not** acquire
  `apps/.bc.lock` (only `BillCollector.py:316` and the harness do) — never run it while the
  harness or a production/cron run is active.
- Expected outcome for `testhappy`/`user1`: `result: True`, 2 files in `apps/Downloads`
  (`invoice_happy_user1_1.pdf`, `contract_info_happy_user1.pdf`), success `Service` row.
  Downloaded files stay behind (the harness is what cleans them up) — delete by hand or
  re-run the harness to sweep.
- WSL2: the headed Chromium window appears on the Windows desktop (WSLg), and the mock is
  also reachable from a Windows browser at `http://127.0.0.1:8787/happy/` via localhost
  forwarding (use a real browser, not the editor's built-in one — the session/cookie flow
  and PDF attachments need full browser behavior).

**Vault e2e mode (`--vault`, dev host only):**

Exercises the production vault path (DNS local-IP check → status/unlock → sync →
per-pair item + TOTP fetch → engine, vault-derived URL) against the real LAN
Vaultwarden, with the same per-pair assertions as the default mode. Not CI-able (real
vault, LAN, `apps/.env`, one-time items); CI keeps the self-contained mode.

One-time setup — create these items in Vaultwarden (done 2026-10-01 via the API's
`POST /object/item`, all seven verified by round-trip incl. the 400 TOTP response for
`testbadlogin wrongpass`). The item **name** must be exactly
`<service> <user>` (how `WebRetriDoc` builds it, `BillCollector.py:241`); login username
/ password / URI as listed; TOTP = the base32 secret from `tests/scenarios.py`:

| item name | login username | login password | URI | TOTP |
|---|---|---|---|---|
| `testhappy user1` | `user1` | `user1-pass` | `http://127.0.0.1:8787/happy/` | secret |
| `testhappy user2` | `user2` | `user2-pass` | `http://127.0.0.1:8787/happy/` | secret |
| `testhappy user3` | `user3` | `user3-pass` | `http://127.0.0.1:8787/happy/` | secret |
| `testgraceful user1` | `user1` | `user1-pass` | `http://127.0.0.1:8787/graceful/` | secret |
| `testbadlogin wrongpass` | `wrongpass` | `wrong-password` | `http://127.0.0.1:8787/badlogin/` | **none** (pair aborts at the missing OTP field before the code is used; exercises the `get_totp` 400 path) |
| `testempty nodocts` | `nodocts` | `nodocts-pass` | `http://127.0.0.1:8787/empty/` | secret |
| `testdlfail dlerror` | `dlerror` | `dlerror-pass` | `http://127.0.0.1:8787/dlfail/` | secret |

Secrets: six random base32 values (e.g.
`python -c "import base64,os;print(base64.b32encode(os.urandom(16)).decode().rstrip('='))"`),
stored in `tests/scenarios.py` next to the user data (fake test secrets — committing them
is fine, as with the fake passwords already there). The mock's OTP endpoint accepts a
valid TOTP for the user's secret (±1 window) in addition to the static `123456`.

**Procedures by development activity:**

1. **Engine / helper change** (`BillCollectorServices_pw.py`, `helpers/*`, `BillCollector.py`,
   schema): run the happy scope as the fast gate, then the full scope before merge / before a
   production cron run. On red: the per-pair diff line names the pair + the deviated
   expectation; the mock log path is printed; re-run with `--keep-downloads` and inspect
   `PageStatus_<service>_RunN` in `apps/db/bc.db`.
2. **New production service / recipe**: first build a mock scenario emulating the portal
   (see "Extending the environment" below) with a recipe + expectations and run it — a new
   portal is tested without touching the real one. Then validate the real recipe with
   CheckRecipe only (the mock cannot stand in for the real portal's drift).
3. **New engine feature** (new locator method, new recipe `method`, graceful handling,
   dedup, pause/resume): extend the environment **first** (scenario + mock route + recipe +
   `EXPECTATIONS`), then implement, then run the covering scope. A feature is not done until
   a scenario exercises it and the harness asserts it.
4. **Incident → regression test**: when a production run fails, encode the failing site's
   behavior as a mock scenario (the "changed website" repair drill) so the incident becomes a
   standing regression scenario.
5. **Toolchain / dependency bump** (Playwright pin, Python, `requirements.txt`): re-run
   CheckRecipe over all 15 recipes (7 production + 8 test) plus the full scope (the M0
   pattern).
6. **Daemon development (M1–M3)**: the daemon runner's pytest suite wraps this harness and
   executes the Layer B scenarios against the same mock. `SITES` / `CREDENTIALS` /
   `EXPECTATIONS` / `run_pair()` are the shared fixture — do not duplicate them in the daemon
   suite.
7. **Pre-cron / pre-deploy smoke**: run the happy scope as a quick "engine is healthy" check
   before pointing a run at the real portals.

**Extending the environment (add a scenario):**

1. Add the site to `SITES` in `tests/scenarios.py` (scenario switches + per-user data).
2. Add / adjust a mock route + template in `tests/mock_portal/` if the flow needs new page
   behavior.
3. Add `CREDENTIALS[service][user]` — and, for `--vault` coverage, a `totp_secret` plus a
   Vaultwarden item named `<service> <user>` (username/password/URI per the item table).
4. Add `EXPECTATIONS[service][user]` (`return`, `service_result`, `downloads`, and
   `graceful_error` where applicable).
5. Create `apps/recipes_playwright/recipe-pw__<service>.yaml` (goto URL = the site's path
   base).
6. Validate with CheckRecipe.
7. Add the service to a scope INI (or create a new scope).
8. Run the scope; iterate until green.
9. Layer B (daemon-driven) scenarios stay **out** of the Layer A INI; the daemon pytest
   executes them.

## GitHub / Gitea automation

### Decision memo — when integration makes sense

Why it is CI-able at all: the harness is fully self-contained — 127.0.0.1 mock, no secrets,
no vault, no external portal, pinned `apps/requirements.txt`, and `playwright install
chromium`. It is the only part of BillCollector that can be automated; a real-portal run can
never be put into CI.

Integration makes sense when **all** of these hold:

1. **The change rate justifies it.** The engine surface is touched regularly — concretely
   from daemon M1 onward (runner, pause/resume, per-task profile, download tracking) and M3
   (`wait_user`, recipe editor). Today (pre-daemon) engine changes are rare and each is
   followed within a day by a real-portal cron run, so a manual 9-minute run is cheaper than
   maintaining a CI job.
2. **A runner exists.** The primary remote is Gitea (self-hosted); GitHub is only a mirror
   (`sync_github.sh`). The workflow must run on a Gitea Actions runner (NAS or dev host) —
   or on GitHub Actions if CI is pointed at the mirror. Without a runner there is nothing to
   integrate into. Gitea Actions reads the same `.github/workflows/*.yml` syntax.
3. **The pytest wrapper exists (daemon M1).** The daemon plan already foresees an M1 pytest
   suite wrapping this harness. CI should run that suite (or the harness directly), not a
   second copy of the assertion logic.

It does **not** make sense: as a replacement for the production cron smoke (a green CI never
proves a production run works); before a runner exists and while engine changes are rare
(maintenance cost outweighs the benefit); or as a per-PR full-scope gate (9 min with 30 s
timeouts — use the happy scope per PR, the full scope on main / nightly).

### Actionable CI plan (implement when the triggers hold)

**Runner prerequisites (one-time, on the self-hosted runner host):** Ubuntu 24.04-class
host, Python 3.12, a registered Actions runner; pre-install Chromium system libraries once
(`sudo playwright install-deps chromium`) or give the runner user passwordless sudo, so CI
itself only runs `playwright install chromium`.

**Workflow:** add `.github/workflows/regression.yml` (lives with the primary remote, i.e.
Gitea; synced to the GitHub mirror, which can run it too if Actions is enabled there):

```yaml
name: regression

on:
  push:
    paths:
      - "apps/BillCollectorServices_pw.py"
      - "apps/helpers/**"
      - "apps/BillCollector.py"
      - "apps/recipes_playwright/**"
      - "tests/**"
      - "apps/requirements.txt"
  schedule:
    - cron: "17 3 * * *"
  # pull_request:            # enable once the Gitea version / runner supports PR events
  #   paths: (same as push)

jobs:
  happy:   # fast per-change gate
    runs-on: [self-hosted]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-${{ hashFiles('apps/requirements.txt') }}
      - uses: actions/cache@v4
        with:
          path: apps/browser
          key: pw-${{ hashFiles('apps/requirements.txt') }}
      - name: Install deps + Chromium
        env:
          PLAYWRIGHT_BROWSERS_PATH: "$GITHUB_WORKSPACE/apps/browser"
        run: |
          python -m venv .ci-venv
          .ci-venv/bin/pip install -r apps/requirements.txt
          .ci-venv/bin/playwright install chromium
      - name: Run happy scope
        run: .ci-venv/bin/python tests/run_regression.py --ini tests/bc_regression_happy.ini

  full:    # main + nightly
    if: github.event_name == 'schedule' || github.ref == 'refs/heads/main'
    runs-on: [self-hosted]
    steps:
      # same checkout / python / cache / install steps as "happy"
      - name: Run full scope
        run: .ci-venv/bin/python tests/run_regression.py --ini tests/bc_regression.ini
```

**Integration notes:**

- **Browser path:** the helper sets `PLAYWRIGHT_BROWSERS_PATH=apps/browser` on import, so
  install Chromium into `apps/browser` (the env var above) and cache that directory — do not
  rely on the default `~/.cache/ms-playwright`.
- **Invoke the harness with the venv python** so the mock subprocess (started via
  `python_for_mock()`) inherits the same interpreter.
- **Isolation is free:** the checkout is ephemeral, so the harness's writes to the shared
  `apps/db/bc.db`, `apps/Downloads`, and the browser profile are harmless; the lock file and
  the port-8787 guard already protect the run.
- **On failure:** upload `apps/db/bc.db` and the mock log (path printed by the harness) as
  artifacts for triage.
- **Rollout:** deploy the runner → pre-install Chromium deps → add the workflow → watch the
  first `full` run on main → then enable the `pull_request` trigger as the per-PR gate.
- **Out of scope here:** real-portal / daemon-UI coverage stays with the production
  cron and the daemon plan's M1–M3. The `--vault` e2e mode is **not** CI-able (real LAN
  Vaultwarden + `apps/.env` + one-time vault items) — the workflow runs the
  self-contained mode only.

## Open questions

None — remaining details (port 8787, site path bases, English labels, byte-stable
minimal-PDF payloads, three happy-path users) are decided above and trivial to adjust
during implementation.
