# BillCollector — Useful code extensions from the flowcool fork

Input for `.kilo/plans/1790364274061-billcollector-nicegui-daemon-plan.md` (daemon/webui v2).
Goal: catalog every extension in `github.com/flowcool/BillCollector` that is useful for the
daemon/webui plan, with a verdict per item and concrete amendments to the v2 plan.

## 1. What the fork is (verified 2026-09-28)

- `flowcool/BillCollector` is a **public fork of `s-t-e-f-a-n/BillCollector`** (your sanitized
  GitHub mirror). 57 commits, head `7480bc9`. README: "maintained fork … carries
  production-tested changes that have not all been accepted upstream."
- **Fork base = your Selenium-era code, pre-Playwright** (before `edc7e43`/`2a0de6f`):
  it has `BillCollectorServices.py` (Selenium), no `BillCollectorServices_pw.py`, no
  `recipes_playwright/`, no `helpers/`. It renames your `recipe-se__*` recipes to
  `bc-recipe__*`.
- Your repo moved on since: Selenium dropped (`bf5669c`), Playwright 1.63, NiceGUI
  manual-run UI, daemon v2 plan. **Nothing in the fork ports as-is code-wise; extensions
  are ported as concepts, semantics, schemas, and tests.**
- Recipe inventory comparison (evidence: local tree at `bf5669c^` vs fork tree):
  - Your Selenium-era recipes (8): 1und1, buhl, datev, freenet_mobilfunk,
    kabeldeutschland, **lichtblick**, nuernberger, winsim — all inherited by the fork.
    `bc-recipe__winsim.yaml` verified **byte-identical** to your
    `recipe-se__winsim.yaml` (including the commented-out step 4).
  - The fork's **only new recipe: `free` (Freebox Internet)**, production-validated
    end-to-end on 2026-07-27 (README), the first to use `DownloadAll` + metadata.
- Dependencies: the fork's extensions use **stdlib only** (`hashlib`, `json`, `fcntl`,
  `shutil`, `pathlib`, `ipaddress`, `socket`) — no new packages for your stack.

## 2. Extension inventory (all fork additions vs upstream base)

### A1. Persistent download deduplication — staging → publish pipeline
`apps/BillCollectorState.py` (4.9 KB), `docs/DEDUPLICATION.md`, `tests/test_download_state.py`.
- Downloads land in a **staging dir** (`/apps/Downloads`), never the DMS watch dir;
  only after dedup are files **moved** (atomic rename, same filesystem) to the
  **output dir** (`/apps/Output`, e.g. Paperless mount).
- Three independent SHA-256 hash lists per account: **URL**, **final filename**
  ("document identity"), **content**. Decision order: URL pre-filter (only for list
  downloads) → stage → filename/content hash → publish. Freebox regenerates URLs and
  PDF bytes between sessions while the filename stays stable — hence filename is
  authoritative for that provider (DEDUPLICATION.md "Current scope").
- Privacy: state stores hashes only (no raw URLs, names, credentials); account keyed by
  SHA-256 of the Bitwarden **item ID** (rename-safe).
- Durability: atomic write (tmp + fsync + `os.replace`), previous valid state kept as
  `downloads-v1.json.bak`, **fail closed** on corrupt/unsupported state, `fcntl` flock
  against concurrent jobs. At-least-once semantics (state saved after publish).
- **Usefulness: high.** Your current `expect_download` flow
  (`BillCollectorServices_pw.py:431-458`) drops files straight into `DOWNLOAD_DIR` with
  no dedup — the daemon plan's decision #14 ("folder drop stays + sha256 dedup") is
  refined by this: the DMS must never see partial/duplicate files.

### A2. Vault client hardening + Bitwarden Cloud via `bw serve`
`apps/BillCollector.py` (+ `tests/test_bitwarden_api.py`, 14 tests).
- `get_item_by_name`: `/list/object/items?search=…` then **exact name match**, hard error
  on 0 or >1 matches (doublette detection — your old "TODO Intercept doublettes" is
  solved). Item naming `f"{service} {user}".strip()` is **identical** to daemon-plan
  decision #7's vault link.
- `get_totp`: HTTP 400 → `None` ("TOTP not configured"), other failures raise with
  status (replaces "No TOTP" magic-string handling — daemon plan M0 step 3).
- `is_api_url_local`: `BW_API_URL` must resolve **only** to RFC1918/loopback addresses
  (getaddrinfo + `ipaddress`; rejects mixed public+private DNS).
