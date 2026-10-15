# BillCollector — M3: Interactive sessions (execution plan)

Master plan: `.kilo/plans/1790364274061-billcollector-nicegui-daemon-plan.md`
(v3, M3 section — items 1–5 and the Wave 1 exit). M2 execution plan:
`.kilo/plans/1791705823133-m2-ui-core-plan.md` (chunks D1–D6). M2 exit pass
guide: `.kilo/plans/1791829791901-m2-d64-exit-pass-guide.md`.

**Goal:** the Wave 1 exit — all three friction points (DOM change,
ads/cookie forms, CAPTCHAs) are demonstrable end-to-end by a human from the
web UI: the session view (Copilot + noVNC) at the ntfy deep link, and the
recipe repair flow with the candidate picker (primary no-YAML path).
M3 items 4–5 of the master plan (`wait_user`, git commit messages) are
already implemented (M1 C5.5, M2 D5.2) — M3 exercises and verifies them, it
does not build them.

## Verified current state (dev, 2026-10-14)

- **M2 state:** **M2 closed (2026-10-14).** D1–D6.4 all done; the D6.4
  exit pass is **complete** (steps 0–11 verified; M2 plan progress
  records + guide review log). The D6.4 step-4 fixes (dashboard log-pane
  re-point + step strip, engineio disconnect tolerance, `CustomEvent`
  global, runner per-step `logger.info`) are committed
  (`6e7a4f0`, `89af6ea`, `10998af`); the pass record is `7ed16da`.
  Suite 253/253 green, ruff clean. One recorded operator decision
  remains (keep/revert the step-8 description-only recipe commit
  `6fb7108`) — non-blocking for M3.
- **Control protocol v1** (`apps/billcollector/control.py`): JSON lines
  over a per-run unix socket; actions `screenshot`, `elements`
  (numbered, with `rect`), `context`, `click {n}`, `fill {n, text}`,
  `press {key}`, `drag {n, dx, dy}`, `resume`, `cancel`
  (last two reserved, consumed by the runner). `ControlClient` = one
  short-lived connection per request; `PROTOCOL_VERSION = 1`.
- **Pause subsystem** (`pause.py`): `pause_loop` persists the context on
  the Run row, flips the task `waiting`, pushes ntfy, serves the socket
  in the waiting loop until resume/cancel/deadline. `build_pause_context`
  payload: `reason`, `prompt`, `url`, `page_title`, `error`, `step`
  (the `transform_step_to_json` output: `description`, `locators[]`,
  `actions[]` — **no step number**), `screenshot` (path + base64),
  `elements[]`, `page_text` (≈20 KB cap), `deadline_at`.
  `make_action_handlers` is coordinate-based: every element action
  re-scans the page and acts on element `n`'s rect center.
- **Element scan** (`pagestate.py`): interactive = tag in
  `button/a/input/textarea/select/summary/label`, or `onclick`
  attribute, or `contenteditable`; every element carries a `rect`
  (viewport pixels). **The `testcaptchadrag` slider knob
  (`<div id="knob">`, pointer-event JS) is not scannable → the
  `elements` list is empty at that pause** (expected state, see locked
  decision 1).
- **Runner** (`runner.py`): `wait_user(prompt[, until])` implemented
  (C5.5): pauses before execution, consumed on resume, `until` locator
  polled bounded by the pause deadline (deadline exceeded → re-pause).
  Pause call sites — all with the step in scope: `:610` (wait_user),
  `:652` (step_failed), `:668` (download_failed).
  `transform_step_to_json`: actions =
  `click/fill/expect_download/goto/close/content_frame/first`, every
  other method is a locator. Methods dispatch via
  `getattr(previous_result, method_name)` → every Playwright locator
  method (`get_by_text`, `get_by_label`, …) is a valid recipe method.
  Terminal results: cancel → `cancelled`, timeout → `needs_attention`.
