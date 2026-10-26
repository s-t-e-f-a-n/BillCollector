# -*- coding: utf-8 -*-
"""Download tracking, per-task sha256 dedup, and the post-download hook
(decision 14).

Runs inside the runner subprocess: every downloaded file is dropped into the
download folder (DMS-agnostic, unchanged) and tracked in the ``Download``
table. A file whose sha256 was already seen for this task is recorded as a
duplicate (``duplicate_of_id``) and the consumer hook is NOT re-run for it -
the hook slot is for document consumers that must see each document once.
"""

import hashlib
import logging
import os
import shutil
import tempfile
from pathlib import Path

from . import config, notice
from .consumers import CONSUMERS
from .interrupt import RunInterrupted
from .redaction import sanitize_url

logger = logging.getLogger(__name__)

_CHUNK = 1024 * 1024


def sha256_of(path):
    """Chunked sha256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def download_dir(db):
    """The download folder: the Settings override wins, else the default."""
    value = db.get_setting("download_dir")
    return value if value else str(config.DOWNLOAD_DIR)


def track_download(download, run_id, task, db, *, identity=None):
    if identity is not None:
        return _track_notice_download(download, run_id, task, db, identity=identity)
    return _track_legacy_download(download, run_id, task, db)


def _track_legacy_download(download, run_id, task, db):
    """Save one Playwright ``Download`` and record it in the DB.

    Returns the tracked record dict: run_id, task_id, url, filename, size,
    sha256, saved_path, duplicate (bool). Raises OSError on save failure -
    the runner treats that as a step failure (3x retry, then pause).
    """
    target_dir = download_dir(db)
    os.makedirs(target_dir, exist_ok=True)
    filename = str(download.suggested_filename)
    saved_path = os.path.join(target_dir, filename)
    download.save_as(saved_path)

    sha = sha256_of(saved_path)
    size = os.path.getsize(saved_path)
    task_id = task["id"]
    retained_url = sanitize_url(str(download.url))

    existing = db.find_download_by_sha(task_id, sha)
    duplicate = existing is not None
    if duplicate:
        logger.info(f"Download {filename} already tracked for this task "
                    f"(sha256 {sha[:12]}, duplicate of Download {existing['id']}).")
    else:
        for consume in CONSUMERS:
            try:
                consume({
                    "run_id": run_id,
                    "task_id": task_id,
                    "url": retained_url,
                    "filename": filename,
                    "size": size,
                    "sha256": sha,
                    "saved_path": saved_path,
                })
            except RunInterrupted:
                raise  # a shutdown signal must end the run, not be logged as a consumer failure
            except Exception:
                # A consumer must never break the run: log and continue.
                logger.exception(f"Consumer {getattr(consume, '__name__', consume)} failed")

    db.insert_download(run_id, task_id, retained_url, filename, size, sha,
                       saved_path,
                       duplicate_of_id=existing["id"] if duplicate else None)
    return {
        "run_id": run_id,
        "task_id": task_id,
        "url": retained_url,
        "filename": filename,
        "size": size,
        "sha256": sha,
        "saved_path": saved_path,
        "duplicate": duplicate,
    }


def _publish_unique(source, target_dir, filename):
    # Stage only new content on the destination filesystem. The final link is
    # atomic and fails on an existing file, including another task's output.
    stem, ext = os.path.splitext(filename)
    with tempfile.TemporaryDirectory(prefix=".bc-publish-", dir=target_dir) as tmp:
        staged = Path(tmp) / "document.part"
        shutil.copyfile(source, staged)
        index = 0
        while True:
            name = filename if index == 0 else f"{stem} ({index}){ext}"
            final = Path(target_dir) / name
            try:
                os.link(staged, final)
                return str(final)
            except FileExistsError:
                index += 1


def _track_notice_download(download, run_id, task, db, *, identity):
    """Save one Playwright ``Download`` and record it in the DB.

    Returns the tracked record dict: run_id, task_id, url, filename, size,
    sha256, saved_path, duplicate (bool). Raises OSError on save failure -
    the runner treats that as a step failure (3x retry, then pause).
    """
    source_identity = (notice.source_digest(str(download.url), identity)
                       if identity is not None else None)
    revision = None
    target_dir = download_dir(db)
    os.makedirs(target_dir, exist_ok=True)
    filename = str(download.suggested_filename).replace("\\", "/").rsplit("/", 1)[-1]
    if filename in ("", ".", ".."):
        filename = "download"
    task_id = task["id"]
    retained_url = sanitize_url(str(download.url))
    staging_root = config.RUN_DIR / str(run_id)
    staging_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="download-", dir=staging_root) as tmp:
        staged = Path(tmp) / "document.part"
        download.save_as(str(staged))
        sha = sha256_of(staged)
        size = staged.stat().st_size
        if identity is None:
            existing = db.find_download_by_sha(task_id, sha)
        else:
            revision = notice.revision_digest(staged)
            existing = db.find_notice_revision(task_id, source_identity, revision)
        duplicate = existing is not None
        saved_path = (existing["saved_path"] if duplicate else
                      _publish_unique(staged, target_dir, filename))
    if duplicate:
        logger.info(f"Download {filename} already tracked for this task "
                    f"(duplicate of Download {existing['id']}).")
    else:
        for consume in CONSUMERS:
            try:
                consume({
                    "run_id": run_id,
                    "task_id": task_id,
                    "url": retained_url,
                    "filename": filename,
                    "size": size,
                    "sha256": sha,
                    "saved_path": saved_path,
                })
            except RunInterrupted:
                raise  # a shutdown signal must end the run, not be logged as a consumer failure
            except Exception:
                # A consumer must never break the run: log and continue.
                logger.exception(f"Consumer {getattr(consume, '__name__', consume)} failed")

    db.insert_download(run_id, task_id, retained_url, filename, size, sha,
                       saved_path,
                       duplicate_of_id=existing["id"] if duplicate else None,
                       source_identity=source_identity, revision_sha256=revision)
    return {
        "run_id": run_id,
        "task_id": task_id,
        "url": retained_url,
        "filename": filename,
        "size": size,
        "sha256": sha,
        "saved_path": saved_path,
        "duplicate": duplicate,
    }
