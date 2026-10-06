# PR #11 Review — fix: keep sensitive vault request data out of diagnostics

Repo `s-t-e-f-a-n/BillCollector`, PR by **flowcool**, head `2e73e83` (5 commits),
base `main`, fixes issue #9. Review date 2026-10-05, against local Gitea state
`dev` = `0428cc2` / `main` = `ddd9639`, public mirror `github/main` = `80eeea9`.

## Verdict

**Approve.** The code changes are correct, minimal, and well tested. The only
blockers are mechanical: one CHANGELOG merge conflict (the PR was based on an
older empty `[Unreleased]` section) and fork-behind-base diff noise (18
apparently "deleted" private files that are not PR intent).

## Verified facts

- Merge base is `2f6952e`. The PR's first commit `38ff01b` ("doc: add
  CONTRIBUTING.md") is the orphaned Oct-4 sanitized public tip — a recommit of
  Gitea `4456d75`. The Oct-5 force-push of `github/main` to `80eeea9` replaced
  it, so `38ff01b` is no longer in public main's history.
- The 18 "removed" files (all `.kilo/*`, `.private/sync_github.sh`,
  `.vscode/*`) are a comparison artifact: they exist at merge base `2f6952e`
  (public tip still carried them before the sync strip took effect) and not at
  the PR head. Not PR intent. Verified harmless under either GitHub merge
  strategy — they are already absent from current public main `80eeea9`, and a
  3-way merge keeps the deletions.
- Real PR content is 6 files: `apps/BillCollector.py` (+11/−9),
  `apps/helpers/BillCollectorHelpers.py` (+4),
  `tests/test_vault_diagnostics.py` (+212, new), `CHANGELOG.md` (+8),
  `CONTRIBUTING.md` (+72, new), `README.md` (+1/−1).
- `CONTRIBUTING.md` in the PR is **byte-identical** to Gitea `4456d75`; the
  README pointer line (line 59) already exists in Gitea. Both merge as
  no-conflict (identical content on both sides).
- Since the merge base, Gitea touched only `CHANGELOG.md` (b0297ae) and
  `README.md`/`CONTRIBUTING.md` among the PR's files → the **only conflict is
  CHANGELOG.md**: the PR assumes an empty `## [Unreleased]`, Gitea already has
  `### Changed` + `### Removed` entries there.
- Pre-images of all three code files match the current Gitea dev state
  byte-for-byte (`vault_request` BillCollector.py:88-109,
  `setup_logging` helpers:66-69) → the code hunks apply cleanly.

## Code review findings

1. **`vault_request` (BillCollector.py:88-109)** — except clause simplified from
   `(ConnectionError, Timeout, RequestException)` to `RequestException`:
   behavior-identical (the old tuple was redundant; both are subclasses).
   4xx `VaultAPIError` keeps the status, drops `response.text`; 5xx warning
   drops the body; the final exhaustion error drops the URL. Retry warnings
   keep the exception **class** (`network error (ConnectTimeout)`) — a bad
   `BW_API_URL` stays distinguishable from an outage. Timeout (10 s), 3
   attempts, backoff `2, 4`, final-4xx semantics all preserved.
2. **`bitwarden_api_check_status`** — `logger.debug(content)` (full status body
   dump: account email + server URL) replaced with a constant string. Correct.
3. **`post_json`** — unexpected-status error logs the status code only (202
   path covered by test).
4. **`WebRetriDoc`** — locked/failed vault status now logs its parsed state
   (`Vault API status: locked` / `check failed (success is not true)`) before
   `sys.exit(1)`. Restores debuggability that the body removal would otherwise
   cost. The body itself stays unlogged (it holds account identity) — correct.
5. **`setup_logging` (helpers:66)** — `logging.getLogger("urllib3").setLevel(
   logging.CRITICAL + 1)` placed **before** the idempotence guard, so every
   call re-applies it. Covers the `urllib3.*` hierarchy (children inherit).
   All three entry points that log call `setup_logging` (BillCollector.py:311,
   CheckRecipe:81, CreateRecipe:348). No collateral loss: the app's only
   urllib3 traffic is the vault API (nslookup is DNS; Playwright has its own
   network stack). Nit (optional): `urllib3_logger.disabled = True` is more
   idiomatic than level 51.
