# -*- coding: utf-8 -*-
"""Unit tests for the orchestrator spawn/monitor (M1 chunk C7.2).

``start_run`` (the scheduler job) claims the task (DB row lock),
acquires the global semaphore, spawns the runner subprocess, and hands
the monitoring to its own asyncio task (C7.5), which monitors the exit
and finalizes the Run row. The runner itself creates the Run row and (on
the normal path) finalizes it, so the tests use a stub runner: a real
subprocess that mimics that contract (create the Run row with its own
pid, print output, optionally finalize the row + release the task,
exit). Stub modes (env ``ORCH_TEST_MODE``):

- ``ok``: finalize result=success, release the task, exit 0
- ``fail``: print a traceback, finalize result=failure, release the
  task, exit 1
- ``timeout``: print a traceback, finalize result=needs_attention,
  release the task, exit 1 (the runner's pause-timeout contract)
- ``crash``: print a traceback, exit 1 without finalizing (hard crash /
  killed subprocess)
- ``earlyfail``: exit 1 before creating the Run row (the real runner's
  invalid-recipe / display-allocation paths)
"""

import asyncio
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import config  # noqa: E402
from billcollector.db import Database  # noqa: E402
from billcollector.orchestrator import Orchestrator  # noqa: E402

# The stub runner: the same contract the real runner keeps for the
# orchestrator (create the Run row with its own pid, finalize + release
# the task on the normal path, exit 0 on success / 1 otherwise).
STUB_RUNNER = '''
import os
import sys
import time

sys.path.insert(0, os.environ["ORCH_TEST_APPS"])
from billcollector.db import Database, now  # noqa: E402

task_id = int(sys.argv[-1])
mode = os.environ.get("ORCH_TEST_MODE", "ok")
db = Database(os.environ["ORCH_TEST_DB"])
markers = os.environ.get("ORCH_TEST_MARKERS")


def mark(label):
    if markers:
        with open(markers, "a", encoding="utf-8") as f:
            f.write(f"{label}:{task_id}\\n")


mark("start")
print(f"stub runner for task {task_id} (mode={mode})")
if mode == "earlyfail":
    # The real runner's pre-Run-row failure paths (invalid recipe,
    # display allocation): exit 1 without creating the Run row or
    # releasing the task.
    db.close()
    mark("end")
    sys.exit(1)
run_id = db.create_run(task_id, pid=os.getpid())
if mode in ("fail", "crash", "timeout"):
    print("Traceback (most recent call last):")
    print('  File "fake.py", line 1, in <module>')
    print("RuntimeError: stub runner failure")
sleep = float(os.environ.get("ORCH_TEST_SLEEP", "0") or "0")
if sleep:
    time.sleep(sleep)
if mode == "ok":
    db.update_run(run_id, result="success", ended_at=now())
elif mode == "fail":
    db.update_run(run_id, result="failure", ended_at=now())
elif mode == "timeout":
    db.update_run(run_id, result="needs_attention", ended_at=now())
if mode in ("ok", "fail", "timeout"):
    db.set_task_status(task_id, "idle")
db.close()
mark("end")
sys.exit(0 if mode == "ok" else 1)
'''

# The C7.5 stub modes run after the Run row exists, replacing the normal
# tail. They emulate the two runner faces of the daemon's SIGTERM:
# gracefulterm - the real runner's SIGTERM handler (C7.5) finalizes the
# run itself and exits 1; stubborn - a runner that ignores SIGTERM with
# a display-stack grandchild in its process group (the group-signal
# contract of C7.5: the stack must die with the runner).
STUB_RUNNER_SIGNALS = '''
import os
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.environ["ORCH_TEST_APPS"])
from billcollector.db import Database, now  # noqa: E402

task_id = int(sys.argv[-1])
mode = os.environ.get("ORCH_TEST_MODE")
db = Database(os.environ["ORCH_TEST_DB"])
markers = os.environ.get("ORCH_TEST_MARKERS")


def mark(label):
    if markers:
        with open(markers, "a", encoding="utf-8") as f:
            f.write(f"{label}:{task_id}\\n")


run_id = db.create_run(task_id, pid=os.getpid())
mark("row")
if mode == "gracefulterm":
    def on_term(signum, frame):
        db.update_run(run_id, result="interrupted", ended_at=now())
        db.set_task_status(task_id, "idle")
        db.close()
        mark("end")
        sys.exit(1)

    signal.signal(signal.SIGTERM, on_term)
    mark("ready")  # the handler is in place; the test waits for this
elif mode == "stubborn":
    child = subprocess.Popen(["sleep", "300"])
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    mark(f"child:{child.pid}")
time.sleep(300)
db.close()
mark("end")
sys.exit(1)
'''


class OrchestratorTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.apps = Path(__file__).resolve().parents[1] / "apps"
        self.db_file = self.tmp / "bc.db"
        self.markers = self.tmp / "markers.txt"
        # The orchestrator streams each run's stdout to <data>/logs/run-<id>.log
        # (C7.3); point LOG_DIR at the temp dir so tests never write into the
        # repo's apps/data.
        self._old_log_dir = config.LOG_DIR
        config.LOG_DIR = self.tmp / "logs"
        self.db = Database(self.db_file)
        self.stub = self.tmp / "stub_runner.py"
        self.stub.write_text(STUB_RUNNER, encoding="utf-8")
        self.signal_stub = self.tmp / "signal_stub_runner.py"
        self.signal_stub.write_text(STUB_RUNNER_SIGNALS, encoding="utf-8")
        self.orch = Orchestrator(
            self.db, runner_cmd=[sys.executable, str(self.stub)],
            env=self._make_env())

    def tearDown(self):
        self.db.close()
        config.LOG_DIR = self._old_log_dir
        self._tmp.cleanup()

    def _make_env(self, mode="ok", sleep=0.0):
        env = {
            **os.environ,
            "ORCH_TEST_APPS": str(self.apps),
            "ORCH_TEST_DB": str(self.db_file),
            "ORCH_TEST_MODE": mode,
            "ORCH_TEST_MARKERS": str(self.markers),
        }
        if sleep:
            env["ORCH_TEST_SLEEP"] = str(sleep)
        return env

    def _orch(self, mode="ok", sleep=0.0):
        return Orchestrator(
            self.db, runner_cmd=[sys.executable, str(self.stub)],
            env=self._make_env(mode=mode, sleep=sleep))

    def _signal_orch(self, mode):
        return Orchestrator(
            self.db, runner_cmd=[sys.executable, str(self.signal_stub)],
            env=self._make_env(mode=mode))

    def _run_to_exit(self, orch, task_id):
        """Await start_run (the job) and then the run's monitor; returns
        the runner's exit code (C7.5: the monitoring is its own task)."""

        async def scenario():
            self.assertTrue(await orch.start_run(task_id))
            return await orch.monitors[task_id]

        return asyncio.run(scenario())


class StartRunTests(OrchestratorTestBase):
    """start_run spawns the runner; the monitor task monitors the exit and
    finalizes the Run."""

    def test_successful_run_keeps_the_runner_result_and_releases_the_task(self):
        task_id = self.db.create_task("svc", "u1", enabled=True)
        exit_code = self._run_to_exit(self.orch, task_id)
        self.assertEqual(exit_code, 0)
        run = self.db.list_runs(task_id)[0]
        self.assertIsNotNone(run["pid"])
        self.assertEqual(run["result"], "success")
        self.assertIsNotNone(run["ended_at"])
        self.assertIsNone(run["notes"])
        self.assertEqual(self.db.get_task(task_id)["status"], "idle")
        self.assertEqual(self.orch.processes, {})

    def test_failed_run_appends_the_traceback_tail_to_notes(self):
        task_id = self.db.create_task("svc", "u1", enabled=True)
        exit_code = self._run_to_exit(self._orch(mode="fail"), task_id)
        self.assertEqual(exit_code, 1)
        run = self.db.list_runs(task_id)[0]
        self.assertEqual(run["result"], "failure")
        self.assertIsNotNone(run["ended_at"])
        self.assertIn("Traceback (most recent call last):", run["notes"])
        self.assertIn("RuntimeError: stub runner failure", run["notes"])
        self.assertEqual(self.db.get_task(task_id)["status"], "idle")

    def test_pause_timeout_result_is_not_overwritten_by_the_exit_code(self):
        task_id = self.db.create_task("svc", "u1", enabled=True)
        exit_code = self._run_to_exit(self._orch(mode="timeout"), task_id)
        self.assertEqual(exit_code, 1)
        run = self.db.list_runs(task_id)[0]
        # The runner's pause-outcome result (needs_attention) wins over a
        # generic failure derived from the non-zero exit code.
        self.assertEqual(run["result"], "needs_attention")
        self.assertIn("RuntimeError: stub runner failure", run["notes"])

    def test_crashed_runner_is_finalized_by_the_orchestrator(self):
        task_id = self.db.create_task("svc", "u1", enabled=True)
        exit_code = self._run_to_exit(self._orch(mode="crash"), task_id)
        self.assertEqual(exit_code, 1)
        run = self.db.list_runs(task_id)[0]
        self.assertEqual(run["result"], "failure")
        self.assertIsNotNone(run["ended_at"])
        self.assertIn("RuntimeError: stub runner failure", run["notes"])
        # The killed runner's teardown never ran, so the orchestrator
        # released the task (a daemon restart with the runner still alive
        # is C7.4's startup orphan cleanup).
        self.assertEqual(self.db.get_task(task_id)["status"], "idle")

    def test_early_runner_failure_releases_the_claim(self):
        task_id = self.db.create_task("svc", "u1", enabled=True)
        exit_code = self._run_to_exit(self._orch(mode="earlyfail"), task_id)
        self.assertEqual(exit_code, 1)
        self.assertEqual(self.db.list_runs(task_id), [])
        self.assertEqual(self.db.get_task(task_id)["status"], "idle")


