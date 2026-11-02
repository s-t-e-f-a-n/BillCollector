# Issue #24: C4 result-semantics contract + C8 delivery-state exposure (design)

Goal: draft the two maintainer lanes that issue #24 stays open for, so they can be
agreed on the issue (contract-first, per CONTRIBUTING: shared-interface
semantics are agreed in an issue before code) and then implemented:

- **C4 (F06)** — the run-result semantics contract: distinguish proved-empty /
  duplicates-only / new documents / partial collection / failed collection, so a
  healthy empty collection is not a `failure` and an arbitrary no-download run
  is not automatically healthy.
- **C8 (F10)** — the delivery-state exposure: expose downloaded / pending
  delivery / delivered / failed-delivery states with safe retries on the agreed
  task + sha256 idempotency key, and state what a plain consume-folder
  integration can prove when no ingestion callback exists.

Committed in the issue #27 triage (`1792861675256-issue27-maintainer-commitments.md`,
C4 and C8); the #24 status comment of 2026-11-01 (comment 6560325739) announced
both lanes as schedulable and committed that the #52 archive-receipt interface
will be drafted on this lane. No code in this plan; implementation follows
agreement (see "Implementation plan").

## Status

- 2026-11-01: created (DRAFT — user review pending).
- 2026-11-01: C4+C8 design posted to issue #24 for agreement (comment 6561111249, 2026-11-01T17:06:07Z).
- 2026-11-01: flowcool's 10-point confirmation request (comment 6561526987, 2026-11-01T17:41:21Z) answered (comment 6561636558, 2026-11-01T17:51:08Z): C4 points 1–5 and C8 points 6–8, 10 confirmed as posted; point 9 clarified — no daemon-level manual reconciliation state (automatic at-least-once retry on the agreed task+sha256 key; reconcile-before-resend is the ingestion-consumer responsibility in the #52 interface). Contract agreed per plan (user, 2026-11-01); implementation follows in the planned order (Delivery A: C4, then Delivery B: C8), after which issue #24 closes and the #52 archive-receipt interface proposal is posted.
- 2026-11-01: implementation plan chunked into session-sized units (A1–A7, B1–B6; one chunk per coding session, one commit each) after repeated context-limit overflows in coding sessions; Delivery A starts with A1.
- 2026-11-01: A1 landed — `Run.collection_outcome` + `Run.date_from` schema + `_migrate` (db.py); 3 migration tests in test_bc_db.py (19 passed). A2 next.
- 2026-11-01: A2 landed — `derive_outcome` + `run_result(completed, rows, empty_proven, pause_outcome)` (runner.py); the sole call site passes the run's committed Download rows (the `allow_empty` proof count is wired in A3/A4, so `empty_proven` is `False` until then); full derivation table replaces the legacy run_result unit tests (46 passed); test_doc_recipe.py's call updated to the new signature (author-example proof test green with real Chromium). A3 next.
- 2026-11-01: A3 landed — `_run_task` finalization (runner.py): the Run row now carries `collection_outcome` (derived at finalization; committed rows re-listed there so an interrupted run reflects them) + `date_from` (window start) on every terminal path; `empty_proven = ran > 0 and ran == proven` from the new `_RunContext.collection_actions_ran`/`collection_actions_proven` counters (0/0 until A4 increments them); three harness tests (completed no-download no-proof → failure + failed with date_from; aborted with a row on the run_id → failure + partial; interrupted with a committed row → interrupted + partial) (49 passed). A4 next.
- 2026-11-01: A4 landed — `download_all` opt-in `allow_empty` (collection.py: an empty listing completes as `[]` and serves as the window-empty proof; a non-boolean option value fails closed) + empty-proof counting in the `_collection_actions.download` adapter (runner.py: every started `download_all` increments `collection_actions_ran`, every completed empty result under `allow_empty` increments `collection_actions_proven`; a raised (graceful-failed) action counts as ran, never proven, which prevents `proved_empty`; `click_until_absent` is not counted). Tests: allow_empty behavior + a focused adapter counting test (test_bc_collection.py); end-to-end empty-listing runs (test_bc_runner.py: allow_empty → exit 0 + success + proved_empty; without the option → fail-closed, the run pauses and cancels, outcome stays failed). Full suite green (775 passed, 10 skipped), including fixing test_bc_date_variables.py's stale leak assertion (Run.date_from is an intentional window-start record since A3). A5 next.
- 2026-11-02: A5 landed — terminal run notification carries outcome + window (notify.py: `notify_run_result` takes keyword `outcome`/`date_from` and appends ` Outcome: <outcome>` + (when known) ` (window from <date_from>)` to the base message; `success` added to `_RUN_MESSAGES` — per the #24 agreement successful runs are now notified with their outcome, a deliberate change from "success stays silent"; `cancelled` stays silent. orchestrator.py: the monitor finalization passes `outcome=row["collection_outcome"], date_from=row["date_from"]` — both None on the orchestrator-finalized crash paths, so the message carries no suffix there; the orphan-cleanup and no-Run-row call sites are unchanged). Tests: test_bc_notify.py (success now dispatches; suffix on success and failure; base message only when the outcome is unknown; None/cancelled/private results still silent); test_bc_orchestrator.py `test_success_does_not_send` → success sends the base message once (the stub runner finalizes without outcome/window). Full suite green (777 passed, 10 skipped). A6 next.
- 2026-11-02: A6 landed — UI run-outcome display: dashboard's last-run cell appends the outcome when set (`2026-10-01 06:00 · success · proved_empty`; dashboard.py `_last_run_cell`) and the task-detail run-history expansion header carries it too (task_detail.py `render_history`, with `collection_outcome` added to the rebuild signature so a finalized outcome appears on the next poll); pre-existing NULL-outcome rows render exactly as before (pinned by the existing `· success` / `success · 4m 5s` assertions). Tests: test_bc_ui_dashboard.py (outcome appended on the last-run cell; NULL unchanged) + test_bc_ui_task_detail.py (outcome in the expansion header; NULL unchanged). Both UI files green (29 passed). A7 next.
- 2026-11-02: A7 landed — C4 docs + CHANGELOG + plan status (docs only, no code): doc/RECIPE_METHODS.md `download_all` options table gains `allow_empty` (boolean, default `false`, not required) + one semantics sentence (empty listing completes with zero records and proves the window empty for the run outcome; without the option the fail-closed error is unchanged); README updated — terminal-notification paragraph (a successful run now sends the push with outcome + window start, cancelled stays silent), dashboard last-run cell and task-detail run history show the outcome, `download_all` bullet gains the opt-in `allow_empty` sentence; CHANGELOG.md Unreleased — new run-result-semantics entry (two-axis result semantics, `allow_empty`, notification change, UI, additive `Run.collection_outcome`/`Run.date_from` schema) and the #49 entry corrected (successful runs are no longer silent). Verify: test_doc_recipe.py green (real Chromium), full suite green (779 passed, 10 skipped, 92 subtests) — Delivery A (C4) complete, delivery gate passed. Next: promote Delivery A per the release cycle (ff-only dev → Gitea main + GitHub mirror), then Delivery B starts with B1.
- 2026-11-02: Delivery A (C4) DELIVERED — Stage 1 re-verified at the promotion tip (full unit suite green: 779 passed, 10 skipped, 92 subtests; full-scope regression harness PASS, exit 0); ff-only dev → Gitea main 67b5b38 (26377b0..67b5b38); sanitized GitHub mirror main 21ef9f3 (no tag — not a versioned release); public listing verified (no private paths). Issue #24 stays open until Delivery B (C8) lands. Delivery B starts with B1.
- 2026-11-02: B1 landed — `Download.delivery_attempts` schema + `_migrate` (db.py); 3 migration tests in test_bc_db.py (22 passed). B2 next.
- 2026-11-02: B2 landed — `_deliver` failed transition (downloads.py): a published-file checksum mismatch is a delivery failure like a consumer exception (stops the consumer loop, no raise); on any failure the attempt is incremented and the row set `failed`, with a first-transition-only `notify_delivery_failed` push (a retry of a `failed` row notifies no further); on success the attempt is incremented and the row set `consumed`; duplicate rows are never delivered. `db.increment_download_attempts` (NULL-safe COALESCE) + `notify.notify_delivery_failed` (best-effort ntfy, task looked up before dispatch, no URLs/secrets). Tests: 5 new in test_bc_downloads.py (failing consumer → failed + attempt 1 + exactly one notification; checksum mismatch → failed without raise; success → consumed with attempt 1; duplicate row untouched; notify message/dispatch unit); 3 recovery tests updated to the B2 intermediate semantics (failed rows are not retried by startup recovery yet — B3 restores the retry, including the runner-start and daemon-startup cases, and the old checksum-raise case now fails the delivery instead). Full suite green (787 passed, 10 skipped, 92 subtests). B3 next.
- 2026-11-02: B3 landed — startup recovery retries `failed` rows (downloads.py `_recover_locked`: rows with state `published` **or** `failed` are delivered on the same code path and idempotency key, no retry cap; the journal-cleanup condition is unchanged, so a still-`failed` row keeps its journal for the next retry; `recover_downloads` target selection and `db.pending_downloads` already include `failed` rows). The three B2 intermediate-semantics tests are restored to retry semantics (test_bc_downloads.py: the failing-consumer row is re-delivered on the same key at recovery → `consumed`, attempt 2; test_bc_downloads_recovery.py: the runner-start recovery retries the `failed` row on the same idempotency key → `consumed`, attempt 2; the daemon-startup subprocess retry delivers the `failed` row immediately with no consumer registered in the child). Two new recovery tests: a `failed` row with a still-failing consumer stays `failed` with the attempt incremented (2) and its journal retained; a `failed` row with a fixed consumer becomes `consumed` (attempt 2) and its journal is cleaned. Chunk suites green (43 passed) + notice-identity/calendar/collection sanity (76 passed, 1 skipped). B4 next.

## Verified context (dev `f11cb30` / public `main` `4a9bffc`, 2026-11-01)

Code facts this design builds on (all verified on the current dev tree):

- **Run health today** — `runner.py:139-157` `run_result`: pause cancel →
  `cancelled`, pause timeout → `needs_attention`, aborted → `failure`,
  completed with zero downloaded files → `failure` (the explicit F06 legacy
  contract), any per-file entry not `success` → `failure`, else `success`.
  Exit code: `runner.py:1140-1144` — 0 only for `success`.
- **Aborted vs. interrupted** — `_run_recipe` (`runner.py:931-978`):
  `aborted=True` on step/recipe error or pause outcome; `RunInterrupted`
  (shutdown signal) is re-raised and finalized as `interrupted`
  (`runner.py:1099-1104`).
- **Per-file entries** — `ctx.files_downloaded` entries carry
  `url` / `suggested_filename` / `result` (`runner.py:535-539`, `924-928`);
  the `duplicate` flag returned by `track_download` is not carried into the
  entry, and graceful download failures add an entry without a committed row.
- **Download row states** — `db.py:74-89`: `state` (default `consumed`),
  `staged_path`, `duplicate_of_id`, `source_identity`, `revision_sha256`.
  `downloads.py`: row committed `staged` before publication
  (`downloads.py:249-250`), `_publish` → `published`
  (`downloads.py:125`), `_deliver` → `consumed` only when no consumer failed
  (`downloads.py:89-90`); a consumer failure leaves the row `published`
  (pending) and is retried at startup (`downloads.py:157-168`); duplicate rows
  are never delivered (`downloads.py:72-73`); the idempotency key is
  `f"{task_id}:{sha256}"` (`downloads.py:75`).
- **Recovery** — `recover_downloads` / `_recover_locked`
  (`downloads.py:128-184`) run at daemon startup in a subprocess
  (`downloads.py:262-288`): staged rows are published, published rows are
  re-delivered, journals are cleaned when the row is `consumed`; a published
  file without a row is recovered conservatively as `consumed` without
  replaying consumers (`downloads.py:149-154`); a downstream folder watcher
  may have moved the published file — the committed intent retains the
  delivery obligation (`downloads.py:122-124`).
- **Consumer slot** — `consumers/__init__.py`: `CONSUMERS = []` (empty by
  default); the at-least-once contract is documented there.
- **Bounded collection** — `collection.py:187-199` `_validate_snapshot`: an
  empty listing is a `CollectionError("download list is empty")` (fail-closed);
  `download_all` (`collection.py:347-460`) commits each item's record as it
  goes — a later item's failure leaves earlier records committed
  (`collection.py:355`).
- **Collection window** — PR #34 (`variables.py`): `Task.date_window_days`
  (default 90), `DateContext.capture(window, override)` → `DATE_FROM` /
  `DATE_TO` / `TODAY±Nd`; the effective window is captured per run
  (`runner.py:1052`) but not recorded on the Run row.
- **Notice identity** — PR #41 (`notice.py`): opt-in `notice_identity` →
  `source_identity` (URL query-parameter digest) + `revision_sha256` (PDF
  object-graph digest); a metadata-only regeneration retains an audit row via
  `find_notice_revision` (`db.py:444-449`).
- **UI** — `ui/downloads.py`: `/downloads` and the task-detail section list
  task / run / filename / size / sha256 / duplicate badge / date; read-only,
  no delivery state, no retry action. Run history shows `Run.result`.
- **Notifications** — PR #56: terminal run notifications (ntfy, opt-in per C1).
- **Open issues** — #50 (incremental keys + `unpack: pdf`; its no-op terminal
  result is explicitly "not assumed upstream" and awaits agreement), #51
  (Bourse Direct adapter; invocation/delivery semantics deferred to this
  lane), #52 (archive receipts — the archive side of C8, interface to be
  drafted on this lane per the 2026-11-01 reply, comment 6560326227).

