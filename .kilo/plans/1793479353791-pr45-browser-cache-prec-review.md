# PR #45 review: preserve explicit Playwright browser cache across imports

> Status: AWAITING-DECISION (2026-10-31) — S1+S2 done: verdict approve with
> M1 (CHANGELOG entry separator) only; all PR code and tests apply as-is from
> head `93f71b2` (5 files byte-identical pre-images on `dev` + 1 clean-add
> test file; full diff applies strictly). Head moved mid-S1 (author merged
> current public main into the branch); reviewed head is the new `93f71b2`.

## PR metadata

- PR: s-t-e-f-a-n/BillCollector#45 "fix: preserve explicit Playwright browser
  cache across imports" (flowcool), head
  `93f71b29ca77818edf1e24a6ba8d90ed31b243e1` (fetched to `refs/pr/45`,
  matches `git ls-remote github`). The head **moved mid-S1**: first fetched at
  `5589c707d103a453128281a847b1ac0cf18ad7ad` (two fix commits atop the
  orphaned public tip `f26b2a9`; GitHub then showed 103 files / +223/−22928,
  `mergeable_state: unknown`), the author then pushed `93f71b2` "Align browser
  cache contribution with current public main" — a **merge commit** (parents
  `5589c70` + `3c950d7`) merging the current public `main` into the branch.
  Reviewed head = `93f71b2`: `mergeable: true`, `mergeable_state: clean`,
  real content **6 files +115/−6** against `3c950d7` (the 103-file view was
  the orphaned-tip STRIP artifact, resolved by the rebase).
