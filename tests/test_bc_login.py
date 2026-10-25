"""Issue #20: isolated durable budget, entry guards and real loopback submits."""

import asyncio
import copy
import fcntl
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import urlsplit
from unittest import mock

import pytest
import yaml
from playwright.sync_api import sync_playwright

from billcollector import config, runner
from billcollector.db import Database, SCHEMA
from billcollector.interrupt import RunInterrupted
from billcollector.login import login_options, settle_attempt, validate_login_recipe
from billcollector.orchestrator import Orchestrator
from billcollector.recipes import validate_recipe


@pytest.fixture(autouse=True)
def no_notification_network(monkeypatch):
    """A missing notification mock must fail locally, never contact ntfy."""
    def refuse(*args, **kwargs):
        raise AssertionError("Notification transport must be mocked in login tests")

    monkeypatch.setattr("billcollector.notify.requests.post", refuse)


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "login.db")
    database.set_setting("ntfy_topic", "")
    yield database
    database.close()


def task_run(db, limit=2):
    task = db.create_task("mock", "synthetic", enabled=True, cron="0 0 * * *")
    run = db.create_run(task)
    db.update_task(task, login_failure_limit=limit)
    return task, run


def login_step():
    return {
        "step": 2,
        "methods": [{"method": "login", "arguments": [
            {"success": {"selector": "#account"}}, {"timeout_ms": 500},
            {"session_timeout_ms": 1000}]}],
        "steps": [{"step": 21, "methods": [
            {"method": "locator", "arguments": [{"selector": "#password"}]},
            {"method": "fill", "arguments": [{"value": "synthetic-password"}]}]}],
        "submit": {"step": 22, "methods": [
            {"method": "locator", "arguments": [{"selector": "#submit"}]},
            {"method": "click"}]},
    }


def test_migrate_old_database_twice_preserves_data(tmp_path):
    path = tmp_path / "old.db"
    old_schema = "\n".join(line for line in SCHEMA.splitlines() if "login_" not in line)
    with sqlite3.connect(path) as conn:
        conn.executescript(old_schema)
        conn.execute("INSERT INTO Task(service,user,enabled) VALUES ('old','user',1)")
    for _ in range(2):
        with_db = Database(path)
        task = with_db.get_task(1)
        assert task["service"] == "old"
        assert task["enabled"] == 1
        assert task["login_failures"] == task["login_locked"] == 0
        assert task["login_pending_run_id"] is None
        with_db.close()


def test_durable_crash_budget_one_attempt_clear_and_success(db):
    task, run = task_run(db)
    assert db.reserve_login_attempt(task, run, 2)
    assert not db.claim_task_run(task)  # pending survives admission, even if idle
    assert not settle_attempt(db, task, run)
    assert not db.settle_login_attempt(task, run)  # idempotent
    second = db.create_run(task)
    assert db.reserve_login_attempt(task, second, 2)
    path = db.path
    other = Database(path)
    assert settle_attempt(other, task, second)
    assert not other.claim_task_run(task)
    third = other.create_run(task)
    assert not other.reserve_login_attempt(task, third, 2)
    assert other.clear_login_lock(task)
    assert other.get_task(task)["login_failures"] == 1
    assert other.get_task(task)["enabled"] == 1
    assert other.reserve_login_attempt(task, third, 2)
    other.login_succeeded(task, third)
    assert other.get_task(task)["login_failures"] == 0
    assert other.get_task(task)["login_pending_run_id"] is None
    other.close()


def test_clear_requires_idle_locked_task_without_pending_submission(db):
    task, run = task_run(db, 1)
    assert not db.clear_login_lock(task)
    assert db.reserve_login_attempt(task, run, 1)
    db.update_task(task, login_locked=1)
    assert not db.clear_login_lock(task)
    settle_attempt(db, task, run)
    db.set_task_status(task, "waiting")
    assert not db.clear_login_lock(task)
    db.set_task_status(task, "idle")
    assert db.clear_login_lock(task)


