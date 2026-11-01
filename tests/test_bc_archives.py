"""Synthetic ZIP transport acceptance: no provider, vault or shared state."""

import hashlib
import io
import os
import shutil
import stat
import sys
import tempfile
import threading
import unittest
import zipfile

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from pypdf import PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import archives, collection, db, downloads, recipes, runner  # noqa: E402
from tests.test_bc_collection import _Events, _Listing, _Page  # noqa: E402

_REQUESTED_BROWSER_PATH = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")


def _synthetic_pdf():
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_metadata({"/Title": "Synthetic unchanged original"})
    writer.write(output)
    return output.getvalue()


PDF = _synthetic_pdf()


def make_zip(entries, compression=zipfile.ZIP_DEFLATED):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=compression) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return output.getvalue()


class Download:
    suggested_filename = "envelope.zip"
    url = "https://synthetic.invalid/document?token=fake"

    def __init__(self, path):
        self.source = path

    def path(self):
        return self.source

    def save_as(self, target):
        shutil.copyfile(self.source, target)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "transport.zip"

    def prepare(self, data):
        self.source.write_bytes(data)
        return archives.pdf_download(Download(self.source))

    def reject(self, data, error=ValueError):
        with self.assertRaises(error):
            with self.prepare(data):
                self.fail("invalid input reached persistence")

    def test_unchanged_pdf_and_flattened_name_with_cleanup(self):
        for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with self.subTest(compression=compression):
                with self.prepare(make_zip([("safe/Original.PDF", PDF)], compression)) as document:
                    self.assertEqual(document.suggested_filename, "Original.PDF")
                    self.assertEqual(document.url, Download.url)
                    saved = self.root / "saved.pdf"
                    document.save_as(saved)
                    self.assertEqual(saved.read_bytes(), PDF)
                    temporary = document.source
                self.assertFalse(temporary.exists())

    def test_large_member_streams_in_chunks_without_rewriting(self):
        content = PDF + b"\n" * (512 * 1024)
        for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with self.subTest(compression=compression):
                with self.prepare(make_zip([("a.pdf", content)], compression)) as document:
                    self.assertEqual(document.source.read_bytes(), content)

    def test_cleanup_when_persistence_fails(self):
        with self.assertRaisesRegex(RuntimeError, "synthetic"):
            with self.prepare(make_zip([("a.pdf", PDF)])) as document:
                temporary = document.source
                raise RuntimeError("synthetic")
        self.assertFalse(temporary.exists())

    def test_member_count_and_non_pdf_content(self):
        for entries in ([], [("a.pdf", PDF), ("b.pdf", PDF)],
                        [("a.pdf", PDF), ("notes.txt", b"text")],
                        [("dir/", b""), ("dir/a.pdf", PDF)],
                        [("a.txt", PDF)], [("a.pdf", b"<html>error</html>")],
                        [("a.pdf", b"")]):
            with self.subTest(entries=[name for name, _ in entries]):
                self.reject(make_zip(entries))

    def test_unsafe_member_paths(self):
        for name in ("../a.pdf", "/a.pdf", "a/../b.pdf", "./a.pdf", "a//b.pdf",
                     "C:/a.pdf", "C:a.pdf", "a\\b.pdf", "a\nb.pdf", "a\x7fb.pdf"):
            with self.subTest(name=name):
                self.reject(make_zip([(name, PDF)]))
        member = zipfile.ZipInfo("a.pdf\x00.txt")
        with self.assertRaises(ValueError):
            archives._member_name(member)

    def test_special_and_directory_members(self):
        for kind in (stat.S_IFLNK, stat.S_IFDIR, stat.S_IFIFO, stat.S_IFSOCK,
                     stat.S_IFCHR, stat.S_IFBLK):
            member = zipfile.ZipInfo("a.pdf")
            member.create_system = 3
            member.external_attr = (kind | 0o600) << 16
            with self.subTest(kind=kind):
                self.reject(make_zip([(member, PDF)]))
        member = zipfile.ZipInfo("a.pdf")
        member.external_attr = 0x10
        self.reject(make_zip([(member, PDF)]))

    def test_archive_and_pdf_size_limits_inclusive(self):
        data = make_zip([("a.pdf", PDF)])
        with mock.patch.object(archives, "MAX_ARCHIVE_BYTES", len(data)):
            with self.prepare(data):
                pass
        with mock.patch.object(archives, "MAX_ARCHIVE_BYTES", len(data) - 1):
            self.reject(data)
        with mock.patch.object(archives, "MAX_PDF_BYTES", len(PDF)):
            with self.prepare(data):
                pass
        with mock.patch.object(archives, "MAX_PDF_BYTES", len(PDF) - 1):
            self.reject(data)
        # A highly compressible member must be rejected before opening it.
        data = make_zip([("bomb.pdf", b"%PDF-" + b"0" * 100_000)])
        with mock.patch.object(archives, "MAX_PDF_BYTES", 1000), \
                mock.patch.object(zipfile.ZipFile, "open", side_effect=AssertionError):
            self.reject(data)

    def test_metadata_is_bounded_before_parsing_many_tiny_members(self):
        data = make_zip([(f"{index}.pdf", b"") for index in range(6000)])
        with self.assertRaisesRegex(ValueError, "metadata exceeds"):
            with self.prepare(data):
                self.fail("oversized directory reached persistence")

    def test_actual_stream_is_bounded_even_with_false_metadata(self):
        data = make_zip([("a.pdf", PDF)])
        with mock.patch.object(archives, "MAX_PDF_BYTES", len(PDF)), \
                mock.patch.object(zipfile.ZipFile, "open", return_value=io.BytesIO(PDF * 2)):
            self.reject(data)
        with mock.patch.object(zipfile.ZipFile, "open", return_value=io.BytesIO(PDF[:-1])):
            self.reject(data)

    def test_invalid_truncated_corrupt_and_encrypted_archives(self):
        data = make_zip([("a.pdf", PDF)], zipfile.ZIP_STORED)
        self.reject(b"")
        self.reject(b"not a zip", zipfile.BadZipFile)
        self.reject(data[:-10], zipfile.BadZipFile)
        corrupt = bytearray(data)
        corrupt[corrupt.index(PDF) + 8] ^= 1
        self.reject(corrupt, zipfile.BadZipFile)
        encrypted = bytearray(data)
        central = encrypted.index(b"PK\x01\x02")
        encrypted[6] |= 1
        encrypted[central + 8] |= 1
        self.reject(encrypted)
        self.reject(make_zip([("a.pdf", PDF)], zipfile.ZIP_BZIP2))

    def test_hash_and_publication_use_member_not_zip_envelope(self):
        database = db.Database(path=self.root / "isolated.db")
        self.addCleanup(database.close)
        database.set_setting("download_dir", str(self.root / "published"))
        task_id = database.create_task("synthetic", "fake")
        run_id = database.create_run(task_id)
        observed = []
        with mock.patch.object(downloads, "CONSUMERS", [observed.append]):
            for name in ("first.pdf", "safe/second.pdf"):
                with self.prepare(make_zip([(name, PDF)])) as document:
                    record = downloads.track_download(
                        document, run_id, {"id": task_id}, database)
                self.assertEqual(record["sha256"], hashlib.sha256(PDF).hexdigest())
                self.assertEqual(Path(record["saved_path"]).read_bytes(), PDF)
        self.assertEqual(len(database.list_downloads()), 2)
        self.assertTrue(record["duplicate"])
        self.assertEqual(len(observed), 1)

    def test_schema_accepts_only_explicit_pdf_option(self):
        options = {"key_attribute": "data-key", "max_items": 1,
                   "timeout_ms": 1000, "event_window_ms": 10}
        recipe = {"services": [{"serviceName": "synthetic", "steps": [{"step": 1,
                  "methods": [{"method": "locator", "arguments": [{"selector": "a"}]},
                              {"method": "download_all", "arguments": [options]}]}]}]}
        import yaml
        for value, accepted in (("pdf", True), (None, False), (False, False),
                                (True, False), ("zip", False), ({}, False)):
            options["unpack"] = value
            with self.subTest(value=value):
                self.assertEqual(recipes.validate_recipe(yaml.safe_dump(recipe))[0], accepted)
                if not accepted:
                    with self.assertRaises(collection.CollectionError):
                        collection.download_all(None, None, None, None, options)

    def test_collection_rejection_preserves_completed_items_and_retry(self):
        valid = self.root / "valid.zip"
        valid.write_bytes(make_zip([("a.pdf", PDF)]))
        self.source.write_bytes(make_zip([("bad.pdf", b"html")]))
        page, context = _Page(), _Events()
        listing = _Listing(page, context, [
            {"data-key": "one", "download": Download(valid)},
            {"data-key": "two", "download": Download(self.source)},
        ])
        options = {"key_attribute": "data-key", "max_items": 2,
                   "timeout_ms": 2000, "event_window_ms": 10, "unpack": "pdf"}
        completed, saved = set(), []

        def save(document):
            saved.append(document.source.read_bytes())
            return document.suggested_filename

        with self.assertRaises(ValueError):
            collection.download_all(page, context, listing, save, options,
                                    completed_keys=completed)
        self.assertEqual(completed, {"one"})
        self.assertEqual(saved, [PDF])
        self.source.write_bytes(make_zip([("b.pdf", PDF)]))
        records = collection.download_all(page, context, listing, save, options,
                                          completed_keys=completed)
        self.assertEqual(records, ["b.pdf"])
        self.assertEqual(completed, {"one", "two"})
        self.assertEqual(listing.clicked, ["one", "two", "two"])

    def test_default_passes_zip_through_untouched(self):
        data = make_zip([("a.pdf", PDF), ("b.txt", b"text")])
        self.source.write_bytes(data)
        original = Download(self.source)
        page, context = _Page(), _Events()
        listing = _Listing(page, context, [{"data-key": "one", "download": original}])
        received = []
        collection.download_all(page, context, listing, received.append, {
            "key_attribute": "data-key", "max_items": 1,
            "timeout_ms": 1000, "event_window_ms": 10})
        self.assertIs(received[0], original)
        target = self.root / "original.zip"
        received[0].save_as(target)
        self.assertEqual(target.read_bytes(), data)


