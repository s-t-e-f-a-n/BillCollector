"""Offline proof of the engine boundary, not a qualified provider adapter."""

import copy
import io
import json
import threading
import zipfile
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml
from playwright.sync_api import sync_playwright
from pypdf import PdfWriter

from billcollector import bourse_direct_boundary as boundary
from billcollector import config, downloads, runner
from billcollector.db import Database
from billcollector.recipes import load_recipe, save_recipe, validate_recipe
from billcollector.variables import DateContext

OPTIONS = {'account_type': 'PEA', 'max_months': 3, 'max_items': 4, 'timeout_ms': 30000}
CHAINS = {'listing': [
    {'method': 'locator', 'arguments': [{'selector': '#listing'}]},
    {'method': 'inner_text'}]}
SOURCE = '''import json
CHAINS = %r
def collect(api, options):
    listing = json.loads(api.call('listing'))
    if listing['account_type'] != options['account_type']:
        raise ValueError('private-account-drift')
    if tuple(listing['month']) != api.months[0]:
        raise ValueError('private-month-drift')
    api.offered(len(listing['items']))
    if not listing['items'] and not listing['empty']:
        raise ValueError('private-missing-empty-proof')
    for item in listing['items']:
        notice = json.loads(api.read(item['notice']))
        if len(notice['pdfs']) != 1:
            raise ValueError('private-ambiguous-original')
        api.save_original(notice['pdfs'][0], item['filename'])
''' % CHAINS


def recipe(url='http://127.0.0.1:1'):
    return {'services': [{'serviceName': 'synthetic', 'steps': [
        {'step': 1, 'methods': [{'method': 'goto', 'arguments': [{'url': url}]}]},
        {'step': 2, 'methods': [{'method': 'login', 'arguments': [
            {'success': {'selector': '#session'}, 'session_timeout_ms': 1000}]}],
         'submit': {'step': 21, 'methods': [
             {'method': 'locator', 'arguments': [{'selector': '#submit'}]},
             {'method': 'click'}]}},
        {'step': 3, 'notice_identity': copy.deepcopy(boundary.IDENTITY),
         'methods': [{'method': boundary.ACTION, 'arguments': [copy.deepcopy(OPTIONS)]}]}]}]}


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'RECIPE_DIR', tmp_path)
    source = tmp_path / 'bourse_direct_adapter.py'
    source.write_text(SOURCE)
    source.chmod(0o644)
    return source


def test_load_save_and_run_start_do_not_execute_adapter(catalog, tmp_path, monkeypatch):
    marker = tmp_path / 'should-not-exist'
    catalog.write_text(SOURCE + f'\nopen({str(marker)!r}, "w").write("executed")\n')
    path = tmp_path / 'recipe.yaml'
    text = yaml.safe_dump(recipe())
    assert validate_recipe(text)[0]
    assert save_recipe(path, text) == (True, None)
    assert load_recipe(path)[0]
    monkeypatch.setattr(config, 'DB_FILE', tmp_path / 'isolated.db')
    db = Database()
    task = db.create_task('synthetic', 'test', recipe_file=str(path))
    db.close()
    resource = Mock(side_effect=runner.display.DisplayError('synthetic stop'))
    monkeypatch.setattr(runner.display, 'allocate_display', resource)
    denied = Mock(side_effect=AssertionError('must not reach vault/browser'))
    monkeypatch.setattr(runner, '_vault_preflight', denied)
    monkeypatch.setattr(runner, 'sync_playwright', denied)
    assert runner.run_task(task) == 1
    resource.assert_called_once()
    denied.assert_not_called()
    assert not marker.exists()


def test_catalog_rejects_group_writable_source(catalog):
    catalog.chmod(0o664)
    with pytest.raises(ValueError, match='runtime-owned'):
        boundary.candidate()


