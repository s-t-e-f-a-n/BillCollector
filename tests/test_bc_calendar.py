"""Credential-free browser proofs for the daemon replacement-calendar action."""

import copy
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
import yaml
from playwright.sync_api import sync_playwright

from billcollector import calendar, collection, config, downloads, recipes, runner
from billcollector.db import Database
from billcollector.interrupt import RunInterrupted
def DateContext(today, date_from):
    # The traversal accepts the immutable context supplied by upstream PR #34.
    return SimpleNamespace(today=today, date_from=date_from)


OPTIONS = {
    'account_id': 'synthetic-account', 'account_selector': '.account',
    'year_selector': '.year', 'month_selector': '.month',
    'previous_selector': '.previous', 'item_selector': '.notice',
    'empty_selector': '.empty', 'ready_selector': '.ready', 'max_months': 3,
    'download_options': {
        'key_attribute': 'href', 'max_items': 8,
        'timeout_ms': 5000, 'event_window_ms': 100,
    },
}


@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def portal(browser, tmp_path, monkeypatch):
    """All browser requests are fulfilled in memory; persistence is temporary."""
    ctx = browser.new_context(service_workers='block', accept_downloads=True)
    page = ctx.new_page()
    data = SimpleNamespace(
        counts={'2026-01': 2, '2025-12': 2, '2025-11': 1},
        visited=[], pdfs=[], denied=[], wrong_account=None, wrong_month=None,
        no_empty=None, missing_control=None, ambiguous=False,
        never_ready=None, same_name=False, detached=False, drift=False, same_tab=False,
    )

    def route(request):
        url = urlsplit(request.request.url)
        if url.netloc != 'calendar.invalid':
            data.denied.append(url.netloc)
            request.abort()
            return
        if url.path.startswith('/pdf/'):
            data.pdfs.append(url.path)
            filename = 'same.pdf' if data.same_name else url.path.rsplit('/', 1)[-1]
            request.fulfill(body=b'%PDF-1.4\n' + url.path.encode() + b'\n%%EOF',
                            content_type='application/pdf', headers={
                                'Content-Disposition': f'attachment; filename="{filename}"',
                            })
            return
        if url.path.startswith('/view/'):
            filename = url.path.rsplit('/', 1)[-1]
            request.fulfill(content_type='text/html', body=(
                f'<a id="download" href="/pdf/{filename}">Download</a>'
                '<script>document.querySelector("#download").click()</script>'
            ))
            return
        month = url.path.rsplit('/', 1)[-1]
        if month not in data.counts:
            data.denied.append(url.path)
            request.abort()
            return
        data.visited.append(month)
        year, number = map(int, month.split('-'))
        previous = f'{year - (number == 1):04d}-{12 if number == 1 else number - 1:02d}'
        account = 'SENSITIVE-ACCOUNT-CANARY' if data.wrong_account == month else OPTIONS['account_id']
        observed = number - 2 if data.wrong_month == month else number
        prefix = 'view' if data.same_tab else 'pdf'
        links = ''.join(
            f'<a class="notice" data-key="{i}" href="/{prefix}/{month}-{i}.pdf">Notice</a>'
            for i in range(data.counts[month])
        )
        empty = '<div class="empty">No notices</div>' if not links and data.no_empty != month else ''
        if data.detached:
            navigate = "document.querySelector('#calendar').remove()"
        else:
            navigate = (
                "document.querySelector('.previous').remove();"
                f"setTimeout(() => location.href='/month/{previous}', 80)"
            )
        button = (f'<button class="previous" onclick="{navigate}">Previous</button>'
                  if data.missing_control != month else '')
        content = (
            f'<div id="calendar"><span class="account">{account}</span>'
            f'<span class="year">{year}</span><span class="month">{observed}</span>'
            f'<div class="ready" style="display:none">{links}{empty}</div>{button}</div>'
        )
        if data.ambiguous:
            content += content
        script = '' if data.never_ready == month else (
            "setTimeout(() => document.querySelector('.ready').style.display='block', 120);"
        )
        if data.drift:
            script += "document.addEventListener('click', e => {if(e.target.matches('.notice')) document.querySelector('.account').textContent='SENSITIVE-ACCOUNT-CANARY';});"
        request.fulfill(content_type='text/html', body=content + '<script>' + script + '</script>')

    ctx.route('**/*', route)
    db = Database(path=tmp_path / 'isolated.db')
    task_id = db.create_task('synthetic-calendar', 'synthetic-user')
    run_id = db.create_run(task_id)
    db.set_setting('download_dir', str(tmp_path / 'downloads'))
    monkeypatch.setattr(config, 'RUN_DIR', tmp_path / 'run')
    monkeypatch.setattr(downloads, 'CONSUMERS', [])
    bcs = SimpleNamespace(page=page, service='synthetic-calendar',
                          date_context=DateContext(date(2026, 1, 15), date(2025, 11, 15)))
    run = SimpleNamespace(page=page, context=ctx, bcs=bcs, db=db,
                          task={'id': task_id}, run_id=run_id, files_downloaded=[])
    data.run = run
    data.options = copy.deepcopy(OPTIONS)
    data.open = lambda: page.goto('https://calendar.invalid/month/2026-01')
    data.collect = lambda: runner._collection_actions(run)['replacement_calendar'](
        page.locator('#calendar'), data.options)
    yield data
    assert not data.denied
    ctx.close()
    db.close()


