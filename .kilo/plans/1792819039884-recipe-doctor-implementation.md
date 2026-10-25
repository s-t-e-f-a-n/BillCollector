# Stage 1: offline LLM recipe doctor — implementation plan

Extended 2026-10-24: Stage 1b continuation for the remaining five
services (see below).

Goal: implement Option B from
`1792793307574-recipe-repair-llm-options.md` — a dev-side
`billcollector doctor` subcommand that proposes a repaired recipe step
for a captured pause context, gated by the existing
`validate_recipe`/`save_recipe` path and explicit human approval.
Then pilot it on `buhl` (the easiest failure) and `datev`.

## Stage 0 results (input to this plan)

All 7 services run locally (display shim for the WSL2 X-socket quirk),
all paused `step_failed`, pause contexts in `/tmp/kilo/triage/`:

| Service | Step | Failing step | Error | Class | Expected fix |
|---|---|---|---|---|---|
| buhl | 5 | `get_by_role(textbox,"E-Mail-Adresse")` + `press(value:"Tab")` | TypeError → `other` | **recipe bug**: Playwright `press()` takes `key`, not `value` (kwargs dispatch, runner.py:418-424) | `value` → `key` |
| datev | 8 | `get_by_role(button,"Login").click` | strict-mode, resolved 2 | locator ambiguity | `locator` with `#login` or `.first` |
| 1und1 | 4 | `get_by_role(button,"Click to reveal",exact).click` | timeout | stale step (Keycloak changed) | drop/replace step |
| winsim | 8 | `get_by_role(link,"Dialog Schließen").click` | timeout | stale step (dialog gone, rect 0,0,0,0) | drop step |
| freenet_mobilfunk | 3 | `get_by_role(link,"Jetzt einloggen").click` | timeout | element visible, click not actionable (overlay?) | locator tweak / force |
| nuernberger | 7 | `get_by_role(link,"Postfach").click` | timeout | element visible, click not actionable (overlay?) | locator tweak / force |
| kabeldeutschland | 3 | `locator('#loginCredintialsId input[type="text"]')` | timeout | **flow break**: goto now redirects to vodafone.de/meinvodafone | re-authoring (Option D, separate) |

Pilot order: **buhl** (known one-line fix — validates the whole
doctor path against a known answer), then **datev**.

## Design

### Placement

- New module `apps/billcollector/doctor.py` (sync, dev-side; no daemon
  import, no protocol change).
- New `doctor` subcommand in `apps/billcollector/cli.py` next to
  `serve`/`run` (lazy import, same pattern as `run`).
- New test module `tests/test_bc_doctor.py` (repo test conventions).

### CLI contract

```
billcollector doctor <service>
    --pause PATH          pause-context JSON file, or a directory
                          (newest *_pause.json wins)
    --from-run RUN_ID     read Run.pause_context from the local DB
    --llm-url URL         OpenAI-compatible base URL (default $BC_LLM_URL)
    --llm-model MODEL     model name (default $BC_LLM_MODEL)
    --llm-api-key KEY     optional (default $BC_LLM_API_KEY)
    --prompt-file FILE    dump the prompt and exit (no LLM call)
    --llm-response FILE   use a canned LLM reply instead of calling
    --out FILE            write the proposed YAML to FILE (default:
                          print to stdout, never touch the recipe)
    --apply               write the proposed YAML to the recipe file
                          via save_recipe (the human-approval gate)
    --timeout S           LLM request timeout seconds (default 120)
```

Default is dry-run: print the verdict + unified diff, exit 0. Nothing
on disk changes without `--apply`.

### LLM endpoint

OpenAI-compatible `POST {base}/chat/completions` with `requests`
(already in requirements). Base URL may be given with or without the
`/chat/completions` suffix. Text-only input (decision: no vision).
LLM-down / bad-JSON / schema-invalid output → clean error, non-zero
exit, recipe untouched.

### Prompt (text-only)

- system: role + method vocabulary (Playwright sync API names as used
  by the runner: `get_by_role/label/text/title/placeholder`,
  `locator`, `first/nth/last`, `content_frame`, `click/fill/press`,
  `goto/close`, `expect_download`) + strict-JSON output contract +
  rules (minimal change, keep `{{USERNAME}}/{{PASSWORD}}/{{OTP}}`,
  prefer elements present in the snapshot, drop steps whose element is
  gone, `press` takes `key` not `value`).
