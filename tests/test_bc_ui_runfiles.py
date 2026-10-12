# -*- coding: utf-8 -*-
"""Unit tests for the runfiles static directory (M2 chunk D4.4).

The startup path (``build_app`` -> ``register_runfiles``) must expose
``config.RUN_DIR`` at ``/runfiles`` (D4.2), and ``runfile_url`` must map
a stored absolute path back to its ``/runfiles`` URL (the screenshot
and pause-thumbnail cells of the task detail page).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import config  # noqa: E402
from billcollector.ui.runfiles import register_runfiles, runfile_url  # noqa: E402


class _FakeApp:
    """Records the ``add_static_files`` calls (the startup-path smoke)."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def add_static_files(self, url_path: str, local_directory, **kwargs) -> None:
        self.calls.append((url_path, str(local_directory), kwargs))


def test_register_runfiles_exposes_the_run_dir():
    app = _FakeApp()
    register_runfiles(app)
    assert app.calls == [("/runfiles", str(config.RUN_DIR), {})]
    # The directory must exist (Starlette's StaticFiles checks it).
    assert config.RUN_DIR.is_dir()


def test_runfile_url_maps_paths_under_the_run_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUN_DIR", tmp_path)
    run_dir = tmp_path / "7"
    run_dir.mkdir()
    shot = run_dir / "step_1.png"
    shot.write_bytes(b"x")
    assert runfile_url(str(shot)) == "/runfiles/7/step_1.png"
    # A Path (not only str) input works as well.
    assert runfile_url(shot) == "/runfiles/7/step_1.png"


def test_runfile_url_rejects_paths_outside_the_run_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUN_DIR", tmp_path / "runs")
    outside = tmp_path / "other" / "x.png"
    assert runfile_url(str(outside)) is None
    assert runfile_url(None) is None
    assert runfile_url("") is None


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
