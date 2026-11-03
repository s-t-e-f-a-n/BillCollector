# PR #57 — S2 execution: verdict + integration plan (doc completion, doc commit, gate)

> For an implementation session ("continue PR #57"). S1 findings are complete in
> `.kilo/plans/1793730437637-pr57-incremental-keys-review.md` (Status: REVIEWING,
> "S2 pending at the user gate"). This plan records the three S2 decisions
> (user-confirmed in the 2026-11-03 planning session) and specifies exactly what
> the S2 session writes into the review plan doc, the doc-only commit + push, and
> the gate to S3. This session is doc-only: no source edits, no PR application.

## State at planning time (verified 2026-11-03)

- `dev` = `origin/dev` = `c377736`; Gitea `main` = `2485719`; GitHub `main` = `eb06503`
  (all match the S1 record; re-verify in the session).
- Working tree: clean except two untracked plan docs (the S1 session plan
  `1793728261986-pr57-incremental-keys-s1-review.md` and the review doc
  `1793730437637-pr57-incremental-keys-review.md`) — the S1 doc commit was never
  made; S2 commits both.
- PR head `24e8492601079ac28c2823357264fffcceefde3a`, 2 commits, fetched as
  `refs/pr/57` (inspection-only).
- The S1 session plan was never committed either; both docs ship in the S2 commit.

## Decisions (resolved 2026-11-03, user-confirmed)

1. **Verdict: approve with maintainer changes.** The PR matches the #50 agreed
   shape exactly (nullable `Download.source_key`, (task, key-attribute) scope,
   no backfill, no-op success, correction boundary documented); the process check
   passes. The one semantic conflict — the pre-C4 `run_result` success channel —
   is resolved by the already-agreed #24 C4 contract, which dev's outcome model
   must realize via a small additive adaptation. No public vocabulary change.
2. **Outcome value: reuse `duplicates_only`.** The #24 contract (public comment
   on GitHub issue #24, quoted in
   `.kilo/plans/completed/1793551618380-issue24-c4-c8-result-delivery-contract.md`
   lines 696-698) settled it explicitly: "an incremental run that skips all
   known keys is `duplicates_only` → `success`". S1's floated `all_items_known`
   value is dropped. README/UI/ntfy vocabulary stays unchanged
   (`duplicates_only` is already documented and healthy).
3. **Precedence: `proved_empty` wins over `all_items_known`** for a completed
   no-row run (both true only when `allow_empty` + `incremental` meet an empty
   listing). Rationale: the contract's `proved_empty` definition fits exactly
   (every collection action proved its listing empty); `duplicates_only` would
   be vacuous (zero download attempts). Pinned by a test.
4. **Nits: fix 2+3 in the integration commits, leave 1.** (2) Declare
   `all_items_known = False` in `_RunContext.__init__` (runner.py is already
   touched); (3) fix the double blank line in `doc/RECIPE_AUTHORING.md` (file is
   applied anyway). Leave (1) `known_source_keys` queried before option
   validation (harmless, as reviewed).

## S2 session tasks

### Task 0 — Preflight

- `git ls-remote github refs/pull/57/head` must equal `24e8492…` (if it moved:
  stop, report, re-run S1 — skill rule).
- `dev` / `origin/dev` / `github/main` tips unchanged (if `dev` moved: re-run the
  S1 pre-image checks and note the adaptation before writing the doc).

### Task 1 — Complete the review plan doc

File: `.kilo/plans/1793730437637-pr57-incremental-keys-review.md`. Changes:

1. Status line →
   `> Status: AWAITING-DECISION (date) — verdict (approve with maintainer changes) + integration plan complete; user gate before S3.`
