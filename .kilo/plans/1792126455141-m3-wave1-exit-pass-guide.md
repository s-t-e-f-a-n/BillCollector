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

## Step 2 — Login + imported tasks + mock-portal tasks (plan step 1)

Open `http://127.0.0.1:18766/` → 307 to `/login` → **set-password** form
(two fields, min 8 chars) → 307 to `/`.

Check on the dashboard:

- one row per imported task (11 on the current dev tree), status `idle`,
  enabled off, next run `—` (no scheduler jobs while disabled);
- `[0 waiting]` badge; log pane empty.

Toolbar **Add task** four times (fields: service, user, cron defaulting
to `0 0 1 * *`, enabled switch; the recipe filename is derived from the
service and shown read-only):

| service           | user      | cron        | enabled |
| ----------------- | --------- | ----------- | ------- |
| `testhappy`       | `user1`  | `0 0 1 * *` | on      |
| `testautopause`   | `user1`  | `0 0 1 * *` | on      |
| `testwaituser`    | `user1`  | `0 0 1 * *` | on      |
| `testcaptchadrag` | `user1`  | `0 0 1 * *` | on      |

Check: the four rows appear, each with the derived `recipe-pw__…yaml`
(the files exist, so no missing-recipe warning) and a real next-run
timestamp from the live APScheduler job (not `—`). Duplicate
`(service, user)` is rejected with a notify (optional check).

## Step 3 — ntfy deep link (plan step 2)

`/settings`: set `ui_base_url` to `http://127.0.0.1:18766` → Save →
notify; reload → the value persists (round-trip). Without it, the deep
link in the ntfy push is a relative path (`/runs/<id>`), not a full URL a
phone can open.

Note: pause pushes go to `$NTFY_HOST` (default `https://ntfy.sh`) on the
`ntfy_topic` setting (default `billcollector`), best-effort — a missed
push never blocks the run. Subscribe to the topic to receive the push (an
ntfy app on the phone, or the browser tab `https://ntfy.sh/billcollector`);
a private server goes via `NTFY_HOST` in the daemon env (daemon restart).

Row **Run now** on `testautopause` (this is the pass's first run — the
Xvfb failure mode from the prerequisites can land here):

- status flips to `running`; terminal 2 logs the display allocation
  (`:99`) and Xvfb/x11vnc/websockify come up (check with `ps`);
- step 11 fails 3× → the task flips to **`waiting`**: dashboard
  `[1 waiting]` badge + highlighted row; the **detail pause card** shows
  the "Paused" heading with the **Open session** link (→
  `/runs/<run_id>`), the reason (`step_failed`), the prompt (`Step 11:
  Click the Verified button (appears only after the operator clicks 'I am
  not a robot'). - failed after 3 attempts. Fix the page (or repair the
  recipe), then resume.`), the deadline countdown (30:00), and the
  **pause screenshot** (read-only in this card);
- terminal 2 logs `Run <id> paused (step_failed): …`; the `<run_id>` is
  the `<id>` in that line (the task detail's run expansion label
  `Run <id> …` shows it too).

**Deep-link check:** the ntfy push arrives on the subscribed topic —
message = the pause prompt, then the deep link
`http://127.0.0.1:18766/runs/<run_id>`. Open that link in a **second
browser/incognito window**: it lands directly on the session page
`/runs/<run_id>` — the pause banner (reason, prompt, deadline countdown),
the live screenshot with the numbered overlay, the element select, the
action bar, **Resume**/**Cancel**, and the noVNC tab — not the dashboard
(the M2 redirect is gone). That is the "the operator acts from a phone"
proof.

Leave the pause open — step 4 resolves it through Copilot.

If the run fails with `Xvfb :99 did not create /tmp/.X11-unix/X99 within
10s` (a Windows/WSL2 restart happened since the step 1 remount): re-run
`sudo mount -o remount,rw /tmp/.X11-unix && sudo chmod 1777 /tmp/.X11-unix`
(remounting rw is the essential part; the chmod only matters on WSL
builds that mount the dir at 775), then Run now again.

## Step 4 — Acceptance 1: resolve the `testautopause` pause via Copilot (plan step 3)

Still on the session page from step 3 (the deep link in the second
browser/incognito window): the pause is open, the state badge is
`waiting`. The **Copilot** tab is active by default; it carries the
live screenshot (the "Security check" page) with the numbered overlay,
the element select, the action bar, and **Resume**/**Cancel**. The
**noVNC** tab is available but not needed here — this is the case where
Copilot can express the intervention.

