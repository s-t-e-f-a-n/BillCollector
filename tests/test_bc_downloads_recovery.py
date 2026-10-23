"""Crash-window proof with real subprocess death, files and SQLite commits."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from billcollector import downloads
from billcollector.db import Database


class Document:
    suggested_filename = "invoice.pdf"
    url = "https://fixture.invalid/invoice?token=synthetic-secret"

    def save_as(self, path):
        Path(path).write_bytes(b"%PDF-1.4 synthetic invoice")


@pytest.mark.parametrize("boundary", [
    "before_commit", "after_commit", "before_rename", "after_rename",
    "after_consumer", "after_consumed",
])
def test_process_death_recovers_one_publication_and_stable_delivery(tmp_path, boundary):
    database = tmp_path / "proof.db"
    output = tmp_path / "output"
    events = tmp_path / "events"
    db = Database(database)
    db.set_setting("download_dir", str(output))
    task_id = db.create_task("synthetic", "crash")
    run_id = db.create_run(task_id)
    db.close()

    def consume(record):
        with events.open("a") as stream:
            stream.write(json.dumps(record) + "\n")
        if boundary == "after_consumer":
            os._exit(73)

    pid = os.fork()
    if pid == 0:
        db = Database(database)
        insert = db.insert_download
        rename = os.rename
        state = db.set_download_state

        def insert_at_boundary(*args, **kwargs):
            if boundary == "before_commit":
                os._exit(73)
            result = insert(*args, **kwargs)
            if boundary == "after_commit":
                os._exit(73)
            return result

        def rename_at_boundary(source, destination):
            if Path(destination).parent == output:
                if boundary == "before_rename":
                    os._exit(73)
                rename(source, destination)
                if boundary == "after_rename":
                    os._exit(73)
            else:
                rename(source, destination)

        def state_at_boundary(download_id, value):
            state(download_id, value)
            if boundary == "after_consumed" and value == "consumed":
                os._exit(73)

        try:
            with patch.object(db, "insert_download", insert_at_boundary), \
                    patch.object(db, "set_download_state", state_at_boundary), \
                    patch.object(downloads.os, "rename", rename_at_boundary), \
                    patch.object(downloads, "CONSUMERS", [consume]):
                downloads.track_download(Document(), run_id, {"id": task_id}, db)
        except BaseException:
            os._exit(74)
        os._exit(75)
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 73

    received = []

    def recovered_consumer(record):
        reader = Database(database)
        try:
            assert reader.find_download_by_sha(task_id, record["sha256"]) is not None
        finally:
            reader.close()
        received.append(record)

    db = Database(database)
    with patch.object(downloads, "CONSUMERS", [recovered_consumer]):
        downloads.recover_downloads(db)
        downloads.track_download(Document(), run_id, {"id": task_id}, db)
        downloads.recover_downloads(db)
    published = [p for p in output.iterdir() if p.is_file()]
    assert len(published) == 1
    assert published[0].read_bytes() == b"%PDF-1.4 synthetic invoice"
    rows = db.list_downloads(task_id=task_id)
    assert len([r for r in rows if r["duplicate_of_id"] is None]) == 1
    assert all(r["state"] == "consumed" for r in rows)
    previous = [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []
    deliveries = previous + received
    assert len(deliveries) == (2 if boundary == "after_consumer" else 1)
    assert len({r["idempotency_key"] for r in deliveries}) == 1
    db.close()


@pytest.fixture
def tracking(tmp_path):
    db = Database(tmp_path / "proof.db")
    db.set_setting("download_dir", str(tmp_path / "output"))
    task = {"id": db.create_task("synthetic", "user")}
    run = db.create_run(task["id"])
    yield db, task, run
    db.close()


def test_same_filename_across_tasks_keeps_separate_consumer_deliveries(tracking):
    db, task, run = tracking
    calls = []
    with patch.object(downloads, "CONSUMERS", [calls.append]):
        first = downloads.track_download(Document(), run, task, db)
        other = {"id": db.create_task("synthetic", "other")}
        second = downloads.track_download(Document(), db.create_run(other["id"]), other, db)
    assert len(calls) == 2
    assert first["saved_path"] != second["saved_path"]
    assert calls[0]["idempotency_key"] != calls[1]["idempotency_key"]


def test_pending_delivery_recovers_at_runner_start_before_any_portal(tracking):
    from billcollector import runner
    db, task, run = tracking
    calls = []

    def unavailable(record):
        raise OSError("synthetic-secret")

    with patch.object(downloads, "CONSUMERS", [unavailable]):
        downloads.track_download(Document(), run, task, db)
    # An invalid recipe prevents display/vault/browser setup. Recovery does not
    # require a working portal or a successful subsequent recipe.
    with patch.object(runner, "Database", lambda: Database(db.path)), \
            patch.object(runner, "CheckRecipe", return_value=None), \
            patch.object(runner, "_vault_preflight") as vault, \
            patch.object(downloads, "CONSUMERS", [calls.append]):
        assert runner.run_task(task["id"]) == 1
    vault.assert_not_called()
    assert len(calls) == 1
    assert db.list_downloads()[0]["state"] == "consumed"


def test_published_file_without_row_is_recovered_without_redelivery(tracking):
    db, task, run = tracking

    def interrupt(record):
        from billcollector.interrupt import RunInterrupted
        raise RunInterrupted("synthetic shutdown")

    from billcollector.interrupt import RunInterrupted
    with patch.object(downloads, "CONSUMERS", [interrupt]), pytest.raises(RunInterrupted):
        downloads.track_download(Document(), run, task, db)
    # Simulate the legacy publication/row gap while preserving the managed
    # journal that ties this file to its task and exact checksum.
    db.conn.execute("DELETE FROM Download")
    db.conn.commit()
    calls = []
    with patch.object(downloads, "CONSUMERS", [calls.append]):
        downloads.recover_downloads(db)
        downloads.recover_downloads(db)
    assert calls == []
    row, = db.list_downloads()
    assert row["state"] == "consumed"
    assert Path(row["saved_path"]).read_bytes() == b"%PDF-1.4 synthetic invoice"


def test_partial_save_is_quarantined_without_publication(tracking):
    db, task, run = tracking

    class Partial(Document):
        def save_as(self, path):
            Path(path).write_bytes(b"partial")
            raise OSError("synthetic save interrupted")

    with pytest.raises(OSError):
        downloads.track_download(Partial(), run, task, db)
    downloads.recover_downloads(db)
    output = Path(downloads.download_dir(db))
    assert not list(output.glob("*.pdf"))
    assert db.list_downloads() == []
    assert [p.read_bytes() for p in output.glob(".billcollector/*/quarantine/*/document")] == [b"partial"]


def test_existing_output_is_not_overwritten_by_new_content(tracking):
    db, task, run = tracking
    first = downloads.track_download(Document(), run, task, db)

    class Changed(Document):
        def save_as(self, path):
            Path(path).write_bytes(b"new invoice")

    second = downloads.track_download(Changed(), run, task, db)
    assert first["saved_path"] != second["saved_path"]
    assert Path(first["saved_path"]).read_bytes() == b"%PDF-1.4 synthetic invoice"
    assert Path(second["saved_path"]).read_bytes() == b"new invoice"


def test_unmanaged_matching_file_is_adopted_conservatively(tracking):
    db, task, run = tracking
    output = Path(downloads.download_dir(db))
    output.mkdir()
    (output / "invoice.pdf").write_bytes(b"%PDF-1.4 synthetic invoice")
    calls = []
    with patch.object(downloads, "CONSUMERS", [calls.append]):
        downloads.track_download(Document(), run, task, db)
    assert calls == []
    assert len(list(output.glob("*.pdf"))) == 1
    assert db.list_downloads()[0]["state"] == "consumed"


def test_migration_does_not_replay_historical_rows(tmp_path):
    import sqlite3
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE Download (
        id INTEGER PRIMARY KEY, run_id INTEGER, task_id INTEGER, url TEXT,
        filename TEXT, size INTEGER, sha256 TEXT, saved_path TEXT,
        created_at TEXT, duplicate_of_id INTEGER)""")
    conn.execute("INSERT INTO Download (id, task_id, sha256) VALUES (1, 7, 'legacy')")
    conn.commit()
    conn.close()
    for _ in range(2):
        db = Database(path)
        assert db.list_downloads()[0]["state"] == "consumed"
        assert db.pending_downloads() == []
        db.close()


