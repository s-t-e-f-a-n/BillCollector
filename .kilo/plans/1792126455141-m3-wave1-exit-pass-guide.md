# M3 Wave 1 exit pass — step-by-step operator guide

Recorded manual pass, the M2 D6.4 guide's pattern: the committed suite stays
fast and display-independent; this pass is the real-browser proof. It covers
the six Wave 1 acceptance scenarios (M3 plan S3) driven **from the web UI**
(the session page's Copilot + noVNC is the client — no driver script needed,
the control socket is documented as the fallback in Appendix A). The M3 plan
is `.kilo/plans/1791998985158-m3-interactive-sessions-plan.md`; the M2 exit
pass guide it mirrors is
`.kilo/plans/1791829791901-m2-d64-exit-pass-guide.md`.

## Review log

Cross-session tracker for the manual pass: every observation lands here with a
status; an entry moves to `resolved` only once the fix is in and the next pass
re-verifies it. Newest pass last.

(No passes recorded yet — the guide is being written in S3.1–S3.5; the live
pass is recorded here as it runs.)

## Prerequisites

- Dev host with the full Xvfb/x11vnc/websockify/novnc stack (the runner
  starts the per-run stack itself; nothing to pre-start).
- LAN Vaultwarden with the Layer B items for `testhappy`, `testautopause`,
  `testwaituser`, `testcaptchadrag` (all `user1`), reachable as configured in
  `apps/.env` (`BW_API_URL`, `BW_API_HOST`).
- Repo on `dev`, working tree clean — **step 8 lands a real git commit on
  this branch** (see the warning there).
- `apps/.venv` with the runtime dependencies installed.
- Ports free: 8787 (mock portal), 18766 (scratch UI), 6080+ (websockify),
  5900+ (x11vnc), X display :99.
- After a Windows/WSL2 restart, WSLg mounts `/tmp/.X11-unix` as a
  read-only tmpfs (a bind of `/mnt/wslg/.X11-unix`), so the non-root
  per-run Xvfb cannot bind its `X99` socket there and a bare `chmod` fails
  with "Read-only file system" — step 1 carries the remount one-liner,
  step 3 (the first `Run now`) carries the failure mode.
- Scratch root: `/tmp/bc-d64` (any path works; adjust the paths in the
  snippets).
- No driver script is needed for the primary path (the Copilot UI is the
  client). The control-socket fallback (Appendix A, the M1 client) is
  documented for a session page that misbehaves.

## Step 0 — Start the mock portal (terminal 1)

```bash
cd /home/stefan/projects/BillCollector
apps/.venv/bin/python -m tests.mock_portal        # default port 8787
```

Check: `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8787/health`
→ `200`. Leave this terminal running.

The mock portal serves the changed-website drill in step 8:
`POST /admin/happy/mutate` (JSON body, e.g. `{"login_button": "Sign in"}`)
sets in-memory overrides, `POST /admin/happy/reset` clears them. Both are
fresh per portal start.

## Step 1 — Scratch env + daemon (terminal 2)

```bash
rm -rf /tmp/bc-d64 && mkdir -p /tmp/bc-d64
export BC_DATA_DIR=/tmp/bc-d64/data
export BC_DB_DIR=/tmp/bc-d64/db
export BC_DB_FILE=/tmp/bc-d64/db/bc.db
export BC_LOG_DIR=/tmp/bc-d64/logs
export BC_DOWNLOAD_DIR=/tmp/bc-d64/downloads
export BC_BROWSER_DIR=/tmp/bc-d64/browser
# WSLg mounts /tmp/.X11-unix read-only on every Windows/WSL2 restart (a
# bind of /mnt/wslg/.X11-unix); the non-root per-run Xvfb cannot bind its
# X99 socket there, and a bare `chmod` fails with "Read-only file system".
# Remount it rw (the WSL-maintainer-recommended fix for a secondary X
# server); on WSL builds that mount the dir at 775 instead of 1777, follow
# with the chmod (a no-op when it is already 1777).
sudo mount -o remount,rw /tmp/.X11-unix
sudo chmod 1777 /tmp/.X11-unix
# Playwright resolves the browser build from BC_BROWSER_DIR (config.py);
# the fresh scratch dir has none - hardlink the repo build in (same
# filesystem, no disk cost; the revision dir must match the installed
# Playwright, `ls apps/browser` shows it).
mkdir -p /tmp/bc-d64/browser
cp -al /home/stefan/projects/BillCollector/apps/browser/chromium-1243 \
    /tmp/bc-d64/browser/
cd /home/stefan/projects/BillCollector/apps
.venv/bin/python -m billcollector serve --port 18766
```

Expected at startup: the ini import creates the tasks from
`bc_default.ini` + `bc_test.ini` (on the current dev tree: **11** —
`winSIM` × Stefan, Auto, Brigitte, Eva, Anna plus 6 other services
[kabeldeutschland, datev, buhl, nuernberger, 1und1, freenet mobilfunk]),
all **disabled** with the default monthly cron. Do **not** set
`BC_UI_PASSWORD` — step 2 exercises the set-password form.