- Issue: none (fix; no shared interface touched).
- Created 2026-10-30T11:37:15Z; last updated 2026-10-31T20:30:04Z (the
  rebase push, before S1's re-fetch).
- Local state at review time: Gitea `dev` = `origin/dev` = `eebb902`, Gitea
  `main` = `origin/main` = `22da847`, GitHub `main` = `3c950d7`. Working tree
  clean.
- AI disclosure present: "AI assistance: Codex prepared and tested this
  contribution."

## Verdict

**Approve with maintainer changes** — M1 (CHANGELOG entry separator) only;
all PR code and tests apply as-is from head (5 files byte-identical
pre-images on `dev`, the new test file is a clean add).

## Verified facts

1. Head stable at re-fetch: `refs/pr/45` = `93f71b29...` matches `ls-remote`;
   `mergeable_state: clean`; GitHub API reports 6 changed files +115/−6,
   matching `git diff 3c950d7..93f71b2`. S4 preflight re-checks via
   `git ls-remote github refs/pull/45/head`.
2. Base: the branch now aligns with the current public main `3c950d7` via the
   merge commit; the real delta is the 6-file diff above. The mid-S1 head
   move changed only the base (the two fix commits `e3fca5d` + `5589c70` are
   unchanged members of the new lineage; `git diff 5589c70..93f71b2` over the
   PR's own files is limited to the CHANGELOG placement adapting to the new
   `[Unreleased]` content).
3. Both claimed bugs verified in the pre-change code:
   - **Helper import overwrites the explicit cache**: old
     `apps/helpers/BillCollectorHelpers.py` set
     `CHROMIUM_PLAYWRIGHT_DIR = os.path.join(APP_DIR, "browser")` (hardcoded)
     and `os.environ["PLAYWRIGHT_BROWSERS_PATH"] = CHROMIUM_PLAYWRIGHT_DIR`
     **unconditionally** — importing the helpers after `billcollector.config`
     clobbered whatever the config set and ignored `BC_BROWSER_DIR`.
   - **Empty cache values defeat the fallback**: old `config.py` computed
     `BROWSER_DIR = _path("BC_BROWSER_DIR", ...)` =
     `Path(os.environ.get(name, str(default)))` — an **empty**
     `BC_BROWSER_DIR` yields `Path("")` (the cwd), and
     `os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", ...)` leaves an empty
     `PLAYWRIGHT_BROWSERS_PATH` untouched.
4. Pre-image vs Gitea `dev` `eebb902`: `apps/billcollector/config.py`,
   `apps/billcollector/redaction.py`, `apps/billcollector/runner.py`,
   `apps/helpers/BillCollectorHelpers.py` and `CHANGELOG.md` are
   **byte-identical** to the PR base (`3c950d7`) → hunks apply cleanly.
   `tests/test_bc_browser_cache.py` is a new file (absent in both base and
   dev) → clean add. The full 6-file diff passed `git apply --check` strictly
   on the clean dev tree (2026-10-31).
5. Code review (per file), behavior preserved vs changed:
   - `config.py`: `BROWSER_DIR = Path(os.environ.get("BC_BROWSER_DIR") or
     APP_DIR / "browser")` (empty → default) and `PLAYWRIGHT_BROWSERS_PATH`
     set only when unset **or empty** (was `setdefault`). Non-empty values
     are untouched in both cases.
   - `BillCollectorHelpers.py`: `CHROMIUM_PLAYWRIGHT_DIR =
     os.environ.get("BC_BROWSER_DIR") or os.path.join(APP_DIR, "browser")`
     (respects the override + empty fallback); the unconditional clobber
     becomes set-if-unset/empty. `CHROMIUM_PLAYWRIGHT_PROFILE` follows, so
     the legacy batch profile moves to `$BC_BROWSER_DIR/profile` when the
     override is set — documented blast radius (PR body + CHANGELOG); the
     Docker image is unaffected (`ENV PLAYWRIGHT_BROWSERS_PATH=/apps/browser`
     stays non-empty, `BC_BROWSER_DIR` unset in the Dockerfile).
   - `redaction.py` (additive): `launch_failure_record(error)` returns
     `failure_record("launch_persistent_context", error)` plus
     `error_type` (the exception class name, identifier-validated via
     `_METHOD_RE`, else `"Error"`) and `message` (a fixed allowlisted reason).
     The two sandbox banners (`Chromium sandboxing failed!`, `No usable
     sandbox!`) are recognized anywhere in the message (Playwright emits them
     in the multiline "Browser logs" section); every other marker matches the
     **first line only**; unrecognized first lines yield the fixed
     "Browser launch failed; unrecognized details omitted". No raw error
     text, call-log line or URL is retained. Pure addition —
     `failure_record`/`failure_category` are unchanged (all other call sites
     unaffected).
   - `runner.py`: the launch-failure log switches to
     `launch_failure_record(e)` (one call site + the import line); the
     `RunInterrupted` re-raise and the `return files_downloaded, True, None`
     abort semantics are unchanged.
   - `tests/test_bc_browser_cache.py` (new, 72 lines, pytest — consistent
     with the repo's pytest modules): 22 cases. 18 subprocess cases
     (2 import orders × 9 env combos of `PLAYWRIGHT_BROWSERS_PATH` ×
     `BC_BROWSER_DIR` incl. absent/empty/`"0"`) pin the precedence
     non-empty `PLAYWRIGHT_BROWSERS_PATH` > non-empty `BC_BROWSER_DIR` >
     `apps/browser`, and assert import-time creates no runtime/db directory;
     4 diagnostic cases: the launch-failure log carries the exception class
     + fixed reason without `SECRET_TOKEN`/`SECRET_PASSWORD`/`Call log`; an
     unrecognized first line never enters the record; both sandbox banners
     after the first line classify without proxy secrets. Synthetic markers
     only, no network, subprocess env strips host `BC_*`/`BW_*`/
     `PLAYWRIGHT_BROWSERS_PATH`.
   - `CHANGELOG.md`: new `### Fixed` entry at the top of `[Unreleased]`
     (above the #48 entry), sanitized wording, no issue ref (consistent with
     the no-issue PR).
6. Out-of-scope residual: the legacy `InitBrowser`
   (`apps/BillCollectorServices_pw.py:21-22`) still logs the raw launch
   exception (`logger.error(f"Error: {e}")`) — raw sandbox banners / proxy
   arguments can still leak there. Pre-existing, outside this PR's scope
   (daemon diagnostics + import precedence); follow-up candidate.
7. Process check (CONTRIBUTING.md): no issue ref — acceptable (fix, not a
   feature, no shared interface touched — noted); intended behavior +
   verification stated (reproduce commands with expected results); proof
   shipped (focused 22/22, regression 7 pairs / 8 downloads PASS, full suite
   657 passed / 6 skipped / 53 subtests on the author's tree, ruff +
   touched-runtime bandit pass); AI assistance disclosed (Codex); no secrets
   (synthetic markers); no new network exposure; no shared-interface change
   (no DB schema, control protocol, recipe contract or exit-code change —
   confirmed in the diff).
8. Cross-PR: open PRs are #45 (this) and #44 (C3 recipe method-chain
   validation) — both flowcool, base `main`. Batch-2 chain
   `#53 → #54 → #56 → #55 → #45 → #44` (user-confirmed 2026-10-30);
   #53/#54/#56/#55 DELIVERED → #45 is next in order. File overlap with #44:
   `CHANGELOG.md` only (expected; #44 closes the batch and its S1 pre-image
   check runs against the settled post-#45 tree).

## Risks

- Low overall: the precedence fix only narrows env handling (an explicit
  non-empty value always wins; empty → bundled default) and is pinned by 18
  subprocess cases across both import orders.
- The legacy batch profile location moves to `$BC_BROWSER_DIR/profile` when
  the override is set (was always `apps/browser/profile`) — intended,
  documented in the PR body and the CHANGELOG entry; the Docker image sets no
  `BC_BROWSER_DIR`, so container behavior is unchanged.
- M1 is cosmetic: the PR-head CHANGELOG entry lacks the blank line before the
  #48 entry that house style keeps between entries.
- No existing-suite surface affected: `tests/conftest.py` sets a non-empty
  `PLAYWRIGHT_BROWSERS_PATH` via `setdefault` (consistent with the new
  semantics) and deliberately does not redirect `BC_BROWSER_DIR`;
  `tests/test_bc_collection.py` saves/restores the value around its
  live-browser test.

## Integration plan (S4, on Gitea `dev`)

| File | Action | Note |
|---|---|---|
| `apps/billcollector/config.py` | apply from head | pre-image byte-identical to dev |
| `apps/billcollector/redaction.py` | apply from head | pre-image byte-identical to dev |
| `apps/billcollector/runner.py` | apply from head | pre-image byte-identical to dev |
| `apps/helpers/BillCollectorHelpers.py` | apply from head | pre-image byte-identical to dev |
| `tests/test_bc_browser_cache.py` | apply from head (new file) | absent in base and dev |
| `CHANGELOG.md` | **manual (M1)** | take the entry text as-is; insert at the top of the existing `[Unreleased] → ### Fixed` section **with the blank-line separator** before the #48 entry (the PR head omits it) |

Commits (dev-commits, one concern each, proposed in S7 — mirroring the PR's
own two fix commits):
1. `fix: preserve the explicit Playwright browser cache on import` —
   config.py + BillCollectorHelpers.py
2. `fix: classify sandbox launch banners without retaining private logs` —
   redaction.py + runner.py + test_bc_browser_cache.py
3. `doc: changelog — browser cache precedence and safe launch diagnostics` —
   CHANGELOG.md (M1 placement)

## Validation plan (S5, on the exact dev tree, `apps/.venv/bin/python`)

1. PR focused tests: `apps/.venv/bin/python -m pytest
   tests/test_bc_browser_cache.py -v` → 22 passed (PR claim: all 22
   browser-cache/diagnostic cases pass).
2. Companion module (PR's stated reproduce command pairs the two):
   `apps/.venv/bin/python -m pytest tests/test_bc_browser_cache.py
   tests/test_bc_redaction.py -q` → all pass.
3. Full unit suite: `apps/.venv/bin/python -m pytest tests/ -q` → all pass,
   expected baseline +22 new cases over the pre-integration tree (the PR
   claimed 657 passed / 6 skipped / 53 subtests on its own pre-#55 tree;
   S5 records the actual count).
4. Full regression: `apps/.venv/bin/python tests/run_regression.py --ini
   tests/bc_regression.ini` → exit 0, VERDICT: PASS (7 scenarios / 8 PDFs);
   PR claim: 7 pairs, 8 expected downloads, PASS, expected failing
   login/download cases preserve exit semantics.
5. `ruff` (F821, E4/E7/E9) + `bandit` on the changed files → nothing new
   beyond the known baseline (test-file B101 asserts only; no production
   findings).

## Deployment validation

**Assessed: not deployment-relevant → recorded skip, to be user-confirmed at
the S5 gate.** No `Dockerfile`, `.dockerignore`, `BillCollector.sh`,
`install_docker-image.sh` or `deploy_remote.sh` change; no INI-key or `.env`-
handling change. The change is Python-level env-var precedence (an explicit
non-empty `PLAYWRIGHT_BROWSERS_PATH` always wins — including the Docker
image's `ENV PLAYWRIGHT_BROWSERS_PATH=/apps/browser`), so image build and
container runtime behavior are unchanged.

## Out of scope

- PR #44 (last in the batch-2 chain).
- The legacy `InitBrowser` raw launch-error log
  (`apps/BillCollectorServices_pw.py:21-22`) — residual, follow-up candidate.
- Any Playwright browser installation or cache migration.

## Open questions

- None as of S2: the verdict + plan await user review (AWAITING-DECISION
  gate); S3 presents the exact proposal.

## Execution record

- S1 (2026-10-31, "continue pr #45" session): fresh S1 — no plan doc existed
  for #45 (the batch-2 chain reached #45 after the #55 delivery). Head first
  fetched at `5589c70` (two fix commits atop the orphaned public tip
  `f26b2a9`; 103-file dirty diff = orphaned-tip STRIP artifact,
  `mergeable_state: unknown`); **the head moved mid-S1** — the author pushed
  `93f71b2` (a merge of the current public main `3c950d7` into the branch);
  re-fetched and reviewed `93f71b2`: `mergeable_state: clean`, real content
  6 files +115/−6. Pre-image vs dev `eebb902`: 5 files byte-identical to
  base + 1 clean-add test file; the full diff applies strictly
  (`git apply --check`). Code review per file (precedence fix for both
  import orders, additive launch diagnostics with allowlisted fixed reasons,
  22-case test file); both claimed bugs verified in the pre-change code;
  legacy `InitBrowser` raw log flagged as out-of-scope residual. Process
  check PASS (no issue ref — fix, no shared interface; AI disclosed; no
  secrets; no network exposure). Cross-PR: only #44 open, CHANGELOG-only
  overlap. S1 gate passed (user confirmation, 2026-10-31).
- S2 (2026-10-31, same session): plan doc created (this file,
  AWAITING-DECISION); README + sequencing cross-references updated; doc-only
  commit to `origin/dev`. S3 next.
