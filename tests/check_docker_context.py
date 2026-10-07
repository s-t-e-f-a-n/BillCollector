"""Check the actual Docker context with synthetic files.

Requires Docker with BuildKit enabled for the local output exporter.
No real checkout data or registry access is used.
"""

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SENTINEL = "SYNTHETIC_PRIVATE_CONTEXT_CANARY"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dockerignore", type=Path, default=ROOT / ".dockerignore")
    args = parser.parse_args()
    excluded = (
        "apps/.env", "apps/.env.local", "apps/bc.log", "apps/.bc_ui_run.json",
        "apps/.bc.lock", "apps/recipes_playwright/.code/recorded.py", "apps/db/bc.db",
        "apps/browser/profile/Default/Cookies",
        "apps/Downloads/invoice.pdf", "apps/.venv/lib/private.py",
        "apps/__pycache__/private.pyc", "apps/nested/.env",
        # Root deploy config, git metadata, rotated logs and other .gitignore'd artifacts.
        ".env", ".git/config", "apps/bc.log.1", "apps/bc_default.ini.bak", "apps/invoice_page.html",
        "apps/chrome-linux64/chrome", "apps/.pytest_cache/state",
    )
    retained = (
        "apps/BillCollector.py", "apps/requirements.txt", "apps/.env.example",
        "apps/recipes_playwright/recipe-pw__sample.yaml", "tests/mock_portal/templates/login.html",
    )
    with tempfile.TemporaryDirectory() as directory:
        context = Path(directory) / "context"
        output = Path(directory) / "output"
        context.mkdir()
        shutil.copy2(args.dockerignore, context / ".dockerignore")
        (context / "Dockerfile").write_text("FROM scratch\nCOPY . /\n", encoding="utf-8")
        for name in excluded + retained:
            path = context / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(SENTINEL if name in excluded else "synthetic source\n", encoding="utf-8")
        # The local output exporter requires BuildKit; enforce it explicitly so
        # the check does not depend on the daemon's default builder.
        env = os.environ.copy()
        env["DOCKER_BUILDKIT"] = "1"
        # Resolve the full docker path to avoid the partial-executable-path
        # flags (Ruff S607 / bandit B607).
        docker_bin = shutil.which("docker") or "docker"
        build = subprocess.run(
            [docker_bin, "build", "--quiet", "--output", f"type=local,dest={output}", str(context)],
            capture_output=True, text=True, env=env,
        )
        if build.returncode != 0:
            raise RuntimeError(f"docker build failed ({build.returncode}):\n{build.stderr}")
        failures = []
        for name in retained:
            if not (output / name).is_file():
                failures.append(f"Required source excluded: {name}")
        for name in excluded:
            if (output / name).exists():
                failures.append(f"Private runtime artifact entered build: {name}")
        if failures:
            raise RuntimeError("Dockerignore validation failed:\n" + "\n".join(failures))
    print(f"Docker context: {len(excluded)} private canaries excluded, {len(retained)} source files retained")


if __name__ == "__main__":
    main()
