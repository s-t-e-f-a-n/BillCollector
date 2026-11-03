# PR #57 review — opt-in incremental download keys

> Status: VALIDATED (2026-11-03) — S5 validated the applied tree (all checks
> green, one M4a signature fix, deployment skip user-confirmed); S6
> documentation confirmed (2026-11-03): CHANGELOG entry kept verbatim,
> README/CONTRIBUTING unchanged per the S3-confirmed plan; S7 (commit +
> push + PR close) next session.

## PR metadata

| Field | Value |
|---|---|
| PR | [#57](https://github.com/s-t-e-f-a-n/BillCollector/pull/57) "feat: add opt-in incremental download keys" |
| Author | flowcool |
| Head | `24e8492601079ac28c2823357264fffcceefde3a` (`flowcool:feature/upstream-incremental-6z1ew`) — verified unchanged since planning (fetched 2026-11-03 as `refs/pr/57`) |
| Base (labeled) | `main` @ `eb06503dcd56da70d9677d2910a51c9dc486442a` |
| Actual fork point | sanitized copy of public `26377b0` (see Verified facts) — 26 commits behind `eb06503` |
| Issue refs | #50 phase (a) (agreed shape: maintainer comment `6560325930`); phase (b) is PR #58 |
| State at review | open, not draft, 2 commits, GitHub stat 114 files +452/−25665 (fork-behind-base noise, explained below) |
| AI disclosure | "AI-assisted implementation and verification with Codex, under my responsibility." |
| Claimed evidence | 6 test modules: 132 passed + 17 subtests, no skips; `ruff check apps tests` clean; isolated legacy regression `tests/run_regression.py --ini tests/bc_regression.ini --keep-downloads` → VERDICT: PASS (7 pairs / 8 files); Bandit 1.9.4: 4 medium, identical to public baseline; no vault/provider/production access. Recorded as **claimed** — S5 re-runs on the dev tree. |

Local state at review (2026-11-03, re-verified by fetch):

| Ref | Hash |
|---|---|
| Gitea `dev` = `origin/dev` | `c37773656a07ee3ce8c044747610335a832ed976` |
| Gitea `main` = `origin/main` | `2485719ecf1192a3e9ec8e86f4a0b1eae003c51f` |
| GitHub `main` | `eb06503dcd56da70d9677d2910a51c9dc486442a` (= PR base label) |

## Verdict

**Approve with maintainer changes** (2026-11-03, user-confirmed).

The PR matches the #50 agreed shape exactly (nullable
`Download.source_key`, (task, key-attribute) scope, no backfill, no-op
success, correction boundary documented) and the process check passes.
The one semantic conflict — the pre-C4 `run_result` success channel — is
resolved by the already-agreed #24 C4 outcome contract, which dev's
outcome model realizes via a small additive adaptation (M1–M3 below); no
public vocabulary change.

## Verified facts

1. **Merge base** `df634cccadd5c99a49f0c4bee9abfe3629cffd53`
   ("test: cover daemon recipe method-chain validation (C3, issue #27)") —
   27 commits behind `github/main`.
2. **PR commits** (`df634cc..refs/pr/57`):
   - `4a9bffc46015b1c6e36d0bf16b0de2b8634265cb`
     "doc: method-chain contract, README validation note, changelog (C3, issue #27)"
     — **orphaned public-history recommit**: a recommit of public commit
     `26377b0` (same subject, an ancestor of `github/main`). Its public files
     are byte-identical to `26377b0`; the only difference is the deletion of
     102 maintainer-private files (`.kilo/`, `.private/`, `.vscode/`,
     `openwiki/`, `AGENTS.md`, `.openwikiignore`,
     `.github/workflows/openwiki-update.yml`). The author's branch is based on
     a sanitized copy of the public tip from the `26377b0` era; the claimed
     baseline hash `4a9bffc4…` is the recommit itself. This single commit
     accounts for the −25665 deletions and most of the 114-file stat.
   - `24e8492` "feat: add opt-in incremental download keys" — the feature
     commit: 10 files, +419/−18 (the ground-truth change set).
3. **Three-dot change set** (`df634cc...24e8492`): 114 files = 102 deletions
   (all maintainer-private paths, all already absent from the current
   `github/main` tip → comparison artifacts) + 12 candidates.
