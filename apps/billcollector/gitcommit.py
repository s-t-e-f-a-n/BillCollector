# -*- coding: utf-8 -*-
"""Git auto-commit for UI recipe edits (M2 chunk D5.2).

Locked decision 13: a recipe edit saved in the UI commits exactly the
recipe file (never ``git add -A`` - the repo is a bind mount on the
NAS, single operator, and unrelated dirty files must never be swept
into the commit), with the message ``recipe(<service>): <summary>``.
A no-op save (nothing staged changed) is a success, not an error:
``git commit`` with nothing staged reports "nothing to commit".
"""

import subprocess
from pathlib import Path

from . import config

# The repo root: the repository containing apps/ (config.APP_DIR).
REPO_ROOT = config.APP_DIR.parent

# How much of a git failure to surface in the UI (the output tail).
TAIL_CHARS = 2000

# The git commands are fast on a local checkout; the timeout bounds a
# wedged NAS mount from freezing the page handler.
GIT_TIMEOUT = 60


def _tail(text: str, width: int = TAIL_CHARS) -> str:
    text = (text or "").strip()
    return text if len(text) <= width else "…" + text[-width:]


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, timeout=GIT_TIMEOUT)


def git_commit(paths, message: str, repo=None) -> tuple:
    """Stage exactly ``paths`` and commit them with ``message``.

    Returns ``(ok, output)``: "nothing to commit" (no changes to the
    staged paths) is a success; any other non-zero exit or git failure
    is ``(False, output tail)``. ``repo`` overrides the repo root
    (tests)."""
    repo = Path(repo) if repo is not None else REPO_ROOT
    try:
        added = _git(repo, "add", "--", *[str(p) for p in paths])
        if added.returncode != 0:
            return False, _tail(added.stderr or added.stdout)
        committed = _git(repo, "commit", "-m", message)
        if committed.returncode != 0:
            out = (committed.stderr or "") + (committed.stdout or "")
            if "nothing to commit" in out or "no changes added" in out:
                return True, "nothing to commit"
            return False, _tail(out)
        return True, _tail(committed.stdout or "")
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"git failed: {e}"
