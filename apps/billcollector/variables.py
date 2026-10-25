"""Daemon argument variables (issue #26); legacy batch substitution is separate.

Parse only original recipe strings. Replacement values are opaque, including
credentials which happen to contain variable delimiters. Errors carry locations
and categories only, never recipe values or credential data.
"""

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_CREDENTIALS = frozenset({'USERNAME', 'PASSWORD', 'OTP'})
_DATE = re.compile(r'(TODAY(?:[+-][0-9]+d)?|DATE_FROM|DATE_TO)\Z')
_FORMAT = re.compile(r'(?:%[Ymd%]|[-/._ ])+\Z')


def daemon_timezone():
    """One explicit zone for both calendar variables and cron triggers."""
    try:
        return ZoneInfo(os.environ.get('TZ', 'UTC'))
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError('timezone: invalid TZ') from None


def validate_window(value):
    if type(value) is not int or value < 1:
        raise ValueError('date_window_days: expected positive integer')
    return value


def parse_override(value, today):
    if (not isinstance(value, str)
            or re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value) is None):
        raise ValueError('date_from: invalid recovery date')
    try:
        start = date.fromisoformat(value)
    except ValueError:
        raise ValueError('date_from: invalid recovery date') from None
    if start > today:
        raise ValueError('date_from: recovery date exceeds DATE_TO')
    return start


@dataclass(frozen=True)
class DateContext:
    today: date
    date_from: date

    @classmethod
    def capture(cls, window=90, override=None, *, instant=None):
        zone = daemon_timezone()
        instant = instant if instant is not None else datetime.now(timezone.utc)
        try:
            today = instant.astimezone(zone).date()
        except (OverflowError, ValueError):
            raise ValueError("timezone: date overflow") from None
        try:
            start = today - timedelta(days=validate_window(window) - 1)
        except OverflowError:
            raise ValueError('date_window_days: date overflow') from None
        if override is not None:
            start = parse_override(override, today)
        return cls(today, start)

    def resolve(self, expression, fmt=None):
        if expression == 'DATE_FROM':
            value = self.date_from
        else:
            value = self.today
            if expression.startswith('TODAY') and len(expression) > 5:
                # Bound the decimal before int(): no Python digit-limit errors
                # or giant integer arithmetic can escape the sanitized error.
                digits = expression[6:-1].lstrip('0') or '0'
                if len(digits) > 7 or int(digits) > date.max.toordinal():
                    raise ValueError('date overflow')
                days = int(digits) * (-1 if expression[5] == '-' else 1)
                try:
                    value += timedelta(days=days)
                except OverflowError:
                    raise ValueError('date overflow') from None
        if fmt is None:
            return value.isoformat()
        fields = {'Y': f'{value.year:04d}', 'm': f'{value.month:02d}',
                  'd': f'{value.day:02d}', '%': '%'}
        return re.sub(r'%([Ymd%])', lambda match: fields[match[1]], fmt)


def _tokens(text, location):
    """Yield (start, end, expression, format) after strict syntax validation."""
    cursor = 0
    while cursor < len(text):
        opening = text.find('{{', cursor)
        closing = text.find('}}', cursor)
        if closing != -1 and (opening == -1 or closing < opening):
            raise ValueError(f'{location}: unbalanced variable delimiters')
        if opening == -1:
            return
        end = text.find('}}', opening + 2)
        if end == -1:
            raise ValueError(f'{location}: unbalanced variable delimiters')
        expression, separator, fmt = text[opening + 2:end].partition('|')
        if expression not in _CREDENTIALS and not _DATE.fullmatch(expression):
            raise ValueError(f'{location}: unknown variable or unsupported syntax')
        if separator:
            if (expression in _CREDENTIALS or not _FORMAT.fullmatch(fmt)
                    or not re.search(r'%[Ymd]', fmt.replace('%%', ''))):
                raise ValueError(f'{location}: invalid date format')
        yield opening, end + 2, expression, fmt if separator else None
        cursor = end + 2


def expand_argument(value, credentials, dates=None, location='arguments'):
    """Recursively expand string values once; preserve keys and other values.

    ``credentials`` maps names to lazy resolvers (OTP stays fresh). Passing no
    resolvers/context validates syntax without reading credentials or the clock.
    """
    if isinstance(value, dict):
        return {key: expand_argument(item, credentials, dates,
                                     f'{location}/{index}')
                for index, (key, item) in enumerate(value.items())}
    if isinstance(value, list):
        return [expand_argument(item, credentials, dates, f'{location}/{index}')
                for index, item in enumerate(value)]
    if not isinstance(value, str):
        return value
    parts = []
    cursor = 0
    for start, end, expression, fmt in _tokens(value, location):
        parts.append(value[cursor:start])
        if expression in _CREDENTIALS:
            replacement = (credentials[expression]() if credentials is not None
                           else value[start:end])
        elif dates is not None:
            try:
                replacement = dates.resolve(expression, fmt)
            except ValueError:
                raise ValueError(f'{location}: date overflow') from None
        else:
            replacement = value[start:end]
        if (credentials is not None and expression in _CREDENTIALS
                and start == 0 and end == len(value)):
            return replacement  # Preserve optional-TOTP None for exact tokens.
        parts.append('' if replacement is None else str(replacement))
        cursor = end
    parts.append(value[cursor:])
    return ''.join(parts)


def validate_variable_recipe(recipe, dates=None):
    """Shared UI/run-start validation of every original method argument."""
    def visit(value, location):
        if isinstance(value, dict):
            for key, label in (("serviceName", "service"), ("step", "step"), ("method", "method")):
                if key in value:
                    location += f", {label} {value[key]}"
            for key, item in value.items():
                if key in {'arguments', 'success'}:
                    expand_argument(item, None, dates, f'{location}/{key}')
                else:
                    visit(item, f'{location}/{key}')
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f'{location}/{index}')
    visit(recipe, 'recipe')