@pytest.mark.parametrize("name", ["../escape.pdf", "/escape.pdf", ".billcollector", "..", ""])
def test_unsafe_filename_cannot_escape_staging(tracking, name):
    db, task, run = tracking
    doc = Document()
    doc.suggested_filename = name
    with pytest.raises(ValueError):
        downloads.track_download(doc, run, task, db)
    assert db.list_downloads() == []


def test_changed_pending_file_is_not_delivered_with_old_checksum(tracking):
    db, task, run = tracking

    def fail(record):
        raise OSError("synthetic unavailable")

    with patch.object(downloads, "CONSUMERS", [fail]):
        record = downloads.track_download(Document(), run, task, db)
    Path(record["saved_path"]).write_bytes(b"different document")
    calls = []
    with patch.object(downloads, "CONSUMERS", [calls.append]), pytest.raises(OSError, match="checksum"):
        downloads.recover_downloads(db)
    assert calls == []
    assert db.list_downloads()[0]["state"] == "published"


def test_completed_download_does_not_require_old_output_root(tracking, tmp_path):
    db, task, run = tracking
    downloads.track_download(Document(), run, task, db)
    output = Path(downloads.download_dir(db))
    output.rename(tmp_path / "unmounted-output")
    output.write_bytes(b"unavailable mount")
    db.set_setting("download_dir", str(tmp_path / "new-output"))
    downloads.recover_downloads(db)
    assert db.pending_downloads() == []


def test_daemon_startup_reconciles_even_without_a_scheduled_task(tracking):
    from billcollector.ui import app as ui_app
    db, task, run = tracking

    def fail(record):
        raise OSError("synthetic unavailable")

    with patch.object(downloads, "CONSUMERS", [fail]):
        downloads.track_download(Document(), run, task, db)
    assert db.list_downloads()[0]["state"] == "published"
    # Use real subprocess recovery on this isolated DB. There are no consumers
    # configured in the child; publication alone completes delivery there.
    with patch.object(ui_app, "Database", return_value=db), \
            patch.object(ui_app, "build_app"), \
            patch.object(ui_app, "build_lifecycle", return_value=(lambda: None, lambda: None)), \
            patch.object(ui_app.nicegui_app, "on_startup"), \
            patch.object(ui_app.nicegui_app, "on_shutdown"), \
            patch.object(ui_app.ui, "run"):
        ui_app.start("127.0.0.1", 8000)
    assert db.list_downloads()[0]["state"] == "consumed"