@unittest.skipUnless(os.environ.get("BILLCOLLECTOR_BROWSER_TESTS") == "1",
                     "set BILLCOLLECTOR_BROWSER_TESTS=1 for loopback Chromium")
class BrowserArchiveTests(unittest.TestCase):
    def test_real_download_through_daemon_persistence_adapter(self):
        valid = make_zip([("safe/invoice.pdf", PDF)])
        invalid = make_zip([("../escape.pdf", PDF)])

        class Portal(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/":
                    body = b'<a data-key="one" href="/valid">valid</a>'
                    body += b'<a data-key="two" href="/invalid">invalid</a>'
                    content_type = "text/html"
                else:
                    body = valid if self.path == "/valid" else invalid
                    content_type = "application/zip"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                if content_type == "application/zip":
                    self.send_header("Content-Disposition", 'attachment; filename="envelope.zip"')
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Portal)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        from playwright.sync_api import sync_playwright

        if _REQUESTED_BROWSER_PATH:
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _REQUESTED_BROWSER_PATH
        with tempfile.TemporaryDirectory() as directory, sync_playwright() as playwright:
            root = Path(directory)
            database = db.Database(path=root / "test.db")
            self.addCleanup(database.close)
            database.set_setting("download_dir", str(root / "published"))
            task_id = database.create_task("synthetic", "fake")
            with playwright.chromium.launch(headless=True) as browser:
                context = browser.new_context(accept_downloads=True)
                page = context.new_page()
                page.goto(f"http://127.0.0.1:{server.server_port}/")
                ctx = SimpleNamespace(page=page, context=context, db=database,
                                      task={"id": task_id}, run_id=database.create_run(task_id),
                                      files_downloaded=[])
                action = runner._collection_actions(ctx, {})["download_all"]
                options = {"key_attribute": "data-key", "max_items": 1,
                           "timeout_ms": 5000, "event_window_ms": 200, "unpack": "pdf"}
                records = action(page.locator('[data-key="one"]'), options)
                self.assertEqual(records[0]["filename"], "invoice.pdf")
                self.assertEqual(Path(records[0]["saved_path"]).read_bytes(), PDF)
                with self.assertRaises(ValueError):
                    action(page.locator('[data-key="two"]'), options)
                self.assertEqual(len(database.list_downloads()), 1)
                self.assertEqual(len(ctx.files_downloaded), 1)