## C4 — result semantics contract (F06)

### Problem

`run_result` (`runner.py:139`) forces two orthogonal facts onto one axis:

1. **Run health** — did the run complete, abort, or get interrupted?
2. **What the collection proved** — new documents, everything already known,
   a proven-empty window, a partial collection, or no proof at all.

Consequences (the F06 finding): a healthy empty collection is a `failure`
(`runner.py:153-154`), and a completed no-download run can never be
distinguished from a broken one — an arbitrary no-download run is neither
proven healthy nor reported as unproven.

### Design: two orthogonal axes on the Run row

**Axis 1 (unchanged values): `Run.result`** — `success` / `failure` /
`interrupted` / `cancelled` / `needs_attention`. The values stay; the
conditions for `success` change (that is the F06 fix).

**Axis 2 (new): `Run.collection_outcome`** — one of five values, derived at
run finalization from the run's own committed data:

| Outcome | Meaning (for this task's collection window) |
|---|---|
| `new_documents` | at least one new (non-duplicate) Download row was committed and published in this run |
| `duplicates_only` | the run completed, at least one download attempt occurred, and every attempt resolved to an existing (task, sha256) or (task, source_identity, revision) — the window was checked, everything is already known |
| `proved_empty` | the run completed and every bounded collection action that ran proved its listing empty under the opt-in (see below) — the window is proven to contain nothing new |
| `partial` | the run did not complete (abort, step error, pause outcome, or interruption) but at least one row was committed in this run — the next run is safe (dedup/keys make it resume-tolerant) and will finish the remainder |
| `failed` | no provable collection: no rows committed and no empty proof (aborted with no rows, vault/display failure, a collection action that raised before committing, or a completed run with no rows and no empty proof) |

**Derivation** (at run finalization, where the Run row is written; the DB is
authoritative — duplicate rows carry the run's `run_id`):

```
completed    = the recipe loop reached the end without abort
               (no step/recipe error, no pause outcome; RunInterrupted is
               a separate terminal path)
empty_proven = every download_all action that ran completed with an empty
               snapshot under allow_empty; a run with no such action ran is
               never empty_proven
rows         = Download rows with this run's run_id

if not completed:
    outcome = "partial" if rows else "failed"
else:
    if any row has duplicate_of_id IS NULL:  outcome = "new_documents"
    elif any row exists:                     outcome = "duplicates_only"
    elif empty_proven:                       outcome = "proved_empty"
    else:                                    outcome = "failed"
```

**`Run.result` mapping** (replaces `runner.py:151-157`):

```
if RunInterrupted:        result = "interrupted"
elif pause cancel:        result = "cancelled"
elif pause timeout:       result = "needs_attention"
elif outcome in (new_documents, duplicates_only, proved_empty):
                          result = "success"
else:                     result = "failure"   # partial or failed
```

Effect on today's behavior:

- Healthy empty collection (`proved_empty`): `failure` → **`success`** (the F06 fix).
- Duplicates-only run: `failure` → **`success`** (dedup did its job).
- Completed run with no rows and no empty proof (an `expect_download` recipe
  that found nothing, a recipe with no download step): stays **`failure`** —
  now with `outcome=failed` saying why.
- Aborted run with committed rows: stays **`failure`**, now
  `outcome=partial` instead of an unexplained failure.
- Graceful step failures (the "run continues" path, `runner.py:918-920`): they
  do not by themselves fail the run — the outcome is derived from committed
  rows and empty proof as above; a graceful failure of a download step prevents
  `proved_empty` (that step never proved its listing empty) and is still
  visible per-step in the run log/UI as today.

**Exit code** — unchanged mechanism: 0 for `success` (now including all three
healthy outcomes), 1 otherwise (`runner.py:1140-1144`).

**Notifications** — the terminal run notification keeps its result→message
mapping and gains the outcome and the window: e.g.
`run finished: success (proved empty, window 2026-07-04..2026-10-01)`,
`run finished: failure (partial: 15 of 20 items committed)`.

### Recipe contract: opt-in empty proof (`allow_empty`)

`proved_empty` must be provable, not guessed. Today an empty listing is an
error (`collection.py:190`), which is the right default: an unexpectedly empty
listing is usually a locator or portal regression, not "no bills".

- New bounded-collection option for `download_all`: **`allow_empty: true`**
  (v1 scope: `download_all` only; `replacement_calendar`'s per-month
  completion semantics are out of scope for v1).
- With `allow_empty`, an empty snapshot is a valid terminal state: the action
  completes with zero records and reports "proved empty" to the run context;
  the run can then reach `proved_empty`.
- Without it, the current `CollectionError` behavior is preserved unchanged.
- The option is a recipe-contract change → it is part of this contract and is
  agreed here before code (CONTRIBUTING).

### Collection window (#26) interaction

The outcome is the statement about the run's configured window
(`Task.date_window_days`, effective `DATE_FROM`): "new documents in this
window" / "everything in this window is already known" / "this window is
proven to contain nothing" / "only partially covered" / "not proven". To make
that auditable, the Run row records the effective window start:

- New column **`Run.date_from TEXT`** (nullable; ISO date; set from the
  captured `DateContext` at run start; `NULL` for runs without a window or for
  pre-existing rows).

### Schema (additive only)

- `Run.collection_outcome TEXT` (nullable; `NULL` for pre-existing runs — the
  UI renders `—`).
- `Run.date_from TEXT` (nullable, as above).
- One-time `ALTER TABLE` migrations in the existing `db.py:_migrate` pattern;
  no backfill.

### Resolves #50's open terminal result

An incremental run (opt-in stable keys, #50's first phase) that skips all
known keys commits no new rows and at least one duplicate audit row → outcome
**`duplicates_only`** → `success`. The contract states this explicitly: the
verified no-op is a healthy duplicates-only collection, not silence and not a
failure. (#50's key persistence and `unpack: pdf` remain flowcool's
contribution phases; this lane only fixes the terminal-result semantics they
depend on.)

### Acceptance (synthetic, isolated — no provider, vault or consumer)

- Unit: the outcome derivation table (all five outcomes × completed /
  aborted / interrupted / pause outcomes), against a synthetic SQLite DB.
- Unit: `allow_empty` — empty snapshot completes with the proof flag; without
  the option the `CollectionError` is unchanged (existing test coverage
  preserved).
- Unit: `Run.result` mapping + exit code — `success` for all three healthy
  outcomes; `failure` for `partial` / `failed`; `interrupted` / `cancelled` /
  `needs_attention` unchanged.
- Integration (synthetic download objects, disposable DB + output dir, the
  #24 proof shape): duplicates-only run → `success` + `duplicates_only`;
  `allow_empty` run with an empty listing → `success` + `proved_empty`;
  completed no-download run without proof → `failure` + `failed`; run aborted
  after committed rows → `failure` + `partial`.
- Compatibility: pre-existing Run rows render `—` in the UI; all
  `run_result` / `Run.result` consumers (orchestrator, UI, notifications,
  scheduler) keep working on the unchanged value set.

## C8 — delivery-state exposure (F10)

### Current state machine

`staged` (row committed, bytes staged) → `published` (atomic rename done) →
`consumed` (all registered consumers succeeded, or none registered). A
consumer failure leaves the row `published`; the only retry is the daemon
startup recovery. The UI shows no state and offers no retry.

### Design: four exposed states

The exposed states from the C8 commitment map onto `Download.state` with one
new value:

| Exposed state | `Download.state` | Meaning |
|---|---|---|
| downloaded | `staged` | row committed, bytes staged, not yet published (transient; visible after a crash between commit and publication) |
| pending delivery | `published` | atomically published; delivery not yet acknowledged by all registered consumers |
| delivered | `consumed` | all registered consumers acknowledged (or none registered — see the F10 statement below for what that proves) |
| failed-delivery | **`failed`** (new value) | a delivery attempt raised (consumer exception or published-file checksum mismatch); safe retry available |

Changes:

- `_deliver` transitions the row to `failed` on consumer failure or checksum
  mismatch (today: left at `published`).
- New column **`Download.delivery_attempts INTEGER`** (nullable, additive;
  incremented per delivery attempt, auto or manual; `NULL` for pre-existing
  rows).
- Startup recovery (`_recover_locked`) retries `failed` rows in addition to
  `published` / `staged` — same at-least-once semantics, same idempotency key,
  same code path. No automatic retry cap (the row keeps retrying on every
  startup until it delivers; a cap is a possible later refinement, not part of
  this contract).

### Safe retry

- **Manual retry**: a new daemon action re-delivers one row — in a runner
  subprocess (consumers run in the runner, never in the UI process, as today),
  opening its own DB connection and taking the output-directory publication
  lock, reusing the recovery delivery path. Same idempotency key
  (`task_id:sha256`); the consumer tolerates re-delivery per the documented
  at-least-once contract.
- **Automatic retry**: every daemon startup (existing behavior, extended to
  `failed` rows).
- A retry re-checks the published file's checksum when it still exists
  (existing behavior, `downloads.py:79-80`); a file already moved by a
  downstream watcher does not block delivery — the consumer receives the
  record and acts on the idempotency key.

### Exposure

- **UI** — `/downloads` and the task-detail downloads section (shared row
  builder): a new **Delivery** column rendering the four exposed states; a
  **Retry delivery** action on rows that are not `delivered`, with a
  confirmation stating that delivery is at-least-once and keyed on
  task + sha256.
- **Notifications** — one notification when a row first transitions to
  `failed` (at run-time delivery and at startup recovery), not per retry:
  `delivery failed: <task> <filename> (attempt N)`. Opt-in ntfy as today.
- **Docs** — `doc/DOWNLOAD_RECOVERY.md` gains the state machine, the retry
  semantics, and the F10 statement below; the README's downloads section
  points at it.

### F10 statement — what a consume-folder integration can prove without a callback

This is the audit finding's core question, stated as contract:

- **With no registered ingestion consumer (the default), `delivered` means
  "atomically published into the output directory with no delivery obligation
  outstanding" — and nothing about the archive.** The daemon's proof ends at
  the checksum-verified atomic rename: a durable row, staged bytes, and a
  rename ordered so a crash cannot produce a published file without a row
  (recovery reconstructs the row conservatively as delivered — a missed
  ingestion is discoverable in the row list, a duplicate ingestion is not, per
  the agreed #24 contract point 3).
- **Ingestion proof requires a registered ingestion consumer** whose success
  means the archive acknowledged the document. The consumer slot
  (`CONSUMERS`) exists for exactly this; until one is registered and
  succeeds, a consume-folder integration can prove "the file arrived in the
  folder with the committed bytes", and the archive side must prove the rest
  (e.g. the archive's document result with a matching checksum readback — the
  #52 archive-receipt interface).
- **Re-delivery and moved files**: the bytes may already have left the folder
  (a watcher took them). Delivery hands off the *record* (idempotency key +
  metadata), not the file: a consumer must be able to act on the record alone
  when `saved_path` no longer exists — checksum-deduplicating consumers do by
  construction; a consumer that needs the bytes must treat a missing
  `saved_path` as "already handed off", not as an error.

### #52 archive-receipt interface (the archive side)

Per the 2026-11-01 reply on #52 (comment 6560326227), the interface proposal
is drafted on this lane and posted to #52 for agreement before any code. Shape
(from #52's agreed boundaries):

- An ingestion consumer that binds optional provider evidence to the exact
  untouched PDF / checksum and preserves that association across retries.
- Proves ingestion by a durable archive document result plus original
  checksum readback, or a verified relation to a previously archived original.
- Reconciles an uncertain existing effect before resending; keeps distinct
  accounts and notices separate.
- Preserves changed originals; no financial correction is inferred from a
  byte change alone; missing, incomplete or ambiguous evidence must not
  silently suppress a document.
- No new schema, consumer state, Paperless version policy, or automatic
  historical conversion before agreement.

Sequencing: the full interface proposal is drafted **after** the #24
agreement (it references the delivery states it rides on) and posted to #52;
its implementation is a separate lane after #52 agreement. The C8 delivery
itself does not depend on it — the consume-folder statement above stands
without it.

### Acceptance (synthetic, isolated)

- A failing consumer → row `failed`, `delivery_attempts` incremented, exactly
  one "delivery failed" notification; a manual retry with a fixed consumer →
  `delivered`; the consumer observes the same idempotency key on re-delivery.
- Startup recovery retries `failed` rows: synthetic kill after the consumer
  effect and before the state commit (the #24 proof shape: interrupt, restart
  with the same task identity, assert row state and consumer call count),
  restart → retry on the same key.
- With no consumers: publication completes immediately to `delivered`; the F10
  statement holds (no ingestion claim).
- UI: the Delivery column renders all four states; the retry action is present
  only on non-`delivered` rows; the retry confirmation text states the
  at-least-once keying.

## Implementation plan (chunked — 2026-11-01)

Session-sized chunks, written after repeated context-limit overflows in
coding sessions. The design sections above stay the contract; the chunk
specs below are self-contained — a coding session reads **only** its chunk
plus the chunk's "read" list, never the whole design or the repo.

### Session protocol (every chunk)

- **One chunk per coding session** (exactly one; never two).
- Read only: this chunk's spec + its "read" list (paths with line anchors).
  No repo exploration, no re-deriving the design, no reading other chunks.
- Edit only the chunk's "edit" list. A needed change outside it stops the
  session (report it; do not expand scope).
- End state: the chunk's verify command green, a one-line entry appended to
  the Status section (same commit), committed via the dev-commits cycle
  (per-item user confirmation).
- Resume after a mid-chunk context overflow: re-read the chunk spec and run
  `git diff` — progress is at most one file deep.
- Verify from the repo root:
  `PYTHONPATH=apps apps/.venv/bin/python -m pytest tests/<file> -x -q`.
- Delivery gate: after A7 and after B6 the **full** unit suite
  (`... python -m pytest tests/ -x -q`) must be green, then ff-only
  promotion + GitHub mirror per the release cycle (one per delivery).

### Delivery A — C4 (7 chunks)

**A1 — Run schema: `collection_outcome` + `date_from`**
- Edit: `apps/billcollector/db.py`. SCHEMA Run table (48-64): add
  `collection_outcome TEXT` and `date_from TEXT` after `notes TEXT`.
  `_migrate()` (115-158): add both as `TEXT` for pre-existing DBs in the
  existing PRAGMA table_info pattern (idempotent, no backfill).
- Read: db.py 48-64, 110-158, 345-381.
- Test: `tests/test_bc_db.py` — a fresh DB has both columns; a legacy DB
  (created without them) picks them up on open; idempotent on re-open
  (follow the file's existing migration-test pattern).
- Commit: `feat: add Run.collection_outcome and Run.date_from with migration (C4, issue #24)`

**A2 — Outcome derivation + result mapping (pure)**
- Edit: `apps/billcollector/runner.py`. Replace `run_result` (139-157):
  - `derive_outcome(completed, rows, empty_proven)`: `not completed` →
    `"partial" if rows else "failed"`; else any row with
    `duplicate_of_id is None` → `"new_documents"`; else rows present →
    `"duplicates_only"`; else `empty_proven` → `"proved_empty"`; else
    `"failed"`. `rows` = this run's committed Download rows (dicts).
  - `run_result(completed, rows, empty_proven, pause_outcome=None)`: pause
    `"cancel"` → `"cancelled"`, `"timeout"` → `"needs_attention"` (terminal
    in itself, unchanged); else `"success"` iff the outcome is one of the
    three healthy values, else `"failure"`. Exit-code mechanism untouched
    (0 only for `success`, runner.py 1140-1144).
- Read: runner.py 100-160, 931-988 (abort/interrupt semantics);
  `tests/test_bc_runner.py:49-70` (the run_result tests to replace).
- Test: `tests/test_bc_runner.py` — replace the run_result unit tests with
  the full derivation table (all five outcomes × completed/aborted,
  rows/no rows, empty_proven, both pause outcomes). Pure dicts, no DB.
- Commit: `feat: collection-outcome derivation and run result mapping (C4, issue #24)`

**A3 — Finalization wiring + `date_from` capture**
- Edit: `apps/billcollector/runner.py` `_run_task` (1012-1153).
  - Init next to `result = "failure"` (1069): `completed = False`,
    `pause_outcome = None`, `rows = []`; next to `children = None` (1078):
    `ctx = None` (unbound when the display stack or vault preflight fails
    before 1095).
  - `_RunContext.__init__` (188-219): add `self.collection_actions_ran = 0`
    and `self.collection_actions_proven = 0` (A4 increments them;
    `empty_proven = ran > 0 and ran == proven`, 0/0 when `ctx is None`).
  - Normal path (1097-1098): `files, aborted, pause_outcome =
    _run_recipe(ctx, recipe)`; `completed = not aborted`;
    `rows = db.list_downloads(run_id=run_id)` (exists, db.py:451);
    `result = run_result(completed, rows, <empty_proven>, pause_outcome)`.
  - Finalization `finally` (1119-1134): when `run_id` is not None, extend
    the row write (1128) with `collection_outcome=derive_outcome(completed,
    rows, <empty_proven>)` and `date_from=dates.date_from.isoformat()`
    (`dates` = the DateContext captured at 1052, always bound when a run
    row exists). Exception paths (vault/display/unexpected, 1105-1118) keep
    their `result = "failure"` and the RunInterrupted path (1099-1104) keeps
    `"interrupted"`; with `completed = False` and no rows the outcome is
    `failed` — matching the contract.
- Read: runner.py 188-220, 988-1153; db.py 451-458.
- Test: `tests/test_bc_runner.py` — extend the existing `_run_task` harness
  classes (the 339/461/583-style fixtures): the finalized Run row carries
  `collection_outcome` + `date_from`; completed no-download no-proof run →
  `failure` + `failed`; aborted run with a row inserted on the run's
  `run_id` → `failure` + `partial`; interrupted run with a committed row →
  `interrupted` + `partial`.
- Commit: `feat: finalize runs with collection outcome and window start (C4, issue #24)`

**A4 — `allow_empty` option + empty-proof tracking**
- Edit: `apps/billcollector/collection.py`.
  - `_validate_snapshot` (187-198): new keyword `allow_empty=False`; the
    empty listing raises `CollectionError` only when the option is off.
  - `download_all` (347-460): add `allow_empty` to the options names set
    (357-362), read it (bool), pass it to `_validate_snapshot`, and return
    `[]` early on an empty snapshot with the option on.
- Edit: `apps/billcollector/runner.py` `_collection_actions.download`
  (542-550): count every started `download_all` call
  (`ctx.collection_actions_ran += 1`) and every completed empty result
  under `allow_empty` (`ctx.collection_actions_proven += 1`). A raised
  (graceful-failed) action counts as ran, never proven — it prevents
  `proved_empty`, as contracted. `click_until_absent` is not counted.
- Read: collection.py 182-233, 347-460; runner.py 501-569.
- Test: `tests/test_bc_collection.py` — empty snapshot + `allow_empty` →
  `[]` without error; empty without the option → `CollectionError`
  unchanged; non-empty with the option → unchanged behavior.
  `tests/test_bc_runner.py` — proof-flag counting via the existing harness
  (or a focused adapter test with a fake ctx).
- Commit: `feat: opt-in download_all allow_empty with run empty-proof (C4, issue #24)`

**A5 — Terminal notification: outcome + window**
- Edit: `apps/billcollector/notify.py`.
  - `notify_run_result(db, result, *, outcome=None, date_from=None,
    dispatch=None)` (87-107): append the outcome to the message when
    known — base message + ` Outcome: <outcome>` + (when `date_from` known)
    ` (window from <date_from>)`, e.g. `A collector run failed. Check the
    BillCollector dashboard. Outcome: partial (window from 2026-07-04)`.
  - Add `"success": "A collector run finished successfully."` to
    `_RUN_MESSAGES`: per the #24 agreement (public comment 6561111249,
    confirmed 2026-11-01) successful runs are now notified with the
    outcome — a deliberate change from "success stays silent"; update the
    docstring. `cancelled` stays silent.
- Edit: `apps/billcollector/orchestrator.py`: the monitor finalization call
  (533-534) passes `outcome=row["collection_outcome"],
  date_from=row["date_from"]` (both None on orchestrator-finalized crash
  paths — the message then carries no outcome suffix). The other call sites
  (215, 497) are left without the suffix.
- Read: notify.py (whole, 122 lines); orchestrator.py 485-534;
  `tests/test_bc_notify.py`.
- Test: `tests/test_bc_notify.py` — success now sends (was silent);
  outcome/window suffix on success and failure; no suffix when unknown;
  cancelled still silent.
- Commit: `feat: terminal run notification carries outcome and window (C4, issue #24)`

**A6 — UI run-outcome display**
- Edit: `apps/billcollector/ui/dashboard.py` — the last-run cell (133-137):
  append the outcome when set (e.g. `2026-10-01 06:00 · success ·
  proved_empty`); pre-existing rows (`collection_outcome` NULL) render
  exactly as today.
- Edit: `apps/billcollector/ui/task_detail.py` — the run-history header
  (318-322): same addition; include `r["collection_outcome"]` in the
  rebuild signature (312).
- Read: dashboard.py 125-215; task_detail.py 300-330; the existing
  assertions in `tests/test_bc_ui_dashboard.py` /
  `tests/test_bc_ui_task_detail.py`.
- Test: both UI test files — a run row with an outcome renders it; a
  NULL-outcome row is unchanged.
- Commit: `feat: show run collection outcome in dashboard and run history (C4, issue #24)`

**A7 — C4 docs + CHANGELOG + plan status**
- Edit: `doc/RECIPE_METHODS.md` (the `download_all` section, 196-217): an
  `allow_empty` row in the options table (boolean, default false, not
  required) + one semantics sentence (an empty listing completes with zero
  records and proves the window empty for the run outcome; without the
  option the fail-closed error is unchanged).
- Edit: README (the run-result/downloads semantics section — locate by
  grep), CHANGELOG.md (unreleased entry: two-axis result semantics,
  `allow_empty`, notification change, UI, additive schema).
  `tests/test_doc_recipe.py` constrains the recipe docs — run it and keep
  it green.
- Edit: this doc — Status entries as the chunks landed.
- Verify: `pytest tests/test_doc_recipe.py -x -q`, then the **full** suite
  (delivery gate).
- Commit: `doc: C4 contract docs — allow_empty, run outcomes, changelog (issue #24)`

### Delivery B — C8 (6 chunks)

**B1 — `Download.delivery_attempts` schema + migration**
- Edit: `apps/billcollector/db.py`. SCHEMA Download table (74-89): add
  `delivery_attempts INTEGER`. `_migrate()` (146-155): add it to the
  Download column loop.
- Read: db.py 74-94, 115-158, 415-432.
- Test: `tests/test_bc_db.py` — fresh DB + legacy-DB migration (existing
  pattern).
- Commit: `feat: add Download.delivery_attempts column with migration (C8, issue #24)`

**B2 — `_deliver`: `failed` transition, attempt count, first-failure notification**
- Edit: `apps/billcollector/downloads.py` `_deliver` (71-91).
  - A published-file checksum mismatch (79-80) no longer raises: it is a
    delivery failure like a consumer exception (stop the consumer loop, do
    not run the remaining consumers).
  - On any failure: increment the attempt, set state to `failed` (a new
    `Download.state` value — no schema change), and send the notification
    **only when the row's previous state was not already `failed`**
    (first transition; run-time delivery and startup recovery share this
    path, so a retry of a `failed` row notifies no further).
  - On success: increment the attempt, set `consumed` (as today).
  - Duplicate rows are still never delivered (72-73).
- Edit: `apps/billcollector/db.py`: `increment_download_attempts(id)`
  (NULL-safe: `COALESCE(delivery_attempts, 0) + 1`).
- Edit: `apps/billcollector/notify.py`: `notify_delivery_failed(db, row)` —
  best-effort ntfy (the runner/recovery subprocesses send directly, as the
  pause push does from the runner): `delivery failed: <service> <user>
  <filename> (attempt N)`; no URLs or secrets; task looked up via
  `db.get_task(row["task_id"])`.
- Read: downloads.py 71-91, 109-126; notify.py 80-122 (the pattern to
  copy); db.py 415-432.
- Test: `tests/test_bc_downloads.py` — failing consumer → row `failed`,
  `delivery_attempts` = 1, exactly one notification (fake dispatch);
  checksum mismatch → `failed` (no raise); successful consumer → `consumed`
  with attempt 1; duplicate row → untouched.
- Commit: `feat: failed delivery state with attempt count and first-failure notification (C8, issue #24)`

**B3 — Startup recovery retries `failed` rows**
- Edit: `apps/billcollector/downloads.py` `_recover_locked` (157-168):
  deliver rows whose state is `published` **or** `failed` (same code path,
  same idempotency key, no retry cap); the journal-cleanup condition is
  unchanged (a row still `failed` keeps its journal for the next retry).
- Read: downloads.py 128-184 (the recovery loop + target selection —
  `failed` rows already select their target, 178-181).
- Test: `tests/test_bc_downloads_recovery.py` — a `failed` row with a
  still-failing consumer stays `failed` with the attempt incremented; a
  `failed` row with a fixed consumer (patch `CONSUMERS`) becomes `consumed`
  and its journal is cleaned; the existing `staged`/`published` cases still
  pass.
- Commit: `feat: startup recovery retries failed delivery rows (C8, issue #24)`

**B4 — Manual retry: `downloads.__main__ --retry` + orchestrator action**
- Edit: `apps/billcollector/downloads.py`.
  - `retry_delivery(db, download_id) -> bool`: fetch the row (new
    `db.get_download(id)` helper); refuse missing or duplicate rows; take
    the output-dir publication lock for the row's target; `staged` rows are
    published first; then `_deliver` on the re-read row; return True iff
    the row ends `consumed`.
  - `__main__` (291-301): a `--retry <id>` mode next to the existing
    recovery entry (`python -m billcollector.downloads <db> --retry <id>`;
    exit 0 only on delivery).
- Edit: `apps/billcollector/orchestrator.py`:
  `async def retry_delivery(self, download_id) -> tuple[bool, str | None]`
  — spawns the same subprocess via `asyncio.create_subprocess_exec`
  (consumers stay out of the UI process, as today), bounded by the
  `download_recovery_timeout_seconds` setting; returns success + a
  sanitized error (never the child's raw stderr).
- Read: downloads.py 54-91, 262-301; orchestrator.py 120-160, 378-410
  (the spawn pattern).
- Test: `tests/test_bc_downloads.py` — `retry_delivery`: `failed` row +
  working consumer → `consumed`; `published` row → `consumed`;
  `consumed`/duplicate row → refused (no consumer call).
- Commit: `feat: manual delivery retry in the runner subprocess (C8, issue #24)`

**B5 — UI: Delivery column + retry action**
- Edit: `apps/billcollector/ui/downloads.py`.
  - `build_download_rows` (60-82): new `delivery` field mapping the four
    exposed states (staged → `downloaded`, published → `pending delivery`,
    consumed → `delivered`, failed → `failed delivery (N)` with the attempt
    count, `—` when NULL) + a hidden `retryable` flag
    (`state != "consumed"` and not a duplicate).
  - COLUMNS (22-30): a Delivery column before `date`.
  - The page: a per-row **Retry delivery** button (the existing body-slot
    pattern) shown only on retryable rows; a confirmation dialog states
    delivery is at-least-once, keyed on task + sha256; on confirm call
    `await orchestrator.retry_delivery(row["id"])`, notify the outcome,
    rebuild the rows. Signature becomes `register_downloads(db,
    orchestrator)`.
- Edit: `apps/billcollector/ui/app.py` (173): pass the orchestrator. The
  task-detail downloads section shares the builder and gains the same
  column/action with no extra work.
- Read: ui/downloads.py (whole, 110 lines); ui/app.py 154-175;
  `tests/test_bc_ui_task_detail.py` (the shared-builder test pattern).
- Test: the row builder renders all four states + the attempt count;
  `retryable` only on non-`delivered` non-duplicate rows; the page
  registers with the orchestrator (existing UI-test pattern).
- Commit: `feat: downloads UI delivery states and retry action (C8, issue #24)`

**B6 — C8 docs + CHANGELOG + plan status**
- Edit: `doc/DOWNLOAD_RECOVERY.md` — add: the state machine (staged →
  published → consumed, plus the `failed` branch with its two retry
  paths), the retry semantics (at-least-once, keyed on task + sha256, no
  cap), and the F10 statement (this doc's "F10 statement" section, as
  contract text).
- Edit: README (the downloads section → pointer at
  `doc/DOWNLOAD_RECOVERY.md`), CHANGELOG.md, this doc's Status.
- Verify: the **full** unit suite (delivery gate).
- Commit: `doc: delivery state machine, retry semantics and F10 statement (C8, issue #24)`

### After the deliveries

1. Promote each delivery: ff-only dev → Gitea main + sanitized GitHub
   mirror (the release cycle), one per delivery, after its full-suite gate.
2. Close issue #24 as delivered (its 2026-11-01 comment states it stays
   open until the state exposure lands), with the close comment per the
   routine.
3. Draft the #52 archive-receipt interface proposal against the landed
   delivery states and post it to #52 for agreement — a drafting session,
   not a coding chunk (the draft shape is in "Public post drafts" below).

## Public post drafts (sanitized; user-confirmed before posting)

### Draft: issue #24 comment (C4 contract + C8 approach)

> Both lanes are drafted. Here is the contract for agreement before any code.
>
> **1. Result semantics (the F06 fix).** The run gets two orthogonal facts
> instead of one overloaded result. `Run.result` keeps its values
> (`success` / `failure` / `interrupted` / `cancelled` / `needs_attention`);
> a new `Run.collection_outcome` records what the collection proved for the
> run's window:
>
> - `new_documents` — at least one new, non-duplicate document was committed and published.
> - `duplicates_only` — the run completed and every download attempt resolved to an existing (task, sha256) or (task, source+revision) identity. The window was checked; everything is already known.
> - `proved_empty` — the run completed and every bounded collection action proved its listing empty under a new opt-in `download_all` option (`allow_empty: true`). Without the option, an empty listing stays an error (fail-closed default).
> - `partial` — the run did not complete (abort, error, pause, or interruption) but at least one row was committed. Re-running is safe: dedup and keys make it resume-tolerant.
> - `failed` — no provable collection: no rows and no empty proof. This includes a completed run with no downloads and no proof of emptiness, which is not success.
>
> Mapping: the three healthy outcomes map to `success` (exit 0); `partial` and
> `failed` map to `failure` (exit 1); `interrupted` / `cancelled` /
> `needs_attention` are unchanged. A healthy empty collection is no longer a
> failure; an arbitrary no-download run is no longer automatically healthy —
> it is a failure with the outcome saying why. The terminal notification
> gains the outcome and the window (e.g. `success (proved empty, window
> 2026-07-04..2026-10-01)`), and the Run row records the effective window
> start so the statement is auditable.
>
> This also settles #50's open question: an incremental run that skips all
> known keys is `duplicates_only` → `success` — the verified no-op is a
> healthy collection, not silence.
>
> **2. Delivery-state exposure (the remaining lane of this issue).** The
> Download row exposes four states: `staged` (downloaded), `published`
> (pending delivery), `consumed` (delivered), and a new `failed`
> (failed-delivery, with an attempt count). A consumer failure moves the row
> to `failed`; startup recovery retries it (same code path as today's
> published-row retry), and a new manual retry action re-delivers one row in
> the runner subprocess on the same idempotency key (task + sha256) —
> at-least-once, as agreed. The Downloads page gains a Delivery column and
> the retry action; a row's first failed delivery sends one notification.
>
> **3. What a consume-folder integration can prove without an ingestion
> callback.** With no registered consumer (the default), `delivered` means
> "atomically published into the output directory with no delivery obligation
> outstanding" — and nothing about the archive. The daemon's proof ends at
> the checksum-verified atomic rename; a crash cannot produce a published
> file without a row, and a row without its file is reconstructable (a missed
> ingestion is discoverable, a duplicate ingestion is not). Ingestion proof
> requires a registered ingestion consumer whose success means the archive
> acknowledged the document; the consumer slot exists for exactly that. The
> archive-receipt interface from #52 (durable document result + checksum
> readback, or a verified relation to a previously archived original) is the
> shape of that consumer — I will draft the full interface on this lane and
> post it to #52 for agreement before any code there.
>
> Schema impact is additive and migration-safe: `Run.collection_outcome`,
> `Run.date_from`, `Download.delivery_attempts` (one-time ALTERs, no
> backfill) and the new `failed` state value. No change to the agreed
> #24 contract (durable row before consumer, at-least-once on task + sha256,
> staged + atomic + reconciled publication).
>
> Please object or confirm on this thread. After agreement I implement C4
> first, then the delivery-state exposure, and close this issue when the
> latter lands.

### Draft: issue #52 comment (posted after the #24 agreement)

> The #24 delivery-state lane is agreed; the archive-side interface
> proposal, as committed, follows. [Full interface proposal — drafted at that
> point against the agreed delivery states: evidence binding to the exact
> untouched PDF/checksum across retries; ingestion proven by a durable
> archive document result + checksum readback or a verified relation to a
> previously archived original; uncertain-effect reconciliation before
> resend; per-account / per-notice separation; changed originals preserved
> with no financial correction inferred from a byte change; missing,
> incomplete or ambiguous evidence never silently suppresses a document.]

## Cross-references

- Commitments + acceptance criteria:
  `1792861675256-issue27-maintainer-commitments.md` (C4, C8).
- #24 agreed contract (crash-recovery half, delivered via PR #33): issue
  comments 6352296709, 6449976998, 6560325739.
- #50 no-op terminal result: issue body + the 2026-11-01 reply
  (comment 6560325930).
- #52 archive-side boundaries: issue body + the 2026-11-01 reply
  (comment 6560326227).
- #26 collection window: PR #34 (`doc` contract, `variables.py`).
- #33 / #41 delivered groundwork: `downloads.py`, `notice.py`,
  `doc/DOWNLOAD_RECOVERY.md`, `doc/NOTICE_IDENTITY.md`.