- **Recipes:** `recipe-pw__testwaituser.yaml` step 11 and
  `recipe-pw__testcaptchadrag.yaml` step 11 both use `wait_user` with a
  prompt. Mock portal: `verify.html` shows the 6-digit code
  (`#captcha-code`) + textbox (placeholder "verification code") +
  "Verify" button; `drag.html` = track/knob slider (pct ≥ 0.98 →
  "Verified" → dashboard); `challenge.html` = "I am not a robot" button
  (`onclick` → replaced by the "Verified" button).
- **Changed-website drill:** `POST /admin/<site>/mutate` with
  `{"login_button": "…"}` renames the landing login button (default
  "Log in"); `POST /admin/<site>/reset` clears it. In-memory, fresh per
  portal start.
- **Run row / display stack:** `Run` carries `control_sock`,
  `novnc_port`, `pause_context`, `pause_deadline_at`, `pause_reason`,
  `pause_prompt`. `display.py`: per-run Xvfb + `x11vnc -display :N
  -rfbport 5900+N -localhost` (optional `-rfbauth` from the
  `vnc_password` setting) + `websockify 6080+N 127.0.0.1:5900+N`
  (listens on all interfaces; serves the noVNC web client from
  `/usr/share/novnc` when the apt `novnc` package is present).
- **UI:** M2's `/runs/<run_id>` route is a redirect to the task detail
  (`dashboard.py:410`); ntfy deep link =
  `<ui_base_url>/runs/<run_id>` (`notify.py:31`). Task detail pause card
  (read-only: reason, prompt, deadline countdown, pause screenshot;
  `task_detail.py:238-276`). Dashboard step strip: latest step
  screenshots via `db.list_page_status(run_id)` + `runfile_url`
  (DB-driven, no directory listing). Recipe editor
  (`/recipes/<service>`): CodeMirror YAML + step-tree sidebar +
  Validate + Save (`save_recipe` atomic → `git_commit` when
  `git_commit_enabled`) + per-task Run now buttons after a successful
  save. `/runfiles/<run_id>/…` static dir for screenshots.
- **Test stack:** pytest + `nicegui.testing.User` (253 tests; `Screen`
  unused), the D3.2 shared-module stub pattern for reaching the
  production orchestrator from User tests, `ruff` (E/F/W) on
  `apps/billcollector/` + tests. Suite:
  `apps/.venv/bin/python -m pytest tests/ -q` from the repo root.

## Prerequisite — M2 closeout (before S1)