@pytest.mark.parametrize('corrupt', ['method', 'arguments', 'literal', 'missing'])
def test_bad_adapter_rejected_at_all_gates(catalog, tmp_path, monkeypatch, corrupt):
    path = tmp_path / 'recipe.yaml'
    text = yaml.safe_dump(recipe())
    assert save_recipe(path, text)[0]
    if corrupt == 'missing':
        catalog.rename(catalog.with_suffix('.retained'))
    elif corrupt == 'literal':
        catalog.write_text(SOURCE.replace(repr(CHAINS), 'dict()'))
    else:
        chains = copy.deepcopy(CHAINS)
        if corrupt == 'method':
            chains['listing'][-1]['method'] = 'private_unknown'
        else:
            chains['listing'][-1]['arguments'] = [{'private_unknown': 'secret-value'}]
        catalog.write_text(SOURCE.replace(repr(CHAINS), repr(chains)))
    ok, error, _ = validate_recipe(text)
    assert not ok and 'secret-value' not in error
    assert 'service synthetic, step 3, method bourse_direct' in error
    assert not load_recipe(path)[0]
    assert not save_recipe(path, text + '\n# rejected')[0]
    assert path.read_text() == text
    monkeypatch.setattr(config, 'DB_FILE', tmp_path / 'isolated.db')
    db = Database()
    task = db.create_task('synthetic', 'test', recipe_file=str(path))
    db.close()
    denied = Mock(side_effect=AssertionError('must not acquire resources'))
    monkeypatch.setattr(runner.display, 'allocate_display', denied)
    monkeypatch.setattr(runner, '_vault_preflight', denied)
    monkeypatch.setattr(runner, 'sync_playwright', denied)
    assert runner.run_task(task) == 1
    denied.assert_not_called()


@pytest.mark.parametrize('change', ['prefix', 'graceful', 'nested', 'login', 'identity',
                                  'duplicate', 'services', 'bounds', 'override'])
def test_adapter_scope_rejected(catalog, change):
    data = recipe()
    steps = data['services'][0]['steps']
    step = steps[-1]
    if change == 'prefix':
        step['methods'].insert(0, {'method': 'locator', 'arguments': [{'selector': 'body'}]})
    elif change == 'graceful':
        step['graceful'] = True
    elif change == 'nested':
        steps[-1] = {'step': 4, 'methods': [{'method': 'expect_download'}], 'steps': [step]}
    elif change == 'login':
        steps.pop(1)
    elif change == 'identity':
        step.pop('notice_identity')
    elif change == 'duplicate':
        steps.append(copy.deepcopy(step))
    elif change == 'services':
        data['services'].append(copy.deepcopy(data['services'][0]))
    elif change == 'bounds':
        step['methods'][0]['arguments'][0]['max_items'] = True
    else:
        step['methods'][0]['arguments'][0]['date_from'] = '2020-01-01'
    assert not validate_recipe(yaml.safe_dump(data))[0]


def pdf(metadata='one', width=100):
    writer = PdfWriter()
    writer.add_blank_page(width, 100)
    writer.add_metadata({'/CreationDate': metadata})
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


@pytest.fixture
def portal():
    state = {'body': pdf(), 'requests': [], 'account_type': 'PEA', 'month': [2026, 1],
             'empty': True, 'items': 2, 'pdfs': 1, 'status': 200}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            state['requests'].append((self.path, self.headers.get('Cookie')))
            base = f'http://127.0.0.1:{self.server.server_port}'
            query = '?nc=123&type=RO&year=2026&month=1&day='
            if self.path == '/transport.zip':
                stream = io.BytesIO()
                with zipfile.ZipFile(stream, 'w') as archive:
                    archive.writestr('safe/invoice.pdf', pdf(width=80))
                body = stream.getvalue()
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Disposition', 'attachment; filename="transport.zip"')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path.startswith('/original'):
                body = state['body']
            elif self.path.startswith('/notice'):
                target = base + self.path.replace('/notice', '/original') + '&pdf=1'
                body = json.dumps({'pdfs': [target] * state['pdfs']}).encode()
            else:
                listing = {key: state[key] for key in ('account_type', 'month', 'empty')}
                listing['items'] = [
                    {'notice': base + '/notice' + query + str(day),
                     'filename': f'original-{day}.pdf'}
                    for day in range(1, state['items'] + 1)]
                body = ('<div id="session">session</div><pre id="listing">'
                        + json.dumps(listing) + '</pre>'
                        + '<a data-key=zip-one href=/transport.zip>ZIP</a>').encode()
            self.send_response(state['status'])
            self.send_header('Set-Cookie', 'fixture=session; Path=/')
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture
def browser_ctx(catalog, portal, tmp_path, monkeypatch):
    url, state = portal
    monkeypatch.setattr(config, 'DB_FILE', tmp_path / 'isolated.db')
    monkeypatch.setattr(config, 'DOWNLOAD_DIR', tmp_path / 'downloads')
    monkeypatch.setattr(config, 'RUN_DIR', tmp_path / 'runs')
    db = Database()
    db.set_setting('download_dir', str(tmp_path / 'downloads'))
    task_id = db.create_task('synthetic', 'test')
    task = db.get_task(task_id)
    run_id = db.create_run(task_id)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url)
        ctx = runner._RunContext(task, run_id, db, False,
                                 {'user': 'synthetic', 'password': 'synthetic', 'otp': None}, '')
        ctx.page, ctx.context, ctx.bcs.page = page, context, page
        ctx.bcs.date_context = DateContext(date(2026, 1, 15), date(2025, 11, 15))
        ctx.bourse_direct_candidate = boundary.prepare(recipe(url))
        monkeypatch.setattr(runner, 'pause_loop', Mock(side_effect=AssertionError('unexpected pause')))
        # Exercise the actual native stored-session proof before collection.
        runner._execute_login(ctx, recipe(url)['services'][0]['steps'][1])
        monkeypatch.setattr(runner, '_record_step', Mock())
        monkeypatch.setattr(runner.PageState, 'set_interactive_elements', lambda *_args: [])
        try:
            yield ctx, state
        finally:
            context.close()
            browser.close()
            db.close()


