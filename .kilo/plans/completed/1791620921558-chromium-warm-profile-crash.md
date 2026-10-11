# Chromium warm-profile download crash — root cause, fix, re-validation

> **Status: RESOLVED (2026-10-10)** — root-caused and fixed in the runner; recorded in
> the v3 master plan (M1 exit validation). Kept in `completed/` for the record.

## Goal

Find the reason the Chromium 153 (`chromium-1243`) browser process crashes
deterministically at the first download (invoice PDF) when the persistent
per-task profile has prior-run state, apply the minimal targeted fix in the
runner (preserving cookies/login per decision 9), and prove it with a fresh +
warm E2E cycle on the mock portal.

## Context

- Blocker recorded in
  `.kilo/plans/1790364274061-billcollector-nicegui-daemon-plan.md` (M1 item 3a
  Status, "Known blocker"): SIGTRAP CHECK then SIGSEGV NULL deref @0x1 in the
  browser process, `GpuControl.CreateCommandBuffer` transient failure preceding
  the crash under xvfb, `--disable-gpu` did not mitigate.
- The user restarted WSL; `/tmp/bc-runner-e2e-attempt1|2` (the original
  crashpad stacks) are gone. Current evidence is post-restart and intact.
- The crash now reproduces on WSLg `:0`, not only under xvfb — display
  backend is not the trigger.

## Evidence (post-WSL-restart, all paths verified present)

- Fresh profile works: `/tmp/warm-dl-probe/runA.log` — `A: RUN_OK`, both PDFs
  saved (`A_invoice.pdf`, `A_contract.pdf`).
- Warm profile crashes: `/tmp/warm-dl-probe/runB.log` —
  `playwright._impl._errors.TargetClosedError: Download.save_as: Target page,
  context or browser has been closed` at `d.save_as(...)` of the invoice.
- Warm minus `Preferences` still crashes: `/tmp/warm-dl-probe/runP.log`
  (identical TargetClosedError) → Preferences is not the trigger.
- Fresh + `Cookies` only works: `/tmp/warm-dl-probe/runC.log` — `C: RUN_OK`,
  "no consent banner" proves the consent cookie is active → Cookies is not
  the trigger.
- Real runner E2E, warm run: `/tmp/bc-runner-e2e-attempt3/run2.log` —
  `Run aborted: Step 15 failed to download: failure: download error
  Download.save_as: Target page, context or browser has been closed` →
  `Task 1 run 2 failed (result=failure, downloads=[])`. Fresh run 1 of the
  same E2E succeeded (`run1.log`).
- Reproduction harness: `/tmp/warm-dl-probe/probe.py` (full warm profile
  `/tmp/warm-dl-probe/profile`), `probe_c.py` (cookies-only profile
  `/tmp/warm-dl-probe/profile.cookies`). Warm full-state snapshot preserved at
  `/tmp/warm-dl-probe/profile.full`. Probes launch
  `launch_persistent_context(user_data_dir=..., headless=False,
  args=["--disable-software-rasterizer"])` against the mock portal
  `http://127.0.0.1:8787/happy/` (login `user1`/`user1-pass`, OTP `123456`).
- Browser: `chromium-1243` under `apps/browser` (pinned via
  `PLAYWRIGHT_BROWSERS_PATH` in `apps/billcollector/config.py:43`).
- No `Crashpad` directory exists under any probe profile; the real
  browser-side stack (signal + frames) is not on disk and must be re-captured
  (Phase 1).

## Bisection state

| Run | State | Result | Conclusion |
|---|---|---|---|
| A | fresh | OK | baseline |
| B | warm (all) | crash @ invoice save_as | reproduced |
| P | warm − Preferences | crash | Preferences excluded |
| C | fresh + Cookies | OK | Cookies excluded |

Remaining suspects (present in B/P, absent in A/C), with hypotheses:

- H2 `Default/Cache` (HTTP disk cache, ~112K): run 1 cached the invoice PDF
  response; run 2 serves it from disk cache during artifact generation →
  download-specific crash. Prime suspect.
