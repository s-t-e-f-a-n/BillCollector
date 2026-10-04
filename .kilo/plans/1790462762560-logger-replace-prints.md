# BillCollector — Replace print() with real logging

> Status: DELIVERED in v0.3 — retained for the record.

Implements M0 step 5 of the daemon plan (`1790364274061-billcollector-nicegui-daemon-plan.md`):
"`logging` module instead of the `print = logging.debug` hack; `RotatingFileHandler` for
`bc.log` plus plain stdout (stdout is what M1 streams to the UI)".

## Current state (facts from the code)

- 63 `print()` calls across the 6 Python files under `apps/`
- Partial setup already exists: `log_setup()` in `BillCollector.py:29` — root logger at
  DEBUG + `WatchedFileHandler(bc.log)`, **no console handler**
- Hack: `print = logging.debug` at `BillCollector.py:250` (only when not debugging)
- Production (cron → `BillCollector.sh` → `docker run --rm`) bind-mounts only
  `Downloads/` and `db/` → `bc.log` is **ephemeral**. In non-debug mode everything goes
  to that file only → **production log output is currently lost**; in F5 debug mode
  prints go to stdout and the file gets nothing
- Tracebacks are lost everywhere: `except` blocks print only `str(e)`
- `CheckRecipe` is in the batch import chain (`BillCollectorServices_pw.py:10`
  `from helpers import *`) and prints "Recipe ... is a valid BillCollector yaml!" on
  every service of every production run
- No `os.chdir` / `latest_download_file` in the current code (v1 plan item is stale);
  all paths are absolute via `APP_DIR`

## Decisions

