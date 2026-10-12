# -*- coding: utf-8 -*-
"""The runfiles static directory (M2 chunk D4.2).

``config.RUN_DIR`` (``<data>/runs/<run_id>/…``) is exposed to the UI as the
NiceGUI static directory ``/runfiles`` (locked decision 10: deliberately not
``/runs``, which is reserved for the ntfy deep-link route). Step screenshots
(``step_N.png``), pause screenshots (``pause_N.png``), and the VNC auth file
live there; :func:`runfile_url` maps a stored absolute path back to its
``/runfiles`` URL.
"""

from pathlib import Path

from .. import config


def register_runfiles(app) -> None:
    """Expose ``config.RUN_DIR`` at ``/runfiles`` (D4.2).

    The URL prefix is ``/runfiles`` (locked decision 10), the local
    directory ``config.RUN_DIR``; the directory must exist (Starlette's
    StaticFiles checks), hence the ``ensure_dirs`` first."""
    config.ensure_dirs()
    app.add_static_files("/runfiles", config.RUN_DIR)


def runfile_url(path) -> str | None:
    """Map an absolute path under ``config.RUN_DIR`` to its ``/runfiles``
    URL (None when the path is missing or outside the run tree)."""
    if not path:
        return None
    p = Path(path)
    try:
        rel = p.relative_to(config.RUN_DIR)
    except ValueError:
        try:
            rel = p.resolve().relative_to(config.RUN_DIR.resolve())
        except ValueError:
            return None
    return "/runfiles/" + rel.as_posix()
