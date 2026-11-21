"""Opt-in source identities and conservative, versioned PDF revisions.

This is not text deduplication. Generation IDs, Info timestamps and the
alias of one named destination are normalized. Stream bytes, images, fonts, annotations, attachments,
XMP and all other reachable objects participate in the revision digest.
"""

import hashlib
import io
import json
import logging
import re
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import parse_qs, urlsplit

from pypdf import PdfReader
from pypdf.generic import (
    ArrayObject, DictionaryObject, IndirectObject, PdfObject, StreamObject,
    TextStringObject,
)

_PDF_DIAGNOSTICS = ContextVar("notice_pdf_diagnostics", default=None)


class _PrivatePdfDiagnostics(logging.Filter):
    def filter(self, record):
        diagnostics = _PDF_DIAGNOSTICS.get()
        if diagnostics is None:
            return True
        if record.levelno >= logging.WARNING:
            diagnostics.append(True)
        return False


@contextmanager
def _reject_pdf_diagnostics():
    # pypdf can repair malformed values even in strict mode. Refuse those
    # documents and suppress diagnostics that can contain original PDF data.
    diagnostic_filter = _PrivatePdfDiagnostics()
    loggers = [logging.getLogger(name) for name in tuple(sys.modules)
               if name == "pypdf" or name.startswith("pypdf.")]
    diagnostics = []
    token = _PDF_DIAGNOSTICS.set(diagnostics)
    for logger in loggers:
        logger.addFilter(diagnostic_filter)
    try:
        yield
        if diagnostics:
            raise ValueError("PDF parser reported an uncertain document")
    finally:
        for logger in loggers:
            logger.removeFilter(diagnostic_filter)
        _PDF_DIAGNOSTICS.reset(token)


def validate_identity(options):
    if not isinstance(options, dict) or set(options) != {"query_parameters"}:
        raise ValueError("notice_identity requires query_parameters only")
    keys = options["query_parameters"]
    if (not isinstance(keys, list) or not 1 <= len(keys) <= 16
            or any(not isinstance(key, str) or not key.strip() or len(key) > 128
                   for key in keys)
            or len(set(keys)) != len(keys)):
        raise ValueError("notice identity fields must be unique non-empty names")


def source_digest(url, options):
    validate_identity(options)
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in {"https", "http"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or len(url) > 16384):
            raise ValueError
        query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=128)
        fields = []
        for key in sorted(options["query_parameters"]):
            values = query.get(key)
            if not values or len(values) != 1 or not values[0].strip():
                raise ValueError
            fields.append((key, values[0]))
        payload = ["source-v1", parsed.scheme, parsed.hostname, parsed.port,
                   parsed.path, fields]
        return hashlib.sha256(json.dumps(payload, ensure_ascii=True).encode()).hexdigest()
    except (ValueError, TypeError):
        raise ValueError("download URL does not prove the declared notice identity") from None


def revision_digest(path):
    try:
        with _reject_pdf_diagnostics():
            return _revision_digest(path)
    except Exception:
        raise ValueError("cannot establish a notice PDF revision") from None