def test_concurrent_connections_can_reserve_only_one_attempt(db):
    task, run = task_run(db)

    def reserve(_):
        connection = Database(db.path)
        try:
            return connection.reserve_login_attempt(task, run, 2)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, range(2))) == [False, True]
    assert db.get_task(task)["login_failures"] == 1


def test_orphan_cleanup_consumes_pending_and_keeps_lock(db):
    task, run = task_run(db, 1)
    assert db.reserve_login_attempt(task, run, 1)
    db.set_task_status(task, "running")
    assert Orchestrator(db).cleanup_orphans() == 1
    assert db.get_task(task)["status"] == "idle"
    assert db.get_task(task)["login_locked"] == 1
    assert not db.claim_task_run(task)


def test_monitor_finalization_cannot_remove_login_lock(db):
    task, run = task_run(db, 1)
    db.update_run(run, pid=12345)
    assert db.reserve_login_attempt(task, run, 1)
    Orchestrator(db)._finalize_run(task, 12345, -9, [])
    assert db.get_task(task)["login_locked"] == 1
    assert db.get_run(run)["result"] == "interrupted"


async def test_blocked_manual_and_scheduled_admission_never_spawns(db):
    task, _ = task_run(db)
    db.update_task(task, login_locked=1)
    orchestrator = Orchestrator(db)
    with mock.patch.object(orchestrator, "_spawn") as spawn:
        assert await orchestrator.start_run(task) is None
        assert await orchestrator.start_run(task) is None
    spawn.assert_not_called()
    assert db.list_runs(task)[0]["pid"] is None


def test_blocked_direct_runner_stops_before_recipe_vault_or_display(db, monkeypatch):
    task, _ = task_run(db)
    db.update_task(task, login_locked=1)
    monkeypatch.setattr(config, "DB_FILE", db.path)
    with mock.patch.object(runner, "_install_signal_handlers"), \
            mock.patch.object(runner, "load_recipe") as recipe, \
            mock.patch.object(runner, "_vault_preflight") as vault, \
            mock.patch.object(runner.display, "allocate_display") as display:
        assert runner.run_task(task) == 1
    recipe.assert_not_called()
    vault.assert_not_called()
    display.assert_not_called()


@pytest.mark.parametrize("mutation", ["graceful", "nested", "prepare_click", "double_submit",
                                      "missing_proof", "negative_limit", "two_logins"])
def test_invalid_contract_rejected_by_runtime_and_ui(mutation):
    step = login_step()
    if mutation == "graceful":
        step["graceful"] = True
    elif mutation == "nested":
        step = {"step": 1, "methods": [{"method": "expect_download"}], "steps": [step]}
    elif mutation == "prepare_click":
        step["steps"][0]["methods"][-1] = {"method": "click"}
    elif mutation == "double_submit":
        step["submit"]["methods"].append({"method": "click"})
    elif mutation == "missing_proof":
        step["methods"][0]["arguments"] = []
    elif mutation == "negative_limit":
        step["methods"][0]["arguments"].append({"max_failures": -1})
    recipe = {"services": [{"serviceName": "mock", "steps": [step]}]}
    if mutation == "two_logins":
        recipe["services"][0]["steps"].append(copy.deepcopy(step))
    with pytest.raises(ValueError):
        validate_login_recipe(recipe)
    assert not validate_recipe(yaml.safe_dump(recipe))[0]


def test_valid_contract_accepted():
    recipe = {"services": [{"serviceName": "mock", "steps": [login_step()]}]}
    validate_login_recipe(recipe)
    assert validate_recipe(yaml.safe_dump(recipe))[0]
    assert login_options(login_step())["max_failures"] == 2


