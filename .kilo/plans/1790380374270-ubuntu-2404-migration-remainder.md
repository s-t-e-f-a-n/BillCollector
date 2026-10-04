# BillCollector — Restore the Playwright Batch Path (M0 Step 1, Code Side)

> Status: DELIVERED in v0.3 (commit bf5669c) — retained for the record.
>
> Supersedes the previous content of this file (Ubuntu 24.04 WSL migration
> remainder): that migration is **done and verified** (2026-09-26) — distro,
> Python 3.12.3, fresh venv with pins, CheckRecipe green on all 7 PW recipes.
> This plan is the follow-up: make F5 / the batch path run again under
> Playwright 1.63, per the daemon plan
> (`.kilo/plans/1790364274061-billcollector-nicegui-daemon-plan.md`).

## Context

- F5 (`BillCollector.py` + `bc_test.ini`) fails at startup on the new distro:
  `apps/BillCollector.py:17` imports `BillCollectorServices` at module top →
  `apps/BillCollectorServices.py:7` does `from selenium import webdriver` → the
  new venv deliberately has no selenium (removed in daemon-plan M0 0.3) →
  `ModuleNotFoundError` before any recipe runs. The old environment's venv had
  selenium 4.27.1, which is why F5 worked there.
- The selenium path is **dead code** in the current flow:
  `WebRetriDoc(bc, "playwright")` (`BillCollector.py:255`) filters the loop to
  the `[Playwright]` ini section; nothing ever calls the selenium function.
  The import is a pure load-time crash.
- **Plan-ordering conflict resolved:** daemon-plan M0 0.5 (F5 verification) is
  listed before M0 step 1 (selenium removal), but it cannot pass once selenium
  is out of the venv (0.3/0.4) → step 1 is pulled forward. This is M0 batch
  stabilization, not the NiceGUI migration (M1).
- **Scope decision (user, 2026-09-26): dev environment only.** NAS image
  rebuild + cron run is a separate follow-up (production impact).
- Working-tree note: `apps/requirements.txt` already holds the new full freeze
  (playwright 1.63.0, nicegui 3.17.1, apscheduler 3.11.3, bcrypt 5.0.0,
  sqlalchemy, no selenium) — uncommitted. All `BillCollector.py` imports are
  satisfied by the new venv (dotenv, nslookup, requests, flatten-json,
  sshkeyboard, playwright).

## Task 1 — Remove the Selenium code side (daemon-plan M0 step 1)

1. `apps/BillCollector.py`:
   - Delete line 17: `from BillCollectorServices import retrieve_from_service_with_selenium`
   - Delete the selenium branch in the service loop (lines 215–216); keep the
     playwright branch, i.e. `if automation_library.lower() == "playwright":`
     followed by `retrieve_from_service_with_playwright(...)` (drop the `elif`).
2. Delete files: `apps/BillCollectorServices.py`, `apps/test_selenium.py`,
   `apps/recipes_selenium/` (schema + 8 recipes).
3. `apps/bc_default.ini` and `apps/bc_test.ini`: delete the `[Selenium]`
   section (lines 1–9); keep the `[Playwright]` section.
4. `apps/helpers/BillCollectorHelpers.py`: delete the selenium constants
   (lines 19–23): `RECIPES_SELENIUM_DIR`, `RECIPES_SELENIUM_SCHEMA_FILE`,
   `RECIPES_SELENIUM_PREFIX`, `CHROMIUM_SELENIUM_DIR`, `CHROMEDRIVER_SELENIUM_DIR`.
   No playwright code references them (only the deleted
   `BillCollectorServices.py` did).
5. **Trap:** `apps/helpers/BillCollectorCheckRecipe.py:81` — the
   debug-mode default recipe points at the deleted
   `recipes_selenium/recipe-se-test.yaml`. Repoint to
   `os.path.join(RECIPES_PLAYWRIGHT_DIR, "recipe-pw__winsim.yaml")`.
   (Only affects F5-ing CheckRecipe, not the main F5 — but it would break
   silently after the deletion.)
6. `chrome-linux64*` / `chromedriver-linux64*` artifacts: **nothing to do** —
   they never existed in the fresh clone (gitignored, excluded from the copy).

