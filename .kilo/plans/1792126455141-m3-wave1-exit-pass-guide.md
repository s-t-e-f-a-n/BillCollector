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
phone can open. Also flip **Git auto-commit** on → Save → notify
`git_commit_enabled saved`; reload → the switch stays on (round-trip).
Step 8's repair Save lands the `recipe(testhappy): …` commit only when it
is on (the default is off).

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

## Step 6 — Acceptance 3: the `testcaptchadrag` drag CAPTCHA via noVNC (plan step 5)

Dashboard: row **Run now** on `testcaptchadrag`. The run performs steps 1–10
on its own (landing, the consent banner [graceful], the login, the OTP,
"Check and log in" — after which the mock redirects to
`/captchadrag/drag`), then pauses **before** step 11: step 11 is a
`wait_user` step and the runner pauses before executing it (the operator's
work happens during the pause):

- the task flips to **`waiting`** (the third pause of the pass); the ntfy
  push with the deep link arrives on the topic — open it (or navigate to
  `/runs/<run_id>`): the session page lands on the waiting view;
- the pause banner: reason `wait_user`, prompt `Drag the slider all the way
  to the right`, the deadline countdown (30:00);
- the **Copilot** tab (active by default) shows the "Security check" page
  with the slider (the 300 px track, the blue knob at the left edge) — and
  in place of the element select, the **noVNC hint**: "No interactive
  elements were detected on this page. Use the noVNC view to operate the
  page directly." The knob (`<div id="knob">`, pointer-event JS) is not a
  scannable interactive element, so the element list is **empty** (the
  expected state — the protocol stays v1, the drag goes through noVNC). The
  action bar is disabled.

Resolve it through noVNC — this is the case Copilot cannot express:

1. Switch to the **noVNC** tab: the noVNC iframe (the run's websockify
   port) shows the live Xvfb screen — the same "Security check" page.
2. Drag the slider knob all the way to the right (press the knob, drag to
   the right edge of the track). At the far right the page shows
   **"Verified"** and navigates to the portal dashboard.
3. Back to the **Copilot** tab, **Resume** → the `wait_user` step is
   **consumed, not re-executed** (no `until` — it completes immediately on
   resume); steps 12–15 (account, invoices, download, close) follow →
   `success`.

Check:

- the ended view: `Finished: success` + the **Last pause (read-only)** card
  (reason `wait_user`, the prompt, the screenshot showing the slider page;
  no "Elements at pause time" lines — the list at pause time was empty);
- the run's **download** `invoice_captchadrag_user1_1.pdf` is tracked
  (sha256 + size) in the run's download section and on the downloads page;
- dashboard: the `testcaptchadrag` row is `idle` again, `[0 waiting]`.

Failure mode: a partial drag (the knob released short of the right edge)
leaves the page in place without "Verified" — drag again from the noVNC tab,
then Resume. If the pause deadline (30:00) lapses instead, the run ends
`needs_attention`.

## Step 7 — Acceptances 4+5: the `testhappy` persistent profile + download dedup (plan steps 6+7)

Two runs of the same task prove both: the per-task profile persists across
runs (the consent cookie survives; the session cookie does not), and the
byte-stable mock downloads dedup by sha256.

**Run 1** — dashboard row **Run now** on `testhappy` (the task has not run
yet in the pass, so its profile is fresh):

- the run performs the full happy path: the consent **banner shows** on the
  landing (fresh profile) → the graceful step 2 clicks "Reject" (a clean
  row) → the login (steps 3–10; the mock sets the session cookie) → the
  popup close (11) → account/invoices (12–13) → the downloads (15
  `invoice_happy_user1_1.pdf`, 16 `contract_info_happy_user1.pdf`) → close
  (17);
- the run ends **`success`**; the browser closes at step 17 — the
  session-scoped cookie is gone, the one-year consent cookie persists in
  the task's profile directory
  (`/tmp/bc-d64/browser/profiles/testhappy_user1/`).

**Run 2** — row **Run now** again on the same task:

- the consent **banner is absent** (the consent cookie was read from the
  profile) → the graceful step 2 finds no "Reject" button and is recorded
  as a **graceful-error row** (the run continues, no pause);
- the **login re-runs** (the session cookie did not persist — the mock
  demands a login on every run): steps 3–10 execute cleanly again (had the
  session cookie survived, step 1 would land on the dashboard and step 3
  would pause with `step_failed`);