@pytest.fixture
def portal():
    state = SimpleNamespace(submissions=0, success=False, accept_submissions=False)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            body = ("<div id='account'>Account</div>" if state.success else
                    "<form method='post'><input id='password' name='password' type='password'>"
                    "<button id='submit'>Sign in</button></form>")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body.encode())

        def do_POST(self):
            state.submissions += 1
            if state.accept_submissions:
                state.success = True
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.url = f"http://127.0.0.1:{server.server_port}"
    yield state
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture
def browser_ctx(db, portal):
    task, run = task_run(db)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.route("**/*", lambda route: route.continue_()
                   if urlsplit(route.request.url).hostname == "127.0.0.1" else route.abort())
        page.goto(portal.url)
        context = SimpleNamespace(db=db, task=db.get_task(task), run_id=run, page=page,
                                  debug=False, bcs=SimpleNamespace(page=page, service="mock"))
        yield context
        browser.close()


def test_real_browser_failure_pause_resume_never_resubmits(browser_ctx, portal):
    ctx = browser_ctx
    pauses = []

    def pause(*_):
        pauses.append(portal.submissions)
        if len(pauses) == 2:
            portal.success = True  # simulate operator completing authentication
            ctx.page.goto(portal.url)
        return "resume"

    with mock.patch.object(runner, "pause_loop", side_effect=pause):
        runner._execute_login(ctx, login_step())
    assert pauses == [1, 1]
    assert portal.submissions == 1
    assert ctx.db.get_task(ctx.task["id"])["login_failures"] == 0


def test_real_browser_threshold_blocks_and_clear_grants_one_attempt(browser_ctx, portal):
    ctx = browser_ctx
    with mock.patch.object(runner, "pause_loop", return_value="timeout"):
        with pytest.raises(runner.PauseOutcomeAbort):
            runner._execute_login(ctx, login_step())
    assert portal.submissions == 1
    with mock.patch("billcollector.notify.notify_login_locked") as notify:
        with pytest.raises(runner.StepAbortError):
            runner._execute_login(ctx, login_step())
        notify.assert_called_once()
    assert portal.submissions == 2
    assert ctx.db.get_task(ctx.task["id"])["login_locked"] == 1
    assert ctx.db.clear_login_lock(ctx.task["id"])
    with pytest.raises(runner.StepAbortError):
        runner._execute_login(ctx, login_step())
    assert portal.submissions == 3
    assert ctx.db.get_task(ctx.task["id"])["login_locked"] == 1


def test_real_browser_existing_session_skips_and_resets(browser_ctx, portal):
    portal.success = True
    browser_ctx.page.goto(portal.url)
    browser_ctx.page.locator("#account").wait_for(state="visible")
    browser_ctx.db.update_task(browser_ctx.task["id"], login_failures=1)
    runner._execute_login(browser_ctx, login_step())
    assert portal.submissions == 0
    assert browser_ctx.db.get_task(browser_ctx.task["id"])["login_failures"] == 0


def test_interruption_after_reservation_remains_durable(browser_ctx):
    step = login_step()
    step["steps"] = []
    with mock.patch.object(runner, "_execute_step", side_effect=RunInterrupted("test")):
        with pytest.raises(RunInterrupted):
            runner._execute_login(browser_ctx, step)
    task = browser_ctx.db.get_task(browser_ctx.task["id"])
    assert task["login_failures"] == 1
    assert task["login_pending_run_id"] == browser_ctx.run_id


def test_prepare_failure_never_consumes_attempt(browser_ctx, portal):
    with mock.patch.object(runner, "_execute_step", side_effect=runner.StepAbortError("test")):
        with pytest.raises(runner.StepAbortError):
            runner._execute_login(browser_ctx, login_step())
    assert portal.submissions == 0
    assert browser_ctx.db.get_task(browser_ctx.task["id"])["login_failures"] == 0


def test_external_socket_transport_is_denied():
    with socket.socket() as connection, pytest.raises(AssertionError, match="loopback"):
        connection.connect(("192.0.2.1", 443))


