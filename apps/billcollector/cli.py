"""Command line interface for the BillCollector daemon.

Subcommands:
- ``serve``: start the NiceGUI daemon (M1 skeleton: placeholder index only)
- ``run``: execute a single task run (sync Playwright step loop)
"""

import argparse
import logging

from . import config
from .db import Database

logger = logging.getLogger("billcollector.cli")


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser (host default reads env, so call after load_env)."""
    parser = argparse.ArgumentParser(
        prog="billcollector",
        description="BillCollector daemon (NiceGUI + Playwright).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="run the daemon HTTP server (NiceGUI)")
    p_serve.add_argument(
        "--host",
        default=config.env("BC_UI_HOST", "127.0.0.1"),
        help="bind host (default: $BC_UI_HOST if set, else 127.0.0.1)",
    )
    p_serve.add_argument(
        "--port", type=int, default=8000, help="bind port (default: 8000)")

    p_run = sub.add_parser("run", help="execute one task run")
    p_run.add_argument("task_id", type=int, help="Task id to run")
    p_run.add_argument("--debug", action="store_true", help="run in debug mode")

    return parser


def main(argv=None) -> int:
    """CLI entry point; returns the process exit code."""
    config.load_env()
    config.ensure_dirs()
    database = Database()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s")

    args = _build_parser().parse_args(argv)

    if args.command == "serve":
        created = database.import_ini(config.INI_FILES)
        # Seed the UI password hash from BC_UI_PASSWORD on first start
        # (before any request is served; never overwrites an existing hash).
        from .ui import auth as ui_auth

        ui_auth.ensure_password(database)
        # Upgraded installs (a password is set and at least one task is
        # enabled) skip the first-start wizard; fresh installs see it
        # (M4 C2, decision 1).
        ui_auth.auto_complete_onboarding(database)
        logger.info("serve starting on %s:%d (ini import created %d task(s), "
                    "total %d)", args.host, args.port, created,
                    len(database.list_tasks()))
        # Lazy import: NiceGUI is only needed when actually serving.
        from .ui import app as ui_app

        ui_app.start(args.host, args.port)
        return 0

    if args.command == "run":
        # Lazy import: Playwright is only needed when actually running a task.
        from . import runner

        return runner.run_task(args.task_id, args.debug)

    return 2  # unreachable: subcommand dispatch is exhaustive