- H1 GPU caches: `Default/GPUCache`, `Default/DawnGraphiteCache`,
  `Default/DawnWebGPUCache` (~300K each) + `GPUPersistentCache/` (profile
  level, ~32K): stale cache keyed to a different GL context; consistent with
  the earlier `GpuControl.CreateCommandBuffer` failure.
- H3 `Default/blob_storage`: stale blob dirs from run 1 (downloads are blob
  artifacts).
- Residual: `Code Cache` (js/wasm), `Local Storage`, `Session Storage` +
  `Sessions`, `DIPS`, `Web Data`, `History`, `Login Data*`, `Network
  Persistent State`, `Trust Tokens`, `Shared Dictionary`,
  `first_party_sets.db`, `segmentation_platform/ukm_db`, `Reporting and NEL`.

## Tasks

### Phase 0 — Environment preflight

1. Mock portal up on `127.0.0.1:8787` (FastAPI app in `tests/mock_portal`,
   previous runs used `mock.pid`); start it if not running.
2. Display: `ls /tmp/.X11-unix/X0` — use WSLg `:0` if present (matches the
   B/P/C runs); otherwise `xvfb-run -a` (documented fallback). Record the
   display used per run in the result log.
3. Snapshot the warm-state reference: keep `/tmp/warm-dl-probe/profile.full`
   as the canonical warm source; create working area
   `/tmp/warm-dl-bisect/` for new variants and logs.

### Phase 1 — Re-capture the real browser-side crash (1 run)

1. Re-run probe B (full warm profile) with browser stderr captured:
   `DEBUG=pw:browser pw:api python probe.py B` → tee to
   `/tmp/warm-dl-bisect/crash-stderr.log`. This surfaces Chromium's
   CHECK/SEGV message and any crashpad output.
2. Locate crashpad reports: check `Crashpad/` inside the user data dir,
   `~/.config/chromium*/Crashpad`, `~/.cache/`; copy any `.dmp`/report to
   `/tmp/warm-dl-bisect/crashpad/`.
3. Extract signal + top frames into
   `/tmp/warm-dl-bisect/crash-stack.txt`. Frame areas immediately distinguish
   H1 (`gpu::`/`viz::`) from H2 (`network::`/`cache::`/`blink` download path).
   If no stack is obtainable, proceed — Phase 2/3 still isolate the trigger.

### Phase 2 — Warm-state bisection (grouped, then split)

1. Generalize the probe: `/tmp/warm-dl-bisect/probe_matrix.py` taking
   `(profile_dir, tag)` (copy of `probe.py` with `PROFILE`/`OUT` from argv,
   same mock-portal flow, same launch args).
2. Build variant profiles = fresh empty dir + one state group copied from
   `profile.full/`:
   - G1 `Default/Cache` (H2)
   - G2 all four GPU caches: `Default/GPUCache`, `Default/DawnGraphiteCache`,
     `Default/DawnWebGPUCache`, `GPUPersistentCache/` (H1)
   - G3 `Default/blob_storage` (H3)
   - G4 `Default/Code Cache`
   - G5 residual: everything else listed above
3. Run each (tag `G1`…`G5`), log OK/crash per
   `/tmp/warm-dl-bisect/run<tag>.log`.
4. If a group crashes: split it to single directories and re-run until one
   state directory is the minimal trigger. If every group passes alone: run
   pairwise combinations of the groups that are individually OK (start with
   G1+G2) before declaring an interaction.

### Phase 3 — Mitigation probes on the full warm profile (independent of Phase 2)

One run each, full warm `profile.full` (fresh copy per run to stay clean),
record OK/crash:

- M1 launch arg `--in-process-gpu`
- M2 launch arg `--disk-cache-size=0`
- M3 `headless=True` (new headless, no display)
- M4 replace `d.save_as(path)` with `d.path()` + local file copy (separates
  crash location: download pipeline vs artifact transfer)
- M5 launch arg `--disable-gpu` re-check on `:0` (previously only tested
  under xvfb)

### Phase 4 — Implement the fix (decision rules)

Apply in `apps/billcollector/runner.py` `_launch_browser`
(apps/billcollector/runner.py:169) as a small pre-launch helper that
**only touches cache state, never cookies/login/Preferences**:

