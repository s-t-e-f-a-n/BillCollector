# -*- coding: utf-8 -*-
"""Durable download publication and at-least-once consumer delivery.

The caller's task lock serializes recipe execution. An output-directory lock
also serializes publication/recovery across tasks and daemon startup. SQLite
rows are committed before publication and before any consumer effect.
"""

import fcntl
import hashlib
import json
import logging
import os
# Fixed child interpreter/module, argument list, and no shell.
import subprocess  # nosec B404
import sys
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from . import config
from .consumers import CONSUMERS
from .interrupt import RunInterrupted
from .redaction import sanitize_url

logger = logging.getLogger(__name__)
_CHUNK = 1024 * 1024
_FIELDS = ("run_id", "task_id", "url", "filename", "size", "sha256", "saved_path")


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


def _sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def _publication_lock(target):
    target.mkdir(parents=True, exist_ok=True)
    control = target / ".billcollector"
    control.mkdir(exist_ok=True)
    with (control / "publication.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _journal_root(target, db):
    # Separate independent databases sharing an output directory. Recovery must
    # never adopt another database's task IDs or orphan manifests.
    identity = hashlib.sha256(os.fsencode(Path(db.path).resolve())).hexdigest()[:16]
    return target / ".billcollector" / identity


def _deliver(row, db):
    if row["duplicate_of_id"] is not None:
        return
    record = {k: row[k] for k in _FIELDS}
    record["idempotency_key"] = f"{row['task_id']}:{row['sha256']}"
    failed = False
    for consume in CONSUMERS:
        saved = Path(row["saved_path"])
        if saved.exists() and (not saved.is_file() or sha256_of(saved) != row["sha256"]):
            raise OSError("Published download checksum mismatch")
        try:
            consume(record.copy())
        except RunInterrupted:
            raise
        except Exception:
            failed = True
            # Consumer exceptions can contain document URLs or credentials.
            logger.error("Download consumer failed; delivery remains pending")
    if not failed:
        db.set_download_state(row["id"], "consumed")


def _clean_journal(entry):
    for name in ("document", "manifest.json"):
        (entry / name).unlink(missing_ok=True)
    entry.rmdir()
    _sync_dir(entry.parent)


def _quarantine(entry):
    quarantine = entry.parent / "quarantine"
    quarantine.mkdir(exist_ok=True)
    os.rename(entry, quarantine / entry.name)
    _sync_dir(quarantine)
    _sync_dir(entry.parent)
    logger.warning("Uncommitted download quarantined; no document published")


def _publish(row, db):
    staged = Path(row["staged_path"])
    saved = Path(row["saved_path"])
    if staged.exists():
        if sha256_of(staged) != row["sha256"]:
            raise OSError("Staged download checksum mismatch")
        if saved.exists():
            raise OSError("Reserved download destination already exists")
        os.rename(staged, saved)
        _sync_dir(saved.parent)
        _sync_dir(staged.parent)
    elif saved.exists() and sha256_of(saved) != row["sha256"]:
        raise OSError("Published download checksum mismatch")
    # A downstream folder watcher may already have moved the published file.
    # The committed intent and disappearance of the staged file retain the
    # delivery obligation; consumers use the stable key on re-delivery.
    db.set_download_state(row["id"], "published")


def _recover_locked(db, target):
    root = _journal_root(target, db)
    rows = {r["staged_path"]: dict(r) for r in db.list_downloads()
            if r["staged_path"] and Path(r["saved_path"]).parent == target}
    if root.exists():
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or entry.name == "quarantine":
                continue
            staged = entry / "document"
            row = rows.get(str(staged))
            if row is None:
                try:
                    metadata = json.loads((entry / "manifest.json").read_text())
                    saved = Path(metadata["saved_path"])
                    valid = (saved.parent == target and saved.name == metadata["filename"]
                             and db.get_task(metadata["task_id"]) is not None)
                    if not valid:
                        raise ValueError("Invalid publication manifest")
                except (OSError, ValueError, KeyError, TypeError):
                    _quarantine(entry)
                    continue
                if saved.is_file() and sha256_of(saved) == metadata["sha256"]:
                    # Conservative recovery of publication without its row:
                    # do not replay an unknown external consumer effect.
                    db.insert_download(**{k: metadata[k] for k in _FIELDS},
                                       staged_path=str(staged), state="consumed")
                    _clean_journal(entry)
                else:
                    _quarantine(entry)
    for row in rows.values():
        entry = Path(row["staged_path"]).parent
        if row["state"] == "staged":
            _publish(row, db)
            row["state"] = "published"
        if row["state"] == "published":
            _deliver(row, db)
        if entry.exists():
            # Failed consumers retain the journal and pending row for retry.
            current = db.find_download_by_sha(row["task_id"], row["sha256"])
            if row["state"] == "consumed" or (current and current["state"] == "consumed"):
                _clean_journal(entry)


def recover_downloads(db):
    """Reconcile managed publications and retry pending deliveries at startup.

    Also visit old output roots retained in pending rows after a setting change.
    Unknown staging files are quarantined. Unmanaged files are never assigned
    to a task by guessing from their name.
    """
    targets = {Path(download_dir(db)).resolve()}
    targets.update(Path(r["saved_path"]).parent for r in db.list_downloads()
                   if r["staged_path"] and (r["state"] != "consumed"
                                             or Path(r["staged_path"]).parent.is_dir()))
    for target in sorted(targets):
        with _publication_lock(target):
            _recover_locked(db, target)


def track_download(download, run_id, task, db):
    """Stage one Playwright Download, commit intent, publish, then deliver.

    Existing same-task hashes retain an audit row without another publication.
    Consumer failures remain pending and do not fail the recipe. Filesystem or
    database errors propagate to the runner; recovery precedes any later save.
    """
    target = Path(download_dir(db)).resolve()
    with _publication_lock(target):
        _recover_locked(db, target)
        filename = str(download.suggested_filename)
        if filename in ("", ".", "..", ".billcollector") or Path(filename).name != filename:
            raise ValueError("Download filename must be a plain basename")
        root = _journal_root(target, db)
        root.mkdir(parents=True, exist_ok=True)
        entry = root / uuid4().hex
        entry.mkdir()
        _sync_dir(root)
        staged = entry / "document"
        download.save_as(str(staged))
        with staged.open("rb") as stream:
            os.fsync(stream.fileno())
        sha = sha256_of(staged)
        record = {
            "run_id": run_id, "task_id": task["id"],
            "url": sanitize_url(str(download.url)), "filename": filename,
            "size": staged.stat().st_size, "sha256": sha,
        }
        existing = db.find_download_by_sha(task["id"], sha)
        if existing is not None:
            record["saved_path"] = existing["saved_path"]
            db.insert_download(**record, duplicate_of_id=existing["id"])
            _clean_journal(entry)
            return {**record, "duplicate": True}
        saved = target / filename
        # Legacy publication without a row: adopt only an exact filename/hash
        # match observed on this task's new download. Do not invoke consumers.
        known = any(r["saved_path"] == str(saved) for r in db.list_downloads())
        orphan = not known and saved.is_file() and sha256_of(saved) == sha
        if saved.exists() and not orphan:
            saved = target / f"{Path(filename).stem}-{uuid4().hex}{Path(filename).suffix}"
        record["saved_path"] = str(saved)
        # A collision changes the actual filename, as exposed by the UI/hook.
        record["filename"] = saved.name
        with (entry / "manifest.json").open("x") as stream:
            json.dump(record, stream)
            stream.flush()
            os.fsync(stream.fileno())
        _sync_dir(entry)
        download_id = db.insert_download(**record, staged_path=str(staged),
                                         state="consumed" if orphan else "staged")
        if not orphan:
            row = {**record, "id": download_id, "staged_path": str(staged),
                   "duplicate_of_id": None}
            _publish(row, db)
            _deliver(row, db)
        current = db.find_download_by_sha(task["id"], sha)
        if current["state"] == "consumed":
            _clean_journal(entry)
        return {**record, "duplicate": False}


def recover_downloads_in_subprocess(db):
    """Finish recovery before the daemon starts its UI or scheduler.

    Keep consumers out of the UI process, as in normal runner execution.
    The child opens its own SQLite connection and uses the publication lock.
    """
    # Only the database path varies; it is a positional module argument.
    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "billcollector.downloads", str(Path(db.path).resolve())],
        cwd=config.APP_DIR, check=False, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
    if result.returncode:
        raise RuntimeError("Download startup recovery failed; daemon not started")


if __name__ == "__main__":
    from .db import Database

    database = Database(path=sys.argv[1])
    try:
        recover_downloads(database)
    except Exception:
        # Do not persist raw exception text or paths from recovery/consumers.
        sys.exit(1)
    finally:
        database.close()
