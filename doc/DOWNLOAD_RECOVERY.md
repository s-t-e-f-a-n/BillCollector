# Download recovery

Contract: upstream [issue #24](https://github.com/s-t-e-f-a-n/BillCollector/issues/24).
This change applies to daemon downloads. It does not change the legacy batch
tracker, recipe contract, control protocol or exit codes.

## Publication and delivery

1. Save the complete document under `<output>/.billcollector/<database-id>/<uuid>/`.
   The staging directory is on the output filesystem. Sync the file and a
   sanitized publication manifest before inserting its Download row.
2. Commit the Download row with `state=staged`, its checksum, output path and
   `staged_path`. No consumer has run at this point.
3. Rename the staged file into the output directory. Sync both directories.
   Commit `state=published`.
4. Call each configured consumer with `idempotency_key=<task_id>:<sha256>`.
   Commit `state=consumed` only after all consumers return successfully.
5. Remove the staging journal. Keep the Download row for dedup and audit.

The output-directory lock serializes publication and recovery across runner
processes. A new file cannot overwrite a previous managed publication. A name
collision gets a UUID suffix in `saved_path`; `filename` retains the original
portal name. A same-task/hash repeat retains an audit row and the original path; it does not publish another copy or trigger another delivery.

Consumers must accept repeated delivery with the same key. A crash after an
external effect but before its state commit can repeat every consumer, including
ones that previously succeeded. This is at-least-once delivery, not exactly-once.
Consumer errors move the row to `failed` (see Delivery states and retry) without
failing the recipe. Exceptions are not logged verbatim. Shutdown signals
propagate and preserve pending state. No configured consumers means that
publication completes immediately.

## Delivery states and retry

A Download row exposes four delivery states:

| Exposed state | Row state | Meaning |
|---|---|---|
| downloaded | `staged` | row committed, bytes staged, not yet published (transient; visible after a crash between the row commit and publication) |
| pending delivery | `published` | atomically published; delivery not yet acknowledged by all registered consumers |
| delivered | `consumed` | all registered consumers acknowledged, or none registered |
| failed delivery (N) | `failed` | a delivery attempt failed (consumer exception or published-file checksum mismatch); N is the attempt count |

The state machine is `staged` → `published` → `consumed`, plus the `failed`
branch: a consumer exception or a published-file checksum mismatch stops the
consumer loop and moves the row to `failed`, incrementing its
`delivery_attempts` count (a nullable additive column; pre-existing rows keep
`NULL`). A successful delivery also increments the count and moves the row to
`consumed`. A failed delivery does not fail the recipe; the run continues.
When a row first transitions to `failed` — at run-time delivery or at startup
recovery — one best-effort ntfy notice goes out on the existing opt-in topic:
`delivery failed: <service> <user> <filename> (attempt N)`. A retry of a
`failed` row sends no further notice.

Two retry paths re-deliver a `failed` or still-pending row:

- **Manual retry**: the per-row **Retry delivery** action on the Downloads
  page and the task-detail downloads section. It runs the row's delivery in a
  runner subprocess (consumers stay out of the UI process, as in startup
  recovery), opening its own database connection and taking the target's
  publication lock; a `staged` row is published first. Missing, duplicate and
  already-delivered rows are refused. The confirmation dialog states that
  delivery is at-least-once and keyed on the task and the document's sha256.
  The same path is available from the command line as
  `python -m billcollector.downloads <db> --retry <id>`; it exits 0 only when
  the row is delivered.
- **Automatic retry**: every startup recovery (below) retries `failed` rows in
  addition to `staged` and `published` rows, on the same code path and the same
  idempotency key. There is no automatic retry cap: a row is retried on every
  startup until it delivers.

Both paths deliver at-least-once, keyed on task + sha256: a consumer may
receive the same document more than once and must tolerate re-delivery with
the same key. A retry re-checks the published file's checksum while the file
still exists; a file already moved by a downstream folder watcher does not
block delivery — the consumer receives the record and acts on the stable key.
Duplicate rows are never delivered and cannot be retried.

## Recovery

Recovery runs before the daemon starts its UI and scheduler, in a separate
Python subprocess with its own SQLite connection. It also runs at runner
startup, before recipe validation, display allocation, vault access or browser
startup, and before each tracked download. Consumers never run in the UI process.
A failed startup recovery prevents the daemon from starting.
The Settings-table key `download_recovery_timeout_seconds` (an advanced key,
not shown on the Settings page) limits this subprocess to 300 seconds by
default. Set its row in the `Settings` table to a positive integer number of
seconds to change the limit. Invalid values prevent startup. On timeout, the parent kills and
waits for the child, then reports that the daemon did not start. A nonzero child
exit reports its exit code. Neither diagnostic exposes document data or paths.
Recovery can resume from committed state on the next start. A timeout can
interrupt a consumer after its external effect, so the same stable key can be
delivered again.

- A committed staged row finishes publication and then delivers consumers.
- A published or failed row retries delivery with the same key. A row that
  still fails keeps its journal for the next retry.
- A consumed row only needs leftover journal cleanup.
- A partial or complete staged file without a row moves into the journal's
  `quarantine/` directory. Recovery does not publish uncertain staging bytes.
- A managed manifest with a matching published file but no row recovers a
  consumed row. It does not replay an unknown consumer effect.
- An unmanaged output file cannot be assigned to a task from its name alone.
  On a later download, an exact name/checksum match with no known Download row
  is adopted conservatively as consumed. Other files remain untouched.

A downstream folder watcher can move a published file before recovery. The
committed row retains its delivery obligation. A consumer must use the stable
key to handle an already ingested or moved document.

The journal namespace uses the absolute database path. Keep that path stable
when restarting. Back up the database and output, including `.billcollector`,
together. Changing the download directory does not discard pending rows: recovery
also visits roots retained in Download rows. Do not relocate an uncommitted
journal without its database or discard quarantine files before inspection.
Filesystem/SQLite failures propagate and stop dependent tracking. Checksum
mismatches or an occupied reserved destination stop recovery without overwrite.

## What delivered proves

The C8 (F10) finding's core question, stated as contract — what a plain
consume-folder integration can prove without an ingestion callback:

- **With no registered ingestion consumer (the default), `delivered` means
  "atomically published into the output directory with no delivery obligation
  outstanding" — and nothing about the archive.** The daemon's proof ends at
  the checksum-verified atomic rename: a durable row, staged bytes, and a
  rename ordered so a crash cannot produce a published file without a row
  (recovery reconstructs the row conservatively as delivered). A missed
  ingestion is discoverable in the row list; a duplicate ingestion is not, per
  the agreed issue #24 contract.
- **Ingestion proof requires a registered ingestion consumer** whose success
  means the archive acknowledged the document. The consumer slot (`CONSUMERS`)
  exists for exactly this; until one is registered and succeeds, a
  consume-folder integration can prove "the file arrived in the folder with
  the committed bytes", and the archive side must prove the rest (for example,
  the archive's document result with a matching checksum readback).
- **Re-delivery and moved files**: the bytes may already have left the folder
  (a watcher took them). Delivery hands off the record (idempotency key +
  metadata), not the file: a consumer must be able to act on the record alone
  when `saved_path` no longer exists — checksum-deduplicating consumers do by
  construction; a consumer that needs the bytes must treat a missing
  `saved_path` as "already handed off", not as an error.

## Migration and rollback

Schema changes are additive: `Download.state`, `Download.staged_path` and
`Download.delivery_attempts`.
Historical rows default to `consumed` with a `NULL` attempt count; migration
does not replay them.
No historical file scan or production data conversion is performed.

A local rollback reverts the contribution. Before running an older binary on
real data, stop runners and retain the database/output backup. Resolve pending
rows with the newer binary first. An older binary does not honor the new state
or recovery protocol. Deployment and live recovery require separate authority.

## Isolated verification

From a disposable checkout, with runtime and test dependencies installed:

```sh
apps/.venv/bin/python -m pytest tests/test_bc_downloads.py tests/test_bc_downloads_recovery.py tests/test_bc_db.py -q
LC_ALL=C apps/.venv/bin/python -m pytest tests/ -q
# The legacy harness expects its Service table in a fresh checkout.
PYTHONPATH=apps apps/.venv/bin/python -c 'from BillCollectorServices_pw import DatabaseManager; DatabaseManager("apps/db/bc.db").close_connection()'
apps/.venv/bin/python tests/run_regression.py --ini tests/bc_regression.ini
```

Expected: all pytest tests pass (environment-dependent skips are allowed), then
`VERDICT: PASS` from the mock-portal harness. Do not use `--vault`.
The crash tests kill only forked test children. They use temporary files and
SQLite databases. They verify before/after commit and rename, after consumer
effect, and after the consumed-state commit. A crash after a consumer effect
produces two deliveries with one stable key and one published document.