- Trigger = G1 (HTTP cache): delete `Default/Cache` before launch. Fallback
  if a wipe proves fragile: launch arg `--disk-cache-size=0` (verify M2 first).
- Trigger = G2 (GPU caches): delete the four GPU cache dirs before launch.
  Keep `BC_CHROMIUM_ARGS` (`--disable-software-rasterizer`) behavior
  unchanged; confirm no regression of the WSL2 cold-frame fix.
- Trigger = G3 (blob storage): delete `Default/blob_storage` (holds only
  blob artifacts) before launch.
- M4 shows the crash is artifact-transfer-only: prefer the `download.path()`
  + copy path in `downloads.track_download` (apps/billcollector/downloads.py:39)
  and note the Playwright/Chromium version for an upstream report.
- Group interaction or no single trigger: use the Phase 3 mitigation that
  passed (M1–M3) via `BC_CHROMIUM_ARGS`-style launch args in
  `config.chromium_args()`, and file an upstream report with the Phase 1
  crash stack.
- The wipe helper logs exactly which dirs it removed (`logger.info`), and is
  a no-op for fresh profiles.

Do not change the persistent-profile contract: no profile deletion, no cookie
clearing, no Preferences rewrite beyond the existing
`_ensure_pdf_preference` (apps/billcollector/runner.py:156).

### Phase 5 — Re-validation

1. Full E2E in a scratch `BC_*` env (as attempt3: `BC_DATA_DIR`, `BC_DB_DIR`,
   `BC_DB_FILE`, `BC_BROWSER_DIR`, `BC_PROFILE_ROOT`, `BC_DOWNLOAD_DIR` under
   `/tmp/bc-runner-e2e-attempt4/`), mock portal + real vault preflight:
   - run 1 (fresh profile): exit 0, `Run.result=success`, 2 `Download` rows,
     consent banner present;
   - run 2 (warm profile): exit 0, `Run.result=success`, step 15/16
     downloads tracked as **duplicates** (cross-run sha256 dedup), consent
     banner absent, no "Target page, context or browser has been closed"
     warnings in the run log.
2. Unit suite green: `python -m unittest discover -s tests` (48 tests) from
   `apps/`.

### Phase 6 — Record findings

1. Update the "Known blocker" paragraph in
   `.kilo/plans/1790364274061-billcollector-nicegui-daemon-plan.md` with:
   trigger state, crash stack excerpt (Phase 1), applied fix, re-validation
   result. `/tmp` is wiped by WSL restarts — the plan file must carry the
   key log/stack excerpts and the exact reproduction recipe (probe
   command + mock-portal start) so the crash is re-producible without the
   `/tmp` artifacts.
2. Note in the same plan: the fix also protects the Docker/NAS deployment
   (C6 Xvfb display path uses the same persistent-profile code).

## Failure modes / risks

- `/tmp` volatility: snapshot `profile.full` + key logs into
  `/tmp/warm-dl-bisect/` at Phase 0; if WSL restarts mid-investigation,
  Phase 0 rebuilds variants from `profile.full` (itself a copy of
  `profile/`, so re-snapshot from a fresh B-run if needed).
- WSLg `:0` instability: fall back to `xvfb-run -a` and record it; the
  crash reproduces on both, so a display change invalidates nothing.
- Each probe run is one full mock-portal login + 2 downloads (~1–2 min);
  Phase 2+3 total is ~12 runs. A hung browser (crash without CDP response)
  can wedge the probe — always run probes under `timeout 180`.
- Mock portal session state: restart the portal between runs if login starts
  failing (previous runs used separate `mock.pid`/`mock2.pid` instances).
- G2 wipe must not regress the WSL2 cold-frame actionability fix
  (commit 9e8dc5c): validate with a fresh-profile E2E in Phase 5 run 1.

## Out of scope

- C5 pause subsystem, C6 display allocation, C7 orchestrator work (separate
  M1 chunks).