4. The recommit's `README.md` / `doc/RECIPE_METHODS.md` changes (present in
   the three-dot diff) are already contained in `dev` via the shared public
   lineage; `dev` is strictly ahead (C4/C8 docs). Nothing to apply from those
   two files.
5. Context (not a PR finding): the public mirror's *history* predates the
   tip-level sanitization — private paths exist in public trees up to and
   including `26377b0`, and are absent from the `eb06503` tip. Pre-existing
   mirror state; the PR changes nothing about it.

## File classification (three-dot diff, 114 files)

### Candidates (12) — per-file pre-image state vs. Gitea `dev`

Patch-application check = `git apply --check` of the per-file
`4a9bffc..24e8492` hunk set against the clean `dev` tree.

| File | PR change | `dev` pre-image | Hunk application on `dev` |
|---|---|---|---|
| `apps/billcollector/collection.py` | M | DIVERGED (dev C4 `allow_empty` in the same options/validation block) | **conflict** |
| `apps/billcollector/db.py` | M | DIVERGED (dev `delivery_attempts` in the same Download DDL + migration dict) | **conflict** |
| `apps/billcollector/downloads.py` | M | DIVERGED (dev C8 delivery state machine; adjacent edits in `_recover_locked`) | **conflict** (mechanical, adjacent) |
| `apps/billcollector/runner.py` | M | DIVERGED (dev C4 `run_result`/`derive_outcome` rewrite, `download()` empty-proof accounting, `_run_task` finalization) | **conflict** (semantic — see Risks 1) |
| `apps/recipes_playwright/recipe-pw-schema.yaml` | M | `dev` == pre-image | applies clean |
| `doc/RECIPE_AUTHORING.md` | M | `dev` == pre-image | applies clean |
| `tests/test_bc_collection.py` | M | DIVERGED (dev C4 tests elsewhere in file) | applies clean |
| `tests/test_bc_incremental.py` | **A** (new, 293 lines) | absent on `dev` | applies clean (2 test adaptations needed — see Code review, item 7) |
| `tests/test_bc_runner.py` | M | DIVERGED (dev C4/C8 tests elsewhere in file) | applies clean |
| `CHANGELOG.md` | M | DIVERGED | **conflict** (expected; manual merge of the `Added` entry) |
| `README.md` | (recommit noise only — no feature-commit change) | `dev` ahead | **skip** — nothing to apply |
| `doc/RECIPE_METHODS.md` | (recommit noise only — no feature-commit change) | `dev` ahead | **skip** — nothing to apply |

### Comparison artifacts (102) — skip, never applied

All deletions of maintainer-private paths (`.kilo/**`, `.private/sync_github.sh`,
`.vscode/**`, `openwiki/**`, `AGENTS.md`, `.openwikiignore`,
`.github/workflows/openwiki-update.yml`) introduced by the recommit `4a9bffc`.
Every path is already absent from the current `github/main` tip. They also fall
in the never-auto-apply categories (flagged paths); both rules point the same
way: skip.

### Flags

None beyond the above: no PR file *adds or modifies* a flagged path.

## Code review findings

Line refs are to the PR head (`git show refs/pr/57:<file>`). Behavior
preserved vs. changed, per file.

### 1. `apps/billcollector/collection.py`

- L347–349 `source_key(key_attribute, key)` → `f"{key_attribute}={key}"`.
  The key attribute is embedded in the persisted identity; the `=` separator
  makes attribute prefixes disjoint (e.g. `key=` never matches `key2=…`).
  Task scoping happens in the DB query, so scope is exactly **(task, key)**
  per the #50 decision.
- L352–355 `download_all` signature: additive keyword `keyed_save=False`.
- L367–378 options: `incremental` added to the allowed-name set; strict
  boolean check (L373–375, `1`/`"yes"`/`None` rejected); `incremental and
  not keyed_save` → `CollectionError("incremental is not supported by this
  runner")` (L376–377) **before any browser action** — the legacy runner
  rejection path. ✓
- L439–450: `pending` = initial snapshot minus `completed_keys`; the event
  budget counts only pending items; `save_completed` passes
  `save_download(download, source_key=…)` only when incremental, otherwise
  the legacy positional `save_download(download)` is unchanged. ✓
- Empty listing still fails closed under incremental: `_validate_snapshot`
  (L187–190, unchanged) raises on count 0 before the pending split, so
  "all items known" success requires a non-empty, valid list. ✓ (pinned by
  `test_invalid_lists_are_not_all_known_success`)
