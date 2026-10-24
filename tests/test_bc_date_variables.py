"""Issue #26: daemon date variables through recipe save and run interfaces."""

import copy
import sqlite3
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from billcollector import config, runner
from billcollector.db import Database
from billcollector.recipes import validate_recipe
from billcollector.variables import DateContext, expand_argument


def test_recipe_save_rejects_unknown_variable_without_disclosing_value():
    text = '''services:
- serviceName: synthetic
  steps:
  - step: 1
    methods:
    - method: goto
      arguments:
      - url: 'https://invalid.example/private-{{UNKNOWN}}'
'''
    ok, error, data = validate_recipe(text)
    assert not ok
    assert data is None
    assert 'arguments/0' in error
    assert 'unknown variable' in error
    assert 'private' not in error


def test_runner_expands_inline_and_nested_values_once():
    from datetime import datetime
    from types import SimpleNamespace

    from billcollector.runner import process_argument
    from billcollector.variables import DateContext

    bcs = SimpleNamespace(usr='synthetic', pwd='opaque-{{TODAY}}', otp='123456',
                          date_context=DateContext.capture(
                              instant=datetime.fromisoformat('2026-10-24T10:00:00+00:00')))
    value = {'{{TODAY}}': ['from={{DATE_FROM}}', {'value': '{{PASSWORD}}',
                                               'day': '{{TODAY-7d|%Y%m%d}}'}, 7]}
    assert process_argument(value, bcs) == {
        '{{TODAY}}': ['from=2026-07-27', {'value': 'opaque-{{TODAY}}',
                                       'day': '20261017'}, 7]}


FIXED = datetime.fromisoformat('2026-10-24T10:00:00+00:00')


def recipe_for(value):
    return {'services': [{'serviceName': 'synthetic', 'steps': [
        {'step': 1, 'methods': [{'method': 'fill', 'arguments': [{'value': value}]}]}
    ]}]}


@pytest.fixture(autouse=True)
def explicit_zone(monkeypatch):
    monkeypatch.setenv('TZ', 'Europe/Zurich')


def render(text, window=90, override=None, instant=FIXED):
    return expand_argument(text, None, DateContext.capture(window, override, instant=instant))


def test_default_window_and_one_day():
    ctx = DateContext.capture(instant=FIXED)
    assert ctx.date_from == date(2026, 7, 27)
    assert (ctx.today - ctx.date_from).days + 1 == 90
    assert render('{{DATE_TO}}') == '2026-10-24'
    assert render('{{DATE_FROM}}/{{DATE_TO}}', window=1) == '2026-10-24/2026-10-24'


@pytest.mark.parametrize(('instant', 'expected'), [
    ('2024-03-01T10:00:00+00:00', '2024-02-29'),
    ('2026-01-01T10:00:00+00:00', '2025-12-31'),
    ('2026-03-30T10:00:00+00:00', '2026-03-29'),
])
def test_calendar_and_dst_edges(instant, expected):
    assert render('{{DATE_FROM}}', window=2, instant=datetime.fromisoformat(instant)) == expected


def test_offsets_and_formats():
    assert render('{{TODAY-7d}} {{TODAY+1d}} {{TODAY-0d}}') == '2026-10-17 2026-10-25 2026-10-24'
    assert render('{{DATE_FROM|%d/%m/%Y}} {{TODAY-7d|%Y%m%d}}') == '27/07/2026 20261017'
    assert render('{{TODAY|%Y._%m-%d %%}}') == '2026._10-24 %'
    assert render('{{TODAY|%Y/%m/%d}}', window=1,
                  instant=datetime(1, 1, 1, 10, tzinfo=FIXED.tzinfo)) == '0001/01/01'


def test_timezone_boundary_and_utc_fallback(monkeypatch):
    instant = datetime.fromisoformat('2026-10-24T22:30:00+00:00')
    assert render('{{TODAY}}', instant=instant) == '2026-10-25'
    monkeypatch.setenv('TZ', 'UTC')
    assert render('{{TODAY}}', instant=instant) == '2026-10-24'
    monkeypatch.delenv('TZ')
    assert render('{{TODAY}}', instant=instant) == '2026-10-24'


@pytest.mark.parametrize('value', ['{{UNKNOWN}}', '{{TODAY-1w}}', '{{TODAY',
                                 'TODAY}}', '{{TODAY|%Q}}', '{{TODAY|%B}}',
                                 '{{TODAY|%-d}}', '{{TODAY|%}}', '{{TODAY|}}',
                                 '{{TODAY|---}}', '{{PASSWORD|%Y}}',
                                 '{{TODAY|%Yx}}', '{{TODAY|%%Y}}', '{{{{TODAY}}'])
