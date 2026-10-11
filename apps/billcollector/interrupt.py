"""The runner's shutdown-signal exception (M1 chunk C7.5).

``RunInterrupted`` is raised by the runner's SIGTERM/SIGINT handler in the
main thread so a shutdown (the daemon's SIGTERM, Ctrl+C standalone) takes
the run's whole teardown with it instead of killing the process in place.

It lives in its own module (not in ``runner``) because the lower-level
modules the runner imports for the run path - ``pause`` (context building,
waiting loop) and ``control`` (the control-socket server) - must be able to
re-raise it from their best-effort ``except Exception`` handlers without
importing ``runner`` (which imports them; a direct import would be a cycle).
"""


class RunInterrupted(Exception):
    """The runner received a shutdown signal (SIGTERM/SIGINT) mid-run.

    Raised by the process' signal handler (main thread, C7.5) so the run
    teardown can run: the display stack is reaped, the claim released,
    and the run ends ``result=interrupted`` (distinct from a step failure
    and from a pause outcome). Without the handler the OS would kill the
    runner in place, leaking the display stack and a stale lockfile.

    Every best-effort ``except Exception`` handler on the runner's
    main-thread run path (page reads, screenshots, control actions) must
    re-raise it: a shutdown signal is not a page error to degrade around,
    it is the end of the run."""
