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
3. spawns the runner subprocess and monitors it to completion: streams its
   output line by line into the per-run log file
   (``<data>/logs/run-<id>.log``), keeps a tail in memory for ``Run.notes``,
   awaits the exit, and finalizes the Run row.

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

Display allocation and the Xvfb/x11vnc/websockify stack are runner-owned
(C6); the orchestrator never touches them.
"""

import asyncio
import logging
import sys
from collections import deque
from pathlib import Path

from . import config
from .db import Database, now

logger = logging.getLogger("billcollector.orchestrator")

# How many tail lines of a failed runner's output land in Run.notes: the
# traceback is what the operator needs, not the full log.
NOTES_TAIL_LINES = 100


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

    @property
    def processes(self) -> dict:
        """task_id -> live runner subprocess (status display / tests)."""
        return self._processes

    async def start_run(self, task_id: int):
        """Claim and start one run; monitor the runner until it exits.

        Returns the runner subprocess' exit code, or None when the run was
        not started (unknown task, task already running/waiting, spawn
        failure)."""
        task = self._db.get_task(task_id)
        if task is None:
            logger.warning("start_run: task %s does not exist; not started", task_id)
            return None
        if not self._db.claim_task_run(task_id):
            logger.info("start_run: task %s already running/waiting; skipped", task_id)
            return None
        await self._semaphore.acquire()
        try:
            proc = await self._spawn(task_id)
        except Exception as e:
            # The runner never started: release the claim so the task is
            # not wedged in 'running' (a started runner normally releases
            # it in its own teardown, but there is no runner here).
            self._db.set_task_status(task_id, "idle")
            logger.error("start_run: spawning the runner for task %s failed: %s",
                         task_id, e)
            return None
        self._processes[task_id] = proc
        try:
            return await self._monitor(task_id, proc)
        finally:
            self._processes.pop(task_id, None)
            self._semaphore.release()

    async def _spawn(self, task_id: int):
        """Spawn the runner subprocess (stderr merged into stdout, piped)."""
        return await asyncio.create_subprocess_exec(
            *self._runner_cmd, "run", str(task_id),
            cwd=str(config.APP_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=self._env,
        )

    async def _monitor(self, task_id: int, proc) -> int:
        """Stream the runner's output line by line and finalize the Run row
        once the subprocess has exited.

        Every stdout line (stderr merged in) is appended to the per-run log
        file ``<data>/logs/run-<id>.log`` (C7.3); the M2 ui.log push reads the
        same file. The Run row is created by the runner (which records its own
        pid), so the file is opened once that row exists: lines seen before
        that are buffered and flushed when the file opens. The last
        NOTES_TAIL_LINES lines are also kept in memory for Run.notes on a
        non-zero exit."""
        tail = deque(maxlen=NOTES_TAIL_LINES)
        pending = []       # stdout lines seen before the Run row exists
        log_fh = None      # the per-run log file, opened once the row is known

        def open_run_log():
            """Open the per-run log file now that the Run row exists and flush
            the lines buffered before it. No-op when the file is already open
            or the runner never created a row (early failure)."""
            nonlocal log_fh
            if log_fh is not None:
                return
            row = self._db.get_run_for_pid(task_id, proc.pid)
            if row is None:
                return
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

    def _finalize_run(self, task_id: int, pid: int, exit_code: int, tail) -> None:
        """Finalize the Run row the subprocess created (module docstring)."""
        row = self._db.get_run_for_pid(task_id, pid)
        if row is None:
            # The runner exited before creating its Run row (invalid
            # recipe, display allocation): it never took ownership of the
            # task, so the orchestrator releases the claim.
            self._db.set_task_status(task_id, "idle")
            logger.warning("start_run: no Run row for task %s (pid %s, exit %s); "
                           "runner output tail: %s", task_id, pid, exit_code,
                           "".join(tail).strip() or "(none)")
            return
        run_id = row["id"]
        updates = {}
        if row["result"] is None:
            # The runner died before its own finalization (hard crash,
            # killed subprocess): the exit code decides the terminal result
            # and the orchestrator releases the task (the runner's teardown
            # that normally does it never ran; a daemon restart with the
            # runner still alive is C7.4's startup orphan cleanup).
            updates["result"] = "success" if exit_code == 0 else "failure"
            updates["ended_at"] = now()
            self._db.set_task_status(task_id, "idle")
        if exit_code != 0:
            notes_tail = "".join(tail).strip()
            if notes_tail:
                existing = row["notes"] or ""
                updates["notes"] = (existing + "\n" if existing else "") + notes_tail
        if updates:
            self._db.update_run(run_id, **updates)
        logger.info("runner for task %s (run %s) exited with code %s",
                    task_id, run_id, exit_code)
