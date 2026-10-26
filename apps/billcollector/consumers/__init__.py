"""Post-download hook slot with at-least-once delivery (issue #24).

Append callables to CONSUMERS. Each receives a dict containing run_id,
task_id, url (sanitized), filename, size, sha256, saved_path and
idempotency_key ("<task_id>:<sha256>"). The Download row is committed and
the file is published before any consumer runs.

Consumers run inside the runner subprocess. They MUST tolerate re-delivery
with the same idempotency_key: a crash after an effect and before the state
commit replays delivery. If any consumer raises, the document remains pending;
all consumers can be called again on recovery, including those that succeeded.
With no configured consumers, publication completes immediately.
"""

CONSUMERS = []
