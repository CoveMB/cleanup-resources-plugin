"""Assessed plan behavior using independently generated disposable resources."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/task-disk-review/scripts"))
CLI = ROOT / "skills/task-disk-review/scripts/devspace.py"


class AssessedPlans(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="assessed-plan-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.project = self.base / "project"
        self.project.mkdir()
        self.records = self.base / "records"
        self.records.mkdir()
        source = self.records / "source.txt"
        source.write_bytes(b"ordinary fixture library\n")
        source.chmod(0o644)
        generator = self.records / "generate.py"
        generator.write_text("from pathlib import Path\nimport sys\n"
                             "source, project = map(Path, sys.argv[1:])\n"
                             "for name in ('A', 'packet/C', 'legacy'):\n"
                             " p = project / name; p.mkdir(parents=True)\n"
                             " (p / 'data.txt').write_bytes(source.read_bytes()); (p / 'data.txt').chmod(0o644)\n"
                             "print('generated A, C and legacy from retained source')\n")
        build = subprocess.run([sys.executable, "-B", str(generator), str(source), str(self.project)],
                               text=True, capture_output=True, timeout=10)
        self.assertEqual(build.returncode, 0, build.stderr)
        result = self.records / "result.txt"
        result.write_text(build.stdout)
        decisions = self.records / "decisions.txt"
        decisions.write_text("Fixture owner released A/C/legacy after successful generation; "
                             "the sole fixture consumer has finished; retain source/generator/result. "
                             "Ordinary rebuild cost accepted. B is a required original failure. D is unknown.")
        expected = self.records / "outputs.json"
        expected.write_text(json.dumps({"schema_version": 1, "entries": [
            {"path": "data.txt", "kind": "file", "mode": 420, "size": 25,
             "sha256": hashlib.sha256(b"ordinary fixture library\n").hexdigest()}]}))
        # Correct independent literal size; never derive expected bytes from the target.
        self.assertEqual(len(b"ordinary fixture library\n"), 25)
        self.references = {key: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                           for key, path in {"source": source, "generator": generator, "result": result,
                                             "decision": decisions, "outputs": expected}.items()}
        self.specifications = []
        for name, category in (("A", "output"), ("packet/C", "dependencies"), ("legacy", "output")):
            self.specifications.append({
                "path": name, "category": category, "purpose": "generated disposable fixture",
                "content": {"method": "inventory", "reference": "outputs",
                            "basis": ["source", "generator", "result"],
                            "explanation": "Actual generator and successful result establish output provenance."},
                "recovery": {"kind": "rebuild", "inputs": ["source", "generator"],
                             "basis": ["result"], "explanation": "Retained deterministic fixture inputs rebuild these bytes."},
                "consumers": [{"id": "fixture-consumer", "state": "released", "basis": ["decision"]}],
                "consumer_scope": {"basis": ["decision"], "unresolved": []},
                "release": {"checkpoint": "successful fixture completion", "basis": ["decision"]},
                "findings": [],
            })
        for name in ("B-original-failure", "D"):
            (self.project / name).mkdir()
            (self.project / name / "retained.txt").write_bytes(b"required or unknown original")
        failed_install = subprocess.run([sys.executable, "-B", "-c",
                                        "import sys; sys.stderr.write('synthetic original install failure\\n'); sys.exit(7)"],
                                       capture_output=True, timeout=10)
        self.assertEqual(failed_install.returncode, 7)
        (self.project / "B-original-failure/retained.txt").write_bytes(failed_install.stderr)
        (self.project / "B-original-failure/exit-status.txt").write_text("7\n")
        self.specifications.extend([{"path": "B-original-failure", "category": "evidence", "purpose": "required failure"},
                                    {"path": "D", "category": "unknown", "purpose": "unknown packet"}])
        self.assessment = {"schema_version": 1, "references": self.references, "candidates": self.specifications}

    def owner(self):
        self.assertIsNotNone(importlib.util.find_spec("devspace.plans"), "canonical assessed-plan owner is absent")
        from devspace import plans
        return plans

    def review(self, assessment=None, **options):
        return self.owner().review_scope(self.project, assessment=assessment or self.assessment, **options)

    def by_path(self, report):
        return {Path(row["path"]).relative_to(self.project).as_posix(): row for row in report["candidates"]}

    def bytes(self):
        return {str(p.relative_to(self.base)): p.read_bytes() for p in self.base.rglob("*") if p.is_file()}

    def nested_outputs(self):
        generator = self.records / "generate.py"
        generator.write_text(generator.read_text().replace("p.mkdir(parents=True)", "p.mkdir(parents=True, exist_ok=True)") +
                             "p = project / 'A/nested'; p.mkdir(exist_ok=True); p.chmod(0o755)\n"
                             "(p / 'data.txt').write_bytes(source.read_bytes()); (p / 'data.txt').chmod(0o644)\n"
                             "print('generated nested ordinary output too')\n")
        generated = subprocess.run([sys.executable, "-B", str(generator), str(self.records / "source.txt"), str(self.project)],
                                   capture_output=True, timeout=10)
        self.assertEqual(generated.returncode, 0, generated.stderr)
        (self.records / "result.txt").write_bytes(generated.stdout)
        decisions = self.records / "decisions.txt"
        decisions.write_text(decisions.read_text() + " Released A includes the independently generated nested output.")
        original = json.loads((self.records / "outputs.json").read_text())["entries"][0]
        expected = self.records / "parent-outputs.json"
        expected.write_text(json.dumps({"schema_version": 1, "entries": [original,
                            {"path": "nested", "kind": "directory", "mode": 493},
                            {**original, "path": "nested/data.txt"}]}))
        for key, path in (("generator", generator), ("result", self.records / "result.txt"),
                          ("decision", decisions), ("parent-outputs", expected)):
            self.references[key] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        child = copy.deepcopy(self.specifications[0])
        child["path"] = "A/nested"
        self.specifications[0]["content"]["reference"] = "parent-outputs"
        return child

    def test_source_journey_and_equivalent_unregistered_assessment_preserve_bytes(self):
        # Equivalent exact source-file comparison; no historical output inventory for legacy.
        self.specifications[2]["content"] = {"method": "source-files", "files": {"data.txt": "source"},
                                                "directories": [], "basis": ["generator", "result"],
                                                "explanation": "Generator copies retained source verbatim."}
        before = self.bytes()
        report = self.review(mode="project")
        rows = self.by_path(report)
        self.assertEqual([rows[name]["assessment"] for name in ("A", "packet/C", "legacy", "B-original-failure", "D")],
                         ["Eligible", "Eligible", "Eligible", "Keep", "Review"])
        self.assertEqual(report["scope"]["mode"], "project")
        for name in ("A", "packet/C", "legacy"):
            self.assertTrue(rows[name]["observation"]["complete"])
            self.assertTrue(rows[name]["comparison"]["matched"])
            self.assertEqual(rows[name]["assessment_basis"], "agent evidence interpretation with mechanical checks")
            self.assertEqual(rows[name]["effect"], "permanent removal of this exact directory; rebuild required")
        self.assertEqual(before, self.bytes())

    def test_changed_extra_and_partial_inventory_contents_cannot_qualify(self):
        for change in ("modified", "extra", "partial"):
            with self.subTest(change=change):
                if change == "modified":
                    (self.project / "A/data.txt").write_bytes(b"modified fixture library\n")
                elif change == "extra":
                    (self.project / "A/data.txt").write_bytes(b"ordinary fixture library\n")
                    (self.project / "A/extra.txt").write_bytes(b"unique")
                else:
                    self.specifications[0]["content"]["reference"] = "source"  # not an output inventory
                row = self.by_path(self.review())["A"]
                self.assertNotEqual(row["assessment"], "Eligible")

    def test_protected_state_and_findings_override_release_and_accepted_loss(self):
        (self.project / "A/.env").write_text("SYNTHETIC_PROTECTED_SECRET")
        self.specifications[0]["recovery"] = {"kind": "accepted-loss", "basis": ["decision"], "explanation": "loss accepted"}
        for finding in ("modified-dependency", "offline-dependency", "unique-state", "required-failure", "hold"):
            with self.subTest(finding=finding):
                self.specifications[1]["findings"] = [{"kind": finding, "basis": ["decision"]}]
                report = self.review()
                self.assertEqual(self.by_path(report)["A"]["assessment"], "Keep")
                self.assertEqual(self.by_path(report)["packet/C"]["assessment"], "Keep")
                self.assertNotIn("SYNTHETIC_PROTECTED_SECRET", json.dumps(report))

    def test_consumers_and_historical_manifest_are_not_release_proof(self):
        manifest = {"schema_version": 1, "resources": [{"path": str(self.project / "A"),
                    "origin": "helper-created", "purpose": "fixture", "association": "fixture-project",
                    "consumers": ["fixture-consumer", "second-consumer"], "retention": [],
                    "release_checkpoint": "historical completion"}]}
        report = self.review(manifest=manifest)
        self.assertEqual(self.by_path(report)["A"]["assessment"], "Review")
        self.specifications[0]["consumers"].append({"id": "second-consumer", "state": "active", "basis": ["decision"]})
        self.assertEqual(self.by_path(self.review(manifest=manifest))["A"]["assessment"], "Keep")
        self.specifications[0]["consumers"][-1]["state"] = "released"
        self.assertEqual(self.by_path(self.review(manifest=manifest))["A"]["assessment"], "Eligible")
        self.specifications[0].pop("release")
        self.assertEqual(self.by_path(self.review(manifest=manifest))["A"]["assessment"], "Review")

    def test_missing_references_self_alias_and_unknown_scope_never_qualify(self):
        for variant in ("missing", "self", "alias", "unknown"):
            assessment = copy.deepcopy(self.assessment)
            if variant == "missing":
                assessment["references"]["source"]["path"] = str(self.records / "missing")
            elif variant in {"self", "alias"}:
                target = self.project / "A/data.txt"
                reference = target
                if variant == "alias":
                    reference = self.records / "alias"
                    os.link(target, reference)
                assessment["references"]["outputs"] = {"path": str(reference), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
            else:
                assessment["candidates"][0]["consumer_scope"]["unresolved"] = ["other tasks unknown"]
            self.assertNotEqual(self.by_path(self.review(assessment))["A"]["assessment"], "Eligible")

    def test_holds_exclusions_limits_and_unavailable_candidate(self):
        report = self.review(holds=[str(self.project / "A")], exclusions=[str(self.project / "packet")])
        self.assertEqual(self.by_path(report)["A"]["assessment"], "Keep")
        self.assertEqual(self.by_path(report)["packet/C"]["assessment"], "Keep")
        self.assertNotEqual(self.by_path(self.review(max_content_bytes=1))["A"]["assessment"], "Eligible")
        assessment = copy.deepcopy(self.assessment)
        assessment["candidates"].append({"path": "missing", "category": "output", "purpose": "missing"})
        self.assertEqual(self.by_path(self.review(assessment))["missing"]["assessment"], "Unavailable")

    def test_frozen_plan_roundtrip_selection_identity_and_protected_overlap_guards(self):
        plans = self.owner()
        report = self.review()
        plan = json.loads(json.dumps(report["plan"]))
        rows = self.by_path(report)
        selected = plans.validate_selection(plan, [rows["A"]["id"], rows["packet/C"]["id"]])
        self.assertEqual({row["path"] for row in selected}, {str(self.project / "A"), str(self.project / "packet/C")})
        for mutation in ("host", "effect", "identity", "digest"):
            changed = copy.deepcopy(plan)
            if mutation == "host":
                changed["host"]["hostname"] = "other-host"
            elif mutation == "effect":
                changed["candidates"][0]["effect"] = "broaden removal"
            elif mutation == "identity":
                changed["candidates"][0]["observation"]["identity"]["inode"] += 1
            else:
                changed["digest"] = "0" * 64
            with self.assertRaises(ValueError):
                plans.validate_selection(changed, [rows["A"]["id"]])
        with self.assertRaises(ValueError):
            plans.validate_selection(plan, [rows["D"]["id"]])
        with self.assertRaises(ValueError):
            plans.validate_selection(plan, ["new-item"])
        # Assessed parent roots and overlapping eligible descendants are never executable candidates.
        self.specifications.append(copy.deepcopy(self.specifications[0]))
        self.specifications[-1]["path"] = "."
        self.assertEqual(self.by_path(self.review())["."]["assessment"], "Keep")

    def test_manifest_opt_in_roundtrip_and_plan_output_never_overwrites_targets(self):
        plans = self.owner()
        manifest = {"schema_version": 1, "resources": [{"path": str(self.project / "A"),
                    "origin": "helper-created", "purpose": "fixture", "association": "fixture-project",
                    "consumers": ["fixture-consumer"], "retention": [], "release_checkpoint": "completion"}]}
        destination = self.records / "manifest.json"
        plans.write_manifest(destination, manifest)
        self.assertEqual(plans.read_document(destination), manifest)
        with self.assertRaises((ValueError, FileExistsError)):
            plans.write_manifest(destination, manifest)
        plan = self.review()["plan"]
        with self.assertRaises(ValueError):
            plans.write_plan(self.project / "A/plan.json", plan)
        plans.write_plan(self.records / "plan.json", plan)
        self.assertEqual(plans.read_document(self.records / "plan.json"), plan)

    def test_terminal_task_project_and_standalone_plan_output(self):
        assessment_path = self.records / "assessment.json"
        assessment_path.write_text(json.dumps(self.assessment))
        for mode in ("task", "project"):
            result = subprocess.run([sys.executable, "-B", str(CLI), "review", "--" + mode, str(self.project),
                                     "--assessment", str(assessment_path)], capture_output=True, text=True, timeout=20)
            self.assertIn(result.returncode, (0, 2), result.stderr)
            self.assertIn("Eligible", result.stdout)
            self.assertIn("agent evidence interpretation", result.stdout)
            self.assertIn("not authorization", result.stdout)
        standalone = subprocess.run([sys.executable, "-B", str(CLI), "review", "--project", str(self.project), "--json"],
                                    capture_output=True, text=True, timeout=20)
        self.assertIn(standalone.returncode, (0, 2), standalone.stderr)
        self.assertTrue(json.loads(standalone.stdout)["plan"]["digest"])

    def test_excluded_contents_are_not_enumerated_and_boundaries_are_report_only(self):
        excluded = self.project / "excluded"
        excluded.mkdir()
        (excluded / "not-to-be-enumerated").write_text("SYNTHETIC_EXCLUDED_PAYLOAD")
        report = self.review(exclusions=[str(excluded)])
        self.assertFalse(any("not-to-be-enumerated" in entry["path"] for entry in report["entries"]))

    def test_nonlocal_filesystem_and_unknown_host_are_report_only(self):
        import devspace.review as review
        self.assertTrue(hasattr(review, "local_filesystem"), "filesystem locality observation is absent")
        with patch("devspace.review.local_filesystem", return_value=False):
            self.assertNotEqual(self.by_path(self.review())["A"]["assessment"], "Eligible")
        with patch("devspace.report.host_identity", return_value=None):
            self.assertNotEqual(self.by_path(self.review())["A"]["assessment"], "Eligible")

    def test_source_file_alias_is_rejected_even_when_its_bytes_match(self):
        alias = self.records / "alias.txt"
        os.link(self.project / "legacy/data.txt", alias)
        self.references["alias"] = {"path": str(alias), "sha256": hashlib.sha256(alias.read_bytes()).hexdigest()}
        self.specifications[2]["content"] = {"method": "source-files", "files": {"data.txt": "alias"},
                                                "directories": [], "basis": ["generator", "result"]}
        self.assertNotEqual(self.by_path(self.review())["legacy"]["assessment"], "Eligible")

    def test_source_file_comparison_cannot_smuggle_unreferenced_file_hashes(self):
        (self.project / "legacy/unique.txt").write_bytes(b"unique current state")
        self.specifications[2]["content"] = {"method": "source-files", "files": {"data.txt": "source"},
            "directories": [{"path": "unique.txt", "kind": "file", "mode": 420, "size": 20,
                             "sha256": hashlib.sha256(b"unique current state").hexdigest()}],
            "basis": ["generator", "result"]}
        with self.assertRaises(ValueError):
            self.review()

    def test_hold_and_manifest_aliases_preserve_known_protections(self):
        alias = self.base / "project-alias"
        alias.symlink_to(self.project, target_is_directory=True)
        self.assertEqual(self.by_path(self.review(holds=[str(alias / "A")]))["A"]["assessment"], "Keep")
        manifest = {"schema_version": 1, "resources": [{"path": str(alias / "A"),
                    "origin": "helper-created", "purpose": "fixture", "association": "fixture-project",
                    "consumers": ["another-consumer"], "retention": [], "release_checkpoint": "historical"}]}
        self.assertEqual(self.by_path(self.review(manifest=manifest))["A"]["assessment"], "Review")

    def test_parent_propagates_nested_manifest_hold_and_consumer_facts(self):
        self.nested_outputs()
        manifest = {"schema_version": 1, "resources": [{"path": str(self.project / "A/nested"),
                    "origin": "helper-created", "purpose": "nested output", "association": "fixture-project",
                    "consumers": ["nested-consumer"], "retention": ["required"], "release_checkpoint": "historical"}]}
        before = self.bytes()
        for retention, expected in ((["required"], "Keep"), ([], "Review")):
            with self.subTest(retention=retention):
                manifest["resources"][0]["retention"] = retention
                row = self.by_path(self.review(manifest=manifest))["A"]
                self.assertTrue(row["comparison"]["matched"])
                self.assertEqual(row["assessment"], expected)
        self.assertEqual(self.bytes(), before)

    def test_known_assessment_protections_propagate_in_both_containment_directions(self):
        child = self.nested_outputs()
        self.specifications.append(child)
        for state, expected in (("required", "Keep"), ("active", "Keep"), ("unknown", "Review")):
            with self.subTest(state=state):
                child["findings"] = [{"kind": "required-failure", "basis": ["decision"]}] if state == "required" else []
                child["consumers"] = [{"id": "nested-consumer", "state": "released" if state == "required" else state,
                                      "basis": ["decision"]}]
                self.assertEqual(self.by_path(self.review())["A"]["assessment"], expected)
        child["consumers"][0]["state"] = "released"
        self.specifications[0]["findings"] = [{"kind": "required-failure", "basis": ["decision"]}]
        self.assertEqual(self.by_path(self.review())["A/nested"]["assessment"], "Keep")

    def test_otherwise_eligible_overlap_is_rejected_in_assessment_and_selection(self):
        child = self.nested_outputs()
        parent_assessment = {**copy.deepcopy(self.assessment), "candidates": [copy.deepcopy(self.specifications[0])]}
        child_assessment = {**copy.deepcopy(self.assessment), "candidates": [child]}
        parent_report, child_report = self.review(parent_assessment), self.review(child_assessment)
        parent_row, child_row = parent_report["candidates"][0], child_report["candidates"][0]
        self.assertEqual((parent_row["assessment"], child_row["assessment"]), ("Eligible", "Eligible"))
        self.specifications.append(child)
        rows = self.by_path(self.review())
        for name in ("A", "A/nested"):
            self.assertTrue(rows[name]["comparison"]["matched"])
            self.assertEqual(rows[name]["assessment"], "Review")
            self.assertIn("overlapping", rows[name]["reason"])
        combined = copy.deepcopy(parent_report["plan"])
        combined["candidates"] = [parent_row, child_row]
        payload = {key: value for key, value in combined.items() if key != "digest"}
        combined["digest"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()
        with self.assertRaises(ValueError):
            self.owner().validate_selection(combined, [parent_row["id"], child_row["id"]])

    def test_case_alias_hold_uses_filesystem_identity_where_applicable(self):
        alias = self.project / "a"
        if not alias.exists() or not alias.samefile(self.project / "A"):
            self.skipTest("case-sensitive filesystem; no case alias exists")
        self.assertEqual(self.by_path(self.review(holds=[str(alias)]))["A"]["assessment"], "Keep")

    def test_case_alias_cannot_select_scope_or_home_root(self):
        target = self.project / "A"
        alias = self.project / "a"
        if not alias.exists() or not alias.samefile(target):
            self.skipTest("case-sensitive filesystem; no case alias exists")
        assessment = copy.deepcopy(self.assessment)
        assessment["candidates"] = [copy.deepcopy(self.specifications[0])]
        assessment["candidates"][0]["path"] = str(alias)
        owner = self.owner()
        eligible = self.review(assessment)
        self.assertEqual(eligible["candidates"][0]["assessment"], "Eligible")
        with self.subTest(boundary="assessment scope root"):
            report = owner.review_scope(target, assessment=assessment)
            self.assertEqual(report["candidates"][0]["assessment"], "Keep")
        with self.subTest(boundary="selection scope root"):
            plan = copy.deepcopy(eligible["plan"])
            plan["scope_roots"] = [str(target)]
            plan["digest"] = owner.digest({key: value for key, value in plan.items() if key != "digest"})
            with self.assertRaises(ValueError):
                owner.validate_selection(plan, [plan["candidates"][0]["id"]])
        with patch("devspace.plans.Path.home", return_value=target):
            with self.subTest(boundary="assessment home root"):
                self.assertEqual(self.review(assessment)["candidates"][0]["assessment"], "Keep")
            with self.subTest(boundary="selection home root"):
                with self.assertRaises(ValueError):
                    owner.validate_selection(eligible["plan"], [eligible["candidates"][0]["id"]])

    def test_unsupported_nested_assertions_fail_without_prose_validation(self):
        for field in ("inspected", "approved", "no_consumers"):
            assessment = copy.deepcopy(self.assessment)
            assessment["candidates"][0]["content"][field] = True
            with self.assertRaises(ValueError):
                self.review(assessment)

    def test_content_drift_during_read_and_json_duplicate_keys_fail_closed(self):
        from devspace import review
        original_read = review.os.read
        changed = False

        def alter_after_read(descriptor, count):
            nonlocal changed
            chunk = original_read(descriptor, count)
            if not changed and chunk == b"ordinary fixture library\n":
                changed = True
                (self.project / "A/data.txt").write_text("changed concurrently")
            return chunk

        with patch("devspace.review.os.read", side_effect=alter_after_read):
            self.assertNotEqual(self.by_path(self.review())["A"]["assessment"], "Eligible")
        duplicate = self.records / "duplicate.json"
        duplicate.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError):
            self.owner().read_document(duplicate)


if __name__ == "__main__":
    unittest.main()