def test_recipe_runner_traverses_replacements_with_equal_and_decreasing_counts(portal):
    portal.open()
    step = {'step': 1, 'methods': [
        {'method': 'locator', 'arguments': [{'selector': '#calendar'}]},
        {'method': 'replacement_calendar', 'arguments': [portal.options]},
    ]}
    ok, error, _ = recipes.validate_recipe(yaml.safe_dump({
        'services': [{'serviceName': 'calendar', 'steps': [step]}],
    }))
    assert ok, error
    runner._process_step(portal.run.bcs, step, runner._collection_actions(portal.run, step))
    assert portal.visited == ['2026-01', '2025-12', '2025-11']
    assert len(portal.run.files_downloaded) == 5
    rows = portal.run.db.list_downloads(task_id=portal.run.task['id'])
    assert len(rows) == 5
    assert all(Path(row['saved_path']).read_bytes().startswith(b'%PDF') for row in rows)


def test_explicit_empty_month_is_covered_before_first_partial_month(portal):
    portal.counts['2025-12'] = 0
    portal.open()
    result = portal.collect()
    assert result == calendar.CalendarResult(
        ((2026, 1), (2025, 12), (2025, 11)), ((2025, 12),), 3)


def test_same_tab_document_page_restores_identity_before_persistence(portal):
    portal.same_tab = True
    portal.options['download_options']['timeout_ms'] = 10000
    portal.open()
    assert portal.collect().downloaded == 5
    assert portal.run.page.url == 'https://calendar.invalid/month/2025-11'
    assert len(portal.run.db.list_downloads(task_id=portal.run.task['id'])) == 5


def test_single_month_window_does_not_click_previous(portal):
    portal.run.bcs.date_context = DateContext(date(2026, 1, 15), date(2026, 1, 15))
    portal.missing_control = '2026-01'
    portal.open()
    assert portal.collect().months == ((2026, 1),)
    assert portal.visited == ['2026-01']


def test_named_month_identity_and_ambiguous_root(portal):
    portal.run.bcs.date_context = DateContext(date(2026, 1, 15), date(2026, 1, 1))
    portal.options['month_names'] = [
        'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
        'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
    ]
    portal.open()
    portal.run.page.locator('.month').evaluate("node => node.textContent='Janvier'")
    assert portal.collect().downloaded == 2
    portal.ambiguous = True
    portal.open()
    with pytest.raises(collection.CollectionError, match='root is ambiguous'):
        portal.collect()


