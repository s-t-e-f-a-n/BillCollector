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
collision gets a UUID suffix. A same-task/hash repeat retains an audit row and
the original path; it does not publish another copy or trigger another delivery.

Consumers must accept repeated delivery with the same key. A crash after an
external effect but before its state commit can repeat every consumer, including
ones that previously succeeded. This is at-least-once delivery, not exactly-once.
Consumer errors retain pending state without failing the recipe. Exceptions are
not logged verbatim. Shutdown signals propagate and preserve pending state.
No configured consumers means that publication completes immediately.

## Recovery

Recovery runs before the daemon starts its UI and scheduler, in a separate
Python subprocess with its own SQLite connection. It also runs at runner
startup, before recipe validation, display allocation, vault access or browser
startup, and before each tracked download. Consumers never run in the UI process.
A failed startup recovery prevents the daemon from starting.
The Settings key `download_recovery_timeout_seconds` limits this subprocess
to 300 seconds by default. Set a positive integer number of seconds to change
the limit. Invalid values prevent startup. On timeout, the parent kills and
waits for the child, then reports that the daemon did not start. A nonzero child
exit reports its exit code. Neither diagnostic exposes document data or paths.
Recovery can resume from committed state on the next start. A timeout can
interrupt a consumer after its external effect, so the same stable key can be
delivered again.

- A committed staged row finishes publication and then delivers consumers.
- A published row retries delivery with the same key.
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

## Migration and rollback

Schema changes are additive: `Download.state` and `Download.staged_path`.
Historical rows default to `consumed`; migration does not replay them.
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
apps/.venv/bin/python tests/run_regression.py --ini tests/bc_regression.ini
```

Expected: all pytest tests pass (environment-dependent skips are allowed), then
`VERDICT: PASS` from the mock-portal harness. Do not use `--vault`.
The crash tests kill only forked test children. They use temporary files and
SQLite databases. They verify before/after commit and rename, after consumer
effect, and after the consumed-state commit. A crash after a consumer effect
produces two deliveries with one stable key and one published document.