- user: service, failed step number, error record, url/title, the
  failing step JSON, the full current recipe YAML, visible elements
  (role | name | rect | candidate locator, truncated to ~120 entries),
  page text truncated to ~8 KB.

### Response contract (strict JSON)

```json
{"explanation": "<= 2 sentences",
 "fix_type": "step" | "recipe",
 "step_number": 5,
 "fixed_step": {"step": 5, "description": "", "methods": [...]}}
```
or `{"fix_type": "recipe", "fixed_recipe": "<full YAML text>"}`.

Processing: fence-tolerant JSON extraction → for `step`: replace the
top-level step by number in the parsed document, re-serialize
(`yaml.safe_dump(sort_keys=False, allow_unicode=True)`),
`validate_recipe` gate → unified diff → `--out`/`--apply`/stdout.
`save_recipe` already refuses unvalidated text atomically.

### Exit codes

0 fix produced (applied if `--apply`); 1 LLM says no in-place fix
(flow break / needs human) with its explanation printed; 2 usage or
LLM/network/parse error; 3 recipe or pause-context load error.

## Validation

1. Unit: prompt build, JSON parse (fences, trailing prose), step
   replace + re-serialize round-trip against the real schema, canned
   `buhl` fix (`key: "Tab"`) passes `validate_recipe` and the diff is
   minimal. — DONE (18 tests in tests/test_bc_doctor.py; the test
   baseline normalizes the buhl recipe to its pre-fix state so it is
   stable against the now-fixed live recipe).
2. Pilot buhl: run the doctor with a canned response (path 1) and,
   once the endpoint is provided, for real; `--apply`; re-run the
   buhl task locally (display shim) — expect it to get past step 5. —
   DONE, see Pilot results.
3. datev: real or canned run; expect a `#login`-scoped or `.first`
   variant; apply; re-run. — DONE, see Pilot results.
4. `ruff check apps tests` + pytest for the new module. — DONE (full
   suite 426 passed, 1 skipped; ruff clean).

## Pilot results (2026-10-24)

All doctor runs used canned responses (`--llm-response`); the real
endpoint is still user-provided at runtime. Fixes were applied via
`--apply` (human gate = the printed diff).

- **buhl** — two fixes:
  1. step 5 `press(value: "Tab")` → `press(key: "Tab")` (the Stage 0
     TypeError — the known-answer validation).
  2. step 2 (cookie-consent click) → `graceful: true`. The consent is
     stored in the persistent profile, so the banner only appears
     until first acceptance; a graceful step (single attempt, failure
     continues the run) keeps the recipe valid in both states. This
     exposed a prompt gap: `graceful` was missing from the doctor's
     step vocabulary — added to `build_prompt` plus a
     round-trip test.
  Re-run (run 16): **success**, `WISO Steuer 2025.pdf` downloaded —
  no further stale step surfaced (the WISO label is current).
- **datev** — two fixes:
  1. step 8 `get_by_role(button, "Login")` (strict mode, 2 matches) →
     `locator("#login")`. A read-only headed page inspection (the
     site rejects plain headless) showed the second match is the
     `#SmartLogin` button; `#login` uniquely identifies the form
     submit.
  2. step 10 "Check and log in" → "Continue": DATEV renamed the
     OTP-confirmation button; surfaced by the post-fix re-run (run 17
     paused there, run 18 after the fix).
  Re-run 18: **success**, `Brutto-Netto-Abrechnung 2026 01
  Januar.pdf` downloaded.

Remaining: a real-LLM run once the endpoint URL/model are provided
(everything else is validated offline via `--prompt-file` /
`--llm-response`); the other five services (1und1, winsim,
freenet_mobilfunk, nuernberger, kabeldeutschland) are covered by
Stage 1b below.

## Stage 1b: complete the remaining five services (2026-10-24)

Goal: all 7 services run to the end (PDF downloaded). Remaining:
`1und1`, `winsim`, `freenet_mobilfunk`, `nuernberger` (doctor
iterations) and `kabeldeutschland` (Option D re-authoring). The Stage
0 triage table above stays the classification source; the per-service
forensics below were re-verified against the triage pause contexts
(`/tmp/kilo/triage/*`) on 2026-10-24.