1. **Element select** (`n · role · name`, the number is the badge on
   the screenshot): pick `1 · button · I am not a robot` — or tap its
   numbered badge on the screenshot (the badge tap selects the element
   into the action bar, mobile-first). For a button the action bar
   enables **Click**.
2. **Click** → notify `Click 1 sent` → the immediate post-action
   refresh re-fetches the screenshot and elements: the button was
   **replaced in place** by "Verified" (the page's JS swaps it), so
   the fresh screenshot shows "Verified" and the element select now
   offers `1 · button · Verified`.
3. **Do not click "Verified" itself**: its `onclick` navigates to the
   portal dashboard, and the re-executed step 11
   (`get_by_role button "Verified" → click`) would no longer find the
   button — the pause would recur. Leave the page as-is.
4. **Resume** (primary button) → notify `Resume sent; the run
   continues` → within the ~2 s poll the state badge flips to
   `running`: the read-only running view (the step strip fills in live;
   the noVNC tab stays available for observation). Step 11 re-executes
   and clicks "Verified" — the page navigates to the portal dashboard —
   then steps 12–14 (account, invoices, download) and step 15 (close).

Check:

- the session page flips to the **ended** view: `Finished: success`
  with the started/ended timestamps, plus the **Last pause
  (read-only)** card (the pause columns survive the resume): reason
  `step_failed`, the prompt, the pause screenshot, and the elements at
  pause time (`1 · button · I am not a robot`); no noVNC tab (the
  display stack is reaped with the run);
- dashboard: the `testautopause` row is `idle` again, `[0 waiting]`;
  task detail: the run's history row is `success`, the step table
  carries the step-11 failure row plus the clean re-execution row
  (one row per step, its final outcome), and the run's **download**
  `invoice_autopause_user1_1.pdf` is tracked (sha256 + size) in the
  run's download section and on the downloads page.

## Step 5 — Acceptance 2: the `testwaituser` wait_user pause (plan step 4)

Dashboard: row **Run now** on `testwaituser`. The run performs the
login and OTP steps (1–10) on its own; step 11 is a `wait_user` step,
and the runner pauses **before** executing it (the step is consumed on
resume, not re-executed — the operator's work happens during the
pause):

- the task flips to **`waiting`** (the second pause of the pass); the
  ntfy push arrives on the topic with the deep link — open it (or
  navigate to `/runs/<run_id>`): the session page lands on the waiting
  view;
- the pause banner: reason `wait_user`, prompt `Type the 6-digit code
  shown on the page, then press Verify`, the deadline countdown
  (30:00);
- the Copilot screenshot shows the "Security check" page **with the
  6-digit code displayed on it** (plus the "verification code" textbox
  and the "Verify" button). The code is readable in the screenshot (the
  pause context's `page_text` carries it too, for a machine client).

Resolve it from Copilot — this is the human-reads-the-CAPTCHA case the
recipe cannot express:

1. Read the 6-digit code from the session screenshot.
2. Select the textbox in the element select
   (`1 · textbox · verification code` — or tap its badge). A textbox
   enables **Click** and **Fill** in the action bar. Type the code
   into the fill text input, then **Fill** → notify `Fill 1 sent` →
   the refresh shows the code in the textbox.
3. Select the "Verify" button (`2 · button · Verify`) → **Click** →
   notify `Click 2 sent` → the form POSTs and the page navigates to
   the portal dashboard.
4. **Resume** → the `wait_user` step is **consumed, not re-executed**
   (no `until` — it completes immediately on resume); steps 12–15
   follow → `success`.

Check:

- the ended view: `Finished: success` + the **Last pause (read-only)**
  card (reason `wait_user`, the prompt, the screenshot **with the code
  visible**, the elements `1 · textbox · verification code` and
  `2 · button · Verify`);
- the run's **download** `invoice_waituser_user1_1.pdf` is tracked;
  the dashboard row is `idle` again.

Failure mode: a mistyped code → the form re-renders with "Invalid code"
(the page stays put) — correct the code (select the textbox, **Fill**
again) and click Verify again, **before** the Resume.
