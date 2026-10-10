# -*- coding: utf-8 -*-
"""Unit tests for the runner's retry/graceful decision logic, the C5.4/C5.5
pause wiring, and the C5.6 terminal results (no vault, no browser, no
network)."""

import json
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError  # noqa: E402

from billcollector import config, pause, runner  # noqa: E402
from billcollector.control import ControlClient  # noqa: E402
from billcollector.db import Database  # noqa: E402
from billcollector.runner import (  # noqa: E402
    MAX_STEP_ATTEMPTS,
    PauseOutcomeAbort,
    StepAbortError,
    _execute_step_with_pause,
    _handle_download_with_pause,
    run_result,
    step_attempts,
    transform_step_to_json,
)


class RetryDecisionTests(unittest.TestCase):
    def test_graceful_steps_are_single_attempt(self):
        self.assertEqual(step_attempts(True), 1)

    def test_non_graceful_steps_retry_up_to_three_times(self):
        self.assertEqual(MAX_STEP_ATTEMPTS, 3)
        self.assertEqual(step_attempts(False), MAX_STEP_ATTEMPTS)


class RunResultTests(unittest.TestCase):
    def test_aborted_run_is_failure(self):
        self.assertEqual(run_result(True, [{"result": "success"}]), "failure")

    def test_completed_run_without_downloads_is_failure(self):
        # Legacy success contract: success needs at least one download.
        self.assertEqual(run_result(False, []), "failure")

    def test_run_with_a_failed_download_is_failure(self):
        files = [{"result": "success"},
                 {"result": "failure: download error boom"}]
        self.assertEqual(run_result(False, files), "failure")

    def test_completed_run_with_successful_downloads_is_success(self):
        files = [{"result": "success"}, {"result": "success"}]
        self.assertEqual(run_result(False, files), "success")

    def test_pause_outcome_cancel_is_cancelled(self):
        self.assertEqual(run_result(True, [], "cancel"), "cancelled")

    def test_pause_outcome_timeout_is_needs_attention(self):
        self.assertEqual(run_result(True, [{"result": "success"}], "timeout"),
                         "needs_attention")


class _FakePageState:
    locator_action = '{"description":"d","locators":[],"actions":[]}'
    error_status = {"error": [{"method": "click", "message": "boom"}]}


class _FakeCtx:
    """Bare context: pause_loop is patched, so nothing else is touched."""


