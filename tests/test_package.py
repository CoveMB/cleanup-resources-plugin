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
    def test_file_v5_extracted_review_and_cancel(self):
        import copy
        from test_exact_file import ExactFileFixture
        fixture = ExactFileFixture(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        archive = fixture.base / "file-plugin.zip"
        built = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/build_package.py"), str(archive)], capture_output=True, text=True, timeout=15)
        self.assertEqual(built.returncode, 0, built.stderr)
        extracted = fixture.base / "extracted"
        with zipfile.ZipFile(archive) as package:
            self.assertEqual(len(package.namelist()), 16)
            self.assertIn("skills/task-disk-review/scripts/devspace/exact_file.py", package.namelist())
            self.assertFalse(any(".superpowers" in name or ".git" in name or name.startswith("tests/") for name in package.namelist()))
            package.extractall(extracted)
        scripts = extracted / "skills/task-disk-review/scripts"; cli = scripts / "devspace.py"
        before = fixture.survivors()
        config = fixture.base / "config.json"; config.write_text(json.dumps({"schema_version": 1, "roots": [str(fixture.project)]}))
        manifest = fixture.base / "manifest.json"; manifest.write_text(json.dumps({"schema_version": 1, "resources": []}))
        for mode in ("task", "project", "global"):
            document = copy.deepcopy(fixture.assessment)
            if mode == "global": document["candidates"][0]["path"] = str(fixture.target)
            ap = fixture.base / (mode + "-assessment.json"); ap.write_text(json.dumps(document))
            args = ["review", "--global", "--config", str(config)] if mode == "global" else ["review", "--" + mode, str(fixture.project)]
            pp = fixture.base / (mode + "-plan.json"); mp = fixture.base / (mode + "-manifest.json")
            def invoke(*extra, arguments=args):
                return subprocess.run([sys.executable, "-B", str(cli), *arguments, "--assessment", str(ap), *extra], cwd=fixture.base, capture_output=True, text=True, timeout=20)
            observed = invoke("--json", "--plan-output", str(pp), "--manifest", str(manifest), "--manifest-output", str(mp))
            self.assertIn(observed.returncode, (0, 2), observed.stderr)
            report = json.loads(observed.stdout); self.assertEqual(json.loads(pp.read_text()), report["plan"])
            self.assertEqual(json.loads(mp.read_text()), {"schema_version": 1, "resources": []})
            row = next(r for r in report["candidates"] if r.get("operation") == "file-remove")
            self.assertEqual(row["assessment"], "Eligible"); self.assertIn("parent and siblings preserved", row["effect"])
            text = invoke(); self.assertIn(text.returncode, (0, 2), text.stderr); self.assertIn("parent and siblings preserved", text.stdout)
            code = ("import json,sys; sys.path.insert(0,sys.argv[1]); from devspace import plans,exact_file; "
                    "assert exact_file.__file__.startswith(sys.argv[1]); plans.validate_selection(json.load(open(sys.argv[2])),[sys.argv[3]])")
            selection = subprocess.run([sys.executable, "-B", "-c", code, str(scripts), str(pp), row["id"]], cwd=fixture.base, capture_output=True, text=True, timeout=15)
            self.assertEqual(selection.returncode, 0, selection.stderr)
            cancelled = subprocess.run([sys.executable, "-B", str(cli), "apply", "--plan", str(pp), "--cancel"], cwd=fixture.base, capture_output=True, text=True, timeout=15)
            self.assertEqual(cancelled.returncode, 0, cancelled.stderr); self.assertEqual(json.loads(cancelled.stdout)["outcome"], "cancelled")
            # On supported hosts the real CLI can acquire state before refusing stdin.
            # Bind that state to this owned fixture, never the runner account's home.
            wrapper = ("import sys,runpy; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
                       "from devspace import cleanup; cleanup._state_path=lambda:Path(sys.argv[2]); "
                       "sys.argv=[sys.argv[3],*sys.argv[4:]]; runpy.run_path(sys.argv[0],run_name='__main__')")
            piped = subprocess.run([sys.executable, "-B", "-c", wrapper, str(scripts), str(fixture.base / "private-state"), str(cli), "apply", "--plan", str(pp), "--assessment", str(ap), "--manifest", str(manifest), *(["--config", str(config)] if mode == "global" else []), "--select", row["id"]], input="REMOVE wrong\n", cwd=fixture.base, capture_output=True, text=True, timeout=15)
            self.assertEqual(piped.returncode, 1); self.assertTrue(fixture.target.exists())
            invalid = invoke("--plan-output", str(fixture.target)); self.assertEqual(invalid.returncode, 1)
            self.assertEqual(before, fixture.survivors())

    def test_packaged_container_refusal_preserves_directory_control(self):
        import copy
        import test_plans
        fixture = test_plans.AssessedPlans(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        base = fixture.base
        archive = base / "refusal-plugin.zip"
        built = subprocess.run([str(Path(sys.executable).resolve()), "-B", str(ROOT / "scripts/build_package.py"), str(archive)],
                               capture_output=True, text=True, timeout=15)
        self.assertEqual(built.returncode, 0, built.stderr)
        extracted = base / "extracted"
        with zipfile.ZipFile(archive) as package:
            self.assertFalse(any(".superpowers" in name or name.startswith("tests/") for name in package.namelist()))
            package.extractall(extracted)
        scripts = extracted / "skills/task-disk-review/scripts"
        cli = scripts / "devspace.py"
        # This extracted invocation's explicit absent-tool fixture is separate
        # from normal suite discovery; no provider executable is manufactured.
        empty_tools = base / "no-provider-tools"; empty_tools.mkdir()
        environment = {**os.environ, "PATH": str(empty_tools)}
        reason = "Container removal unavailable: complete absence of writable changes cannot be established; preserve this container."
        before = fixture.bytes()
        for version in (3, 4):
            assessment = copy.deepcopy(fixture.assessment); assessment["schema_version"] = version
            for item in assessment["candidates"]: item["operation"] = "directory-remove"
            assessment["candidates"].append({"operation": "docker-container-remove", "docker": {
                "endpoint": "unix://" + str(base / "nonexistent-daemon.sock"), "id": "a" * 64},
                "category": "container", "purpose": "fictional old released container"})
            ap, pp = base / f"assessment-v{version}.json", base / f"plan-v{version}.json"
            ap.write_text(json.dumps(assessment))
            arguments = ["review", "--project", str(fixture.project), "--assessment", str(ap), "--hold", str(fixture.project / "legacy")]
            def invoke(*extra):
                return subprocess.run([str(Path(sys.executable).resolve()), "-B", str(cli), *arguments, *extra],
                                      env=environment, cwd=base, capture_output=True, text=True, timeout=20)
            control_path = base / f"control-v{version}.json"
            control_path.write_text(json.dumps({**assessment, "candidates": assessment["candidates"][:-1]}))
            control = invoke("--assessment", str(control_path), "--json")
            self.assertIn(control.returncode, (0, 2), control.stderr)
            observed = invoke("--json", "--plan-output", str(pp))
            # Absent optional Git may make metadata coverage partial (exit 2);
            # an Unavailable container must not invent an additional exit rule.
            self.assertEqual(observed.returncode, control.returncode, observed.stderr)
            report = json.loads(observed.stdout)
            container = next(row for row in report["candidates"] if row.get("operation") == "docker-container-remove")
            self.assertEqual((container["assessment"], container["reason"], container["references"]), ("Unavailable", reason, {}))
            self.assertNotIn("native", container); self.assertNotIn("observation", container)
            directory = next(row for row in report["candidates"] if row["path"] == str(fixture.project / "A"))
            self.assertEqual(directory["assessment"], "Eligible")
            held = next(row for row in report["candidates"] if row["path"] == str(fixture.project / "legacy"))
            self.assertEqual(held["assessment"], "Keep")
            unknown = next(row for row in report["candidates"] if row["path"] == str(fixture.project / "D"))
            self.assertEqual(unknown["assessment"], "Review")
            self.assertEqual(json.loads(pp.read_text()), report["plan"])
            text = invoke()
            self.assertEqual(text.returncode, control.returncode, text.stderr); self.assertIn(reason, text.stdout)
            # Exercise the extracted reader, rather than the test process's imports.
            selection = "import json,sys; sys.path.insert(0,sys.argv[1]); from devspace import plans; plans.validate_selection(json.load(open(sys.argv[2])),[sys.argv[3]])"
            for identifier, exit_code in ((container["id"], 1), (directory["id"], 0)):
                selected = subprocess.run([str(Path(sys.executable).resolve()), "-B", "-c", selection, str(scripts), str(pp), identifier],
                                          env=environment, cwd=base, capture_output=True, text=True, timeout=15)
                self.assertEqual(selected.returncode, exit_code, selected.stderr)
                if exit_code: self.assertIn("unknown or ineligible selection", selected.stderr)
            assessment["candidates"][-1]["docker"]["command"] = "forbidden"
            ap.write_text(json.dumps(assessment))
            invalid = invoke("--json")
            self.assertEqual(invalid.returncode, 1); self.assertEqual(invalid.stdout, "")
        after = fixture.bytes()
        for name, payload in before.items(): self.assertEqual(after[name], payload)

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



    def test_git_lineage_integration_extracted_cli_contract(self):
        import test_git_inventory
        fixture = test_git_inventory.GitInventory()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        linked, request, record = fixture.integration_fixture("squash")
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
            self.assertIs(report["git_lineage"]["patch_equivalence"]["equal"], True)
            self.assertEqual(report["git_lineage"]["patch_equivalence"]["method"], "exact-tree-entry-delta")
            self.assertIs(report["git_lineage"]["ancestry"]["head_in_destination"], False)
            self.assertEqual(report["git_lineage"]["integration"]["squash_provenance"], "unverified")
            self.assertEqual(report["git_lineage"]["integration"]["current_content_preservation"], "unestablished")
            for key in ("candidates", "scope_roots", "plan", "size"):
                self.assertEqual(report[key], json.loads(control.stdout)[key], key)
            text = invoke(*scope, "--git-lineage", str(request_file))
            self.assertIn("Git lineage", text.stdout)
            self.assertIn("not_established", text.stdout)
            self.assertIn('"method": "exact-tree-entry-delta"', text.stdout)
            self.assertIn('"squash_provenance": "unverified"', text.stdout)
            self.assertIn('"head_in_destination": false', text.stdout)
            # A skipped extracted-CLI observation still truthfully retains its requested claim.
            request_file.write_text(json.dumps({**request, "path": str(base / "unmatched-checkout")}))
            skipped = invoke(*scope, "--assessment", str(assessment_file), "--git-lineage", str(request_file), "--json")
            self.assertEqual(skipped.returncode, 2, skipped.stderr)
            skipped_report = json.loads(skipped.stdout)
            lineage = skipped_report["git_lineage"]
            self.assertEqual(lineage["status"], "not_examined")
            self.assertEqual(lineage["integration"]["status"], "unavailable")
            self.assertEqual(lineage["integration"]["source_commit"], request["integration"]["source_commit"])
            self.assertEqual(lineage["integration"]["squash_provenance"], "unverified")
            self.assertIsNone(lineage["patch_equivalence"]["equal"])
            skipped_text = invoke(*scope, "--git-lineage", str(request_file))
            self.assertIn('"squash_provenance": "unverified"', skipped_text.stdout)
            self.assertIn('"source_commit": "'+request["integration"]["source_commit"]+'"', skipped_text.stdout)
            for key in ("candidates", "scope_roots", "plan", "size"):
                self.assertEqual(skipped_report[key], json.loads(control.stdout)[key], key)
            request_file.write_text(json.dumps(request))
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
