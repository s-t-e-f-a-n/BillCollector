"""Post-download hook slot (decision 14).

Initially empty. To add a consumer, append a callable to ``CONSUMERS``; it is
called as ``consume(download: dict)`` for every new (non-duplicate) download,
inside the runner subprocess so a slow consumer never blocks the UI/scheduler.
``download`` carries the tracked record: run_id, task_id, url, filename, size,
sha256, saved_path.
"""

CONSUMERS = []