- **Done (2026-10-14).** The D6.4 exit pass ran to completion (steps
  0–11, fresh scratch env `/tmp/bc-d64`); the outcome is recorded in
  the M2 plan and the guide review log; the step-4 fixes and pass
  artifacts are committed (`6e7a4f0`, `89af6ea`, `10998af`, `7ed16da`).
  No pass bugs surfaced that block S1. The deferred dashboard step-strip
  thumbnail-width observation (guide review log #1) stays deferred
  (cosmetic, M2).

## Locked decisions

1. **Drag CAPTCHA via noVNC; the protocol stays v1** (user-confirmed
   2026-10-14). Master-plan decision 10 already positions noVNC as "full
   mouse/keyboard for anything Copilot cannot express", and the Wave 1
   acceptance says "Copilot `drag` **or** noVNC". No new protocol
   action, no version bump, no coordinate-eyeballing UX. The session
   page must render an **empty `elements` list** gracefully: no
   overlay, no element select, a hint pointing at the noVNC tab.
2. **Session view = `/runs/<run_id>`** — replaces the M2 redirect
   (master plan decisions 13/21: the ntfy deep link lands here; the
   operator acts from a phone without opening the dashboard). Task
   detail stays `/tasks/<id>`; its pause card gains an **Open session**
   link (→ `/runs/<run_id>`).
3. **Session page state machine** (≈2 s DB poll, same regime as the
   other pages):
   - **waiting** → Copilot interactive: prompt banner (reason, prompt,
     deadline countdown), live screenshot + numbered overlay, element
     select + action bar, **Resume**, **Cancel** (confirmation dialog →
     protocol `cancel` → run ends `cancelled`), noVNC tab.
   - **running** → read-only: the latest step screenshot (the newest
     `PageStatus` row with a screenshot, the dashboard step-strip DB
     pattern) + noVNC tab (observation); link to the task detail.
   - **ended** (`success`/`interrupted`/`cancelled`/`needs_attention`)
     → result summary; the last pause context read-only when
     `pause_context` is set (reason, prompt, screenshot, elements);
     link to the task detail. No noVNC (the display stack is reaped).
   - **unknown run id** → 404 label (the M2 behavior).
4. **Copilot transport:** the UI process opens `ControlClient(run
   ["control_sock"])` per request (NiceGUI sync handlers run in the
   threadpool; the socket lives under `BC_DATA_DIR`, shared with the
   runner). While `waiting`: poll `screenshot` + `elements` every ≈5 s
   (the page changes after an action); after every action: immediate
   refresh + a `ui.notify` with the result. A `ControlError` (the run
   ended mid-request) is handled gracefully: notify + state refresh,
   never a page crash.
5. **Overlay placement (server-side):** parse the PNG dimensions from
   the base64 screenshot (IHDR bytes 16–24, no dependency) and place
   each numbered badge by percentage — `left = (x + w/2) / img_w`,
   `top = (y + h/2) / img_h` (a pure, unit-tested function). Badges are
   plain NiceGUI elements (no slot template → no Vue runtime-compiler
   workaround needed). Tapping a badge selects the element into the
   action bar (mobile-first: the phone is a first-class intervention
   device). A non-PNG/corrupt screenshot → no overlay (screenshot +
   element list still usable).
6. **noVNC tab:** `ui.html` iframe whose `src` is built **client-side**
   from `window.location.hostname` + `Run.novnc_port`
   (`/vnc.html?autoconnect=true`) — one URL works for a localhost
   operator and a LAN operator (websockify listens on all interfaces,
   x11vnc is `-localhost`). Rendered only while the run is alive
   (`running`/`waiting`). The RFB password (the `vnc_password` setting)
   is entered in noVNC's own prompt — never in the URL.
7. **Repair flow (primary no-YAML path):** a **Repair recipe** button on
   the session page (a `step_failed` pause, while waiting **or** after
   the run ended) → `/recipes/<service>?run=<run_id>`. The editor
   preloads a **failure panel** from `Run.pause_context`: the failure
   screenshot (`/runfiles` URL), the failed step (number, description,
   expected locator chain, error), and the candidate list (n, role,
   name, locator type) with a **Use** button per row. **Use** = replace
   the failed step's locator prefix with the candidate's locator
   (`locatorType` + `arguments` → the recipe's list-of-single-key-dicts
   method shape, key order preserved), keeping the original action
   methods (`click`/`fill`/`press` with their arguments, e.g.
   `{{PASSWORD}}`); the editor reloads with the rewritten YAML (the
   operator can fine-tune — the advanced path). Then the existing
   Validate → Save → git commit → per-task Run now. **Not applicable**
   (picker disabled with a hint, YAML path): steps with no locator
   prefix (e.g. `goto`), nested `expect_download` steps, and
   `download_failed` pauses.
8. **Additive pause-context field `step_number`** (int, `None` for
   pauses without a step): sibling of `step`, passed from the three
   runner pause call sites (all have the step in scope). The protocol
   stays v1 (no action/message changes); the contract docstring
   (`pause.py`) is updated; older consumers ignore the unknown field.
   This is what lets the editor find the failed step without parsing
   the prompt string.
9. **`wait_user(prompt[, until])` (master plan M3 item 4):** already
   implemented (M1 C5.5, incl. `until` polling + re-pause on deadline);
   the mock recipes already use it. M3 exercises it in the exit pass;
   recipe-authoring docs stay in M4.
10. **Structured git commit messages (master plan M3 item 5):** already
    implemented (M2 D5.2, `recipe(<service>): <summary>`); verified in
    the exit pass (scenarios 7 and 8).
11. **Tests:** unit — PNG dimension parse, overlay percentages,
    candidate replacement, state mapping. UI — `nicegui.testing.User`
    against a **stubbed `ControlClient`** (the session module's client
    factory is monkeypatchable; the D3.2 shared-module stub pattern).
    The M2 `/runs/<id>` redirect test is updated in S1.4. Every chunk
    ends with the **full suite green** + ruff clean.
12. **Exit:** a recorded manual Wave 1 pass (the six acceptance
    scenarios), written as a new guide file in the D6.4 guide's pattern
    (prerequisites, numbered steps with expected results, a review log
    table, appendices); the outcome is recorded in this plan.

## Chunks (S1 → S3)

Same pattern as M2's D-chunks: implement in order; each chunk is
independently committable and ends with the full suite green
(`apps/.venv/bin/python -m pytest tests/ -q`) plus its own verification.
A fresh session resumes at the first chunk not yet committed. Commit
style: `feat:`/`test:`/`doc:` + `(M3 chunk S<n>)`.

### S1 — Session view (Copilot + noVNC)

- **S1.1 `ui/session.py` + route:** `register_session(db)` registers
  `/runs/{run_id}`; the M2 redirect in `dashboard.py` is removed;
  `build_app` wiring; the task-detail pause card gains the **Open
  session** link (decision 2).
- **S1.2 Waiting view (Copilot):** the prompt banner (reason, prompt,
  deadline countdown — reuse the task-detail `_deadline_text` pattern);
  the live screenshot (control socket `screenshot`, decision 4) with
  the numbered overlay (decision 5); the element select
  (`n · role · name`); the action bar — **click**, **fill** + text
  input, **press** + key input, **drag** + dx/dy inputs (shown per the
  element's `actionTypes`); **Resume** (primary); **Cancel** (confirm
  dialog → protocol `cancel`); ≈5 s poll refresh + immediate refresh
  after an action; empty `elements` → the noVNC hint (decision 1).
- **S1.3 noVNC tab + running + ended views** (decisions 3, 6): the
  client-host iframe while the run is alive; the running view's latest
  step screenshot (the `PageStatus` DB pattern); the ended view's
  result + read-only last pause context.
- **S1.4 Tests:** unit — `png_dims` (valid, truncated, non-PNG),
  `overlay_pct` (center math, zero-size guard), state mapping
  (waiting/running/ended/unknown). UI (`User`, a seeded `waiting` Run
  row + a stubbed client factory): the banner fields; N overlay badges
  at the expected percentages; each action dispatches the right
  arguments (`click n`, `fill n + text`, `press key`, `drag n + dx +
  dy`); `resume` and `cancel` dispatch; a `ControlError` from the stub
  notifies without crashing; the empty-elements hint; the noVNC iframe
  HTML carries the port. A `running` run (a real runfiles tree): the
  latest step screenshot URL, no action bar. An `ended` run with a
  `pause_context`: result + read-only context. Unknown id → 404. The
  M2 dashboard `/runs` redirect test is updated (the route is the
  session page now).
- **Baseline:** `/runs/<id>` is the operator's intervention page (the
  ntfy deep-link target); full suite green.
