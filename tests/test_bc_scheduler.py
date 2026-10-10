# -*- coding: utf-8 -*-
"""Unit tests for the per-task cron scheduler (M1 chunk C7.1).

The Task table is the source of truth: ``resync()`` rebuilds the
APScheduler jobstore (persistent, in the same bc.db file) from it and
``sync_task()`` keeps one job in step with a single task. The run callback
is a stub recorder and no job fires within the test window (monthly crons).
"""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import scheduler  # noqa: E402
from billcollector.db import Database  # noqa: E402
from billcollector.scheduler import TaskScheduler, job_id_for  # noqa: E402


class SchedulerTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.db = Database(self.tmp / "bc.db")
        self.calls = []

        async def run_stub(task_id):
            self.calls.append(task_id)

        self.sched = TaskScheduler(self.db, run_stub)

    def tearDown(self):
        self.sched.stop()
        scheduler._run_callback = None
        self.db.close()
        self._tmp.cleanup()

    def _field(self, job, name):
        return next(f for f in job.trigger.fields if f.name == name)

    def _start_stop_cycle(self):
        """Run one scheduler start/stop cycle (AsyncIOScheduler needs the
        running loop) and return the job ids while it was running."""
        async def cycle():
            self.sched.start()
            try:
                return [j.id for j in self.sched.scheduler.get_jobs()]
            finally:
                self.sched.stop()
        return asyncio.run(cycle())


class JobSyncTests(SchedulerTestBase):
    """resync()/sync_task() keep the job table in step with the Task table."""

    def test_enabled_task_with_cron_produces_a_job(self):
        task_id = self.db.create_task("svc", "u1", enabled=True, cron="0 0 1 * *")
        self.sched.resync()
        job = self.sched.scheduler.get_job(job_id_for(task_id))
        self.assertIsNotNone(job)
        self.assertEqual(job.args, (task_id,))
        self.assertEqual(str(self._field(job, "minute").expressions[0]), "0")
        self.assertEqual(str(self._field(job, "hour").expressions[0]), "0")
        self.assertEqual(str(self._field(job, "day").expressions[0]), "1")

    def test_disabled_task_produces_no_job(self):
        # create_task defaults to enabled=False (imported tasks start disabled).
        self.db.create_task("svc", "u1", cron="0 0 1 * *")
        self.sched.resync()
        self.assertEqual(self.sched.scheduler.get_jobs(), [])

    def test_enabled_task_without_cron_produces_no_job(self):
        self.db.create_task("svc", "u1", enabled=True)
        self.sched.resync()
        self.assertEqual(self.sched.scheduler.get_jobs(), [])

    def test_disabling_the_task_removes_its_job(self):
        task_id = self.db.create_task("svc", "u1", enabled=True, cron="0 0 1 * *")
        self.sched.resync()
        self.assertIsNotNone(self.sched.scheduler.get_job(job_id_for(task_id)))
        self.db.update_task(task_id, enabled=False)
        self.sched.sync_task(task_id)
        self.assertIsNone(self.sched.scheduler.get_job(job_id_for(task_id)))

    def test_resync_rebuilds_all_jobs_from_the_task_table(self):
        self.db.create_task("on", "u1", enabled=True, cron="0 0 1 * *")
        self.db.create_task("off", "u2", enabled=False, cron="0 0 1 * *")
        self.db.create_task("nocront", "u3", enabled=True)
        self.sched.resync()
        jobs = self.sched.scheduler.get_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].id, job_id_for(
            self.db.get_task_by_service_user("on", "u1")["id"]))

    def test_resync_drops_the_job_of_a_deleted_task(self):
        task_id = self.db.create_task("svc", "u1", enabled=True, cron="0 0 1 * *")
        self.sched.resync()
        self.assertIsNotNone(self.sched.scheduler.get_job(job_id_for(task_id)))
        self.db.conn.execute("DELETE FROM Task WHERE id=?", (task_id,))
        self.db.conn.commit()
        self.sched.resync()
        self.assertEqual(self.sched.scheduler.get_jobs(), [])


class PersistenceTests(SchedulerTestBase):
    """The jobstore persists in bc.db and the startup resync rebuilds the
    job table from the Task table on a fresh scheduler instance."""

    def test_jobs_survive_a_scheduler_restart(self):
        self.db.create_task("svc", "u1", enabled=True, cron="0 0 1 * *")
        running_jobs = self._start_stop_cycle()
        self.assertEqual(len(running_jobs), 1)

        # A fresh instance (as after a daemon restart) re-syncs from the
        # Task table; the job is back with the same id.
        async def run_stub(task_id):
            pass
        fresh = TaskScheduler(self.db, run_stub)
        try:
            fresh.resync()
            task_id = self.db.get_task_by_service_user("svc", "u1")["id"]
            job = fresh.scheduler.get_job(job_id_for(task_id))
            self.assertIsNotNone(job)
            self.assertEqual(job.args, (task_id,))
        finally:
            fresh.stop()

    def test_resync_drops_stale_jobs_from_the_previous_instance(self):
        # The jobstore still holds the job of a task that was deleted since
        # the last shutdown; the startup resync must drop it.
        task_id = self.db.create_task("svc", "u1", enabled=True, cron="0 0 1 * *")
        self._start_stop_cycle()
        self.db.conn.execute("DELETE FROM Task WHERE id=?", (task_id,))
        self.db.conn.commit()

        async def run_stub(task_id):
            pass
        fresh = TaskScheduler(self.db, run_stub)
        try:
            fresh.resync()
            self.assertEqual(fresh.scheduler.get_jobs(), [])
        finally:
            fresh.stop()

    def test_task_job_dispatches_to_the_run_callback(self):
        # The fired job target awaits the configured run callback with the
        # task id (firing itself needs a live minute-boundary, out of the
        # unit suite's window).
        task_id = self.db.create_task("svc", "u1")
        asyncio.run(scheduler._task_job(task_id))
        self.assertEqual(self.calls, [task_id])


if __name__ == "__main__":
    unittest.main()
