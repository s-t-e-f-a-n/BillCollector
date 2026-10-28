# PR #35 review: docs — tested daemon setup and recipe author guides

> Status: VALIDATED (2026-10-27) — S5 complete: code checks all green on the
> exact tree (PR test 1 passed; full suite 590 passed / 10 skipped / 53
> subtests; regression VERDICT: PASS 7 scenarios / 8 PDFs; ruff clean; bandit
> zero-new; 15/15 recipes validate); deployment-process validation skip
> (not deployment-relevant) confirmed by the user at the S5 gate.

## PR metadata

- PR: `s-t-e-f-a-n/BillCollector#35` "docs: add tested daemon setup and recipe
  author guides" (not draft).
- Author: flowcool; head branch `docs/contributor-guides`.
- Head hash: `205e08693e189387c2c9549c823be1e91f78f1b2` (fetched as
  `refs/pr/35`; `git ls-remote github refs/pull/35/head` identical at review
  time 2026-10-27).
- Fork base: `d9362b3` (sanitized GitHub tip after the PR #31 delivery);
  GitHub base ref at review time: `main` @ `6bb3348`.
- Issue refs: #27 hand-over items D02 (tested daemon setup), D05
  (symptom guide), D07 (recipe-author guide); PR body also documents the
  incidental `$schema` hygiene fix.
- Local state at review time (2026-10-27): dev `da67152`, Gitea `main`
  `53a5dff`, `github/main` `6bb3348`. `mergeable_state: clean`; created
  2026-10-26T09:08:05Z.
- Chain position: second in the 2026-10-27 addendum order
  #34 → #35 → #42 → #39 → #40 (#41 held); #34 DELIVERED 2026-10-27.

## Mirror / fork structure (why the merge-base diff misleads)

- `sync_github.sh` amends only the tip commit of Gitea `main` (strips the
  STRIP paths, pins the committer date) and force-pushes it to GitHub
  `main`. Ancestor commits keep their Gitea hashes — with private files
  still in their trees.
- `git merge-base refs/pr/35 github/main` = `36a8d31`, an unsanitized Gitea
  ancestor whose tree contains `.kilo/`, `.private/`, `openwiki/`,
  `AGENTS.md`, `.vscode/`, `.openwikiignore`,
  `.github/workflows/openwiki-update.yml`.
- The PR is actually based on `d9362b3` (the sanitized post-#31 tip; tree
  clean of private paths).
- Consequently `git diff 36a8d31...refs/pr/35` shows 104 deleted private-file
  entries (19,466 deletions). All sit under the STRIP list and all are absent
  from the current `github/main` tip tree (`6bb3348`). These are
  fork-based comparison artifacts, not PR changes: **skipped, never
  applied** (same classification as the earlier PR #14–#16 triage finding).
- The real PR content is `git diff d9362b3...refs/pr/35`: **22 files,
  +602/−17** — 5 new files, 14 recipe metadata lines, 1 generator line,
  README +4, CONTRIBUTING +6/−2.

## Verdict

**Approve**, with two maintainer-side doc-currency fixes (M1, M2) as S3
decision points.

Grounds:

- Scope matches the accepted #27 hand-over items; the incidental `$schema`
  fix removes a maintainer workstation path from 14 public files (hygiene
  fix, inert at runtime).
- The new test's code references all resolve against the current dev tree
  (verified facts 4–7); the mock-portal fixtures it targets are unchanged
  since the fork base.
- No shared-interface change (no DB schema, control protocol, recipe
  contract, or exit-code change; `$schema` is not consumed at runtime).
- Process check passes: issue referenced (#27 D02/D05/D07); intended
  behavior + verification stated; proof shipped (`pytest
  tests/test_doc_recipe.py` → expected `1 passed`); AI assistance disclosed
  ("prepared and verified with Codex under the contributor's direction");
  no secrets (synthetic credentials already present in
  `tests/scenarios.py`); loopback-only networking (ephemeral bind port 0 +
  route abort for non-`127.0.0.1`; quick-start override publishes one
  `127.0.0.1` port).
- Cross-PR: no hunk-level overlap with open #42/#39/#40/#41; queued second
  per the addendum.

## Verified facts

1. `$schema` is inert at runtime: `billcollector/recipes.py`
   `validate_recipe` (recipes.py:29-46) validates against
   `config.RECIPE_SCHEMA`; the `$schema` field of recipe YAML is never read
   by the daemon, and the legacy batch engine passes the schema file path
   explicitly (`BillCollectorServices_pw.py:181`). The change affects
   editors/contributors only.
2. The 14 bundled recipes on dev carry the maintainer workstation path
   `/home/stefan/projects/BillCollector/apps/recipes_playwright/recipe-pw-schema.yaml`
   in `$schema` (8 quoted, 6 unquoted); the 15th
   (`recipe-pw__freenet_mobilfunk.yaml`) is already
   `recipe-pw-schema.yaml`. The PR fixes exactly the 14 and leaves the 15th
   untouched; after integration no bundled recipe carries a workstation
   path.
3. Generator: `BillCollectorHelpers.py:26`
   `RECIPES_PLAYWRIGHT_SCHEMA_FILE = os.path.join(RECIPES_PLAYWRIGHT_DIR,
   "recipe-pw-schema.yaml")`, so the PR's
   `os.path.relpath(RECIPES_PLAYWRIGHT_SCHEMA_FILE, RECIPES_PLAYWRIGHT_DIR)`
   always emits `recipe-pw-schema.yaml`; `os` is already imported in
   `BillCollectorCreateRecipe_pw.py`.
4. `tests/test_doc_recipe.py` — every referenced symbol exists on dev with a
   matching signature: `runner._RunContext(task, run_id, db, debug,
   credentials, api_url)` (runner.py:183-214), `_run_recipe` (runner.py:929),
   `run_result` (runner.py:135), `_launch_browser(ctx, p)` (runner.py:308),
   `_ensure_pdf_preference` (runner.py:265), `_clear_stale_history`
   (runner.py:278), `get_totp` (runner.py:167), `config.RUN_DIR` /
   `config.PROFILE_ROOT`, `config.profile_dir_for`, `db.create_task(service,
   user, recipe_file=...)` (db.py:154), `db.create_run` (db.py:339),
   `db.list_downloads(run_id=...)` (db.py:434), `db.set_setting` (db.py:451),
   `recipes.load_recipe` 4-tuple (recipes.py:62-77).
5. Mock-portal fixture coverage: `tests/mock_portal/` and
   `tests/scenarios.py` are unchanged since the fork base `d9362b3`.
   `landing.html` carries all five login controls the synthetic recipe
   targets (labelled "E-mail address" textbox inside `<main>`, `#user-id`,
   placeholder "e.g. myusername", `title="Password"`,
   `data-testid="password-input"`, "Log in" button); `otp.html` has `#otp` +
   label "6-digit code" + "Check and log in"; `dashboard.html` has the exact
   "My account" link (phase-2/top-level success marker); `invoices.html`
   has the exact "Invoice" links and the contract label
   "Contract info_user1 (PDF)" (the recipe's `get_by_text('Contract info_')`
   is a substring match).
6. Expected artifacts: `scenarios.download_filename('happy', 'user1', ...)`
   yields exactly the test's expected set
   `{invoice_happy_user1_1.pdf, contract_info_happy_user1.pdf}`; happy
   `user1` credentials (`user1`/`user1-pass`, otp `123456` via
   `_full_users` defaults) match the test's documented synthetic
   credentials and the monkeypatched `get_totp` return.
7. Runtime deps: `fastapi` (requirements.txt:17) and `uvicorn`
   (requirements.txt:61) are app requirements → present in `apps/.venv`;
   Playwright `chromium-1243` is installed for the venv.
8. README anchor fix: dev README has "## Configure BillCollector" (line
   277) → `#configure-billcollector` resolves; the old `#configuration`
   anchor matches no heading (broken link).
9. Post-#34 dev baseline: `docker-compose.yml:58` has
   `TZ: ${TZ:-UTC}` and the Dockerfile no longer sets `ENV TZ` (comment:
   "the daemon defaults to UTC when absent"). The guide's claims about the
   Europe/Berlin image default and "the reference Compose file does not
   forward root `.env` `TZ`" are written against the `d9362b3` baseline and
   are stale against dev (findings M1/M2).
10. The QUICKSTART loopback override remains valid against the current
    compose file (`!reset` container_name, image tag, `!override` ports →
    single `127.0.0.1:8766:8000`, no noVNC ports published); its `TZ` line
    is now identical to the base file (redundant, harmless).

## Code review findings

- **M1 (doc staleness — S3 decision):**
  `doc/TROUBLESHOOTING.md`, row "Schedule uses the wrong timezone": "The
  image defaults to Europe/Berlin on this guide's validation baseline. The
  reference Compose file does not forward root `.env` `TZ`." Both clauses
  are false on the integration tree (post-#34: the compose forwards `TZ`
  with a UTC default; the image imposes no default). Proposed maintainer
  fix: rewrite the likely-cause as "root `.env` `TZ` unset (UTC default) or
  set to the wrong zone; an exported shell `TZ` takes precedence", and keep
  the safe next action (set `TZ` in root `.env`, recreate the daemon, verify
  the resolved service environment).
- **M2 (doc currency — S3 decision, optional):**
  `doc/QUICKSTART.md` "Limits and pending work" lists "Runtime date
  variables (PR #34)" and "collision recovery (PR #33)" as pending — both
  are delivered to `main` before this integration. The guide's own hedge
  ("must be checked against the public version you install. Do not assume
  approval means integration.") is still sound; the fix updates the two
  references to their integrated state (or to the generic "verify in your
  installed revision").
- **N3 (nit, no action):** the QUICKSTART override's `TZ` line duplicates
  the base compose after #34; harmless.
- **N4 (scope note):** the PR title is "docs:" but commit `5c69911` also
  carries the one generator line and 14 recipe metadata lines. The PR body
  documents this explicitly ("Fixes 14 workstation-specific bundled
  `$schema` paths and the generator to use recipe-relative references;
  recipe behavior is unchanged"). Not a process issue; at S4/S7 the helper
  + recipe changes ride in their own commit.

Test review: `tests/test_doc_recipe.py` — single test, two runs against the
ephemeral loopback mock portal, asserting per-run the two expected PDFs
(`%PDF` magic), per-task dedup on the second run (`duplicate_of_id` set
iff attempt 1), and `login_failures == 0`. Fixture hygiene: bind port 0
(free loopback port), tmp_path db/profiles/downloads, `get_totp`
monkeypatched with the documented test credential (already committed in
`tests/scenarios.py`), browser route aborts every non-`127.0.0.1` request,
headless Chromium. It executes the guide's exact YAML through the full
runner (phased login, `expect_download`, dedup) — the proof for the guide's
claims. No secrets, no external network.

## Risks

- Doc drift: the guides pin validation baseline `d9362b3`; #34 (TZ)
  changed that baseline's behavior → M1/M2.
- The synthetic recipe and test hardcode mock-portal internals
  (selectors, filenames); a future mock-portal change would break the test
  — acceptable, same coupling as the existing Layer B recipes/tests.
- No runtime behavior change (validator ignores `$schema`; the generator is
  a dev-time tool); regression risk ≈ 0.

## Integration plan (per file)

Skip — fork-based artifacts (104 files): every deletion under `.kilo/`,
`.private/`, `.vscode/`, `openwiki/`, `AGENTS.md`, `.openwikiignore`,
`.github/workflows/openwiki-update.yml`; absent from the current
`github/main` tip; never applied.

Apply as-is from `refs/pr/35` — clean pre-images (16):

- `CONTRIBUTING.md` (anchor fix + guide links)
- `apps/helpers/BillCollectorCreateRecipe_pw.py` (relative `$schema`)
- `apps/recipes_playwright/recipe-pw__{1und1,buhl,datev,kabeldeutschland,
  nuernberger,testautopause,testbadlogin,testcaptchadrag,testdlfail,
  testempty,testgraceful,testhappy,testwaituser,winsim}.yaml` (14 ×
  `$schema` line)

Apply as-is — new files (5), with the confirmed maintainer-side fixes M1/M2
applied on top (exact text in the S3 decision section):

- `doc/QUICKSTART.md`, `doc/RECIPE_AUTHORING.md`, `doc/TROUBLESHOOTING.md`
- `doc/examples/recipe-pw__synthetic.yaml`
- `tests/test_doc_recipe.py`

Manual (diverged, non-overlapping hunks — 2):

- `README.md`: insert the PR's four guide-link lines directly under the
  "## Quick Start" heading (dev's Quick Start section diverged elsewhere,
  +43 lines since the fork base; the insertion point is unchanged).
- `CHANGELOG.md`: the PR ships no entry → author one under
  `## [Unreleased]`: `### Added` (the three contributor guides + the
  credential-free synthetic example) and `### Fixed` (recipe-relative
  `$schema` references in the bundled recipes and the generator). Wording
  drafted at S6.

Expected conflicts: none at hunk level (pre-image check verified against
current dev `da67152`).

## Validation plan (S5, exact dev tree, repo root, `apps/.venv`)

- `apps/.venv/bin/python -m pytest tests/test_doc_recipe.py -q` → `1
  passed`.
- Full suite: `apps/.venv/bin/python -m pytest tests/ -q` → green
  (589 + 1 new at last count).
- Full regression: `apps/.venv/bin/python tests/run_regression.py --ini
  tests/bc_regression.ini` → exit 0, `VERDICT: PASS` (7 scenarios / 8
  PDFs).
- `ruff check` (F821, E4/E7/E9) + `bandit` on the changed files → nothing
  new beyond the known baseline.
- Bundled-recipe schema check (PR body claims "All 15 shipped recipes ...
  validate"): validate every `apps/recipes_playwright/recipe-pw__*.yaml`
  via `billcollector.recipes.validate_recipe` → all ok (one-liner at S5).

## Deployment validation

Recorded skip: **not deployment-relevant** — the PR changes no `Dockerfile`,
`.dockerignore`, `BillCollector.sh`, `install_docker-image.sh`,
`deploy_remote.sh`, INI keys, or `.env` handling. The `$schema` lines are
inert at runtime (verified fact 1) and the generator is a dev-time tool;
container build/launch/canary behavior on the dev tree is unchanged by
this PR. The S5 user gate still applies to this recorded skip.

## Out of scope

- Recipe storage policy (F02), noVNC routing/authentication (F03), C3/F08
  pre-run validation, F06 empty-run semantics — referenced in the guides as
  pending/verify-in-installed-revision; no code changes here.
- `doc/RECIPE_METHODS.md` contract-doc bundle — already delivered with
  #34.
- The #25 publication routine (close comment, issue handling, Discussion
  summary) — S7.

## S3 decision (2026-10-27, user-confirmed)

Proposal accepted **as-is**: 16 clean pre-images + 5 new files + 2 manual
merges (README insertion, CHANGELOG authoring), 104 fork-based STRIP
artifacts skipped, deployment validation recorded skip (not
deployment-relevant) accepted.

**M1 confirmed — TROUBLESHOOTING.md, row "Schedule uses the wrong timezone"**
(replaces the PR head row verbatim):

```
| Schedule uses the wrong timezone | Root `.env` `TZ` is unset (the Compose default is UTC) or set to the wrong zone. | Use the [quick-start override](QUICKSTART.md#build-start-and-check), set root `.env` `TZ` to your IANA zone, then recreate the daemon. Check for an exported shell `TZ`, which takes precedence. Verify the resolved Compose service environment. | The resolved Compose service contains the chosen `TZ`, and the next task time uses that zone. |
```

**M2 confirmed — QUICKSTART.md, "Limits and pending work" bullet** (replaces
the PR head bullet verbatim):

```
- Broader pre-run method validation (C3/F08) and empty-run semantics must be
  checked against the public version you install. Do not assume approval means
  integration.
```

**Commit split confirmed:**

1. `docs: contributor guides for daemon setup and recipe authoring
   (issue #27 D02/D05/D07)` — README + CONTRIBUTING + 3 guides +
   synthetic example + test;
2. `fix: recipe-relative $schema references in bundled recipes and
   generator`;
3. `doc: CHANGELOG — contributor guides + $schema references`.

## S4 execution record (2026-10-27)

**Preflight (green):**

- On `dev` at `cbb995d`, clean tree.
- PR head unchanged: `git ls-remote github refs/pull/35/head` =
  `205e08693e189387c2c9549c823be1e91f78f1b2` = local `refs/pr/35`.
- Pre-image check re-run against the current dev: all 16 candidate files
  byte-identical to their fork-base `d9362b3` versions; all 5 new files
  absent on dev.

**Applied (working tree, uncommitted — S5 validates before any commit):**

- 16 clean pre-images from `refs/pr/35` — verified byte-identical per file
  after apply.
- 5 new files from `refs/pr/35` — `QUICKSTART.md`/`TROUBLESHOOTING.md`
  carry exactly the confirmed M2/M1 replacements (the only deltas vs the PR
  head); the other three byte-identical to the PR head.
- `README.md`: the PR's four guide-link lines inserted under "## Quick
  Start" (byte-identical to the PR block; dev's rest of the divergence
  untouched).
- `CHANGELOG.md` (authored; the PR ships no entry): `### Added` — the three
  contributor guides + credential-free synthetic example + doc test (issue
  #27, D02/D05/D07); `### Fixed` — recipe-relative `$schema` references in
  the bundled recipes and the generator.

**Post-apply checks:**

- All 15 bundled recipes validate via `billcollector.recipes.load_recipe`
  (incl. the untouched 15th).
- Sanitization grep over all applied content: no private paths, hosts or
  credentials.
- `os` import present in the modified generator (verified fact 3).

Integration files intentionally left dirty (S4 rule); this doc-only commit
records the stage. Next: S5 validation on the exact tree.

## S5 execution record (2026-10-27)

**Code checks (all green)** — on the exact integrated dev tree (dev tip
`8479806` doc-only + the S4 dirty files: 18 modified + 5 untracked), from the
repo root with `apps/.venv/bin/python` (`PYTHONPATH=apps`):

- PR's unit test: `pytest tests/test_doc_recipe.py -q` → **1 passed in
  101.34s** (two runs against the ephemeral loopback mock portal).
- Full pytest: `pytest tests/ -q` → **590 passed, 10 skipped, 53 subtests
  passed** (396s). Delta fully accounted for: 589 (dev baseline recorded at
  the #34 delivery) + 1 (the new doc-recipe test) = 590.
- Full regression: `tests/run_regression.py --ini tests/bc_regression.ini` →
  exit 0, **7 scenarios / 8 PDFs, VERDICT: PASS — all expectations matched**
  (testbadlogin / testempty / testdlfail fail as expected; downloads exactly
  the 8 expected files).
- `ruff check --select F821,E4,E7,E9` on the two changed Python files
  (generator + new test) → **All checks passed**.
- bandit on the two changed Python files → **13 LOW / 0 MEDIUM / 0 HIGH**,
  all baseline-consistent: the new test's B101×8 / B105×1 match the existing
  test idioms (`tests/` already carries B101×785 / B105×36, synthetic
  credentials); the generator's B404 / B607 / B603×2 sit in pre-existing code
  (the PR's diff is the single `$schema` line at line 314). **Zero new beyond
  the known baseline.**
- Bundled-recipe schema check: **all 15** `recipe-pw__*.yaml` validate via
  `billcollector.recipes.load_recipe` (including the untouched 15th,
  `recipe-pw__freenet_mobilfunk`).
- PR head unchanged throughout: `git ls-remote github refs/pull/35/head` =
  `205e08693e189387c2c9549c823be1e91f78f1b2`.

**Deployment-process validation — recorded skip (S5 gate pending):**

- Trigger check: the PR changes no `Dockerfile`, `.dockerignore`,
  `BillCollector.sh`, `install_docker-image.sh`, `deploy_remote.sh`, INI keys,
  or `.env` handling → **not deployment-relevant** (as recorded at S3/S4).
  The `$schema` lines are inert at runtime (verified fact 1); the generator is
  a dev-time tool. Container build/launch/canary behavior on the dev tree is
  unchanged by this PR.
- Gate: the user confirms this recorded skip (or orders the full NAS block
  anyway) before S6/S7 proceed; S7 may not commit or push to `main` without
  the confirmation.

**S5 gate (2026-10-27, user-confirmed):** the recorded skip is accepted
(not deployment-relevant; no Dockerfile/.dockerignore/shell/INI/.env change,
`$schema` inert at runtime). Status flipped to VALIDATED. Next: S6
documentation (the CHANGELOG `## [Unreleased]` entry was authored at S4;
S6 reviews its wording + confirms the README/CONTRIBUTING changes need no
further doc work).
