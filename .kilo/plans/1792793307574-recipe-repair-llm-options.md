# Public service recipe recovery - options for LLM-assisted repair (pre-step)

Goal: make the 7 public service recipes (`1und1`, `buhl`, `datev`,
`freenet_mobilfunk`, `kabeldeutschland`, `nuernberger`, `winsim`) fully
operational again (run to end, PDF downloaded). The recipes are months to a
year old; the portals changed in the meantime. This document is the **pre-step
options analysis** for a follow-up implementation plan.

## Verified context

- **Recipes** live in `apps/recipes_playwright/recipe-pw__<service>.yaml`,
  validated against `recipe-pw-schema.yaml`. Method chains: locators
  (`locator`, `get_by_role/label/text/title/...`) into actions
  (`click`, `fill`, `press`), page-level `goto`/`close`, `expect_download`
  with nested steps, daemon-only `wait_user`, `graceful` steps, and the
  candidate phased-`login` contract (`login.py`, `doc/SAFE_LOGIN.md`).
- **No LLM code exists today.** No module, setting, or protocol action
  references a local LLM (no ollama/LLM endpoint in `config.py`
  `DEFAULT_SETTINGS`, the control protocol, or the UI).
- **The pause context is the designed LLM input contract** (decision 20,
  `apps/billcollector/pause.py:91-164`): complete, stable, small, versioned
  via `control.py`. Per pause it persists on `Run.pause_context`:
  `reason`, `prompt`, `url`, `page_title`, `error`, `step_number`, the
  failing step's locator-action JSON, **screenshot** (path + base64),
  **numbered interactive elements** (role/name/rect/candidate
  locator/actionTypes from the `pagestate.py` DOM scan), `page_text`
  (<= 20 KB), `deadline_at`. The pause columns survive resume/timeout, so a
  pause context stays queryable after the run ends.
- **Roadmap states explicitly**: "AI-driven intervention is designed for but
  not implemented" (`openwiki/architecture/roadmap.md`); "a future AI
  assistant is a second client of the same protocol, **gated by human
  approval**" (daemon plan, decision line).
