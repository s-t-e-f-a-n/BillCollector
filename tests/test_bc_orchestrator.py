# -*- coding: utf-8 -*-
"""Unit tests for the orchestrator spawn/monitor (M1 chunk C7.2).

``start_run`` claims the task (DB row lock), acquires the global
semaphore, spawns the runner subprocess, monitors it to exit, and
finalizes the Run row. The runner itself creates the Run row and (on the
normal path) finalizes it, so the tests use a stub runner: a real
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
import sys
import tempfile
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


class StartRunTests(OrchestratorTestBase):
    """start_run spawns the runner, monitors the exit, finalizes the Run."""

    def test_successful_run_keeps_the_runner_result_and_releases_the_task(self):
        task_id = self.db.create_task("svc", "u1", enabled=True)
        exit_code = asyncio.run(self.orch.start_run(task_id))
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
        exit_code = asyncio.run(self._orch(mode="fail").start_run(task_id))
        self.assertEqual(exit_code, 1)
        run = self.db.list_runs(task_id)[0]
        self.assertEqual(run["result"], "failure")
        self.assertIsNotNone(run["ended_at"])
        self.assertIn("Traceback (most recent call last):", run["notes"])
        self.assertIn("RuntimeError: stub runner failure", run["notes"])
        self.assertEqual(self.db.get_task(task_id)["status"], "idle")

    def test_pause_timeout_result_is_not_overwritten_by_the_exit_code(self):
        task_id = self.db.create_task("svc", "u1", enabled=True)
        exit_code = asyncio.run(self._orch(mode="timeout").start_run(task_id))
        self.assertEqual(exit_code, 1)
        run = self.db.list_runs(task_id)[0]
        # The runner's pause-outcome result (needs_attention) wins over a
        # generic failure derived from the non-zero exit code.
        self.assertEqual(run["result"], "needs_attention")
        self.assertIn("RuntimeError: stub runner failure", run["notes"])

    def test_crashed_runner_is_finalized_by_the_orchestrator(self):
        task_id = self.db.create_task("svc", "u1", enabled=True)
        exit_code = asyncio.run(self._orch(mode="crash").start_run(task_id))
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
        exit_code = asyncio.run(self._orch(mode="earlyfail").start_run(task_id))
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
        exit_code = asyncio.run(self._orch(mode="fail").start_run(task_id))
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
        exit_code = asyncio.run(self.orch.start_run(task_id))
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
            return await asyncio.gather(orch.start_run(t1), orch.start_run(t2))

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


if __name__ == "__main__":
    unittest.main()