class StepPauseWiringTests(unittest.TestCase):
    """C5.4: the step loop pauses on an exhausted StepAbortError; a resume
    re-executes the step, cancel/timeout abort with their terminal outcome."""

    step = {"step": 7, "description": "Click the button",
            "methods": [{"method": "click", "arguments": [{"name": "Button"}]}]}

    def _failing_execute_step(self):
        calls = []

        def fake_execute_step(ctx, step):
            calls.append(step)
            if len(calls) == 1:
                raise StepAbortError("Step 7 failed: boom", page_state=_FakePageState())
            return "state"
        return fake_execute_step, calls

    def test_resume_reruns_the_step_with_fresh_budget(self):
        fake_execute_step, calls = self._failing_execute_step()
        with mock.patch.object(runner, "_execute_step", fake_execute_step), \
                mock.patch.object(runner, "pause_loop", return_value="resume") as pause:
            state = _execute_step_with_pause(_FakeCtx(), self.step)
        self.assertEqual(state, "state")
        self.assertEqual(len(calls), 2)
        args = pause.call_args[0]
        self.assertEqual(args[1], "step_failed")
        self.assertEqual(args[3], _FakePageState.locator_action)
        self.assertEqual(args[4], _FakePageState.error_status)
        self.assertIn("Step 7", args[2])

    def test_cancel_aborts_with_terminal_outcome(self):
        fake_execute_step, _ = self._failing_execute_step()
        with mock.patch.object(runner, "_execute_step", fake_execute_step), \
                mock.patch.object(runner, "pause_loop", return_value="cancel"):
            with self.assertRaises(PauseOutcomeAbort) as caught:
                _execute_step_with_pause(_FakeCtx(), self.step)
        self.assertEqual(caught.exception.outcome, "cancel")

    def test_timeout_aborts_with_terminal_outcome(self):
        fake_execute_step, _ = self._failing_execute_step()
        with mock.patch.object(runner, "_execute_step", fake_execute_step), \
                mock.patch.object(runner, "pause_loop", return_value="timeout"):
            with self.assertRaises(PauseOutcomeAbort) as caught:
                _execute_step_with_pause(_FakeCtx(), self.step)
        self.assertEqual(caught.exception.outcome, "timeout")

    def test_download_failure_pauses_with_download_failed_reason(self):
        step = {"step": 14, "description": "Download the invoice",
                "methods": [{"method": "expect_download", "arguments": []}],
                "steps": []}
        with mock.patch.object(runner, "_handle_download",
                               side_effect=[StepAbortError("no download"), None]), \
                mock.patch.object(runner, "pause_loop", return_value="resume") as pause:
            _handle_download_with_pause(_FakeCtx(), step)
        args = pause.call_args[0]
        self.assertEqual(args[1], "download_failed")
        self.assertEqual(args[3], transform_step_to_json(step))
        self.assertIn("Step 14", args[2])

    def test_download_failure_cancel_aborts(self):
        step = {"step": 14, "description": "Download the invoice",
                "methods": [{"method": "expect_download", "arguments": []}],
                "steps": []}
        with mock.patch.object(runner, "_handle_download", side_effect=StepAbortError("no download")), \
                mock.patch.object(runner, "pause_loop", return_value="cancel"):
            with self.assertRaises(PauseOutcomeAbort) as caught:
                _handle_download_with_pause(_FakeCtx(), step)
        self.assertEqual(caught.exception.outcome, "cancel")


class _FakePage:
    """A page without recipe methods: every dispatched step fails instantly
    (AttributeError -> StepAbortError), so the pause is reached without
    waiting out Playwright's per-attempt timeouts. The element scan and the
    pause-context page reads answer the same way as test_bc_pause.FakePage."""

    url = "http://127.0.0.1:8787/fake/"

    def title(self):
        return "Fake page"

    def inner_text(self, selector):
        return "fake body"

    def evaluate(self, script):
        if "MutationObserver" in script:
            return True
        return []

    def screenshot(self, path=None):
        if path is not None:
            Path(path).write_bytes(b"FAKEPNG")
        return b"FAKEPNG"

    def close(self):
        pass


class _FakeContext:
    def __init__(self):
        self._page = _FakePage()

    def new_page(self):
        return self._page

    def close(self):
        pass


class _FakePlaywrightManager:
    """Stand-in for ``sync_playwright()``: the real ``_launch_browser`` runs
    (profile setup included), only the browser factory is faked."""

    def __enter__(self):
        chromium = mock.Mock()
        chromium.launch_persistent_context.return_value = _FakeContext()
        self.playwright = mock.Mock(chromium=chromium)
        return self.playwright

    def __exit__(self, *exc):
        return False


