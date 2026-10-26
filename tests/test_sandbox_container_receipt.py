"""Retain cleanup evidence and the primary failure without contacting Docker."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "sandbox_container_check", Path(__file__).with_name("run_sandbox_container.py"))
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)


@pytest.mark.parametrize("primary_failure", [False, True])
@pytest.mark.parametrize("cleanup_step", ["inspect", "stop", "rm", "ps", "volume"])
@pytest.mark.parametrize("failure_type", [subprocess.CalledProcessError, subprocess.TimeoutExpired])
def test_cleanup_failure_keeps_receipt_and_primary_error(
        tmp_path, monkeypatch, primary_failure, cleanup_step, failure_type):
    output = tmp_path / "proof"
    name = "billcollector-sandbox-owned"
    monkeypatch.setattr(check, "uuid4", lambda: SimpleNamespace(hex="owned"))
    monkeypatch.setattr(check.shutil, "which", lambda _: "/synthetic/docker")
    monkeypatch.setattr(sys, "argv", ["check", "--image", "synthetic", "--output", str(output)])
    cleanup = False
    commands = []
    inspections = 0

    def run(command, **kwargs):
        nonlocal cleanup, inspections
        args = command[3:]
        commands.append(args)
        if args[0] == "inspect":
            inspections += 1
        final_inspection = inspections >= (2 if primary_failure else 3)
        if cleanup and args[0] == cleanup_step and (cleanup_step != "inspect" or final_inspection):
            if failure_type is subprocess.TimeoutExpired:
                raise failure_type(command, 30)
            raise failure_type(1, command)
        if args[:2] == ["image", "inspect"]:
            data = [{"Id": "image-id", "Config": {"User": "1000", "Labels": {}}}]
        elif args[0] == "create":
            return SimpleNamespace(stdout="container-id", stderr="")
        elif args[0] == "inspect":
            data = [{"Id": "container-id", "Config": {
                "Labels": {"sandbox.owner": name}, "User": "1000"},
                "HostConfig": {"NetworkMode": "none", "Privileged": False,
                               "CapAdd": None, "Binds": []},
                "Mounts": [{"Type": "volume", "Destination": "/apps/Downloads", "Name": "owned-volume"}],
                "AppArmorProfile": "synthetic", "State": {"Running": True, "ExitCode": 0}}]
        elif args[0] == "start":
            cleanup = True
            if primary_failure:
                raise subprocess.CalledProcessError(1, command, output="primary output", stderr="primary error")
            return SimpleNamespace(stdout="ok", stderr="")
        else:
            return SimpleNamespace(stdout="", stderr="")
        return SimpleNamespace(stdout=json.dumps(data), stderr="")

    monkeypatch.setattr(check.subprocess, "run", run)
    message = "Container command failed" if primary_failure else "Owned cleanup was not verified"
    with pytest.raises(RuntimeError, match=message):
        check.main()
    receipt = json.loads((output / "receipt.json").read_text())
    assert receipt["cleanup_verified"] is False
    assert receipt["cleanup_error"] == failure_type.__name__
    assert receipt["container"] == "container-id"
    if primary_failure:
        assert (output / "stderr.log").read_text() == "primary error"
    # A failed ownership inspection must never proceed to removal.
    if cleanup_step == "inspect":
        assert not any(args[0] in ("stop", "rm") for args in commands)
