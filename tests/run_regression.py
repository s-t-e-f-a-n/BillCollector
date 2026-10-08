# -*- coding: utf-8 -*-
"""Layer A regression test harness for BillCollector.

Starts the local mock portal as a subprocess, executes every
(service, user) pair of a scope INI against the production scraping
engine (retrieve_from_service_with_playwright), and checks the outcome
against the expectations in tests/scenarios.py:

- engine return value (True/False)
- 'Service' row result (success/failure) of the pair's new run table
- exactly one graceful-error PageStatus row (testgraceful)
- new files in apps/Downloads == union of the expected downloads
- skip-and-continue: every pair produced its own new Service run row
- BillCollector exit semantics (1 if any pair failed, else 0)

Usage (from the repo root):
    apps/.venv/bin/python tests/run_regression.py --ini tests/bc_regression.ini
        [--keep-downloads] [--port 8787] [--vault]

Exit codes:
    0 - all expectations matched
    1 - at least one expectation deviated
    2 - the mock portal could not be started (e.g. port occupied)
    3 - a real BillCollector run holds the run lock
    4 - Vaultwarden preflight failed (--vault mode: env, DNS check,
        status/unlock, or sync)
"""

import argparse
import configparser
import fcntl
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_DIR = os.path.join(REPO_ROOT, "apps")
DOWNLOAD_DIR = os.path.join(APPS_DIR, "Downloads")
DB_FILE = os.path.join(APPS_DIR, "db", "bc.db")
LOCK_FILE = os.path.join(APPS_DIR, ".bc.lock")

sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, APPS_DIR)

from tests.scenarios import (  # noqa: E402
    CREDENTIALS,
    EXPECTATIONS,
    PORT_DEFAULT,
    SERVICE_TO_SITE,
    site_url,
)
from BillCollectorServices_pw import retrieve_from_service_with_playwright  # noqa: E402


def python_for_mock():
    venv = os.path.join(APPS_DIR, ".venv", "bin", "python")
    return venv if os.path.exists(venv) else sys.executable


def acquire_guard_lock():
    """Non-blocking exclusive flock on the shared run lock file (the same
    lock a real BillCollector run holds): shared browser profile, Downloads
    dir and DB must not be touched concurrently."""
    try:
        lock = open(LOCK_FILE, "a+")
    except OSError as e:
        print(f"Error: cannot open run lock {LOCK_FILE}: {e}")
        sys.exit(3)
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"Error: another BillCollector run is in progress "
              f"(lock file: {LOCK_FILE}); refusing to start the regression run.")
        sys.exit(3)
    except OSError as e:
        print(f"Error: cannot lock run lock {LOCK_FILE}: {e}")
        sys.exit(3)
    return lock  # keep the handle alive for the whole process


def vault_preflight():
    """Once-per-run vault checks mirroring WebRetriDoc
    (BillCollector.py:152-176): .env loaded, BW_API_URL resolves only to
    local HTTP addresses, the Bitwarden API answers success=true and is
    unlocked, sync works. Any failure exits 4. Returns the BW API base URL."""
    from dotenv import load_dotenv

    load_dotenv(os.path.join(APPS_DIR, ".env"))
    api = os.getenv("BW_API_URL")
    if not api:
        print("Error: --vault requires BW_API_URL in apps/.env.")
        sys.exit(4)

    from BillCollector import (
        bitwarden_api_check_status,
        is_json_property_value,
        post_json,
    )

    from vault_transport import VaultTransportError, pinned_api_url

    try:
        pinned_api_url(api)
    except VaultTransportError:
        print("Error: vault API does not resolve only to local HTTP addresses.")
        sys.exit(4)
    try:
        ret, status = bitwarden_api_check_status(api)
    except SystemExit:
        print(f"Error: vault API status check failed for {api}.")
        sys.exit(4)
    if not ret or status != "unlocked":
        print(f"Error: vault API {api} not ready (success={ret}, status={status!r}).")
        sys.exit(4)
    sync = post_json(f"{api}/sync", None)
    if not sync or not is_json_property_value(sync, "success", True):
        print(f"Error: vault sync failed for {api}.")
        sys.exit(4)
    return api