def test_save_and_runtime_reject_same_syntax(value, tmp_path, monkeypatch, capsys):
    from billcollector.variables import validate_variable_recipe

    recipe = recipe_for('private-' + value)
    ok, error, _ = validate_recipe(yaml.safe_dump(recipe))
    assert not ok
    assert 'arguments/0' in error
    assert 'private' not in error
    with pytest.raises(ValueError, match='arguments/0'):
        validate_variable_recipe(recipe)
    assert_prelaunch_failure(recipe, tmp_path, monkeypatch, capsys)


def assert_prelaunch_failure(recipe, tmp_path, monkeypatch, capsys,
                             window=90, override=None, instant=FIXED):
    path = tmp_path / 'recipe.yaml'
    path.write_text(yaml.safe_dump(recipe))
    dbpath = tmp_path / 'test.db'
    monkeypatch.setattr(config, 'DB_FILE', dbpath)
    with_db = Database(dbpath)
    task_id = with_db.create_task('synthetic', 'test', recipe_file=str(path))
    # Simulate a corrupt stored setting without DB API coercion hiding it.
    with_db.conn.execute('UPDATE Task SET date_window_days=? WHERE id=?', (window, task_id))
    with_db.conn.commit()
    with_db.close()
    monkeypatch.setattr(runner.DateContext, 'capture',
                        lambda window, override: _CAPTURE(window, override, instant=instant))
    resources = Mock(side_effect=AssertionError('must not launch'))
    monkeypatch.setattr(runner.display, 'allocate_display', resources)
    monkeypatch.setattr(runner, '_vault_preflight', resources)
    monkeypatch.setattr(runner, 'sync_playwright', resources)
    assert runner.run_task(task_id, date_from=override) == 1
    resources.assert_not_called()
    output = capsys.readouterr()
    assert 'invalid variable contract' in output.err
    assert 'private' not in output.err
    check = Database(dbpath)
    assert check.list_runs(task_id) == []
    check.close()


_CAPTURE = DateContext.capture


@pytest.mark.parametrize('window', [0, -1, True, 1.5, '90', 1000000000])
def test_invalid_window_rejected(window):
    with pytest.raises(ValueError, match='date_window_days'):
        DateContext.capture(window, instant=FIXED)


@pytest.mark.parametrize('window', [0, -1, 1.5, 1000000000])
def test_invalid_stored_window_stops_before_resources(window, tmp_path, monkeypatch, capsys):
    assert_prelaunch_failure(recipe_for('{{TODAY}}'), tmp_path, monkeypatch,
                             capsys, window=window)


@pytest.mark.parametrize('override', ['2026-02-30', '24/10/2026', '2026-10-25',
                                     '20261024', '2026-1-01', '2026-01-01\n', ''])
def test_invalid_recovery_before_resources(override, tmp_path, monkeypatch, capsys):
    assert_prelaunch_failure(recipe_for('{{DATE_FROM}}'), tmp_path, monkeypatch,
                             capsys, override=override)