- `BW_API_HOST`: optional `Host` header override for `bw serve` DNS-rebinding protection.
- Startup flow: `/status` (success + `data_template_status: unlocked`) → `/sync` → work.
- Same API works for **Vaultwarden and Bitwarden Cloud** (the latter via a sidecar
  `bw serve` container) — broadens M4 adoption beyond self-hosted Vaultwarden.
- **Usefulness: high** (M0 step 3 `vault.py` gets all of this nearly for free).

### A3. `DownloadAll` action
`BillCollectorServices.py::download_all_webelements`, schema entry, `bc-recipe__free.yaml`.
- Locates **all** links matching one selector (invoice-history lists); per link:
  URL pre-filter via dedup state → open via `window.open(href, '_blank')` (or click for
  non-href elements) → wait for the new download → close the popup window → if the
  listing page changed, navigate back and re-assert the list. Guards: "list changed
  after N of M", 0 elements → error unless `graceful`.
- **Usefulness: high for community portals** (Freebox proves it); **potentially for
  winSIM** — your winsim recipe navigates to `/mytariff/invoice/showAll` (step 7) and
  downloads a single `Rechnung` link (step 9). If that page lists multiple invoices,
  `download_all` replaces the single download. (Open question Q1.)

### A4. `ClickUntilAbsent` action
`BillCollectorServices.py::click_until_absent_webelement`, schema (exactly 2 locators,
`maxClicks` 1–100), 6 dedicated unit tests.
- Bounded pagination: click button-locator until it disappears; progress proven by a
  second "result" locator whose visible count must grow (or the button must vanish);
  **stalled pagination and disabled-but-present button are distinct failures**;
  `scrollIntoView` before each click; hard `maxClicks` limit.
- **Usefulness: medium-high** — generic recipe primitive (paged document lists),
  complements `download_all`.

### A5. Recipe metadata compatibility contract
`apps/bc-recipes/bc-metadata-schema.yaml`, `bc-metadata__free.yaml`,
`BillCollectorRecipes.py::CheckRecipeMetadata`.
- Optional per-service `bc-metadata__<service>.yaml`: `service`, `recipeVersion`
  (semver), `recipeFormatVersion` (int), `requiredActions` (list).
- Engine checks it **before opening the portal**: format version newer than supported
  or missing required actions → explicit immediate stop. Recipes without metadata stay
  supported.
- **Usefulness: high** — the daemon plan already changes the recipe format
  (`wait_user`); a `recipeFormatVersion` + required-methods contract makes the runner
  fail fast and is the foundation for community recipe releases (M4).

### A6. Download hardening semantics
`BillCollectorServices.py` (`download_webelement`, `wait_for_new_download`,
`download_all_webelements`, `perform__navigate`).
- `wait_for_new_download`: monotonic deadline; ignores Chrome temp artifacts
  (`.crdownload`, dot-prefixed); requires **exactly one** completed new file
  (0 or >1 → error); 0.2 s poll.
- Document URL = element `href`, falling back to `current_url` (button-based
  downloads); for click-based list entries a synthetic stable URL
  `<listing>#clickable-download-<n>` is recorded for dedup.
- `Navigate` requires an absolute `https://` URL (schema pattern + runtime check).
- **Usefulness: high** — port the *semantics* to the Playwright runner
  (`page.expect_download`, completed-event before `save_as`, single-download
  assertion). Your pw code already records `download.url` + `suggested_filename`
  (lines 448-452), so the data for all three dedup hashes is already collected.

### A7. Log hygiene / credential redaction
README ("standard container logs without credential values in action traces"),
`test_recipes.py::test_actions_do_not_log_subscriber_identifier` (asserts the
`{USERNAME}` value never appears in action-trace output; only service names are logged).
- **Usefulness: high** — the daemon streams runner stdout into the UI (`ui.log`) and to
  per-run log files; a test-verified redaction policy belongs in M1 (runner) and
  protects the "share logs with the community" path (M4).

### A8. CI + test suite
`.github/workflows/ci.yml` (Python 3.12, `py_compile`, `unittest discover`),
`.github/workflows/container.yml` (GHCR publish: branch/tag/sha/latest tags, GHA cache,
PR smoke test asserting `id -u` = 1000), `tests/` (3 files, ~32 tests).
- **Usefulness: high** — your repo has no CI (v2 plan fact). The fork's three test
  files are ready-made templates for the v2 plan's M1/M2 pytest suites (vault client,
  dedup state, recipe validation incl. "every schema action has a runtime handler"
  and "all bundled recipes match the schema").

