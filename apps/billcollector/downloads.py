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

from . import config
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


def track_download(download, run_id, task, db):
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
