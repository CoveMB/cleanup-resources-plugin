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

            config = base / "global-config.json"
            config.write_text(json.dumps({"schema_version": 1, "roots": [str(task)]}))
            global_review = subprocess.run([sys.executable, "-B", str(base / "installed/skills/task-disk-review/scripts/devspace.py"),
                                           "review", "--global", "--config", str(config), "--json"],
                                          cwd=base, text=True, capture_output=True, timeout=15)
            self.assertEqual(global_review.returncode, 2, global_review.stderr)
            self.assertEqual(global_review.stderr, "")
            report = json.loads(global_review.stdout)
            self.assertEqual(report["scope"]["mode"], "global")
            self.assertEqual(report["size"]["logical_bytes"], 5)
            self.assertEqual(report["coverage"]["unconfigured"], 3)
            self.assertIsNone(report["retention"]["desktop"]["effective"])
            self.assertEqual((task / "artifact").read_bytes(), b"12345")

            evidence = task / "evidence"
            (evidence / ".venv").mkdir(parents=True)
            original = evidence / "failure.txt"
            original.write_bytes(b"original attempt")
            captured = subprocess.run([sys.executable, "-B", str(base / "installed/skills/task-disk-review/scripts/devspace.py"),
                                       "review", "--task", str(task), "--evidence-warn-bytes", "1",
                                       "--evidence-explain-bytes", "2"], cwd=base, text=True, capture_output=True, timeout=15)
            self.assertEqual(captured.returncode, 0, captured.stderr)
            self.assertIn("explain retained size", captured.stdout)
            self.assertIn("possible nested installed environment", captured.stdout)
            self.assertIn("Optional for development/evidence workflows, including incremental planning", captured.stdout)
            self.assertEqual(original.read_bytes(), b"original attempt")
            self.assertEqual((task / "artifact").read_bytes(), b"12345")


if __name__ == "__main__":
    unittest.main()