def vault_creds(api, service, user):
    """Per-pair credential fetch mirroring WebRetriDoc
    (BillCollector.py:244-251): item <service> <user> -> username / password
    / URI, plus the item's TOTP (400 = no TOTP -> None). Returns
    (url, username, password, totp). A missing item exits via the production
    client's sys.exit(1), exactly like production."""
    from BillCollector import get_json, get_json_property_value, get_totp

    item_name = f"{service} {user}".strip()
    item = get_json(f"{api}/object/item/{item_name}")
    totp_item = get_totp(f"{api}/object/totp/{item_name}")
    totp = get_json_property_value(totp_item, "data_data") if totp_item is not None else None
    return (
        get_json_property_value(item, "data_login_uris_0_uri"),
        get_json_property_value(item, "data_login_username"),
        get_json_property_value(item, "data_login_password"),
        totp,
    )


def start_mock(port):
    """Start the mock portal subprocess and poll /health (30 s timeout)."""
    mock_log = tempfile.NamedTemporaryFile(
        prefix=f"bc_mock_{port}_", suffix=".log", delete=False, mode="w")
    proc = subprocess.Popen(
        [python_for_mock(), "-m", "tests.mock_portal", "--port", str(port)],
        cwd=REPO_ROOT,
        stdout=mock_log,
        stderr=subprocess.STDOUT,
    )
    proc.mock_log = mock_log.name
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            print(f"Error: mock portal exited during startup "
                  f"(code {proc.returncode}); log: {proc.mock_log}")
            proc.terminate()
            return None
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:
                if r.status == 200:
                    return proc
        except Exception:
            time.sleep(0.5)
    print(f"Error: mock portal not ready on port {port} within 30 s "
          f"(port already occupied?); log: {proc.mock_log}")
    proc.terminate()
    return None


def db_snapshot():
    """Latest Service run number per service name."""
    conn = sqlite3.connect(DB_FILE)
    try:
        cur = conn.cursor()
        cur.execute("SELECT service_name, MAX(run_number) FROM Service GROUP BY service_name")
        return {row[0]: row[1] for row in cur.fetchall() if row[1] is not None}
    finally:
        conn.close()


def latest_service_run(service):
    """(run_number, run_table, result) of the newest Service row, or None."""
    conn = sqlite3.connect(DB_FILE)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT run_number, run_table, result FROM Service "
            "WHERE service_name = ? ORDER BY run_number DESC LIMIT 1",
            (service,))
        return cur.fetchone()
    finally:
        conn.close()


def graceful_error_rows(run_table):
    """PageStatus rows whose result JSON carries a non-empty 'error' list."""
    conn = sqlite3.connect(DB_FILE)
    try:
        cur = conn.cursor()
        cur.execute(f'SELECT step_number, locator_action, result FROM "{run_table}"')
        rows = cur.fetchall()
    finally:
        conn.close()
    graceful = []
    for step_number, action, result in rows:
        try:
            res = json.loads(result) if result else {}
        except (TypeError, ValueError):
            res = {}
        if isinstance(res, dict) and res.get("error"):
            graceful.append((step_number, action, res))
    return graceful


def run_pair(service, user, port, creds=None):
    """Run one (service, user) pair through the production engine.

    Default mode: credentials and URL from scenarios.py. Vault e2e mode:
    creds = (url, username, password, totp) fetched from the vault item."""
    if creds is not None:
        url, username, password, otp = creds
    else:
        site = SERVICE_TO_SITE[service]
        c = CREDENTIALS[service][user]
        url = site_url(port, site)
        username, password, otp = c["user"], c["password"], c["otp"]
    return retrieve_from_service_with_playwright(
        service, url, username, password, otp, False)


