"""Build/extract/invoke the actual deliverable; no private plans should ship."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class PackageInvocation(unittest.TestCase):
    def test_deliverable_excludes_private_material_and_runs_independently(self):
        with tempfile.TemporaryDirectory(prefix="task-review-package-") as temporary:
            base = Path(temporary).resolve()
            archive = base / "plugin.zip"
            result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/build_package.py"), str(archive)],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(archive) as package:
                members = package.namelist()
                self.assertIn("plugin.json", members)
                self.assertEqual(len([name for name in members if name.endswith("SKILL.md")]), 1)
                self.assertFalse(any(part in name for name in members
                                     for part in (".git", ".local", "plan.md", "handoff", "tests/", "__pycache__")))
                for name in members:
                    payload = package.read(name)
                    self.assertNotIn(b"/Users/", payload, name)
                    self.assertNotIn(b"SYNTHETIC_SECRET_PAYLOAD", payload, name)
                package.extractall(base / "installed")
            task = base / "task"
            task.mkdir()
            (task / "artifact").write_bytes(b"12345")
            invocation = subprocess.run([sys.executable, "-B", str(base / "installed/skills/task-disk-review/scripts/devspace.py"),
                                         "review", "--task", str(task), "--json"],
                                        cwd=base, text=True, capture_output=True, timeout=15)
            self.assertEqual(invocation.returncode, 0, invocation.stderr)
            report = json.loads(invocation.stdout)
            self.assertEqual(report["size"]["logical_bytes"], 5)
            self.assertEqual(report["entries"][0]["path"], "artifact")
            self.assertEqual((task / "artifact").read_bytes(), b"12345")
            self.assertFalse(list((base / "installed").rglob("__pycache__")))
            project = subprocess.run([sys.executable, "-B", str(base / "installed/skills/task-disk-review/scripts/devspace.py"),
                                      "review", "--project", str(task), "--json", "--plan-output", str(base / "review-plan.json")],
                                     cwd=base, text=True, capture_output=True, timeout=15)
            self.assertEqual(project.returncode, 0, project.stderr)
            report = json.loads(project.stdout)
            saved = json.loads((base / "review-plan.json").read_text())
            self.assertEqual(saved, report["plan"])
            self.assertEqual(report["scope"]["mode"], "project")
            self.assertEqual(saved["kind"], "frozen-review-not-authorization")
            self.assertEqual((task / "artifact").read_bytes(), b"12345")


if __name__ == "__main__":
    unittest.main()