- **Verify (manual):** scratch env + mock portal: a `testautopause`
  pause → the ntfy deep link (or `/runs/<id>`) opens the session page;
  Copilot selects "I am not a robot" → click → refresh → "Verified" →
  click → resume → `success` (the M2 driver script is no longer needed);
  a `testhappy` run shows the read-only step screenshots + noVNC
  observation; after the run: the ended view.

### S2 — Recipe repair flow

- **S2.1 `step_number` in the pause context** (decision 8): the
  `pause_loop` parameter, `build_pause_context` payload, the three
  runner call sites, the `pause.py` contract docstring; the M1 contract
  tests updated additively where they assert the payload.
- **S2.2 Candidate replacement (pure):** `recipes.apply_candidate_to_
  step(recipe_data, step_number, candidate) -> recipe_data` (decision 7
  semantics: locator prefix replaced, action methods kept, the
  candidate's `arguments` dict → ordered list of single-key dicts;
  `None`/raise when not applicable — no locator prefix, step not
  found, nested step). Unit tests: the replacement keeps the actions
  and their arguments (`{{PASSWORD}}` intact), the method-entry shape,
  a `get_by_text` candidate, a `get_by_role` candidate with
  `exact: true`; rejection of a `goto` step (no locators), a missing
  step, a nested step.
