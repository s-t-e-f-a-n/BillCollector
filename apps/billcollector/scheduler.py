# -*- coding: utf-8 -*-
"""Per-task cron scheduling for the daemon (M1 chunk C7.1).

The Task table is the source of truth for what runs when. This module
mirrors it into an APScheduler ``AsyncIOScheduler`` backed by a persistent
SQLAlchemy jobstore in the same ``bc.db`` file:

- ``resync()`` (the startup hook) rebuilds the job table from the Task
  table: every stored job is dropped and one job is re-added per enabled
  task that carries a cron expression. The jobstore is a cache - the Task
  table always wins.
- ``sync_task(task_id)`` is the single-task hook for task changes (the M2
  task CRUD: create, enable/disable, cron edit).

One cron job per task (job id ``task-<id>``). The job target is the
module-level :func:`_task_job` (importable by the jobstore, which persists
it by reference and re-imports it after a daemon restart); it awaits the
run callback configured on the scheduler (the orchestrator's ``start_run``).
Job defaults: coalesced missed fires, at most one concurrent instance per
job (the DB row lock is the second guard), and no misfire grace window -
a missed monthly run still runs on the next daemon start.
"""

import logging
import re

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .db import Database
from .variables import daemon_timezone

logger = logging.getLogger("billcollector.scheduler")


def cron_trigger(expression: str, timezone=None) -> CronTrigger:
    """Use cron's numeric weekdays (0/7 Sunday), not APScheduler's Monday=0.

    Convert numeric lists/ranges/steps before the pinned APScheduler parser.
    Other fields and named weekday expressions retain that parser's semantics.
    """
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("Cron requires five fields")
    names = ("sun", "mon", "tue", "wed", "thu", "fri", "sat", "sun")
    weekdays = []
    for item in fields[4].split(","):
        if not any(c.isdigit() for c in item):
            weekdays.append(item)
            continue
        match = re.fullmatch(r"(\*|[0-7](?:-[0-7])?)(?:/([1-9][0-9]*))?", item)
        if not match:
            raise ValueError("Invalid numeric cron weekday")
        base, step = match.groups()
        if base == "*":
            start, end = 0, 6
        elif "-" in base:
            start, end = map(int, base.split("-"))
        else:
            if step is not None:
                raise ValueError("Cron weekday steps require a range or wildcard")
            start = end = int(base)
        if start > end:
            raise ValueError("Cron weekday range must ascend")
        weekdays.extend(names[day] for day in range(start, end + 1, int(step or 1)))
    fields[4] = ",".join(dict.fromkeys(weekdays))
    return CronTrigger.from_crontab(" ".join(fields), timezone=timezone)


def job_id_for(task_id: int) -> str:
    """Stable APScheduler job id for one task (one cron job per task)."""
    return f"task-{task_id}"


# The run callback a fired job awaits (async callable taking a task_id).
# Set by TaskScheduler at construction; module-level so the jobstore can
# persist the importable _task_job reference and dispatch here at fire time.
_run_callback = None


async def _task_job(task_id: int) -> None:
    """Job target: module-level (the SQLAlchemy jobstore stores it by
    importable reference and re-imports it after a daemon restart)."""
    if _run_callback is None:
        raise RuntimeError("scheduler fired a task job without a run callback")
    await _run_callback(task_id)


class TaskScheduler:
    """One cron job per enabled Task, mirrored into the APScheduler jobstore."""

    def __init__(self, db: Database, run_func):
        if not callable(run_func):
            raise TypeError("run_func must be an async callable taking a task_id")
        global _run_callback
        self._db = db
        _run_callback = run_func
        self._timezone = daemon_timezone()
        self._scheduler = AsyncIOScheduler(
            timezone=self._timezone,
            jobstores={"default": SQLAlchemyJobStore(url=f"sqlite:///{db.path}")},
            job_defaults={"coalesce": True, "max_instances": 1,
                          "misfire_grace_time": None})

    @property
    def scheduler(self) -> AsyncIOScheduler:
        """The underlying APScheduler (for M2 status display / tests)."""
        return self._scheduler

    def start(self) -> None:
        """Re-sync all jobs from the Task table and start the scheduler."""
        self._scheduler.start(paused=True)
        try:
            self.resync()
        except Exception:
            self._scheduler.shutdown(wait=False)
            raise
        self._scheduler.resume()
        logger.info("Scheduler started (%d job(s))",
                    len(self._scheduler.get_jobs()))

    def stop(self) -> None:
        """Stop the scheduler (no-op when it is not running).

        The asyncio executor cancels the job futures still in flight
        (APScheduler 3.x cannot honour ``wait`` for asyncio executors).
        On the serve shutdown path (this runs first, C7.5) that is
        harmless: a job that just started is at most between spawn and
        handoff, and the monitoring of its live runner is its own task
        that the orchestrator's shutdown awaits.
        """
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def resync(self) -> None:
        """Rebuild the job table from the Task table (startup hook): drop
        every stored job and re-add one per enabled task with a cron."""
        self._scheduler.remove_all_jobs()
        for task in self._db.list_tasks():
            self._add_job_for(task)

    def sync_task(self, task_id: int) -> None:
        """Add/update/remove the single job of one task (task change hook)."""
        self._remove_job(task_id)
        task = self._db.get_task(task_id)
        if task is not None:
            self._add_job_for(task)

    def _add_job_for(self, task) -> None:
        if not task["enabled"] or not task["cron"]:
            return
        try:
            trigger = cron_trigger(task["cron"], timezone=self._timezone)
        except ValueError as exc:
            logger.error("Task %s not scheduled: invalid cron (%s)", task["id"], exc)
            return
        self._scheduler.add_job(
            _task_job,
            trigger=trigger,
            args=[task["id"]],
            id=job_id_for(task["id"]),
            replace_existing=True)

    def _remove_job(self, task_id: int) -> None:
        job = self._scheduler.get_job(job_id_for(task_id))
        if job is not None:
            job.remove()