def test_concurrent_direct_entry_stops_before_task_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    directory = tmp_path / "task-locks"
    directory.mkdir()
    with (directory / "task-7.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with mock.patch.object(runner, "_run_task") as execute:
            assert runner.run_task(7) == 1
            execute.assert_not_called()
    with mock.patch.object(runner, "_run_task", return_value=0) as execute:
        assert runner.run_task(7) == 0
        execute.assert_called_once_with(7, False)


def test_rejected_contender_cannot_release_active_task(db):
    task, run = task_run(db)
    db.set_task_status(task, "running")
    Orchestrator(db)._finalize_run(task, 98765, 1, [])
    assert db.get_task(task)["status"] == "running"
    db.update_run(run, result="interrupted")
    db.release_task_run(task)
    assert db.get_task(task)["status"] == "idle"


def test_foreign_or_completed_run_cannot_reset_budget(db):
    task, run = task_run(db)
    other_task = db.create_task("other", "synthetic")
    foreign = db.create_run(other_task)
    db.reserve_login_attempt(task, run, 2)
    assert not db.login_succeeded(task, foreign)
    db.update_run(run, result="failure")
    assert not db.login_succeeded(task, run)
    assert db.get_task(task)["login_failures"] == 1


def test_limit_cannot_increase_to_bypass_clear_budget(db):
    task, run = task_run(db)
    assert db.reserve_login_attempt(task, run, 2)
    settle_attempt(db, task, run)
    second = db.create_run(task)
    assert db.reserve_login_attempt(task, second, 9)
    assert db.get_task(task)["login_failure_limit"] == 2
    assert settle_attempt(db, task, second)
    assert db.clear_login_lock(task)
    third = db.create_run(task)
    assert db.reserve_login_attempt(task, third, 9)
    assert settle_attempt(db, task, third)


def test_notification_is_mocked_and_sent_once_per_block(db):
    task, run = task_run(db)
    db.set_setting("ntfy_topic", "synthetic-test-only")
    assert db.reserve_login_attempt(task, run, 1)
    with mock.patch("billcollector.notify.requests.post",
                    return_value=SimpleNamespace(status_code=200)) as post:
        assert settle_attempt(db, task, run)
        assert settle_attempt(db, task, run)
    post.assert_called_once()
    assert "blocked after 1" in post.call_args.kwargs["data"].decode()


@pytest.mark.parametrize("base", ["", "https://synthetic.invalid/ui/"])
def test_login_notification_links_require_a_base_url(db, base):
    task, run = task_run(db, 1)
    db.set_setting("ntfy_topic", "synthetic-test-only")
    db.set_setting("ui_base_url", base)
    assert db.reserve_login_attempt(task, run, 1)
    with mock.patch("billcollector.notify.requests.post",
                    return_value=SimpleNamespace(status_code=200)) as post:
        settle_attempt(db, task, run)
    message = post.call_args.kwargs["data"].decode()
    if base:
        assert message.endswith(f"\n{base.rstrip('/')}/tasks/{task}")
    else:
        assert "\n" not in message
        assert "/tasks/" not in message


@pytest.mark.parametrize("path", ["finalize", "orphan", "terminal_orphan", "shutdown"])
async def test_slow_login_notification_keeps_daemon_loop_responsive(db, path):
    task, run = task_run(db, 1)
    db.set_setting("ntfy_topic", "synthetic-test-only")
    assert db.reserve_login_attempt(task, run, 1)
    orch = Orchestrator(db)
    finished = threading.Event()
    worker_threads = []
    loop_thread = threading.get_ident()

    def slow_post(*args, **kwargs):
        worker_threads.append(threading.get_ident())
        time.sleep(0.3)
        finished.set()
        return SimpleNamespace(status_code=200)

    heartbeat = asyncio.Event()
    asyncio.get_running_loop().call_later(0.01, heartbeat.set)
    shutdown = None
    with mock.patch("billcollector.notify.requests.post", side_effect=slow_post) as post:
        try:
            if path == "finalize":
                db.update_run(run, pid=12345)
                orch._finalize_run(task, 12345, -9, [])
            elif path == "shutdown":
                db.update_run(run, pid=12345)
                orch._processes[task] = SimpleNamespace(
                    pid=12345, returncode=-9, wait=mock.AsyncMock(return_value=-9))
                shutdown = asyncio.create_task(orch.shutdown())
            else:
                if path == "terminal_orphan":
                    db.update_run(run, result="failure")
                orch.cleanup_orphans()
            await asyncio.wait_for(heartbeat.wait(), timeout=2)
            assert not finished.is_set(), "HTTP transport blocked the event loop"
            assert db.get_task(task)["login_locked"] == 1
            assert db.get_task(task)["login_pending_run_id"] is None
        finally:
            if shutdown is not None:
                await shutdown
            else:
                await orch.shutdown()
        assert finished.is_set()
        assert len(worker_threads) == 1
        assert worker_threads[0] != loop_thread
        post.assert_called_once()
        assert not orch._notifications


def test_submission_exception_never_replays_and_consumes_budget(browser_ctx):
    step = login_step()
    step["steps"] = []
    with mock.patch.object(runner, "_execute_step", side_effect=RuntimeError("synthetic")) as submit, \
            mock.patch.object(runner, "pause_loop", return_value="cancel"):
        with pytest.raises(runner.PauseOutcomeAbort):
            runner._execute_login(browser_ctx, step)
    submit.assert_called_once()
    assert browser_ctx.db.get_task(browser_ctx.task["id"])["login_failures"] == 1
    assert browser_ctx.db.get_task(browser_ctx.task["id"])["login_pending_run_id"] is None


def test_dispatcher_runs_login_and_continues_only_after_success(browser_ctx, portal):
    ctx = browser_ctx
    ctx.context = ctx.page.context
    ctx.bcs.usr = "synthetic"
    ctx.files_downloaded = []
    portal.accept_submissions = True
    after_login = {"step": 3, "methods": [{"method": "wait_for_timeout",
                                            "arguments": [{"timeout": 1}]}]}
    recipe = {"services": [{"serviceName": "mock", "steps": [login_step(), after_login]}]}
    with mock.patch.object(runner, "sync_playwright", return_value=nullcontext(None)), \
            mock.patch.object(runner, "_launch_browser"), \
            mock.patch.object(runner, "pause_loop") as pause:
        _, aborted, outcome = runner._run_recipe(ctx, recipe)
    assert not aborted and outcome is None
    pause.assert_not_called()
    assert portal.submissions == 1
    assert ctx.db.get_task(ctx.task["id"])["login_failures"] == 0
    assert any(row["step_number"] == 3 for row in ctx.db.list_page_status(ctx.run_id))


def test_process_crash_after_reservation_recovers_without_replay(db):
    task, run = task_run(db)
    script = (
        "import os,sys; from billcollector.db import Database; "
        "db=Database(sys.argv[1]); "
        "assert db.reserve_login_attempt(int(sys.argv[2]),int(sys.argv[3]),1); "
        "os._exit(9)"
    )
    process = subprocess.run([sys.executable, "-c", script, db.path, str(task), str(run)],
                             cwd=str(config.APP_DIR), check=False)
    assert process.returncode == 9
    assert db.get_task(task)["login_pending_run_id"] == run
    Orchestrator(db).cleanup_orphans()
    assert db.get_task(task)["login_failures"] == 1
    assert db.get_task(task)["login_locked"] == 1
    assert not db.claim_task_run(task)


def test_crash_between_finalization_and_settlement_recovers(db):
    task, run = task_run(db)
    db.reserve_login_attempt(task, run, 1)
    db.set_task_status(task, "running")
    db.update_run(run, result="failure")
    assert Orchestrator(db).cleanup_orphans() == 0
    recovered = db.get_task(task)
    assert recovered["login_pending_run_id"] is None
    assert recovered["login_locked"] == 1
    assert recovered["status"] == "idle"
    assert db.clear_login_lock(task)


def phased_login_step():
    step = login_step()
    first = {"steps": step.pop("steps"), "submit": step.pop("submit"),
             "success": {"selector": "#otp"}}
    second = copy.deepcopy(first)
    second["success"] = {"selector": "#account"}
    second["steps"][0]["methods"][0]["arguments"] = [{"selector": "#otp"}]
    second["steps"][0]["methods"][-1]["arguments"] = [{"value": "123456"}]
    second["submit"]["methods"][0]["arguments"] = [{"selector": "#verify"}]
    step["phases"] = [first, second]
    return step


@pytest.mark.parametrize("failure", [None, "password", "otp"])
@pytest.mark.parametrize("start_at_otp", [False, True])
def test_two_phase_browser_login_counts_one_transaction(browser_ctx, failure, start_at_otp):
    ctx = browser_ctx
    ctx.page.set_content("""
        <input id="password"><button id="submit">Password</button>
        <section id="second" hidden><input id="otp"><button id="verify">OTP</button></section>
        <div id="account" hidden>Account</div>
        <script>
        window.counts = [0, 0];
        document.querySelector('#submit').onclick = () => {
            counts[0]++;
            if (window.failure !== 'password') document.querySelector('#second').hidden = false;
        };
        document.querySelector('#verify').onclick = () => {
            counts[1]++;
            if (window.failure !== 'otp') document.querySelector('#account').hidden = false;
        };
        </script>
    """)
    ctx.page.evaluate("failure => window.failure = failure", failure)
    if start_at_otp:
        ctx.page.locator("#second").evaluate("element => element.hidden = false")
    step = phased_login_step()
    recipe = {"services": [{"serviceName": "mock", "steps": [step]}]}
    validate_login_recipe(recipe)
    assert validate_recipe(yaml.safe_dump(recipe))[0]
    pauses = []

    def resume(*_):
        pauses.append(ctx.page.evaluate("counts.slice()"))
        assert ctx.db.get_task(ctx.task["id"])["login_failures"] == 1
        ctx.page.locator("#account").evaluate("element => element.hidden = false")
        return "resume"

    with mock.patch.object(runner, "pause_loop", side_effect=resume):
        runner._execute_login(ctx, step)
    expected = [int(not start_at_otp), int(start_at_otp or failure != "password")]
    assert ctx.page.evaluate("counts") == expected
    assert len(pauses) == int(failure == "otp" or (failure == "password" and not start_at_otp))
    assert ctx.db.get_task(ctx.task["id"])["login_failures"] == 0


@pytest.mark.parametrize("mutation", ["mixed", "empty", "final", "nested", "unknown"])
def test_phased_contract_rejects_ambiguous_or_nested_actions(mutation):
    step = phased_login_step()
    if mutation == "mixed":
        step["steps"] = []
    elif mutation == "empty":
        step["phases"] = []
    elif mutation == "final":
        step["phases"][-1]["success"] = {"selector": "#not-final"}
    elif mutation == "nested":
        step["phases"][0]["steps"][0]["phases"] = [{}]
    else:
        step["phases"][0]["graceful"] = True
    with pytest.raises(ValueError):
        login_options(step)


def test_interruption_between_phases_keeps_one_durable_attempt(browser_ctx):
    ctx = browser_ctx
    step = phased_login_step()
    # Successful first submit exposes OTP. Death during OTP preparation cannot
    # refund the transaction or execute the second submit.
    actions = []

    def execute(_, action, **kwargs):
        actions.append(action)
        if len(actions) == 2:
            ctx.page.set_content('<input id="otp">')
        if len(actions) == 3:
            raise RunInterrupted()

    with mock.patch.object(runner, "_execute_step", side_effect=execute):
        with pytest.raises(RunInterrupted):
            runner._execute_login(ctx, step)
    assert len(actions) == 3
    task = ctx.db.get_task(ctx.task["id"])
    assert task["login_failures"] == 1
    assert task["login_pending_run_id"] == ctx.run_id
    settle_attempt(ctx.db, ctx.task["id"], ctx.run_id)
    assert ctx.db.get_task(ctx.task["id"])["login_pending_run_id"] is None


def test_lowered_limit_clear_grants_exactly_one_retry(db):
    task, run = task_run(db)
    assert db.reserve_login_attempt(task, run, 2)
    settle_attempt(db, task, run)
    retry = db.create_run(task)
    assert not db.reserve_login_attempt(task, retry, 1)
    blocked = db.get_task(task)
    assert blocked["login_locked"] == 1
    assert blocked["login_failure_limit"] == 1
    assert db.clear_login_lock(task)
    assert db.reserve_login_attempt(task, retry, 1)
    assert settle_attempt(db, task, retry)
    assert not db.reserve_login_attempt(task, db.create_run(task), 1)


def test_unsupported_test_id_option_rejected_before_runtime(db, monkeypatch):
    step = login_step()
    step["methods"][0]["arguments"][0] = {"success": {"test_id": "account", "exact": True}}
    recipe = {"services": [{"serviceName": "mock", "steps": [step]}]}
    assert not validate_recipe(yaml.safe_dump(recipe))[0]
    task, _ = task_run(db)
    monkeypatch.setattr(config, "DB_FILE", db.path)
    with mock.patch.object(runner, "_install_signal_handlers"), \
            mock.patch.object(runner, "load_recipe", return_value=(True, None, None, recipe)), \
            mock.patch.object(runner, "_vault_preflight") as vault, \
            mock.patch.object(runner.display, "allocate_display") as display:
        assert runner.run_task(task) == 1
    vault.assert_not_called()
    display.assert_not_called()


def test_finalized_attempt_recovery_preserves_another_active_run(db):
    task, run = task_run(db)
    assert db.reserve_login_attempt(task, run, 2)
    db.set_task_status(task, "running")
    db.update_run(run, result="failure")
    active = db.create_run(task, pid=os.getpid())
    assert Orchestrator(db).cleanup_orphans() == 0
    assert db.get_task(task)["login_pending_run_id"] is None
    assert db.get_task(task)["status"] == "running"
    assert db.get_run(active)["result"] is None


def test_limit_one_clear_cannot_raise_budget_and_survives_restart(db):
    task, run = task_run(db, 1)
    assert db.reserve_login_attempt(task, run, 1)
    assert settle_attempt(db, task, run)
    assert db.clear_login_lock(task)
    reopened = Database(db.path)
    try:
        retry = reopened.create_run(task)
        assert reopened.reserve_login_attempt(task, retry, 2)
        assert reopened.get_task(task)["login_failure_limit"] == 1
        assert settle_attempt(reopened, task, retry)
        assert not reopened.reserve_login_attempt(task, reopened.create_run(task), 2)
        assert reopened.clear_login_lock(task)
        success = reopened.create_run(task)
        assert reopened.reserve_login_attempt(task, success, 2)
        assert reopened.login_succeeded(task, success)
        assert reopened.reserve_login_attempt(task, reopened.create_run(task), 2)
        assert reopened.get_task(task)["login_failure_limit"] == 2
    finally:
        reopened.close()



def test_migrate_prior_candidate_preserves_cleared_limit_one(tmp_path):
    path = tmp_path / "prior-candidate.db"
    prior_schema = "\n".join(line for line in SCHEMA.splitlines()
                             if "login_cycle_active" not in line)
    with sqlite3.connect(path) as conn:
        conn.executescript(prior_schema)
        conn.execute("""INSERT INTO Task(service,user,login_failure_limit)
                        VALUES ('prior','synthetic',1)""")
    for _ in range(2):
        migrated = Database(path)
        assert migrated.get_task(1)["login_cycle_active"] == 1
        migrated.close()
    migrated = Database(path)
    migrated.set_setting("ntfy_topic", "")
    try:
        run = migrated.create_run(1)
        assert migrated.reserve_login_attempt(1, run, 2)
        assert migrated.get_task(1)["login_failure_limit"] == 1
        assert settle_attempt(migrated, 1, run)
    finally:
        migrated.close()
