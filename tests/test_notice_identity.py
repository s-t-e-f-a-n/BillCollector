"""Synthetic original PDFs exercise the public tracking boundary."""

from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

from billcollector import config, downloads
from billcollector.db import Database


POLICY = {"query_parameters": ["account", "notice"]}


def pdf(path, generation="one", content=b"0 0 10 10 re S"):
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    stream = DecodedStreamObject()
    stream.set_data(content)
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.add_metadata({"/CreationDate": generation, "/ModDate": generation})
    writer.write(path)
    return path


class Download:
    suggested_filename = "notice.pdf"

    def __init__(self, path, url="https://portal.invalid/pdf?account=A&notice=N"):
        self.path = path
        self.url = url

    def save_as(self, path):
        Path(path).write_bytes(self.path.read_bytes())


def test_regenerated_notice_does_not_publish_or_consume_again(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUN_DIR", tmp_path / "runs")
    seen = []
    with patch.object(downloads, "CONSUMERS", [seen.append]):
        for index, generation in enumerate(("one", "two")):
            db = Database(tmp_path / "db.sqlite")
            if index == 0:
                task_id = db.create_task("synthetic", "account")
                db.set_setting("download_dir", str(tmp_path / "out"))
            run_id = db.create_run(task_id)
            original = pdf(tmp_path / f"{index}.pdf", generation)
            record = downloads.track_download(
                Download(original), run_id, db.get_task(task_id), db,
                identity=POLICY,
            )
            assert record["duplicate"] is bool(index)
            db.close()
    assert len(seen) == 1
    assert [p for p in (tmp_path / "out").iterdir() if p.is_file()] == [tmp_path / "out" / "notice.pdf"]
    assert (tmp_path / "out" / "notice.pdf").read_bytes() == (tmp_path / "0.pdf").read_bytes()


def test_corrections_and_different_sources_keep_originals(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUN_DIR", tmp_path / "runs")
    db = Database(tmp_path / "db.sqlite")
    db.set_setting("download_dir", str(tmp_path / "out"))
    task_id = db.create_task("synthetic", "account")
    seen = []
    with patch.object(downloads, "CONSUMERS", [seen.append]):
        first = downloads.track_download(
            Download(pdf(tmp_path / "first.pdf")), db.create_run(task_id),
            db.get_task(task_id), db, identity=POLICY)
        corrected = downloads.track_download(
            Download(pdf(tmp_path / "corrected.pdf", content=b"0 0 20 10 re S")),
            db.create_run(task_id), db.get_task(task_id), db, identity=POLICY)
        other = downloads.track_download(
            Download(tmp_path / "first.pdf", "https://portal.invalid/pdf?account=A&notice=OTHER"),
            db.create_run(task_id), db.get_task(task_id), db, identity=POLICY)
    assert [r["duplicate"] for r in (first, corrected, other)] == [False, False, False]
    assert len({r["saved_path"] for r in (first, corrected, other)}) == 3
    assert len(seen) == 3
    for record, name in zip((first, corrected, other), ("first", "corrected", "first")):
        assert Path(record["saved_path"]).read_bytes() == (tmp_path / f"{name}.pdf").read_bytes()
    db.close()


def test_same_bytes_in_other_account_are_distinct(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUN_DIR", tmp_path / "runs")
    db = Database(tmp_path / "db.sqlite")
    db.set_setting("download_dir", str(tmp_path / "out"))
    source = Download(pdf(tmp_path / "notice.pdf"))
    records = []
    for user in ("PEA", "PEA-PME"):
        task = db.create_task("synthetic", user)
        records.append(downloads.track_download(
            source, db.create_run(task), db.get_task(task), db, identity=POLICY))
    assert [r["duplicate"] for r in records] == [False, False]
    assert records[0]["saved_path"] != records[1]["saved_path"]
    db.close()


def test_identity_fields_are_hashed_and_session_tokens_do_not_define_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUN_DIR", tmp_path / "runs")
    db = Database(tmp_path / "db.sqlite")
    db.set_setting("download_dir", str(tmp_path / "out"))
    task = db.create_task("synthetic", "account")
    records = []
    for token in ("one", "two"):
        source = Download(pdf(tmp_path / "notice.pdf", generation=token),
                          f"https://portal.invalid/pdf?account=private-account&notice=private-notice&token={token}")
        records.append(downloads.track_download(
            source, db.create_run(task), db.get_task(task), db, identity=POLICY))
    assert [r["duplicate"] for r in records] == [False, True]
    rows = [dict(row) for row in db.list_downloads(task_id=task)]
    assert len(rows[0]["source_identity"]) == 64
    assert "private-account" not in str(rows)
    assert "private-notice" not in str(rows)
    assert rows[1]["duplicate_of_id"] == rows[0]["id"]
    db.close()


def test_missing_or_ambiguous_source_and_bad_pdf_do_not_publish(tmp_path, monkeypatch, caplog):
    import pytest

    monkeypatch.setattr(config, "RUN_DIR", tmp_path / "runs")
    db = Database(tmp_path / "db.sqlite")
    db.set_setting("download_dir", str(tmp_path / "out"))
    task = db.create_task("synthetic", "account")
    valid = pdf(tmp_path / "notice.pdf")
    invalid = tmp_path / "bad.pdf"
    invalid.write_bytes(b"SECRET confidential document")
    for source in (
        Download(valid, "https://portal.invalid/pdf?account=A"),
        Download(valid, "https://portal.invalid/pdf?account=A&notice=N&notice=OTHER"),
        Download(valid, "blob:unverifiable"),
        Download(invalid),
    ):
        with pytest.raises(ValueError) as caught:
            downloads.track_download(source, db.create_run(task), db.get_task(task), db, identity=POLICY)
        assert "SECRET" not in str(caught.value)
    assert "SECRET" not in caplog.text
    assert not db.list_downloads(task_id=task)
    assert not list((tmp_path / "out").glob("*.pdf"))
    db.close()


def test_named_destination_alias_changes_but_target_corrections_survive(tmp_path):
    from billcollector.notice import revision_digest

    hashes = []
    for index, (alias, page_number) in enumerate((("gen_abc123", 0), ("gen_def456", 0), ("gen_ghi789", 1))):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.add_blank_page(width=100, height=100)
        writer.add_named_destination(alias, page_number)
        path = tmp_path / f"dest-{index}.pdf"
        writer.write(path)
        hashes.append(revision_digest(path))
    assert hashes[0] == hashes[1]
    assert hashes[1] != hashes[2]


def test_non_text_corrections_and_metadata_are_part_of_revision(tmp_path):
    from billcollector.notice import revision_digest

    hashes = []
    for index, (title, attachment) in enumerate((("Original", b"one"), ("Corrected", b"one"), ("Original", b"two"))):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.add_metadata({"/Title": title})
        writer.add_attachment("document.bin", attachment)
        path = tmp_path / f"attachment-{index}.pdf"
        writer.write(path)
        hashes.append(revision_digest(path))
    assert len(set(hashes)) == 3


def test_legacy_database_migration_is_additive_without_backfill(tmp_path):
    import sqlite3

    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE Download (id INTEGER PRIMARY KEY, run_id INTEGER, task_id INTEGER, url TEXT, filename TEXT, size INTEGER, sha256 TEXT, saved_path TEXT, created_at TEXT, duplicate_of_id INTEGER)")
        conn.execute("INSERT INTO Download (task_id, sha256, saved_path) VALUES (1, 'old-sha', 'old.pdf')")
    for _ in range(2):
        db = Database(path)
        row = db.find_download_by_sha(1, "old-sha")
        assert row["saved_path"] == "old.pdf"
        assert row["source_identity"] is None
        assert row["revision_sha256"] is None
        db.close()


def test_recipe_option_only_on_download_steps():
    import yaml
    from billcollector.recipes import validate_recipe

    for method, expected in (("expect_download", True), ("goto", False)):
        step = {"step": 1, "methods": [{"method": method}], "notice_identity": POLICY}
        recipe = {"services": [{"serviceName": "synthetic", "steps": [step]}]}
        assert validate_recipe(yaml.safe_dump(recipe))[0] is expected
    for invalid in ({}, {"query_parameters": []}, {"query_parameters": [" "]},
                    {"query_parameters": ["account", "account"]},
                    {"query_parameters": ["account"], "unknown": True}):
        step = {"step": 1, "methods": [{"method": "expect_download"}],
                "notice_identity": invalid}
        recipe = {"services": [{"serviceName": "synthetic", "steps": [step]}]}
        assert validate_recipe(yaml.safe_dump(recipe))[0] is False


def test_runner_download_adapter_applies_identity(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from billcollector import runner

    monkeypatch.setattr(config, "RUN_DIR", tmp_path / "runs")
    db = Database(tmp_path / "db.sqlite")
    db.set_setting("download_dir", str(tmp_path / "out"))
    task = db.create_task("synthetic", "account")

    class Page:
        @contextmanager
        def expect_download(self):
            yield SimpleNamespace(value=Download(pdf(tmp_path / "notice.pdf", self.generation)))

    ctx = SimpleNamespace(page=Page(), task=db.get_task(task), db=db, files_downloaded=[])
    step = {"step": 1, "notice_identity": POLICY}
    seen = []
    with patch.object(downloads, "CONSUMERS", [seen.append]):
        for generation in ("one", "two"):
            ctx.page.generation = generation
            ctx.run_id = db.create_run(task)
            runner._handle_download(ctx, step)
    assert len(seen) == 1
    assert len(ctx.files_downloaded) == 2
    assert all(row["result"] == "success" for row in ctx.files_downloaded)
    db.close()


def test_browser_collection_repeats_and_retains_correction_with_equal_names(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from playwright.sync_api import sync_playwright
    from billcollector import runner

    monkeypatch.setattr(config, "RUN_DIR", tmp_path / "runs")
    db = Database(tmp_path / "db.sqlite")
    db.set_setting("download_dir", str(tmp_path / "out"))
    task = db.create_task("synthetic", "account")
    seen = []
    with sync_playwright() as p, patch.object(downloads, "CONSUMERS", [seen.append]):
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        for index in range(3):
            first = pdf(tmp_path / "first.pdf", str(index),
                        b"0 0 20 10 re S" if index == 2 else b"0 0 10 10 re S").read_bytes()
            second = pdf(tmp_path / "second.pdf", str(index)).read_bytes()
            context.route("http://127.0.0.1/**", lambda route: route.fulfill(
                status=200, content_type="application/pdf",
                headers={"Content-Disposition": 'attachment; filename="notice.pdf"'},
                body=first if "notice=ONE" in route.request.url else second))
            page.set_content('''<a href="http://127.0.0.1/pdf?account=A&notice=ONE">One</a>
                <a href="http://127.0.0.1/pdf?account=A&notice=TWO">Two</a>''')
            ctx = SimpleNamespace(page=page, context=context, db=db, task=db.get_task(task),
                                  run_id=db.create_run(task), files_downloaded=[])
            runner._collection_actions(ctx, {"notice_identity": POLICY})["download_all"](
                page.locator("a"), {"key_attribute": "href", "max_items": 2,
                                    "timeout_ms": 5000, "event_window_ms": 20})
            context.unroute_all()
        browser.close()
    rows = db.list_downloads(task_id=task)
    assert [row["duplicate_of_id"] is not None for row in rows] == [False, False, True, True, False, True]
    assert len(seen) == 3
    assert len([p for p in (tmp_path / "out").iterdir() if p.is_file()]) == 3
    db.close()


def test_meaningful_named_destination_labels_are_not_generation_metadata(tmp_path):
    from billcollector.notice import revision_digest

    hashes = []
    for label in ("Original section", "Corrected section"):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.add_named_destination(label, 0)
        path = tmp_path / f"{len(hashes)}.pdf"
        writer.write(path)
        hashes.append(revision_digest(path))
    assert hashes[0] != hashes[1]


def test_long_linked_pdf_graphs_are_not_direct_nesting(tmp_path):
    from pypdf.annotations import Link
    from billcollector.notice import revision_digest

    for kind in ("outlines", "links"):
        paths = []
        for generation in ("one", "two"):
            writer = PdfWriter()
            for _ in range(20 if kind == "links" else 1):
                writer.add_blank_page(width=100, height=100)
            if kind == "outlines":
                for i in range(60):
                    writer.add_outline_item(f"Section {i}", 0)
            else:
                for i in range(19):
                    writer.add_annotation(i, Link(rect=(0, 0, 10, 10), target_page_index=i + 1))
            writer.add_metadata({"/CreationDate": generation})
            path = tmp_path / f"{kind}-{generation}.pdf"
            writer.write(path)
            paths.append(path)
        assert revision_digest(paths[0]) == revision_digest(paths[1])


def test_deep_direct_pdf_nesting_is_still_refused(tmp_path):
    import pytest
    from pypdf.generic import DictionaryObject, NumberObject
    from billcollector.notice import revision_digest

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    value = NumberObject(1)
    for _ in range(110):
        value = DictionaryObject({NameObject("/Nested"): value})
    writer.root_object[NameObject("/Synthetic")] = value
    path = tmp_path / "deep.pdf"
    writer.write(path)
    with pytest.raises(ValueError, match="cannot establish"):
        revision_digest(path)
