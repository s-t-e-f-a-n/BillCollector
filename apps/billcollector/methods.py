"""C3: inspect the installed sync API without starting Playwright or a browser.

Signatures, annotations and properties come from the pinned package. No method
list is maintained here. Reserved actions retain their separate contracts.
"""

import collections.abc
import inspect
from functools import lru_cache
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints, is_typeddict

from playwright import sync_api
from playwright.sync_api import Page

_RESERVED = frozenset({'login', 'wait_user', 'expect_download',
                       'click_until_absent', 'download_all'})
_UNTIL = (('role', 'get_by_role'), ('test_id', 'get_by_test_id'),
          ('placeholder', 'get_by_placeholder'), ('label', 'get_by_label'),
          ('text', 'get_by_text'), ('selector', 'locator'))


@lru_cache(maxsize=None)
def _attribute(owner, name):
    if name.startswith('_'):
        return None
    attribute = inspect.getattr_static(owner, name, None)
    if attribute is None:
        return None
    target = attribute.fget if isinstance(attribute, property) else attribute
    try:
        hints = get_type_hints(target)
    except (TypeError, NameError):
        hints = {}
    return attribute, hints


def _return_types(annotation):
    if get_origin(annotation) in (Union, UnionType):
        return {item for arg in get_args(annotation) for item in _return_types(arg)}
    if annotation is Any:
        # An evaluate() result has no statically known type. Permit public sync
        # API continuations without inventing a fixed list of browser methods.
        return {value for value in vars(sync_api).values()
                if inspect.isclass(value) and value.__module__.startswith('playwright.')}
    return {get_origin(annotation) or annotation}


def _matches(value, annotation):
    """Check YAML values against Playwright annotations, including TypedDicts."""
    if annotation is Any:
        return True
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, UnionType):
        return any(_matches(value, arg) for arg in args)
    if origin is Literal:
        # Syntax was checked by the shared variable gate. Its string result
        # cannot be compared to an enum until credentials/dates are resolved.
        if isinstance(value, str) and '{{' in value:
            return any(isinstance(arg, str) for arg in args)
        return any(type(value) is type(arg) and value == arg for arg in args)
    if annotation in (int, float):
        return type(value) in ((int, float) if annotation is float else (int,))
    if is_typeddict(annotation):
        fields = get_type_hints(annotation)
        return (isinstance(value, dict)
                and annotation.__required_keys__ <= value.keys() <= fields.keys()
                and all(_matches(item, fields[key]) for key, item in value.items()))
    if origin in (list, tuple, collections.abc.Sequence):
        return (isinstance(value, (list, tuple))
                and all(_matches(item, args[0]) for item in value))
    if origin in (dict, collections.abc.Mapping):
        return (isinstance(value, dict)
                and all(_matches(key, args[0]) and _matches(item, args[1])
                        for key, item in value.items()))
    if origin is collections.abc.Callable:
        return callable(value)
    try:
        return isinstance(value, origin or annotation)
    except TypeError:
        return False


def _kwargs(arguments):
    if not isinstance(arguments, list) or any(not isinstance(arg, dict) for arg in arguments):
        raise ValueError('arguments must be a list of option objects')
    return {key: value for arg in arguments for key, value in arg.items()}


def _check_arguments(attribute, hints, arguments):
    if not callable(attribute):
        if arguments:
            raise ValueError('property does not accept arguments')
        return
    signature = inspect.signature(attribute)
    # C3 explicitly retains press("Enter") in login submit chains.
    positional = arguments == ['Enter'] and attribute.__name__ == 'press'
    kwargs = {} if positional else _kwargs(arguments)
    try:
        signature.bind(None, *(['Enter'] if positional else []), **kwargs)
    except TypeError:
        raise ValueError('missing or unsupported argument name') from None
    parameters = signature.parameters
    for key, value in kwargs.items():
        if key == 'self' or key not in parameters:
            raise ValueError('unsupported argument name')
        annotation = hints.get(key, Any)
        if not _matches(value, annotation):
            raise ValueError('unsupported argument type or literal')


def _wait_user(arguments):
    options = _kwargs(arguments)
    if options.keys() - {'prompt', 'until'}:
        raise ValueError('unsupported wait_user argument name')
    if 'prompt' in options and not isinstance(options['prompt'], str):
        raise ValueError('wait_user prompt must be a string')
    if 'until' not in options:
        return
    until = options['until']
    if not isinstance(until, dict):
        raise ValueError('wait_user until must be a locator object')
    for key, name in _UNTIL:
        if key in until:
            attribute, hints = _attribute(Page, name)
            # Keep the C3 locator keys; Playwright calls these two values text.
            kwargs = dict(until)
            if key in {'placeholder', 'label'}:
                kwargs['text'] = kwargs.pop(key)
            _check_arguments(attribute, hints, [kwargs])
            return
    raise ValueError('wait_user until requires a recognized locator key')


def validate_method_recipe(recipe):
    """Shared UI/run-start gate; diagnostics never contain argument values."""
    def visit(step, service):
        owners = {Page}
        for entry in step.get('methods', []):
            name = entry['method']
            location = f'service {service}, step {step["step"]}, method {name}'
            try:
                arguments = entry.get('arguments', [])
                if name == 'wait_user':
                    _wait_user(arguments)
                    continue
                if name == 'expect_download':
                    if arguments:
                        raise ValueError('expect_download does not accept arguments')
                    continue
                if name in _RESERVED:
                    continue
                following, failures = set(), []
                for owner in owners:
                    found = _attribute(owner, name)
                    if found is None:
                        continue
                    attribute, hints = found
                    try:
                        _check_arguments(attribute, hints, arguments)
                    except ValueError as error:
                        failures.append(str(error))
                        continue
                    result = hints.get('return', Any)
                    for target in _return_types(result):
                        following.add(owner if target is type(None) else target)
                if not following:
                    raise ValueError(failures[0] if failures else
                                     'unknown public Playwright attribute')
                owners = following
            except ValueError as error:
                raise ValueError(f'{location}: {error}') from None
        for child in step.get('steps', []):
            visit(child, service)
        if 'submit' in step:
            visit(step['submit'], service)
        for phase in step.get('phases', []):
            for child in phase.get('steps', []):
                visit(child, service)
            visit(phase['submit'], service)

    for service in recipe.get('services', []):
        for step in service.get('steps', []):
            visit(step, service['serviceName'])
