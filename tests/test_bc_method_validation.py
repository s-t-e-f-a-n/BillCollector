"""C3 recipe validation through the shared UI and run-start gates."""

import pytest
import yaml

from billcollector.recipes import validate_recipe


def document(methods, **step_options):
    return {'services': [{'serviceName': 'synthetic', 'steps': [
        {'step': 17, 'methods': methods, **step_options}]}]}


def test_unknown_method_is_rejected_with_location_without_argument_values():
    recipe = document([{'method': 'unknown_method',
                        'arguments': [{'value': 'synthetic-secret'}]}])
    ok, error, data = validate_recipe(yaml.safe_dump(recipe))
    assert not ok
    assert data is None
    assert 'synthetic' in error
    assert '17' in error
    assert 'unknown_method' in error
    assert 'synthetic-secret' not in error


def test_chain_tracks_properties_frames_and_void_actions():
    recipe = document([
        {'method': 'get_by_role', 'arguments': [{'role': 'main'}]},
        {'method': 'first'},
        {'method': 'filter', 'arguments': [{'has_text': 'Invoice'}]},
        {'method': 'locator', 'arguments': [{'selector_or_locator': 'iframe'}]},
        {'method': 'content_frame'},
        {'method': 'get_by_label', 'arguments': [{'text': 'Account'}]},
        {'method': 'click'},
        {'method': 'fill', 'arguments': [{'value': '{{PASSWORD}}'}]},
    ])
    ok, error, _ = validate_recipe(yaml.safe_dump(recipe))
    assert ok, error


def test_method_on_wrong_chain_type_is_rejected():
    recipe = document([
        {'method': 'locator', 'arguments': [{'selector': 'button'}]},
        {'method': 'goto', 'arguments': [{'url': 'https://invalid.example'}]},
    ])
    ok, error, _ = validate_recipe(yaml.safe_dump(recipe))
    assert not ok
    assert 'goto' in error
    assert '17' in error


@pytest.mark.parametrize('methods', [
    [{'method': 'goto', 'arguments': [{'url': 'private'}, {'unknown': 'secret'}]}],
    [{'method': 'goto', 'arguments': [{'url': 42}]}],
    [{'method': 'goto', 'arguments': [{'url': 'private'}, {'timeout': True}]}],
    [{'method': 'goto', 'arguments': [{'url': 'private'}, {'wait_until': 'secret'}]}],
    [{'method': 'locator', 'arguments': [{'selector': 'button'}]},
     {'method': 'first', 'arguments': [{'value': 'secret'}]}],
    [{'method': '_impl_obj'}],
])
def test_invalid_arguments_and_private_attributes_are_rejected(methods):
    ok, error, _ = validate_recipe(yaml.safe_dump(document(methods)))
    assert not ok
    assert 'synthetic' in error
    assert '17' in error
    assert 'private' not in error
    assert 'secret' not in error


@pytest.mark.parametrize('arguments', [
    [{'unexpected': 'secret'}], [{'prompt': 12}], [{'until': 'secret'}],
    [{'until': {}}], [{'until': {'nonsense': 'secret'}}],
    [{'until': {'role': 'button', 'unknown': 'secret'}}],
])
def test_wait_user_arguments_are_validated(arguments):
    ok, error, _ = validate_recipe(yaml.safe_dump(document([
        {'method': 'wait_user', 'arguments': arguments}])))
    assert not ok
    assert 'wait_user' in error
    assert 'synthetic' in error
    assert '17' in error
    assert 'secret' not in error


@pytest.mark.parametrize('arguments', [[], [{'prompt': 'act'}],
    [{'until': {'role': 'button', 'name': 'Continue', 'exact': True}}],
    [{'until': {'selector': '#account'}}],
])
def test_wait_user_valid_options_are_preserved(arguments):
    ok, error, _ = validate_recipe(yaml.safe_dump(document([
        {'method': 'wait_user', 'arguments': arguments}])))
    assert ok, error


def test_schema_error_does_not_disclose_argument_value():
    recipe = document([{'method': 'goto', 'arguments': [{'url': ['synthetic-secret']}]}])
    ok, error, _ = validate_recipe(yaml.safe_dump(recipe))
    assert not ok
    assert 'synthetic-secret' not in error
    assert 'synthetic' in error
    assert '17' in error


def test_unknown_variable_has_service_step_method_context():
    ok, error, _ = validate_recipe(yaml.safe_dump(document([
        {'method': 'goto', 'arguments': [{'url': 'private-{{UNKNOWN}}'}]}])))
    assert not ok
    assert 'synthetic' in error
    assert '17' in error
    assert 'goto' in error
    assert 'private' not in error