class SkipTests(OrchestratorTestBase):
    """start_run does not spawn when it cannot claim the task."""

    def test_unknown_task_is_not_started(self):
        self.assertIsNone(asyncio.run(self.orch.start_run(9999)))
        self.assertEqual(self.db.list_tasks(), [])

    def test_task_already_running_is_skipped(self):
        task_id = self.db.create_task("svc", "u1")
        self.db.set_task_status(task_id, "running")
        self.assertIsNone(asyncio.run(self.orch.start_run(task_id)))
        self.assertEqual(self.db.list_runs(task_id), [])
        self.assertEqual(self.db.get_task(task_id)["status"], "running")

    def test_task_already_waiting_is_skipped(self):
        task_id = self.db.create_task("svc", "u1")
        self.db.set_task_status(task_id, "waiting")
        self.assertIsNone(asyncio.run(self.orch.start_run(task_id)))
        self.assertEqual(self.db.list_runs(task_id), [])
        self.assertEqual(self.db.get_task(task_id)["status"], "waiting")


class SpawnFailureTests(OrchestratorTestBase):
    def test_spawn_failure_releases_the_claim(self):
        task_id = self.db.create_task("svc", "u1")
        orch = Orchestrator(
            self.db, runner_cmd=[str(self.tmp / "no-such-runner")],
            env=self._make_env())
        self.assertIsNone(asyncio.run(orch.start_run(task_id)))
        self.assertEqual(self.db.list_runs(task_id), [])
        self.assertEqual(self.db.get_task(task_id)["status"], "idle")


class RunLogTests(OrchestratorTestBase):
    """C7.3: the runner subprocess' stdout is streamed line by line into the
    per-run log file <data>/logs/run-<id>.log (the M2 ui.log push reads the
    same file)."""

    def test_stdout_before_and_after_the_run_row_lands_in_the_log_file(self):
        # 'fail' prints one line before it creates the Run row (buffered) and
        # the traceback lines after it: both must reach the log file, in order.
        task_id = self.db.create_task("svc", "u1", enabled=True)
        exit_code = self._run_to_exit(self._orch(mode="fail"), task_id)
        self.assertEqual(exit_code, 1)
        run = self.db.list_runs(task_id)[0]
        self.assertIsNotNone(run["log_path"])
        log = Path(run["log_path"])
        self.assertEqual(log.name, f"run-{run['id']}.log")
        self.assertTrue(log.is_relative_to(self.tmp))
        text = log.read_text(encoding="utf-8")
        self.assertIn(f"stub runner for task {task_id} (mode=fail)", text)
        self.assertIn("Traceback (most recent call last):", text)
        self.assertIn("RuntimeError: stub runner failure", text)
        # The pre-row line (buffered) precedes the post-row traceback.
        self.assertLess(text.index("stub runner for task"), text.index("Traceback"))

    def test_clean_run_writes_its_per_run_log_file(self):
        # 'ok' prints only the pre-row line: the file is still written once the
        # Run row is discovered after the process has fully exited.
        task_id = self.db.create_task("svc", "u1", enabled=True)
        exit_code = self._run_to_exit(self.orch, task_id)
        self.assertEqual(exit_code, 0)
        run = self.db.list_runs(task_id)[0]
        self.assertIsNotNone(run["log_path"])
        log = Path(run["log_path"])
        self.assertEqual(log.name, f"run-{run['id']}.log")
        self.assertIn(f"stub runner for task {task_id} (mode=ok)",
                      log.read_text(encoding="utf-8"))


