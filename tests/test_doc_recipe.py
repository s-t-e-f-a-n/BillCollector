"""Execute the author guide's exact YAML with real loopback Chromium downloads.

The display adapter uses headless Chromium. Vault/TOTP values are synthetic;
all recipe dispatch, login budgets, tracking and dedup use the daemon code.
"""

import json
import socket
import threading
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import uvicorn

from billcollector import config, runner
from billcollector.db import Database
from billcollector.recipes import load_recipe
from tests.mock_portal.app import create_app

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'doc/examples/recipe-pw__synthetic.yaml'


@pytest.fixture
def portal():
    # Bind first so no other test can take the chosen loopback port.
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(), log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()


def test_author_example_login_downloads_and_session_reuse(portal, tmp_path, monkeypatch):
    ok, error, text, _ = load_recipe(EXAMPLE)
    assert ok, error
    # Change only the fixture port. Validate the modified copy as well.
    path = tmp_path / 'recipe.yaml'
    path.write_text(text.replace('127.0.0.1:8787', f'127.0.0.1:{portal}'))
    ok, error, _, recipe = load_recipe(path)
    assert ok, error
    db = Database(tmp_path / 'proof.db')
    monkeypatch.setattr(config, 'RUN_DIR', tmp_path / 'runs')
    monkeypatch.setattr(config, 'PROFILE_ROOT', tmp_path / 'profiles')
    db.set_setting('download_dir', str(tmp_path / 'downloads'))
    db.set_setting('ntfy_topic', '')
    db.set_setting('pause_deadline_seconds', '2')
    task_id = db.create_task('synthetic', 'user1', recipe_file=str(path))
    # No real API call. This is the documented test credential, not a secret.
    monkeypatch.setattr(runner, 'get_totp', lambda url: json.dumps({'data': {'data': '123456'}}))

    def launch(ctx, playwright):
        profile = config.profile_dir_for(ctx.task['service'], ctx.task['user'])
        runner._ensure_pdf_preference(profile)
        runner._clear_stale_history(profile)
        ctx.context = playwright.chromium.launch_persistent_context(str(profile), headless=True)
        ctx.context.route('**/*', lambda route: route.continue_()
                          if urlsplit(route.request.url).hostname == '127.0.0.1'
                          else route.abort())
        ctx.page = ctx.context.new_page()
        ctx.bcs.page = ctx.page

    monkeypatch.setattr(runner, '_launch_browser', launch)
    expected = {'invoice_happy_user1_1.pdf', 'contract_info_happy_user1.pdf'}
    try:
        for attempt in range(2):
            task = db.get_task(task_id)
            run_id = db.create_run(task_id)
            ctx = runner._RunContext(task, run_id, db, False,
                                     {'user': 'user1', 'password': 'user1-pass', 'otp': '123456'},
                                     'http://127.0.0.1:9')
            files, aborted, outcome = runner._run_recipe(ctx, recipe)
            assert not aborted and outcome is None
            assert runner.run_result(aborted, files, outcome) == 'success'
            records = db.list_downloads(run_id=run_id)
            assert {row['filename'] for row in records} == expected
            assert all(bool(row['duplicate_of_id']) is bool(attempt) for row in records)
            assert all(Path(row['saved_path']).read_bytes().startswith(b'%PDF') for row in records)
            assert db.get_task(task_id)['login_failures'] == 0
    finally:
        db.close()
