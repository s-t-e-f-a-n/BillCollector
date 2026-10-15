# -*- coding: utf-8 -*-
"""Unit tests for the runner's pause subsystem (M1 chunk C5).

Covers the pause context builder, the Run/task persist, the deadline math,
the coordinate-based Copilot action handlers, and the waiting loop (resume /
cancel / timeout) against a real ControlServer + ControlClient pair. No
browser, no vault, no network (the ntfy topic is emptied in the tests).
"""

import base64
import json
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import config, pause  # noqa: E402
from billcollector.control import ControlClient  # noqa: E402
from billcollector.db import Database  # noqa: E402

FAKE_PNG = b"FAKEPNG"
# Raw pagestate scan entries (the js_collect output shape: tag/innerText/...).
# PageState.set_interactive_elements derives the locator candidates:
# - the button yields n=1 (get_by_role) + n=2 (get_by_text),
# - the input yields n=3 (get_by_label) + n=4 (get_by_role).
ELEMENTS = [
    {
        "tag": "button",
        "innerText": "Verify",
        "computedText": "Verify",
        "ariaLabel": "",
        "title": "",
        "placeholder": "",
        "id": "",
        "onclick": "",
        "contenteditable": False,
        "href": "",
        "value": "",
        "labelText": "",
        "rect": {"x": 10, "y": 20, "w": 100, "h": 30},
    },
    {
        "tag": "input",
        "innerText": "",
        "computedText": "",
        "ariaLabel": "",
        "title": "",
        "placeholder": "6-digit code",
        "id": "",
        "onclick": "",
        "contenteditable": False,
        "href": "",
        "value": "",
        "labelText": "",
        "rect": {"x": 10, "y": 60, "w": 120, "h": 24},
    },
]


class FakeMouse:
    def __init__(self):
        self.calls = []

    def click(self, x, y):
        self.calls.append(("click", x, y))

    def move(self, x, y, steps=None):
        self.calls.append(("move", x, y, steps))

    def down(self):
        self.calls.append(("down",))

    def up(self):
        self.calls.append(("up",))


class FakeKeyboard:
    def __init__(self):
        self.calls = []

    def type(self, text):
        self.calls.append(("type", text))

    def press(self, key):
        self.calls.append(("press", key))


class FakePage:
    def __init__(self, elements=ELEMENTS, title="Page title",
                 url="http://127.0.0.1:8787/autopause/", body="visible body text"):
        self.url = url
        self._title = title
        self.body = body
        self.elements = elements
        self.mouse = FakeMouse()
        self.keyboard = FakeKeyboard()

    def title(self):
        return self._title

    def inner_text(self, selector):
        return self.body

    def evaluate(self, script):
        if "MutationObserver" in script:
            return True
        return self.elements

    def screenshot(self, path=None):
        if path is not None:
            Path(path).write_bytes(FAKE_PNG)
        return FAKE_PNG


class FakeCtx:
    def __init__(self, db, run_id, page):
        self.db = db
        self.run_id = run_id
        self.task = {"id": 1, "service": "svc", "user": "u1"}
        self.page = page
        self.pause_count = 0
        self.last_pause_context = None
        self.last_pause_deadline = None


class PauseTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        # Redirect run artifacts and the control socket into the temp dir.
        self._old_run_dir = config.RUN_DIR
        config.RUN_DIR = self.tmp / "runs"
        self.db = Database(self.tmp / "test.db")
        task_id = self.db.create_task("svc", "u1")
        self.run_id = self.db.create_run(task_id)
        self.page = FakePage()
        self.ctx = FakeCtx(self.db, self.run_id, self.page)

    def tearDown(self):
        self.db.close()
        config.RUN_DIR = self._old_run_dir
        self._tmp.cleanup()


