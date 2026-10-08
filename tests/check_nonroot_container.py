"""Exercise a built image with synthetic private mounts and no network."""

import json
import subprocess
import sys

CHECK = r'''
import os, pathlib, subprocess, sys
from helpers import (DB_FILE, DOWNLOAD_DIR, LOG_DEFAULT_FILE, LOCK_FILE,
                     CHROMIUM_PLAYWRIGHT_PROFILE, acquire_run_lock, setup_logging)
from BillCollectorServices_pw import DatabaseManager, init_browser_profile
from playwright.sync_api import sync_playwright
assert os.getuid() != 0, 'image runs as root'
assert not os.access('/apps/BillCollector.py', os.W_OK), 'app source writable'
writable = [str(path) for path in pathlib.Path('/apps').rglob('*')
            if path.parts[2] not in ('db', 'Downloads', 'runtime') and not path.is_symlink()
            and os.access(path, os.W_OK)]
assert not writable, f'image paths writable: {writable[:5]}'
setup_logging(LOG_DEFAULT_FILE)
lock = acquire_run_lock()
try:
    acquire_run_lock()
except SystemExit as error:
    assert error.code == 1
else:
    raise AssertionError('overlap lock accepted a second run')
lock.close()
DatabaseManager(DB_FILE).close_connection()
assert init_browser_profile()
with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(CHROMIUM_PLAYWRIGHT_PROFILE, headless=True)
    page = browser.new_page()
    page.set_content('<h1>Synthetic non-root check</h1>')
    page.pdf(path=str(pathlib.Path(DOWNLOAD_DIR) / 'synthetic.pdf'))
    browser.close()
ini = pathlib.Path('/apps/runtime/synthetic.ini')
ini.write_text('[Playwright]\nsynthetic=\n')
env = dict(os.environ, VAULT_HOST='127.0.0.1', BW_API_URL='http://127.0.0.1:9')
result = subprocess.run([sys.executable, 'BillCollector.py', str(ini)], env=env,
                        capture_output=True, text=True, timeout=30)
assert result.returncode == 1, f'CLI did not fail cleanly without vault: {result.returncode}'
assert 'PermissionError' not in result.stdout + result.stderr
assert 'Traceback' not in result.stdout + result.stderr
for path in (DB_FILE, LOG_DEFAULT_FILE, LOCK_FILE, str(pathlib.Path(DOWNLOAD_DIR) / 'synthetic.pdf')):
    assert pathlib.Path(path).is_file(), f'missing writable artifact: {path}'
print(f'Non-root runtime UID={os.getuid()}: source protected, lock/DB/log/profile/PDF and CLI verified')
'''


def main():
    image = sys.argv[1]
    info = json.loads(subprocess.check_output(["docker", "image", "inspect", image]))[0]
    default_identity = info["Config"]["User"]
    uid, gid = default_identity.split(":")
    if not uid.isdecimal() or not gid.isdecimal() or int(uid) == 0:
        raise RuntimeError("Image must default to a numeric non-root UID/GID")
    # GID 0 models the arbitrary-UID convention: the source must not be group-writable.
    for identity in (default_identity, "1234:2345", "1234:0"):
        uid, gid = identity.split(":")
        command = ["docker", "run", "--rm", "--network", "none", "--user", identity]
        for directory in ("/apps/db", "/apps/Downloads", "/apps/runtime"):
            command += ["--tmpfs", f"{directory}:uid={uid},gid={gid},mode=0700"]
        subprocess.run(command + ["--entrypoint", "python3", image, "-c", CHECK], check=True)

    # Model folders shared through a secondary group, not the operator's UID/GID.
    for allowed in (False, True):
        command = ["docker", "run", "--rm", "--network", "none", "--user", "1000:1000"]
        if allowed:
            command += ["--group-add", "100"]
        for directory in ("/apps/db", "/apps/Downloads"):
            command += ["--tmpfs", f"{directory}:uid=7777,gid=100,mode=0770"]
        probe = f"""
import os, pathlib
for directory in ('/apps/db', '/apps/Downloads'):
    assert os.access(directory, os.W_OK) == {allowed!r}
    if {allowed!r}:
        (pathlib.Path(directory) / 'synthetic').write_text('synthetic')
assert not os.access('/apps/BillCollector.py', os.W_OK)
print('Supplementary-group access allowed={allowed}: PASS')
"""
        subprocess.run(command + ["--entrypoint", "python3", image, "-c", probe], check=True)


if __name__ == "__main__":
    main()