@pytest.mark.parametrize('zone', ['Invalid/Zone', '', '../UTC', '/etc/localtime'])
def test_invalid_zone_before_resources(zone, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('TZ', zone)
    assert_prelaunch_failure(recipe_for('{{TODAY}}'), tmp_path, monkeypatch, capsys)


@pytest.mark.parametrize('value', ['{{TODAY+999999999d}}', '{{TODAY-999999999d}}',
                                 '{{TODAY+' + '9' * 5000 + 'd}}'])
def test_overflow_before_resources(value, tmp_path, monkeypatch, capsys):
    assert_prelaunch_failure(recipe_for(value), tmp_path, monkeypatch, capsys)


def test_date_limits(monkeypatch):
    monkeypatch.setenv('TZ', 'UTC')
    minimum = datetime(1, 1, 1, tzinfo=FIXED.tzinfo)
    maximum = datetime(9999, 12, 31, tzinfo=FIXED.tzinfo)
    assert render('{{TODAY}}', window=1, instant=minimum) == '0001-01-01'
    with pytest.raises(ValueError, match='overflow'):
        render('{{DATE_FROM}}', window=2, instant=minimum)
    with pytest.raises(ValueError, match='overflow'):
        render('{{TODAY+1d}}', window=1, instant=maximum)


def test_nested_arguments_single_pass_and_secret_absent_from_records(caplog):
    secret = 'synthetic-opaque-{{TODAY}}'
    received = []

    class Page:
        def evaluate(self, script):
            return []

        def fill(self, value):
            received.append(value)

    bcs = SimpleNamespace(service='synthetic', page=Page(), pwd=secret,
                          date_context=DateContext.capture(instant=FIXED))
    step = recipe_for('{{PASSWORD}}')['services'][0]['steps'][0]
    original = copy.deepcopy(step)
    state = runner._process_step(bcs, step)
    assert received == [secret]
    assert step == original
    assert secret not in repr(vars(state)) + caplog.text
    assert '{{PASSWORD}}' in state.locator_action


def test_migration_and_task_window_validation(tmp_path):
    path = tmp_path / 'old.db'
    conn = sqlite3.connect(path)
    # Build the exact previous schema by omitting the new additive column.
    from billcollector.db import SCHEMA
    conn.executescript(SCHEMA.replace('    date_window_days INTEGER NOT NULL DEFAULT 90,\n', ''))
    conn.execute("INSERT INTO Task(service,user) VALUES ('synthetic','test')")
    conn.commit()
    conn.close()
    for _ in range(2):
        db = Database(path)
        assert db.get_task(1)['date_window_days'] == 90
        db.close()
    db = Database(path)
    task = db.create_task('synthetic', 'other', date_window_days=1)
    assert db.get_task(task)['date_window_days'] == 1
    for bad in [True, '90', 1.5, 0, -1]:
        with pytest.raises(ValueError):
            db.update_task(task, date_window_days=bad)
        with pytest.raises(ValueError):
            db.create_task('bad', 'test', date_window_days=bad)
    db.close()


def test_stable_runner_context_recovery_and_restart(tmp_path, monkeypatch, caplog):
    path = tmp_path / 'recipe.yaml'
    document = recipe_for('{{DATE_FROM}} {{TODAY}} {{TODAY-7d}}')
    path.write_text(yaml.safe_dump(document))
    dbpath = tmp_path / 'test.db'
    monkeypatch.setattr(config, 'DB_FILE', dbpath)
    db = Database(dbpath)
    task = db.create_task('synthetic', 'test', recipe_file=str(path))
    before = dict(db.get_task(task))
    db.close()
    clock = [datetime.fromisoformat('2026-10-24T21:59:59+00:00')]
    monkeypatch.setattr(runner.DateContext, 'capture',
                        lambda window, override: _CAPTURE(window, override, instant=clock[0]))
    monkeypatch.setattr(runner.display, 'allocate_display', lambda db: (199, 6199))
    monkeypatch.setattr(runner.display, 'release_display', lambda n: None)
    monkeypatch.setattr(runner, '_start_display_stack', lambda *args: None)
    monkeypatch.setattr(runner, '_vault_preflight', lambda *args: {
        'user': 'synthetic', 'password': 'opaque-{{TODAY}}', 'otp': '123456'})
    observed = []

    def execute(ctx, recipe):
        arg = recipe['services'][0]['steps'][0]['methods'][0]['arguments']
        first = runner.process_argument(arg, ctx.bcs)
        # A retry/resume after local midnight keeps the original run context.
        clock[0] = datetime.fromisoformat('2026-10-24T22:30:00+00:00')
        assert runner.process_argument(arg, ctx.bcs) == first
        observed.append(first)
        return [], False, None

    monkeypatch.setattr(runner, '_run_recipe', execute)
    assert runner.run_task(task, date_from='2026-01-01') == 1  # no download
    clock[0] = FIXED
    assert runner.run_task(task) == 1
    # Reopen the database and create a new dispatcher, as on daemon restart.
    db = Database(dbpath)
    from billcollector.orchestrator import Orchestrator
    Orchestrator(db).cleanup_orphans()
    clock[0] = FIXED
    assert runner.run_task(task) == 1
    assert observed == [
        [{'value': '2026-01-01 2026-10-24 2026-10-17'}],
        [{'value': '2026-07-27 2026-10-24 2026-10-17'}],
        [{'value': '2026-07-27 2026-10-24 2026-10-17'}],
    ]
    after = dict(db.get_task(task))
    assert after['date_window_days'] == before['date_window_days']
    for key in ('recipe_file', 'cron', 'enabled', 'profile_dir'):
        assert after[key] == before[key]
    dump = '\n'.join(db.conn.iterdump())
    assert '2026-01-01' not in dump + caplog.text + path.read_text()
    assert 'opaque-{{TODAY}}' not in dump + caplog.text
    assert document == yaml.safe_load(path.read_text())
    db.close()


@pytest.mark.asyncio
async def test_dispatch_override_uses_pipe_only_and_is_not_replayed(tmp_path, monkeypatch):
    import sys

    from billcollector.orchestrator import Orchestrator

    monkeypatch.setattr(DateContext, 'capture',
                        lambda window, override: _CAPTURE(window, override, instant=FIXED))
    db = Database(tmp_path / 'dispatch.db')
    task = db.create_task('synthetic', 'test')
    observed = tmp_path / 'observed.txt'
    # The isolated child asserts the actual dispatch transport contract.
    script = """
import pathlib, sys
assert '2026-01-01' not in repr(sys.argv)
if '--date-from-stdin' in sys.argv:
    assert sys.stdin.read() == '2026-01-01'
    result = 'recovery'
else:
    result = 'normal'
with pathlib.Path(sys.argv[1]).open('a') as output:
    output.write(result + '\\n')
"""
    cmd = [sys.executable, '-c', script, str(observed)]
    orch = Orchestrator(db, runner_cmd=cmd)
    assert await orch.start_run(task, date_from='2026-01-01')
    await orch.monitors[task]
    restarted = Orchestrator(db, runner_cmd=cmd)
    assert await restarted.start_run(task)
    await restarted.monitors[task]
    assert observed.read_text() == 'recovery\nnormal\n'
    assert '2026-01-01' not in '\n'.join(db.conn.iterdump())
    with pytest.raises(ValueError):
        await restarted.start_run(task, date_from='2099-01-01')
    assert db.get_task(task)['status'] == 'idle'
    assert not restarted.processes
    db.close()


def test_scheduler_uses_the_date_timezone(tmp_path, monkeypatch):
    from billcollector.scheduler import TaskScheduler

    monkeypatch.setenv('TZ', 'Europe/Zurich')
    db = Database(tmp_path / 'schedule.db')
    task = db.create_task('synthetic', 'test', enabled=True, cron='0 0 * * *')
    scheduler = TaskScheduler(db, Mock())
    scheduler.resync()
    job = scheduler.scheduler.get_job(f'task-{task}')
    assert str(job.trigger.timezone) == 'Europe/Zurich'
    db.close()


def test_real_browser_fill_and_nested_arguments_keep_credentials_opaque(caplog):
    from playwright.sync_api import sync_playwright

    secret = 'synthetic-password-{{TODAY}}'
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content('<input id="password"><output id="dates"></output>')
            bcs = SimpleNamespace(service='synthetic', page=page, pwd=secret,
                                  date_context=DateContext.capture(instant=FIXED))
            fill = {'step': 1, 'methods': [
                {'method': 'locator', 'arguments': [{'selector': '#password'}]},
                {'method': 'fill', 'arguments': [{'value': '{{PASSWORD}}'}]},
            ]}
            state = runner._process_step(bcs, fill)
            assert page.locator('#password').input_value() == secret
            nested = {'step': 2, 'methods': [{'method': 'evaluate', 'arguments': [
                {'expression': '(arg) => document.querySelector("#dates").textContent = JSON.stringify(arg)'},
                {'arg': {'{{TODAY}}': ['{{DATE_FROM}}', {'to': '{{DATE_TO}}'}, 7]}},
            ]}]}
            nested_state = runner._process_step(bcs, nested)
            assert page.locator('#dates').text_content() == '{"{{TODAY}}":["2026-07-27",{"to":"2026-10-24"},7]}'
            assert secret not in repr(vars(state)) + repr(vars(nested_state)) + caplog.text
        finally:
            browser.close()


def test_cli_consumes_override_from_stdin_only(monkeypatch):
    import io
    import sys

    from billcollector import cli

    run = Mock(return_value=0)
    monkeypatch.setattr(runner, 'run_task', run)
    monkeypatch.setattr(sys, 'stdin', io.StringIO('2026-01-01'))
    assert cli.main(['run', '1', '--date-from-stdin']) == 0
    run.assert_called_once_with(1, False, date_from='2026-01-01')


def test_optional_totp_exact_token_keeps_none_and_inline_is_empty(monkeypatch):
    monkeypatch.setattr(runner, 'get_totp', lambda url: None)
    bcs = SimpleNamespace(api_url='http://127.0.0.1:1', vault_item_name='synthetic',
                          otp_fallback=None)
    assert runner.process_argument({'value': '{{OTP}}'}, bcs) == {'value': None}
    assert runner.process_argument('otp={{OTP}}', bcs) == 'otp='


@pytest.mark.parametrize(('instant', 'window', 'expression'), [
    (datetime(1, 1, 1, tzinfo=FIXED.tzinfo), 2, '{{DATE_FROM}}'),
    (datetime(9999, 12, 31, tzinfo=FIXED.tzinfo), 1, '{{TODAY+1d}}'),
])
def test_date_limits_fail_before_resources(instant, window, expression,
                                          tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('TZ', 'UTC')
    assert_prelaunch_failure(recipe_for(expression), tmp_path, monkeypatch,
                             capsys, window=window, instant=instant)
