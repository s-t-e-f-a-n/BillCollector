# PR #41 review: source notice identities and PDF revisions (issue #38)

> Status: VALIDATED (2026-10-30) — S5 all green on the exact dirty tree (dev
> `e0cab50` + the 10 uncommitted S4 files): 14/14 unit, 647 passed / 10
> skipped full regression, harness VERDICT: PASS (7/7 scenarios, 8 PDFs),
> 15/15 recipe validation, ruff clean, bandit baseline-identical, pypdf
> 6.21.2 verified in venv; deployment-process validation justified skip
> (no deploy-script change; pypdf via existing `Dockerfile:35` pip install)
> user-confirmed 2026-10-30. Awaiting S6 documentation.

## PR metadata

- Author: flowcool; head branch
  `flowcool:feature/upstream-notice-revisions-20261026`
- Head hash: `74421dd2ea3feac6cb290b611a7d62bbd4f43484` (stable at S1;
  `git ls-remote github refs/pull/41/head` matches the local `refs/pr/41`)
- Base: `main` @ `f26b2a9d04bd89b45260b5ba9b13e90418b912d5` (current public
  tip); the branch itself starts from public main `36a8d31` (post-#31),
  i.e. it **predates #32, #33, #34, #40** which are already in dev/main
- Issue refs: #38 (source notice identity + revision handling) — OPEN,
  explicitly a *"decision requested before code"*; source implementation
  `flowcool/BillCollector#64`
- Created 2026-10-26T14:25:23Z; updated 2026-10-29T21:42:54Z; 2 commits;
  state open; 97 files / +833 / −19459
- Local state at review: Gitea `dev` `a4ccc15` (clean, == `origin/dev`),
  Gitea `main` `61defd3`, GitHub `main` `f26b2a9`

## Verdict

**Approve with maintainer changes.** The core feature (source-scoped notice
identity + a conservative, versioned PDF object-graph revision digest) is
sound, self-contained, opt-in, backward-compatible, and well tested. It
cannot be applied as-is because the PR branched from `36a8d31`, which
predates #32/#33/#34/#40; four files need manual adaptation against current
dev, dominated by re-authoring the download-tracking path on #33's journal
staged-publication + crash-recovery pipeline. The two new shared interfaces
(the `notice_identity` recipe contract and the additive `Download` schema)
are S3 decision points per issue #38.

## Decision history (issue #38)

- **2026-10-27 (comment `6449978430`, recorded in
  `1793124431799-open-issues-plans-20261027.md`):** collector keeps byte-hash
  dedup; stable notice identity / revision handling **delegated to the
  archive layer**. PR #41 **HELD** until (1) #34 lands, (2) F10/C8
  delivery-state exposure is scheduled/done, (3) identity scope +
  metadata-vs-correction rule decided on the issue.
- **2026-10-29 (user, this session):** the HOLD is **revised toward
  integration**. The collector-side `notice_identity` + PDF revision digest
  (PR #41's approach) is accepted as the path forward, superseding the
  archive-delegation direction for the collector. Precondition (1) #34 was
  already delivered; precondition (3) is resolved by accepting PR #41's
  contract as the issue #38 interface; precondition (2) F10/C8 delivery-state
  exposure is **not yet done** and is carried as an **accepted risk** (the
  collector-side suppression is opt-in, additive, and does not weaken #33's
  crash-recovery contract).

## Verified facts

- Merge base of `refs/pr/41` and `github/main` is `36a8d31` (PR #31 delivery
  test commit). The branch carries the sanitized public tip re-committed as
  `d9362b3` (orphaned public-history commit, skill flag) plus exactly one
  feature commit `74421dd`. `d9362b3` is byte-for-byte the same artifact
  commit as PR #40's.
- The `d9362b3` diff vs the merge base is 88 files: the public CHANGELOG
  entry (already present in current `github/main` via the sanitized lineage)
  + 87 pure deletions of private agent-context files (`.kilo/` 49,
  `openwiki/` 32, `.vscode/` 2, `.github` 1, `.private`, `.openwikiignore`,
  `AGENTS.md`) — none present in current `github/main` → all comparison
  artifacts (fork-behind-base noise), **skipped, never applied**. This
  accounts for the −19459 deletion count. No candidate file under a
  protected path.
- Actual feature content (`d9362b3..74421dd`): 10 files, +828/−10:
  - new: `apps/billcollector/notice.py` (232), `tests/test_notice_identity.py`
    (326), `doc/NOTICE_IDENTITY.md` (109);
  - modified: `apps/billcollector/db.py` (+30), `downloads.py` (+100),
    `recipes.py` (+5), `runner.py` (+12),
    `apps/recipes_playwright/recipe-pw-schema.yaml` (+20),
    `apps/requirements.txt` (+1, pin `pypdf==6.21.2`), `CHANGELOG.md` (+3).
- Pre-image / applicability check of each base→`74421dd` hunk against Gitea
  `dev` `a4ccc15` (via `git apply --check`):
  - **clean**: `notice.py`/`test_notice_identity.py`/`NOTICE_IDENTITY.md`
    (absent in base and dev → clean add), `runner.py` (both call sites match
    the pre-image), `recipe-pw-schema.yaml`, `requirements.txt`;
  - **manual adaptation required**: `db.py`, `downloads.py`, `recipes.py`,
    `CHANGELOG.md`.
- dev moved since the PR base via, at least: `78ed5f9` (#33 staged
  publication + crash recovery — `db.py`, `downloads.py`, `runner.py`),
  `cfb7875` (#34 daemon date variables — `db.py`, `recipes.py`, `runner.py`),
  `b01be29` (#32 Chromium sandbox — `runner.py`), `df3ec4b` (#40
  replacement_calendar — `runner.py`, `recipe-pw-schema.yaml`). All four are
  in `origin/dev` **and** in `github/main` `f26b2a9`; `origin/dev` and
  `github/main` are byte-identical for `downloads.py` (post-#33).
- #40's `replacement_calendar` (a method that `notice.py::validate_notice_recipe`
  names as a valid download step) is already in dev — the feature's only
  cross-feature dependency is satisfied.

## Code review findings

Behavior is preserved for the legacy path and additive for the opt-in path:

- `apps/billcollector/notice.py` (new, self-contained, depends only on
  `pypdf` + stdlib):
  - `validate_identity`: `notice_identity` is `{query_parameters: [...]}`
    only; 1–16 unique, non-blank names ≤128 chars.
  - `source_digest(url, options)`: rejects non-http(s), authority userinfo,
    `blob:`, URL >16 KiB; requires each declared field to occur exactly once
    with a non-blank value; hashes `[source-v1, scheme, host, port, path,
    sorted fields]` → 64-hex `source_identity`. Undeclared fields (session
    tokens) are excluded. Generic `ValueError` on any failure.
  - `revision_digest(path)` → `_revision_digest`: `pdf-graph-v1` digest over
    the parsed object graph; size ≤20 MiB; refuses encrypted/empty docs;
    omits trailer `/ID`,`/Size`,`/Prev`,`/XRefStm`, Info `/CreationDate`,
    `/ModDate`, stream `/Length`; normalizes a single generated named-dest
    alias (`[A-Za-z]{3}_[A-Za-z0-9]{6}`) in a single-child name tree + its
    `/Limits` and matching `/Dest`/`/GoTo` refs; preserves sharing/cycles via
    an explicit DFS stack (`seen` map, `b"ref"` emission) with independent
    100,000-node and depth-100 limits; uses `StreamObject._data` (pinned
    dep) to avoid decompressing untrusted streams.
  - Security hygiene: `_reject_pdf_diagnostics` installs a logging filter on
    `pypdf*` loggers to drop warnings (which can embed raw PDF bytes) and
    rejects the document if any fired; no raw parser error escapes the
    boundary.
  - `validate_notice_recipe`: walks services/steps/nested/submit/phases;
    `notice_identity` is allowed only on a step whose methods intersect
    `{expect_download, download_all, replacement_calendar}`.
- `downloads.py`: `track_download` gains keyword-only `identity`; when set,
  routes to `_track_notice_download` (source digest + revision digest +
  `find_notice_revision` → duplicate suppresses publication and consumers;
  `_publish_unique` stages in a temp dir and atomically `os.link`s with
  ` (index)` suffixing on collision); when unset, routes to the renamed
  `_track_legacy_download` (unchanged legacy behavior).
- `db.py`: adds nullable `source_identity`, `revision_sha256` columns to
  `Download`; idempotent `PRAGMA table_info`-guarded `ALTER TABLE` migration
  + `CREATE INDEX download_notice_revision (task_id, source_identity,
  revision_sha256)`; `insert_download` gains keyword-only
  `source_identity`/`revision_sha256`; new `find_notice_revision` (matches
  `task_id`+identity+revision with `duplicate_of_id IS NULL`).
- `recipes.py`: imports + calls `validate_notice_recipe` in `validate_recipe`
  (same pattern as the existing `validate_login_recipe` / #34
  `validate_variable_recipe` guards).
- `runner.py`: `_collection_actions.save_download` and `_handle_download`
  build `identity_kwargs` from `step["notice_identity"]` and pass
  `**identity_kwargs` to `track_download`; the collection duplicate-filename
  guard is bypassed when `identity_kwargs` is set (opted-in collection steps
  permit equal filenames, per doc).
- `recipe-pw-schema.yaml`: adds `noticeIdentity` definition and a
  `notice_identity` property to the step and method-carrying step
  definitions, described as "Daemon-only … unsupported by the legacy batch
  runner".
- `requirements.txt`: pins `pypdf==6.21.2`.
- `tests/test_notice_identity.py`: 14 synthetic tests (no private data).
  Coverage: metadata-only regeneration suppresses re-publish + re-consume;
  corrections and distinct sources each keep their original; identical bytes
  across accounts are distinct; identity fields hashed and session tokens
  excluded (asserts no raw account/notice values retained); missing/ambiguous
  identity and malformed PDFs refuse with generic errors and leak no secret
  into the message or logs; named-dest alias vs meaningful label
  discrimination; non-text/metadata/attachment participation in revision;
  legacy additive migration without backfill; recipe-option gating on
  download steps; runner adapter; browser collection repeat + correction with
  equal filenames (intercepted loopback); long linked graphs accepted; deep
  direct nesting refused.

## Risks

- **Stale base / #33 pipeline (HIGH, integration).** The PR's
  `_track_notice_download` + `_publish_unique` target the **pre-#33**
  `downloads.py`. dev's `track_download` is #33's journal
  staged-publication + crash-recovery model (`staged_path`, `state`,
  `manifest.json`, `_publish`/`_deliver`/`_recover_locked`, subprocess
  recovery). The notice path must be **re-authored** on that pipeline, not
  copied. The PR's `db.insert_download` call shape (positional +
  `duplicate_of_id`/`source_identity`/`revision_sha256`) differs from dev's
  (`**record` + `state`/`staged_path`) and must be reconciled.
- **Shared interface not yet agreed (MEDIUM, process).** Issue #38 is open
  and a "decision requested before code" vehicle; the `notice_identity`
  recipe contract and the additive `Download` schema are exactly the
  interfaces it says need agreement first. Mitigation: opt-in + backward
  compatible + additive (nullable, no backfill, old engine ignores columns);
  author defers the decision to the maintainer and offers to adapt.
- **Behavioral coupling to #33 crash window (LOW).** The PR's doc states the
  existing publication/consumer/DB crash window is unchanged and there is no
   exactly-once consumer guarantee; the notice duplicate-suppression must not
   weaken #33's recovery semantics.
- **F10/C8 archive contract not yet delivered (ACCEPTED, MEDIUM).** The
  2026-10-27 #38 decision tied the no-duplicate-output claim to the archive's
  F10/C8 delivery-state proof, still an open maintainer lane. The 2026-10-29
  revision accepts the collector-side suppression now; the archive lane stays
  separate. The collector change is opt-in and must not weaken #33 recovery.
- **`pypdf` private attr (LOW).** `StreamObject._data` is a private API;
  mitigated by the `pypdf==6.21.2` pin and the "no stream decode" guarantee.

## Integration plan (per file)

Apply on Gitea `dev`, file-level (S4). Skip every `d9362b3` deletion under a
protected path and the stale PR #31 CHANGELOG line.

1. `apps/billcollector/notice.py` — **apply as-is** (new).
2. `tests/test_notice_identity.py` — **apply as-is** (new).
3. `doc/NOTICE_IDENTITY.md` — **apply as-is** (new).
4. `apps/requirements.txt` — **apply as-is** (`pypdf==6.21.2`); verify the
   pin matches the lock/venv and update any lockfile if present.
5. `apps/billcollector/runner.py` — **apply the two hunks** (clean); confirm
   against post-#32/#40 `runner.py`.
6. `apps/recipes_playwright/recipe-pw-schema.yaml` — **apply as-is** (clean).
7. `apps/billcollector/recipes.py` — **manual union**: add
   `from .notice import validate_notice_recipe` alongside #34's
   `validate_variable_recipe`, and add the `validate_notice_recipe` guard in
   `validate_recipe` next to the existing two guards.
8. `apps/billcollector/db.py` — **manual merge** with #33/#34: add the two
   nullable columns to the `Download` `CREATE TABLE`, extend the
   `PRAGMA table_info`-guarded migration, add `find_notice_revision`, and
   extend `insert_download`'s keyword-only args (merge with dev's
   `state`/`staged_path`).
9. `apps/billcollector/downloads.py` — **manual re-author** (dominant work):
   keep the legacy path = dev's current #33 `track_download`; add the
   `identity` keyword; implement the notice path by computing
   `source_digest`/`revision_digest`, looking up `find_notice_revision`, and
   routing a duplicate through the existing "audit row without another
   publication/consumers" branch, while a new source/revision stages through
   the #33 journal (`staged_path`/`state`, `_publish`/`_deliver`) so the
   crash-recovery contract is preserved. Preserve the observable test
   contract (duplicate flag, `saved_path`, consumer-once, no secret leak).
   The PR's `_publish_unique` (temp-dir + `os.link`) is **not** reused; its
   collision-suffixing intent maps onto #33's existing filename handling.
10. `CHANGELOG.md` — **manual merge**: fold the PR's `Added` entry into the
    existing `## [Unreleased]` (Keep a Changelog order).

## S3/S4 execution record (2026-10-29)

- **S3 gate:** user confirmed the proposal as-is → M1 (`notice_identity`
  recipe contract), M2 (additive `Download` columns + index), M3 (re-author
  on the #33 journal pipeline) all accepted.
- **S4 preflight:** `dev` clean at `c24d1b4` (== `origin/dev`); PR head
  `74421dd` unchanged vs S1; `git apply --check` of the six clean candidates
  re-verified against dev.
- **Applied from `refs/pr/41` head** (single `git apply` of the
  base→head diff for the clean set): `notice.py` (new), `runner.py` (2
  hunks), `recipe-pw-schema.yaml`, `requirements.txt` (`pypdf==6.21.2`),
  `doc/NOTICE_IDENTITY.md` (new), `tests/test_notice_identity.py` (new).
- **`db.py` manual merge** (per plan item 8): two nullable columns appended
  after `staged_path TEXT` in `CREATE TABLE Download`; the two names added to
  the existing `PRAGMA table_info`-guarded migration dict;
  `download_notice_revision` index created after the loop;
  `insert_download` keyword-only `source_identity`/`revision_sha256`
  (INSERT 11→13 columns); `find_notice_revision` added after
  `find_download_by_sha`.
- **`recipes.py` manual merge** (plan item 7): `validate_notice_recipe`
  import + `invalid notice identity contract` guard beside the login/variable
  guards.
- **`downloads.py` re-author** (plan item 9 / M3): `track_download` gains
  keyword-only `identity`; `notice.source_digest` runs **before staging**
  (unidentifiable sources fail with no journal entry); `notice.revision_digest`
  runs on the staged document after the sha; the record carries
  `source_identity`/`revision_sha256` and duplicates resolve via
  `find_notice_revision` into the existing audit-row branch (no publication,
  no consumers); staging/manifest/`_publish`/`_deliver`/journal cleanup are
  the unchanged #33 code. The PR's `_track_notice_download`/`_publish_unique`
  and RUN_DIR staging are **not** shipped.
- **Test adaptation** (maintainer-side, 2 lines): both output-dir assertions
  now filter to files (`[p for p in out.iterdir() if p.is_file()]`), house
  style from `tests/test_bc_downloads_recovery.py:100`, because the #33
  journal (`.billcollector/`) lives inside the output dir.
- **`CHANGELOG.md`:** PR's `Added` entry folded into `## [Unreleased]` with a
  trailing `(issue #38)` reference, matching the neighboring entries' style.
- **Environment:** `pypdf==6.21.2` installed into `apps/.venv` (env-only,
  not committed; no lockfile exists).
- **Smoke (not the S5 gate):** `pytest tests/test_notice_identity.py -q` →
  14 passed in 7.86s on the dirty tree, including the real-browser
  collection test (chromium 153.0.8010.12 verified in the venv).
- **Known edge (recorded, not fixed):** a row recovered through
  `_recover_locked`'s conservative manifest path is re-inserted with only the
  `_FIELDS` keys, so its identity columns stay NULL and a later regeneration
  of that one document republishes with a suffixed filename instead of being
  suppressed — conservative (no missed delivery, no data loss).

## S5 execution record (2026-10-30)

- **Preflight:** on `dev` at `e0cab50` (== `origin/dev`, the S3/S4 record
  commit); dirty set exactly the 10 S4 files; PR head `74421dd` unchanged
  (`git ls-remote github refs/pull/41/head` == local `refs/pr/41`).
- **Validated-tree fingerprint** (worktree `git hash-object` of the 10
  files, in this order): CHANGELOG.md `d311ea6`, db.py `c669fe7`,
  downloads.py `06dadd0`, recipes.py `c15fd6a`, runner.py `c5b4f55`,
  recipe-pw-schema.yaml `20904d5`, requirements.txt `4d13c37`,
  notice.py `23019be`, doc/NOTICE_IDENTITY.md `b3fa1b6`,
  tests/test_notice_identity.py `2ae7a51`.
- **PR unit tests:** `apps/.venv/bin/python -m pytest
  tests/test_notice_identity.py -q` -> 14 passed in 5.7s (incl. the
  real-chromium collection test).
- **Full regression:** `apps/.venv/bin/python -m pytest tests/ -q
  --tb=short` -> 647 passed, 10 skipped, 53 subtests passed in 499s; zero
  failures (dev baseline plus the 14 new).
- **Regression harness:** `apps/.venv/bin/python tests/run_regression.py
  --ini tests/bc_regression.ini` -> VERDICT: PASS — 7/7 scenario pairs OK
  (testhappy x3, testgraceful, testbadlogin, testempty, testdlfail; the
  three expected failures returned their expected `False`), "downloads:
  exactly the 8 expected file(s)", 8 test downloads cleaned up from
  `apps/Downloads`.
- **Recipe/schema validation:** `CheckRecipe` over all 15 bundled
  `recipe-pw__*.yaml` against the modified `recipe-pw-schema.yaml` ->
  15/15 OK (invoked with the `apps/` package root on `PYTHONPATH`; the
  helper's `from helpers import *` needs it).
- **ruff (F821, E4/E7/E9, ruff 0.17.0)** on the five changed app files +
  `notice.py` + the new test file -> all checks passed.
- **bandit** on the same files -> worktree identical to the HEAD baseline
  (B110 x1, B608 x2, all pre-existing); test-file B101 (assert) is the
  house test pattern.
- **pypdf:** `pypdf 6.21.2` imports in `apps/.venv` (pin installed at S4,
  env-only; no lockfile exists).
- **Deployment-process validation: justified skip, user-confirmed
  2026-10-30 at the S5 gate.** No `Dockerfile` / `.dockerignore` /
  `BillCollector.sh` / `install_docker-image.sh` / `deploy_remote.sh` /
  INI/`.env` change. The only runtime impact is the `pypdf==6.21.2` pin in
  `apps/requirements.txt`; `Dockerfile:35` already runs `pip3 install -r
  requirements.txt`, so the standard deploy rebuild installs it (pure-Python
  package, no wheels or build toolchain). The venv checks above prove the
  pin resolves and the full suite + harness are green under it. No Docker
  build/canary/smoke on the dev host (no Docker). Re-validation required if
  the tree moves before the S7 promotion.

## Validation plan (S5, on the exact dev tree, from repo root, venv)

- PR unit tests: `apps/.venv/bin/python -m pytest tests/test_notice_identity.py -q`
  → expected 14 passed (re-run after the S4 re-author; the re-authored
  notice path must keep the same observable contract).
- Full regression: `apps/.venv/bin/python -m pytest tests/ -q --tb=short`
  → all pass (PR reported 466 passed / 3 skipped / 53 subtests on its own
  base; expect the dev baseline plus the 14 new, no new failures).
- Regression harness: `apps/.venv/bin/python tests/run_regression.py --ini
  tests/bc_regression.ini` → exit 0 (VERDICT: PASS).
- Recipe/schema validation: run the CheckRecipe / schema validation path over
  all bundled recipes → 15/15 still validate (the new schema `definitions`
  must not break existing recipes).
- ruff + bandit on changed files → nothing new beyond the known baseline.
- `pypdf` import/availability in `apps/.venv` (pin installed).

## Deployment validation

**Recorded skip, user-confirmed at the S5 gate (2026-10-30).** Not
deployment-relevant for the code change: no `Dockerfile`, `.dockerignore`,
`BillCollector.sh`, `install_docker-image.sh`, `deploy_remote.sh`, or
INI/`.env` handling touched. The only runtime impact is the `pypdf==6.21.2`
pin in `apps/requirements.txt`; `Dockerfile:35` already runs `pip3 install -r
requirements.txt`, so the standard deploy rebuild installs it (pure-Python
package; venv-verified — import + full suite + harness green under it). No
Docker build/canary/smoke run on the dev host (no Docker). S7 may proceed on
this confirmation; re-validation required if the tree moves before
promotion.

## Out of scope

- Issue #38's broader ownership decision (collector vs archive revision
  authority) — the PR does not claim that resolution; it ships a conservative
  opt-in collector-side implementation.
- Crash-recovery semantics (#33) — unchanged; only the notice path is
  grafted onto it.
- The legacy batch engine — explicitly not implementing `notice_identity`
  (schema/doc state this); no backfill or historical conversion.
- Any change to consumer error handling, run results, scheduling, or
  financial import behavior.

## Open questions (S3 decision points)

Resolved 2026-10-29 at the S3 gate — user confirmed the proposal as-is:

- **M1 — recipe contract:** accepted as the issue #38 interface
  (`query_parameters`: 1–16 unique non-blank names ≤128 chars, on daemon
  `expect_download`/`download_all`/`replacement_calendar` steps only).
- **M2 — DB schema:** accepted (additive `source_identity`/`revision_sha256`
  + `download_notice_revision` index).
- **M3 — reconciliation approach:** confirmed — notice tracking re-authored
  on the #33 journal pipeline; the PR's pre-#33 `_publish_unique` is not
  shipped.