class RunTaskOutcomeTests(unittest.TestCase):
    """C5.6: terminal results of a paused run at the Run-row level.

    A real ``run_task`` with only the vault preflight, the recipe check and
    the browser factory stubbed: the step loop, the 3x retry, the pause loop
    (real ControlServer, real deadline math) and the terminal result mapping
    all run for real. One step that clicks an element the fake page does not
    have exhausts its attempts instantly and pauses the run."""

    RECIPE = {
        "services": [{
            "serviceName": "svc",
            "steps": [
                {"step": 1, "description": "Click",
                 "methods": [{"method": "click",
                              "arguments": [{"name": "Missing"}]}]},
            ],
        }]
    }

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._old_db_file = config.DB_FILE
        self._old_run_dir = config.RUN_DIR
        self._old_profile_root = config.PROFILE_ROOT
        config.DB_FILE = self.tmp / "bc.db"
        config.RUN_DIR = self.tmp / "runs"
        config.PROFILE_ROOT = self.tmp / "profiles"
        self.db = Database(self.tmp / "bc.db")
        self.task_id = self.db.create_task("svc", "u1")
        # No ntfy network access from the unit tests.
        self.db.set_setting("ntfy_topic", "")

    def tearDown(self):
        config.DB_FILE = self._old_db_file
        config.RUN_DIR = self._old_run_dir
        config.PROFILE_ROOT = self._old_profile_root
        self.db.close()
        self._tmp.cleanup()

    def _run_task(self, deadline_seconds=None):
        if deadline_seconds is not None:
            self.db.set_setting("pause_deadline_seconds", str(deadline_seconds))
        with mock.patch.object(runner, "CheckRecipe", return_value=self.RECIPE), \
                mock.patch.object(runner, "_vault_preflight",
                                  return_value={"user": "u1",
                                                "password": "p",
                                                "otp": "o"}), \
                mock.patch.object(runner, "sync_playwright",
                                  return_value=_FakePlaywrightManager()):
            return runner.run_task(self.task_id)

    def test_cancelled_run_ends_cancelled(self):
        # Bound the worst case: if the cancel thread ever fails to reach the
        # socket, the run times out after 20 s instead of the 30 min hold.
        self.db.set_setting("pause_deadline_seconds", "20")

        def cancel_when_paused():
            sock_path = pause.control_sock_path(1)
            deadline = time.time() + 25
            while not sock_path.exists():
                if time.time() > deadline:
                    return
                time.sleep(0.02)
            ControlClient(sock_path).request("cancel")

        thread = threading.Thread(target=cancel_when_paused)
        thread.start()
        try:
            exit_code = self._run_task()
        finally:
            thread.join(timeout=30)
        self.assertFalse(thread.is_alive())
        self.assertEqual(exit_code, 1)
        run = self.db.get_run(1)
        self.assertEqual(run["result"], "cancelled")
        self.assertEqual(run["pause_reason"], "step_failed")
        self.assertIsNotNone(run["ended_at"])
        self.assertEqual(self.db.get_task(self.task_id)["status"], "idle")
        self.assertFalse(pause.control_sock_path(1).exists())

    def test_timed_out_run_ends_needs_attention_and_keeps_the_profile(self):
        profile_dir = config.profile_dir_for("svc", "u1")
        profile_dir.mkdir(parents=True, exist_ok=True)
        marker = profile_dir / "marker.txt"
        marker.write_text("persist me", encoding="utf-8")
        history = profile_dir / "Default" / "History"
        history.parent.mkdir(parents=True, exist_ok=True)
        history.write_text("stale", encoding="utf-8")

        exit_code = self._run_task(deadline_seconds=1)

        self.assertEqual(exit_code, 1)
        run = self.db.get_run(1)
        self.assertEqual(run["result"], "needs_attention")
        self.assertEqual(run["pause_reason"], "step_failed")
        self.assertIsNotNone(run["ended_at"])
        # The deadline came from the pause_deadline_seconds setting (1 s),
        # not the 30 min default.
        delta = (pause.parse_ts(run["pause_deadline_at"])
                 - pause.parse_ts(run["started_at"])).total_seconds()
        self.assertGreaterEqual(delta, 0.5)
        self.assertLessEqual(delta, 10)
        context = json.loads(run["pause_context"])
        self.assertEqual(context["reason"], "step_failed")
        self.assertEqual(context["deadline_at"], run["pause_deadline_at"])
        # C5.6 / decision 9: the profile is preserved on timeout - only the
        # stale history is wiped before launch, cookies/contents survive.
        self.assertTrue(marker.exists())
        self.assertTrue((profile_dir / "Default" / "Preferences").exists())
        self.assertFalse(history.exists())
        self.assertEqual(self.db.get_task(self.task_id)["status"], "idle")