- Upstream Playwright/Chromium bug fix (only an optional report in Phase 4).
- Real-portal (F5) validation — mock portal only.
- Docker/NAS deployment changes (the runner-side fix applies automatically;
  image-level validation is a later M1 step).

## Open questions

None — scope confirmed by user: diagnose + fix + re-validate in one session,
targeted cache wipe permitted (cookies/login untouched).

## Progress log (intermediate results — updated per phase)

### Phase 0 — preflight (2026-10-10, session 2)

- Display: WSLg `:0` present (`/tmp/.X11-unix/X0`) — used for all runs,
  matches B/P/C.
- Mock portal: system python3 is PEP 668 externally managed and lacked
  uvicorn/fastapi (old `mock.pid` PIDs dead after WSL restart).
  **Convention established**: venv at `/tmp/bc-probe-venv`
  (`python3 -m venv /tmp/bc-probe-venv && /tmp/bc-probe-venv/bin/pip install
  uvicorn fastapi jinja2 python-multipart` — python-multipart is REQUIRED,
  login returns 500 without it). Start portal from repo root with
  `/tmp/bc-probe-venv/bin/python -m tests.mock_portal --port 8787`
  (background process; log to `/tmp/warm-dl-bisect/mock.log`). If `/tmp` was
  wiped, recreate the venv the same way.
- `/tmp/warm-dl-probe/profile.full` verified intact (canonical warm source);
  working dir `/tmp/warm-dl-bisect/` created.
- Probe scripts `probe.py` (tag B = full warm) / `probe_c.py` still in
  `/tmp/warm-dl-probe/`; `probe_matrix.py` (Phase 2) not yet created.
- Probe interpreter: `apps/.venv/bin/python` (has playwright; system python3
  does NOT). Browsers live in `~/.cache/ms-playwright/chromium-1243`
  (`PLAYWRIGHT_BROWSERS_PATH=apps/browser` only matters inside the app venv's
  launch config; probes use the default cache path).

### Phase 1 — crash re-capture (2026-10-10, session 2)

- `/tmp/warm-dl-bisect/probe_matrix.py` created:
  `probe_matrix.py PROFILE OUT TAG [extra launch args...]`, env
  `PROBE_HEADLESS=1` (M3), env `PROBE_SAVEAS=path` (M4: d.path()+copy instead
  of save_as). Same flow/args as `probe.py`.
- B1 run (fresh copy of `profile.full` → `/tmp/warm-dl-bisect/profileB`,
  `DEBUG="pw:browser pw:api" DISPLAY=:0 timeout 180 apps/.venv/bin/python
  probe_matrix.py <profile> /tmp/warm-dl-bisect B1`) **reproduced the crash**:
  `pipestatus=1`, no RUN_OK; browser process died.
