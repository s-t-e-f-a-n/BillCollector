"""Exercise launcher argument/permission behavior without a Docker daemon."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class NonrootWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "apps").mkdir()
        (self.root / "bin").mkdir()
        (self.root / "apps/.env").write_text("SYNTHETIC_VALUE=private\n")
        shutil.copy2(ROOT / "BillCollector.sh", self.root / "BillCollector.sh")
        scripts = {
            "id": '#!/bin/sh\ncase "$1" in -u) echo "$WRAPPER_TEST_UID";; -g) echo 2345;; -G) echo "2345 100 4567";; esac\n',
            "docker": '#!/usr/bin/env python3\nimport json,os,sys\nopen(os.environ["WRAPPER_CAPTURE"],"w").write(json.dumps(sys.argv[1:]))\n',
        }
        for name, source in scripts.items():
            path = self.root / "bin" / name
            path.write_text(source)
            path.chmod(0o700)
        self.capture = self.root / "arguments.json"
        self.env = dict(os.environ, PATH=f'{self.root / "bin"}:{os.environ["PATH"]}',
                        WRAPPER_TEST_UID="1234", WRAPPER_CAPTURE=str(self.capture))

    def run_wrapper(self):
        return subprocess.run(["bash", str(self.root / "BillCollector.sh"), "bc_test.ini", "--service", "synthetic"],
                              cwd=self.root, env=self.env, capture_output=True, text=True, check=False)

    def test_maps_uid_paths_env_and_quoted_arguments(self):
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads(self.capture.read_text())
        self.assertEqual(args[args.index("--user") + 1], "1234:2345")
        groups = [args[index + 1] for index, arg in enumerate(args) if arg == "--group-add"]
        self.assertEqual(groups, ["100", "4567"])
        self.assertEqual(args[args.index("--tmpfs") + 1], "/apps/runtime:uid=1234,gid=2345,mode=0700")
        self.assertIn(f"{self.root / 'apps/.env'}:/apps/.env:ro", args)
        self.assertNotIn("--env-file", args)
        self.assertEqual(args[-3:], ["bc_test.ini", "--service", "synthetic"])
        self.assertNotIn("private", result.stdout + result.stderr + self.capture.read_text())
        self.assertEqual((self.root / "apps/db").stat().st_mode & 0o777, 0o700)

    def test_refuses_missing_env_without_creating_a_directory(self):
        (self.root / "apps/.env").unlink()
        self.assertNotEqual(self.run_wrapper().returncode, 0)
        self.assertFalse(self.capture.exists())
        self.assertFalse((self.root / "apps/.env").exists())
        self.assertFalse((self.root / "apps/db").exists())
        self.assertFalse((self.root / "apps/Downloads").exists())

    def test_refuses_root_before_docker(self):
        self.env["WRAPPER_TEST_UID"] = "0"
        self.assertNotEqual(self.run_wrapper().returncode, 0)
        self.assertFalse(self.capture.exists())

    def test_preserves_download_symlink_and_existing_directory_modes(self):
        output = self.root / "trusted-output"
        output.mkdir(mode=0o750)
        (self.root / "apps/Downloads").symlink_to(output)
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "apps/Downloads").is_symlink())
        self.assertEqual(output.stat().st_mode & 0o777, 0o750)

    def test_refuses_broken_output_symlink_without_changing_it(self):
        output = self.root / "apps/Downloads"
        output.symlink_to(self.root / "missing")
        self.assertNotEqual(self.run_wrapper().returncode, 0)
        self.assertTrue(output.is_symlink())
        self.assertFalse(self.capture.exists())


if __name__ == "__main__":
    unittest.main()