class ConcurrencyTests(OrchestratorTestBase):
    def test_runs_are_serialized_by_the_global_semaphore(self):
        t1 = self.db.create_task("svc", "u1", enabled=True)
        t2 = self.db.create_task("svc", "u2", enabled=True)
        orch = self._orch(sleep=0.3)

        async def both():
            # Both jobs are in flight: t2's job blocks at the slot until
            # t1's monitor releases it. Each monitor is captured right
            # after its job returns - once the job is done the monitor is
            # in ``monitors`` and cannot have finished yet (the runner is
            # still sleeping).
            j1 = asyncio.create_task(orch.start_run(t1))
            j2 = asyncio.create_task(orch.start_run(t2))
            await j1
            m1 = orch.monitors[t1]
            await j2
            m2 = orch.monitors[t2]
            return await asyncio.gather(m1, m2)

        exit_codes = asyncio.run(both())
        self.assertEqual(sorted(exit_codes), [0, 0])
        self.assertEqual(len(self.db.list_runs(t1)), 1)
        self.assertEqual(len(self.db.list_runs(t2)), 1)
        lines = self.markers.read_text(encoding="utf-8").splitlines()
        start1, start2 = lines.index(f"start:{t1}"), lines.index(f"start:{t2}")
        end1, end2 = lines.index(f"end:{t1}"), lines.index(f"end:{t2}")
        # max_concurrency defaults to 1: the second run starts only after
        # the first has finished.
        self.assertTrue(start1 < end1 < start2 or start2 < end2 < start1)


class OrphanCleanupTests(OrchestratorTestBase):
    """C7.4: the startup cleanup marks leftover active runs whose pid is
    dead as interrupted (and frees their displays)."""

    def setUp(self):
        super().setUp()
        # The cleanup force-removes stale display lockfiles under
        # config.DISPLAY_DIR; redirect it like LOG_DIR so tests never
        # touch the repo's apps/data.
        self._old_display_dir = config.DISPLAY_DIR
        config.DISPLAY_DIR = self.tmp / "displays"
        config.DISPLAY_DIR.mkdir(parents=True)

    def tearDown(self):
        config.DISPLAY_DIR = self._old_display_dir
        super().tearDown()

    @staticmethod
    def _dead_pid() -> int:
        """A pid that is guaranteed to be dead (a spawned, reaped process)."""
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        return proc.pid

    def test_active_run_with_dead_pid_is_marked_interrupted(self):
        task_id = self.db.create_task("svc", "u1", enabled=True)
        run_id = self.db.create_run(task_id, pid=self._dead_pid())
        self.db.set_task_status(task_id, "running")
        self.assertEqual(self.orch.cleanup_orphans(), 1)
        run = self.db.get_run(run_id)
        self.assertEqual(run["result"], "interrupted")
        self.assertIsNotNone(run["ended_at"])
        # The killed runner's teardown never ran: the task is released.
        self.assertEqual(self.db.get_task(task_id)["status"], "idle")

    def test_active_run_with_a_live_pid_is_left_alone(self):
        # A still-alive orphaned runner finalizes the row itself.
        task_id = self.db.create_task("svc", "u1", enabled=True)
        run_id = self.db.create_run(task_id, pid=os.getpid())
        self.db.set_task_status(task_id, "running")
        self.assertEqual(self.orch.cleanup_orphans(), 0)
        self.assertIsNone(self.db.get_run(run_id)["result"])
        self.assertEqual(self.db.get_task(task_id)["status"], "running")

    def test_active_run_without_a_pid_is_marked_interrupted(self):
        # A row without a pid can never be a live run.
        task_id = self.db.create_task("svc", "u1")
        run_id = self.db.create_run(task_id)
        self.assertEqual(self.orch.cleanup_orphans(), 1)
        self.assertEqual(self.db.get_run(run_id)["result"], "interrupted")

    def test_orphan_display_lock_is_removed(self):
        task_id = self.db.create_task("svc", "u1")
        run_id = self.db.create_run(task_id, pid=self._dead_pid(), display=99)
        lock = config.DISPLAY_DIR / ":99.lock"
        lock.write_text("424242\n", encoding="utf-8")
        self.assertEqual(self.orch.cleanup_orphans(), 1)
        self.assertFalse(lock.exists())
        self.assertEqual(self.db.get_run(run_id)["result"], "interrupted")

    def test_finalized_runs_are_left_alone(self):
        task_id = self.db.create_task("svc", "u1")
        run_id = self.db.create_run(task_id, pid=self._dead_pid())
        self.db.update_run(run_id, result="success",
                           ended_at="2026-10-10 10:00:00")
        self.assertEqual(self.db.get_task(task_id)["status"], "idle")
        self.assertEqual(self.orch.cleanup_orphans(), 0)
        self.assertEqual(self.db.get_run(run_id)["result"], "success")


