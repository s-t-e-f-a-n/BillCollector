# PR #55 review: exact vault item identity before credential reads (issue #48)

> Status: VALIDATED (2026-10-31) — S5 all green on the exact dev tree:
> before/after proof (8/8 new tests fail pre-integration, pass after), PR
> commands exact (130 passed/30 subtests; 18/14), full unit 675 passed/10
> skipped/90 subtests, regression VERDICT: PASS exit 0 (7 scenarios/8 PDFs),
> ruff clean, bandit zero-new on production files (test file: B101 asserts +
> B105 synthetic only); deployment skip recorded + user-confirmed at the S5
> gate; S6 docs confirmed (CHANGELOG M1 stands + vault_transport.md
> correction, no README/CONTRIBUTING change). S7 next.

## PR metadata

- PR: s-t-e-f-a-n/BillCollector#55 "fix(vault): resolve exact item identity
  before credential reads" (flowcool), head
  `397b0b617aaa0eaaf174d0a93897b244e492fc06` (fetched to `refs/pr/55`,
  matches `git ls-remote github`). Two commits in the fetched ref (orphaned
  public tip `e83c8e2` + the fix commit `397b0b6`); the real content is
  **6 files +177/−11** against the branch point `e83c8e2`. The GitHub "Files
  changed" view (104 files, +290/−23395) is an orphaned-tip STRIP artifact:
  the merge-base `5c8216f` carries 32 `openwiki/` files, the PR head has 0.
  Base ref `main` @ `4265ddb` (current GitHub tip); the branch actually
  starts at the orphaned public tip `e83c8e2` (GitHub `main` at the PR #41
  delivery; Gitea-side equivalent `74ba171`).
- Issue: #48 (flowcool, open) — `fetch_credentials()` retrieves
  `/object/item/<name>` and `/object/totp/<name>`; the CLI's name resolution
  can select a case-insensitive or ambiguous match, and the fresh-TOTP
  lookup repeats name selection. Required: list/search, filter on the exact
  full name, exactly one match, item and TOTP by the validated id; optional
  TOTP and existing retries preserved; item naming unchanged; the pinned
  local transport must allow the endpoint search query while continuing to
  reject queried base URLs, userinfo, fragments, redirects and non-local
  targets; errors/logs must not include names, query values, credentials or
  raw endpoint bodies; no schema, recipe, control-protocol or exit-code
  change.
