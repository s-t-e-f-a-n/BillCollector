"""Use a scratch build with fake canaries to check the actual Docker context."""

import argparse
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
        "apps/profiles/account/Cookies", "apps/browser/profile/Default/Cookies",
        "apps/Downloads/invoice.pdf", "apps/.venv/lib/private.py",
        "apps/__pycache__/private.pyc", "apps/nested/.env",
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
        subprocess.run(
            ["docker", "build", "--quiet", "--output", f"type=local,dest={output}", str(context)],
            check=True, capture_output=True, text=True,
        )
        for name in retained:
            if not (output / name).is_file():
                raise RuntimeError(f"Required source excluded: {name}")
        for name in excluded:
            if (output / name).exists():
                raise RuntimeError(f"Private runtime artifact entered build: {name}")
    print(f"Docker context: {len(excluded)} private canaries excluded, {len(retained)} source files retained")


if __name__ == "__main__":
    main()