1. **Single shared setup** in `helpers/BillCollectorHelpers.py` (exported via the
   existing `from helpers import *`), replacing `log_setup()` in `BillCollector.py`:

   ```python
   def setup_logging(logfile=None, debug=False, max_bytes=5_000_000, backup_count=5):
       root = logging.getLogger()
       if root.handlers:          # idempotent — safe if called twice in one process
           return
       root.setLevel(logging.DEBUG)
       fmt = logging.Formatter(
           "%(asctime)s %(name)s [%(process)d] %(levelname)s: %(message)s",
           "%b %d %H:%M:%S")
       fmt.converter = time.localtime
       if logfile is not None:
           file_handler = logging.handlers.RotatingFileHandler(
               logfile, maxBytes=max_bytes, backupCount=backup_count)
           file_handler.setLevel(logging.DEBUG)
           file_handler.setFormatter(fmt)
           root.addHandler(file_handler)
       console = logging.StreamHandler(sys.stdout)
       console.setLevel(logging.DEBUG if debug else logging.INFO)
       console.setFormatter(fmt)
       root.addHandler(console)
   ```

   - Batch entry point: `setup_logging(LOG_DEFAULT_FILE, debug=bc.debug)` (file DEBUG +
     console INFO; console DEBUG in debug mode — preserves today's F5 visibility)
   - CLI tools (CheckRecipe, CreateRecipe `__main__`): `setup_logging()` → console-only,
     so dev-tool runs do not pollute the production log file
   - Rotation: 5 MB × 5 backups (25 MB cap); `bc.log` path unchanged

2. **Per-module logger**: `logger = logging.getLogger(__name__)` in each module.

3. **Level mapping** (file gets everything at DEBUG, console stays clean at INFO):

   | Output | Level |
   |---|---|
   | Service started/finished, file(s) downloaded, vault synced, pause/resume, debug-mode notice | INFO |
   | "finished without a file downloaded", DNS/vault retry attempts, all-evaluation-attempts-failed | WARNING |
   | "Processing Step N", Bitwarden status JSON dump, "is a valid BillCollector yaml", JS evaluation retry attempts | DEBUG |
   | Failures, invalid YAML, missing files, usage errors | ERROR — inside `except` blocks use `logger.exception(...)` so the **traceback is no longer lost** |

4. **Scope (confirmed):** all 6 modules. In `CreateRecipe_pw.py` the interactive TUI
   (menu rendering, `get_user_choice` prompts, "Skipping modification.") stays
   `print()` — that is user interaction, not log output. Everything else becomes logger
   calls.

5. **Remove the noise:** the `else: print(f"{__name__} imported as module.")` blocks in
   `BillCollector.py`, `CheckRecipe`, `CreateRecipe_pw.py` are deleted. The commented-out
   prints in `safe_evaluate` (`BillCollectorServices_pw.py:194,196`) are replaced by
   `logger.debug` / `logger.warning` calls.

6. **Drive-by fixes** (only in functions already edited):
   - `CheckRecipe.get_schema_for_yaml`: `except yml.YAMLError:` → `except yaml.YAMLError:`
     (`yml` is unbound when `safe_load` fails → NameError masks the real error)
   - `CheckRecipe`: `except FileNotFoundError or OSError:` (×2) → `except OSError:`
   - `BillCollector.py:42,50`: German comments → English (global rule)

## Task list

1. **`apps/helpers/BillCollectorHelpers.py`**
   - Add `import logging`, `import logging.handlers`, module logger
   - Add `setup_logging()` as decided above
   - `pause_check()`: both prints → `logger.info`

2. **`apps/BillCollector.py`**
   - Delete `log_setup()`; `__main__` calls `setup_logging(LOG_DEFAULT_FILE, debug=bc.debug)`
     (keep the existing `sys.stdout = sys.__stdout__` line, keep call order)
   - Delete the `print = logging.debug` hack (line 250)
   - Convert all prints per the level table; collapse the `else: print(...)` one-liners
     in `WebRetriDoc` into normal if/else blocks
   - `bitwarden_api_check_status`: status JSON dump → DEBUG
   - `post_json`: two error prints → one `logger.error` including status + body
   - Translate the two German comments (lines 42, 50)
   - Delete the `imported as module` print

3. **`apps/BillCollectorServices_pw.py`**
   - Module logger; `InitBrowser` / `init_browser_profile` excepts → ERROR (keep the
     `return None/False` behavior)
   - `safe_evaluate`: commented-out prints → `logger.debug` (per failed attempt) and
     `logger.warning` (all attempts failed)
   - `retrieve_from_service_with_playwright`: finished-with-files → INFO,
     finished-without-files → WARNING, exception → `logger.exception` (keeps the
     `inspect.currentframe()` function name in the message)
   - `perform_actions`: "Processing Service" → INFO; swallowed exception at line 463 →
     `logger.exception` (traceback now visible; behavior — swallow and continue —
     unchanged, error propagation is M0.2)
   - `process_step`: "Processing Step N" → DEBUG

4. **`apps/helpers/BillCollectorCheckRecipe.py`**
   - Module logger; all prints per the level table ("valid yaml" → DEBUG, usage → ERROR)
   - `__main__`: `setup_logging()` (console-only) before the checks
   - Drive-by fixes (item 6)
   - Exit codes unchanged (`exit(1)` paths stay)
   - Delete the `imported as module` print

5. **`apps/helpers/BillCollectorCreateRecipe_pw.py`**
   - Module logger; errors (file missing, read/save failure, usage) → ERROR,
     results ("Recipe has been saved in ...") → INFO
   - TUI lines stay `print()` (menu, prompt, "Skipping modification.")
   - `__main__`: `setup_logging()` (console-only)
   - Delete the `imported as module` print

6. **Validation** (from `apps/`, venv `apps/.venv`)
   - `python -m py_compile` on all 6 files
   - `python helpers/BillCollectorCheckRecipe.py` over all 7
     `recipes_playwright/recipe-pw__*.yaml` → all valid, output via logger
   - Negative: CheckRecipe against a deliberately broken YAML → ERROR line, exit code 1
   - Local non-debug run `python BillCollector.py bc_test.ini` (hits real portals —
     user's call): stdout must carry INFO lines, `bc.log` must carry DEBUG lines
   - F5 debug (`bc_test.ini`): console shows DEBUG, pause/resume logged, `bc.log` on
     the host filled
   - Rotation sanity: temp-dir script calling `setup_logging(tmp, max_bytes=1000)`,
     emit >1 KB, assert `bc.log.1` exists
   - `grep -rn "print(" apps/` → remaining hits only in the CreateRecipe TUI lines

## Risks

- **Third-party loggers** (playwright, requests) attach to the root logger and will now
  appear in `bc.log` / console at WARNING+. Accepted — that is useful signal, no filter.
- **Cron mail format changes** (timestamp/level prefixes on each line). Harmless;
  exit codes and cron behavior unchanged.
- **Double handler attachment** if `setup_logging` is called twice in one process —
  guarded by the `root.handlers` idempotency check.
- `perform_actions` still **swallows** its exception (now with traceback in the log);
  run-abort-on-failure is M0.2, out of scope here.

## Out of scope

- Error propagation / aborting the run on a failed step (daemon plan M0.2)
- Persisting `bc.log` across production container runs (`BillCollector.sh` mounts only
  Downloads + db; stdout is the durable channel until M1)
- The M1 daemon runner / `python -m billcollector` (the stdout handler is what it will
  stream — this change prepares for it)
- Third-party log level filtering, log format changes beyond adding `%(levelname)s`

## Open questions

- Do you want a persistent log file in production (mount a log dir in
  `BillCollector.sh`)? Recommendation: **no for now** — cron captures stdout, and M1
  adds per-run log files.
