"""Task runner: executes one task run as a sync Playwright step loop.

This module is a deliberate chunk boundary: the step loop, pause subsystem,
and display management land in a later milestone chunk.
"""


def run_task(task_id: int, debug: bool = False) -> int:
    """Execute one task run (sync Playwright step loop).

    Stub: the step loop, pause subsystem and display management land in
    the next milestone chunk (M1 item 3).
    """
    raise NotImplementedError("runner not yet implemented")