def test_actual_adapter_path_original_bytes_and_notice_revisions(browser_ctx, catalog):
    ctx, state = browser_ctx
    step = recipe()['services'][0]['steps'][-1]
    assert ctx.native_login_proven
    # Execution uses frozen source, even if a catalog update races with the run.
    catalog.write_text('raise AssertionError("must not execute changed source")')
    runner._execute_step(ctx, step)
    rows = ctx.db.conn.execute('SELECT * FROM Download').fetchall()
    assert len(rows) == 2
    for row in rows:
        assert Path(row['saved_path']).read_bytes() == state['body']
    assert all(cookie == 'fixture=session' for path, cookie in state['requests']
               if path.startswith(('/notice', '/original')))
    # Regenerated PDF with changed Info timestamp remains one notice revision.
    state['body'] = pdf('two')
    runner._execute_step(ctx, step)
    assert ctx.db.conn.execute('SELECT count(*) FROM Download WHERE duplicate_of_id IS NULL').fetchone()[0] == 2
    # A material correction is fetched and kept, despite the same daily source.
    state['body'] = pdf('three', width=200)
    runner._execute_step(ctx, step)
    assert ctx.db.conn.execute('SELECT count(*) FROM Download WHERE duplicate_of_id IS NULL').fetchone()[0] == 4
    assert ctx.db.conn.execute('SELECT count(*) FROM Download').fetchone()[0] == 6
    assert len([path for path, _ in state['requests'] if path.startswith('/original')]) == 6
    assert ctx.bcs.date_context.today == date(2026, 1, 15)


@pytest.mark.parametrize('field,value', [('account_type', 'PEA-PME'), ('month', [2025, 12]),
                                       ('items', 5), ('pdfs', 2), ('status', 302)])
def test_synthetic_failure_is_single_attempt_and_redacted(browser_ctx, field, value):
    ctx, state = browser_ctx
    state[field] = value
    # Update rendered listing after changing source identity/item count.
    ctx.page.reload()
    calls = []
    original = boundary.collect

    def count(*args):
        calls.append(1)
        return original(*args)

    from unittest.mock import patch
    with patch.object(boundary, 'collect', count):
        with pytest.raises(runner.StepAbortError) as error:
            runner._execute_step(ctx, recipe()['services'][0]['steps'][-1])
    assert len(calls) == 1
    assert 'private-' not in str(error.value)


def test_explicit_empty_retains_native_empty_run_result(browser_ctx):
    ctx, state = browser_ctx
    state['items'] = 0
    ctx.page.reload()
    runner._execute_step(ctx, recipe()['services'][0]['steps'][-1])
    assert ctx.files_downloaded == []
    assert runner.run_result(True, [], False) == 'failure'
    state['empty'] = False
    ctx.page.reload()
    with pytest.raises(runner.StepAbortError):
        runner._execute_step(ctx, recipe()['services'][0]['steps'][-1])


def test_dates_bounds_and_runtime_call_validation(browser_ctx):
    ctx, state = browser_ctx
    save = Mock()
    api = boundary.Acquisition(ctx, ctx.bourse_direct_candidate, OPTIONS, save)
    assert api.months == ((2026, 1), (2025, 12), (2025, 11))
    with pytest.raises(ValueError):
        api.call('listing', unsupported='private')
    with pytest.raises(boundary.CollectionError):
        api.read('http://other.invalid/original')
    with pytest.raises(boundary.CollectionError):
        api.save_original(ctx.page.url, '../unsafe.pdf')
    with pytest.raises(boundary.CollectionError):
        boundary.Acquisition(ctx, ctx.bourse_direct_candidate, dict(OPTIONS, max_months=2), save)
    api._deadline = 0
    with pytest.raises(boundary.CollectionError):
        api.call('listing')
    save.assert_not_called()