2. New **Verdict** section (after PR metadata / before Verified facts, per the
   skill's section order): "approve with maintainer changes" + the rationale of
   Decision 1 (one paragraph: shape match, process pass, the single semantic
   conflict resolved by the agreed #24 contract, no public vocabulary change).
3. **Integration plan** section (currently "Filled in S2") → the per-file table
   and the maintainer-side changes M1–M4 below.
4. **Validation plan** section (currently "Filled in S2") → the S5 commands +
   expected results below.
5. **Risks** 1–2: mark resolved (Risk 1: contract reference per Decision 2;
   Risk 2: precedence pinned per Decision 3).
6. **Open questions**: replace with the three resolved decisions (one line each,
   with the contract citation for decision 2).

### Task 2 — Doc-only commit + push (dev-commits gate)

- Stage both untracked plan docs (S1 session plan + updated review doc).
- Propose one doc commit (draft message, user confirms per dev-commits):
  `doc: plans — PR #57: S1 findings + S2 verdict and integration plan (AWAITING-DECISION)`
- Push to Gitea `origin/dev`. No PR content, no public text, nothing reaches the
  GitHub mirror (`.kilo/` is stripped).

### Task 3 — Gate

Present verdict + integration plan to the user. Next session = **S3** (exact
proposal: files applied/skipped, the M1–M4 diffs, CHANGELOG merge, commit
split; user confirms as-is / with changes / declines → refusal branch).

## Integration plan content (to be written into the review doc)

### Per-file decisions (three-dot change set, 114 files)

| File | Decision |
|---|---|
| `apps/billcollector/collection.py` | apply + manual merge (keep-both in the options/validation block) |
| `apps/billcollector/db.py` | apply + manual merge (DDL + migration dict, keep both) |
| `apps/billcollector/downloads.py` | apply (PR hunks sit adjacent to dev C8 edits; keep both) |
| `apps/billcollector/runner.py` | apply PR hunks **except** the `run_result` hunk (superseded by M1/M2) + maintainer changes M1–M3 |
| `apps/recipes_playwright/recipe-pw-schema.yaml` | apply verbatim (clean) |
| `doc/RECIPE_AUTHORING.md` | apply + nit-3 whitespace fix (M4c) |
| `tests/test_bc_collection.py` | apply (mock `download_all` gains `keyed_save`) |
| `tests/test_bc_incremental.py` | apply (new) + adaptations M4a/M4b |
| `tests/test_bc_runner.py` | apply verbatim (green once M1–M3 land) |
| `CHANGELOG.md` | manual merge: append only the incremental-keys entry to `### Added` (the C3 entry in the PR diff already exists on dev, CHANGELOG.md:44) |
| `README.md`, `doc/RECIPE_METHODS.md` | skip (recommit noise only; dev ahead) |
| 102 comparison artifacts (private-path deletions) | skip, never apply |

`collection.py` merge detail: the merged allowed-name set is
`{"key_attribute", "max_items", "timeout_ms", "event_window_ms", "allow_empty",
"incremental"}`; keep dev's `allow_empty` validation + `if not keys: return []`
early return (L369-371, L389-390) and add the PR's strict-boolean `incremental`
check, the `source_key()` helper, the `keyed_save=False` parameter, the
`incremental and not keyed_save` rejection, and the incremental
`save_completed` branch — all verbatim from the PR hunks.

`db.py` merge detail: Download DDL becomes
`… source_identity TEXT, revision_sha256 TEXT, delivery_attempts INTEGER,
source_key TEXT);` and the migration dict gains both `"delivery_attempts":
"INTEGER"` (dev, already present) and `"source_key": "TEXT"` (PR).
`insert_download` and `known_source_keys` apply verbatim.

### Maintainer-side changes (exact intended shape)

**M1 — `runner.py` `derive_outcome` (runner.py:142).** Add keyword-only
`all_items_known: bool = False`; docstring gains the clause: a completed run
with no rows and no empty proof is `duplicates_only` when the incremental
collection verified every item known (#50, per the C4 contract on issue #24),
`failed` otherwise. Body tail becomes:

```python
    if empty_proven:
        return "proved_empty"
    if all_items_known:
        return "duplicates_only"
    return "failed"
```

(precedence per Decision 3; `HEALTHY_OUTCOMES` unchanged).

**M2 — `runner.py` `run_result` (runner.py:161).** Add keyword-only
`all_items_known: bool = False`, pass it through to `derive_outcome`;
docstring note. No other change.

**M3 — `runner.py` `_collection_actions` (runner.py:522-603).**
- `save_download(download, *, source_key=None)` hunk verbatim (the
  `key_kwargs` thread into `track_download`).
- Merged `download` closure (dev empty-proof accounting + PR incremental
  block; both kept):

```python
    def download(locator, options):
        # Empty-proof accounting (C4, issue #24): count the call before the
        # action so a raised (graceful-failed) action counts as ran, never
        # proven; only a completed empty result under allow_empty proves the
        # listing empty.
        ctx.collection_actions_ran += 1
        incremental = isinstance(options, dict) and options.get("incremental") is True
        if incremental:
            prefix = collection.source_key(options.get("key_attribute"), "")
            completed_keys.update(
                key[len(prefix):] for key in ctx.db.known_source_keys(ctx.task["id"])
                if key.startswith(prefix))
        records = collection.download_all(
            ctx.page,
            ctx.context,
            locator,
            save_download,
            options,
            completed_keys=completed_keys,
            keyed_save=True,
        )
        if (not records and isinstance(options, dict)
                and options.get("allow_empty") is True):
            ctx.collection_actions_proven += 1
        if incremental and not records:
            ctx.all_items_known = True
            logger.info("Incremental collection succeeded: all items known")
        return records
```

  (Edge: `allow_empty` + `incremental` + empty listing sets both flags; M1's
  precedence makes the outcome `proved_empty` — pinned by M4a.)
- Finalization (runner.py:1145, 1180-1183): pass
  `all_items_known=ctx.all_items_known` at the `run_result` call and the
  `derive_outcome` call (attribute direct, not `getattr`, per nit-2); the PR's
  success-log hunk verbatim (`if not files:` → "succeeded: all items known.").
- `_RunContext.__init__` (runner.py:210-220): add
  `self.all_items_known = False` beside `collection_actions_ran/proven` (nit-2).

**M4 — Test adaptations (maintainer-side).**
- M4a `tests/test_bc_incremental.py`: re-express the pre-C4 pinned
  `run_result` calls to the dev signature
  `run_result(completed, rows, empty_proven, pause_outcome, *, all_items_known)`
  (rows = run's Download rows, i.e. `db.list_downloads(run_id=…)` — never
  `ctx.files_downloaded`, which lacks `duplicate_of_id`):
  - `test_stable_keys_survive_restart_and_skip_only_known_items`:
    `run_result(False, ctx.files_downloaded)` →
    `run_result(True, self.db.list_downloads(run_id=self.rid), False)`
    (→ `new_documents` → `success`).
  - `test_all_known_is_explicit_success_without_a_fake_download`:
    `run_result(False, [], all_items_known=ctx.all_items_known)` →
    `run_result(True, [], False, all_items_known=ctx.all_items_known)`;
    re-express the pinned branch table to the C4 model (aborted/no rows →
    `failure`; aborted/committed row → `partial` → `failure`; `cancel` →
    `cancelled`; `timeout` → `needs_attention`; completed/no rows/
    all-items-known → `success`); final `run_result(False, [])` →
    `run_result(True, [], False)`. Add `derive_outcome` pins:
    `derive_outcome(True, [], False, all_items_known=True) == "duplicates_only"`,
    `derive_outcome(True, [], True, all_items_known=True) == "proved_empty"`
    (precedence), `derive_outcome(True, [], False) == "failed"`.
  - `test_published_pending_delivery_retains_key_and_retries_consumer`: state
    assertion `"published"` → `"failed"` (dev C8); the recovery/retry half is
    unchanged (dev re-delivers `failed` rows at startup).
- M4b `tests/test_bc_runner.py`
  `test_incremental_all_known_finishes_run_successfully`: keep as applied;
  recommended one-line addition asserting
  `self.db.get_run(1)["collection_outcome"] == "duplicates_only"` to pin the
  contract mapping end-to-end (S3 confirms).
- M4c `doc/RECIPE_AUTHORING.md`: remove the double blank line before
  "## Test without a real account" (nit-3).

### Validation plan (S5 executes on the exact dev tree, repo root, venv)

- PR's 6 test modules per the PR body's Evidence list (re-read from
  `GET …/pulls/57`): `apps/.venv/bin/python -m unittest <module> -v` each →
  expected counts OK, no skips. Includes `tests.test_bc_incremental`
  (17 tests / 17 subtests after M4a) and `tests.test_bc_runner` (incl. the
  all-known end-to-end test, green after M1–M3).
- Full regression: `apps/.venv/bin/python tests/run_regression.py --ini
  tests/bc_regression.ini` → exit 0, VERDICT: PASS (7 pairs / 8 files).
- `ruff check apps tests` → clean; bandit on the changed files → nothing new
  beyond the public baseline (4 medium).
- Deployment-process validation: **not deployment-relevant** (no Dockerfile,
  shell script, or runtime-config change) — record the skip in the doc; no
  Docker host needed.

## Failure modes

- PR head moved after S1 → diff new vs. reviewed head; non-empty → re-run S1,
  never integrate an unreviewed head.
- `dev` moved since S1 → re-run pre-image checks, rebase the hunks, record the
  adaptation in the doc.
- Doc commit rejected at the dev-commits gate → adjust message, re-propose.

## Out of scope

- S3–S7 (proposal/confirmation, selective integration, validation, docs,
  commit + push + PR close) — later user-gated sessions.
- PR #58 (phase b, separate lane). Any ZIP/`unpack`, C4/C8 behavior change,
  UI change, backfill, control-protocol or exit-code change.
- Source edits in this session (doc-only).
