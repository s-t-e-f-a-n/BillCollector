# -*- coding: utf-8 -*-
"""Orchestrator: spawn/monitor for task runs (M1 chunk C7.2).

Each task run is an isolated subprocess (``python -m billcollector run
<task_id>``) running the sync Playwright runner (decision 2): the daemon
process never imports scraping code, a runner crash cannot take down the
UI/scheduler, and the OS reclaims the runner's memory when it exits.

``start_run`` is the run callback the scheduler awaits (C7.1) and the M2
"run now" button will call. It:

1. claims the task with the DB row lock (``claim_task_run``) - a task that
   is already running/waiting is skipped, which also guards against a
   double queue entry for the same task;
2. acquires the global semaphore (``max_concurrency`` setting, default 1);
3. spawns the runner subprocess and hands off the monitoring to its own
   asyncio task (C7.5): the task streams the output line by line into the
   per-run log file (``<data>/logs/run-<id>.log``) and to the registered
   log subscribers (D2.2, the UI live-log push), keeps a tail in memory
   for ``Run.notes``, awaits the exit, and finalizes the Run row. The
   scheduler job itself only covers the claim/spawn/handoff, so a daemon
   shutdown that stops the scheduler (cancelling the running job) does not
   kill the monitoring of a live runner - ``shutdown`` terminates the
   runner and awaits the monitor.

Finalization on exit: the runner finalizes its own Run row with the
authoritative result (``success``/``failure``/``cancelled``/
``needs_attention``) and normally releases the task back to ``idle``
itself, so a non-zero exit code never overwrites its result. The
orchestrator only finalizes a row the runner left open (hard crash,
killed subprocess): exit 0 -> ``success``, non-zero -> ``failure`` - and
takes over the task release whenever the runner's own teardown did not
run (including a runner that exited before creating its Run row). On any
non-zero exit the tail of the subprocess output (the traceback) is
appended to ``Run.notes``.

C7.4 adds the two lifecycle edges:

- ``cleanup_orphans`` (the startup hook) marks every leftover active Run
  row (``result IS NULL``) whose runner pid is dead - or was never
  recorded - as ``interrupted``, force-frees its stale display lock, and
  releases the task back to ``idle``. A run whose pid is still alive is
  left alone: its orphaned runner finalizes the row and releases the
  task in its own teardown.
- ``shutdown`` (the SIGTERM hook, wired into ``serve`` in C7.5)
  terminates every live runner's whole process group (SIGTERM, then
  SIGKILL after ``SHUTDOWN_TIMEOUT``) and marks each run the runner did
  not finalize itself as ``interrupted``. The group signal reaches the
  display-stack children too (they share the runner's group, C6/C7.5),
  so a runner that cannot clean up still takes the stack down; the
  runner's own SIGTERM handler (C7.5) normally finalizes its run
  gracefully before the group signal matters.

C7.5 completes the lifecycle in ``serve`` (ui/app.py): on startup
``cleanup_orphans`` runs and the scheduler starts; on SIGTERM the
scheduler stops first (no new job can dispatch while runners are being
reaped) and then ``shutdown`` runs. The monitor being its own task (step
3) is what makes that order safe: stopping the scheduler cancels the
running job, not the monitoring of the live runner.

A runner killed by a signal (negative exit code) ends its still-open Run
row as ``interrupted`` rather than ``failure`` (the exit-code mapping in
:meth:`Orchestrator._finalize_run`).

D3.1 adds ``stop_run`` (the UI "Stop" button): it signals one task's live
runner (SIGTERM the group, SIGKILL after STOP_TIMEOUT) and lets the
runner's own handler / the monitor do the finalization, so a graceful
runner result is never overwritten.

Display allocation and the Xvfb/x11vnc/websockify stack are runner-owned
(C6); the orchestrator never touches them, except for force-removing the
stale lockfile of a dead run in ``cleanup_orphans``.
"""

import asyncio
import logging
import os
import signal
import sys
from collections import deque
from pathlib import Path

from . import config, display
from .db import Database, now
from .login import settle_attempt

logger = logging.getLogger("billcollector.orchestrator")