- **Real browser-side stack (re-captured)** — `/tmp/warm-dl-bisect/crash-stderr.log`
  + `/tmp/warm-dl-bisect/crash-stack.txt`:
  - `Received signal 11 SEGV_MAPERR 000000000090` (SIGSEGV, fault addr 0x90 =
    null-object field access).
  - Crash in the **browser process** (main chrome pid), **49 ms after the
    invoice download link click** ("click action done" → "navigations have
    finished" → SEGV). First download of the warm run, as before.
  - Top frames (chrome binary is stripped; `addr2line` → `??`, offsets only):
    `chrome+0x6a9abc2`, `+0xb760493`, libc `+0x4532f`, then
    `+0xac693d2 +0xac69b01 +0xac688c4 +0xac69309 +0xac6a962` (cluster),
    `+0x446906f +0x5c67f13 +0x5dbad95 +0x5dbc4e0 +0x3591169 +0x3d7bee0`,
    glib `+0x5d634 +0xbcbf6 +0x5cad2`, `+0x3596279 +0x3db624c +0x3db5935
    +0x62f8d21 +0x62f90c2 +0x5fcee1f +0x4e13bf3` … 38 frames total.
  - Pre-crash noise (non-causal): dbus UPower error at launch,
    `GpuControl.CreateCommandBuffer` kTransientFailure (~10 ms after launch,
    also present in OK runs), crashpad cpufreq read errors.
- **No Crashpad reports**: Playwright launches chrome with
  `--disable-breakpad`, so nothing is written to disk — the stderr capture
  above is the only browser-side evidence. `~/.config`, `~/.cache`, profile
  dirs contain no `Crashpad/` report dirs.
- Frame clustering around `chrome+0xac6xxxx` (5 adjacent frames) is a
  single subsystem; H1 (gpu::/viz::) vs H2 (network::/blink download) cannot
  be told apart without symbols → Phase 2 bisection decides.

### Phase 2 — warm-state bisection (2026-10-10, session 2)

Scripts: `/tmp/warm-dl-bisect/run_matrix.sh`, `run_hsplit.sh`,
`run_pairs.sh`, `run_quads.sh`, `run_quads2.sh` (quadrant pattern: build
group dirs from the parent, fresh profile copy per run, `timeout 180`,
log `run_<TAG>.log`). All runs on WSLg `:0`, venv python.

Round 1 (groups vs `profile.full` partition): G1 Cache **OK**, G2 GPU caches
**OK**, G3 blob_storage **OK**, G4 Code Cache **OK**, G5 everything-else
**CRASH** → trigger fully inside G5 (no G1–G4 interaction needed).
Split: G5a (Default/ residual) **CRASH**, G5b (top-level residual) OK.
Split H1 (network/auth state incl. Cookies) OK, H2 (Preferences) OK,
H3 (storage/UI: Local/Session Storage, Sessions, WebStorage, History, Top
Sites, Favicons, Web Data, …) OK, H4 (remaining DBs: Login Data, GCM,
Reporting, shared_proto_db, commerce DBs, …) OK.
Pairwise (13 runs): **only H3+H4 crashes** (P34/P43); every pair with H1 OK
(H1 excluded entirely).
Quadrants: H3a+H4a OK, H3a+H4b OK, H3b+H4a OK, **H3b+H4b CRASH**.
Second split: H3c (History, Top Sites, Web Data, Favicons, Account Web
Data, Affiliation, Shortcuts) × H4d (commerce +
declarative_performance_observer, heavy_ad_intervention_opt_out,
shared_proto_db): **H3c+H4d CRASH**, others OK.
Third split: H3e (History, Top Sites, Shortcuts) × H4f
(declarative_performance_observer.db, heavy_ad_intervention_opt_out.db,
shared_proto_db): **H3e+H4f CRASH**, others OK.
File level: **History(+journal) + shared_proto_db CRASH**; all other
quadrants OK. History-alone OK, shared_proto_db-alone OK.

**RESULT — minimal deterministic trigger: `Default/History` AND
`Default/shared_proto_db` both present in the persistent profile.**
- Journal files not required (`V1`: History without journal + shared_proto_db
  → crash).
- Neither file triggers alone (U1/U2 OK) → genuine two-state interaction,
  not a single-file poison.
- Crash confirmed on every step of the bisection (browser process exit at
  the first/invoice download, identical signature to Phase 1).
- Note: `shared_proto_db` is the network service's shared proto DB
  (HSTS/cookie/network prefs persistence); `History` is the browsing
  history SQLite. The crash is in the browser process during download
  handling of a warm profile carrying both.
- Per Phase 4 decision rules this is the "group interaction / no single
  trigger" case → mitigation via Phase 3 (M1–M5) + upstream report; a
  targeted wipe of just these two DBs before launch is a candidate
  alternative fix (more surgical than a launch arg) — to be weighed in
  Phase 4 against the M-results.

### Phase 3 — mitigation probes (2026-10-10, session 2)

Script `/tmp/warm-dl-bisect/run_mitigations.sh`; each on a fresh copy of
`profile.full`, WSLg `:0`:

- M1 `--in-process-gpu`: **crash**
- M2 `--disk-cache-size=0`: **crash**
- M3 `headless=True`: **OK** (RUN_OK)
- M4 `d.path()` + copy (instead of `save_as`): **crash** → crash is in the
  browser process during download handling, NOT in the CDP artifact transfer
- M5 `--disable-gpu` (re-check on `:0`): **crash**

Only headless avoids it → the crash is tied to headed display rendering at
download time, not to GPU-process configuration per se.

### Phase 4 — fix (2026-10-10, session 2)

Decisive wipe tests on full warm `profile.full` (2026-10-10):
- `W` (full warm − `History`; `shared_proto_db` is a DIRECTORY, `rm -f`
  skipped it): **OK**
- `W2` (full warm − History/History-journal, repeat): **OK**
- `X` (full warm − `shared_proto_db/` dir only): **OK**

Either single wipe breaks the interaction. **Chosen fix: wipe
`Default/History` + `Default/History-journal`** (the browsing-history DB is
unused by the app; `shared_proto_db` holds network-service state — less
invasive to leave). Implemented as
`apps/billcollector/runner.py::_clear_stale_history` (renamed from the
original `_wipe_download_crash_state` on 2026-10-10 per code-refinement
request: neutral name, no .kilo plan references in productive source),
called from `_launch_browser` after `_ensure_pdf_preference`; no-op for
fresh profiles, logs removed names via `logger.info`
("Cleared stale browsing history before launch: …"). Deviation from the
literal "group interaction → launch arg" rule: M3 (headless) is the only
passing mitigation but regresses the headed display contract (WSL2
cold-frame fix, 9e8dc5c); the surgical wipe is the plan's own Phase 2
candidate and now decisively validated. Cookies/login/Preferences
untouched.

### Phase 5 — re-validation (2026-10-10, session 2) — ALL GREEN

`/tmp/bc-runner-e2e-attempt4/` (scratch `BC_DB_FILE`/`BC_DATA_DIR`/
`BC_PROFILE_ROOT`/`BC_DOWNLOAD_DIR`), WSLg `:0`, mock portal + real vault
(unlocked):
- RUN 1 (fresh): exit 0, `Run.result=success`, 19 PageStatus rows, 0 errors,
  DL id=1 `invoice_happy_user1_1.pdf` sha=`adc8aee79214090f…`, DL id=2
  `contract_info_happy_user1.pdf` sha=`c6ad8605e8f18adc…`.
- RUN 2 (warm, History present pre-launch): exit 0,
  `Run.result=success`, log line `Removed warm-profile crash-trigger state
  before launch: History, History-journal`, DL id=3/4 with `dup_of=1/2`
  (cross-run sha256 dedup), exactly one PageStatus error on step 2 (graceful
  consent, banner absent), all screenshots present.
- Unit suite: `PYTHONPATH=apps apps/.venv/bin/python -m unittest discover
  -s tests` → **48 tests, OK**.
- (Benign pre-existing: step-17 screenshot warning after run end also
  appears in the attempt3 baseline run 1.)

### Phase 6 — record findings (2026-10-10, session 2)

- "Known blocker" paragraph in
  `.kilo/plans/1790364274061-billcollector-nicegui-daemon-plan.md` rewritten
  as "RESOLVED" with trigger, stack excerpt, fix, re-validation result, and
  the full repro recipe (venv + mock-portal + probe commands).
- Docker/NAS note added (C6 Xvfb path uses the same persistent-profile code).
- Plan status: **DONE** (diagnose + fix + re-validate). The original
  optional follow-up (file an upstream bug report) is superseded — the
  crash is already reported and fixed upstream; see "Second opinion
  cross-check" below.

### Second opinion cross-check (2026-10-10, finalization)

An external second opinion on the crash (dual-file trigger
`Default/History` + `Default/shared_proto_db`; fix = purge History) was
checked against our evidence and upstream sources.

- **Confirmed as a known upstream bug**: Chromium issue **556160935** —
  "[M152 regression] Browser crashes after setDownloadBehavior during
  persistent-profile startup" (filed 2026-09-02, Chrome 152.0.7977.75,
  macOS; repro gist `ayazhafiz/cae9e0adb6…`). Upstream repro = CDP
  (`Browser.setDownloadBehavior`, `eventsEnabled`) + persistent profile
  seeded with a prior download → browser process dies (SIGTRAP or SIGSEGV,
  "depending on the run", racy across attempts) on the next download.
  Matches our situation exactly: Playwright attaches CDP, our warm
  per-task profile carries run-1 download history, and our evidence
  (pre-restart: SIGTRAP CHECK then SIGSEGV NULL deref; Phase 1 re-capture:
  SEGV_MAPERR 0x90) is the same crash-class pair the issue describes.