- Created 2026-10-30T20:11:14Z; last updated 2026-10-31T13:59:37Z (before
  this review's fetch).
- Local state at review time: Gitea `dev` = `origin/dev` = `19c4164`, Gitea
  `main` = `origin/main` = `2bf53d8`, GitHub `main` = `4265ddb`. Working
  tree clean.
- AI disclosure present: "AI-assisted focused port and synthetic
  verification under my responsibility. Branch starts directly at public
  main `e83c8e2`."

## Verdict

**Approve with maintainer changes** — M1 (CHANGELOG placement) only; all PR
code and tests apply as-is from head (byte-identical pre-images on `dev`,
the new test file is a clean add).

## Verified facts

1. Head stable: fetched `refs/pr/55` = `397b0b61...`; PR `updated_at`
   2026-10-31T13:59:37Z predates the fetch. S4 preflight re-checks via
   `git ls-remote github refs/pull/55/head`.
2. Branch point: the fork starts at the orphaned public tip `e83c8e2`
   (GitHub `main` at the PR #41 delivery; Gitea-side equivalent `74ba171`).
   `e83c8e2` is **not** an ancestor of the current GitHub `main` `4265ddb`
   (each mirror sync re-pushes the Gitea lineage plus one amended sanitized
   tip, orphaning the previous public tip — same pattern as #53/#54/#56).
   The GitHub "Files changed" view (104 files, +290/−23395; the
   merge-base-`5c8216f`-to-`e83c8e2` part is 99 files −23384 of STRIPped
   private content, `openwiki/` et al.) is an orphaned-tip STRIP artifact,
   not PR content. Integration applies the 6-file delta against `e83c8e2`
   only.
3. Issue #48 before-claim plausible and S5-verifiable: on the pre-integration
   tree the new `test_case_variants_resolve_exact_id_and_totp_by_id` must
   fail (the base `fetch_credentials` resolves by name, so the mocked
   search response is misread and `user`/`password` come back None); after
   integration the PR's stated command passes: 130 passed, 30 subtests.
4. Pre-image vs Gitea `dev` `19c4164`: `apps/billcollector/vault.py`,
   `apps/billcollector/runner.py`, `apps/vault_transport.py` and
   `tests/test_vault_transport.py` are **byte-identical** to the PR base →
   hunks apply cleanly. `tests/test_bc_vault_exact.py` is a new file (absent
   in both base and dev) → clean add. `CHANGELOG.md` diverges (PR #53/#54/
   #56 entries under `[Unreleased]`) → manual merge (M1). Dev files changed
   since the Gitea branch point `74ba171`: `CHANGELOG.md`, `README.md`,
   `apps/billcollector/notify.py`, `apps/billcollector/orchestrator.py`,
   `apps/billcollector/scheduler.py`, `apps/billcollector/ui/tasks.py`,
   `tests/test_bc_login.py`, `tests/test_bc_notify.py`,
   `tests/test_bc_orchestrator.py`, `tests/test_bc_scheduler.py` — only
   `CHANGELOG.md` overlaps the PR.
5. Code review (per file), behavior preserved vs changed:
   - `vault.py` `fetch_credentials` (the core fix): search
     `/list/object/items?search=<quoted name>` → `json.loads` → require
     `success is True` + list `data.data` → **exact case-sensitive** name
     match (`item.get("name") == item_name`) → **exactly one** match, else
     `VaultAPIError("Expected one exact vault item match")` → `item_id`
     validated against `[A-Za-z0-9_-]{1,128}` → item fetched **by id**
     `/object/item/<id>` → detail re-validated (`success is True`,
     `data.id == item_id`, `data.name == item_name`) → TOTP fetched **by id**
     (optional TOTP preserved: `get_totp` still treats 400 as "no TOTP").
     Return dict gains an additive `item_id`; the `user`/`password`/`otp`/
     `url` extraction is unchanged. Error handling:
     `ValueError/TypeError/KeyError/AttributeError` from parsing →
     `VaultAPIError("Invalid vault item response")` **`from None`** (no
     names, queries, credentials or bodies leak); `VaultAPIError` itself
     (e.g. a real 4xx from the search) is not in the catch tuple and
     propagates with its status intact, as does the "exactly one match"
     error. Retry behavior preserved (unchanged `vault_request` policy).
   - `runner.py` (2 hunks): `_fresh_otp` now resolves the TOTP target as
     `getattr(bcs, "vault_item_id", None) or bcs.vault_item_name` — the
     run-start credential re-fetch targets the validated id when present
     and falls back to the name (backwards-compatible with any context that
     sets only the name). `_RunContext.__init__` stores
     `self.bcs.vault_item_id = credentials.get("item_id")` alongside the
     existing `vault_item_name`/`otp_fallback` attributes.
   - `vault_transport.py` (1 hunk pair): `pinned_api_urls(url, *,
     allow_query=True)` — the rejection clause changes from `parsed.query`
     to `(parsed.query and not allow_query)`, so request URLs may carry a
     query while every other authority check (scheme, hostname, userinfo,
     fragment, port, local-only DNS resolution, sorted numeric targets) is
     untouched. `pinned_api_url` (the configured-base validator) now calls
     `pinned_api_urls(url, allow_query=False)` → **queried base URLs stay
     rejected**. `vault_http_request` (the request path) uses the default
     `allow_query=True`, preserving path+query in every pinned target
     (`parsed._replace(netloc=...)`). Redirect refusal, Host-header ASCII
     check and exception sanitization are unchanged.
   - Test review: `tests/test_bc_vault_exact.py` (new, 115 lines, pytest —
     consistent with the repo's 21 pytest test modules + `pytest.ini`):
     case-variant exact selection + item/TOTP by id (asserts the exact
     request URLs); missing/ambiguous/invalid-id (`../SECRET_TOKEN`) all
     fail before TOTP with no "SECRET_TOKEN"/"Genevois" in the error;
     changed item identity rejected; `_fresh_otp` uses the stored id; and a
     real loopback `ThreadingHTTPServer` preflight test (status, escaped
     name `CC Genevois & #/?`, exact item, optional TOTP 400 — only config
     injected, DNS/transport/HTTP stay real). `tests/test_vault_transport.py`
     +24: the search query is preserved in every pinned target (IPv4+IPv6),
     more unsafe forms rejected for the base validator, and a query never
     bypasses the authority/fragment/port/public-IP checks. Synthetic
     markers only, no secrets, no network beyond 127.0.0.1.
6. Process check (CONTRIBUTING.md): issue referenced (#48); intended
   behavior + verification stated in the PR body; proof shipped
   (before/after pytest with expected counts + ruff/bandit/whitespace
   results); AI assistance disclosed; no secrets in code/tests/artifacts; no
   new network exposure (local pinning preserved; only the search query on
   request URLs is new — URL-quoted and local-only); no shared-interface
   change (no DB schema, control protocol, recipe contract or exit code —
   confirmed in the diff; the `fetch_credentials` return dict gains an
   additive `item_id` key read by its only caller).
7. Cross-PR: open PRs are #55 (this), #45 (Playwright browser cache), #44
   (recipe method-chain validation) — all flowcool, all base `main`.
   Batch-2 chain `#53 → #54 → #56 → #55 → #45 → #44` (user-confirmed
   2026-10-30); #53/#54/#56 DELIVERED → #55 is next in order. File overlap
   with #45/#44 besides `CHANGELOG.md`: `apps/billcollector/runner.py`
   (their real content also touches runner.py; #55's two hunks sit in
   `_fresh_otp`/`_RunContext`, a different area — S4/S5 pre-image re-checks
   cover any movement). #55's `vault.py`, `vault_transport.py` and both
   test files are unique to this PR.

## Risks

- Low overall: the change narrows credential resolution (name → validated
  id) behind the existing transport pinning; new failure modes are
  `VaultAPIError`s the runner already records as run failures; no behavior
  change for a vault with exactly one correctly-cased item.
- New hard dependency on the `/list/object/items?search=` endpoint in the
  operator's bw serve build; if absent, runs fail with a clear 4xx
  `VaultAPIError` (final, no retry) instead of silently resolving the wrong
  item — a deliberate behavior change per issue #48.
- M1 as-shipped breaks the Keep a Changelog ordering (a new `### Fixed`
  section inserted before `### Added`) → manual placement fix required.

## Integration plan (S4, on Gitea `dev`)

| File | Action | Note |
|---|---|---|
| `apps/billcollector/vault.py` | apply from head | pre-image byte-identical to dev |
| `apps/billcollector/runner.py` | apply from head | pre-image byte-identical to dev |
| `apps/vault_transport.py` | apply from head | pre-image byte-identical to dev |
| `tests/test_bc_vault_exact.py` | apply from head (new file) | absent in base and dev |
| `tests/test_vault_transport.py` | apply from head | pre-image byte-identical to dev |
| `CHANGELOG.md` | **manual (M1)** | drop the author's misplaced `### Fixed` section (inserted before `### Added`); add the entry at the top of the existing `## [Unreleased] → ### Fixed` section in house style: `- Resolve one exact full vault item name, then fetch credentials and fresh TOTP by its validated id (#48). The pinned local HTTP transport preserves endpoint queries while continuing to refuse queried base URLs and unsafe authorities.` |

Commits (dev-commits, one concern each, proposed in S7):
1. `fix: resolve the exact vault item id before credential reads (#48)` —
   vault.py + runner.py + vault_transport.py
2. `test: cover exact vault item identity and the query-preserving transport
   pin (#48)` — test_bc_vault_exact.py + test_vault_transport.py
3. `doc: changelog + vault transport doc — exact vault item identity (#48)`
   — CHANGELOG.md (M1 placement) + doc/vault_transport.md (S6 correction:
   base/request query distinction, exact-id resolution description)

## Validation plan (S5, on the exact dev tree, `apps/.venv/bin/python`)

1. Before/after proof: the new `tests/test_bc_vault_exact.py` fails on the
   pre-integration tree (name-based resolution), passes after (PR's stated
   evidence: 130 passed, 30 subtests across
   `test_vault_transport.py test_bc_vault_exact.py test_bc_login.py
   test_bc_runner.py`; plus 18 passed, 14 subtests for
   `test_vault_diagnostics.py test_bc_vault_settings.py`).
2. PR unit tests: `apps/.venv/bin/python -m pytest
   tests/test_bc_vault_exact.py tests/test_vault_transport.py -v` → all
   pass.
3. Full unit suite: `apps/.venv/bin/python -m pytest tests/ -q` → all pass
   (watch for pinned behavior assertions in other modules, as in PR #56's
   M2).
4. Full regression: `apps/.venv/bin/python tests/run_regression.py --ini
   tests/bc_regression.ini` → exit 0, VERDICT: PASS (7 scenarios / 8 PDFs).
5. `ruff` + `bandit` on the changed files → nothing new beyond the known
   baseline (PR claim: ruff + whitespace pass, bandit retains the same four
   baseline findings).

## Deployment validation

**Recorded skip, user-confirmed at the S5 gate (2026-10-31).** Not
deployment-relevant: no `Dockerfile`, `.dockerignore`, `BillCollector.sh`,
`install_docker-image.sh`, `deploy_remote.sh`, INI key or `.env`-handling
change (the change is pure Python inside the existing runtime). Validated tree
basis for S7: dev `53bed6b` + the dirty integration (5 PR files + M1
CHANGELOG); if the tree moves after S6, re-validate per the S7 prerequisite.

## Out of scope

- PRs #45, #44 (later in the batch-2 chain).
- The bw serve search-endpoint availability (operator environment, not
  shipped by this PR).
- Any vault-side data change (item naming unchanged per issue #48).

## Open questions

- None: S3 confirmed, S4 applied, S5 validated (deployment skip
  user-confirmed), S6 docs confirmed. S7 (commit + push, promote, mirror,
  close) is the only remaining stage.

## Execution record

- S1 (2026-10-31, "continue pr 55" session): fresh S1 review — no plan doc
  existed for #55 (plans jumped #54 → #56). Head fetched to `refs/pr/55`
  (`397b0b61...`, matches `ls-remote`); PR metadata via the GitHub API
  (issue #48, open PRs #55/#45/#44). Merge-base analysis untangled the
  orphaned-tip base (`e83c8e2`, not an ancestor of GitHub `main`
  `4265ddb`; merge-base `5c8216f`); real content = 6 files +177/−11 against
  `e83c8e2` (the 104-file GitHub diff is an orphaned-tip STRIP artifact).
  Pre-image vs Gitea `dev` `19c4164`: 4/5 existing files byte-identical
  (clean hunks), the new test file a clean add, CHANGELOG diverged (manual
  M1). Code review per file (vault.py exact-id resolution + error
  sanitization, runner.py fresh-OTP id, vault_transport.py `allow_query`
  scoping); process check PASS; cross-PR overlap limited to runner.py +
  CHANGELOG. Verdict: approve with M1 (CHANGELOG placement). S1 gate passed
  (user "proceed, yes", 2026-10-31).
- S2 (2026-10-31, same session): plan doc created (this file,
  AWAITING-DECISION); README + sequencing cross-references updated; doc-only
  commit pushed to `origin/dev`. S3 next.
- S3 (2026-10-31, "continue pr 55" session): proposal presented (5 files
  as-is from head, M1 CHANGELOG placement, 3 commits); user confirmed as-is.
- S4 (2026-10-31, same session): preflight re-verified (dev = origin/dev =
  `53bed6b` doc-only atop the reviewed `19c4164`; PR head still `397b0b61`;
  4 files byte-identical to the PR base, new test file absent). Applied the
  5 files from `refs/pr/55` to the worktree (worktree-only, index untouched)
  and verified byte-identity: the 4 modified files share the PR delta's
  patch-id `034ddf9b...`, the new file's blob hash `f5995304...` matches the
  head. M1 applied: the author's misplaced `### Fixed` block (before
  `### Added`) was NOT taken; the identical entry text was inserted at the
  top of the existing `[Unreleased] → ### Fixed` section (above the #47
  entry). Working tree left dirty (5 code/test files + CHANGELOG) for S5.
  Status: INTEGRATING.
- S5 (2026-10-31, same session): all checks green on the exact dev tree
  (`53bed6b` + dirty integration), from repo root with the venv:
  - Before/after proof: with the 3 production files stashed to base, the new
    `test_bc_vault_exact.py` fails **8/8** (name-based resolution); with the
    integration, all pass.
  - PR unit tests (2 files): 30 passed, 30 subtests.
  - PR-stated 4-file command (`test_vault_transport.py test_bc_vault_exact.py
    test_bc_login.py test_bc_runner.py`): **130 passed, 30 subtests** — exact
    match to the PR's stated evidence.
  - PR-stated 2-file command (`test_vault_diagnostics.py
    test_bc_vault_settings.py`): 18 passed, 14 subtests — exact match.
  - Full unit suite: 675 passed, 10 skipped, 90 subtests (Δ +10 vs PR #56's
    665 = exactly the 8 new exact-identity tests + 2 new transport tests).
  - Full regression: `run_regression.py --ini tests/bc_regression.ini` →
    exit 0, VERDICT: PASS (7 scenarios / 8 PDFs).
  - ruff (F821, E4/E7/E9) on all 5 changed files: all checks passed.
  - bandit per-file vs the pre-image: vault.py / vault_transport.py /
    test_vault_transport.py 0 findings (unchanged); runner.py 1×B110
    (pre-existing, identical to base); new test file 11×B101 (asserts) +
    3×B105 (`synthetic-password`) — test-file baseline only, no secrets.
    Production files: zero new.
  - Deployment validation: **recorded skip** — not deployment-relevant (no
    Dockerfile / .dockerignore / BillCollector.sh / install_docker-image.sh /
    deploy_remote.sh / INI key / .env change; pure Python inside the existing
    runtime).
  S5 gate passed: user confirmed the deployment skip and proceeded
  (2026-10-31). Status: VALIDATED.
- S6 (2026-10-31, same session): CHANGELOG M1 entry stands as-is in the
  `[Unreleased] → Fixed` section (sanitized, public-safe). No README or
  CONTRIBUTING change: the operator-visible contract (`BW_API_URL`, item
  naming, optional TOTP) is unchanged, only the internal resolution path
  narrows. `doc/vault_transport.md` corrected (two edits, in tree, pending
  the S6 gate): (a) the "URL credentials, query strings, fragments, HTTPS and
  public targets are refused" line now distinguishes the base URL (still
  refuses query strings) from request URLs (endpoint query preserved, e.g. the
  item search query); (b) the stale "Exact item resolution and stable account
  identity are separate work" + "The diagnostics fix in upstream PR #11 is
  also needed" sentences (PR #11 already delivered; #48 now landed) replaced
  with the exact-id resolution description. S6 gate passed: user confirmed
  the docs (2026-10-31). S7 next: dev-commits (3 commits: code / test /
  doc — the doc commit now covers CHANGELOG.md + doc/vault_transport.md),
  push origin/dev, ff-only promote to main, sync_github.sh mirror, PR +
  issue close comments per the publication routine.