# How many tail lines of a failed runner's output land in Run.notes: the
# traceback is what the operator needs, not the full log.
NOTES_TAIL_LINES = 100

# How long shutdown() gives a runner to exit after SIGTERM before SIGKILL.
SHUTDOWN_TIMEOUT = 5.0

# How long stop_run() gives a runner to exit after SIGTERM before SIGKILL
# (dashboard spec: 10 s).
STOP_TIMEOUT = 10.0


def _pid_alive(pid: int) -> bool:
    """True when a process with the given pid currently exists."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # the pid exists but belongs to another user
    return True


def run_log_path(run_id: int) -> Path:
    """Per-run stdout log file: ``<data>/logs/run-<id>.log`` (C7.3)."""
    return config.LOG_DIR / f"run-{run_id}.log"


class Orchestrator:
    """Spawns one runner subprocess per run and monitors it to completion."""

    def __init__(self, db: Database, runner_cmd=None, env=None):
        self._db = db
        # The runner command: the real daemon uses the current interpreter
        # with the billcollector package (tests inject a stub runner).
        self._runner_cmd = list(runner_cmd) if runner_cmd else [
            sys.executable, "-m", "billcollector"]
        self._env = env
        self._semaphore = asyncio.Semaphore(
            int(db.get_setting("max_concurrency") or 1))
        # task_id -> runner subprocess of the currently spawned run (C7.4's
        # shutdown terminates these).
        self._processes = {}
        # task_id -> the run's monitoring task (C7.5): it outlives the
        # scheduler job that started it, so shutdown() can await it.
        self._monitors = {}
        # Registered log subscriber callables (D2.2): each runner stdout
        # line is pushed to them by the monitor (after the file write).
        self._log_subscribers = []
        self._notifications = set()

    def _dispatch_notification(self, send, *args):
        """Send immutable payloads off-loop; retain jobs until shutdown."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return send(*args)
        job = loop.create_task(asyncio.to_thread(send, *args))
        self._notifications.add(job)
        job.add_done_callback(self._notifications.discard)
        return job

    @property
    def processes(self) -> dict:
        """task_id -> live runner subprocess (status display / tests)."""
        return self._processes

    @property
    def monitors(self) -> dict:
        """task_id -> live monitoring task (status display / tests)."""
        return self._monitors

    def add_log_subscriber(self, callback) -> None:
        """Register a callback receiving each runner stdout line (D2.2).

        ``callback(task_id, run_id, line)`` is invoked by the monitor on
        the event-loop thread, after the line has been written to the
        per-run log file, in the same order the lines are written.
        ``run_id`` is None for the lines emitted before the runner has
        created its Run row. The UI's log panes register on connect and
        unregister on disconnect; a subscriber raising is caught + logged
        and never breaks the monitor."""
        self._log_subscribers.append(callback)

    def remove_log_subscriber(self, callback) -> None:
        """Unregister a log subscriber (a no-op when it is not registered)."""
        try:
            self._log_subscribers.remove(callback)
        except ValueError:
            pass

    def _emit_line(self, task_id: int, run_id, line: str) -> None:
        """Push one stdout line to all subscribers (a raising subscriber is
        caught + logged and skipped)."""
        for callback in list(self._log_subscribers):
            try:
                callback(task_id, run_id, line)
            except Exception:
                logger.exception("log subscriber raised for task %s; "
                                 "subscriber skipped", task_id)

    def cleanup_orphans(self) -> int:
        """Startup hook: mark leftover active runs whose runner process is
        dead as ``interrupted`` (C7.4).

        A daemon restart leaves Run rows open (``result IS NULL``). When
        the runner's pid is gone - or was never recorded - the run can
        never finalize itself: it is marked interrupted, its stale
        display lock is force-removed, and its task goes back to
        ``idle`` so the scheduler can claim it again. A run whose pid is
        still alive is left alone: its orphaned runner finalizes the row
        and releases the task in its own teardown.

        Returns the number of runs interrupted."""
        count = 0
        for run in self._db.list_active_runs():
            if run["pid"] is not None and _pid_alive(run["pid"]):
                continue
            self._db.update_run(run["id"], result="interrupted", ended_at=now())
            settle_attempt(self._db, run["task_id"], run["id"],
                           dispatch=self._dispatch_notification)
            if run["display"] is not None:
                display.remove_display_lock(run["display"])
            self._db.release_task_run(run["task_id"])
            count += 1
            logger.info("orphan cleanup: run %s (task %s, pid %s) marked interrupted",
                        run["id"], run["task_id"], run["pid"])
        if count:
            logger.info("orphan cleanup: %d leftover run(s) interrupted", count)
        # A crash can land after Run finalization but before attempt settlement.
        # Such a row is no longer part of list_active_runs(). A live orphan
        # runner still owns its pending proof, even when its row is finalized.
        for task in self._db.list_tasks():
            pending = task["login_pending_run_id"]
            if pending is None:
                continue
            run = self._db.get_run(pending)
            if run is not None and run["pid"] is not None and _pid_alive(run["pid"]):
                continue
            settle_attempt(self._db, task["id"], pending,
                           dispatch=self._dispatch_notification)
            self._db.release_task_run(task["id"])
        return count

    async def shutdown(self) -> None:
        """Shutdown hook: terminate every live runner and mark its run
        ``interrupted`` (C7.4, group signal per C7.5).

        Each runner's whole process group gets SIGTERM - the runner's
        display-stack children share the group (C6), so a runner that
        cannot clean up (e.g. stuck in a Playwright call) still takes the
        stack down; a group that does not exit within SHUTDOWN_TIMEOUT
        gets SIGKILL. The runner's own SIGTERM handler (C7.5) normally
        finalizes its run gracefully on the first signal. A run the
        runner did not finalize itself (``result IS NULL``) is marked
        interrupted and its task released back to ``idle`` - the runner's
        own teardown never ran. A run the runner already finalized is
        left untouched. A no-op when no runner is live."""
        for task_id, proc in list(self._processes.items()):
            if proc.returncode is None:
                self._signal_group(proc, signal.SIGTERM)
        for task_id, proc in list(self._processes.items()):
            try:
                await asyncio.wait_for(proc.wait(), timeout=SHUTDOWN_TIMEOUT)
            except asyncio.TimeoutError:
                logger.warning("runner for task %s ignored SIGTERM; killing", task_id)
                self._signal_group(proc, signal.SIGKILL)
                await proc.wait()
            row = self._db.get_run_for_pid(task_id, proc.pid)
            if row is not None and row["result"] is None:
                self._db.update_run(row["id"], result="interrupted", ended_at=now())
                settle_attempt(self._db, task_id, row["id"],
                               dispatch=self._dispatch_notification)
            self._db.release_task_run(task_id)
            logger.info("shutdown: runner for task %s terminated (pid %s)",
                        task_id, proc.pid)
        # All runners are reaped: their monitors now finish (per-run log
        # flush + finalization) and release their slots. Await them so no
        # monitor outlives the daemon (C7.5: the scheduler job may have
        # been cancelled by then, but the monitor is its own task).
        for task_id, monitor in list(self._monitors.items()):
            await monitor
        self._processes.clear()
        self._monitors.clear()
        if self._notifications:
            await asyncio.gather(*self._notifications)

    async def stop_run(self, task_id: int, timeout: float = STOP_TIMEOUT) -> bool:
        """Stop the task's live runner (D3.1): SIGTERM its process group,
        then SIGKILL after ``timeout`` (STOP_TIMEOUT: the dashboard spec's
        10 s; a shorter value is injectable for the tests).

        The orchestrator only signals - it never touches the Run row. The
        runner's own SIGTERM handler (C7.5) normally finalizes the run
        ``interrupted`` on the first signal; when it does not (a runner
        that ignores SIGTERM), the monitor finalizes the still-open row
        from the signal exit code. The monitor (still alive) releases the
        task and the global slot as usual. Returns False when the task
        has no live runner (nothing to stop)."""
        proc = self._processes.get(task_id)
        if proc is None or proc.returncode is not None:
            return False
        self._signal_group(proc, signal.SIGTERM)
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("runner for task %s ignored SIGTERM; killing", task_id)
            self._signal_group(proc, signal.SIGKILL)
            await proc.wait()
        return True

    @staticmethod
    def _signal_group(proc, signum) -> None:
        """Signal a runner's whole process group (the display-stack
        children share it). A process that does not lead its own group
        (test doubles) is signalled alone; a process that already exited
        is skipped."""
        try:
            pgid = os.getpgid(proc.pid)
        except (ProcessLookupError, PermissionError):
            return
        try:
            if pgid == proc.pid:
                os.killpg(pgid, signum)
            else:
                os.kill(proc.pid, signum)
        except ProcessLookupError:
            pass

    async def start_run(self, task_id: int):
        """Claim and start one run; the monitoring runs as its own task.

        Returns True when the run was started - the monitoring task (in
        ``monitors``) streams the output to the per-run log, awaits the
        exit, and finalizes the Run row; await it for the runner's exit
        code. Returns None when the run was not started (unknown task,
        task already running/waiting, spawn failure).

        This method is the scheduler job (C7.1): it only covers the
        claim/spawn/handoff. A daemon shutdown that stops the scheduler
        while the job is still running (waiting for the global slot, or
        mid-spawn) cancels the job - and only the job: the monitor of an
        already-spawned runner is its own task (C7.5) that ``shutdown``
        awaits."""
        task = self._db.get_task(task_id)
        if task is None:
            logger.warning("start_run: task %s does not exist; not started", task_id)
            return None
        if not self._db.claim_task_run(task_id):
            logger.info("start_run: task %s already running/waiting; skipped", task_id)
            return None
        try:
            await self._semaphore.acquire()
        except asyncio.CancelledError:
            # The job was cancelled while waiting for the global slot:
            # release the claim so the task is not wedged in 'running'
            # without a run (the startup orphan cleanup only sees rows).
            self._db.release_task_run(task_id)
            raise
        try:
            proc = await self._spawn(task_id)
        except asyncio.CancelledError:
            # Cancelled between the claim and the spawn: release slot +
            # claim (the runner never started).
            self._semaphore.release()
            self._db.release_task_run(task_id)
            raise
        except Exception as e:
            # The runner never started: release the claim so the task is
            # not wedged in 'running' (a started runner normally releases
            # it in its own teardown, but there is no runner here).
            self._semaphore.release()
            self._db.release_task_run(task_id)
            logger.error("start_run: spawning the runner for task %s failed: %s",
                         task_id, e)
            return None
        # The monitor is its own task (C7.5): it outlives this job, so a
        # scheduler stop (daemon shutdown) cannot cancel the monitoring of
        # the live runner.
        self._processes[task_id] = proc
        self._monitors[task_id] = asyncio.create_task(self._monitor(task_id, proc))
        return True

    async def _spawn(self, task_id: int):
        """Spawn the runner subprocess in its own session (stderr merged
        into stdout, piped).

        ``start_new_session`` makes the runner a session/group leader
        (pgid == pid) for two reasons: the display-stack children share
        that group (C6), so shutdown() can signal the whole stack with
        one killpg (C7.5); and a serve process killed with SIGKILL
        orphans the runner instead of dragging it down - C7.4's startup
        cleanup then sees the live pid and leaves the run to its
        orphaned runner."""
        return await asyncio.create_subprocess_exec(
            *self._runner_cmd, "run", str(task_id),
            cwd=str(config.APP_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=self._env,
            start_new_session=True,
        )

    async def _monitor(self, task_id: int, proc) -> int:
        """Stream the runner's output line by line and finalize the Run row
        once the subprocess has exited.

        Every stdout line (stderr merged in) is appended to the per-run log
        file ``<data>/logs/run-<id>.log`` (C7.3) and pushed to the registered
        log subscribers (D2.2) after the file write, in the same order the
        lines are written (``run_id`` is None while the row does not exist
        yet). The Run row is created by the runner (which records its own
        pid), so the file is opened once that row exists: lines seen before
        that are buffered and flushed (and emitted) when the file opens. The
        last NOTES_TAIL_LINES lines are also kept in memory for Run.notes on
        a non-zero exit."""
        tail = deque(maxlen=NOTES_TAIL_LINES)
        pending = []       # stdout lines seen before the Run row exists
        log_fh = None      # the per-run log file, opened once the row is known
        run_id = None      # known once the Run row exists (log subscribers)

        def open_run_log():
            """Open the per-run log file now that the Run row exists and flush
            the lines buffered before it. No-op when the file is already open
            or the runner never created a row (early failure)."""
            nonlocal log_fh, run_id
            if log_fh is not None:
                return
            row = self._db.get_run_for_pid(task_id, proc.pid)
            if row is None:
                return
            run_id = row["id"]
            path = run_log_path(row["id"])
            path.parent.mkdir(parents=True, exist_ok=True)
            log_fh = path.open("a", encoding="utf-8")
            # Record the log location on the row so the UI (M2) can find it.
            self._db.update_run(row["id"], log_path=str(path))
            for old in pending:
                log_fh.write(old)
            pending.clear()
            log_fh.flush()

        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace")
                tail.append(text)
                logger.debug("runner[%s]: %s", task_id, text.rstrip("\n"))
                if log_fh is not None:
                    log_fh.write(text)
                    log_fh.flush()
                else:
                    pending.append(text)
                    open_run_log()
                # Push the line to the subscribers after the file write
                # (D2.2): run_id is None while the runner has not created
                # its Run row yet.
                self._emit_line(task_id, run_id, text)
            exit_code = await proc.wait()
            # The runner may have created the Run row without printing any
            # further line (a clean run): discover it now that the process has
            # fully exited and its row is committed.
            open_run_log()
            self._finalize_run(task_id, proc.pid, exit_code, tail)
            return exit_code
        finally:
            if log_fh is not None:
                log_fh.close()
            # The monitor owns the run's bookkeeping (C7.5): it is the only
            # path that releases the slot and the tracking entries, whether
            # it ran to the end or the daemon shutdown signalled the runner
            # first (the scheduler job may have been cancelled meanwhile).
            self._processes.pop(task_id, None)
            self._monitors.pop(task_id, None)
            self._semaphore.release()

    def _finalize_run(self, task_id: int, pid: int, exit_code: int, tail) -> None:
        """Finalize the Run row the subprocess created (module docstring)."""
        row = self._db.get_run_for_pid(task_id, pid)
        if row is None:
            # The runner exited before creating its Run row (invalid
            # recipe, display allocation): it never took ownership of the
            # task, so the orchestrator releases the claim.
            self._db.release_task_run(task_id)
            logger.warning("start_run: no Run row for task %s (pid %s, exit %s); "
                           "runner output tail: %s", task_id, pid, exit_code,
                           "".join(tail).strip() or "(none)")
            return
        run_id = row["id"]
        settle_attempt(self._db, task_id, run_id,
                       dispatch=self._dispatch_notification)
        updates = {}
        if row["result"] is None:
            # The runner died before its own finalization (hard crash,
            # killed subprocess): the exit code decides the terminal result
            # and the orchestrator releases the task (the runner's teardown
            # that normally does it never ran; a daemon restart with the
            # runner still alive is C7.4's startup orphan cleanup). A
            # signal-killed runner (negative exit code) is interrupted,
            # not a failure (C7.4's shutdown kills the children this way).
            if exit_code == 0:
                updates["result"] = "success"
            elif exit_code < 0:
                updates["result"] = "interrupted"
            else:
                updates["result"] = "failure"
            updates["ended_at"] = now()
        if exit_code > 0:
            # A real non-zero exit: append the traceback tail (a
            # signal-killed runner has no traceback, only what it printed
            # before the signal).
            notes_tail = "".join(tail).strip()
            if notes_tail:
                existing = row["notes"] or ""
                updates["notes"] = (existing + "\n" if existing else "") + notes_tail
        if updates:
            self._db.update_run(run_id, **updates)
        self._db.release_task_run(task_id)
        logger.info("runner for task %s (run %s) exited with code %s",
                    task_id, run_id, exit_code)