- **Upstream root cause (fix CL 8378127, targeted M154)**:
  `DevToolsDownloadManagerDelegate` wraps the normal download delegate but
  does not forward `SupportsHistoryLoading()`, so with DevTools attached
  the download-history path misbehaves on a profile that already has
  download history. The reporter's interim workaround was "surgery on
  `shared_proto_db`" — consistent with our X/W wipe tests.
- **Second opinion vs our bisection — every testable claim agrees**:
  dual-file trigger (ours: minimal deterministic pair; neither file alone,
  U1/U2; journal not required, V1), History-purge fix (ours: W/W2; we
  additionally proved the shared_proto_db wipe also works, X),
  cookies/login/Preferences untouched (contract + E2E run 2). The
  opinion's "0xC0000005 in msedge.dll" phrasing is the Windows variant of
  our Linux SEGV_MAPERR — same crash class, different platform.
- **Differences, none of which change the fix**:
  - Its mechanism wording ("cross-reference and write metadata across
    History and shared_proto_db") is a plausible paraphrase; the precise
    upstream cause is the DevTools download delegate's history-loading
    path, which is why the crash only occurs under CDP/automation.
  - Its alternative "truncate the SQLite `downloads` table" is inferior to
    whole-file removal: it adds a sqlite3 dependency to the runner, leaves
    a stale DB Chromium still opens, and is no safer (the upstream trigger
    is the presence of download history, not the row count). Keep the
    current unlink approach.
  - Its "file coexistence pre-check" before launch is unnecessary: our
    wipe is already a no-op when the files are absent.
  - Untested by both sides: whether an *empty* History file triggers the
    crash (our warm profile and the upstream repro both carry real
    download rows). Irrelevant to the fix (we delete the file entirely);
    no re-probe warranted.
  - Upstream calls the crash racy (their repro loops up to 10 attempts);
    ours reproduced deterministically on WSLg `:0` + chromium-1243 headed.
    Fix unaffected.
- **Verdict: no logic change to `_clear_stale_history`** (apps/billcollector/
  runner.py:169). One small source update recommended (Phase 7): cite the
  upstream bug and its fix in the docstring.
- Side observation (cleanup only, not source): a stray
  `apps/browser/profile/` (singular; default root is `apps/browser/profiles`,
  currently empty) from an earlier run exists — gitignored via `browser/`;
  safe to delete locally.

### Phase 7 — finalization (pending implementation)

1. Update the docstring of `_clear_stale_history`
   (apps/billcollector/runner.py:169) to cite the upstream bug and state
   the removal condition. Target text (neutral, no plan references):

   ```python
   """Clear the previous run's browsing-history state before launch.

   Workaround for Chromium issue 556160935 ([M152 regression] browser
   process crash after setDownloadBehavior with a persistent profile that
   has download history): with DevTools/CDP attached, a persistent profile
   carrying both ``Default/History`` and the network service's
   ``Default/shared_proto_db`` crashes (SEGV/SIGTRAP) when the first
   download starts. Upstream fix CL 8378127 (DevToolsDownloadManagerDelegate
   forwards SupportsHistoryLoading) targets M154 - this wipe can be removed
   once the pinned Playwright chromium build is >= 154. Clearing the history
   side of that pair avoids it; the history data is not needed by the
   collector. Cookies, login and Preferences are untouched. No-op for fresh
   profiles."""
   ```

2. In the daemon plan's RESOLVED note
   (`.kilo/plans/1790364274061-billcollector-nicegui-daemon-plan.md`):
   add the upstream bug link (issues.chromium.org/issues/556160935) next to
   the fix description. Optional: comment our Linux/Playwright datapoint
   (chromium-1243, WSLg, deterministic) on the issue.
3. Commit the working-tree changes (runner.py, tests/__init__.py, both plan
   files) via the dev-commits skill flow (user-gated).
