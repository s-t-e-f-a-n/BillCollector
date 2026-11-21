"""One agreed catalog adapter, with native login/date/download ownership.

The catalog module is trusted application code, not a sandboxed plugin. Only
its literal CHAINS declaration is read during preflight. No import, discovery,
registration, recipe-selected path or alternate credential engine is provided.
"""

import ast
import copy
import inspect
import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from . import config
from .collection import CollectionError
from .interrupt import RunInterrupted

ACTION = 'bourse_direct'
IDENTITY = {'query_parameters': ['nc', 'type', 'year', 'month', 'day']}


def _document(chains):
    return {'services': [{'serviceName': 'BourseDirect adapter', 'steps': [
        {'step': index, 'methods': chain}
        for index, chain in enumerate(chains.values(), 1)]}]}


def _validate_chains(chains):
    from .methods import _RESERVED, validate_method_recipe

    if not isinstance(chains, dict) or not chains or len(chains) > 64:
        raise ValueError('adapter requires 1..64 named chains')
    for name, chain in chains.items():
        if (not isinstance(name, str) or not name.isidentifier()
                or not isinstance(chain, list) or not 1 <= len(chain) <= 16):
            raise ValueError('adapter chain declaration is invalid')
        for entry in chain:
            if (not isinstance(entry, dict) or set(entry) - {'method', 'arguments'}
                    or not isinstance(entry.get('method'), str)
                    or entry['method'] in _RESERVED):
                raise ValueError('adapter chains require public Playwright methods only')
    validate_method_recipe(_document(chains))


@dataclass(frozen=True)
class Candidate:
    source: bytes
    chains: dict


def candidate():
    """Freeze source without executing catalog code at load/save/run start."""
    try:
        path = config.RECIPE_DIR / 'bourse_direct_adapter.py'
        metadata = path.stat()
        if metadata.st_uid != os.getuid() or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ValueError('adapter catalog must be runtime-owned and not group/world-writable')
        source = path.read_bytes()
        if len(source) > 256 * 1024:
            raise ValueError
        tree = ast.parse(source)
        declarations = [node for node in tree.body if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == 'CHAINS'
                                for target in node.targets)]
        if len(declarations) != 1:
            raise ValueError
        chains = ast.literal_eval(declarations[0].value)
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name == 'collect']
        if (len(functions) != 1 or functions[0].decorator_list
                or [arg.arg for arg in functions[0].args.args] != ['api', 'options']
                or functions[0].args.defaults or functions[0].args.posonlyargs
                or functions[0].args.kwonlyargs or functions[0].args.vararg
                or functions[0].args.kwarg):
            raise ValueError
    except ValueError as error:
        if str(error).startswith('adapter catalog must be'):
            raise
        raise ValueError('fixed catalog adapter source or literal CHAINS is invalid') from None
    except (OSError, SyntaxError, TypeError, RecursionError):
        raise ValueError('fixed catalog adapter source or literal CHAINS is invalid') from None
    _validate_chains(chains)
    # These are also installed Playwright calls. Check them before resources.
    _validate_chains({'read': [
        {'method': 'context'}, {'method': 'request'},
        {'method': 'get', 'arguments': [{'url': 'https://example.invalid',
                                       'max_redirects': 0, 'timeout': 1}]},
        {'method': 'body'}]})
    return Candidate(source, chains)


def validate_options(options):
    if (not isinstance(options, dict)
            or set(options) != {'account_type', 'max_months', 'max_items', 'timeout_ms'}
            or options['account_type'] not in ('PEA', 'PEA-PME')):
        raise ValueError('adapter requires one supported account type and fixed bounds')
    for name, maximum in [('max_months', 120), ('max_items', 200), ('timeout_ms', 7_200_000)]:
        if type(options[name]) is not int or not 1 <= options[name] <= maximum:
            raise ValueError('adapter bound is invalid')


def prepare(recipe):
    """One standalone collection after native final-session proof, one service."""
    found = []

    def visit(step, top=False):
        if any(entry.get('method') == ACTION for entry in step.get('methods', [])):
            if (not top or len(step['methods']) != 1 or step.get('graceful', False)
                    or any(key in step for key in ('steps', 'submit', 'phases'))
                    or step.get('notice_identity') != IDENTITY):
                raise ValueError('adapter requires one standalone notice collection step')
            arguments = step['methods'][0].get('arguments', [])
            if len(arguments) != 1:
                raise ValueError('adapter requires one options object')
            validate_options(arguments[0])
            found.append(step)
        for child in step.get('steps', []):
            visit(child)
        if 'submit' in step:
            visit(step['submit'])
        for phase in step.get('phases', []):
            visit(phase)

    services = recipe.get('services', [])
    for service in services:
        for step in service.get('steps', []):
            visit(step, True)
    if not found:
        return None
    if len(found) != 1 or len(services) != 1:
        raise ValueError('adapter requires one service and one collection per task')
    from .login import is_login

    ordered = sorted(services[0]['steps'], key=lambda step: step['step'])
    before = ordered[:ordered.index(found[0])]
    if sum(is_login(step) for step in ordered) != 1 or not any(is_login(step) for step in before):
        raise ValueError('adapter requires a preceding native login with final-session proof')
    return candidate()