class BuildPauseContextTests(PauseTestBase):
    def test_context_payload_shape(self):
        ctx = self.ctx
        ctx.pause_count = 1
        context = pause.build_pause_context(
            ctx, "step_failed", "Step 11 failed",
            json.dumps({"description": "d", "locators": [], "actions": []}),
            "boom", "2026-10-10 13:00:00", step_number=11)
        self.assertEqual(context["reason"], "step_failed")
        self.assertEqual(context["prompt"], "Step 11 failed")
        self.assertEqual(context["url"], "http://127.0.0.1:8787/autopause/")
        self.assertEqual(context["page_title"], "Page title")
        self.assertEqual(context["error"], "boom")
        self.assertEqual(context["step_number"], 11)
        self.assertEqual(context["step"]["description"], "d")
        self.assertEqual(context["deadline_at"], "2026-10-10 13:00:00")
        self.assertEqual(context["page_text"], "visible body text")

        shot = context["screenshot"]
        self.assertTrue(shot["path"])
        self.assertTrue(Path(shot["path"]).exists())
        self.assertEqual(base64.b64decode(shot["data"]), FAKE_PNG)

        elements = context["elements"]
        self.assertEqual([e["n"] for e in elements], [1, 2, 3, 4])
        self.assertEqual(elements[0]["role"], "button")
        self.assertEqual(elements[0]["name"], "Verify")
        self.assertEqual(elements[0]["rect"], {"x": 10, "y": 20, "w": 100, "h": 30})
        self.assertEqual(elements[2]["actionTypes"], ["click", "fill"])

    def test_step_number_defaults_to_none(self):
        # M3 decision 8: a pause without a step carries step_number=None.
        context = pause.build_pause_context(self.ctx, "wait_user", "p", None, None, "d")
        self.assertIsNone(context["step_number"])

    def test_page_text_is_capped(self):
        self.page.body = "x" * (pause.PAUSE_PAGE_TEXT_CAP + 5000)
        context = pause.build_pause_context(self.ctx, "wait_user", "p", None, None, "d")
        self.assertEqual(len(context["page_text"]), pause.PAUSE_PAGE_TEXT_CAP)

    def test_context_degrades_when_the_page_is_broken(self):
        page = FakePage()
        page.title = lambda: (_ for _ in ()).throw(RuntimeError("nav gone"))
        page.inner_text = lambda selector: (_ for _ in ()).throw(RuntimeError("nav gone"))
        page.evaluate = lambda script: (_ for _ in ()).throw(RuntimeError("nav gone"))
        page.screenshot = lambda path=None: (_ for _ in ()).throw(RuntimeError("nav gone"))
        ctx = FakeCtx(self.db, self.run_id, page)
        ctx.pause_count = 1
        context = pause.build_pause_context(ctx, "step_failed", "p", None, "e", "d")
        self.assertIsNone(context["page_title"])
        self.assertIsNone(context["page_text"])
        self.assertEqual(context["elements"], [])
        self.assertIsNone(context["screenshot"]["path"])
        self.assertIsNone(context["screenshot"]["data"])


class PersistPauseTests(PauseTestBase):
    def test_persist_pause_writes_run_row_and_task_status(self):
        context = {"reason": "step_failed", "prompt": "p"}
        pause.persist_pause(self.db, self.run_id, 1, "step_failed", "p",
                            context, "2026-10-10 13:00:00")
        run = self.db.get_run(self.run_id)
        self.assertEqual(run["pause_reason"], "step_failed")
        self.assertEqual(run["pause_prompt"], "p")
        self.assertEqual(json.loads(run["pause_context"]), context)
        self.assertEqual(run["pause_deadline_at"], "2026-10-10 13:00:00")
        task = self.db.get_task(1)
        self.assertEqual(task["status"], "waiting")


class DeadlineMathTests(unittest.TestCase):
    def test_deadline_after(self):
        ref = datetime(2026, 10, 10, 12, 0, 0)
        self.assertEqual(
            pause.deadline_after(90, reference=ref), "2026-10-10 12:01:30")

    def test_deadline_passed(self):
        self.assertFalse(pause.deadline_passed("2999-01-01 00:00:00"))
        self.assertTrue(pause.deadline_passed("2000-01-01 00:00:00"))


class ActionHandlerTests(PauseTestBase):
    def setUp(self):
        super().setUp()
        self.handlers = pause.make_action_handlers(self.ctx)

    def test_screenshot_returns_base64(self):
        response = self.handlers["screenshot"]()
        self.assertEqual(base64.b64decode(response["screenshot"]), FAKE_PNG)

    def test_elements_returns_numbered_scan(self):
        response = self.handlers["elements"]()
        self.assertEqual([e["n"] for e in response["elements"]], [1, 2, 3, 4])
        self.assertEqual(response["elements"][0]["name"], "Verify")

    def test_context_returns_the_last_pause_context(self):
        self.ctx.last_pause_context = {"reason": "wait_user"}
        self.assertEqual(self.handlers["context"](),
                         {"context": {"reason": "wait_user"}})

    def test_click_acts_on_the_rect_center(self):
        self.assertEqual(self.handlers["click"](1), {"action": "click", "n": 1})
        self.assertEqual(self.page.mouse.calls, [("click", 60.0, 35.0)])

    def test_click_rejects_unknown_elements(self):
        with self.assertRaises(ValueError):
            self.handlers["click"](99)
        with self.assertRaises(ValueError):
            self.handlers["click"](-1)
        self.assertEqual(self.page.mouse.calls, [])

    def test_fill_clicks_center_then_types(self):
        self.handlers["fill"](3, "123456")
        self.assertEqual(self.page.mouse.calls, [("click", 70.0, 72.0)])
        self.assertEqual(self.page.keyboard.calls, [("type", "123456")])

    def test_press_forwards_to_the_keyboard(self):
        self.assertEqual(self.handlers["press"]("Enter"),
                         {"action": "press", "key": "Enter"})
        self.assertEqual(self.page.keyboard.calls, [("press", "Enter")])

    def test_drag_moves_down_moves_up_from_the_center(self):
        self.handlers["drag"](1, dx=100, dy=10)
        self.assertEqual(self.page.mouse.calls, [
            ("move", 60.0, 35.0, None),
            ("down",),
            ("move", 160.0, 45.0, 10),
            ("up",),
        ])


