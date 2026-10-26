"""User timezone configuration through the shipped Compose interface."""

import json
import os
import shutil
import subprocess
from datetime import date, datetime
from pathlib import Path

import pytest

from billcollector.db import Database
from billcollector.scheduler import TaskScheduler
from billcollector.variables import DateContext

ROOT = Path(__file__).resolve().parents[1]


def compose_environment(tmp_path, monkeypatch, contents, exported_zone=None):
    """Resolve only synthetic configuration; never start a service."""
    docker = shutil.which('docker')
    if docker is None:
        pytest.skip('Docker Compose is required for configuration checks')
    shutil.copyfile(ROOT / 'docker-compose.yml', tmp_path / 'docker-compose.yml')
    (tmp_path / '.env').write_text(contents)
    for name in list(os.environ):
        if name.startswith('COMPOSE_') or name in {
            'TZ', 'APP_UID', 'APP_GID', 'BC_UI_PORT', 'NTFY_HOST', 'NTFY_BASE_URL',
        }:
            monkeypatch.delenv(name)
    if exported_zone is not None:
        monkeypatch.setenv('TZ', exported_zone)
    result = subprocess.run(
        [docker, 'compose', '--project-directory', str(tmp_path),
         '--env-file', str(tmp_path / '.env'), 'config', '--format', 'json'],
        cwd=tmp_path, capture_output=True, text=True, check=True, timeout=30,
    )
    return json.loads(result.stdout)['services']['billcollector']['environment']


def test_compose_user_timezone_reaches_dates_and_cron(tmp_path, monkeypatch):
    environment = compose_environment(tmp_path, monkeypatch, 'TZ=Europe/Zurich\n')
    assert environment['TZ'] == 'Europe/Zurich'
    monkeypatch.setenv('TZ', environment['TZ'])
    context = DateContext.capture(
        instant=datetime.fromisoformat('2026-10-24T22:30:00+00:00'))
    assert context.today == date(2026, 10, 25)
    db = Database(tmp_path / 'schedule.db')
    try:
        task = db.create_task('synthetic', 'test', enabled=True, cron='0 6 * * *')
        scheduler = TaskScheduler(db, lambda task_id: None)
        scheduler.resync()
        trigger = scheduler.scheduler.get_job(f'task-{task}').trigger
        fire = trigger.get_next_fire_time(
            None, datetime.fromisoformat('2026-10-24T22:30:00+00:00'))
        assert fire.isoformat() == '2026-10-25T06:00:00+01:00'
    finally:
        db.close()


@pytest.mark.parametrize(('contents', 'exported_zone', 'expected'), [
    ('', None, 'UTC'),
    ('TZ=\n', None, 'UTC'),
    ('TZ=Europe/Zurich\n', 'America/New_York', 'America/New_York'),
])
def test_compose_timezone_defaults_and_shell_precedence(
        tmp_path, monkeypatch, contents, exported_zone, expected):
    environment = compose_environment(tmp_path, monkeypatch, contents, exported_zone)
    assert environment['TZ'] == expected
    monkeypatch.setenv('TZ', environment['TZ'])
    instant = datetime.fromisoformat('2026-10-24T00:30:00+00:00')
    assert DateContext.capture(instant=instant).today == (
        date(2026, 10, 23) if expected == 'America/New_York' else date(2026, 10, 24))


def test_compose_invalid_timezone_fails_before_scheduling(tmp_path, monkeypatch):
    environment = compose_environment(tmp_path, monkeypatch, 'TZ=Invalid/Synthetic\n')
    monkeypatch.setenv('TZ', environment['TZ'])
    with pytest.raises(ValueError, match='timezone: invalid TZ'):
        DateContext.capture()
    db = Database(tmp_path / 'schedule.db')
    try:
        with pytest.raises(ValueError, match='timezone: invalid TZ'):
            TaskScheduler(db, lambda task_id: None)
    finally:
        db.close()


@pytest.mark.parametrize(('contents', 'exported_zone', 'expected'), [
    ('TZ=Europe/Zurich\n', None, 'Europe/Zurich'),
    ('TZ=Europe/Zurich\n', 'America/New_York', 'America/New_York'),
    ('', None, 'UTC'),
])
def test_direct_process_apps_env_timezone(
        tmp_path, monkeypatch, contents, exported_zone, expected):
    from billcollector import config
    from billcollector.variables import daemon_timezone

    (tmp_path / '.env').write_text(contents)
    monkeypatch.setattr(config, 'APP_DIR', tmp_path)
    # Register even an originally absent key before load_env writes it directly.
    monkeypatch.setenv('TZ', '')
    monkeypatch.delenv('TZ', raising=False)
    if exported_zone is not None:
        monkeypatch.setenv('TZ', exported_zone)
    config.load_env()
    assert str(daemon_timezone()) == expected


@pytest.mark.parametrize(('app_zone', 'exported_zone', 'expected'), [
    (None, None, 'UTC'),
    ('Europe/Zurich', None, 'Europe/Zurich'),
    ('Europe/Zurich', 'America/New_York', 'America/New_York'),
])
def test_runtime_image_does_not_mask_apps_env(tmp_path, app_zone, exported_zone, expected):
    """Optional actual-image proof, using only an isolated synthetic env file."""
    image = os.environ.get('BC_TIMEZONE_TEST_IMAGE')
    if image is None:
        pytest.skip('Set BC_TIMEZONE_TEST_IMAGE to a locally built candidate image')
    env_file = tmp_path / 'app.env'
    env_file.write_text('' if app_zone is None else f'TZ={app_zone}\n')
    env_file.chmod(0o644)
    code = (
        'from billcollector import config; '
        'from billcollector.variables import daemon_timezone; '
        'config.load_env(); print(daemon_timezone())'
    )
    command = ['docker', 'run', '--rm', '--network', 'none', '--read-only',
               '--mount', f'type=bind,src={env_file},dst=/apps/.env,readonly']
    if exported_zone is not None:
        command.extend(['--env', f'TZ={exported_zone}'])
    result = subprocess.run(
        [*command, image, 'python3', '-c', code],
        capture_output=True, text=True, check=True, timeout=30,
    )
    assert result.stdout.strip() == expected