### First: commit the uncommitted Stage 1 work

The working tree still carries all of Stage 1 uncommitted
(`doctor.py`, `tests/test_bc_doctor.py`, the `doctor` subcommand in
`cli.py`, the buhl/datev recipe fixes, the plan README + this file,
`.gitignore` `data/`). Suggest the commits via the dev-commits skill
(user confirms each) before starting Stage 1b, so the new recipe
fixes land as separate commits.

### LLM operation

- The endpoint is user-provided at runtime (no local engine on this
  machine): `BC_LLM_URL` / `BC_LLM_MODEL` / optional `BC_LLM_API_KEY`
  env vars, or `--llm-url/--llm-model/--llm-api-key`. OpenAI-
  compatible base URL (Ollama/vLLM/LM Studio), text-only.
- No endpoint available: `--prompt-file` (inspect the prompt) and
  `--llm-response FILE` (canned reply) still exercise the whole path —
  the mechanism is validated, the judgment is not.
- Per-iteration loop, per service:
  1. Fresh pause: re-run the task locally the same way as Stage 0
     (display shim for the WSL2 X-socket quirk); let it pause on the
     stale step. Use `--from-run <run_id>` — do not reuse the
     `/tmp/kilo/triage/*` contexts as doctor input (2026-10-24
     captures; portals may have changed since). They stay forensic
     reference only.
  2. `billcollector doctor <service> --from-run <run_id>` → read the
     explanation + diff (the human gate).
  3. `--apply`, re-run the task.
  4. Repeat until the run succeeds and the PDF lands in Downloads.
     Expect ≥ 1 iteration per service: each fix surfaces the next
     stale step (datev needed two).

### Doctor prompt enhancement (small code change)