def check_pair(service, user, port, expected, expected_run_number, creds=None):
    """Run the pair and compare with the expectations. Returns (actual, problems)."""
    problems = []
    actual = run_pair(service, user, port, creds)
    if actual != expected["return"]:
        problems.append(f"return value: expected {expected['return']}, got {actual}")

    row = latest_service_run(service)
    if row is None:
        problems.append("no Service run row in DB")
    else:
        run_number, run_table, result = row
        if run_number != expected_run_number:
            problems.append(f"Service run number: expected {expected_run_number}, got {run_number}")
        if result != expected["service_result"]:
            problems.append(f"Service result: expected {expected['service_result']!r}, got {result!r}")
        if "graceful_error" in expected:
            ge = graceful_error_rows(run_table)
            if len(ge) != 1:
                problems.append(f"graceful error rows: expected exactly 1, found {len(ge)}")
            elif expected["graceful_error"] not in (ge[0][1] or ""):
                problems.append(
                    f"graceful error row does not reference "
                    f"{expected['graceful_error']!r}: {ge[0][1]}")
    return actual, problems


def read_scope_ini(path):
    """Parse the scope INI with the same section/loop order as WebRetriDoc."""
    script = configparser.ConfigParser()
    if not os.path.isfile(path):
        print(f"Error: INI file {path} not found.")
        sys.exit(2)
    script.read(path, encoding="utf-8")
    pairs = []
    for section in script.sections():
        if section.lower() != "playwright":
            continue
        for service, users_list in script[section].items():
            users = [u.strip() for u in users_list.split(",")] if users_list else [""]
            for user in users:
                pairs.append((service, user))
    if not pairs:
        print(f"Error: no [Playwright] service entries in {path}.")
        sys.exit(2)
    for service, user in pairs:
        if service not in EXPECTATIONS or user not in EXPECTATIONS[service]:
            print(f"Error: no expectations for pair {service} {user!r} in scenarios.py.")
            sys.exit(2)
    return pairs


def sweep_stale_downloads(pairs):
    """Remove expected test downloads left behind by earlier runs (manual
    single-pair runs or interrupted harness runs) so this run's new-files
    check counts them again. Only the scope's own expected filenames are
    touched (all prefixed by the test site names); the run lock is held, so
    no production run can be writing to the shared Downloads dir."""
    if not os.path.isdir(DOWNLOAD_DIR):
        return 0
    removed = 0
    for service, user in pairs:
        for name in EXPECTATIONS[service][user].get("downloads", []):
            path = os.path.join(DOWNLOAD_DIR, name)
            if os.path.isfile(path):
                os.remove(path)
                removed += 1
    return removed