@pytest.mark.parametrize('mode', ['originals', 'empty', 'incremental_zip'])
def test_full_run_start_reaches_frozen_adapter(catalog, portal, tmp_path, monkeypatch, mode):
    url, state = portal
    path = tmp_path / 'recipe.yaml'
    data = recipe(url)
    if mode == 'empty':
        state['items'] = 0
    if mode == 'incremental_zip':
        data['services'][0]['steps'].append({'step': 4, 'methods': [
            {'method': 'locator', 'arguments': [{'selector': 'a[data-key]'}]},
            {'method': 'download_all', 'arguments': [{
                'key_attribute': 'data-key', 'max_items': 1, 'timeout_ms': 5000,
                'event_window_ms': 200, 'incremental': True, 'unpack': 'pdf'}]}]})
    assert save_recipe(path, yaml.safe_dump(data))[0]
    delivered = []
    monkeypatch.setattr(downloads, 'CONSUMERS', [delivered.append])
    monkeypatch.setattr(config, 'DB_FILE', tmp_path / 'isolated.db')
    db = Database()
    db.set_setting('download_dir', str(tmp_path / 'originals'))
    task_id = db.create_task('synthetic', 'test', recipe_file=str(path))
    db.close()
    monkeypatch.setattr(runner.DateContext, 'capture', Mock(return_value=DateContext(
        date(2026, 1, 15), date(2025, 11, 15))))
    monkeypatch.setattr(runner.display, 'allocate_display', Mock(return_value=(99, 5999)))
    monkeypatch.setattr(runner.display, 'release_display', Mock())
    monkeypatch.setattr(runner, '_start_display_stack', Mock(return_value=[]))
    monkeypatch.setattr(runner.display, 'stop_display_stack', Mock())
    monkeypatch.setattr(runner, 'pause_loop', Mock(side_effect=AssertionError('unexpected pause')))
    monkeypatch.setattr(runner, '_record_step', Mock())
    monkeypatch.setattr(runner.PageState, 'set_interactive_elements', lambda *_args: [])

    def synthetic_credentials(*_args):
        catalog.write_text('raise AssertionError("catalog changed after admission")')
        return {'user': 'synthetic', 'password': 'synthetic', 'otp': None}

    def isolated_browser(ctx, p):
        ctx.context = p.chromium.launch_persistent_context(str(tmp_path / 'profile'), headless=True)
        ctx.page = ctx.context.new_page()
        ctx.bcs.page = ctx.page

    monkeypatch.setattr(runner, '_vault_preflight', synthetic_credentials)
    monkeypatch.setattr(runner, '_launch_browser', isolated_browser)
    assert runner.run_task(task_id) == (1 if mode == 'empty' else 0)
    db = Database()
    try:
        run = db.list_runs(task_id)[0]
        assert run['result'] == ('failure' if mode == 'empty' else 'success')
        assert run['collection_outcome'] == ('failed' if mode == 'empty' else 'new_documents')
        assert run['date_from'] == '2025-11-15'
        rows = db.list_downloads(run_id=run['id'])
        assert len(rows) == {'originals': 2, 'empty': 0, 'incremental_zip': 3}[mode]
        for row in rows:
            expected = pdf(width=80) if row['source_key'] else state['body']
            assert Path(row['saved_path']).read_bytes() == expected
            assert row['state'] == 'consumed'
        assert len(delivered) == len(rows)
        assert all(item['idempotency_key'] == f"{task_id}:{item['sha256']}"
                   for item in delivered)
        assert db.known_source_keys(task_id) == ({'data-key=zip-one'}
                                               if mode == 'incremental_zip' else set())
        if mode == 'incremental_zip':
            # A second native run rereads adapter originals but skips the keyed ZIP.
            catalog.write_text(SOURCE)
            assert runner.run_task(task_id) == 0
            repeat = db.list_runs(task_id)[0]
            assert repeat['result'] == 'success'
            assert repeat['collection_outcome'] == 'duplicates_only'
            repeated = db.list_downloads(run_id=repeat['id'])
            assert len(repeated) == 2
            assert all(row['duplicate_of_id'] is not None for row in repeated)
            assert len(delivered) == 3
            assert len([path for path, _ in state['requests']
                        if path.startswith('/original')]) == 4
            assert len([path for path, _ in state['requests']
                        if path == '/transport.zip']) == 1
    finally:
        db.close()