- **Existing repair machinery (works today, no new code):**
  - Run -> non-graceful step fails 3x -> **pause** (`step_failed` /
    `download_failed` / `login_failed` / `wait_user`) -> ntfy deep link.
  - Session page `/runs/<id>`: **Copilot** tab (live screenshot + numbered
    overlay + click/fill/press/drag + Resume/Cancel) and **noVNC** tab
    (full browser on the run's Xvfb display, websockify port `6080 +
    (display - display_start)`).
  - **Repair recipe** link -> editor failure panel (screenshot, failed step,
    expected locator chain, candidate rows with **Use** ->
    `apply_candidate_to_step` at `recipes.py:213`) -> Validate -> atomic
    Save -> optional git auto-commit.
  - **One-off vs permanent split:** a Copilot action (click the right
    element, navigate) rescues the *current* run on resume; the recipe edit
    on disk takes effect on the **next** run (the recipe is loaded once at
    run start, `runner.py:906-908` - resume re-executes the in-memory step,
    it does not re-read the file).
  - **Verification channel:** step screenshots strip + noVNC tab while the
    run is live; PDF lands on the Downloads page / consumer folder.

## Options

### Option A - Manual repair loop (no LLM), as-is

Per service: **Run now** -> wait for pause -> read Copilot screenshot +
candidate list -> **Use** the matching candidate (or hand-edit the step in
the editor) -> Save -> **Run now** again (fresh run picks up the fixed
recipe) -> watch (noVNC / step strip) -> confirm PDF on Downloads. Repeat
per failing step.

- Pros: zero code; the designed path; every pause produced becomes a real
  `pause_context` corpus for later LLM prompt design.
- Cons: human must judge every step across 7 services; slow; flow-level
  breaks (new dialogs, changed navigation, changed download mechanism)
  still require hand-authoring YAML; one-off Copilot rescues re-occur every
  run unless the recipe is also fixed.

### Option B - Offline "recipe doctor" (first LLM integration, dev-side)

A new dev-side CLI (new `billcollector` subcommand, e.g. `doctor <service>`,
or a `helpers/` script following the `BillCollector*` pattern) that takes:

1. the current recipe YAML (`recipe_path_for(service)`), and
2. one or more `pause_context` payloads - exported from the NAS DB
   (`Run.pause_context` rows) or freshly captured locally with a short
   Playwright session against the live portal -

and prompts the local LLM (OpenAI-compatible / Ollama HTTP endpoint) to
return the corrected step or corrected recipe YAML (strict output format).
The tool passes the result through the existing `validate_recipe` gate
(`recipes.py:28`), prints a diff, and the operator applies it through the
existing editor **Use/Save/commit** path (or `save_recipe`). Verification
is the standard Run-now + watch + PDF check.

- Pros: no daemon change, no protocol version bump, no NAS risk; consumes
  the *exact live failure state* (pause context includes the post-login
  page); reuses the existing validation/save/commit gate; text-only LLM
  input (elements + step + error + page text) works with any local model,
  no vision requirement; the human-approval gate is inherent (editor).
- Cons: two hops (export context -> apply fix); no live feedback loop;
  fresh local captures of login-gated pages still need a manual login or
  the exported post-login context.

### Option C - In-daemon "LLM copilot" at pause time (follow-up)

LLM suggestion inside the pause experience: on `step_failed`, the UI (or a
new `suggest` control-socket action = protocol version bump) sends the live
pause context (screenshot if the model is vision-capable, else elements +
step + page text) to the configured local LLM endpoint; the suggestion
renders as an extra candidate row in the failure panel / pause banner with
the existing **Use** button. Human approval stays (project decision: AI is
a second client of the same protocol, gated by human approval); noVNC stays
the fallback.

- Pros: suggestion at the exact moment of failure against the live page;
  one click to apply; becomes the durable product feature.
- Cons: largest surface - new Settings entry (`llm_url`/`llm_model`),
  network reachability from the NAS container to the LLM, prompt
  engineering, LLM-down must not break the pause (degrade to the current
  UI), and either a `control.py` protocol version bump (runner-side) or a
  UI-side HTTP call.

### Option D - LLM-assisted re-authoring (for flow-level breaks)

For portals whose flow changed fundamentally (new onboarding/consent
dialogs, restructured invoice area, new download mechanism): re-record the
new flow with the codegen helper (`helpers/BillCollectorCreateRecipe_pw.py`,
`playwright codegen` against the live portal) and let the LLM translate the
recorded Python into recipe YAML - the existing `-t` translator is
mechanical; the LLM improves locator quality, wraps the download in
`expect_download`, adds `graceful` banner steps, and keeps the
`{{USERNAME}}/{{PASSWORD}}/{{OTP}}` placeholders. Verify with Run now.

- Pros: handles breaks beyond locator drift; reuses the authoring pipeline.
- Cons: codegen needs a logged-in session (manual login in the codegen
  browser, or reuse of the daemon's per-task profile); most effort per
  service; use only where A/B show a flow break, not locator drift.

## How the existing pause/noVNC tools support the objective

1. **Pause context = LLM input contract.** Complete, stable, small,
   versioned, and persisted - an LLM can be invoked on demand, even after
   the run ended (pause columns survive).
2. **Element scan already produces locator candidates**
   (`pagestate.py` -> `get_by_label`/`get_by_role`/`get_by_text`/
   `get_by_title` with rects). The LLM's value-add is *selection and
   chain-building against the step's intent* (description text, expected
   locator, error), not DOM scanning.
3. **The editor's Use-candidate + Validate/Save/commit is the sanctioned
   apply path** for any LLM output - human approval, git history, schema
   gate, no new write path.
4. **noVNC + step strip = verification channel.** After applying a fix,
   Run now and watch the browser live until the PDF lands; when the LLM is
   uncertain, the operator drives the page directly.
5. **Copilot click/fill/press/drag rescues the current paused run
   one-off**, so PDF collection can continue while the permanent recipe
   fix is being worked out.

## Recommended staging

- **Stage 0 (no code):** Option A triage of all 7 services. Classify each
  failure (locator drift vs flow break vs download break vs login break),
  collect real `pause_context`s. Unblocks immediate PDF collection and
  produces the corpus for prompt design.
- **Stage 1:** Option B (offline recipe doctor) - first LLM integration,
  dev-side, reusing the validation gate; pilot on one service.
- **Stage 2 (separate plan, optional):** Option C (in-daemon LLM copilot)
  once the prompt is proven in Stage 1; Option D per service as needed for
  flow-level breaks.

## Open questions (resolve before the implementation plan)

1. **LLM stack:** engine (Ollama?), model(s), vision-capable?, and where it
   runs (NAS host reachable from the daemon container vs dev machine) with
   the network path. Determines prompt input (screenshot vs text) and
   whether Stage 2/C is feasible on the NAS at all.
2. **Autonomy:** confirm human approval stays required for every LLM
   proposed change (recommended; consistent with the project decision).
3. **Pilot service:** recommend `datev` (TOTP login, most complex) - or
   start with the easiest to win a quick success.
