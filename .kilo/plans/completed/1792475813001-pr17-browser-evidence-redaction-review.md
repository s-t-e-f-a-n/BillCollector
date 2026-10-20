# PR #17 review — fix: redact retained browser evidence

> Status: AWAITING-DECISION (2026-10-20) — verdict **approve**; all 10 files
> apply cleanly on `dev`; full evidence re-verified on head `3967bf3`.

## PR metadata

- PR: [#17](https://github.com/s-t-e-f-a-n/BillCollector/pull/17)
  "fix: redact retained browser evidence", author `flowcool`, fixes #10
  (retention policy agreed in the maintainer's #10 comment).
- Head: `3967bf3b1cff7ba5d166024503515d140a2692f4` (fetched as `refs/pr/17`).
- Base per GitHub: `main` @ `4508909128bf4082706ac4fa545a482f5e286c87`.
- Merge base (PR head vs `github/main` and vs Gitea `dev`): `7c83c7e`
  ("fix: docker: pin tzdata==2026.5").
- Local state at review: `dev` = `main` = `3b406f0`, `github/main` = `4508909`.
- PR commits (2):
  - `3967bf3` "fix: redact retained browser evidence" — the actual work,
    10 files, +347/−33.
  - `53ae226` "doc: plans: add the wave1-nas-deploy plan …" — **orphaned
    public-history commit**: an amended (sanitized) copy of Gitea's `baa4046`
    (14,923 deletions of `.kilo/`, `openwiki/`, `.github/workflows/`, …).
    It is the author's fork base (a sanitized snapshot of the mirror), not
    part of the contribution. **Flag: never integrate; it would delete
    maintainer-private files from `dev`.**
- Cross-PR: #17 is the only open PR; no dependencies.

## Verdict

**Approve.** The PR implements the retention policy agreed in #10 one-to-one,
keeps the SQLite schema and the locator-candidate structure, ships synthetic
proof for both the daemon runner and the legacy batch path, and every piece of
evidence in the PR body was re-verified on the exact head (below). No
maintainer-side code changes required; the only manual step is the CHANGELOG
entry (the PR ships none).

## Verified facts (re-run by the reviewer on head `3967bf3`, temp worktree)

1. **Policy conformance (#10, all five items):**
   - DOM scan no longer reads `el.value` (JS collection + Python side,
     `pagestate.py`); accessible-name chain is aria-label → placeholder →
     label text; an unlabelled textbox yields a **role-only**
     `get_by_role` candidate (name falls back to the role), never a
     value-derived name.
   - URLs: `sanitize_url` retains scheme + host (port, IPv6 bracketed) +
     path only; query, fragment and user-info are dropped. Applied to link
     hrefs (before persistence), download records (DB row, consumer payload,
     return record), and the pause-context `url`.
   - Step failures: `fail_step` and every `StepAbortError` message now carry
     `{"method", "category"}` with category in the fixed set
     {timeout, strict-mode, navigation, download, other}; no raw exception
     text anywhere in the step-failure, download-failure, or pause paths.
   - Schema untouched (`db.py` unchanged); `CONSUMERS` is empty, so no
     download consumer depends on full URLs.
   - Proof is synthetic: `tests/test_bc_redaction.py` uses a local fake page
     with a **filled, unlabelled password input** and an error raised after
     credential entry, against a **temporary SQLite** database, asserting the
     secret is absent from the serialized elements, the stored error, and the
     captured logs — for both `runner._process_step` and the legacy
     `BillCollectorServices_pw.process_step`.
2. **PR's four unit-test modules:** `67 passed, 5 subtests passed` —
   matches the PR body exactly.
3. **Full suite:** `309 passed, 1 skipped, 42 subtests` on this host
   (PR body: 307/2 — the delta is the host-dependent display-stack test
   `test_bc_display.py:234`; `dev` baseline is `301 passed, 1 skipped`,
   so the PR adds exactly its 8 new tests, no regressions).
4. **ruff 0.17.0** (venv; PR used pinned 0.16.9): `All checks passed!` on
   `apps tests`.
5. **bandit 1.9.4** (same version as the PR): `redaction.py` — 0 findings
   (PR claim holds). Tree-wide dev-vs-head diff: exactly **+1 B105 (Low)** at
   `tests/test_bc_redaction.py:24` (`SECRET = "synthetic-password-never-store"`)
   — a synthetic marker consistent with the repo's 29 existing test-fixture
   B105 findings; not a real secret.
6. **Full regression on the PR head tree:** `VERDICT: PASS` — all 7
   service/user pairs as expected, exactly the 8 expected files (exit
   semantics 1 = mixed outcomes, as designed). The run also showed the new
   redaction live: `Step 14 failed: {'method': 'click', 'category': 'timeout'}`
   and `failed to download: failure: download` in the service log.
   (Worktree needed the gitignored `bc.db` copied in and the browser dir
   symlinked; on the `dev` tree at the repo root both are native.)
7. **Pre-image check:** all 8 modified files are byte-identical between
   Gitea `dev` and the PR base — every hunk applies cleanly, no conflicts
   expected. The 2 new files have no pre-image.
8. **Shared-interface check:** the pause-context/step-error payload changes
   from free-form text to the structured record — exactly the shape agreed in
   the #10 comment (item 4). The UI (`ui/task_detail.py`) renders
   `PageStatus.error` as a (truncated) JSON string; no UI change needed.
   CONTRIBUTING process: issue referenced, behaviour + verification stated,
   proof shipped, AI assistance declared, no secrets, no new network
   exposure. All pass.

## Code review findings

- **F1 (nit, non-blocking):** the new B105 on the synthetic `SECRET` test
  constant. The repo convention leaves its 29 test-fixture B105s un-annotated,
  so leaving this one as-is is consistent; the PR's "no new finding versus
  the public baseline" line is imprecise by exactly this one Low.
- **F2 (out of scope, candidate follow-up issue):** two residual raw-`e` log
  sites outside the agreed step-failure scope:
  - `pause.py:84` "Element scan failed: {type(e).__name__}: {e}" — a
    Playwright evaluate error can embed the page URL; transient warning only,
    never persisted.
  - `runner.py:152` "OTP re-fetch failed ({e})" — `VaultAPIError` text;
    vault transport is an explicitly separate contribution topic per #10.
- **F3 (info, behavior note):** `processed_args`/`getattr` moved inside the
  try block in both runners. Argument-processing exceptions (e.g. a broken
  `VARIABLE_MAP` lookup) now become a structured step failure instead of
  propagating out of `_process_step`. Strictly more robust and consistent
  with the redaction intent; noted for the record.
- **F4 (info):** the retry warning (`runner.py:519`) logs `{e}` of the
  `StepAbortError` — safe now because every `StepAbortError` message is
  fixed-format (verified all raise sites).
- **F5 (observation, not a PR issue):** the public mirror's history contains
  Gitea-private commits (`sync_github.sh` amends only the tip tree):
  `github/main~1` (`baa4046`) adds `.kilo/plans/1792384312843-wave1-nas-deploy.md`
  and is reachable in the public repo history. Pre-existing sync design;
  flagged separately, unrelated to this PR.

## Risks

- Unlabelled textboxes keep a role-only locator candidate (less precise than
  a value-derived name) — agreed in #10; the DB is write-only and
  self-healing is not yet implemented, so there is no compatibility cost.
- Operators lose raw step-failure detail in logs/UI by design (step + method
  + fixed category retained).
- Blast radius: runner evidence only. Two-way door: a plain revert restores
  the previous behavior; no schema migration or data rewrite.

## Integration plan (Gitea `dev`, file-level)

| File | Action |
| --- | --- |
| `apps/billcollector/redaction.py` | apply (new) |
| `apps/billcollector/pagestate.py` | apply |
| `apps/billcollector/runner.py` | apply |
| `apps/billcollector/downloads.py` | apply |
| `apps/billcollector/pause.py` | apply |
| `apps/BillCollectorServices_pw.py` | apply |
| `tests/test_bc_redaction.py` | apply (new) |
| `tests/test_bc_downloads.py` | apply |
| `tests/test_bc_pause.py` | apply |
| `tests/test_bc_runner.py` | apply |
| `CHANGELOG.md` | manual: author a `### Fixed` entry under `## [Unreleased]` (the PR ships none) |
| commit `53ae226` (all 70 deleted private paths) | **skip** — fork-base artifact, never apply to `dev` |

Expected conflicts: none (pre-images verified identical). Suggested
CHANGELOG entry (sanitized):

- Retained browser evidence is now secret-safe in the Playwright runner and
  the legacy batch path (issue #10): input values are no longer used as
  locator names for unlabelled textboxes (role-only candidates instead),
  link and download URLs are stored without query strings or fragments, and
  step failures record the step, method and a fixed failure category
  instead of raw exception text.

## Validation plan (S5, on the exact integrated `dev` tree, from repo root)

- `apps/.venv/bin/python -m pytest tests/test_bc_redaction.py
  tests/test_bc_downloads.py tests/test_bc_pause.py tests/test_bc_runner.py
  -q` → `67 passed, 5 subtests passed`.
- `apps/.venv/bin/python -m pytest tests/ -q` → `309 passed, 1 skipped,
  42 subtests passed` (skip = host-dependent display-stack test).
- `apps/.venv/bin/python tests/run_regression.py --ini
  tests/bc_regression.ini` → `VERDICT: PASS`, 7 pairs, exactly 8 files.
- `apps/.venv/bin/ruff check apps tests` → clean.
- bandit (1.9.4) on changed files → nothing new beyond the +1 B105 test
  fixture (F1).
- Scope: recipe contract, DB schema, control protocol, exit codes untouched.

## Deployment validation

Not deployment-relevant: the PR touches no `Dockerfile`, `.dockerignore`,
`BillCollector.sh`, `install_docker-image.sh`, `deploy_remote.sh`, INI keys,
or `.env` handling. **Recorded skip** — user confirmation of this skip is
required in S5 before S7 may commit or push to `main`.

## Out of scope

- F2 residual raw-exception log sites (separate follow-up issue if wanted).
- F5 mirror-history observation (sync-process matter, not this PR).
- Pause-context `page_title`/`page_text` (content-derived, length-capped;
  outside the agreed URL/locator/step-error policy).

## Open questions

- Do we want a small follow-up issue for the F2 log-site residuals, or leave
  them? (Does not affect this PR.)