class _UntilLocator:
    """A fake Playwright locator with a scripted wait_for outcome: each
    entry is None (found) or the exception instance to raise."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def wait_for(self, state=None, timeout=None):
        self.calls.append({"state": state, "timeout": timeout})
        if not self.outcomes:
            return None
        outcome = self.outcomes.pop(0)
        if outcome is not None:
            raise outcome
        return None


class _UntilPage:
    """A fake page exposing the Playwright locator factory methods that the
    until-locator mapping can select."""

    def __init__(self, locator):
        self._locator = locator
        self.calls = []

    def evaluate(self, script):
        # The element scan is not under test here.
        return None

    def _make(self, name, kwargs):
        self.calls.append((name, kwargs))
        return self._locator

    def get_by_role(self, **kwargs):
        return self._make("get_by_role", kwargs)

    def get_by_test_id(self, **kwargs):
        return self._make("get_by_test_id", kwargs)

    def get_by_placeholder(self, **kwargs):
        return self._make("get_by_placeholder", kwargs)

    def get_by_label(self, **kwargs):
        return self._make("get_by_label", kwargs)

    def get_by_text(self, **kwargs):
        return self._make("get_by_text", kwargs)

    def locator(self, **kwargs):
        return self._make("locator", kwargs)


class WaitUserTests(unittest.TestCase):
    """C5.5: a wait_user step pauses before execution (reason=wait_user) and
    completes on resume (consumed, not re-executed); an until locator, when
    given, must be visible before the step completes (bounded by the pause
    deadline, a miss re-pauses with the same prompt)."""

    step = {"step": 11, "description": "Wait for the operator",
            "methods": [{"method": "wait_user",
                         "arguments": [{"prompt": "Type the code"}]}]}

    def _ctx(self, page):
        ctx = _FakeCtx()
        ctx.page = page
        ctx.bcs = mock.Mock(service="waituser")
        ctx.last_pause_deadline = datetime.now() + timedelta(seconds=60)
        return ctx

    def _until_step(self, until):
        return {"step": 11, "description": "Wait for the operator",
                "methods": [{"method": "wait_user",
                             "arguments": [{"prompt": "p"}, {"until": until}]}]}

    def test_wait_user_method_is_detected(self):
        self.assertIsNotNone(runner._wait_user_method(self.step))
        normal = {"step": 1, "methods": [{"method": "click", "arguments": []}]}
        self.assertIsNone(runner._wait_user_method(normal))

    def test_wait_user_args_extract_prompt_and_until(self):
        method = {"method": "wait_user",
                  "arguments": [{"prompt": "p"}, {"until": {"role": "link"}}]}
        self.assertEqual(runner._wait_user_args(self.step, method),
                         ("p", {"role": "link"}))
        # prompt and until may also share one argument dict.
        method2 = {"method": "wait_user",
                   "arguments": [{"prompt": "p", "until": {"text": "t"}}]}
        self.assertEqual(runner._wait_user_args(self.step, method2),
                         ("p", {"text": "t"}))

    def test_wait_user_prompt_falls_back_to_the_step_prompt(self):
        method = {"method": "wait_user", "arguments": []}
        prompt, until = runner._wait_user_args(self.step, method)
        self.assertIsNone(until)
        self.assertIn("Step 11", prompt)

    def test_locator_for_builds_the_matching_locator_method(self):
        for until, expected in (
                ({"role": "link", "name": "My account"}, "get_by_role"),
                ({"test_id": "done"}, "get_by_test_id"),
                ({"placeholder": "code"}, "get_by_placeholder"),
                ({"label": "code"}, "get_by_label"),
                ({"text": "Done", "exact": True}, "get_by_text"),
                ({"selector": "#done"}, "locator")):
            page = _UntilPage(_UntilLocator([]))
            runner._locator_for(page, until)
            self.assertEqual(page.calls, [(expected, until)])

    def test_locator_for_rejects_unrecognized_dicts(self):
        page = _UntilPage(_UntilLocator([]))
        with self.assertRaises(ValueError):
            runner._locator_for(page, {"bogus": 1})
        with self.assertRaises(ValueError):
            runner._locator_for(page, "not a dict")

    def test_resume_completes_the_step_without_reexecution(self):
        ctx = self._ctx(_UntilPage(_UntilLocator([])))
        with mock.patch.object(runner, "pause_loop", return_value="resume") as pause, \
                mock.patch.object(runner, "_record_step") as record:
            runner._execute_wait_user_step(
                ctx, self.step, runner._wait_user_method(self.step))
        self.assertEqual(pause.call_count, 1)
        args = pause.call_args[0]
        self.assertEqual(args[1], "wait_user")
        self.assertEqual(args[2], "Type the code")
        self.assertEqual(args[3], transform_step_to_json(self.step))
        self.assertIsNone(args[4])  # no error on a wait_user pause
        self.assertEqual(record.call_count, 1)
        state = record.call_args[0][1]
        self.assertEqual(state.locator_action, transform_step_to_json(self.step))
        self.assertEqual(state.error_status, {})

    def test_until_completes_when_the_locator_is_visible(self):
        locator = _UntilLocator([None])
        ctx = self._ctx(_UntilPage(locator))
        step = self._until_step({"role": "link", "name": "My account"})
        with mock.patch.object(runner, "pause_loop", return_value="resume") as pause, \
                mock.patch.object(runner, "_record_step"):
            runner._execute_wait_user_step(ctx, step, runner._wait_user_method(step))
        self.assertEqual(pause.call_count, 1)
        self.assertEqual(locator.calls[0]["state"], "visible")
        self.assertGreaterEqual(locator.calls[0]["timeout"], 0)
        self.assertLessEqual(locator.calls[0]["timeout"], 60000)

    def test_until_repauses_when_the_locator_is_not_found_in_time(self):
        locator = _UntilLocator([PlaywrightTimeoutError("deadline"), None])
        ctx = self._ctx(_UntilPage(locator))
        step = self._until_step({"role": "link", "name": "My account"})
        with mock.patch.object(runner, "pause_loop", return_value="resume") as pause, \
                mock.patch.object(runner, "_record_step") as record:
            runner._execute_wait_user_step(ctx, step, runner._wait_user_method(step))
        self.assertEqual(pause.call_count, 2)
        self.assertEqual(len(locator.calls), 2)
        self.assertEqual(record.call_count, 1)

    def test_until_cancel_aborts_before_completion(self):
        locator = _UntilLocator([None])
        ctx = self._ctx(_UntilPage(locator))
        step = self._until_step({"role": "link", "name": "My account"})
        with mock.patch.object(runner, "pause_loop", return_value="cancel"), \
                mock.patch.object(runner, "_record_step") as record:
            with self.assertRaises(PauseOutcomeAbort) as caught:
                runner._execute_wait_user_step(ctx, step, runner._wait_user_method(step))
        self.assertEqual(caught.exception.outcome, "cancel")
        self.assertEqual(locator.calls, [])
        record.assert_not_called()

    def test_invalid_until_aborts_before_any_pause(self):
        ctx = self._ctx(_UntilPage(_UntilLocator([])))
        step = self._until_step({"bogus": 1})
        with mock.patch.object(runner, "pause_loop") as pause, \
                mock.patch.object(runner, "_record_step") as record:
            with self.assertRaises(StepAbortError):
                runner._execute_wait_user_step(ctx, step, runner._wait_user_method(step))
        pause.assert_not_called()
        record.assert_not_called()


if __name__ == "__main__":
    unittest.main()
