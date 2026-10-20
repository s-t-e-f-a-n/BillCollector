# -*- coding: utf-8 -*-
"""Shared retention rules for public runner evidence.

The helpers in this module transform transient browser data before it reaches
logs, SQLite, pause contexts, or download consumers.
"""

import re
from urllib.parse import urlsplit, urlunsplit


FAILURE_CATEGORIES = frozenset({
    "timeout",
    "strict-mode",
    "navigation",
    "download",
    "other",
})

_METHOD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_NAVIGATION_METHODS = frozenset({"goto", "go_back", "go_forward", "reload"})


def sanitize_url(value):
    """Retain only a URL's scheme, host (and port), and path.

    Query strings, fragments, and user information are always removed.
    Relative URLs retain only their path.
    """
    if not value:
        return value
    raw_value = str(value)
    try:
        parsed = urlsplit(raw_value)
    except ValueError:
        return ""
    if parsed.scheme.lower() in {"blob", "filesystem"}:
        inner_url = raw_value.partition(":")[2]
        return f"{parsed.scheme}:{sanitize_url(inner_url)}"
    if parsed.scheme and not parsed.netloc:
        return f"{parsed.scheme}:"
    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    try:
        port = parsed.port
    except ValueError:
        port = None
    host = f"{hostname}:{port}" if port is not None else hostname
    path = "/".join(segment.split(";", 1)[0] for segment in parsed.path.split("/"))
    return urlunsplit((parsed.scheme, host, path, "", ""))


def failure_category(method, error):
    """Map a transient exception to one fixed public failure category."""
    method_name = method if isinstance(method, str) else ""
    error_type = type(error).__name__
    if error_type == "TimeoutError":
        return "timeout"
    if error_type in {"AttributeError", "TypeError", "ValueError", "KeyError"}:
        return "other"
    if method_name == "expect_download":
        return "download"
    text = str(error).lower()
    if "strict mode" in text or "strict-mode" in text:
        return "strict-mode"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if method_name in _NAVIGATION_METHODS or "navigation" in text or "net::err" in text:
        return "navigation"
    return "other"


def failure_record(method, error=None, category=None):
    """Return safe structural evidence for one failed recipe method.

    For a strict-mode violation the record additionally carries the resolved
    element count parsed from the exception message (``resolved_count``, an
    int only): it distinguishes a stale locator (0 or 1 match) from an
    ambiguous one (several matches). No message text is retained.
    """
    safe_method = method if isinstance(method, str) and _METHOD_RE.fullmatch(method) else "unknown"
    safe_category = category or failure_category(safe_method, error)
    if safe_category not in FAILURE_CATEGORIES:
        safe_category = "other"
    record = {"method": safe_method, "category": safe_category}
    if safe_category == "strict-mode" and error is not None:
        match = re.search(r"resolved to (\d+) elements", str(error))
        if match:
            record["resolved_count"] = int(match.group(1))
    return record