- Returns `records` (list of saved records); the runner treats "empty
  records + incremental" as the all-known signal.
- Nit: the runner's incremental branch (item 4) queries
  `known_source_keys` before option validation; a missing `key_attribute`
  yields the harmless prefix `"None="` and the error still fires. No action.

### 2. `apps/billcollector/db.py`

- L89 Download DDL: `source_key TEXT` — nullable, no default. ✓ additive.
- L154: `"source_key": "TEXT"` in the existing migration dict → same
  `ALTER TABLE Download ADD COLUMN` pattern as `revision_sha256` (PR #41).
  No backfill; old rows stay NULL. ✓ (#50 decision 2)
- L417–427 `insert_download(…, source_key=None)` keyword-only.
- L453–457 `known_source_keys(task_id)`: `SELECT DISTINCT source_key …
  WHERE task_id=? AND source_key IS NOT NULL` — task-scoped, old rows
  excluded. ✓

### 3. `apps/billcollector/downloads.py`

- `_recover_locked`: the publication-without-row recovery passes
  `source_key=metadata.get("source_key")` into `insert_download` — the key
  round-trips through `manifest.json` (the `record` dict is json-dumped in
  `track_download`). ✓ "Keys survive publication-journal recovery."
- `track_download(…, source_key=None)`: `record["source_key"]` is set only
  when not None, so it (a) lands in the journal manifest, and (b) flows into
  **every** `insert_download(**record)` call — including the duplicate
  audit-row path (`existing is not None` → `insert_download(**record,
  duplicate_of_id=existing["id"])`). ✓ "Keys survive duplicate-download
  audit rows."
- The default (no key) and `notice_identity` paths are untouched;
  `source_key` is orthogonal to the identity/revision mechanism — keys
  establish no revisions. ✓ (#50 decision 4)
- `dev` conflict (mechanical): dev C8 rewrote `_deliver` (failed state,
  attempt counts, notify), added `retry_delivery` + the `--retry` CLI, and
  changed the recovery state check; the PR's two hunks sit adjacent to those
  edits. Resolution = keep both.

### 4. `apps/billcollector/runner.py`

- L139–156 `run_result(aborted, files, pause_outcome, *, all_items_known=False)`:
  `not files_downloaded` → `"success" if all_items_known else "failure"`.
  **Semantic conflict with dev's C4 rewrite** (`run_result(completed, rows,
  empty_proven, pause_outcome)` + `derive_outcome`): on dev, an
  all-known incremental run commits no rows and holds no empty proof, so
  `derive_outcome` yields `"failed"` and the #50 no-op-success semantics
  break. The all-known channel must be re-expressed in the outcome model —
  the central S2 decision (Risks 1–2).
- L545–560 `download()` closure: computes the per-attribute prefix
  `source_key(key_attribute, "")`, merges `db.known_source_keys(task)` into
  the per-step `completed_keys` set, passes `keyed_save=True`; empty records
  + incremental → `ctx.all_items_known = True` +
  `logger.info("Incremental collection succeeded: all items known")`.
  Conflicts with dev's `collection_actions_ran/proven` accounting in the same
  closure (mechanical merge, keep both).
- L527–543 `save_download(download, *, source_key=None)`: keyword-only,
  additive; `key_kwargs` threaded into `track_download`. `dev` unchanged here
  (clean hunk).
- L1112–1115 `_run_task` result call: `getattr(ctx, "all_items_known", False)`
  — conflicts with dev's rewritten call site.
- L1158–1161 finalization log: success with no files →
  "succeeded: all items known." (clean hunk).
- `all_items_known` is not declared in `_RunContext.__init__` (set in the
  closure, read via `getattr` default). Works; initializing it in
  `__init__` would be cleaner. Nit.
- `completed_keys` is the existing per-step resume set; merging the
  DB-known keys into it composes with the operator-resume skip behavior.

### 5. `apps/recipes_playwright/recipe-pw-schema.yaml`

- L259–260: `incremental: {type: boolean}` in the `downloadAllMethod`
  options object (`additionalProperties: false`, not in `required`).
  Additive; `unpack` and any other option remain rejected. ✓

### 6. `doc/RECIPE_AUTHORING.md`

- New "Opt-in incremental downloads" section (L107–131). Carries the #50
  decision-4 declaration: "Opt in only when each `key_attribute` value is
  stable, unique, and identifies a notice that the portal never corrects in
  place … Portals that can correct notices, including Bourse Direct, must
  fetch originals and use `notice_identity` instead." ✓ present and
  sanitized. Also documents the `Download.source_key` format, (task,
  attribute) scope, no-backfill, journal retention, all-known success,
  empty/invalid-list failure, additive schema, and revert safety.
- Nit: double blank line before "## Test without a real account".

### 7. `tests/test_bc_incremental.py` (new)

17 tests / 17 `subTest`s (matches the claimed evidence), synthetic isolated
fixtures only (`portal.example`, `token=x`, temp DB + download dir) — no
secrets, no network. Coverage:

- key persistence for new and duplicate rows; task scoping; old-schema DB
  migration (column added, row kept, `source_key` NULL, `known_source_keys`
  empty);
- restart persistence, skip-only-known-items;
- all-known explicit success: no clicks, no fake row, log line, and pinned
  `run_result` branches (aborted/failing-file/cancel/timeout/default);
- correction boundary: known keys are not re-fetched for in-place
  corrections (file bytes unchanged, no new row); non-opt-in re-fetches the
  correction and does not query or seed keys;
- task/attribute scope independence; invalid lists fail closed;
- partial failure keeps only committed keys (retry re-clicks only the rest);
- old unkeyed download is re-acquired without backfill (the duplicate audit
  row carries the key); failed save commits no key;
- legacy callback stays positional; opt-in rejected before any click;
- strict boolean + `unpack` (ZIP) absent; `source_key` value/attribute
  preservation; schema accepts only booleans;
- journal recovery: publication-without-row restores the key from the
  manifest (row `consumed`); published-but-undelivered rows retain the key
  and retry the consumer.

**`dev` compatibility — two maintainer-side adaptations required on
integration:**

1. All `runner.run_result(…)` calls use the PR's pre-C4 signature; dev's is
   `run_result(completed, rows, empty_proven, pause_outcome)`. They must be
   re-expressed together with the Risks-1 adaptation.
2. `test_published_pending_delivery_retains_key_and_retries_consumer` asserts
   row state `"published"` after a consumer failure; dev C8 sets `"failed"`.
   The recovery/retry half of the test still holds on dev (dev re-delivers
   `failed` rows at startup); only the state assertion changes.

### 8. `tests/test_bc_runner.py`

- `test_incremental_all_known_finishes_run_successfully`: full `_run_task`
  with a pre-seeded `source_key` row, mock recipe driving the incremental
  action; asserts exit 0, `Run.result == "success"`, the log line, no
  re-download. It is a correct spec of the *intended* behavior on dev — but
  it cannot pass until the outcome-model adaptation (Risks 1) lands: as
  written on dev, the run has no rows for its `run_id` and no empty proof →
  `"failed"`. Keep it; the adaptation must make it green.

### 9. `tests/test_bc_collection.py`

- One signature fix: the mocked `download_all` accepts the new
  `keyed_save` keyword the runner now passes. Mechanical. ✓

### 10. `CHANGELOG.md`

- New `Added` entry: "Opt-in daemon `download_all` incremental keys scoped
  to each task and key attribute. … Keys do not detect corrections (issue
  #50)." Sanitized, accurate. Manual merge into dev's `## [Unreleased]`
  (Keep a Changelog order).

### Out-of-scope residuals (verified absent)

No ZIP extraction / `unpack`, no C4/C8/archive-protocol changes, no UI
changes, no backfill, no control-protocol or exit-code changes — matching the
PR body and the #50 phase split. `test_option_is_strictly_boolean_and_zip_is_
not_implemented` pins the absence.

## Process check (CONTRIBUTING.md)

| Requirement | Result |
|---|---|
| Issue referenced before code | ✓ "Refs #50"; shape agreed in #50 comment `6560325930` |
| Intended behavior + verification stated | ✓ Summary + Evidence with commands and expected results |
| Proof shipped | ✓ unit tests + isolated regression harness — **claimed**; S5 re-runs on the dev tree |
| AI assistance disclosed | ✓ (Codex, author responsibility) |
| No secrets in code/tests/artifacts | ✓ synthetic fixtures only |
| No new network exposure | ✓ none |
| Shared interfaces agreed in the issue first | ✓ `Download` schema + `download_all` recipe contract; PR matches the agreed shape exactly: nullable column, (task, key) scope, no default change, no-op success semantics, correction boundary documented |

## Cross-PR

Only other open PR: **#58** "Add opt-in bounded single-PDF ZIP extraction"
(flowcool, head `d97d7f324951d343e275db2b1b7cb01a5da0f6b6`, same base
`eb06503`). Phase (b) of #58's parent issue — disjoint part of the download
path (extraction after save vs. key skipping before save). Per #50, either
merge order is acceptable; tests passing in both orders are a plus, not a
requirement. No other open PR or lane touches this PR's diff.

## Risks

1. **Central — outcome-model conflict (dev C4, issue #24 lane). RESOLVED
   (S2, 2026-11-03).** The PR's `all_items_known` success channel is built
   on the pre-C4 `run_result`; on dev, an all-known incremental run (no
   new rows, no `allow_empty` proof) would derive `"failed"`. The channel
   is re-expressed in `derive_outcome`/`run_result` (M1/M2) reusing the
   existing healthy outcome `duplicates_only`, per the agreed #24 C4
   contract (public comment on issue #24, quoted in
   `.kilo/plans/completed/1793551618380-issue24-c4-c8-result-delivery-contract.md`
   lines 696-698): "an incremental run that skips all known keys is
   `duplicates_only` → `success`". No new outcome value; README/UI/ntfy
   vocabulary unchanged.
2. **`allow_empty` × `incremental` interaction (dev C4 × PR). RESOLVED
   (S2, 2026-11-03).** `proved_empty` wins over `all_items_known` for a
   completed no-row run (both true only when `allow_empty` +
   `incremental` meet an empty listing): the contract's `proved_empty`
   definition fits exactly (every collection action proved its listing
   empty), whereas `duplicates_only` would be vacuous (zero download
   attempts). Pinned by M1's order and the M4a `derive_outcome` pins.
3. C8 delivery-state test assertion (`"published"` → `"failed"`) — trivial
   adaptation, see item 7 above.
4. Mechanical conflicts in `collection.py` (shared options/validation
   block), `db.py` (shared DDL + migration dict), `downloads.py` (adjacent
   `_recover_locked`/`track_download` edits) — low risk, keep-both merges.
5. Nits (optional fixes on integration): `known_source_keys` queried before
   option validation; `all_items_known` not in `_RunContext.__init__`;
   double blank line in `RECIPE_AUTHORING.md`.
6. The recommit `4a9bffc` proves the author worked from a sanitized copy of
   an older public tip; all review/verification was done on that base
   (pre-C4/C8). Nothing in the PR leaked or re-introduced private content
   (it only deletes it on the branch), and integration never applies
   deletions from a PR head.

## Integration plan

Per-file decisions (three-dot change set, 114 files):

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

(precedence per decision 3; `HEALTHY_OUTCOMES` unchanged).

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
- Finalization (runner.py:1145, 1180-1183): a run-local `all_items_known`
  (initialized `False` beside `empty_proven`, assigned
  `all_items_known = ctx.all_items_known` at the `run_result` call where ctx
  is guaranteed) is passed to both the `run_result` and the finalize
  `derive_outcome` call (S3 refinement of the S2 wording: on the finalize
  path `ctx` can be `None` — vault-preflight/display failure after the Run
  row exists — so a direct attribute read would crash finalization; the local
  keeps the attribute direct where ctx exists, and is required for
  consistency: without the flag the all-known success path would end
  `result=success` with `collection_outcome=failed`); the PR's success-log
  hunk verbatim (`if not files:` → "succeeded: all items known.").
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
   contract mapping end-to-end (confirmed in S3, included in the proposal).
- M4c `doc/RECIPE_AUTHORING.md`: remove the double blank line before
  "## Test without a real account" (nit-3).

Commit split (confirmed as-is in S3, 2026-11-03; one concern per commit,
dev-commits skill):

1. `feat: opt-in incremental download keys with all-known success (issue #50)`
   — `collection.py`, `db.py`, `downloads.py`, `runner.py` (M1–M3),
   `recipe-pw-schema.yaml`, `tests/test_bc_collection.py`,
   `tests/test_bc_incremental.py` (M4a), `tests/test_bc_runner.py` (M4b).
2. `doc: incremental downloads — recipe authoring guide and changelog (issue #50)`
   — `doc/RECIPE_AUTHORING.md` (M4c), `CHANGELOG.md`.

### S3 result (2026-11-03)

- Preflight re-verified: PR head `24e8492…` unchanged
  (`ls-remote github refs/pull/57/head`); `dev` = `origin/dev` = `87c5443`
  (the S2 doc commit); working tree clean.
- The exact proposal (apply/skip list, manual merges, M1–M4 exact diffs,
  commit split) presented; **user confirmed as-is** at the S3 gate.
- One S3 refinement recorded above (M3 finalization: run-local
  `all_items_known` instead of a direct `ctx.` read at both call sites).
- Next session: S4 selective integration on `dev` (apply the confirmed
  content, leave the tree dirty for S5 validation).

### S4 result (2026-11-03)

- Preflight re-verified: PR head `24e8492…` unchanged
  (`ls-remote github refs/pull/57/head`); `dev` = `origin/dev` = `82297f1`
  (the S3 doc commit); since the S1 pre-image record (`c377736`) only doc
  commits landed, the pre-image checks remain valid; working tree clean.
- All 12 candidates applied to the working tree per the confirmed plan:
  verbatim hunks for `recipe-pw-schema.yaml`, `RECIPE_AUTHORING.md` (+ M4c
  whitespace fix), `test_bc_collection.py`, `test_bc_incremental.py`
  (new, + M4a), `test_bc_runner.py` (+ M4b one-line pin); keep-both manual
  merges for `collection.py`, `db.py`, `downloads.py`; `runner.py` = PR
  hunks except the superseded pre-C4 `run_result` hunk + M1–M3 (with the S3
  run-local finalization refinement); `CHANGELOG.md` incremental entry merged
  into `## [Unreleased]` → `### Added` (newest-first position, before the
  F06 entry). Skipped per plan: `README.md`, `doc/RECIPE_METHODS.md`
  (recommit noise, dev ahead), 102 comparison artifacts (private-path
  deletions, never applied).
- Sanity only (full validation is S5 on the exact dirty tree): `py_compile`
  on all 7 changed Python files OK; `ruff check apps tests` clean.
- Tree left dirty (uncommitted) for S5 validation, per S4.
- Next session: S5 validate/refine — PR's 6 test modules, full regression,
  bandit; deployment-process validation recorded as not deployment-relevant
  (skip, no Docker host needed) and user-confirmed there.

### S5 result (2026-11-03)

- Preflight re-verified: PR head `24e8492…` unchanged
  (`ls-remote github refs/pull/57/head`); `dev` = `origin/dev` = `2d4d32d`
  (the S4 doc commit; since the S3 pre-image record only doc commits landed,
  the S1 pre-image checks remain valid); dirty tree exactly the 9 modified +
  1 untracked file S4 applied.
- Validation on the exact dirty tree (repo root, venv), all green:
  - PR's 6 test modules via the PR body's pytest command
    (`BILLCOLLECTOR_BROWSER_TESTS=1 apps/.venv/bin/python -m pytest
    tests/test_bc_incremental.py tests/test_bc_collection.py
    tests/test_bc_runner.py tests/test_bc_downloads.py
    tests/test_bc_downloads_recovery.py tests/test_notice_identity.py -q`):
    **161 passed, 17 subtests passed, no skips** (after the S5 fix below).
    Note: `test_bc_downloads_recovery` and `test_notice_identity` are
    pytest-style (fixtures `tmp_path`/`monkeypatch`, parametrize); they
    collect 0 tests under `python -m unittest`, so the PR body's pytest
    command is the S5 vehicle for the full 6-module set.
  - Full regression: `apps/.venv/bin/python tests/run_regression.py --ini
    tests/bc_regression.ini` → exit 0, **VERDICT: PASS** (7 pairs / 8 files).
  - `ruff check apps tests` → clean (exit 0).
  - Bandit on the 4 changed app files → identical findings to the
    pre-integration HEAD (`2d4d32d`) scan (B608 ×2 in `db.py`, B110 in
    `runner.py`; line-shifted only) → nothing new beyond the known baseline.
- S5 fix (M4a refinement, on dev, uncommitted — ships in the S7 code commit):
  `tests/test_bc_incremental.py` branch table — the re-expressed
  `run_result` call passed `pause` as the third positional arg (the
  `empty_proven` slot), so the `cancel`/`timeout` rows derived
  `proved_empty` → `success` instead of `cancelled`/`needs_attention`.
  Now `run_result(completed, rows, False, pause, all_items_known=True)` —
  the dev signature M4a specified. Re-run: 161 passed, 17 subtests, no
  skips.
- Deployment-process validation: **skip (not deployment-relevant; no
  Dockerfile, shell script, or runtime-config change) — user-confirmed at
  the S5 gate (2026-11-03)**.
- Status: VALIDATED. Next session: S6 documentation — review the merged
  CHANGELOG `### Added` entry (sanitized, public-safe wording; merged in
  S4), README/CONTRIBUTING only if user-visible behavior or contributor
  rules changed (none expected beyond the RECIPE_AUTHORING section already
  applied), plan-doc record; then S7 commit + push + PR close.

### S6 result (2026-11-03)

- Preflight re-verified: PR head `24e8492…` unchanged
  (`ls-remote github refs/pull/57/head`); `dev` = `origin/dev` = `c5974f4`
  (the S5 doc commit); dirty tree exactly the 9 modified + 1 untracked
  file S4 applied + S5 fixed.
- CHANGELOG: the incremental-keys entry under `## [Unreleased]` →
  `### Added` (merged in S4, newest-first before the F06 entry) is the
  PR's own entry verbatim; re-checked for sanitization (no Gitea host,
  NAS details, or private paths) and accuracy against the applied code
  (task+attribute key scoping, skip-known, all-known → `success` with
  the explicit log, no backfill, default acquisition unchanged, no
  correction detection) — confirmed, no change.
- README / CONTRIBUTING: **no change** — the S3-confirmed plan kept,
  user-confirmed at the S6 gate (2026-11-03). Re-verified the PR's
  README/RECIPE_METHODS hunks are fork-behind noise (method-chain
  validation + `replacement_calendar` text; zero `incremental` content).
  Maintainer observation recorded: README:333's `download_all` note
  documents the opt-in `allow_empty` option but not the new opt-in
  `incremental` option; a one-sentence README addition was offered at
  the S6 gate and declined. The feature documentation lives in
  `doc/RECIPE_AUTHORING.md` § "Opt-in incremental downloads" (PR
  section, applied in S4).
- Tree unchanged by S6 (doc-only session): exactly the 9 modified + 1
  untracked file from S4/S5.
- Next session: S7 — the two confirmed commits (S3 split: code / doc),
  Gitea `origin/dev` first, then promotion + GitHub mirror + PR close
  per the publication routine. Deployment-validation skip was
  user-confirmed at S5; the tree must not move before S7.

## Validation plan

S5 executes on the exact dev tree, from the repo root, with the venv:

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

## Deployment validation

Not deployment-relevant: the PR touches no `Dockerfile`, `.dockerignore`,
`BillCollector.sh`, `install_docker-image.sh`, `deploy_remote.sh`, or app
runtime configuration. Skip recorded in S5 (2026-11-03); **user-confirmed at
the S5 gate (2026-11-03)**. No Docker host needed.

## Out of scope

- ZIP extraction (issue #50 phase b, PR #58).
- C4/C8/archive-protocol behavior changes (dev #24 lane).
- Any UI change; any backfill; any control-protocol/exit-code change.
- PR #58 review (separate lane).

## Open questions (resolved in S2, 2026-11-03, user-confirmed)

1. Outcome value: reuse `duplicates_only` — settled by the #24 C4 contract
   (public comment on issue #24, quoted in
   `.kilo/plans/completed/1793551618380-issue24-c4-c8-result-delivery-contract.md`
   lines 696-698): "an incremental run that skips all known keys is
   `duplicates_only` → `success`". S1's floated `all_items_known` value is
   dropped; README/UI/ntfy vocabulary unchanged.
2. Precedence: `proved_empty` wins over `all_items_known` for a completed
   no-row run (both true only when `allow_empty` + `incremental` meet an
   empty listing); pinned by M1's order + the M4a `derive_outcome` pins.
3. Nits: fix 2 (`all_items_known` declared in `_RunContext.__init__`) and 3
   (double blank line in `doc/RECIPE_AUTHORING.md`) in the integration
   commits; leave 1 (`known_source_keys` queried before option validation;
   harmless, as reviewed).