class WaitingLoopTests(PauseTestBase):
    def setUp(self):
        super().setUp()
        # No ntfy network access from the unit tests.
        self.db.set_setting("ntfy_topic", "")

    def _wait_for_socket(self, timeout=10):
        sock_path = pause.control_sock_path(self.run_id)
        deadline = time.time() + timeout
        while not sock_path.exists():
            if time.time() > deadline:
                self.fail("control socket was not created")
            time.sleep(0.02)
        return sock_path

    def _run_pause(self, **pause_kwargs):
        outcome = {}

        def target():
            outcome["value"] = pause.pause_loop(self.ctx, **pause_kwargs)

        thread = threading.Thread(target=target)
        thread.start()
        return thread, outcome

    def test_resume_completes_the_pause(self):
        thread, outcome = self._run_pause(
            reason="step_failed", prompt="p",
            step_action_json=None, error="e", step_number=3)
        sock_path = self._wait_for_socket()
        client = ControlClient(sock_path)
        self.assertEqual(client.request("screenshot")["screenshot"],
                         base64.b64encode(FAKE_PNG).decode("ascii"))
        self.assertEqual(len(client.request("elements")["elements"]), 4)
        self.assertEqual(client.request("context")["context"]["reason"],
                         "step_failed")
        client.request("resume")
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(outcome["value"], "resume")

        run = self.db.get_run(self.run_id)
        self.assertEqual(run["pause_reason"], "step_failed")
        self.assertEqual(run["pause_prompt"], "p")
        self.assertTrue(run["pause_context"])
        self.assertEqual(json.loads(run["pause_context"])["step_number"], 3)
        self.assertEqual(run["control_sock"], str(sock_path))
        self.assertFalse(sock_path.exists())
        self.assertEqual(self.db.get_task(1)["status"], "waiting")

    def test_cancel_aborts_the_pause(self):
        thread, outcome = self._run_pause(
            reason="wait_user", prompt="p", step_action_json=None, error=None)
        sock_path = self._wait_for_socket()
        ControlClient(sock_path).request("cancel")
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(outcome["value"], "cancel")

    def test_deadline_exceeded_times_out(self):
        self.db.set_setting("pause_deadline_seconds", "1")
        thread, outcome = self._run_pause(
            reason="step_failed", prompt="p", step_action_json=None, error="e")
        self._wait_for_socket()
        thread.join(timeout=20)
        self.assertFalse(thread.is_alive())
        self.assertEqual(outcome["value"], "timeout")

    def test_pause_deadline_is_persisted_from_the_setting(self):
        # C5.6: the pause deadline comes from pause_deadline_seconds and is
        # persisted on the Run row (the waiting loop and the context both
        # read it back from there).
        self.db.set_setting("pause_deadline_seconds", "90")
        thread, outcome = self._run_pause(
            reason="step_failed", prompt="p", step_action_json=None, error="e")
        sock_path = self._wait_for_socket()
        ControlClient(sock_path).request("resume")
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        run = self.db.get_run(self.run_id)
        remaining = (pause.parse_ts(run["pause_deadline_at"])
                     - datetime.now()).total_seconds()
        self.assertGreaterEqual(remaining, 85)
        self.assertLessEqual(remaining, 95)
        self.assertEqual(
            pause.parse_ts(
                json.loads(run["pause_context"])["deadline_at"]),
            pause.parse_ts(run["pause_deadline_at"]))

    def test_ntfy_is_pushed_on_every_pause(self):
        # C5.6: every pause (not just the first) pushes the ntfy deep link.
        with mock.patch.object(pause.notify, "notify_pause",
                               return_value=True) as ntfy:
            for _ in range(2):
                thread, outcome = self._run_pause(
                    reason="step_failed", prompt="p",
                    step_action_json=None, error="e")
                sock_path = self._wait_for_socket()
                ControlClient(sock_path).request("cancel")
                thread.join(timeout=10)
                self.assertFalse(thread.is_alive())
                self.assertEqual(outcome["value"], "cancel")
        self.assertEqual(ntfy.call_count, 2)
        for call in ntfy.call_args_list:
            db_arg, run_arg, task_arg = call.args
            self.assertIs(db_arg, self.db)
            self.assertEqual(run_arg["id"], self.run_id)
            self.assertEqual(task_arg["id"], 1)

    def test_second_pause_increments_the_pause_counter(self):
        thread, outcome = self._run_pause(
            reason="step_failed", prompt="p", step_action_json=None, error="e")
        sock_path = self._wait_for_socket()
        ControlClient(sock_path).request("cancel")
        thread.join(timeout=10)
        self.assertEqual(self.ctx.pause_count, 1)
        self.assertTrue((config.RUN_DIR / str(self.run_id) / "pause_1.png").exists())
        thread, outcome = self._run_pause(
            reason="step_failed", prompt="p2", step_action_json=None, error="e")
        self._wait_for_socket()
        ControlClient(pause.control_sock_path(self.run_id)).request("cancel")
        thread.join(timeout=10)
        self.assertEqual(self.ctx.pause_count, 2)
        self.assertTrue((config.RUN_DIR / str(self.run_id) / "pause_2.png").exists())


if __name__ == "__main__":
    unittest.main()
