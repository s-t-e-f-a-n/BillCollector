"""Both application launch paths must request Chromium's sandbox."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from billcollector import config, runner
import BillCollectorServices_pw as batch


def test_daemon_requests_sandbox_on_persistent_browser(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILE_ROOT", tmp_path)
    context = SimpleNamespace(task={"service": "synthetic", "user": "sandbox"},
                              bcs=SimpleNamespace())
    playwright = Mock()
    runner._launch_browser(context, playwright)
    assert playwright.chromium.launch_persistent_context.call_args.kwargs["chromium_sandbox"] is True


@pytest.mark.parametrize("prefix", ["-", "--"])
@pytest.mark.parametrize("argument", [
    "--no-sandbox", "--no-sandbox=true", "--disable-setuid-sandbox",
    "--disable-seccomp-filter-sandbox", "--disable-namespace-sandbox",
    "--disable-gpu-sandbox", "--disable-gpu-sandbox=true",
    "--single-process", "--in-process-gpu",
])
def test_disabling_sandbox_is_rejected_before_launch(tmp_path, monkeypatch, argument, prefix):
    argument = prefix + argument[2:]
    monkeypatch.setenv("BC_CHROMIUM_ARGS", argument)
    monkeypatch.setattr(config, "PROFILE_ROOT", tmp_path)
    monkeypatch.setattr(batch, "CHROMIUM_PLAYWRIGHT_PROFILE", str(tmp_path / "batch"))
    playwright = Mock()
    ctx = SimpleNamespace(task={"service": "synthetic", "user": "sandbox"}, bcs=SimpleNamespace())
    with pytest.raises(ValueError, match="must not disable"):
        runner._launch_browser(ctx, playwright)
    assert batch.InitBrowser(playwright, SimpleNamespace(dbg=False)) is None
    playwright.chromium.launch_persistent_context.assert_not_called()


def test_safe_browser_arguments_remain_supported(monkeypatch):
    monkeypatch.setenv("BC_CHROMIUM_ARGS", "--disable-software-rasterizer --lang=en")
    assert config.chromium_args() == ["--disable-software-rasterizer", "--lang=en"]


def test_batch_requests_sandbox_on_persistent_browser(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "CHROMIUM_PLAYWRIGHT_PROFILE", str(tmp_path / "batch"))
    playwright = Mock()
    assert batch.InitBrowser(playwright, SimpleNamespace(dbg=False)) is not None
    assert playwright.chromium.launch_persistent_context.call_args.kwargs["chromium_sandbox"] is True
