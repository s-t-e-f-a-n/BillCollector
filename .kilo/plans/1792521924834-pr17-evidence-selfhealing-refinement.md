# PR #17 refined — redact retained browser evidence (head `170a366`) + post-attach self-healing improvements

> Status: INTEGRATING (2026-10-20) — verdict **approve**; S4 applied and
> verified on head `170a366` (re-confirmed unchanged by `ls-remote` on
> 2026-10-20T21:57Z); R1 + R2 implemented in the working tree; S5 evidence
> collected on the final tree (unit, full suite, ruff, bandit, live
> regression) — pending the user-gated S5 close-out and the S7 commits.
> This plan **supersedes**
> `.kilo/plans/1792475813001-pr17-browser-evidence-redaction-review.md`
> (review of old head `3967bf3`), which is kept as history.
>
> Refinement direction (agreed with the maintainer, 2026-10-20): accept the
> #10 redaction boundary exactly as the PR draws it; increase the likelihood
> of future self-healing with two maintainer-side commits on `dev` (R1, R2
> below) — not with a PR amendment.

## 1. PR metadata (re-based)

- PR [#17](https://github.com/s-t-e-f-a-n/BillCollector/pull/17) "fix: redact
  retained browser evidence", author `flowcool`, fixes #10.
- Head: `170a36648c49d7f1aa31d3b026636cd508f266e0` (moved since the last
  review, which was on `3967bf3`). Base: `main` @ `4508909`. Re-confirmed
  unchanged via `git ls-remote github refs/pull/17/head` on 2026-10-20
  (21:57Z) — the S4 preflight gate is satisfied.
- Commits (2, both substantive; the orphaned fork-base commit `53ae226`
  flagged in the old review — 70 deleted private paths — is gone after the
  author's rebase, so that skip-risk no longer exists):
  - `9b25621` "fix: redact retained browser evidence" (the original work).
  - `170a366` "fix: tighten retained evidence redaction": strips
    `;path-parameters`, keeps the sanitized inner URL of `blob:`/
    `filesystem:` URLs, limits the role-only fallback to textboxes, keeps the
    static value of submit/button/reset inputs as their name, classifies
    failures by exception type before message text, and keeps a fixed
    category plus the exception type name on download failures (log only).
- 10 files, +558/−30.
- **Pending author confirmations** (PR comment #6286178353): (1) `value` read
  for `input type=submit|button|reset` only; (2) `;path-parameters` removed
  and `blob:`/`filesystem:` inner kept sanitized. **Maintainer decision:
  confirm both** (Section 5).

## 2. What changed between `3967bf3` and `170a366` (all re-read from the diff)

| Area | New behavior at head |
| --- | --- |
| `sanitize_url` | Also strips `;path-parameters` per path segment; `blob:`/`filesystem:` recurse into the inner URL (origin + GUID retained, tokens dropped); scheme-only URLs (`javascript:`) collapse to `scheme:`; unparseable → `""` |
| Button names | `input type=submit/button/reset` maps to role `button`, accessible name = aria-label or the **static markup `value`** (never user-entered); editable inputs/textareas still never expose `value` |
| Role-only fallback | Limited to `textbox` (a nameless `get_by_role` candidate is emitted only for textboxes; buttons/comboboxes etc. without a name drop the candidate) |
| Failure records | `failure_category` checks exception **type** first (`TimeoutError` → timeout; `AttributeError/TypeError/ValueError/KeyError` → other) before message-text heuristics; download failures carry `failure: download (<category>)` plus the exception type name in a `logger.warning` (never persisted) |
| Tests | 4 PR modules: `67 passed, 5 subtests` → `75 passed, 9 subtests`; full suite `309/1 skipped/42` → `316 passed, 2 skipped, 46 subtests` (PR ran `LC_ALL=C`; the 2nd skip is host/locale-dependent — attributed to the gitcommit test, it did not reproduce on this host, see Section 8); new real-Chromium DOM-scan test with filled password/text/textarea + submit input |

Everything else in the old review (policy conformance per #10, schema
untouched, empty `CONSUMERS`, UI rendering of the structured error, F3/F4
behavior notes) carries over unchanged — the new diff does not touch those
sites.

## 3. Verdict

**Approve**, conditional on S5 re-verification on head `170a366` (the
old review's evidence was collected on `3967bf3` and is stale for the
numbers and the new behaviors) — S5 evidence collected 2026-10-20 (Section
8), user close-out pending. No maintainer-side code changes are needed
for integration; the manual step was the CHANGELOG entry (the PR ships
none; it is in place, Section 6).

## 4. Self-healing rationale (the compromise, for the record)

Condensed from the 2026-10-20 review discussion. Live scraping is untouched:
recipe dispatch, runtime element resolution, fill/click/expect_download,
screenshots, and downloaded files behave exactly as before; the DOM scan is
a recording pass, not the action mechanism.

What self-healing will have, per failed step, after PR #17:

- step number + method + fixed failure **category** (DB `PageStatus.error`);
- the failing step's **recipe** in template form (`locator_action`,
  `transform_step_to_json` never resolves `{{…}}` placeholders — no secrets);
- the page's **interactive elements** at that step: role, accessible name
  (aria-label → placeholder → label text; static label for submit/button/
  reset inputs), locator candidate, `rect`, `actionTypes`, sanitized link
  URL;
- the step **screenshot**, and on pause: numbered elements + page text +
  title + sanitized URL.

Why the three reductions are self-healing-neutral or positive:

1. **Locator names** — value-derived names were garbage for self-healing: a
   filled value changes every session, so it could never match in a later
   run. Static-attribute names are reproducible. An unlabelled textbox now
   yields a role-only candidate plus its `rect` and list position — the
   reproducible disambiguators.
2. **URLs** — URLs are never locators in the recipe contract (README
   recipe section: `locator`, `get_by_role/label/text/title/placeholder/
   test_id`), so dropping query/fragment/userinfo/path-params costs
   self-healing nothing.
3. **Failure detail** — the only real granularity loss (raw Playwright
   message gone). Priced in #10 item 4: those messages can embed filled
   values and signed URLs. R2 below recovers the one structural fact that
   matters (how many elements a strict-mode violation resolved to) without
   retaining any message text.

**Honest caveat, now addressed:** the failure record did not say whether a
strict-mode violation meant "locator stale" (0 matches) or "ambiguous"
(N>1 matches). R2 adds the count; R1 adds the static `id` the scan already
collects but currently discards, which is the strongest reproducible
disambiguator for unlabelled fields.

## 5. Decisions

- **D1 — confirm author point (1)** (submit/button/reset value as button
  name): within #10 — a static markup label, never user-entered data, and
  the only reproducible name most login buttons have; it strictly increases
  locator precision. The real-Chromium test proves editable inputs are never
  exposed.
- **D2 — confirm author point (2)** (path-parameter stripping; blob/
  filesystem inner): `;jsessionid=`-style parameters carry session state the
  same way query strings do; URLs are not locators, so self-healing loses
  nothing; the sanitized blob inner (origin + GUID) keeps the download
  record meaningful with no tokens.
- **D3 — R1/R2 placement**: maintainer-side commits on Gitea `dev` **after**
  PR #17 is integrated and validated (not a PR amendment). Self-healing
  evidence needs are the maintainer's design space per #10 ("your
  self-healing work"); the PR's security boundary stays minimal and
  reviewable.
- **D4 — R1 is metadata-only**: `id` is retained as an additive entry key;
  no locator candidate is generated from it, so the candidate shape (4
  `locatorType`s) stays stable until the self-healing design decides.

Suggested PR reply (maintainer posts at the integration stage):

> Both confirmed. (1) The static value of submit/button/reset inputs is a
> markup label, never user-entered data, and is the only reproducible name
> most login buttons have — keeping it as the accessible name fits the #10
> policy and strengthens the retained locator evidence. (2) Stripping
> `;path-parameters` is correct: they carry session state like query
> strings, URLs are never used as locators here, and keeping the sanitized
> inner of `blob:`/`filesystem:` retains what makes the download record
> meaningful without exposing tokens. We will integrate after re-verification
> on the head.

## 6. Integration plan (Gitea `dev`, file-level — S4 applied + verified)

All 10 files applied to the `dev` working tree (2026-10-20) and verified
content-identical to head `170a366` (`git diff refs/pr/17` per file; the 2
untracked new files by `diff` against `git show refs/pr/17:<file>`). R1 + R2
changes then applied on top (Section 7). Tree left dirty by design; S5
validates before any commit.

| File | Action |
| --- | --- |
| `apps/billcollector/redaction.py` | applied (new) + R2 |
| `apps/billcollector/pagestate.py` | applied + R1 |
| `apps/billcollector/runner.py` | applied (identical to PR) |
| `apps/billcollector/downloads.py` | applied (identical to PR) |
| `apps/billcollector/pause.py` | applied + R1 |
| `apps/BillCollectorServices_pw.py` | applied (identical to PR) |
| `tests/test_bc_redaction.py` | applied (new) + R1/R2 tests |
| `tests/test_bc_downloads.py` | applied (identical to PR) |
| `tests/test_bc_pause.py` | applied + R1 test |
| `tests/test_bc_runner.py` | applied (identical to PR) |
| `CHANGELOG.md` | done: the `### Fixed` entry below is in place under `## [Unreleased]` |

Pre-image check (verified at S4): the 8 modified files were byte-identical
between Gitea `dev` (`3b406f0`) and the PR base (`4508909`); the 2 new files
had no pre-image. Conflicts: none.

CHANGELOG entry (sanitized, in place):

- Retained browser evidence is now secret-safe in the Playwright runner and
  the legacy batch path (issue #10): input values are no longer used as
  locator names for editable fields (role-only candidates for unlabelled
  textboxes), the static label of submit/button/reset inputs is kept as the
  button name, link/download/page URLs are stored without query strings,
  fragments, path parameters or user info (`blob:`/`filesystem:` keep their
  sanitized inner URL), and step failures record the step, method and a
  fixed failure category (download failures additionally log the exception
  type) instead of raw exception text.

## 7. Post-attach refinements — implemented in-tree (two separate `dev`
commits at S7, after the PR integration commit)

Both refinements were implemented in the `dev` working tree on 2026-10-20,
on top of the applied PR files (Section 6). They land at S7 as two separate
commits in this order: (1) PR integration, (2) R1, (3) R2 — before the
promotion, so the promoted tree is exactly the validated one.

### R1 — retain the element `id` as additive metadata (implemented)

- `apps/billcollector/pagestate.py`: the JS scan already collects `id`
  (now line 141; was 137 pre-R1) but the entry dropped it. Entry
  construction now appends `id_attr = data.get("id", "")` /
  `if id_attr: entry["id"] = id_attr` (lines 270-272, after `actionTypes`,
  before the link `url`); the `set_interactive_elements` docstring key list
  carries the optional `id` (line 67).
- `apps/billcollector/pause.py` `_number_elements` (whitelist projection,
  def at line 55): `if entry.get("id"): item["id"] = entry["id"]`
  (lines 69-70).
- Tests (passing): `test_bc_redaction.py::
  test_id_is_retained_as_additive_metadata_only_when_present` (synthetic
  elements with/without `id` → `id` present only when non-empty; key order
  `role, name, locator, rect, actionTypes` unchanged for the first five
  keys) and `test_bc_pause.py::
  test_context_elements_carry_the_optional_id` (numbered pause elements
  carry `id`; elements without one gain no key).
- Security note: `id` is a static markup attribute, the same retained class
  as `aria-label`/`title`/`placeholder` (no live values). No candidate is
  generated from it (D4). Caveat for the record: a pathological portal could
  generate dynamic ids; metadata-only retention leaves the decision to the
  self-healer/user, never to auto-locator logic.
- Contract note (verified at implementation, 2026-10-20): the pause context
  is the documented AI-integration contract (`openwiki/architecture/
  shared-interfaces.md`, line 157: "complete, stable, and small" — payload
  requirements, not keys). An additive optional key preserves stability and
  serves completeness; the socket protocol in `control.py` is untouched, so
  no `PROTOCOL_VERSION` bump and no wiki page edit.

### R2 — retain the strict-mode resolved count in failure records
(implemented)

- `apps/billcollector/redaction.py` `failure_record`: after the category is
  computed, when `safe_category == "strict-mode"` and an error is given,
  `re.search(r"resolved to (\d+) elements", str(error))`; on match,
  `record["resolved_count"] = int(match.group(1))` (plus a docstring
  explaining the int-only retention). The record stays `{method, category}`
  plus the optional key; no message text is retained. Graceful: unparseable
  message → key omitted.
- Self-healing value: the count distinguishes "locator stale" (portal
  changed; rewrite needed) from "ambiguous" (pick among N candidates using
  name + `rect` + the new `id`) — the exact gap flagged in Section 4.
- Tests (passing, `test_bc_redaction.py`):
  `test_strict_mode_record_keeps_only_the_resolved_count` (message embedding
  the `SECRET` + "resolved to 3 elements" → `resolved_count: 3`, secret
  absent from the serialized record),
  `test_strict_mode_without_the_count_pattern_has_no_resolved_count`,
  `test_non_strict_mode_record_has_no_resolved_count`.
- Bandit: R1/R2 introduce no new finding — the only B105 in
  `test_bc_redaction.py` remains the `SECRET` fixture (line 28, F1); no B105
  in `test_bc_pause.py` (tree-wide re-scan, 2026-10-20).

## 8. Validation plan — S5 evidence collected on the final tree (2026-10-20)

Run from the repo root on the exact integrated `dev` working tree
(PR + R1 + R2, uncommitted; `bc.db` and the browser dir are native here, so
no temp-worktree procedure). Items marked [measured] were re-run on
2026-10-20T21:5x–22:1xZ on this tree.

- [measured] `apps/.venv/bin/python -m pytest tests/test_bc_redaction.py
  tests/test_bc_downloads.py tests/test_bc_pause.py tests/test_bc_runner.py
  -q` → `80 passed, 9 subtests passed` (the PR's `75 passed, 9 subtests`
  plus the 5 R1/R2 tests).
- [measured] `LC_ALL=C apps/.venv/bin/python -m pytest tests/ -q` →
  `322 passed, 1 skipped, 46 subtests passed` (the PR-only expectation was
  `316 passed, 2 skipped, 46 subtests` under `LC_ALL=C`; the second skip did
  not reproduce on this host — the gitcommit tests carry no skip logic and
  pass under `LC_ALL=C` here, so the PR-only tree measures 317/1 on this
  host; +5 R1/R2 tests → 322/1). The one skip:
  `test_bc_display.py:234` "real stack could not start on this host"
  (host-dependent, also skipped on the `dev` baseline).
- [measured] `apps/.venv/bin/python tests/run_regression.py --ini
  tests/bc_regression.ini` → `VERDICT: PASS`, 7 pairs all OK, exactly the 8
  expected files, exit 1 (mixed outcomes, as designed). Live spot-checks in
  the service log: `Step 15 failed (graceful, run continues): {'method':
  'click', 'category': 'timeout'}`, `Run aborted: Step 9 failed: {'method':
  'fill', 'category': 'timeout'}`, and the testdlfail pair —
  `Download failed with TimeoutError` (exception type in the transient
  warning) + `Step 15 failed to download: failure: download (timeout)`
  (fixed category, no raw message persisted).
- [measured] `apps/.venv/bin/ruff check apps tests` → `All checks passed!`.
- [measured] bandit 1.9.4 (temp `--target` install, venv untouched) on the
  6 touched modules → the 5 `main` findings only (B110 ×4, B608 ×1);
  tree-wide re-scan: no new finding from the PR or from R1/R2 — the only
  B105 in `test_bc_redaction.py` is the `SECRET` fixture (F1).
- Scope guard: no schema, control-protocol, recipe-contract, or exit-code
  change (shared interfaces untouched — no issue needed per CONTRIBUTING).

## 9. Carried-over review findings (line refs verified on the final tree,
2026-10-20)

- **F1 (nit):** new B105 on the synthetic `SECRET` test constant
  (`test_bc_redaction.py:28` on the final tree; line 24 at the PR head);
  consistent with the repo's existing test-fixture findings, left
  un-annotated.
- **F2 (out of scope, candidate follow-up issue):** residual raw-`e` log
  sites outside the agreed scope — `pause.py:86` ("Element scan failed:
  {type(e).__name__}: {e}" — a Playwright evaluate error can embed the page
  URL; transient warning, never persisted; was `pause.py:84` at the PR head,
  +2 from R1) and `runner.py:152` ("OTP re-fetch failed ({e})" — vault
  transport is a separate #10 topic).
- **F3 (info):** `processed_args`/`getattr` moved inside the try in both
  runners — argument-processing exceptions now become structured step
  failures; strictly more robust.
- **F4 (info):** the retry warning (`runner.py:517-519`) logs the
  `StepAbortError` — safe: the message is now fixed-format
  (`Step N failed: {'method': …, 'category': …}`).
- **F5 (observation):** the public mirror's history contains Gitea-private
  commits (`sync_github.sh` amends only the tip tree); pre-existing sync
  design, separate topic.

## 10. Risks

- Unlabelled textboxes keep a role-only candidate (agreed in #10); R1
  partially mitigates the disambiguation gap via `id` metadata.
- Operators lose raw step-failure detail in logs/UI by design.
- Blast radius: runner evidence only. Two-way door: a plain revert restores
  the previous behavior; no schema migration or data rewrite. R1/R2 are
  additive JSON keys — independently revertible.
- R2 depends on Playwright's message phrasing; the key is optional and
  omitted when the pattern does not match, so a Playwright wording change
  degrades to today's behavior, never to a leak.

## 11. Deployment validation

Not deployment-relevant: PR #17 and R1/R2 touch no `Dockerfile`,
`.dockerignore`, `BillCollector.sh`, `install_docker-image.sh`,
`deploy_remote.sh`, INI keys, or `.env` handling. **Recorded skip** — user
confirmation required before any promotion to `main` per the deploy skill;
dev integration is unaffected.

## 12. Out of scope

- F2 residual raw-exception log sites (follow-up issue if wanted).
- F5 mirror-history observation (sync-process matter).
- The self-healer itself: DB read path, recipe-rewrite proposal, UI
  integration — separate future design work.
- Generating locator candidates from `id` (deferred to that design, D4).
- Pause-context `page_title`/`page_text` (content-derived, length-capped;
  outside the agreed URL/locator/step-error policy).

## 13. Open questions

- Do we file the F2 follow-up issue (carried over from the old review)?
  Does not block integration.

## 14. Finalization log (2026-10-20, ~22:00–22:30Z)

- 21:57Z: `git ls-remote github refs/pull/17/head` → head still `170a366`;
  local `refs/pr/17` re-fetched (S4 preflight head gate satisfied).
- S4 application verified file-by-file: the 8 tracked files are
  `git diff refs/pr/17`-clean; the 2 untracked new files are
  content-identical to the PR head.
- R1 + R2 found already implemented in the working tree (previous session,
  after this plan was drafted); every hunk re-verified against the Section 7
  design, all 5 new tests included and passing.
- S5 evidence collected on the final tree (Section 8 `[measured]` items):
  4-module `80/9`, full suite `322 passed, 1 skipped, 46 subtests`, ruff
  clean, bandit no new findings, full regression `VERDICT: PASS` (7 pairs,
  8 files) with all live spot-checks of the new redaction behavior observed
  in the service log.
- Plan line refs corrected against the final tree: F2 `pause.py:86` /
  `runner.py:152`; F4 `runner.py:517-519`; R1 anchors renumbered to the
  post-implementation lines.
- R1 contract note closed: `openwiki/architecture/shared-interfaces.md:157`
  documents payload requirements only ("complete, stable, and small"), no
  element keys — no wiki edit, no `PROTOCOL_VERSION` bump.
- Remaining before S7: the user-gated S5 close-out (confirming the Section 8
  evidence and the Section 11 deployment skip), then the S7 commit sequence
  (PR integration → R1 → R2), the PR reply (Section 5 suggested text), and
  PR close.
