"""Run the sandbox check in one owned, isolated Docker container and retain proof."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
# Fixed executable/argument vectors; no shell or credentials.
import subprocess  # nosec B404
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
PROFILE_SHA = "cc3e61cabda6bbc1e53e54d27ba4d55a9d3be829b6dd1a596f4a7b31b1cc7849"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--expect", choices=("active", "disabled", "blocked"), default="active")
    parser.add_argument("--force-sandbox", action="store_true")
    parser.add_argument("--runtime-regression", action="store_true",
                        help="Run the existing image/UI/mock-portal checks instead")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.runtime_regression and args.force_sandbox:
        parser.error("--force-sandbox applies only to the baseline sandbox check")
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("Docker is required")
    # Pin the local control plane; an ambient DOCKER_HOST cannot select production.
    command = [docker, "--host", "unix:///var/run/docker.sock"]

    def run(argv, timeout=30):
        return subprocess.run(command + argv,  # nosec B603
                              check=True, capture_output=True,
                              text=True, timeout=timeout)

    image = json.loads(run(["image", "inspect", args.image]).stdout)[0]
    if image['Config']['User'].split(':')[0] in ('', '0', 'root'):
        raise RuntimeError('Nonroot image required')
    if args.profile:
        if not (hashlib.sha256(args.profile.read_bytes()).hexdigest() == PROFILE_SHA):
            raise RuntimeError('Profile mismatch')
    args.output.mkdir(parents=True, exist_ok=False)
    name = f"billcollector-sandbox-{uuid4().hex}"
    identifier = None
    volumes = []
    receipt = {"image": image["Id"], "revision": image["Config"]["Labels"].get(
        "org.opencontainers.image.revision"), "expect": args.expect,
        "forced": args.force_sandbox, "profile_sha256": PROFILE_SHA if args.profile else None,
        "cleanup_verified": False}
    try:
        options = ["create", "--name", name, "--label", f"sandbox.owner={name}",
                   "--network", "none", "--shm-size", "256m", "--memory", "1g",
                   "--cpus", "2", "--pids-limit", "512"]
        if args.profile:
            options += ["--security-opt", f"seccomp={args.profile.resolve()}"]
        options += ["--entrypoint", "python3", image["Id"]]
        if args.runtime_regression:
            options += ["/checks/check_image_runtime.py"]
        else:
            options += ["/sandbox-check.py", "--expect", args.expect]
        if args.force_sandbox:
            options += ["--force-sandbox"]
        identifier = run(options).stdout.strip()
        details = json.loads(run(["inspect", identifier]).stdout)[0]
        if not (details['Id'] == identifier and details['Config']['Labels']['sandbox.owner'] == name):
            raise RuntimeError('Synthetic check failed')
        host = details["HostConfig"]
        if not (host['NetworkMode'] == 'none' and (not host['Privileged']) and (not host['CapAdd'])):
            raise RuntimeError('Synthetic check failed')
        if host['Binds']:
            raise RuntimeError('Synthetic check failed')
        if not all(m['Type'] == 'volume' and m['Destination'] == '/apps/Downloads'
                   for m in details['Mounts']):
            raise RuntimeError('Unexpected runtime mount')
        volumes = [mount['Name'] for mount in details['Mounts']]
        receipt.update(container=identifier, apparmor=details["AppArmorProfile"],
                       user=details["Config"]["User"])
        if args.runtime_regression:
            run(["cp", str(ROOT / "tests"), f"{identifier}:/checks"])
        else:
            run(["cp", str(ROOT / "tests/check_chromium_sandbox.py"), f"{identifier}:/sandbox-check.py"])
        result = run(["start", "-a", identifier], timeout=900 if args.runtime_regression else 120)
        (args.output / "stdout.log").write_text(result.stdout)
        (args.output / "stderr.log").write_text(result.stderr)
        state = json.loads(run(["inspect", identifier]).stdout)[0]["State"]
        receipt["exit_code"] = state["ExitCode"]
        if not (state['ExitCode'] == 0):
            raise RuntimeError('Container check failed; inspect retained logs')
        print(result.stdout, end="")
    except subprocess.CalledProcessError as error:
        (args.output / "stdout.log").write_text(error.stdout or "")
        (args.output / "stderr.log").write_text(error.stderr or "")
        raise RuntimeError("Container command failed; inspect retained logs") from None
    except subprocess.TimeoutExpired as error:
        for stream in ("stdout", "stderr"):
            value = getattr(error, stream) or b""
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            (args.output / f"{stream}.log").write_text(value)
        raise RuntimeError("Container check timed out; inspect retained logs") from None
    finally:
        primary_error = sys.exception()
        cleanup_error = None
        try:
            if identifier:
                details = json.loads(run(["inspect", identifier]).stdout)[0]
                if not (details['Id'] == identifier and details['Config']['Labels']['sandbox.owner'] == name):
                    raise RuntimeError('Synthetic check failed')
                receipt["exit_code"] = details["State"]["ExitCode"]
                if details["State"]["Running"]:
                    run(["stop", "--time", "5", identifier])
                # The label/ID check confines removal to this invocation and its anonymous volume.
                run(["rm", "--volumes", identifier])
                receipt["cleanup_verified"] = not run([
                    "ps", "-a", "--filter", f"name=^/{name}$", "--format", "{{.ID}}"]).stdout.strip()
                receipt["volumes_removed"] = all(volume not in run([
                    "volume", "ls", "--filter", f"name={volume}", "--format", "{{.Name}}"
                ]).stdout.splitlines() for volume in volumes)
                receipt["cleanup_verified"] = receipt["cleanup_verified"] and receipt["volumes_removed"]
        except Exception as error:
            cleanup_error = error
            receipt["cleanup_verified"] = False
            receipt["cleanup_error"] = type(error).__name__
        finally:
            (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        if not receipt["cleanup_verified"] and primary_error is None:
            raise RuntimeError("Owned cleanup was not verified; inspect receipt.json") from cleanup_error


if __name__ == "__main__":
    main()