class ShutdownTests(OrchestratorTestBase):
    """C7.4: shutdown terminates the live runner subprocesses and marks
    their runs interrupted."""

    def test_shutdown_terminates_the_runner_and_interrupts_the_run(self):
        task_id = self.db.create_task("svc", "u1", enabled=True)
        orch = self._orch(mode="crash", sleep=30.0)  # a long-running run

        async def scenario():
            job = asyncio.create_task(orch.start_run(task_id))
            # Wait for the stub runner to have created its Run row (it
            # then sleeps without finalizing, like a long-running run).
            for _ in range(200):
                if self.db.list_runs(task_id):
                    break
                await asyncio.sleep(0.05)
            await orch.shutdown()
            await job
            return orch.processes

        self.assertEqual(asyncio.run(scenario()), {})
        run = self.db.list_runs(task_id)[0]
        self.assertEqual(run["result"], "interrupted")
        self.assertIsNotNone(run["ended_at"])
        # The killed runner's teardown never ran: the task is released.
        self.assertEqual(self.db.get_task(task_id)["status"], "idle")

    def test_shutdown_without_live_runners_is_a_noop(self):
        asyncio.run(self.orch.shutdown())
        self.assertEqual(self.orch.processes, {})


class ShutdownSignalTests(OrchestratorTestBase):
    """C7.5: shutdown signals the runner's whole process group.

    The runner is spawned in its own session (``start_new_session`` in
    ``_spawn``), and its display-stack children share that group (C6), so
    one ``killpg`` takes runner and stack down together. Two runner faces:
    ``gracefulterm`` mirrors the real runner's C7.5 SIGTERM handler (the
    runner finalizes its own run before exiting); ``stubborn`` is a runner
    that ignores SIGTERM while a grandchild (the display stack's stand-in)
    lives in its group - the group signal must still take the whole stack
    down, and the orchestrator's SIGKILL fallback the runner itself."""

    def _markers(self):
        if self.markers.exists():
            return self.markers.read_text(encoding="utf-8").splitlines()
        return []

    @staticmethod
    def _pid_alive(pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def test_shutdown_of_a_graceful_runner_keeps_its_own_result(self):
        # gracefulterm: the runner's own SIGTERM handler (the real
        # runner's C7.5 handler, mirrored) finalizes its run interrupted
        # and exits 1; the orchestrator must not overwrite that result.
        task_id = self.db.create_task("svc", "u1", enabled=True)
        orch = self._signal_orch(mode="gracefulterm")

        async def scenario():
            job = asyncio.create_task(orch.start_run(task_id))
            for _ in range(400):
                if f"ready:{task_id}" in self._markers():
                    break
                await asyncio.sleep(0.05)
            monitor = orch.monitors[task_id]  # the job handed off by now
            await orch.shutdown()
            await job
            return await monitor

        exit_code = asyncio.run(scenario())
        self.assertEqual(exit_code, 1)
        run = self.db.list_runs(task_id)[0]
        self.assertEqual(run["result"], "interrupted")
        self.assertIsNotNone(run["ended_at"])
        self.assertIsNone(run["notes"])
        self.assertEqual(self.db.get_task(task_id)["status"], "idle")
        self.assertEqual(orch.processes, {})
        self.assertIn(f"end:{task_id}", self._markers())

    def test_shutdown_of_a_stubborn_runner_kills_its_whole_group(self):
        # stubborn: the runner ignores SIGTERM and holds a sleep grandchild
        # in its process group (the display-stack contract). The group
        # SIGTERM kills the grandchild, the group SIGKILL (after
        # SHUTDOWN_TIMEOUT) takes the runner, and the orchestrator marks
        # the run the runner never finalized itself as interrupted.
        task_id = self.db.create_task("svc", "u1", enabled=True)
        orch = self._signal_orch(mode="stubborn")

        async def scenario():
            job = asyncio.create_task(orch.start_run(task_id))
            child_pid = None
            for _ in range(400):
                for line in self._markers():
                    if line.startswith("child:") and line.endswith(f":{task_id}"):
                        child_pid = int(line.split(":")[1])
                if child_pid is not None and self.db.list_runs(task_id):
                    break
                await asyncio.sleep(0.05)
            self.assertIsNotNone(child_pid)
            self.assertTrue(self._pid_alive(child_pid))
            await orch.shutdown()
            await job
            return child_pid

        child_pid = asyncio.run(scenario())
        run = self.db.list_runs(task_id)[0]
        self.assertEqual(run["result"], "interrupted")
        self.assertIsNotNone(run["ended_at"])
        self.assertEqual(self.db.get_task(task_id)["status"], "idle")
        self.assertEqual(orch.processes, {})
        # The group signal reached the grandchild: sleep dies on SIGTERM
        # even though its parent (the runner) ignored it. PID 1 reaps the
        # zombie shortly after the runner is SIGKILLed; give it a moment.
        deadline = time.time() + 5
        while self._pid_alive(child_pid) and time.time() < deadline:
            time.sleep(0.05)
        self.assertFalse(self._pid_alive(child_pid))


class JobCancelTests(OrchestratorTestBase):
    """C7.5: a daemon shutdown stops the scheduler and cancels whatever job
    coroutines are still running - but the monitoring of a spawned runner
    is never a job, so it survives. The only window in which the job is
    still running is between the claim and the handoff (waiting for the
    global slot, or mid-spawn): a cancellation there must release the
    claim, so the task is not wedged in 'running' without a run (the
    startup orphan cleanup only sees Run rows)."""

    def test_job_cancelled_while_waiting_for_the_slot_releases_the_claim(self):
        # max_concurrency=1: run A holds the slot (a long sleep), so run
        # B's job blocks at the semaphore. Cancelling B's job (the
        # scheduler stop) must release B's claim; A's monitor keeps
        # running until shutdown() reaps A's runner.
        t1 = self.db.create_task("svc", "u1", enabled=True)
        t2 = self.db.create_task("svc", "u2", enabled=True)
        orch = self._orch(mode="crash", sleep=30.0)

        async def scenario():
            self.assertTrue(await orch.start_run(t1))  # A holds the slot
            job = asyncio.create_task(orch.start_run(t2))
            for _ in range(200):
                if self.db.get_task(t2)["status"] == "running":
                    break
                await asyncio.sleep(0.05)
            self.assertIn(t1, orch.monitors)  # A is being monitored
            # A's runner must have created its Run row before the shutdown
            # signals the group: interpreter startup outlasts the claim, so
            # without this wait a slow start would SIGTERM the runner before
            # the row exists and the row would never appear.
            for _ in range(200):
                if self.db.list_runs(t1):
                    break
                await asyncio.sleep(0.05)
            job.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await job
            await orch.shutdown()
            return orch.processes, orch.monitors

        processes, monitors = asyncio.run(scenario())
        self.assertEqual(processes, {})
        self.assertEqual(monitors, {})
        # B's claim was released; B never spawned (no run row).
        self.assertEqual(self.db.get_task(t2)["status"], "idle")
        self.assertEqual(self.db.list_runs(t2), [])
        # A's run was interrupted by the shutdown; its task was released.
        run = self.db.list_runs(t1)[0]
        self.assertEqual(run["result"], "interrupted")
        self.assertEqual(self.db.get_task(t1)["status"], "idle")


if __name__ == "__main__":
    unittest.main()
