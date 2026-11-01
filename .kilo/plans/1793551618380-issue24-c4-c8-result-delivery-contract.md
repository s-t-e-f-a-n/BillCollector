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
- 2026-11-01: C4+C8 design posted to issue #24 for agreement (comment 6561111249, 2026-11-01T17:06:07Z) — awaiting confirmation; implementation follows agreement in the planned order (Delivery A: C4, then Delivery B: C8), after which issue #24 closes and the #52 archive-receipt interface proposal is posted.

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

## Implementation plan (after agreement)

Two deliveries, each via the dev-commits cycle (per-item user confirmation) +
ff-only promotion + GitHub mirror, in this order:

1. **Delivery A — C4**: `Run.collection_outcome` + `Run.date_from` (schema +
   migration), outcome derivation at run finalization, `run_result` mapping,
   `allow_empty` option (schema + `collection.py` + runner adapter + contract
   docs), notification outcome + window, UI run-outcome display, README /
   CHANGELOG, the C4 test set above.
2. **Delivery B — C8**: `failed` state + `delivery_attempts`, recovery retry
   extension, manual-retry daemon action (subprocess), UI Delivery column +
   retry action, failed-transition notification, `doc/DOWNLOAD_RECOVERY.md`
   extension (state machine + F10 statement) + README pointer, the C8 test set
   above.

Then: close issue #24 as delivered (its 2026-11-01 comment states it stays
open until the state exposure lands), and post the drafted #52
archive-receipt interface proposal to #52 for agreement.

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