class Original:
    def __init__(self, body, url, filename):
        self.body, self.url, self.suggested_filename = body, url, filename

    def save_as(self, path):
        Path(path).write_bytes(self.body)


def _data(value):
    """Return data only; do not hand the adapter an unchecked browser object."""
    if value is None or type(value) in (str, int, float, bool, bytes):
        return value
    if isinstance(value, (list, tuple)):
        return [_data(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _data(item) for key, item in value.items()}
    raise CollectionError('adapter chain must return data, not a browser object')


class Acquisition:
    """Capabilities for the fixed adapter. No vault, DB or login callback."""

    def __init__(self, ctx, spec, options, save_download):
        from .calendar import _months

        validate_options(options)
        self.dates = ctx.bcs.date_context
        self.months = tuple(_months(self.dates, options['max_months']))
        self._page, self._context = ctx.page, ctx.context
        self._chains, self._save = copy.deepcopy(spec.chains), save_download
        self._deadline = time.monotonic() + options['timeout_ms'] / 1000
        self._maximum, self._offered, self._saved, self._reads = options['max_items'], 0, 0, 0
        self._origin = self._origin_of(ctx.page.url.split('#', 1)[0])

    @staticmethod
    def _origin_of(url):
        try:
            parts = urlsplit(url)
            if (parts.scheme not in ('http', 'https') or not parts.hostname
                    or parts.username is not None or parts.password is not None
                    or parts.fragment):
                raise ValueError
            return parts.scheme, parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80)
        except (ValueError, TypeError):
            raise CollectionError('adapter source origin is invalid') from None

    def remaining_ms(self):
        remaining = int((self._deadline - time.monotonic()) * 1000)
        if remaining < 1:
            raise CollectionError('adapter total deadline expired')
        return remaining

    def offered(self, count):
        """Count every offered item, including repeats, before reading a month."""
        self.remaining_ms()
        if type(count) is not int or count < 0 or self._offered + count > self._maximum:
            raise CollectionError('adapter offered item limit exceeded')
        self._offered += count

    def call(self, name, **arguments):
        """Use one declared C3 chain; dynamic kwargs replace its last arguments."""
        if name not in self._chains:
            raise CollectionError('adapter chain is not declared')
        chain = copy.deepcopy(self._chains[name])
        if arguments:
            chain[-1]['arguments'] = [arguments]
        _validate_chains({name: chain})
        previous, result = self._page, None
        for entry in chain:
            remaining = self.remaining_ms()
            method = getattr(previous, entry['method'])
            args = entry.get('arguments', [])
            positional = ['Enter'] if args == ['Enter'] else []
            kwargs = {key: value for item in ([] if positional else args)
                      for key, value in item.items()}
            # A zero timeout means unbounded in Playwright. Replace it here.
            if callable(method) and 'timeout' in inspect.signature(method).parameters:
                kwargs['timeout'] = min(kwargs.get('timeout') or remaining, remaining)
            result = method(*positional, **kwargs) if callable(method) else method
            previous = result if result is not None else previous
        self.remaining_ms()
        return _data(result)

    def read(self, url, *, pdf=False):
        """Read unchanged bytes through the current authenticated request context."""
        if self._origin_of(url) != self._origin or len(url) > 16384:
            raise CollectionError('adapter request origin changed')
        if self._reads >= self._maximum * 2:
            raise CollectionError('adapter request limit exceeded')
        self._reads += 1
        response = self._context.request.get(
            url, max_redirects=0, timeout=min(30_000, self.remaining_ms()))
        try:
            if response.status != 200 or response.url != url:
                raise CollectionError('adapter response is not proven')
            body = response.body()
            self.remaining_ms()
            if (not body or len(body) > 20 * 1024 * 1024
                    or (pdf and not body.startswith(b'%PDF-'))):
                raise CollectionError('adapter original response is invalid')
            return body
        finally:
            response.dispose()

    def save_original(self, url, filename):
        if self._saved >= self._offered:
            raise CollectionError('adapter original exceeds offered item count')
        if (not isinstance(filename, str) or not filename.endswith('.pdf')
                or Path(filename).name != filename or '\\' in filename):
            raise CollectionError('adapter original filename is invalid')
        body = self.read(url, pdf=True)
        self._saved += 1
        self._save(Original(body, url, filename))
        self.remaining_ms()


def collect(ctx, spec, options, save_download):
    """Execute the frozen trusted catalog candidate once; redact its failures."""
    try:
        if spec is None:
            raise CollectionError('adapter was not prepared before resources')
        api = Acquisition(ctx, spec, options, save_download)
        namespace = {'__name__': 'billcollector_bourse_direct_adapter'}
        # Fixed operator-installed application code; never a YAML-selected path.
        code = compile(spec.source, '<bourse_direct_adapter>', 'exec')
        exec(code, namespace)  # nosec B102
        namespace['collect'](api, copy.deepcopy(options))
        api.remaining_ms()
    except RunInterrupted:
        raise
    except Exception:
        raise CollectionError('adapter acquisition failed; inspect before resuming') from None
