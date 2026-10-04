# Fast-Track: Minimal NiceGUI UI for Manual Start/Stop of Scraping (per-service)

> Status: DELIVERED in v0.3 — retained for the record.

Fast-track carve-out from the bidirectional plan
`.kilo/plans/1790364274061-billcollector-nicegui-daemon-plan.md` (M0 done, M1/M2 not
started). Goal: **see a working NiceGUI page as quickly as possible** where the operator
manually **starts** and **stops** one service's scraping run and watches it live —
without the full M1 daemon (no scheduler, no new DB, no Copilot, no noVNC).

Resolved decisions (interview 2026-09-26):
- **Start granularity: per-service from day one** (UI dropdown + `--service` flag on the
  existing entry point). Per-(service, user) explicitly NOT included.
- **First validation: a real run of one small (single-user) service** — no mock portal
  exists yet (M1 deliverable); the first manual start hits a real portal with real
  Vaultwarden credentials.
- UI process is a pure subprocess supervisor; the scraping code stays sync and untouched
  (except the additive `--service` flag).

## Gathered facts (verified 2026-09-26)

- Ubuntu 24.04.5 (WSL2), `apps/.venv` Python 3.12, **nicegui==3.17.1** and
  **playwright==1.63.0** installed; `chromium-1243` + `ffmpeg-1011` in `apps/browser/`.
- `setup_logging()` (M0) writes to `bc.log` **and stdout** — stdout is the stream the
  UI tails. `BillCollector.py` forces unbuffered stdout (`sys.stdout = sys.__stdout__`)
  and loads `.env` itself → the UI process needs no scraping knowledge.
- Entry: `python3 BillCollector.py <ini> [debug]` → `WebRetriDoc(bc, "playwright")` →
  Vaultwarden check (fail = `sys.exit(1)`, exit code 1) → sequential loop over all
  `(service, user)` pairs of the ini. No per-service filter exists.
- `BillCollector.sh` (cron) invokes `python3 ./BillCollector.py $1 $2` — two positionals,
  so the new filter must be an **optional `--service` flag**, positionally compatible.
- `bc_default.ini` and `bc_test.ini` are currently identical: winSIM = 5 users, plus
  7 single-run services (KabelDeutschland, DATEV, Buhl, Nuernberger, 1und1, Freenet
  Mobilfunk).
- Playwright `headless = not debug` → a UI-launched run (no `debug` arg) is headless.
- Dev host has no local crontab (production cron runs on the remote NAS) → no local
  duplicate-run contention for this fast track.

## Changes

### 1. `apps/BillCollector.py` — additive `--service` flag (backward compatible)

- In `if __name__ == "__main__":`, before the existing argv handling: pull
  `--service <NAME>` out of `sys.argv[1:]` (error + exit 1 if the flag has no value);
  keep the remaining argv handling exactly as is (ini positional + optional `debug`
  positional).
- `WebRetriDoc(self, type=None, service=None)`: in the service loop, skip services where
  `service` is set and `servicename.lower() != service.lower()`.
- If a filter was set but matched no service in the ini: `logger.warning(...)` before
  exiting (so a typo is visible in the UI log instead of a silent no-op).
- `BillCollector.sh`, docker, and the cron invocation are unchanged.

### 2. `apps/bc_ui.py` — new standalone file (the whole UI)

Single-page NiceGUI app, ~150 lines, no package (M1's `billcollector/ui/` absorbs it):

- **Page layout** (`@ui.page("/")`):
  - ini selector: `bc_test.ini` (default — existing debug convention), `bc_default.ini`,
    free path entry; changing it refreshes the service list (parsed from the
    `[Playwright]` section via `configparser`).
  - service selector (dropdown, required).
  - status chip: `idle / running / finished (exit N) / stopped / error`.
  - Start button (disabled while running) · Stop button (enabled only while running).
  - elapsed-time label via `ui.timer` (1 s).
  - `ui.log` streaming the run's stdout, one line per push, capped (drop oldest beyond
    ~2000 lines).