- **S2.3 Editor preload + session button:** the recipe editor reads
  `?run=<run_id>` → loads `Run.pause_context` → renders the failure
  panel (screenshot `/runfiles` URL, step number/description, expected
  locators, the error) + the candidate rows with **Use** →
  `apply_candidate_to_step` → the editor reloads with the rewritten
  YAML; the disabled-with-hint state when not applicable. The session
  page's **Repair recipe** button links to
  `/recipes/<service>?run=<run_id>` (a `step_failed` pause, waiting or
  ended).
- **S2.4 Tests:** UI — the editor with a seeded `pause_context` renders
  the panel (screenshot URL, step number, candidate rows); **Use**
  rewrites the chain in the editor (assert the re-parsed YAML); Save
  writes the file (the D5.4 pattern: per-test temp recipe dir, temp git
  repo with the toggle on); a `goto` step → disabled picker + hint.
  Unit — the S2.2 function.
- **Baseline:** the candidate picker is the primary repair path (no
  YAML); full suite green.
- **Verify (manual):** `POST /admin/happy/mutate`
  `{"login_button": "Sign in"}` → `testhappy` Run now → the login step
  pauses with failure context → Repair recipe → **Use** "Sign in" →
  Validate → Save → `git log` shows `recipe(testhappy): …` → Run now →
  `success` → `POST /admin/happy/reset`.

### S3 — Wave 1 exit pass (recorded manual)

- **Guide:** new file `.kilo/plans/1791<ts>-m3-wave1-exit-pass-guide.md`
  in the D6.4 guide's pattern. Prerequisites: the dev host stack
  (Xvfb/x11vnc/websockify/novnc), the LAN Vaultwarden Layer B items
  (`testhappy`, `testautopause`, `testwaituser`, `testcaptchadrag` /
  `user1`), repo on `dev` clean (scenario 7 lands a real recipe commit
  — keep or revert afterwards), ports free (8787, 18766, 6080+, 5900+,
  display :99), the WSLg `/tmp/.X11-unix` remount one-liner, the
  browser-build hardlink, scratch root `/tmp/bc-d64`. No driver script
  needed (the Copilot UI is the client); the control socket is
  documented as the fallback (M1 client).