def test_browser_error_does_not_retain_selector_or_account_values(portal):
    portal.options['account_selector'] = '???SENSITIVE-SELECTOR-CANARY'
    portal.open()
    with pytest.raises(collection.CollectionError, match='browser operation failed') as caught:
        portal.collect()
    assert 'SENSITIVE' not in str(caught.value)
    assert not portal.pdfs


@pytest.mark.parametrize('fault,month,error', [
    ('wrong_account', '2025-12', 'account identity'),
    ('wrong_month', '2025-11', 'month identity'),
    ('no_empty', '2025-12', 'timeout'),
    ('missing_control', '2026-01', 'previous control'),
    ('never_ready', '2025-12', 'timeout'),
])
def test_later_failure_preserves_committed_documents_without_automatic_resend(portal, fault, month, error):
    setattr(portal, fault, month)
    if fault == 'no_empty':
        portal.counts[month] = 0
    portal.options['download_options']['timeout_ms'] = (
        1500 if fault in {'no_empty', 'never_ready'} else 5000)
    portal.open()
    with pytest.raises(collection.CollectionError, match=error) as caught:
        portal.collect()
    assert 'SENSITIVE-ACCOUNT-CANARY' not in str(caught.value)
    assert len(portal.run.files_downloaded) >= 2
    rows = portal.run.db.list_downloads(task_id=portal.run.task['id'])
    assert all(Path(row['saved_path']).is_file() for row in rows)
    assert len(portal.pdfs) == len(set(portal.pdfs))


def test_item_budget_refuses_next_month_before_download(portal):
    portal.options['download_options']['max_items'] = 3
    portal.open()
    with pytest.raises(collection.CollectionError, match='limit'):
        portal.collect()
    assert len(portal.pdfs) == len(portal.run.files_downloaded) == 2


def test_month_budget_refuses_window_before_any_download(portal):
    portal.options['max_months'] = 2
    portal.open()
    with pytest.raises(collection.CollectionError, match='month limit'):
        portal.collect()
    assert not portal.pdfs


def test_detachment_is_not_success(portal):
    portal.detached = True
    portal.options['download_options']['timeout_ms'] = 1200
    portal.open()
    with pytest.raises(collection.CollectionError, match='timeout'):
        portal.collect()
    assert len(portal.run.files_downloaded) == 2


def test_wrong_initial_account_refuses_download_and_redacts_identity(portal):
    portal.wrong_account = '2026-01'
    portal.open()
    with pytest.raises(collection.CollectionError, match='account identity') as caught:
        portal.collect()
    assert 'SENSITIVE-ACCOUNT-CANARY' not in str(caught.value)
    assert not portal.pdfs


def test_identity_drift_during_download_refuses_persistence(portal):
    portal.drift = True
    portal.open()
    with pytest.raises(collection.CollectionError, match='account identity'):
        portal.collect()
    assert not portal.run.files_downloaded


def test_existing_filename_collision_contract_is_preserved(portal):
    portal.same_name = True
    portal.open()
    with pytest.raises(collection.CollectionError, match='duplicate suggested filename'):
        portal.collect()
    assert len(portal.run.files_downloaded) == 1


def test_shutdown_preserves_previous_files_and_propagates(portal, monkeypatch):
    original = downloads.track_download

    def track(download, *args):
        if portal.run.files_downloaded:
            raise RunInterrupted('synthetic shutdown')
        return original(download, *args)

    monkeypatch.setattr(downloads, 'track_download', track)
    portal.open()
    with pytest.raises(RunInterrupted):
        portal.collect()
    assert len(portal.run.files_downloaded) == 1
    row, = portal.run.db.list_downloads(task_id=portal.run.task['id'])
    assert Path(row['saved_path']).is_file()