- **Start** (async handler): guard on status; spawn
  `asyncio.create_subprocess_exec(sys.executable, "BillCollector.py", <ini>,
  "--service", <service>, cwd=<apps dir>, stdout=PIPE, stderr=STDOUT,
  start_new_session=True)`; write `{"pgid", "ini", "service", "started"}` to
  `apps/.bc_ui_run.json`; consume stdout line-by-line into the `ui.log`; on exit:
  delete the state file, set status from the exit code (0 = `finished`, else
  `finished (exit N)`).
- **Stop** (async handler): `os.killpg(pgid, SIGTERM)` → `await proc.wait()` with a 10 s
  timeout → `SIGKILL` if still alive. Process-group kill takes down the Chromium
  children with the Python process. Guard `ProcessLookupError` (run already finishing).
- **Orphan protection:** on app startup (`on_startup`), if `.bc_ui_run.json` exists and
  its pgid is alive (`os.kill(pgid, 0)`): kill the group, log "cleaned up orphaned run"
  into the page log; otherwise delete the stale file.
- **Run:** `ui.run(port=8000, host="0.0.0.0", title="BillCollector", show=False)`.
  No auth (single-operator dev machine; auth is M2). `0.0.0.0` so the Windows host
  browser reaches it via WSL2 port forwarding at `http://localhost:8000`.

## Failure modes / edge cases

- Vault locked or unreachable → batch exits 1 after the vault check → UI shows
  `finished (exit 1)` with the error lines in the log. Expected, visible.
- Stop mid-`expect_download` → at most one partial file in `apps/Downloads/` (the
  `save_as` window); partial `Service` DB row (`timestamp_end` NULL) remains — same
  artifact as today's killed batch; acceptable.
- `--service` unknown name → warning line + clean exit, no silent no-op.
- UI restarted mid-run → orphan cleanup on startup (see above).
- Two UI instances / double Start → Start guard + single-run status; the remote-NAS cron
  is a different machine, no local flock needed for this fast track.
- winSIM start = 5 sequential user runs; Stop kills the current one, remaining users of
  that service are skipped (they never start).

## Validation

1. CLI backward compat (no real run): `.venv/bin/python BillCollector.py` → usage
   message; `.venv/bin/python BillCollector.py bc_test.ini --service NOPE` → warning
   line, exit 0.
2. UI starts: `.venv/bin/python bc_ui.py`; open `http://localhost:8000` in the Windows
   browser (WSL2 forwarding); page renders, dropdowns populated from the selected ini.
3. **Real first run (the point):** select `bc_test.ini` + one small single-user service
   (DATEV or Buhl) → Start → watch live log: vault check → login → steps → download /
   "no file downloaded" → status `finished (exit 0)`; new file in `apps/Downloads/`
   (if the portal had a document).
4. Stop semantics: Start winSIM → after the first user's login is visible in the log,
   Stop → status `stopped`, no `chromium` process left (`ps`), UI immediately usable
   again.
5. Orphan path: Start winSIM, `kill -9` the UI process, restart `bc_ui.py` → the
   orphaned run is killed on startup, cleanup line in the log.

## Risks

- Real-portal side effects on first runs (real logins, real invoices in
  `apps/Downloads/`) — inherent; chosen deliberately.
- No auth on a 0.0.0.0 port — dev machine only; do not expose beyond the LAN; auth is
  M2.
- `ui.log` memory on very long runs → line cap (above).
- Playwright 1.48 → 1.63 drift on the real portals: the first real run doubles as the
  drift check (M0 step 0.5's F5/cron equivalent).

## Out of scope (stays in the bidirectional plan)

APScheduler/scheduler, redesigned Task/Run DB, runner refactor, control socket,
Copilot, noVNC, recipe editor, auth, mock portal, Docker changes, per-(service, user)
granularity.