- **Steps** (fresh scratch env; tasks created via the UI):
  1. Login + imported tasks; create `testhappy`, `testautopause`,
     `testwaituser`, `testcaptchadrag` (`user1`), enabled.
  2. ntfy deep link: set `ui_base_url` in Settings; a `testautopause`
     pause pushes ntfy — the link opens the session page directly
     (a second browser/incognito proves it).
  3. **Acceptance 1 — `testautopause`:** 3× step failure → `waiting` →
     Copilot: select "I am not a robot" → click → refresh → select
     "Verified" → click → **Resume** → the step re-executes →
     `success`, the download tracked.
  4. **Acceptance 2 — `testwaituser`:** `wait_user` pause → read the
     6-digit code from the session screenshot (the context `page_text`
     has it too) → Copilot: **fill** the code into the "verification
     code" textbox → click "Verify" → **Resume** → `success` +
     download.
  5. **Acceptance 3 — `testcaptchadrag`:** `wait_user` pause → the
     element list is **empty** (the hint shows) → **noVNC tab** → drag
     the slider all the way right ("Verified") → back to the session
     page → **Resume** → `success` + download.
  6. **Acceptances 4+5 — persistent profile + dedup:** `testhappy`
     run 1: the consent banner shows (the graceful "Reject" row);
     run 2: the banner is absent; run 2's downloads carry the
     duplicate badge (sha256, `duplicate_of` → run 1's rows).
  7. **Acceptance 6 — changed website:** `POST /admin/happy/mutate`
     `{"login_button": "Sign in"}` → `testhappy` Run now → the login
     step fails 3× → pause with failure context → session page →
     **Repair recipe** → the failure panel (screenshot, step,
     candidates) → **Use** the "Sign in" button → Validate → Save →
     `git log` shows `recipe(testhappy): …` (`git show --stat HEAD` =
     the recipe file only) → Run now → `success` →
     `POST /admin/happy/reset`.
  8. Read-only running view + ended view + noVNC observation, as
     observed during steps 3–7.
  9. Final DB checks (no run left `running`/`waiting`; the
     `cancelled`/`needs_attention` rows only if exercised; dedup
     pointers; `profile_reset_at` where set) + record the outcome in
     this plan (`*Done (<date>): …*`) and commit the pass artifacts;
     decide on the scenario-7 recipe commit (keep/revert, a
     description-level change).
- **Baseline (M3 / Wave 1 exit):** all six acceptance scenarios green
  from the web UI; this plan recorded; full suite green.

## M3 exit (v3, unchanged)

The six acceptance scenarios above on the mock portal, incl. the
`git log` check of the repair commit. **Wave 1 exit:** all three
friction points (DOM change, ads/cookie forms, CAPTCHAs) are
demonstrable end-to-end by a human from the web UI, and the AI-open
architecture (versioned intervention protocol + machine-readable pause
context + human-approval gate) is in place and exercised.

## Risks

- **M2 closeout dependency:** if the pending D6.4 steps 7–10 surface
  bugs, they land before S1 (the suite is the gate).
- **nicegui.testing limits:** the overlay is plain elements (assertable
  in `User` tests); the iframe `src` is asserted on the `ui.html` text;
  the real-browser proof is the S3 pass (the M2 pattern).
- **Control socket from the UI process:** a request racing the run's
  end raises `ControlError` — the page must degrade (notify + refresh),
  covered by a stub-raising test (decision 4).
- **PNG dimension parse:** a non-PNG screenshot must not kill the
  overlay path (decision 5 fallback), covered by a unit test.
- **noVNC reachability on the NAS:** websockify listens on all
  interfaces; if a LAN operator cannot reach `6080+N` it is a
  firewall/NAS config matter (documented in the pass guide's
  prerequisites). Recommend setting `vnc_password` on the NAS (the
  noVNC prompt then asks for it).
- **`step_number` touches the "stable contract":** it is additive and
  documented (decision 8) — the context stays complete, stable, small;
  a future pinned-shape client finds the field already there.
- **Candidate replacement semantics:** for a scoped locator chain
  (`get_by_role(main)` → `get_by_role(textbox)`), the candidate's
  absolute locator replaces the whole chain — the expected semantics
  (the candidate **is** the full locator of the real element); the
  operator can still fine-tune by hand (the advanced path).
- **Empty `elements` is a state, not an error** (decision 1): the drag
  pause always yields an empty list; the UI treats it as the noVNC
  hint.

## Out of scope (M3)

- ML/LLM code, action proposals, auto-repair, CAPTCHA solving (a
  future wave, behind the human-approval gate)
- Coordinate-based drag / protocol v2 (locked decision 1)
- Candidate picker for nested (`expect_download`) steps and
  `download_failed` pauses (the YAML path)
- Improving the pagestate scan (the slider knob stays unscannable —
  the noVNC path)
- Onboarding wizard, Docker Compose, recipe-authoring docs, cron
  retirement (M4)
- Multi-user, e-mail/SMTP, paperless consumer, custom REST API
- `playwright codegen` in the UI