### A9. Container hardening + compose reference
`Dockerfile` (ubuntu 24.04, UID/GID 1000, `VOLUME /apps/Downloads`, OCI image labels,
amd64 guard), `examples/docker-compose.yml` (read-only config/recipes mounts, staging
`/apps/Downloads` + state `2750` + output `/apps/Output` separation, `cap_drop:
NET_RAW`, `no-new-privileges`, pinned `sha-` image tag), `examples/billcollector.ini`.
- **Usefulness: medium-high** — your daemon image differs (uvicorn serve, Playwright
  Chromium, x11vnc/websockify/novnc), but the hardening *patterns* feed M0 step 6
  (non-root) and the M4 Docker Compose package. Do **not** copy the
  chrome-for-testing install (you use Playwright Chromium).

### A10. Freebox recipe + "safe operating model"
`bc-recipe__free.yaml` (5 steps, `DownloadAll`, per-step `description`),
README section "Safe operating model": pin image + pin a tagged recipe release, manual
runs before any scheduling, keep previous release for rollback, never track recipe
`main` in production.
- **Usefulness: medium.** The Freebox recipe is Selenium-format (not directly reusable,
  but a reference for a `download_all` recipe + metadata example). The operating model
  **confirms your own deployment strategy** (cc6630e) and should be cited in M4 docs.

### Not adopted (and why)

