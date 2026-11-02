# -*- coding: utf-8 -*-
"""Unit tests for daemon download tracking + per-task sha256 dedup (no browser)."""

import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import db as bcd  # noqa: E402
from billcollector import downloads as bcdl  # noqa: E402
from billcollector import notify as bcn  # noqa: E402


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

    def test_consumer_receives_a_committed_row_and_stable_key(self):
        observed = []

        def consume(record):
            reader = bcd.Database(path=self.db.path)
            try:
                row = reader.find_download_by_sha(self.tid, record["sha256"])
                observed.append((row is not None, record.get("idempotency_key")))
            finally:
                reader.close()

        from unittest.mock import patch
        with patch.object(bcdl, "CONSUMERS", [consume]):
            record = self._track("a.pdf", b"durable document", "http://x/a.pdf")
        self.assertEqual(observed, [(True, f"{self.tid}:{record['sha256']}")])

    def test_failed_consumer_leaves_row_failed_until_recovery(self):
        from unittest.mock import patch
        attempts = []

        def consume(record):
            attempts.append(record["idempotency_key"])
            if len(attempts) == 1:
                raise OSError("synthetic consumer unavailable")

        with patch.object(bcdl, "CONSUMERS", [consume]):
            record = self._track("a.pdf", b"retry delivery", "http://x/a.pdf")
            self.db.close()
            self.db = bcd.Database(path=Path(self.tmp.name) / "test.db")
            bcdl.recover_downloads(self.db)
            bcdl.recover_downloads(self.db)
        # The first failure leaves the row failed; the startup recovery retry
        # re-delivers it on the same idempotency key and consumes it.
        self.assertEqual(attempts, [f"{self.tid}:{record['sha256']}"] * 2)
        row = self.db.list_downloads()[0]
        self.assertEqual(row["state"], "consumed")
        self.assertEqual(row["delivery_attempts"], 2)

    def test_failed_consumer_records_one_first_failure_notification(self):
        from unittest.mock import patch

        def consume(record):
            raise OSError("synthetic consumer unavailable")

        with patch.object(bcdl, "CONSUMERS", [consume]), \
             patch.object(bcdl.notify, "notify_delivery_failed") as notification:
            self._track("a.pdf", b"notify delivery", "http://x/a.pdf")
        self.assertEqual(notification.call_count, 1)
        row = self.db.list_downloads()[0]
        self.assertEqual(row["state"], "failed")
        self.assertEqual(row["delivery_attempts"], 1)

    def test_checksum_mismatch_fails_delivery_without_raising(self):
        from unittest.mock import patch
        self._track("a.pdf", b"original", "http://x/a.pdf")
        row = dict(self.db.find_download_by_sha(self.tid, hashlib.sha256(b"original").hexdigest()))
        # Force the published state, corrupt the published file, then deliver.
        self.db.set_download_state(row["id"], "published")
        Path(row["saved_path"]).write_bytes(b"corrupted bytes")
        with patch.object(bcdl, "CONSUMERS", [lambda record: None]), \
             patch.object(bcdl.notify, "notify_delivery_failed") as notification:
            bcdl._deliver(row, self.db)
        fresh = dict(self.db.find_download_by_sha(self.tid, row["sha256"]))
        self.assertEqual(fresh["state"], "failed")
        self.assertEqual(fresh["delivery_attempts"], 2)
        self.assertEqual(notification.call_count, 1)

    def test_successful_consumer_consumes_with_attempt_count(self):
        from unittest.mock import patch

        def consume(record):
            pass

        with patch.object(bcdl, "CONSUMERS", [consume]), \
             patch.object(bcdl.notify, "notify_delivery_failed") as notification:
            self._track("a.pdf", b"ok bytes", "http://x/a.pdf")
        row = self.db.list_downloads()[0]
        self.assertEqual(row["state"], "consumed")
        self.assertEqual(row["delivery_attempts"], 1)
        self.assertEqual(notification.call_count, 0)

    def test_duplicate_row_is_never_delivered(self):
        self._track("a.pdf", b"same bytes", "http://x/a.pdf")
        second = self._track("a.pdf", b"same bytes", "http://x/a-mirror.pdf")
        self.assertIs(second["duplicate"], True)
        dup = [r for r in self.db.list_downloads(task_id=self.tid)
               if r["duplicate_of_id"] is not None][0]
        self.assertEqual(dup["state"], "consumed")
        self.assertIsNone(dup["delivery_attempts"])

    def test_retry_delivery_consumes_a_failed_row(self):
        from unittest.mock import patch

        def consume(record):
            raise OSError("synthetic consumer unavailable")

        with patch.object(bcdl, "CONSUMERS", [consume]):
            record = self._track("a.pdf", b"manual retry", "http://x/a.pdf")
        row = self.db.find_download_by_sha(self.tid, record["sha256"])
        self.assertEqual(row["state"], "failed")
        with patch.object(bcdl, "CONSUMERS", [lambda r: None]):
            self.assertIs(bcdl.retry_delivery(self.db, row["id"]), True)
        fresh = self.db.get_download(row["id"])
        self.assertEqual(fresh["state"], "consumed")
        self.assertEqual(fresh["delivery_attempts"], 2)

    def test_retry_delivery_consumes_a_published_row(self):
        from unittest.mock import patch
        self._track("a.pdf", b"published retry", "http://x/a.pdf")
        row = dict(self.db.list_downloads()[0])
        # Simulate the crash window: published but not yet delivered.
        self.db.set_download_state(row["id"], "published")
        with patch.object(bcdl, "CONSUMERS", [lambda r: None]):
            self.assertIs(bcdl.retry_delivery(self.db, row["id"]), True)
        fresh = self.db.get_download(row["id"])
        self.assertEqual(fresh["state"], "consumed")

    def test_retry_delivery_publishes_a_staged_row_before_delivery(self):
        from unittest.mock import patch
        data = b"staged retry bytes"
        target = Path(self.tmp.name) / "dl"
        identity = hashlib.sha256(os.fsencode(Path(self.db.path).resolve())).hexdigest()[:16]
        entry = target / ".billcollector" / identity / "manual"
        entry.mkdir(parents=True)
        staged = entry / "document"
        staged.write_bytes(data)
        row_id = self.db.insert_download(
            self.rid, self.tid, "http://x/s.pdf", "s.pdf", len(data),
            hashlib.sha256(data).hexdigest(), str(target / "s.pdf"),
            state="staged", staged_path=str(staged))
        with patch.object(bcdl, "CONSUMERS", [lambda r: None]):
            self.assertIs(bcdl.retry_delivery(self.db, row_id), True)
        fresh = self.db.get_download(row_id)
        self.assertEqual(fresh["state"], "consumed")
        self.assertEqual((target / "s.pdf").read_bytes(), data)

    def test_retry_delivery_refuses_consumed_duplicate_and_missing_rows(self):
        from unittest.mock import patch

        def refuse(record):
            raise AssertionError("consumer must not run for refused rows")

        self._track("a.pdf", b"refuse bytes", "http://x/a.pdf")
        self._track("a.pdf", b"refuse bytes", "http://x/a-mirror.pdf")
        rows = self.db.list_downloads(task_id=self.tid)
        consumed = [r for r in rows if r["duplicate_of_id"] is None][0]
        dup = [r for r in rows if r["duplicate_of_id"] is not None][0]
        with patch.object(bcdl, "CONSUMERS", [refuse]):
            self.assertIs(bcdl.retry_delivery(self.db, consumed["id"]), False)
            self.assertIs(bcdl.retry_delivery(self.db, dup["id"]), False)
            self.assertIs(bcdl.retry_delivery(self.db, 987654), False)

    def test_notify_delivery_failed_sends_message_with_dispatch(self):
        from unittest.mock import patch
        self.db.set_setting("ntfy_topic", "testtopic")
        row = {"task_id": self.tid, "filename": "a.pdf", "delivery_attempts": 0}
        sent = []

        def fake_dispatch(send, url, message):
            sent.append((url, message))
            return True

        with patch.object(bcn, "_ntfy_host", return_value="http://ntfy.test"):
            ok = bcn.notify_delivery_failed(self.db, row, dispatch=fake_dispatch)
        self.assertTrue(ok)
        self.assertEqual(len(sent), 1)
        url, message = sent[0]
        self.assertEqual(url, "http://ntfy.test/testtopic")
        self.assertEqual(message, "delivery failed: svc u1 a.pdf (attempt 1)")

    def test_first_download_tracked(self):
        data = b"first file bytes"
        rec = self._track(
            "a.pdf", data,
            "https://portal.invalid/invoices/a.pdf?token=synthetic-secret#download",
        )

        self.assertIs(rec["duplicate"], False)
        saved = Path(rec["saved_path"])
        self.assertTrue(saved.is_file(), "saved file must exist")
        self.assertEqual(saved.read_bytes(), data)
        self.assertEqual(rec["filename"], "a.pdf")
        self.assertEqual(rec["url"], "https://portal.invalid/invoices/a.pdf")
        self.assertEqual(rec["size"], len(data))
        self.assertEqual(rec["sha256"], hashlib.sha256(data).hexdigest())

        row = self.db.find_download_by_sha(self.tid, rec["sha256"])
        self.assertIsNotNone(row)
        self.assertEqual(row["task_id"], self.tid)
        self.assertEqual(row["run_id"], self.rid)
        self.assertEqual(row["url"], "https://portal.invalid/invoices/a.pdf")
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
