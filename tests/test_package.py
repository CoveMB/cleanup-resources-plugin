"""Build/extract/invoke the actual deliverable; no private plans should ship."""
import json
import os
import shlex
import shutil
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



    def test_git_lineage_extracted_cli_contract(self):
        import test_git_inventory
        fixture = test_git_inventory.GitInventory()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        linked, request, record = fixture.lineage_fixture(linked_name="linked")
        base = fixture.fixture
        archive = base / "plugin.zip"
        build = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/build_package.py"), str(archive)],
                               capture_output=True, timeout=15)
        self.assertEqual(build.returncode, 0, build.stderr)
        with zipfile.ZipFile(archive) as package: package.extractall(base / "installed")
        cli = base / "installed/skills/task-disk-review/scripts/devspace.py"
        request_file = base / "lineage.json"
        request_file.write_text(json.dumps(request))
        config_file = base / "config.json"
        config_file.write_text(json.dumps({"schema_version": 1, "roots": [str(fixture.project)]}))
        # A real PATH wrapper reaches subprocesses; process-local which patches do not.
        binary = base / "bin"
        binary.mkdir()
        wrapper = binary / "git"
        executable = shutil.which("git")
        # fixture's which patch returns its safe wrapper, itself targeting real Git.
        wrapper.write_text("#!/bin/sh\nGIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null exec "
                           + shlex.quote(executable) + ' "$@"\n')
        wrapper.chmod(0o700)
        environment = {**fixture.environment, "PATH": str(binary)+os.pathsep+os.environ["PATH"]}
        def invoke(*args):
            return subprocess.run([sys.executable, "-B", str(cli), "review", *args],
                                  env=environment, cwd=base, capture_output=True, text=True, timeout=30)
        import test_plans
        assessed = test_plans.AssessedPlans()
        assessed.setUp()
        self.addCleanup(assessed.doCleanups)
        # Move the independently generated project under the bound repository, leaving retained evidence outside it.
        assessed.project.rename(fixture.project / "generated")
        assessed.project = fixture.project / "generated"
        for specification in assessed.assessment["candidates"]:
            specification["path"] = str(assessed.project / specification["path"])
        assessment_file = base / "assessment.json"
        assessment_file.write_text(json.dumps(assessed.assessment))
        preserved = (test_git_inventory.lineage_snapshot(fixture.project), test_git_inventory.lineage_snapshot(linked),
                     test_git_inventory.lineage_snapshot(assessed.records))
        for scope in (("--project", str(fixture.project)), ("--global", "--config", str(config_file))):
            control = invoke(*scope, "--assessment", str(assessment_file), "--json")
            self.assertTrue(any(row["assessment"] == "Eligible" for row in json.loads(control.stdout)["candidates"]))
            observed = invoke(*scope, "--assessment", str(assessment_file), "--git-lineage", str(request_file), "--json")
            self.assertEqual(observed.returncode, control.returncode, observed.stderr)
            self.assertTrue(observed.stdout, observed.stderr)
            report = json.loads(observed.stdout)
            self.assertEqual(report["git_lineage"]["status"], "observed", report["git_lineage"])
            for key in ("candidates", "scope_roots", "plan", "size"):
                self.assertEqual(report[key], json.loads(control.stdout)[key], key)
            text = invoke(*scope, "--git-lineage", str(request_file))
            self.assertIn("Git lineage", text.stdout)
            self.assertIn("not_established", text.stdout)
        refused = invoke("--task", str(linked), "--git-lineage", str(request_file), "--json")
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stdout, "")
        # Stall only the extra phase: all ordinary inventory remains usable.
        wrapper.write_text("#!/bin/sh\ncase \" $* \" in *' --no-replace-objects '*) sleep 1;; esac\n"
                           + "GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null exec " + shlex.quote(executable) + ' "$@"\n')
        control = invoke("--project", str(fixture.project), "--timeout", "0.5", "--assessment", str(assessment_file), "--json")
        exhausted = invoke("--project", str(fixture.project), "--timeout", "0.5", "--assessment", str(assessment_file), "--git-lineage", str(request_file), "--json")
        self.assertEqual(exhausted.returncode, 2, exhausted.stderr)
        result = json.loads(exhausted.stdout)
        self.assertNotEqual(result["git_lineage"]["status"], "observed")
        for key in ("candidates", "scope_roots", "plan", "size"):
            self.assertEqual(result[key], json.loads(control.stdout)[key], key)
        self.assertEqual((test_git_inventory.lineage_snapshot(fixture.project), test_git_inventory.lineage_snapshot(linked),
                          test_git_inventory.lineage_snapshot(assessed.records)), preserved)


if __name__ == "__main__":
    unittest.main()