| Item | Reason |
|---|---|
| Selenium engine code (`LOCATOR_MAP`, `ACTION_MAP`, `clickshadow_webelement`, `InitBrowser`) | Your base is Playwright; only semantics (A3/A4/A6) port |
| Fork recipe layout/naming (`bc-recipes/`, `bc-recipe__*`) | Keep `recipes_playwright/` + `recipe-pw__*` (v2 plan decision #7) |
| `is_domain_local_ip` / `extract_ip` (nslookup-based) | Superseded by cleaner `is_api_url_local` (A2) |
| Dead helpers `latest_download_file`, `is_download_finished` (`os.chdir` hack) | Legacy; no equivalent needed (pw uses download events) |
| Line-file ini + `[bracket]` syntax (`extract_strings`) | Your sectioned ini + comma list is already equivalent; M1 import parses your actual ini format |
| GHCR publishing of the Selenium image | Your deployment builds locally per your deployment strategy plan |
| `WatchedFileHandler` log setup | Your M0 already moves to the `logging` module |

## 3. Verdict summary

| # | Extension | Verdict | Lands in (v2 plan) |
|---|---|---|---|
| A1 | Dedup staging→publish, 3-hash, fail-closed | **Adopt** | decision #14, M1 |
| A2 | Vault hardening + `bw serve`/Bitwarden Cloud | **Adopt** | M0 step 3, M4 |
| A3 | `DownloadAll` | **Adopt** (method `download_all`) | schema ext., M1/M3 |
| A4 | `ClickUntilAbsent` | **Adopt** (method `click_until_absent`) | schema ext., M1 |
| A5 | Recipe metadata contract | **Adopt** | schema ext., M1, M4 |
| A6 | Download hardening semantics | **Adopt** | M1 runner |
| A7 | Log redaction (test-verified) | **Adopt** | M1, M4 docs |
| A8 | CI + 3 test suites | **Adopt** | M0, M1, M2 |
| A9 | Container hardening patterns | **Adapt** | M0 step 6, M4 |
| A10 | Freebox recipe + operating model | **Reference only** | M4 docs |

## 4. Proposed amendments to the v2 daemon plan

Apply when updating `.kilo/plans/1790364274061-billcollector-nicegui-daemon-plan.md`:

1. **Decision #14 (downloads)** — replace "folder drop stays + per-task sha256 dedup"
   with: per-run **staging dir** (`<data>/runs/<run_id>/staging/`); after download,
   dedup per task on **three** hashes (url, filename, content) — all already captured
   by the pw flow; publish = atomic move to the shared Downloads folder (the DMS watch
   dir); `Download` rows gain `dedup_reason` (`url`/`filename`/`content`/`none`) and
   `duplicate_of_id`; corrupt dedup history **fails the run closed** (never auto-reset);
   post-download hook (`consumers/`) runs **after publish**, not on staging.
   State lives in the existing SQLite `Download` table (v2 data model) — the fork's
   JSON-file state is *not* adopted; only hash semantics + staging + durability rules
   (atomic replace, `.bak`, fail-closed) carry over.
2. **Recipe schema extension** — extend `recipe-pw-schema.yaml` with methods
   `download_all` (args: locator, timeout, maxClicks default 100, graceful),
   `click_until_absent` (args: 2 locators — button + progress, timeout, maxClicks),
   alongside the already-planned `wait_user`; add `recipeFormatVersion: 2`; add
   optional per-service metadata file (`recipe-pw-metadata__<service>.yaml`:
   `service`, `recipeVersion`, `recipeFormatVersion`, `requiredMethods`) validated by
   `CheckRecipe` **before** the runner opens the portal (unsupported → explicit stop).
3. **M0 step 3 (vault)** — `vault.py` implements: exact-name match (error on 0/>1),
   TOTP 400→`None`, `is_api_url_local` guard on `BW_API_URL`, optional `BW_API_HOST`
   header, `/status` (unlocked) + `/sync` before first use; works against Vaultwarden
   **and** Bitwarden Cloud via local `bw serve` (documented in M4). Port
   `tests/test_bitwarden_api.py` to pytest.
4. **M1 (runner)** — port A6 semantics to Playwright: `expect_download` with
   completed-event before `save_as` into staging, exactly-one-download assertion,
   href-or-page-url as document URL, synthetic URL for click-based list entries,
   https-only `goto`. Port `tests/test_download_state.py` (rewritten against the
   SQLite dedup logic) and `tests/test_recipes.py` (schema↔handler parity, all
   bundled recipes validate, metadata rejection cases). Add the log-redaction test
   (A7) to the runner suite.
5. **M0 (CI)** — add `ci.yml` (Python 3.12, `py_compile` + test run on PR/push to main)
   now that tests exist; when the image rebuilds, add the container smoke assertion
   `id -u` = 1000.
6. **M2 (UI)** — Downloads page: add "dedup reason" column (url/filename/content/none).
   Recipe editor: show metadata block + format version; block save if metadata says
   the recipe needs a method the engine lacks.
7. **M4 (adoption)** — Docker Compose package per fork patterns: read-only config/
   recipe mounts, staging/state/output volume separation, state dir `2750`,
   `cap_drop: NET_RAW`, `no-new-privileges`; `.env.example` with `BW_API_URL` /
   `BW_API_HOST`; docs section "Safe operating model" (pin image + recipe release,
   manual runs before scheduling, rollback) — cite the fork's Freebox validation as
   community evidence; Bitwarden Cloud path (sidecar `bw serve`) documented.
8. **Dependencies** — no additions required (all A-items are stdlib).

## 5. Open questions

1. **winSIM multi-invoice download** — does the `/mytariff/invoice/showAll` page list
   several PDFs per run, or one? Recommendation: implement `download_all` regardless
   (portable, proven on Freebox); rewrite the winsim recipe to use it only if you
   confirm multiple invoices.
2. **Bitwarden Cloud scope** — ship `bw serve` support in M0 (recommended: same code
   path, tests ready, ~a day of work) or defer to M4 (only needed for community
   adoption)? Recommendation: M0.
3. **Upstream coordination** — the fork intends to "contribute compatible improvements
   back" to *your* upstream. You are upstream: consider (a) a short note to the fork
   maintainer, (b) merging their dedup/CI designs into your repo via this plan, and/or
    (c) asking them to port Freebox to the Playwright recipe format. Out of scope for
    implementation; flag for a community-communication session.
4. **Community selenium line (Option A, section 6)** — do you want to keep offering a
   maintained selenium branch in *your* repo for community members who stay on the
   batch/Selenium path? Recommendation: no — let the fork remain the community's
   selenium line; decide together with flowcool in a community session (they already
   intend to contribute back upstream).

## 6. Option: the fork as a branch in your repo (merged vs. reference)

Question: "Is it an option — and a big advantage — to merge the fork with my selenium
as a branch?"

Facts (verified 2026-09-28):
- **No selenium branch exists locally.** Branches: `dev` (current, = main + 3 commits),
  `main` — both Playwright-era since `bf5669c`; selenium code lives only in history
  (before `bf5669c`). "My selenium" = a point in history (the fork's base).
- **The fork is a true descendant of your history.** After `git fetch flowcool`,
  `git merge-base dev flowcool/main` yields the fork point F (selenium era, before
  `edc7e43`). Merging `flowcool/main` into a branch created at F is a **fast-forward
  with zero conflicts**.
- **The fork's extensions are clean PR units** (individually cherry-pickable):
  #12 recipe-compat metadata, #13 persistent list dedup, #14 single-download dedup,
  #15 `ClickUntilAbsent`, #16 `Navigate` action, #17 clickable `DownloadAll` — plus
  earlier Bitwarden-exact-match/CI/Docker PRs.
- **The fork is active**: latest merge `7480bc9` on 2026-09-27 (PR #17). It keeps
  evolving on the selenium base; divergence from your Playwright line will grow.

### Option A — merge into a recreated selenium branch

- How: `git branch selenium <fork-point F>` (or any selenium-era commit), then
  `git merge flowcool/main` → fast-forward, no conflicts.
- Advantage: **only if you intend to keep offering a maintained selenium line to the
  community.** Your public GitHub repo is what they use; making their maintained line
  live in upstream (instead of "a fork") is genuinely better for them — and the fork
  README explicitly wants to contribute back upstream.
- Cost: a second live code line to track while your own roadmap retires selenium
  (v2 plan M0 step 1, daemon replaces the batch path in M4); the fork keeps shipping
  PRs → an ongoing merge-back loop for a line you will not run.
- **Verdict: option exists, technically trivial, but NOT a big advantage for the
  daemon/webui goal.** It is a community-strategy decision, not an engineering one —
  take it only deliberately, and then coordinate with flowcool (they PR against your
  branch going forward). See open question Q4.

### Option B — reference branch, no merge (recommended)

- How (local only; never pushed to gitea or the GitHub mirror — `sync_github.sh`
  mirrors `main` only):
  ```
  git remote add flowcool https://github.com/flowcool/BillCollector.git
  git fetch flowcool
  git branch reference/flowcool flowcool/main
  git merge-base dev reference/flowcool      # identify fork point F
  git log --oneline <F>..reference/flowcool  # the extension commits, per PR
  ```
- Advantage: the v2 plan's "port/adapt" items become "import + adapt imports" with
  provenance and working tests included; extension commits are locally reviewable and
  diffable; future fork updates diff against one branch; attribution stays intact.
- Import list (all **new paths** in your repo → conflict-free
  `git checkout reference/flowcool -- <path>`, one commit each, message "Port from
  flowcool/BillCollector (MIT): …"):

  | Path | Serves | When |
  |---|---|---|
  | `apps/BillCollectorState.py` | A1 | M0 (standalone, stdlib only) |
  | `tests/test_download_state.py` | A1 | M0 — passes as-is under new CI |
  | `tests/test_bitwarden_api.py` | A2 | M0 step 3 — re-point imports to `billcollector/vault.py` |
  | `tests/test_recipes.py` | A8 | M2 — import the validation/metadata tests only; the selenium-service tests stay on the fork |
  | `.github/workflows/ci.yml` | A8 | M0 — point at pytest instead of unittest |
  | `docs/DEDUPLICATION.md` | A1 | M1 — adjust to daemon design (staging `<data>/runs/<id>/staging/`, SQLite dedup, env var names) |
  | `apps/bc-recipes/bc-metadata-schema.yaml` | A5 | M1 — into `recipes_playwright/` as the pw-format metadata schema |
  | `examples/docker-compose.yml` | A9 | M4 — reference for the compose package (rename image) |

- **Not imported** (conflict or wrong-engine risk): `BillCollector.py`,
  `BillCollectorServices.py`, `bc-recipe__*` + their `bc-recipe-schema.yaml`,
  `Dockerfile` (chrome-for-testing), `requirements.txt` (selenium), `install_*.sh`,
  `BillCollector.sh`, `.env.example` (add the two `BW_API_*` lines by hand).
- Sanity check before importing (defense in depth): quick grep of the imported paths
  for credential patterns — the fork is public and self-sanitized, but it costs
  seconds.
- **Verdict: yes, a real (medium) advantage and cheap** — but "big" only in the sense
  that it removes transcription risk and ships tested, provenance-bearing code into
  M0/M1. It changes no architecture: the Playwright ports (`download_all`, `vault.py`,
  runner staging) are still your work either way.

### Decision for the v2 plan

Add to M0 (after step 0.5): create `reference/flowcool` and import the eight files
above (one commit each). Option A is out of scope unless Q4 is answered yes.

## 7. Validation

- Collection itself: fork files fetched raw from GitHub (tree head `7480bc9`); local
  git evidence: `git show bf5669c^:apps/recipes_selenium/recipe-se__winsim.yaml`
  (identical to fork's winsim recipe), `git ls-tree bf5669c^ -- apps/` (lichtblick
  present pre-fork).
- Reference branch (section 6, Option B): `git merge-base dev reference/flowcool`
  resolves to a selenium-era commit (fork point F); `git log --oneline <F>..reference/flowcool`
  lists only extension commits; the eight imported files land as new paths with no
  merge conflicts; `tests/test_download_state.py` passes unmodified in CI.
- For the implementer: after applying section 4 — CI green (`py_compile` + pytest),
  all 7 bundled `recipe-pw__*.yaml` validate against the extended schema, metadata
  rejection tests pass, dedup unit tests pass (new/filename-dup/content-dup/
  corrupt-state/concurrent-lock cases), container smoke `id -u` = 1000.