def main():
    import logging
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
                        datefmt="%b %d %H:%M:%S")

    parser = argparse.ArgumentParser(description="BillCollector Layer A regression harness")
    parser.add_argument("--ini", required=True, help="scope INI file (e.g. tests/bc_regression.ini)")
    parser.add_argument("--keep-downloads", action="store_true",
                        help="do not delete the test downloads afterwards")
    parser.add_argument("--port", type=int, default=PORT_DEFAULT,
                        help=f"mock portal port (default {PORT_DEFAULT})")
    parser.add_argument("--vault", action="store_true",
                        help="fetch credentials, URL and TOTP from the real "
                             "Vaultwarden (BW_API_URL in apps/.env) "
                             "instead of scenarios.py (dev host only)")
    args = parser.parse_args()
    if args.vault and args.port != PORT_DEFAULT:
        parser.error("--vault requires the default mock port (the vault URIs bake in "
                     f"port {PORT_DEFAULT})")

    guard = acquire_guard_lock()  # noqa: F841 (held until process exit)

    pairs = read_scope_ini(args.ini)
    print(f"Scope: {len(pairs)} pair(s) from {args.ini}")

    removed = sweep_stale_downloads(pairs)
    if removed:
        print(f"Swept {removed} stale test download(s) from {DOWNLOAD_DIR}.")

    vault_api = None
    if args.vault:
        vault_api = vault_preflight()
        print(f"Vault preflight OK (API {vault_api}).")

    mock = start_mock(args.port)
    if mock is None:
        sys.exit(2)
    print(f"Mock portal ready on port {args.port} (pid {mock.pid}).")

    new_files = set()
    try:
        dl_before = set(os.listdir(DOWNLOAD_DIR)) if os.path.isdir(DOWNLOAD_DIR) else set()
        run_snap = db_snapshot()
        run_count = {}  # service -> pairs already run in this invocation

        results = []
        for service, user in pairs:
            expected = EXPECTATIONS[service][user]
            run_count[service] = run_count.get(service, 0) + 1
            expected_run_number = run_snap.get(service, 0) + run_count[service]
            t0 = time.time()
            creds = vault_creds(vault_api, service, user) if vault_api else None
            actual, problems = check_pair(service, user, args.port,
                                          expected, expected_run_number, creds)
            ok = not problems
            results.append((service, user, expected, actual, ok, problems))
            status = "OK  " if ok else "FAIL"
            print(f"{status} {service} {user} "
                  f"(return={actual}, expected={expected['return']}, "
                  f"{time.time() - t0:.1f}s)"
                  + (f" -> {problems}" if problems else ""))

        # Download check: new files in Downloads == union of the per-pair
        # expectations (failing pairs download nothing).
        dl_after = set(os.listdir(DOWNLOAD_DIR)) if os.path.isdir(DOWNLOAD_DIR) else set()
        new_files = dl_after - dl_before
        expected_files = set()
        for service, user in pairs:
            expected_files.update(EXPECTATIONS[service][user].get("downloads", []))
        missing = sorted(expected_files - new_files)
        extra = sorted(new_files - expected_files)
        downloads_ok = not missing and not extra
        if missing:
            print(f"FAIL downloads missing: {missing}")
        if extra:
            print(f"FAIL unexpected downloads: {extra}")
        if downloads_ok:
            print(f"OK   downloads: exactly the {len(expected_files)} expected file(s).")

        # BillCollector exit semantics (BillCollector.py:266-268).
        bc_exit = 1 if any(actual is False for _, _, _, actual, _, _ in results) else 0

        print()
        print(f"{'service':<15} {'user':<10} {'return':>8} {'db result':>12} verdict")
        for service, user, expected, actual, ok, problems in results:
            row = latest_service_run(service)
            db_result = row[2] if row else "-"
            exp_result = expected["service_result"]
            db_note = "" if db_result == exp_result else f" (expected {exp_result})"
            print(f"{service:<15} {user:<10} {str(actual):>8} {db_result + db_note:>12} "
                  f"{'OK' if ok else 'FAIL'}")
        print()
        print(f"BillCollector exit semantics: {bc_exit} "
              f"({'at least one pair failed' if bc_exit else 'all pairs succeeded'})")

        all_ok = all(ok for (_, _, _, _, ok, _) in results) and downloads_ok
        print("VERDICT:", "PASS - all expectations matched." if all_ok
              else "FAIL - at least one expectation deviated.")
        sys.exit(0 if all_ok else 1)
    finally:
        mock.terminate()
        try:
            mock.wait(timeout=10)
        except subprocess.TimeoutExpired:
            mock.kill()
        print(f"Mock portal stopped (log: {mock.mock_log}).")
        if not args.keep_downloads and new_files:
            for name in new_files:
                path = os.path.join(DOWNLOAD_DIR, name)
                try:
                    os.remove(path)
                except OSError as e:
                    print(f"Warning: could not remove {path}: {e}")
            print(f"Removed {len(new_files)} test download(s) from {DOWNLOAD_DIR}.")


if __name__ == "__main__":
    main()