@pytest.mark.parametrize('repeated_keys', [False, True])
def test_operator_resume_skips_persisted_keys_scoped_to_each_month(portal, monkeypatch, repeated_keys):
    original = downloads.track_download
    fail = True

    def track(download, *args):
        if fail and download.suggested_filename == '2025-12-1.pdf':
            raise OSError('synthetic persistence failure')
        return original(download, *args)

    monkeypatch.setattr(downloads, 'track_download', track)
    if repeated_keys:
        portal.options['download_options']['key_attribute'] = 'data-key'
    portal.open()
    with pytest.raises(OSError, match='synthetic persistence failure'):
        portal.collect()
    assert len(portal.run.files_downloaded) == 3

    fail = False
    # Operator restores the first month before explicitly resuming the step.
    portal.open()
    assert portal.collect().downloaded == 2
    assert len(portal.run.files_downloaded) == 5
    rows = portal.run.db.list_downloads(task_id=portal.run.task['id'])
    assert len(rows) == 5
    assert all(Path(row['saved_path']).is_file() for row in rows)
    assert portal.pdfs.count('/pdf/2026-01-0.pdf') == 1
    assert portal.pdfs.count('/pdf/2026-01-1.pdf') == 1
    assert portal.pdfs.count('/pdf/2025-12-0.pdf') == 1
    assert portal.pdfs.count('/pdf/2025-11-0.pdf') == 1


def test_batch_runner_reports_unsupported_calendar_action():
    import BillCollectorServices_pw as batch

    page = SimpleNamespace(
        evaluate=lambda script: True if 'MutationObserver' in script else [],
        locator=lambda **kwargs: object(),
    )
    bcs = SimpleNamespace(page=page, service='synthetic-calendar')
    step = {'step': 1, 'methods': [
        {'method': 'locator', 'arguments': [{'selector': '#calendar'}]},
        {'method': 'replacement_calendar', 'arguments': [copy.deepcopy(OPTIONS)]},
    ]}
    with pytest.raises(batch.StepAbortError, match='replacement_calendar is unavailable in this runner'):
        batch.process_step(bcs, step, collection_actions={})


def test_run_start_timezone_controls_inclusive_months(portal, monkeypatch):
    monkeypatch.setenv('TZ', 'Europe/Zurich')
    # Still December in UTC; already January in the configured timezone.
    dates = pytest.importorskip(
        "billcollector.variables", reason="requires upstream date-context PR #34"
    ).DateContext.capture(2, instant=datetime(2025, 12, 31, 23, 30, tzinfo=timezone.utc))
    portal.run.bcs.date_context = dates
    portal.open()
    assert portal.collect().months == ((2026, 1), (2025, 12))


@pytest.mark.parametrize('option,value', [
    ('max_months', True), ('max_months', float('nan')),
    ('max_months', 121), ('account_id', ''), ('ready_selector', ' '),
    ('month_names', ['January'] * 12),
])
def test_invalid_input_fails_before_browser_access(option, value):
    options = copy.deepcopy(OPTIONS)
    options[option] = value
    with pytest.raises(collection.CollectionError):
        calendar.collect_calendar(None, None, None, None, options, dates=None)


@pytest.mark.parametrize('mutation', ['graceful', 'nested', 'extra_action', 'unknown', 'invalid_budget'])
def test_recipe_validation_refuses_unsafe_calendar_shapes(mutation):
    step = {'step': 1, 'methods': [
        {'method': 'locator', 'arguments': [{'selector': '#calendar'}]},
        {'method': 'replacement_calendar', 'arguments': [copy.deepcopy(OPTIONS)]},
    ]}
    if mutation == 'graceful':
        step['graceful'] = True
    elif mutation == 'nested':
        step = {'step': 1, 'methods': [{'method': 'expect_download'}], 'steps': [step]}
    elif mutation == 'extra_action':
        step['methods'].insert(1, {'method': 'click'})
    elif mutation == 'unknown':
        step['methods'][1]['arguments'][0]['script'] = 'arbitrary code'
    else:
        step['methods'][1]['arguments'][0]['download_options']['timeout_ms'] = True
    ok, _, _ = recipes.validate_recipe(yaml.safe_dump({
        'services': [{'serviceName': 'calendar', 'steps': [step]}],
    }))
    assert not ok