6. **Tests (tests/test_vault_diagnostics.py, 11 tests)** — solid. Assert the
   synthetic marker and the URL are absent from console, file, and exception
   strings; one test drives a **real** loopback HTTP server through
   `setup_logging` in both debug modes (proves the urllib3 suppression, not
   just the app-level changes); retry/backoff/TOTP behavior pinned exactly
   (`sleep` called with 2 and 4, 400→"No TOTP"→None without retry, 403→exit 1).
   Root-logger state is saved/restored. The
   `hasattr(collector, "vault_http_request")` branches are deliberate
   forward-compat with PR #13 — the suite passes whichever of #11/#13 lands
   first. No secrets in the tests (synthetic markers, 127.0.0.1, port 0).
7. **Residuals (out of scope, noted only)** — `Service {service_user} started.`
   (BillCollector.py:242) still logs the account identity per run, and
   `is_domain_local_ip` logs the vault hostname on DNS failure. These are
   run-tracking/config logs, not request diagnostics — outside issue #9's
   scope, but the identity is the same data the PR removes from request
   logging. No credential logging found in `BillCollectorServices_pw.py`.
8. **Process** — AI assistance disclosed in the PR description and commit
   trailers (per the CONTRIBUTING.md AI rule); issue #9 referenced;
   validation evidence (11 unit tests, regression harness `VERDICT: PASS`,
   ruff/bandit baseline) is specific and reproducible.

## Risks

- **Diagnostics loss:** a final vault failure no longer names the failing
  endpoint (URL removed from the exhaustion error). Accepted trade-off per
  issue #9 — status + exception class remain. Do not "fix" by re-adding the
  path; it contains the vault item name (identity).
- **urllib3 suppression is per-`setup_logging` call:** an entry point that
  never calls `setup_logging` would not get it. Currently all entry points do;
  note this when adding new ones.
- **CHANGELOG conflict on a direct GitHub merge** (see integration step 2).

## Integration plan (Gitea-first, per deploy skill)

1. On Gitea `dev`, apply the three code files from PR head `2e73e83`:
   `apps/BillCollector.py`, `apps/helpers/BillCollectorHelpers.py`,
   `tests/test_vault_diagnostics.py`. Hunks verified to apply cleanly
   (pre-images byte-identical to dev). Skip `CONTRIBUTING.md` and `README.md`
   (already present, identical).
2. `CHANGELOG.md`: add a `### Fixed` subsection under the existing
   `## [Unreleased]` with the PR's two bullets (vault diagnostics; urllib3
   suppression). This is the manual resolution of the only conflict.
3. Validate (repo root, from the venv):
   - `apps/.venv/bin/python -m unittest tests.test_vault_diagnostics -v`
     → expect **11 OK**
   - `apps/.venv/bin/python tests/run_regression.py --ini tests/bc_regression.ini`
     → expect 7 scenarios / 8 PDFs, `VERDICT: PASS` (mock portal, port 8787)
   - ruff (F821, E4/E7/E9) and bandit on the changed files → no new findings
     beyond the known baseline (B608 dynamic SQL table names, B104 UI bind)
4. Commit on `dev` (use the dev-commits skill for the commit suggestion).
5. GitHub PR handling — maintainer decision (open question):
   - (a) merge on GitHub for the public record: safe (3-way merge keeps the
     sanitized state), but the orphaned `38ff01b` re-enters public history and
     the next mirror sync overwrites it; or
   - (b) **recommended:** keep the PR open, let the change reach GitHub via the
     normal promote + `sync_github.sh` mirror, then close/merge the PR.
     Keeps public history canonical.
6. Ordering vs PR #13 (`vault_http_request`): no dependency — #11's tests are
   written to pass in either merge order.

## Open question

- GitHub PR handling: merge-on-GitHub vs Gitea-first-then-close
  (recommendation: Gitea-first). Code outcome is identical either way.

## Out of scope

- PRs #12, #13, #14, #15 (separate reviews); issue #10 (DOM/SQLite retention);
  the residual identity logs in `Service ... started.` (would be a follow-up
  issue, not this PR).
