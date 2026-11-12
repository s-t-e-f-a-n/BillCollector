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
BROWSER_DIR = Path(os.environ.get("BC_BROWSER_DIR") or APP_DIR / "browser")
PROFILE_ROOT = _path("BC_PROFILE_ROOT", BROWSER_DIR / "profiles")
DOWNLOAD_DIR = _path("BC_DOWNLOAD_DIR", APP_DIR / "Downloads")

# Recipes stay as git-versioned YAML on disk (decision 7).
RECIPE_DIR = APP_DIR / "recipes_playwright"
# RECIPE_SCHEMA stays bound to the built-in dir: the schema/contract is
# core-owned; a schema file inside the overlay is ignored.
RECIPE_SCHEMA = RECIPE_DIR / "recipe-pw-schema.yaml"
RECIPE_PREFIX = "recipe-pw__"


def _recipe_extra_dir() -> Path | None:
    """The optional user recipe overlay directory, or ``None`` when
    ``BC_RECIPE_EXTRA_DIR`` is unset/empty. When set, per-service recipes are
    shadowed by files in this directory and UI recipe edits are saved into it;
    when ``None`` every recipe path is the built-in (``RECIPE_DIR``) one and
    behavior is unchanged."""
    raw = os.environ.get("BC_RECIPE_EXTRA_DIR")
    if raw is None:
        return None
    raw = str(raw).strip()
    return Path(raw) if raw else None


# Optional user recipe overlay (see :func:`_recipe_extra_dir`). Refreshed by
# :func:`load_env` so a value loaded from ``apps/.env`` at startup is honored.
RECIPE_EXTRA_DIR = _recipe_extra_dir()

# INI files imported into Tasks on first daemon start (decision 7 / M1 item 2).
INI_FILES = (APP_DIR / "bc_default.ini", APP_DIR / "bc_test.ini")

# Point Playwright at the repo-local browser build before it is imported.
if not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSER_DIR)

# Defaults. Runtime-overridable via the Settings table (db.get_setting).
# Values are strings to match the TEXT Settings table; parse at the call site.
DEFAULT_SETTINGS = {
    "pause_deadline_seconds": "1800",    # 30 min hold before a pause aborts
    "max_concurrency": "1",              # global runner semaphore
    "display_start": "99",               # first Xvfb display (:99)
    "display_count": "16",               # how many displays to scan when allocating
    "git_commit_enabled": "false",       # auto-commit recipe edits made in the UI
    "ui_base_url": "http://127.0.0.1:8000",
    # Empty: no push notifications until the operator sets a topic (opt-in).
    "ntfy_topic": "",
    "download_dir": str(DOWNLOAD_DIR),
    "download_recovery_timeout_seconds": "300",
    "vnc_password": "",                  # empty: noVNC is localhost-only, no auth
}


def ensure_dirs() -> None:
    """Create the runtime directories the daemon writes to."""
    for d in (DATA_DIR, DB_DIR, LOG_DIR, DISPLAY_DIR, RUN_DIR, DOWNLOAD_DIR, PROFILE_ROOT):
        d.mkdir(parents=True, exist_ok=True)
    if RECIPE_EXTRA_DIR is not None:
        RECIPE_EXTRA_DIR.mkdir(parents=True, exist_ok=True)


def load_env() -> None:
    """Load apps/.env into os.environ (without clobbering exported values)."""
    from dotenv import load_dotenv

    global RECIPE_EXTRA_DIR
    env_file = APP_DIR / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)
    RECIPE_EXTRA_DIR = _recipe_extra_dir()


def env(name: str, default=None):
    """Read an environment variable (call :func:`load_env` first at startup)."""
    return os.environ.get(name, default)


