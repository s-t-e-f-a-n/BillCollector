"""SQLite data layer for the daemon.

WAL mode with a busy_timeout; writers are split by table (orchestrator owns
Task/Run lifecycle, the runner owns PageStatus/Download, the UI owns Task CRUD
and Settings) and all writes are short. The legacy batch tables (``Service``,
``PageStatus_<service>_RunN``) are left untouched in the same file: they are
runtime status, not an archive (decision 7).
"""

import configparser
import json
import os
import shutil
import sqlite3
from datetime import datetime

from . import config


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


SCHEMA = """
CREATE TABLE IF NOT EXISTS Task (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,
    user TEXT NOT NULL,
    recipe_file TEXT,
    enabled INTEGER NOT NULL DEFAULT 0,
    cron TEXT,
    last_run TEXT,
    next_run TEXT,
    status TEXT NOT NULL DEFAULT 'idle',
    profile_dir TEXT,
    profile_reset_at TEXT,
    login_failures INTEGER NOT NULL DEFAULT 0,
    login_failure_limit INTEGER NOT NULL DEFAULT 2,
    login_locked INTEGER NOT NULL DEFAULT 0,
    login_cycle_active INTEGER NOT NULL DEFAULT 0,
    login_pending_run_id INTEGER,
    created_at TEXT,
    updated_at TEXT,
    UNIQUE (service, user)
);
CREATE TABLE IF NOT EXISTS Run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    pid INTEGER,
    display INTEGER,
    novnc_port INTEGER,
    log_path TEXT,
    control_sock TEXT,
    started_at TEXT,
    ended_at TEXT,
    result TEXT,
    pause_reason TEXT,
    pause_prompt TEXT,
    pause_context TEXT,
    pause_deadline_at TEXT,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS PageStatus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    step_number INTEGER,
    locator_action TEXT,
    interactive_elements TEXT,
    screenshot_path TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS Download (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    task_id INTEGER,
    url TEXT,
    filename TEXT,
    size INTEGER,
    sha256 TEXT,
    saved_path TEXT,
    created_at TEXT,
    duplicate_of_id INTEGER,
    state TEXT NOT NULL DEFAULT 'consumed',
    staged_path TEXT
);
CREATE TABLE IF NOT EXISTS Settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


class Database:
    def __init__(self, path=None):
        self.path = str(path or config.DB_FILE)
        config.ensure_dirs()
        # check_same_thread=False: the daemon touches the DB from the event-loop
        # thread (scheduler/orchestrator) and the runner's main thread; safety
        # comes from WAL + busy_timeout and short writes only.
        self.conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self):
        """Additive column migrations for pre-existing DBs (D3.4).

        The schema above is ``CREATE TABLE IF NOT EXISTS`` only, so a DB file
        created before a column was added keeps the old layout; each new
        column gets a one-time ``ALTER TABLE`` guarded by a
        ``PRAGMA table_info`` check (idempotent, no migration framework)."""
        cols = {r["name"] for r in
                self.conn.execute("PRAGMA table_info(Task)").fetchall()}
        if "profile_reset_at" not in cols:
            self.conn.execute(
                "ALTER TABLE Task ADD COLUMN profile_reset_at TEXT")
        for name, definition in {
            "login_failures": "INTEGER NOT NULL DEFAULT 0",
            "login_failure_limit": "INTEGER NOT NULL DEFAULT 2",
            "login_locked": "INTEGER NOT NULL DEFAULT 0",
            "login_cycle_active": "INTEGER NOT NULL DEFAULT 0",
            "login_pending_run_id": "INTEGER",
        }.items():
            if name not in cols:
                self.conn.execute(f"ALTER TABLE Task ADD COLUMN {name} {definition}")

        if "login_cycle_active" not in cols:
            # Old candidates cannot distinguish a cleared limit-one task from
            # success. Preserve its cap conservatively until fresh session proof.
            self.conn.execute(
                """UPDATE Task SET login_cycle_active=1
                   WHERE login_failures>0 OR login_locked=1
                     OR login_pending_run_id IS NOT NULL OR login_failure_limit=1""")

        download_cols = {r["name"] for r in
                         self.conn.execute("PRAGMA table_info(Download)")}
        for name, definition in {
            "state": "TEXT NOT NULL DEFAULT 'consumed'",
            "staged_path": "TEXT",
        }.items():
            if name not in download_cols:
                self.conn.execute(f"ALTER TABLE Download ADD COLUMN {name} {definition}")

    # ---- Task -------------------------------------------------------------
    def create_task(self, service, user, recipe_file=None, enabled=False,
                    cron=None, profile_dir=None):
        cur = self.conn.execute(
            """INSERT INTO Task (service, user, recipe_file, enabled, cron, status,
                                 profile_dir, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'idle', ?, ?, ?)""",
            (service, user, recipe_file, int(bool(enabled)), cron,
             profile_dir, now(), now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_task(self, task_id):
        return self.conn.execute("SELECT * FROM Task WHERE id=?", (task_id,)).fetchone()

    def get_task_by_service_user(self, service, user):
        return self.conn.execute(
            "SELECT * FROM Task WHERE service=? AND user=?", (service, user)).fetchone()

    def list_tasks(self):
        return self.conn.execute("SELECT * FROM Task ORDER BY id").fetchall()

    def update_task(self, task_id, **fields):
        if not fields:
            return
        fields["updated_at"] = now()
        cols = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [task_id]
        self.conn.execute(f"UPDATE Task SET {cols} WHERE id=?", vals)
        self.conn.commit()

    def set_task_status(self, task_id, status):
        self.conn.execute(
            "UPDATE Task SET status=?, updated_at=? WHERE id=?",
            (status, now(), task_id))
        self.conn.commit()

    def reset_profile(self, task_id):
        """Delete the task's browser profile so the next run cold-starts (D3.4).

        Rejected unless the task is ``idle`` (locked decision 8: a reset
        under a live runner would race its profile lock). Removes the
        profile dir if present and records ``profile_reset_at`` either way.
        Returns ``(ok, error)``."""
        task = self.get_task(task_id)
        if task is None:
            return False, f"task {task_id} does not exist"
        if task["status"] != "idle":
            return False, (f"task {task_id} is {task['status']}; "
                           "reset the profile only while idle")
        profile = task["profile_dir"]
        if profile and os.path.isdir(profile):
            try:
                shutil.rmtree(profile)
            except OSError as e:
                return False, f"could not remove {profile}: {e}"
        self.update_task(task_id, profile_reset_at=now())
        return True, None

    def claim_task_run(self, task_id):
        """Atomically mark a task ``running`` unless it is already running/waiting.

        Returns True when this caller won the claim (the DB row lock of the
        orchestration flow)."""
        cur = self.conn.execute(
            """UPDATE Task SET status='running', updated_at=?
               WHERE id=? AND status NOT IN ('running','waiting')
                 AND login_locked=0 AND login_pending_run_id IS NULL""",
            (now(), task_id))
        self.conn.commit()
        return cur.rowcount == 1

    def release_task_run(self, task_id):
        """Do not let a rejected contender release another runner's task."""
        self.conn.execute(
            """UPDATE Task SET status='idle', updated_at=? WHERE id=?
               AND NOT EXISTS (SELECT 1 FROM Run WHERE task_id=? AND result IS NULL)""",
            (now(), task_id, task_id))
        self.conn.commit()

    def reserve_login_attempt(self, task_id, run_id, limit):
        """Commit the attempt before dispatch. An uncertain submit consumes it."""
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("login failure limit must be a positive integer")
        cur = self.conn.execute(
            """UPDATE Task SET login_failures=login_failures+1, login_cycle_active=1,
                   login_failure_limit=CASE WHEN login_failures>0 OR login_cycle_active=1
                     THEN MIN(login_failure_limit,?) ELSE ? END,
                   login_pending_run_id=?, updated_at=?
               WHERE id=? AND login_locked=0 AND login_pending_run_id IS NULL
                   AND login_failures < CASE WHEN login_failures>0 OR login_cycle_active=1
                     THEN MIN(login_failure_limit,?) ELSE ? END""",
            (limit, limit, run_id, now(), task_id, limit, limit))
        reserved = cur.rowcount == 1
        if not reserved:
            self.conn.execute(
                """UPDATE Task SET login_locked=1, login_cycle_active=1,
                       login_failure_limit=MIN(login_failure_limit,?), updated_at=?
                   WHERE id=? AND login_pending_run_id IS NULL
                     AND login_failures>=MIN(login_failure_limit,?)""",
                (limit, now(), task_id, limit))
        self.conn.commit()
        return reserved

    def settle_login_attempt(self, task_id, run_id):
        """Consume an unproven submission once, including crash recovery."""
        cur = self.conn.execute(
            """UPDATE Task SET login_pending_run_id=NULL,
                   login_locked=CASE WHEN login_failures>=login_failure_limit
                                     THEN 1 ELSE login_locked END,
                   updated_at=? WHERE id=? AND login_pending_run_id=?""",
            (now(), task_id, run_id))
        self.conn.commit()
        return cur.rowcount == 1

    def login_succeeded(self, task_id, run_id):
        """Only an explicit session proof resets the consecutive budget."""
        cur = self.conn.execute(
            """UPDATE Task SET login_failures=0, login_locked=0, login_cycle_active=0,
                   login_pending_run_id=NULL, updated_at=? WHERE id=?
                   AND login_locked=0
                   AND (login_pending_run_id IS NULL OR login_pending_run_id=?)
                   AND EXISTS (SELECT 1 FROM Run WHERE id=? AND task_id=?
                               AND result IS NULL)""",
            (now(), task_id, run_id, run_id, task_id))
        self.conn.commit()
        return cur.rowcount == 1

    def clear_login_lock(self, task_id):
        """Grant one further attempt. Preserve profile and scheduling intent."""
        cur = self.conn.execute(
            """UPDATE Task SET login_locked=0, login_cycle_active=1,
                   login_failures=MAX(0, login_failure_limit-1), updated_at=?
               WHERE id=? AND status='idle' AND login_locked=1
                   AND login_pending_run_id IS NULL""", (now(), task_id))
        self.conn.commit()
        return cur.rowcount == 1

    def import_ini(self, ini_paths=None, default_cron="0 0 1 * *",
                   force=False):
        """One-time import of the ``[Playwright]`` sections into Tasks.

        Imported tasks are created disabled (decision 7: "disabled until
        confirmed in the UI") with a default monthly cron. Without
        ``force`` this runs only when the Task table is still empty (the
        first-start import); with ``force=True`` (the onboarding wizard's
        re-import, M4 C2) the empty-table guard is skipped while the
        existing (service, user) duplicate guard still applies, so only
        pairs missing from the table are added - including ones the user
        deleted. Duplicate (service, user) pairs across files are imported
        only once. Returns the number of tasks created.
        """
        if not force and self.conn.execute(
                "SELECT COUNT(*) c FROM Task").fetchone()["c"]:
            return 0
        created = 0
        for ini in (ini_paths if ini_paths is not None else config.INI_FILES):
            ini = str(ini)
            if not os.path.exists(ini):
                continue
            parser = configparser.ConfigParser()
            parser.read(ini, encoding="utf-8")
            if not parser.has_section("Playwright"):
                continue
            for service, users_raw in parser["Playwright"].items():
                users = ([u.strip() for u in users_raw.split(",") if u.strip()]
                         if users_raw.strip() else [""])
                for user in users:
                    if self.get_task_by_service_user(service, user) is not None:
                        continue
                    self.create_task(
                        service, user,
                        recipe_file=str(config.recipe_path_for(service)),
                        enabled=False, cron=default_cron,
                        profile_dir=str(config.profile_dir_for(service, user)))
                    created += 1
        self.conn.execute(
            "INSERT OR REPLACE INTO Settings (key, value) VALUES ('ini_imported', '1')")
        self.conn.commit()
        return created

    # ---- Run --------------------------------------------------------------
    def create_run(self, task_id, pid=None, display=None, novnc_port=None,
                   log_path=None, control_sock=None):
        cur = self.conn.execute(
            """INSERT INTO Run (task_id, pid, display, novnc_port, log_path,
                                control_sock, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (task_id, pid, display, novnc_port, log_path, control_sock, now()))
        self.conn.commit()
        return cur.lastrowid

    def get_run(self, run_id):
        return self.conn.execute("SELECT * FROM Run WHERE id=?", (run_id,)).fetchone()

    def get_run_for_pid(self, task_id, pid):
        """Latest Run row of a task created by the given pid.

        The orchestrator matches the runner subprocess it spawned (whose pid
        it knows) to the Run row the runner itself created."""
        return self.conn.execute(
            "SELECT * FROM Run WHERE task_id=? AND pid=? ORDER BY id DESC LIMIT 1",
            (task_id, pid)).fetchone()

    def update_run(self, run_id, **fields):
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [run_id]
        self.conn.execute(f"UPDATE Run SET {cols} WHERE id=?", vals)
        self.conn.commit()

    def list_runs(self, task_id=None):
        if task_id is None:
            return self.conn.execute(
                "SELECT * FROM Run ORDER BY id DESC").fetchall()
        return self.conn.execute(
            "SELECT * FROM Run WHERE task_id=? ORDER BY id DESC", (task_id,)).fetchall()

    def list_active_runs(self):
        """Runs that have not been finalized yet (result IS NULL), i.e. the
        runner subprocess is expected to still own them."""
        return self.conn.execute(
            "SELECT * FROM Run WHERE result IS NULL ORDER BY id").fetchall()

    def list_waiting_runs(self):
        """Active runs currently paused, awaiting operator interaction."""
        return self.conn.execute(
            "SELECT * FROM Run WHERE result IS NULL AND pause_reason IS NOT NULL"
            " ORDER BY id").fetchall()

    # ---- PageStatus -------------------------------------------------------
    def insert_page_status(self, run_id, step_number, locator_action=None,
                           interactive_elements=None, screenshot_path=None, error=None):
        self.conn.execute(
            """INSERT INTO PageStatus (run_id, step_number, locator_action,
                                       interactive_elements, screenshot_path, error)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (run_id, step_number,
             json.dumps(locator_action) if isinstance(locator_action, (dict, list)) else locator_action,
             json.dumps(interactive_elements) if isinstance(interactive_elements, (dict, list)) else interactive_elements,
             screenshot_path,
             json.dumps(error) if isinstance(error, (dict, list)) else error))
        self.conn.commit()

    def list_page_status(self, run_id):
        return self.conn.execute(
            "SELECT * FROM PageStatus WHERE run_id=? ORDER BY step_number, id",
            (run_id,)).fetchall()

    # ---- Download ---------------------------------------------------------
    def insert_download(self, run_id, task_id, url, filename, size, sha256,
                        saved_path, duplicate_of_id=None, *,
                        state="consumed", staged_path=None):
        cur = self.conn.execute(
            """INSERT INTO Download (run_id, task_id, url, filename, size, sha256,
                                     saved_path, created_at, duplicate_of_id, state, staged_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, task_id, url, filename, size, sha256, saved_path, now(), duplicate_of_id, state, staged_path))
        self.conn.commit()
        return cur.lastrowid

    def set_download_state(self, download_id, state):
        self.conn.execute("UPDATE Download SET state=? WHERE id=?",
                          (state, download_id))
        self.conn.commit()

    def pending_downloads(self):
        return self.conn.execute(
            "SELECT * FROM Download WHERE state!='consumed' ORDER BY id").fetchall()

    def find_download_by_sha(self, task_id, sha256):
        """First Download row for this task with the given sha256 (dedup key)."""
        return self.conn.execute(
            "SELECT * FROM Download WHERE task_id=? AND sha256=? ORDER BY id",
            (task_id, sha256)).fetchone()

    def list_downloads(self, run_id=None, task_id=None):
        if run_id is not None:
            return self.conn.execute(
                "SELECT * FROM Download WHERE run_id=? ORDER BY id", (run_id,)).fetchall()
        if task_id is not None:
            return self.conn.execute(
                "SELECT * FROM Download WHERE task_id=? ORDER BY id", (task_id,)).fetchall()
        return self.conn.execute("SELECT * FROM Download ORDER BY id").fetchall()

    # ---- Settings ---------------------------------------------------------
    def get_setting(self, key):
        row = self.conn.execute(
            "SELECT value FROM Settings WHERE key=?", (key,)).fetchone()
        if row is not None:
            return row["value"]
        return config.DEFAULT_SETTINGS.get(key)

    def set_setting(self, key, value):
        self.conn.execute(
            "INSERT OR REPLACE INTO Settings (key, value) VALUES (?, ?)", (key, str(value)))
        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
