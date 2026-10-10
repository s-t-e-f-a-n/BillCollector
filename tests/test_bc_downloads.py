# -*- coding: utf-8 -*-
"""Unit tests for daemon download tracking + per-task sha256 dedup (no browser)."""

import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import db as bcd  # noqa: E402
from billcollector import downloads as bcdl  # noqa: E402


class _StubDownload:
    """Duck-typed stand-in for a Playwright Download (save_as copies bytes)."""

    def __init__(self, source_path, name, url):
        self.suggested_filename = name
        self.url = url
        self._source_path = Path(source_path)

    def save_as(self, target):
        shutil.copyfile(self._source_path, target)


class DownloadTrackingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = bcd.Database(path=Path(self.tmp.name) / "test.db")
        self.db.set_setting("download_dir", str(Path(self.tmp.name) / "dl"))
        self.tid = self.db.create_task("svc", "u1")
        self.rid = self.db.create_run(self.tid)
        self.task = {"id": self.tid}

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def _track(self, filename, data, url):
        """Write a source file with the given bytes and track it as a download."""
        src = Path(self.tmp.name) / "src" / filename
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_bytes(data)
        return bcdl.track_download(_StubDownload(src, filename, url),
                                   self.rid, self.task, self.db)

    def test_first_download_tracked(self):
        data = b"first file bytes"
        rec = self._track("a.pdf", data, "http://x/a.pdf")

        self.assertIs(rec["duplicate"], False)
        saved = Path(rec["saved_path"])
        self.assertTrue(saved.is_file(), "saved file must exist")
        self.assertEqual(saved.read_bytes(), data)
        self.assertEqual(rec["filename"], "a.pdf")
        self.assertEqual(rec["url"], "http://x/a.pdf")
        self.assertEqual(rec["size"], len(data))
        self.assertEqual(rec["sha256"], hashlib.sha256(data).hexdigest())

        row = self.db.find_download_by_sha(self.tid, rec["sha256"])
        self.assertIsNotNone(row)
        self.assertEqual(row["task_id"], self.tid)
        self.assertEqual(row["run_id"], self.rid)
        self.assertIsNone(row["duplicate_of_id"])
        self.assertEqual(row["saved_path"], str(saved))

    def test_identical_download_is_deduped(self):
        data = b"identical content"
        first = self._track("a.pdf", data, "http://x/a.pdf")
        second = self._track("a.pdf", data, "http://x/a-mirror.pdf")

        self.assertIs(first["duplicate"], False)
        self.assertIs(second["duplicate"], True)

        rows = self.db.list_downloads(task_id=self.tid)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["sha256"], rows[1]["sha256"])
        self.assertEqual(rows[0]["sha256"], hashlib.sha256(data).hexdigest())
        self.assertIsNone(rows[0]["duplicate_of_id"])
        self.assertEqual(rows[1]["duplicate_of_id"], rows[0]["id"])

    def test_different_content_is_not_deduped(self):
        first = self._track("a.pdf", b"content one", "http://x/a.pdf")
        second = self._track("b.pdf", b"content two", "http://x/b.pdf")

        self.assertIs(first["duplicate"], False)
        self.assertIs(second["duplicate"], False)

        rows = self.db.list_downloads(task_id=self.tid)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertIsNone(row["duplicate_of_id"])
        self.assertNotEqual(rows[0]["sha256"], rows[1]["sha256"])


if __name__ == "__main__":
    unittest.main()
