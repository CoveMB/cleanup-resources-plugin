"""Global coverage contracts; providers are synthetic, never real daemon probes."""
import copy
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/task-disk-review/scripts"))
from devspace import plans
from devspace.git_inventory import InspectionUnavailable, InspectionCancelled
import test_plans


class GlobalCoverage(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="global-coverage-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "development"
        self.root.mkdir()
        (self.root / "output").mkdir()
        (self.root / "output/data").write_bytes(b"12345")
        self.config = {"schema_version": 1, "roots": [str(self.root)]}

    def review(self, **options):
        return plans.review_scope(self.config, mode="global", **options)

    def locations(self, report, kind):
        return [row for row in report["locations"] if row["kind"] == kind]

    def test_unconfigured_and_missing_coverage_never_become_zero_success(self):
        self.config["roots"].append(str(self.base / "missing"))
        report = self.review()
        self.assertFalse(report["coverage"]["complete"])
        self.assertEqual([row["status"] for row in self.locations(report, "development")],
                         ["examined", "unavailable"])
        for kind in ("codex-worktrees", "package-storage", "docker"):
            self.assertEqual(self.locations(report, kind)[0]["status"], "unconfigured")
        self.assertEqual(report["retention"]["cli"]["effective"], None)
        self.assertEqual(report["retention"]["desktop"]["effective"], None)
        self.assertEqual(report["size"]["logical_bytes"], 5)

    def test_nested_roots_and_disjoint_hardlinks_count_once(self):
        second = self.base / "other"
        second.mkdir()
        os.link(self.root / "output/data", second / "same")
        self.config["roots"] += [str(self.root / "output"), str(second)]
        report = self.review()
        self.assertEqual(report["size"]["logical_bytes"], 5)
        self.assertEqual(report["size"]["unique_files"], 1)
        self.assertEqual(report["size"]["duplicate_hardlinks"], 1)
        self.assertIn("skipped", [row["status"] for row in self.locations(report, "development")])
        self.assertEqual(len(report["scope_roots"]), 3)
        self.assertEqual(len({row["id"] for row in report["candidates"]}), len(report["candidates"]))

    def test_provider_storage_excluded_from_development_and_plan(self):
        managed = self.root / "output"
        self.config["package_storage"] = [str(managed)]
        report = self.review(assessment={"schema_version": 1, "references": {}, "candidates": [
            {"path": str(managed), "category": "output"}]})
        row = next(row for row in report["candidates"] if row["path"] == str(managed))
        self.assertEqual(row["assessment"], "Keep")
        self.assertEqual(report["size"]["logical_bytes"], 0)
        provider = self.locations(report, "package-storage")[0]
        self.assertEqual(provider["size"]["logical_bytes"], 5)
        self.assertEqual(provider["assessment"], "Review")
        self.assertIn(str(managed), report["plan"]["policy"]["holds"])
        with self.assertRaises(ValueError):
            plans.write_plan(managed / "plan.json", report["plan"])
        with self.assertRaises(ValueError):
            plans.validate_selection(report["plan"], [row["id"]])

    def test_plan_output_cannot_write_into_provider_outside_development_roots(self):
        storage = self.base / "provider-storage"
        storage.mkdir()
        self.config["package_storage"] = [str(storage)]
        report = self.review()
        with self.assertRaises(ValueError):
            plans.write_plan(storage / "plan.json", report["plan"])
        self.assertFalse((storage / "plan.json").exists())

    def test_global_manifest_output_protects_configured_and_provider_roots(self):
        skipped = self.base / "excluded-development"
        storage = self.base / "package-store"
        worktrees = self.base / "managed-worktrees"
        for path in (skipped, storage, worktrees):
            path.mkdir()
        self.config.update(roots=[str(self.root), str(skipped)], exclusions=[str(skipped)],
                           package_storage=[str(storage)], codex_worktrees=[str(worktrees)])
        config = self.base / "config.json"
        config.write_text(json.dumps(self.config))
        manifest = self.base / "manifest.json"
        manifest.write_text(json.dumps({"schema_version": 1, "resources": []}))
        before = {str(path): path.read_bytes() for path in self.base.rglob("*") if path.is_file()}
        for root in (self.root, skipped, storage, worktrees):
            with self.subTest(root=root):
                destination = root / "manifest-output.json"
                result = subprocess.run([sys.executable, "-B", str(ROOT / "skills/task-disk-review/scripts/devspace.py"),
                    "review", "--global", "--config", str(config), "--manifest", str(manifest),
                    "--manifest-output", str(destination)], capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertFalse(destination.exists())
        self.assertEqual({str(path): path.read_bytes() for path in self.base.rglob("*") if path.is_file()}, before)

    def test_host_mismatch_refuses_all_probes(self):
        self.config.update(host_identity="different-host", docker_host="unix:///not-probed.sock")
        with patch("devspace.global_inventory.inventory_docker", side_effect=AssertionError("probe")):
            report = self.review()
        self.assertEqual(report["size"]["logical_bytes"], 0)
        self.assertTrue(all(row["status"] in {"skipped", "unconfigured"} for row in report["locations"]))
        self.assertFalse(report["coverage"]["complete"])

    def test_denied_root_distinct_from_unconfigured_and_failure_isolated(self):
        denied = self.base / "denied"
        denied.mkdir()
        self.config["roots"].insert(0, str(denied))
        real = os.open
        def open_path(path, *args, **kwargs):
            if path == "denied" or Path(path) == denied:
                raise PermissionError(13, "private diagnostic")
            return real(path, *args, **kwargs)
        with patch("os.open", side_effect=open_path), patch("devspace.review.descriptor_traversal_available", return_value=True):
            report = self.review()
        self.assertEqual(self.locations(report, "development")[0]["status"], "inaccessible")
        self.assertEqual(self.locations(report, "development")[1]["status"], "examined")
        self.assertNotIn("private diagnostic", json.dumps(report))

    def test_entry_budget_and_cancellation_stop_later_work(self):
        other = self.base / "other"
        other.mkdir()
        (other / "unexamined").write_bytes(b"bytes")
        self.config["roots"].append(str(other))
        limited = self.review(max_entries=1)
        self.assertLessEqual(limited["coverage"]["examined"], 1)
        self.assertEqual(self.locations(limited, "development")[-1]["status"], "skipped")
        cancelled = self.review(cancelled=lambda: True)
        self.assertTrue(cancelled["cancelled"])
        self.assertEqual(cancelled["coverage"]["examined"], 0)

    def test_remote_docker_refused_without_command_and_unknown_vm_allocation(self):
        from devspace.global_inventory import inventory_docker
        with patch("devspace.global_inventory.run_readonly", side_effect=AssertionError("command")):
            row = inventory_docker("ssh://remote", timeout=1)
        self.assertEqual(row["status"], "skipped")
        self.assertEqual(row["locality"], "remote-or-unsupported")
        self.assertIsNone(row["host_allocated_bytes"])
        self.assertIsNone(row["vm_maximum_bytes"])

    def test_docker_success_selects_summary_and_never_adds_provider_bytes(self):
        self.config["docker_host"] = "unix:///synthetic/docker.sock"
        payload = b"\n".join(json.dumps({"Type": kind, "TotalCount": "2", "Active": "1", "Size": "8GB", "Reclaimable": "4GB (50%)", "Names": "SYNTHETIC_SECRET_PAYLOAD"}).encode()
                              for kind in ("Images", "Containers", "Local Volumes", "Build Cache"))
        with patch("devspace.global_inventory.shutil.which", return_value="/synthetic/docker"), \
             patch("devspace.global_inventory.run_readonly", return_value=payload) as runner:
            report = self.review()
        docker = self.locations(report, "docker")[0]
        self.assertEqual(docker["status"], "examined")
        self.assertEqual(docker["usage"][0]["Size"], "8GB")
        self.assertEqual(report["size"]["logical_bytes"], 5)
        self.assertNotIn("SYNTHETIC_SECRET_PAYLOAD", json.dumps(report))
        command = runner.call_args.args[0]
        self.assertEqual(command, ["/synthetic/docker", "--host", self.config["docker_host"],
                                   "system", "df", "--format", "{{json .}}"])
        self.assertFalse(any(key.startswith("DOCKER_") for key in runner.call_args.args[2]))

    def test_docker_unavailable_refusal_timeout_and_cancel_keep_other_results(self):
        from devspace.global_inventory import inventory_docker
        with patch("devspace.global_inventory.shutil.which", return_value=None):
            self.assertEqual(inventory_docker("unix:///synthetic", timeout=1)["status"], "unavailable")
        self.config["docker_host"] = "unix:///synthetic"
        for error in (InspectionUnavailable("refused"), InspectionUnavailable("time limit")):
            with self.subTest(error=str(error)), \
                 patch("devspace.global_inventory.shutil.which", return_value="docker"), \
                 patch("devspace.global_inventory.run_readonly", side_effect=error):
                report = self.review()
                self.assertEqual(self.locations(report, "docker")[0]["status"], "unavailable")
                self.assertEqual(report["size"]["logical_bytes"], 5)
                self.assertFalse(report["coverage"]["complete"])
        with patch("devspace.global_inventory.shutil.which", return_value="docker"), \
             patch("devspace.global_inventory.run_readonly", side_effect=InspectionCancelled("cancelled")):
            self.assertTrue(self.review()["cancelled"])

    def test_actual_bounded_provider_process_success_refusal_timeout_output_limit_and_cancel(self):
        from devspace.global_inventory import inventory_docker
        executable = self.base / "synthetic-docker"
        def script(body):
            executable.write_text("#!" + sys.executable + "\nimport sys, time, os\n" + body)
            executable.chmod(0o755)
        endpoint = "unix:///synthetic/socket"
        payload = "\n".join(json.dumps({"Type": kind, "TotalCount": "1", "Active": "0", "Size": "2GB", "Reclaimable": "2GB (100%)"})
                            for kind in ("Images", "Containers", "Local Volumes", "Build Cache"))
        script("assert sys.argv[1:] == ['--host', 'unix:///synthetic/socket', 'system', 'df', '--format', '{{json .}}']\n"
               "assert 'DOCKER_CONTEXT' not in os.environ\nprint(" + repr(payload) + ")\n")
        with patch("devspace.global_inventory.shutil.which", return_value=str(executable)), \
             patch.dict(os.environ, {"DOCKER_CONTEXT": "must-not-use-remote"}):
            self.assertEqual(inventory_docker(endpoint, timeout=2)["status"], "examined")
            script("sys.exit(23)\n")
            self.assertEqual(inventory_docker(endpoint, timeout=2)["status"], "unavailable")
            script("time.sleep(2)\n")
            self.assertEqual(inventory_docker(endpoint, timeout=0.02)["status"], "unavailable")
            script("sys.stdout.write('x' * (1024 * 1024 + 1))\n")
            self.assertEqual(inventory_docker(endpoint, timeout=2)["status"], "unavailable")
            script("time.sleep(2)\n")
            calls = []
            def cancel():
                calls.append(True)
                return len(calls) > 1
            self.assertTrue(inventory_docker(endpoint, timeout=2, cancelled=cancel)["cancelled"])

    def test_global_git_failure_isolated_and_sync_locality_remains_report_only(self):
        repository = self.root / "repo"
        (repository / ".git").mkdir(parents=True)
        sync = self.base / "Dropbox"
        sync.mkdir()
        (sync / "data").write_bytes(b"x")
        self.config["roots"].append(str(sync))
        with patch("devspace.global_inventory.inventory_git", return_value={
                "complete": False, "cancelled": False, "worktrees": [], "limitations": ["synthetic refusal"]}) as git:
            report = self.review()
        self.assertEqual(git.call_args.args[0], repository)
        self.assertFalse(report["coverage"]["complete"])
        self.assertEqual(self.locations(report, "development")[1]["locality"], "unsupported-or-unknown")
        self.assertEqual(report["size"]["logical_bytes"], 6)
        self.assertTrue(all(row["assessment"] != "Eligible" for row in report["candidates"]))

    def test_child_exclusions_preserve_sibling_inventory_in_roots_and_provider_storage(self):
        excluded = self.root / "unrelated"
        excluded.mkdir()
        (excluded / "do-not-enumerate").write_bytes(b"unknown bytes")
        self.config["exclusions"] = [str(excluded)]
        storage = self.base / "storage"
        (storage / "skip").mkdir(parents=True)
        (storage / "shared").write_bytes(b"12")
        (storage / "skip/hidden").write_bytes(b"must not enumerate")
        self.config["package_storage"] = [str(storage)]
        report = self.review(exclusions=[str(storage / "skip")])
        self.assertEqual(report["size"]["logical_bytes"], 5)
        self.assertTrue(any(row["path"] == str(self.root / "output") for row in report["candidates"]))
        self.assertEqual(self.locations(report, "package-storage")[0]["size"]["logical_bytes"], 2)
        self.assertNotIn("do-not-enumerate", json.dumps(report))
        self.assertNotIn("hidden", json.dumps(report))

    def test_case_alias_provider_exclusion_does_not_enumerate_descendants(self):
        storage = self.base / "provider"
        excluded = storage / "Retained"
        excluded.mkdir(parents=True)
        alias = storage / "retained"
        if not alias.exists() or not alias.samefile(excluded):
            self.skipTest("filesystem is case-sensitive; actual alias unavailable")
        (excluded / "do-not-enumerate").write_bytes(b"must remain excluded")
        (storage / "shared").write_bytes(b"12")
        self.config["package_storage"] = [str(storage)]
        report = self.review(exclusions=[str(alias)])
        provider = self.locations(report, "package-storage")[0]
        self.assertEqual(provider["size"]["logical_bytes"], 2)
        self.assertEqual(provider["coverage"]["skipped"], 1)
        self.assertFalse(provider["coverage"]["complete"])
        from devspace.review import review_task
        direct = review_task(storage, exclusions=[str(alias)])
        self.assertEqual(direct["size"]["logical_bytes"], 2)
        self.assertNotIn("do-not-enumerate", json.dumps(direct))
        selected_alias = review_task(excluded, exclusions=[str(alias)])
        self.assertEqual(selected_alias["coverage"]["skipped"], 1)
        self.assertNotIn("do-not-enumerate", json.dumps(selected_alias))

    def test_images_only_docker_response_cannot_claim_complete_provider_coverage(self):
        from devspace.global_inventory import inventory_docker
        payload = b'{"Type":"Images","TotalCount":"1","Active":"0","Size":"2GB","Reclaimable":"2GB"}\n'
        with patch("devspace.global_inventory.shutil.which", return_value="docker"), \
             patch("devspace.global_inventory.run_readonly", return_value=payload):
            row = inventory_docker("unix:///synthetic", timeout=1)
        self.assertEqual(row["status"], "unavailable")
        self.assertEqual(row["usage"], [])

    def test_actual_content_reads_share_global_budget_even_for_hardlinks(self):
        source = self.base / "source.txt"
        source.write_bytes(b"12345")
        source.chmod(0o644)
        context = self.base / "context.txt"
        context.write_text("Synthetic copied outputs; sole fixture consumer released; retained source recreates both paths.")
        import hashlib
        references = {key: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                      for key, path in (("source", source), ("context", context))}
        roots, specifications = [], []
        for name in ("first", "second", "third"):
            root = self.base / name
            target = root / "generated"
            target.mkdir(parents=True)
            roots.append(str(root))
            (target / "one").write_bytes(source.read_bytes())
            (target / "one").chmod(0o644)
            os.link(target / "one", target / "two")
            specifications.append({"path": str(target), "category": "output", "purpose": "synthetic copy",
                "content": {"method": "source-files", "files": {"one": "source", "two": "source"},
                            "directories": [], "basis": ["context"]},
                "recovery": {"kind": "rebuild", "inputs": ["source"], "basis": ["context"]},
                "consumer_scope": {"basis": ["context"], "unresolved": []},
                "release": {"checkpoint": "synthetic completed", "basis": ["context"]}})
        self.config["roots"] = roots
        observed, real = [], plans.review_task
        def observe(*args, **kwargs):
            result = real(*args, **kwargs)
            if kwargs.get("inspect_content"):
                observed.append(result["content"]["read_bytes"])
            return result
        with patch("devspace.plans.review_task", side_effect=observe):
            report = self.review(assessment={"schema_version": 1, "references": references, "candidates": specifications},
                                 max_content_bytes=12)
        self.assertLessEqual(sum(observed), 13)  # one byte detects an over-budget target
        self.assertEqual(observed, [10, 3])
        self.assertEqual(report["content"]["read_bytes"], sum(observed))
        self.assertEqual([row["assessment"] for row in report["candidates"] if row["path"].endswith("generated")],
                         ["Eligible", "Unavailable", "Unavailable"])

    def test_unsafe_config_rejected_and_empty_roots_explicit(self):
        for addition in ({"approved": True}, {"roots": ["relative"]}, {"roots": ["/"]}, {"roots": ["/tmp/.."]},
                         {"package_storage": "not-a-list"}, {"roots": [str(Path.home())]}):
            with self.subTest(addition=addition):
                self.config.update(addition)
                with self.assertRaises(ValueError), patch("devspace.plans.review_task", side_effect=AssertionError("rejected scope reached traversal")):
                    self.review()
                self.config = {"schema_version": 1, "roots": [str(self.root)]}
        self.config["roots"] = []
        self.assertEqual(self.locations(self.review(), "development")[0]["status"], "unconfigured")


class GlobalAssessment(unittest.TestCase):
    def test_shared_eligible_hold_and_frozen_selection_contract(self):
        fixture = test_plans.AssessedPlans(methodName="test_source_journey_and_equivalent_unregistered_assessment_preserve_bytes")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        assessment = copy.deepcopy(fixture.assessment)
        for row in assessment["candidates"]:
            row["path"] = str(fixture.project / row["path"])
        config = {"schema_version": 1, "roots": [str(fixture.project)],
                  "holds": [str(fixture.project / "packet/C")]}
        report = plans.review_scope(config, mode="global", assessment=assessment)
        rows = fixture.by_path(report)
        self.assertEqual(rows["A"]["assessment"], "Eligible")
        from devspace.report import render_text
        printed = render_text(report)
        self.assertNotIn("No file payloads are read", printed)
        self.assertNotIn("No deletion eligibility", printed)
        self.assertGreater(report["content"]["read_bytes"], 0)
        self.assertEqual(rows["packet/C"]["assessment"], "Keep")
        self.assertEqual(rows["B-original-failure"]["assessment"], "Keep")
        self.assertEqual(rows["D"]["assessment"], "Review")
        self.assertEqual(plans.validate_selection(report["plan"], [rows["A"]["id"]])[0]["id"], rows["A"]["id"])

    def test_global_cross_root_candidates_preserve_each_others_evidence(self):
        fixture = test_plans.AssessedPlans(methodName="test_source_journey_and_equivalent_unregistered_assessment_preserve_bytes")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        other = fixture.base / "other-project"
        target = other / "generated"
        target.mkdir(parents=True)
        (target / "data.txt").write_bytes((fixture.records / "source.txt").read_bytes())
        (target / "data.txt").chmod(0o644)
        import hashlib
        references = copy.deepcopy(fixture.references)
        references["retained-input"] = {"path": str(target / "data.txt"),
            "sha256": hashlib.sha256(b"ordinary fixture library\n").hexdigest()}
        first, second = copy.deepcopy(fixture.specifications[:2])
        first["path"] = str(fixture.project / "A")
        second["path"] = str(target)
        config = {"schema_version": 1, "roots": [str(fixture.project), str(other)]}
        before = fixture.bytes()
        for role in ("rebuild-input", "context-basis"):
            candidate = copy.deepcopy(first)
            if role == "rebuild-input":
                candidate["recovery"]["inputs"] = ["retained-input"]
            else:
                candidate["content"]["basis"].append("retained-input")
            for specification in (candidate, second):
                single = plans.review_scope(config, mode="global", assessment={"schema_version": 1,
                    "references": references, "candidates": [specification]})
                row = next(row for row in single["candidates"] if row["path"] == specification["path"])
                self.assertEqual(row["assessment"], "Eligible")
                plans.validate_selection(single["plan"], [row["id"]])
            combined = plans.review_scope(config, mode="global", assessment={"schema_version": 1,
                "references": references, "candidates": [candidate, second]})
            rows = [row for row in combined["candidates"] if row["path"] in {candidate["path"], second["path"]}]
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row["comparison"]["matched"] for row in rows))
            self.assertEqual([row["assessment"] for row in rows], ["Review", "Review"])
            for root_review in combined["root_reviews"]:
                payload = {key: value for key, value in root_review["plan"].items() if key != "digest"}
                self.assertEqual(root_review["plan"]["digest"], plans.digest(payload))
        self.assertEqual(fixture.bytes(), before)

    def test_global_file_mount_boundary_is_refused_before_target_read(self):
        fixture = test_plans.AssessedPlans(methodName="test_source_journey_and_equivalent_unregistered_assessment_preserve_bytes")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        target = fixture.project / "A/data.txt"
        identity = target.stat()
        specification = copy.deepcopy(fixture.specifications[0])
        specification["path"] = str(fixture.project / "A")
        def mount(descriptor):
            observed = os.fstat(descriptor)
            return 11 if (observed.st_dev, observed.st_ino) == (identity.st_dev, identity.st_ino) else 10
        from devspace import review
        real = review.os.read
        target_reads = []
        def observe(descriptor, count):
            observed = os.fstat(descriptor)
            if (observed.st_dev, observed.st_ino) == (identity.st_dev, identity.st_ino):
                target_reads.append(descriptor)
            return real(descriptor, count)
        with patch("devspace.review.mount_identity", side_effect=mount), \
             patch("devspace.review.local_filesystem", return_value=True), \
             patch("devspace.review.os.read", side_effect=observe):
            report = plans.review_scope({"schema_version": 1, "roots": [str(fixture.project)]}, mode="global",
                assessment={**fixture.assessment, "candidates": [specification]})
        row = next(row for row in report["candidates"] if row["path"] == specification["path"])
        self.assertEqual(row["assessment"], "Unavailable")
        self.assertFalse(row["observation"]["complete"])
        self.assertEqual(report["content"]["read_bytes"], 0)
        self.assertEqual(target_reads, [])