## Task 2 — `install_local.sh` on 24.04 (daemon-plan M0 0.2)

The venv already exists, so this is for future environment rebuilds, not the
F5 path — but the script is currently broken on 24.04 and references deleted
files.

- Delete `install_selenium()` (lines 94–155), the `selenium` dispatch
  (lines 229–231) and its usage/error strings (lines 7–14, 226, 236). Usage
  becomes `bash install_local.sh playwright`.
- `install_playwright()` apt list (lines 205–212): update the 20.04 package
  names to 24.04 names, aligning with `Dockerfile_pw:24-31`:
  - `libasound2` → `libasound2t64`
  - `ttf-unifont` → `fonts-unifont`
  - `ttf-ubuntu-font-family` → `fonts-ubuntu`
- Header comment: "tested on Ubuntu 20.04 LTS" → "tested on Ubuntu 24.04 LTS".

## Task 3 — Verify the batch path (dev side of M0 0.5)

```bash
cd ~/projects/BillCollector/apps
for f in recipes_playwright/recipe-pw__*.yaml; do
    .venv/bin/python -m helpers.BillCollectorCheckRecipe "$f" || echo "FAILED: $f"
done        # all 7 must pass (regression after the constants removal)
```

- No remaining selenium references: `grep -ri selenium apps/ install_local.sh`
  → expect zero matches.
- **F5** `BillCollector.py` (VS Code, interpreter `apps/.venv/bin/python`) →
  `bc_test.ini`, debug mode with SPACE pauses — hits the **real portals**
  (Playwright 1.48 → 1.63 drift check). Time it deliberately.
  Preconditions (unchanged from the old environment): `apps/.env` holds
  `VAULT_HOST` (must resolve to a local IP) + `BW_API_URL`, and Vaultwarden
  reports `data_template_status=unlocked`.
- If a recipe fails on PW 1.63 drift: fix the locator in
  `recipes_playwright/recipe-pw__<service>.yaml`, re-run CheckRecipe for that
  file, repeat F5 for that service. Distinguish code regressions from
  portal-side changes (CAPTCHA, layout) via the step log / page state.

**Done =** all 7 CheckRecipe pass, no selenium references left, and an F5 run
processes every service in the `[Playwright]` section of `bc_test.ini` with
downloads landing in `apps/Downloads/` and rows written to the fresh
`apps/db/bc.db`.

## Follow-up (explicitly out of this scope — separate step, production impact)

1. Commit + push: new `apps/requirements.txt` freeze + this removal (branch
   `playwright`).
2. Rebuild the NAS image: `deploy_remote.sh` (it does `git fetch` on the
   remote → the push must exist first) or `install_docker-image.sh playwright`
   on the NAS. `Dockerfile_pw:20-21` installs from `requirements.txt` and
   `playwright install chromium ffmpeg` → PW 1.63 + fresh Chromium are picked
   up automatically.
3. Next monthly cron run must complete unchanged (daemon-plan M0 0.5 exit).
4. Optional cleanup (later, M4-docs territory): old selenium `Dockerfile`,
   selenium branch in `install_docker-image.sh`, `.env.example` wording
   ("playwright or selenium"), README selenium sections.

## Risks / edge cases

- F5 uses real credentials against real portals — deliberate, scheduled run;
  failures may be portal-side, not regressions.
- `BillCollectorCheckRecipe.py:81` is a hidden dependency on the deleted
  directory — covered by Task 1.5; if missed, F5-ing CheckRecipe breaks, not
  the main F5.
- Deleted code remains recoverable from git history and from the old 20.04
  distro (kept as backup until daemon-plan M0 is complete).
- The new venv already contains nicegui/apscheduler/bcrypt/sqlalchemy (frozen
  in 0.3) — inert for the batch path until M1; no action needed.

## Out of scope

- NAS image rebuild + production cron verification (follow-up above).
- Daemon-plan M0 steps 2–6 (error propagation, vault client retries, flock,
  logging overhaul, Docker non-root).
- M1+ (NiceGUI daemon), README/docs rewrite (M4).