def _revision_digest(path):
    """Hash the parsed object graph, independent of indirect object numbers.

    The graph preserves sharing and cycles. A different serialization may
    conservatively produce a new revision. No PDF is rewritten. No raw parser
    error leaves this boundary. Pin pypdf: StreamObject._data is its stored
    (encoded) bytes; using it avoids decompression of untrusted streams.
    """
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("notice PDF exceeds the identity size limit")
    try:
        reader = PdfReader(path, strict=True)
        if reader.is_encrypted or not reader.pages:
            raise ValueError
        info = reader.trailer.get("/Info")
        info = info.get_object() if info is not None else None
        # Some generators emit one random named destination alias.
        # Rename only its alias and local references. Keep its target, name
        # tree shape, outline titles and every other string in the graph.
        aliases = set()
        alias = None
        names = reader.root_object.get("/Names")
        if names is not None:
            tree = names.get_object().get("/Dests")
            for _ in range(20):
                if tree is None:
                    break
                tree = tree.get_object()
                kids = tree.get("/Kids")
                if kids is None:
                    entries = tree.get("/Names", [])
                    if (len(entries) == 2 and isinstance(entries[0], TextStringObject)
                            and re.fullmatch(r"[A-Za-z]{3}_[A-Za-z0-9]{6}", str(entries[0]))):
                        alias = str(entries[0])
                        aliases.add(id(entries[0]))
                    break
                if len(kids) != 1:
                    break
                tree = kids[0]
            # Limits on all single-child nodes must refer to that same alias.
            tree = names.get_object().get("/Dests")
            for _ in range(20):
                if tree is None or alias is None:
                    break
                tree = tree.get_object()
                for limit in tree.get("/Limits", []):
                    if isinstance(limit, TextStringObject) and str(limit) == alias:
                        aliases.add(id(limit))
                kids = tree.get("/Kids", [])
                tree = kids[0] if len(kids) == 1 else None
        seen = {}
        digest = hashlib.sha256(b"pdf-graph-v1\0")
        nodes = 0

        def emit(data):
            digest.update(len(data).to_bytes(8, "big"))
            digest.update(data)

        # Direct nesting and graph length have independent limits. Use an
        # explicit DFS stack so linked pages and outlines do not recurse.
        pending = [("visit", reader.trailer, 0)]
        while pending:
            action, value, depth = pending.pop()
            if action == "emit":
                emit(value)
                continue
            nodes += 1
            if nodes > 100000 or depth > 100:
                raise ValueError
            if isinstance(value, IndirectObject):
                key = (value.idnum, value.generation)
                if key in seen:
                    emit(b"ref" + str(seen[key]).encode())
                    continue
                seen[key] = len(seen)
                emit(b"object")
                pending.append(("visit", value.get_object(), 0))
            elif isinstance(value, DictionaryObject):
                emit(b"stream" if isinstance(value, StreamObject) else b"dict")
                omitted = {"/CreationDate", "/ModDate"} if value is info else set()
                if value is reader.trailer:
                    omitted |= {"/ID", "/Size", "/Prev", "/XRefStm"}
                if isinstance(value, StreamObject):
                    omitted |= {"/Length"}
                pending.append(("emit", b"end", 0))
                if isinstance(value, StreamObject):
                    pending.append(("emit", value._data, 0))
                for key in reversed(sorted(value)):
                    if key not in omitted:
                        item = value.raw_get(key)
                        if (alias is not None and isinstance(item, TextStringObject)
                                and str(item) == alias
                                and (key == "/Dest" or
                                     (key == "/D" and value.get("/S") == "/GoTo"))):
                            pending.append(("emit", b"generated-destination-alias", 0))
                        else:
                            pending.append(("visit", item, depth + 1))
                        pending.append(("emit", str(key).encode(), 0))
            elif isinstance(value, ArrayObject):
                emit(b"array")
                pending.append(("emit", b"end", 0))
                pending.extend(("visit", item, depth + 1) for item in reversed(value))
            elif isinstance(value, PdfObject):
                if id(value) in aliases:
                    emit(b"generated-destination-alias")
                else:
                    token = io.BytesIO()
                    value.write_to_stream(token)
                    emit(token.getvalue())
            else:
                raise ValueError

        return digest.hexdigest()
    except Exception:
        raise ValueError("cannot establish a notice PDF revision") from None


def validate_notice_recipe(recipe):
    def visit(step):
        if "notice_identity" in step:
            validate_identity(step["notice_identity"])
            names = {entry.get("method") for entry in step.get("methods", [])}
            if not names & {"expect_download", "download_all", "replacement_calendar", "bourse_direct"}:
                raise ValueError("notice_identity requires a download step")
        for nested in step.get("steps", []):
            visit(nested)
        if "submit" in step:
            visit(step["submit"])
        for phase in step.get("phases", []):
            visit(phase)

    for service in recipe.get("services", []):
        for step in service.get("steps", []):
            visit(step)