- the downloads: the same byte-stable PDFs → the same sha256 as run 1 →
  run 2's two Download rows are recorded as **duplicates** of run 1's rows
  (`duplicate_of_id` → run 1's row ids); the consumer hook is not re-run
  for them;
- the run ends **`success`**.

Check:

- task detail `testhappy` → Run history: both runs `success`; expanding run
  2 shows the graceful-error row on step 2 (the banner absent) and clean
  rows on the login steps (the login re-ran);
- the task detail's **Downloads** section (and the `/downloads` page,
  filtered to the task): run 1's two rows carry no duplicate badge (`—` in
  the Duplicate column); run 2's two rows carry the orange outlined
  **`duplicate of #N`** badge (N = run 1's Download row id), with the same
  filename and the same truncated sha256 (first 12 chars).
- (Optional, falsifiability:) task detail → **Reset profile** → confirm →
   the profile directory is deleted and the next run cold-starts **with the
   consent banner back** (the same loop the M2 pass's step 9 exercised).

## Step 8 — Acceptance 6: changed website + recipe repair (plan step 6)

The DOM-change friction point, resolved through the recipe-repair flow (the
primary no-YAML path: the candidate picker, preloaded from the paused run's
failure context). The mutation lives in the mock portal's memory only (fresh
per portal start), so the drill is: mutate → run → repair → cancel the
stale run → re-run → reset.

1. **Mutate** the landing page (terminal 3, or a curl from any terminal):

```bash
curl -s -X POST http://127.0.0.1:8787/admin/happy/mutate \
  -H 'Content-Type: application/json' \
  -d '{"login_button": "Sign in"}'
```

→ `{"ok": true, "overrides": {"login_button": "Sign in"}}`. The landing
submit button now reads "Sign in"; the recipe's step 8 ("Submit the login
form.") still expects `get_by_role button "Log in"`.

2. Dashboard: row **Run now** on `testhappy`. Steps 1–7 execute (landing,
consent banner, the form fields); step 8 fails 3× — the `Log in` button no
longer exists — and the task flips to **`waiting`** (the fourth pause of
the pass). The ntfy push with the deep link arrives on the topic; terminal
2 logs `Run <id> paused (step_failed): …`.

3. Open the session page (the deep link, or `/runs/<run_id>`): the pause
banner shows reason `step_failed`, the prompt (`Step 8: Submit the login
form. - failed after 3 attempts. Fix the page (or repair the recipe), then
resume.`), the deadline countdown — and, because this is a `step_failed`
pause, the **Repair recipe** link (the primary path; the Copilot tab is
available, but the fix is the recipe's locator, not a page state).

4. **Repair recipe** → `/recipes/testhappy?run=<run_id>`: the editor loads
`recipe-pw__testhappy.yaml` with a red **failure panel** above it (title
`Failure (run N)`):

- the failure screenshot (the landing page with the **Sign in** button) via
  its `/runfiles` URL;
- the step label: `Step 8: Submit the login form.`;
- the expected locator (mono): `get_by_role(role=button, name=Log in)`;
- the error (the step-8 locator timeout);
- the candidate rows for the pause page — one per interactive element
  (`n · role · name (locatorType)`), each with a **Use** button — including
  the `n · button · Sign in (get_by_role)` row.

5. **Use** on the Sign in row → the editor reloads with the rewritten YAML:
step 8's locator prefix is replaced with the candidate's locator
(`get_by_role` with `role: "button"`, `name: "Sign in"`, `exact: true`) and
the `click` action is kept; the result label says what was replaced. (The
advanced path: fine-tune the YAML by hand.)

6. **Validate** → OK; **Save** → notify saved. Check the repo (repo root):

```bash
git log --oneline -1     # recipe(testhappy): edited via UI
git show --stat HEAD     # only apps/recipes_playwright/recipe-pw__testhappy.yaml
```

**Warning** (the M2 step-8 pattern): the recipe directory is fixed to
`apps/recipes_playwright` and the commit targets the repo root, so this
lands on the **real `dev` branch** (no scratch redirect). Unlike M2's
description-only change, this locator repair is only valid while the
mutation is active — after the reset in 8.9, the portal's button is back to
"Log in" and the repaired recipe would fail. Revert it with a new commit
after the pass (no amends) — the keep/revert decision is step 10.

7. Back on the session page: **Cancel** → the confirmation dialog ("Cancel
the run? … the run ends as cancelled.") → **Cancel run** → notify `Cancel
sent; the run ends` → the run ends **`cancelled`**, the task flips to
`idle` (the display stack is reaped). The session page flips to the ended
view: `Finished: cancelled` + the **Last pause (read-only)** card — the
pause columns survive the cancel, so the **Repair recipe** link is still
offered on it.

(While the run is `waiting`, the dashboard's **Run now** refuses —
`testhappy: not started (already running/waiting?)` — the claim inside
`start_run` is the double-start guard; the cancel is what frees the task
for the re-run.)

8. **Run now** again (the dashboard row, or the per-task button the recipe
editor offers after the save) → the run with the repaired recipe: step 8
finds the **Sign in** button → the login (steps 9–10, the OTP) → the
dashboard → the downloads (steps 15–16) → close (17) → **`success`**. The
two downloads are byte-stable → the same sha256 as step 7's run 1 →
recorded as **duplicates** of run 1's rows (dedup key = task + sha256; the
consumer hook is not re-run for them).

9. **Reset** the portal:

```bash
curl -s -X POST http://127.0.0.1:8787/admin/happy/reset
```

→ `{"ok": true}` (the overrides are cleared; the landing button is back to
"Log in").

## Step 9 — Running view + ended view + noVNC observation

Verified as observed during steps 4–8 (the S1.3 views, not new scenarios):

- **running** (e.g. during the login/OTP steps of any `testhappy` run, or
  right after a **Resume** while the run continues): the session page is
  read-only — the step strip fills in live with the run's step screenshots
  (one `PageStatus` row per step, its final outcome; thumbnail click → the
  full image in a dialog), the **noVNC** tab shows the live Xvfb screen
  (the operator observes without intervening), the **Steps** tab is active
  by default, no action bar;
- **ended** (steps 4–6 and 8): `Finished: <result>` with the
  started/ended timestamps + the **Last pause (read-only)** card for the
  paused runs (reason, prompt, the pause screenshot, the elements at pause
  time as `n · role · name` lines — the drag pause of step 6 shows none,
  its list was empty) and, for the `step_failed` runs, the **Repair
  recipe** link (it survives the resume/cancel); no noVNC tab (the display
  stack is reaped with the run).

Record any deviation from this in the review log.

## Step 10 — Final DB checks + record

```bash
sqlite3 /tmp/bc-d64/db/bc.db <<'SQL'
SELECT id, task_id, result, display, novnc_port FROM Run ORDER BY id;
SELECT id, filename, size, sha256, duplicate_of_id FROM Download ORDER BY id;
SELECT key, value FROM Settings;
SELECT id, service, user, status, enabled, profile_reset_at FROM Task;
SQL
```

Expect (7 runs, 9 downloads):

- no run left `running`/`waiting`: 6× `success` + 1× `cancelled` (step
  8's pre-repair run); all tasks `idle`;
- downloads: one per paused task (`invoice_autopause_user1_1.pdf`,
  `invoice_waituser_user1_1.pdf`, `invoice_captchadrag_user1_1.pdf`) +
  6× `testhappy` (step 7 run 1's two clean, step 7 run 2's and the
  post-repair run's four with `duplicate_of_id` → run 1's rows);
- Settings: `ui_base_url = http://127.0.0.1:18766`,
  `git_commit_enabled = true`;
- `profile_reset_at` set for `testhappy`/`user1` only if step 7's optional
  Reset profile was exercised.

Then:

- record the outcome in the M3 plan
  (`.kilo/plans/1791998985158-m3-interactive-sessions-plan.md`, the S3
  progress section) and commit it with the pass artifacts;
- stop the daemon (terminal 2: `kill <daemon pid>` → the log shows
  `Scheduler has been shut down`, then `serve stopped: scheduler stopped,
  runners terminated`); kill the mock portal (terminal 1);
  `rm -rf /tmp/bc-d64`;
- decide on step 8's recipe commit: **revert** (recommended — the mutation
  is in-memory and gone with the portal; the repaired locator points at a
  button that no longer exists) with a new commit restoring
  `name: "Log in"`, or keep it. No amends.

## Appendix A — the control socket as the fallback client

The Copilot UI is the primary intervention client (the session page's
tabs); no driver script is needed for this pass. If a session page ever
misbehaves (stale state, a mis-rendered view), the per-run control socket
is the M1 fallback: JSON lines over
`<BC_DATA_DIR>/runs/run-<run_id>.sock` (the `<run_id>` is the `<id>` in
terminal 2's `Run <id> paused …` line). Actions: `screenshot`, `elements`,
`context`, `click {n}`, `fill {n, text}`, `press {key}`, `drag {n, dx,
dy}`, `resume`, `cancel` (protocol v1; `context` returns the same machine-
readable pause payload the detail pause card and the failure panel show).

```bash
# list the numbered elements of the pause page (the package is not
# pip-installed in the venv - PYTHONPATH=apps, run from the repo root)
PYTHONPATH=apps apps/.venv/bin/python - <<'PY'
from billcollector.control import ControlClient
c = ControlClient("/tmp/bc-d64/data/runs/run-<run_id>.sock")
for el in c.request("elements")["elements"]:
    print(el["n"], el["role"], el.get("name", ""))
PY
```

The M2 D6.4 guide's driver
(`.kilo/plans/1791829791901-m2-d64-exit-pass-guide.md`, Appendix A) is the
same client as a script file — reuse it if a multi-call resolution is
needed.
