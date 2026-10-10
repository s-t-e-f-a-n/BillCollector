"""Runtime configuration for the BillCollector daemon.

Central place for filesystem paths, ``.env`` loading, and default settings.
The DB ``Settings`` table (see :mod:`billcollector.db`) overrides the defaults
at runtime. Paths can be redirected with ``BC_*`` environment variables, which
keeps the test suite from touching the production ``apps/`` data.
"""

import os
from pathlib import Path

# The package lives at apps/billcollector/, so the app root is the parent dir.
APP_DIR = Path(__file__).resolve().parent.parent


def _path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default)))


# Data layout. Everything the daemon writes at runtime lives under data/
# (logs, display locks, run artifacts) so a single volume mount covers it.
DATA_DIR = _path("BC_DATA_DIR", APP_DIR / "data")
DB_DIR = _path("BC_DB_DIR", APP_DIR / "db")
DB_FILE = _path("BC_DB_FILE", APP_DIR / "db" / "bc.db")
LOG_DIR = _path("BC_LOG_DIR", DATA_DIR / "logs")
DISPLAY_DIR = DATA_DIR / "displays"
RUN_DIR = DATA_DIR / "runs"

# Browser + downloads. Per-task profiles are never auto-deleted (decision 9).
BROWSER_DIR = _path("BC_BROWSER_DIR", APP_DIR / "browser")
PROFILE_ROOT = _path("BC_PROFILE_ROOT", BROWSER_DIR / "profiles")
DOWNLOAD_DIR = _path("BC_DOWNLOAD_DIR", APP_DIR / "Downloads")

# Recipes stay as git-versioned YAML on disk (decision 7).
RECIPE_DIR = APP_DIR / "recipes_playwright"
RECIPE_SCHEMA = RECIPE_DIR / "recipe-pw-schema.yaml"
RECIPE_PREFIX = "recipe-pw__"

# INI files imported into Tasks on first daemon start (decision 7 / M1 item 2).
INI_FILES = (APP_DIR / "bc_default.ini", APP_DIR / "bc_test.ini")

# Point Playwright at the repo-local browser build before it is imported.
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(BROWSER_DIR))

# Defaults. Runtime-overridable via the Settings table (db.get_setting).
# Values are strings to match the TEXT Settings table; parse at the call site.
DEFAULT_SETTINGS = {
    "pause_deadline_seconds": "1800",    # 30 min hold before a pause aborts
    "max_concurrency": "1",              # global runner semaphore
    "display_start": "99",               # first Xvfb display (:99)
    "display_count": "16",               # how many displays to scan when allocating
    "git_commit_enabled": "false",       # auto-commit recipe edits made in the UI
    "ui_base_url": "http://127.0.0.1:8000",
    "ntfy_topic": "billcollector",       # ntfy push topic for pause deep links
    "download_dir": str(DOWNLOAD_DIR),
    "vnc_password": "",                  # empty: noVNC is localhost-only, no auth
}


def ensure_dirs() -> None:
    """Create the runtime directories the daemon writes to."""
    for d in (DATA_DIR, DB_DIR, LOG_DIR, DISPLAY_DIR, RUN_DIR, DOWNLOAD_DIR, PROFILE_ROOT):
        d.mkdir(parents=True, exist_ok=True)


def load_env() -> None:
    """Load apps/.env into os.environ (without clobbering exported values)."""
    from dotenv import load_dotenv

    env_file = APP_DIR / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)


def env(name: str, default=None):
    """Read an environment variable (call :func:`load_env` first at startup)."""
    return os.environ.get(name, default)

def chromium_args() -> list[str]:
    """Additional Chromium launch arguments, space-separated, from BC_CHROMIUM_ARGS.

    Host-specific launch workaround only — leave unset for stock behavior;
    example: ``--disable-software-rasterizer`` on GPU-less WSL2 hosts where the
    renderer produces no frames during the process cold phase (Playwright
    actionability timeouts).
    """
    return os.environ.get("BC_CHROMIUM_ARGS", "").split()


def recipe_path_for(service: str) -> Path:
    """Path of the per-service recipe file, e.g. recipe-pw__winsim.yaml."""
    return RECIPE_DIR / f"{RECIPE_PREFIX}{service.lower().replace(' ', '_')}.yaml"


def profile_dir_for(service: str, user: str) -> Path:
    """Per-task persistent browser profile directory (decision 9)."""
    safe = f"{service}_{user}".strip("_").replace(" ", "_").lower()
    return PROFILE_ROOT / (safe or "default")