def vault_settings(db) -> tuple[str, str]:
    """The effective vault API ``(url, host)`` for a run or a check.

    Per key, a non-empty Settings value (``vault_api_url`` /
    ``vault_api_host``) wins over the environment (``BW_API_URL`` /
    ``BW_API_HOST``); an empty result means unset for that key. The two
    Settings keys are deliberately absent from DEFAULT_SETTINGS: a missing
    row means "use the environment" (legacy env-only deployments)."""
    def resolve(key: str, env_name: str) -> str:
        value = db.get_setting(key)
        if value is not None and str(value).strip():
            return str(value).strip()
        return str(os.environ.get(env_name) or "").strip()
    return (resolve("vault_api_url", "BW_API_URL"),
            resolve("vault_api_host", "BW_API_HOST"))


def chromium_args() -> list[str]:
    """Additional Chromium launch arguments, space-separated, from BC_CHROMIUM_ARGS.

    Host-specific launch workaround only — leave unset for stock behavior;
    example: ``--disable-software-rasterizer`` on GPU-less WSL2 hosts where the
    renderer produces no frames during the process cold phase (Playwright
    actionability timeouts).
    """
    args = os.environ.get("BC_CHROMIUM_ARGS", "").split()
    forbidden = {"--no-sandbox", "--disable-setuid-sandbox",
                 "--disable-seccomp-filter-sandbox", "--disable-namespace-sandbox",
                 "--disable-gpu-sandbox", "--single-process", "--in-process-gpu"}
    if any("--" + arg.split("=", 1)[0].lstrip("-") in forbidden for arg in args):
        raise ValueError("BC_CHROMIUM_ARGS must not disable Chromium sandbox isolation")
    return args


def recipe_filename_for(service: str) -> str:
    """Per-service recipe file name, e.g. recipe-pw__winsim.yaml
    (lowercased, spaces -> underscores)."""
    return f"{RECIPE_PREFIX}{service.lower().replace(' ', '_')}.yaml"


def recipe_path_for(service: str) -> Path:
    """Path of the per-service recipe file, e.g. recipe-pw__winsim.yaml.

    When the recipe overlay (``BC_RECIPE_EXTRA_DIR``) is set and holds a file
    for the service, that shadow path wins; otherwise the built-in path is
    used. The same normalization as before (lowercase, spaces -> underscores)."""
    name = recipe_filename_for(service)
    if RECIPE_EXTRA_DIR is not None and (RECIPE_EXTRA_DIR / name).exists():
        return RECIPE_EXTRA_DIR / name
    return RECIPE_DIR / name


def recipe_builtin_path_for(service: str) -> Path:
    """The built-in (image) recipe path, ignoring any overlay."""
    return RECIPE_DIR / recipe_filename_for(service)


def recipe_save_path_for(service: str) -> Path:
    """Where a UI recipe edit of the service is written.

    When the overlay is set, saves always land in the overlay (a save of a
    built-in service shadows it); when unset, saves go to the built-in path
    (today's behavior)."""
    name = recipe_filename_for(service)
    if RECIPE_EXTRA_DIR is not None:
        return RECIPE_EXTRA_DIR / name
    return RECIPE_DIR / name


def resolve_recipe_path(stored: str | None, service: str) -> str:
    """The effective recipe path for a run (the runner's run-time resolution).

    A task's stored ``recipe_file`` wins only when it is set, is not the
    auto-populated built-in default for the service, and the file exists;
    otherwise the overlay-aware :func:`recipe_path_for` is used. So a shadow
    added after task creation takes effect for existing tasks, and a stale
    built-in snapshot (stored before the column stopped being auto-populated)
    never hides a shadow. An explicit non-default path still wins."""
    builtin = str(recipe_builtin_path_for(service))
    if stored and stored != builtin and Path(stored).exists():
        return stored
    return str(recipe_path_for(service))


def profile_dir_for(service: str, user: str) -> Path:
    """Per-task persistent browser profile directory (decision 9)."""
    safe = f"{service}_{user}".strip("_").replace(" ", "_").lower()
    return PROFILE_ROOT / (safe or "default")