def test_run_start_rejects_unknown_method_before_resources(tmp_path, monkeypatch, capsys):
    from unittest.mock import Mock

    from billcollector import config, runner
    from billcollector.db import Database

    path = tmp_path / 'recipe.yaml'
    path.write_text(yaml.safe_dump(document([{'method': 'unknown_method'}])))
    monkeypatch.setattr(config, 'DB_FILE', tmp_path / 'isolated.db')
    db = Database(config.DB_FILE)
    task = db.create_task('synthetic', 'test', recipe_file=str(path))
    db.close()
    resources = Mock(side_effect=AssertionError('must not acquire resources'))
    monkeypatch.setattr(runner.display, 'allocate_display', resources)
    monkeypatch.setattr(runner, '_vault_preflight', resources)
    monkeypatch.setattr(runner, 'sync_playwright', resources)
    assert runner.run_task(task) == 1
    resources.assert_not_called()
    error = capsys.readouterr().err
    assert 'synthetic' in error and '17' in error and 'unknown_method' in error


def test_shipped_recipes_and_documented_login_candidate_validate():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    paths = sorted((root / 'apps/recipes_playwright').glob('recipe-pw__*.yaml'))
    assert len(paths) == 15
    for path in paths:
        ok, error, _ = validate_recipe(path.read_text())
        assert ok, (path.name, error)
    text = (root / 'doc/SAFE_LOGIN.md').read_text()
    candidate = re.search(r'```yaml\n(.*?)```', text, re.S)[1]
    ok, error, _ = validate_recipe(candidate)
    assert ok, error


@pytest.mark.parametrize('place', ['download', 'preparation', 'submit', 'phase'])
def test_nested_method_errors_have_the_child_step_context(place):
    child = {'step': 42, 'methods': [
        {'method': 'locator', 'arguments': [{'selector': '#account'}]},
        {'method': 'fill', 'arguments': [{'unsupported': 'secret'}]},
    ]}
    if place == 'download':
        recipe = document([{'method': 'expect_download'}], steps=[child])
    else:
        submit = {'step': 43, 'methods': [
            {'method': 'locator', 'arguments': [{'selector': '#submit'}]},
            {'method': 'click'}]}
        success = {'selector': '#account'}
        options = {'steps': [child], 'submit': submit}
        if place == 'submit':
            child['methods'][-1]['method'] = 'click'
            options = {'submit': child}
        if place == 'phase':
            options = {'phases': [{'steps': [child], 'submit': submit, 'success': success}]}
        recipe = document([{'method': 'login', 'arguments': [{'success': success}]}], **options)
    ok, error, _ = validate_recipe(yaml.safe_dump(recipe))
    assert not ok
    assert 'synthetic' in error and '42' in error
    assert 'secret' not in error


@pytest.mark.parametrize('methods', [
    [{'method': 'context'}, {'method': 'new_page'}, {'method': 'goto',
      'arguments': [{'url': 'https://invalid.example/{{TODAY}}'}]}],
    [{'method': 'goto', 'arguments': [{'url': 'https://invalid.example'}]},
     {'method': 'request'}, {'method': 'method'}],
    [{'method': 'locator', 'arguments': [{'selector': 'iframe'}]},
     {'method': 'element_handle'}, {'method': 'content_frame'},
     {'method': 'get_by_label', 'arguments': [{'text': 'Name'}]}, {'method': 'click'}],
    [{'method': 'screenshot', 'arguments': [{'mask_color': '#000'},
                                         {'clip': {'x': 0, 'y': 0, 'width': 5, 'height': 5}}]}],
])
def test_public_return_types_and_typed_options_remain_supported(methods):
    ok, error, _ = validate_recipe(yaml.safe_dump(document(methods)))
    assert ok, error


@pytest.mark.parametrize('key', ['role', 'test_id', 'placeholder', 'label', 'text', 'selector'])
def test_wait_user_recognized_locator_keys_remain_supported(key):
    value = 'button' if key == 'role' else 'Account'
    ok, error, _ = validate_recipe(yaml.safe_dump(document([
        {'method': 'wait_user', 'arguments': [{'until': {key: value}}]}])))
    assert ok, error


def test_required_playwright_arguments_are_checked():
    ok, error, _ = validate_recipe(yaml.safe_dump(document([{'method': 'goto'}])))
    assert not ok
    assert 'synthetic' in error and '17' in error and 'goto' in error


def test_login_positional_enter_submit_is_preserved():
    recipe = document([{'method': 'login', 'arguments': [{'success': {'selector': '#account'}}]}],
                      submit={'step': 42, 'methods': [
                          {'method': 'locator', 'arguments': [{'selector': '#submit'}]},
                          {'method': 'press', 'arguments': ['Enter']}]})
    ok, error, _ = validate_recipe(yaml.safe_dump(recipe))
    assert ok, error