`build_prompt` (doctor.py:224) does not mention the `force` argument,
so the LLM can never propose it. Add to the action vocabulary:
`click`/`fill`/`press` accept `{force: true}` in `arguments` — the
runner's kwargs dispatch (runner.py:418-424) passes it through as
`locator.<action>(force=True)`, which bypasses the actionability
checks (schema-valid via the open `arguments` item schema). Guidance
in the prompt: prefer dismissing a covering banner (a `graceful`
dismiss step) when the snapshot shows a dismissable overlay; use
`force: true` only when the target is present, visible, and no
overlay is identifiable — and note that force does not click
*through* an interactive overlay (the event is still dispatched at
the element's point and routed by normal hit-testing).

Test: extend `tests/test_bc_doctor.py` — the prompt contains the
force guidance; a canned reply adding `{force: true}` to a click's
arguments passes `validate_recipe` and yields a minimal diff.
Validate with `ruff check apps tests` + the full pytest suite.
— DONE (2026-10-24): `test_build_prompt_force_guidance` +
`test_replace_step_force_argument_roundtrip` added; ruff clean, full
suite green (453 passed, 2 skipped).

### Stage 1b results

- **nuernberger** — DONE (2026-10-24, run 21 success): re-targeted
  step 7 to `get_by_role(link, "Postfach", exact)` (the glyph tile is
  gone) and the two invoice rows to the "… PDF" links
  (`Leistungsabrechnung PDF` / `Vertragsinformation PDF`); both PDFs
  landed in Downloads (`Leistungsabrechnung_1079485_01-10-2026.pdf`,
  `Vertragsinformation_1079485_05-10-2026.pdf`).
- **winsim** — DONE (2026-10-25, run 30 success): three doctor
  iterations (all canned replies derived from live page probes; the
  real endpoint is still user-provided at runtime):
  1. Re-run 26 (original recipe) paused at step 7: the "Bestätigen"
     dialog was visible this time (run 14 had surfaced step 8). Fix 1
     (`/tmp/kilo/winsim_fix1.json`): steps 7 + 8 → `graceful: true`
     (both dialogs are transient), stale step 9 "Meine Rechnung" (gone
     from the start page) → `get_by_role(link, "Rechnungen", exact)`
     + `.first`.
  2. Run 27 paused at step 9 (still on /start): the nav "Rechnungen"
     link is covered by the userDataSwitch header widget (click lands
     on the overlay). Fix 2 (`winsim_fix2.json`): step 9 →
     `locator a[title='Rechnungen']` (the quick-entry tile; probe
     `winsim_inspect3.py` verified it navigates to
     /mytariff/invoice/showAll).
  3. Runs 28/29 paused at the step 11 `expect_download`
     (download_failed): the first "Rechnung vom" anchor is itself the
     PDF link (`/mytariff/invoice/showPDF/...`) — the plain step 10
     click already fires the download outside the window, and the
     inner "Rechnung" link no longer exists (probe
     `winsim_inspect4.py` confirmed the click downloads
     `B954329320_rech.pdf`). Fix 3 (`winsim_fix3.json`): the
     `expect_download` window now wraps the "Rechnung vom" + `first`
     click; the stale inner step is dropped.
  Run 30: **success** — `B954329320_rech.pdf` in apps/Downloads.

### Status (2026-10-25)

4 of 7 services are done (buhl, datev, nuernberger, winsim); the
Stage 1b work so far is committed on dev. The remaining three services
deliberately stay open for a follow-up session:

- **1und1** — in progress: the expected fixes (drop the stale
  "Click to reveal" step, graceful consent) are applied and committed,
  but runs 22–25 still pause `step_failed`; next: re-capture a fresh
  pause, then the next doctor iteration.
- **freenet_mobilfunk** — not started: the overlay/consent case
  (checklist item 4), including the `force: true` decision point.
- **kabeldeutschland** — not started: flow break → Option D
  re-authoring against the new vodafone portal (checklist item 5).

The per-iteration loop (fresh pause → doctor → `--apply` → re-run),
the definition of done, and the wrap-up steps below are unchanged; the
wrap-up (batch commit, plan archival) happens after all seven are
green.

### Per-service checklist (order: cheap wins first)

1. **nuernberger** — re-target (not an overlay case).
   Forensics: step 7 targets the glyph tile
   `get_by_role(link, "Postfach \uf054")`; the pause snapshot shows
   the plain nav link `"Postfach"` visible at (460,72) linking to
   `/kunde/pages/postfach/postfach.html` — the intended target.
    Expected fix: rename step 7 to `get_by_role(link, "Postfach",
    exact: true)`; add `.first` if strict mode complains (multiple
    visible matches). Next stale step likely in the Postfach table
    (steps 8/11: cells "Leistungsabrechnung" / "Vertragsinformation")
    — iterate. — DONE (2026-10-24, run 21 success; see Stage 1b
    results).
2. **1und1** — drop a stale step.
   Forensics: the failing step 4 clicks the Keycloak password-
   visibility toggle `get_by_role(button, "Click to reveal", exact)` —
   that button is **absent** from the pause snapshot, the step has no
   automation purpose, and the recipe contains a duplicated step
   number 4 (the first step 4, `get_by_title("Zum Control-Center-
   Login")`, works and lands on the Keycloak page).
   Expected fix: drop the "Click to reveal" step (clean up the
   numbering). Hardening (operator judgment): make step 2 "Ablehnen"
   (cookie consent) `graceful: true` so the run survives when the
    banner is absent (buhl precedent). Next stale step unknown (e.g.
    step 10 `test_id "invoice-link"` in the Control-Center) — iterate.
    — IN PROGRESS (2026-10-25): the two expected fixes are applied
    in the working tree, but runs 22–25 still pause
    `step_failed`; the next doctor iteration is pending (re-capture a
    fresh pause first).
3. **winsim** — drop a hidden-dialog step, then re-target.
   Forensics: step 8's link "Dialog Schließen" has rect 0×0 in the
   pause snapshot (the dialog is no longer shown) → the click times
   out waiting for visibility. Step 9's "Meine Rechnung" no longer
   exists on the start page; "Rechnungen" is visible in two places
   (nav at y≈240, tile at y≈635).
    Expected fixes, two iterations: drop step 8 (or make it graceful);
    re-target step 9 to `get_by_role(link, "Rechnungen")` + `.first`
    (strict mode: two visible matches). — DONE (2026-10-25, run 30
    success; three iterations, see Stage 1b results).
4. **freenet_mobilfunk** — overlay case (the force decision point).
   Forensics: step 3 "Jetzt einloggen" is visible on the pre-login
   page; the snapshot has no top-frame consent element — the
   SP-consent iframe content is invisible to the DOM scan (top-frame
   only) — and the recipe carries a commented-out consent step
   (iframe `SP Consent Message` → "Alle akzeptieren"): the consent
   banner is likely back, covering the CTA.
   Plan: re-enable the consent step as `graceful: true` first (the
   banner text/iframe may have changed — the re-run shows), re-run.
   If the same timeout recurs, drive the paused run once via noVNC /
   Copilot to see the actual banner and set the dismiss locator.
   `force: true` on the step 3 click is only the fallback if no
   covering overlay is found (see the force semantics note above).
   Also watch step 4: its `goto` carries a frozen Keycloak `state`
   parameter; if login is rejected as an invalid/expired session,
   re-capture the login URL from a fresh "Jetzt einloggen" click (a
   new state is issued per click) — a one-line re-record.
5. **kabeldeutschland** — flow break → Option D re-authoring (last).
   Forensics: step 3's `#loginCredintialsId input[type="text"]` no
   longer exists — the portal moved to vodafone.de/meinvodafone
   (pause URL `vodafone.de/meinvodafone/account/login`; the snapshot
   shows the new login form: "Benutzername*", "Passwort*",
   "Zugangsdaten vergessen?").
   The doctor is expected to answer `fix_type: none` here — that is
   the correct outcome, do not force a step edit. Re-author per
   Option D: codegen against the live portal
   (`helpers/BillCollectorCreateRecipe_pw.py`, manual login in the
   codegen browser) → translate to YAML (the mechanical `-t`
   translator; optionally feed the recorded Python to the LLM for
   locator quality, `expect_download` wrapping, `graceful` banner
   steps, `{{USERNAME}}/{{PASSWORD}}/{{OTP}}` kept verbatim) → the
   usual validate/apply gate → Run-now verification. The whole
   post-login invoice flow must be re-recorded inside MeinVodafone;
   this is the most labor-intensive service.

### Definition of done (per service)

Task run completes, PDF downloaded (verify via the Downloads page /
consumer folder), recipe change landed through the validation gate
with the reviewed diff.

### Wrap-up (after all seven are green)

1. Commit the recipe fixes + the doctor prompt enhancement
   (dev-commits, user confirms).
2. Archive the delivered plans: move this file and
   `1792793307574-recipe-repair-llm-options.md` to
   `.kilo/plans/completed/`, update `.kilo/plans/README.md` per its
   own rules (the daemon master plan stays active).
3. Stage 2 (Option C in-daemon copilot) stays a separate plan; the
   pause context + the proven doctor prompt are its foundation.

### Risks (Stage 1b)

- Pause contexts go stale: always re-capture before each doctor
  iteration; the triage captures are forensic reference only.
- The element scan is top-frame only: iframe overlays (freenet
  consent) are invisible to the doctor → noVNC/Copilot inspection as
  the manual fallback.
- No local LLM: the endpoint arrives at runtime; without it the
  canned-reply path validates the mechanism, not the judgment.
- A wrong LLM fix is caught by `validate_recipe` + the diff review;
  worst case is another pause — the recipe file is only written via
  `save_recipe` with `--apply`.
- Portals may change again between now and the runs — per-iteration
  re-capture keeps the doctor input fresh.

## Out of scope

- Option C (in-daemon copilot at pause time) — Stage 2, separate plan.
- Option D re-authoring for kabeldeutschland (vodafone flow) — per-
  service manual work with the codegen helper.
- NAS deployment of the doctor (it is dev-side; the NAS keeps the
  current pause/editor repair flow).

## Risks

- No local LLM engine on this machine: the endpoint URL/model arrive
  at runtime (user-provided). Everything is testable offline via
  `--prompt-file` / `--llm-response`.
- YAML re-serialization changes quoting style → noisy diff;
  mitigated by `sort_keys=False` and review before `--apply` (the
  validation gate is correctness, the diff is the human gate).
- The doctor must never break the daemon: it is a separate
  subcommand, imports no daemon state, and writes only through
  `save_recipe`.
