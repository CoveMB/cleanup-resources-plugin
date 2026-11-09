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

    def test_unresolved_obligations_report_distinct_reasons(self):
        from devspace.report import render_text
        cases = (
            ("missing-inventory", "independent content baseline missing or unsupported"),
            ("unknown-consumer", "consumer state unresolved"),
            ("changed-reference", "reference digest changed"),
            ("missing-recovery", "recovery evidence missing"),
            ("malformed-inventory", "independent content baseline invalid or incomplete"),
            ("missing-reference", "referenced evidence unavailable or unsafe"),
        )
        for variant, expected_reason in cases:
            with self.subTest(variant=variant):
                assessment = copy.deepcopy(self.assessment)
                candidate = assessment["candidates"][0]
                if variant == "missing-inventory":
                    candidate["content"].pop("reference")
                elif variant == "unknown-consumer":
                    candidate["consumers"][0]["state"] = "unknown"
                elif variant == "changed-reference":
                    record = self.records / "changed-reference.txt"
                    record.write_bytes(b"original scoped decision")
                    assessment["references"]["decision"] = {
                        "path": str(record), "sha256": hashlib.sha256(record.read_bytes()).hexdigest()}
                    record.write_bytes(b"UNTRUSTED_REFERENCE_PAYLOAD changed decision")
                elif variant == "missing-recovery":
                    candidate.pop("recovery")
                elif variant == "malformed-inventory":
                    candidate["content"]["reference"] = "source"
                else:
                    assessment["references"]["source"]["path"] = str(self.records / "PRIVATE_MISSING_REFERENCE")
                before = self.bytes()
                report = self.review(assessment)
                row = self.by_path(report)["A"]
                self.assertEqual(row["assessment"], "Review")
                self.assertEqual(row["reason"], expected_reason)
                rendered = render_text(report)
                self.assertIn(expected_reason, rendered)
                for marker in ("UNTRUSTED_REFERENCE_PAYLOAD", "PRIVATE_MISSING_REFERENCE"):
                    self.assertNotIn(marker, rendered)
                    self.assertNotIn(marker, row["reason"])
                self.assertEqual(self.bytes(), before)
                self.assertEqual((self.project / "A/data.txt").read_bytes(), b"ordinary fixture library\n")
                self.assertEqual((self.project / "B-original-failure/retained.txt").read_bytes(),
                                 b"synthetic original install failure\n")

    def test_contextual_obligations_identify_the_missing_basis(self):
        cases = (
            ("content", "content provenance evidence missing"),
            ("recovery", "recovery evidence missing"),
            ("consumer_scope", "consumer scope evidence missing"),
            ("release", "release evidence missing"),
        )
        before = self.bytes()
        for claim, expected_reason in cases:
            with self.subTest(claim=claim):
                assessment = copy.deepcopy(self.assessment)
                assessment["candidates"][0][claim]["basis"] = []
                row = self.by_path(self.review(assessment))["A"]
                self.assertEqual(row["assessment"], "Review")
                self.assertEqual(row["reason"], expected_reason)
        self.assertEqual(self.bytes(), before)

    def test_unexpected_reference_errors_do_not_leak(self):
        from devspace.report import render_text
        before = self.bytes()
        for error_type in (OSError, ValueError, KeyError, TypeError, UnicodeError, RecursionError):
            with self.subTest(error=error_type.__name__):
                with patch("devspace.plans._read_file", side_effect=error_type("RAW_PRIVATE_ERROR /private/source")):
                    report = self.review()
                row = self.by_path(report)["A"]
                self.assertEqual(row["assessment"], "Review")
                self.assertEqual(row["reason"], "referenced evidence unavailable or unsafe")
                self.assertNotIn("RAW_PRIVATE_ERROR", json.dumps(report))
                self.assertNotIn("/private/source", render_text(report))
        self.assertEqual(self.bytes(), before)

    def test_protection_precedes_unresolved_diagnostics(self):
        (self.project / "A/.env").write_bytes(b"SYNTHETIC_PROTECTED_SECRET")
        self.specifications[0]["content"] = {}
        self.specifications[1]["consumers"][0]["state"] = "active"
        self.specifications[1].pop("recovery")
        before = self.bytes()
        report = self.review()
        rows = self.by_path(report)
        self.assertEqual(rows["A"]["assessment"], "Keep")
        self.assertEqual(rows["packet/C"]["assessment"], "Keep")
        self.assertEqual(rows["B-original-failure"]["assessment"], "Keep")
        limited = self.review({**self.assessment, "candidates": [self.specifications[2]]}, max_content_bytes=1)
        self.assertEqual(self.by_path(limited)["legacy"]["assessment"], "Unavailable")
        self.assertNotIn("SYNTHETIC_PROTECTED_SECRET", json.dumps(report))
        self.assertEqual(self.bytes(), before)

    def test_diagnostic_changes_preserve_versioned_selection(self):
        before = self.bytes()
        owner = self.owner()
        for version in (1, 2, 3, 4, 5):
            with self.subTest(version=version):
                assessment = copy.deepcopy(self.assessment)
                assessment["schema_version"] = version
                if version > 1:
                    for candidate in assessment["candidates"]:
                        candidate["operation"] = "directory-remove"
                report = self.review(assessment)
                eligible = self.by_path(report)["A"]
                self.assertEqual(eligible["assessment"], "Eligible")
                self.assertEqual(eligible["reason"],
                                 "complete comparison and evidence-backed content/use/release/recovery assessment")
                self.assertEqual(report["plan"]["schema_version"], version)
                plan = json.loads(json.dumps(report["plan"]))
                self.assertEqual(owner.validate_selection(plan, [eligible["id"]]), [eligible])
                assessment["candidates"][0]["consumers"][0]["state"] = "unknown"
                unresolved = self.review(assessment)
                row = self.by_path(unresolved)["A"]
                self.assertEqual(row["assessment"], "Review")
                self.assertEqual(row["reason"], "consumer state unresolved")
                with self.assertRaises(ValueError):
                    owner.validate_selection(unresolved["plan"], [row["id"]])
        self.assertEqual(self.bytes(), before)

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

    def test_manifest_prerequisite_preserves_output_paths_for_retry(self):
        manifest = {"schema_version": 1, "resources": []}
        source = self.records / "retry-manifest-input.json"
        source.write_text(json.dumps(manifest))
        plan_output = self.records / "retry-plan.json"
        manifest_output = self.records / "retry-manifest.json"
        command = [sys.executable, "-B", str(CLI), "review", "--task", str(self.project),
                   "--plan-output", str(plan_output), "--manifest-output", str(manifest_output)]
        before = self.bytes()
        invalid = subprocess.run(command, capture_output=True, timeout=20)
        self.assertEqual(invalid.returncode, 1)
        self.assertEqual(invalid.stdout, b"")
        self.assertNotIn(b"Traceback", invalid.stderr)
        self.assertFalse(plan_output.exists())
        self.assertFalse(manifest_output.exists())
        self.assertEqual(self.bytes(), before)
        retry = subprocess.run(command + ["--manifest", str(source)], capture_output=True, timeout=20)
        self.assertIn(retry.returncode, (0, 2), retry.stderr)
        self.assertEqual(retry.stderr, b"")
        self.assertEqual(json.loads(plan_output.read_text())["kind"], "frozen-review-not-authorization")
        self.assertEqual(json.loads(manifest_output.read_text()), manifest)
        after = self.bytes()
        self.assertEqual(set(after) - set(before), {"records/retry-plan.json", "records/retry-manifest.json"})
        self.assertTrue(all(after[name] == contents for name, contents in before.items()))

    def test_manifest_output_cannot_modify_reviewed_roots(self):
        manifest = {"schema_version": 1, "resources": [{"path": str(self.project / "A"),
                    "origin": "helper-created", "purpose": "fixture", "association": "fixture-project",
                    "consumers": [], "retention": [], "release_checkpoint": "completion"}]}
        source = self.records / "manifest-input.json"
        source.write_text(json.dumps(manifest))
        before = self.bytes()
        for mode in ("task", "project"):
            with self.subTest(mode=mode):
                destination = self.project / (mode + "-manifest.json")
                result = subprocess.run([sys.executable, "-B", str(CLI), "review", "--" + mode,
                    str(self.project), "--manifest", str(source), "--manifest-output", str(destination)],
                    capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 1)
                self.assertFalse(destination.exists())
        self.assertEqual(self.bytes(), before)
        destination = self.records / "manifest-output.json"
        result = subprocess.run([sys.executable, "-B", str(CLI), "review", "--task", str(self.project),
            "--manifest", str(source), "--manifest-output", str(destination)], capture_output=True, timeout=20)
        self.assertIn(result.returncode, (0, 2), result.stderr)
        self.assertEqual(json.loads(destination.read_text()), manifest)

    def test_combined_selection_preserves_other_candidates_references(self):
        owner = self.owner()
        self.references["retained-input"] = {"path": str(self.project / "packet/C/data.txt"),
            "sha256": hashlib.sha256(b"ordinary fixture library\n").hexdigest()}
        before = self.bytes()
        for role in ("rebuild-input", "context-basis"):
            with self.subTest(role=role):
                first = copy.deepcopy(self.specifications[0])
                second = copy.deepcopy(self.specifications[1])
                if role == "rebuild-input":
                    first["recovery"]["inputs"] = ["retained-input"]
                else:
                    first["content"]["basis"].append("retained-input")
                first_report = self.review({**self.assessment, "candidates": [first]})
                second_report = self.review({**self.assessment, "candidates": [second]})
                first_row, second_row = first_report["candidates"][0], second_report["candidates"][0]
                self.assertEqual((first_row["assessment"], second_row["assessment"]), ("Eligible", "Eligible"))
                owner.validate_selection(first_report["plan"], [first_row["id"]])
                owner.validate_selection(second_report["plan"], [second_row["id"]])
                plan = copy.deepcopy(first_report["plan"])
                plan["candidates"] = [first_row, second_row]
                plan["digest"] = owner.digest({key: value for key, value in plan.items() if key != "digest"})
                for order in ([first_row["id"], second_row["id"]], [second_row["id"], first_row["id"]]):
                    with self.subTest(order=order), self.assertRaises(ValueError):
                        owner.validate_selection(plan, order)
                combined = self.review({**self.assessment, "candidates": [first, second]})
                for row in combined["candidates"][:2]:
                    self.assertTrue(row["comparison"]["matched"])
                    self.assertEqual(row["assessment"], "Review")
                    self.assertIn("evidence", row["reason"])
        self.assertEqual(self.bytes(), before)

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

    @unittest.skipUnless(hasattr(os, "O_SEARCH"), "search-only directory handles unavailable")
    def test_reference_read_through_search_only_ancestor(self):
        ancestor = self.records / "search-only"
        documents = ancestor / "documents"
        documents.mkdir(parents=True)
        document = documents / "review.json"
        document.write_text('{"schema_version": 1, "purpose": "public fixture"}')
        if os.geteuid() == 0:
            self.skipTest("root bypasses directory read permissions")
        for restricted in (ancestor, documents):
            with self.subTest(search_only_directory=restricted.name):
                restricted.chmod(0o111)
                try:
                    with self.assertRaises(PermissionError):
                        descriptor = os.open(restricted, os.O_RDONLY | os.O_DIRECTORY)
                        os.close(descriptor)
                    try:
                        observed = self.owner().read_document(document)
                    except ValueError as error:
                        self.fail(f"public reference behind search-only directory was refused: {error}")
                    self.assertEqual(observed, {"schema_version": 1, "purpose": "public fixture"})
                finally:
                    restricted.chmod(0o755)

    def test_reference_read_without_platform_search_flag(self):
        document = self.records / "review.json"
        document.write_text('{"schema_version": 1, "purpose": "portable fixture"}')
        with patch.dict(os.__dict__):
            os.__dict__.pop("O_SEARCH", None)
            self.assertEqual(self.owner().read_document(document),
                             {"schema_version": 1, "purpose": "portable fixture"})

    def test_reference_ancestor_and_leaf_links_remain_refused(self):
        document = self.records / "review.json"
        document.write_text('{"schema_version": 1}')
        ancestor_alias = self.base / "records-alias"
        ancestor_alias.symlink_to(self.records, target_is_directory=True)
        leaf_alias = self.records / "review-alias.json"
        leaf_alias.symlink_to(document)
        for path in (ancestor_alias / document.name, leaf_alias):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.owner().read_document(path)

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



    def test_git_lineage_final_phase_preserves_review(self):
        import test_git_inventory
        import devspace.git_inventory as inventory
        fixture = test_git_inventory.GitInventory()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        linked, request, record = fixture.lineage_fixture(linked_name="linked")
        config = {"schema_version": 1, "roots": [str(self.project), str(fixture.project)]}
        from devspace import docker_cleanup, npm_cache
        import base64
        for version in (1, 2, 3, 4, 5):
            assessment = copy.deepcopy(self.assessment)
            assessment["schema_version"] = version
            for row in assessment["candidates"]:
                row["path"] = str(self.project / row["path"])
                if version >= 2: row["operation"] = "directory-remove"
            if version >= 3:
                assessment["candidates"].append({"operation": "docker-container-remove",
                    "docker": {"endpoint": "unix://"+str(self.base / "fixture.sock"), "id": "a"*64}})
            if version >= 4:
                (self.base / "selected-cache").mkdir(exist_ok=True)
                assessment["candidates"].append({"operation": "npm-cache-remove", "npm": {
                    "cache": str(self.base / "selected-cache"), "key": "selected",
                    "integrity": "sha512-"+base64.b64encode(bytes(64)).decode()}})
            cache = str(self.base / "optional-cache")
            before = (test_git_inventory.lineage_snapshot(fixture.fixture), test_git_inventory.lineage_snapshot(self.base))
            events = []
            clock = [100.0]
            advancing_clock = [False]
            original_docker, original_npm = docker_cleanup.review, npm_cache.review
            def docker(*args, **kwargs):
                events.append("docker")
                with patch("devspace.docker_cleanup.inspect", side_effect=inventory.InspectionUnavailable("fixture provider unavailable")):
                    return original_docker(*args, **kwargs)
            def npm(*args, **kwargs):
                events.append("npm")
                with patch("devspace.npm_cache.inspect", side_effect=inventory.InspectionUnavailable("fixture provider unavailable")):
                    return original_npm(*args, **kwargs)
            def discover(*args, **kwargs):
                events.append("cache")
                if advancing_clock[0]: clock[0] = 108.0
                return {"cache": cache, "coverage": "examined", "entries": []}
            with patch("devspace.npm_cache.inventory", side_effect=discover), \
                    patch("devspace.docker_cleanup.review", side_effect=docker), \
                    patch("devspace.npm_cache.review", side_effect=npm):
                control = self.owner().review_scope(config, mode="global", assessment=assessment, npm_caches=[cache])
            self.assertTrue(any(row["assessment"] == "Eligible" for row in control["candidates"]))
            def exhausted(*args, **kwargs):
                expected = (["docker"] if version >= 3 else []) + (["npm"] if version >= 4 else []) + ["cache"]
                self.assertEqual(events[-len(expected):], expected)
                self.assertEqual(kwargs["deadline"], 110.0, "lineage receives the original outer deadline")
                self.assertEqual(freeze.call_args.args[0]["plan"], control["plan"], "final frozen plan exists before lineage")
                freezes_at_lineage.append(freeze.call_count)
                raise inventory.InspectionUnavailable("Git inspection time limit; remaining state unknown")
            with patch("devspace.npm_cache.inventory", side_effect=discover), \
                    patch("devspace.docker_cleanup.review", side_effect=docker), \
                    patch("devspace.npm_cache.review", side_effect=npm):
                observed = self.owner().review_scope(config, mode="global", assessment=assessment,
                                                    npm_caches=[cache], git_lineage=request)
            self.assertEqual(observed["git_lineage"]["status"], "observed")
            for key in ("candidates", "scope_roots", "plan", "size"):
                self.assertEqual(observed[key], control[key], key)
            advancing_clock[0] = True
            freezes_at_lineage = []
            with self.subTest(version=version), patch("devspace.plans.time.monotonic", side_effect=lambda: clock[0]), \
                    patch("devspace.npm_cache.inventory", side_effect=discover), \
                    patch("devspace.docker_cleanup.review", side_effect=docker), \
                    patch("devspace.npm_cache.review", side_effect=npm), \
                    patch("devspace.plans.freeze_review", wraps=self.owner().freeze_review) as freeze, \
                    patch("devspace.git_inventory.observe_lineage", side_effect=exhausted) as observe:
                report = self.owner().review_scope(config, mode="global", assessment=assessment,
                                                  npm_caches=[cache], git_lineage=request)
            observe.assert_called_once()
            self.assertEqual(freezes_at_lineage, [freeze.call_count], "no freeze occurs after lineage")
            for key in ("candidates", "scope_roots", "plan", "size"):
                self.assertEqual(report[key], control[key], key)
            self.assertFalse(report["coverage"]["complete"])
            self.assertNotEqual(report["git_lineage"]["status"], "observed")
            self.assertEqual((test_git_inventory.lineage_snapshot(fixture.fixture), test_git_inventory.lineage_snapshot(self.base)), before)
        # Time consumed by ordinary work cannot create a fresh advisory budget.
        with patch("devspace.plans._review_docker_scope", return_value=copy.deepcopy(control)), \
                patch("devspace.plans.time.monotonic", side_effect=[10, 30]), \
                patch("devspace.git_inventory.observe_lineage", side_effect=AssertionError("expired acquisition")):
            report = self.owner().review_scope(config, mode="global", timeout=1, git_lineage=request)
        self.assertEqual(report["git_lineage"]["status"], "not_examined")

    def test_git_lineage_global_later_root_survives_exhaustion(self):
        import test_git_inventory
        import devspace.git_inventory as inventory
        fixture = test_git_inventory.GitInventory()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        linked, request, record = fixture.lineage_fixture(linked_name="linked")
        config = {"schema_version": 1, "roots": [str(fixture.project), str(self.project)]}
        assessment = copy.deepcopy(self.assessment)
        for row in assessment["candidates"]: row["path"] = str(self.project / row["path"])
        before = (test_git_inventory.lineage_snapshot(fixture.fixture), test_git_inventory.lineage_snapshot(self.base))
        control = self.owner().review_scope(config, mode="global", assessment=assessment)
        self.assertTrue(any(row["assessment"] == "Eligible" for row in control["candidates"]))
        for failure in (inventory.InspectionUnavailable("time limit"), inventory.InspectionCancelled("cancelled"), KeyboardInterrupt()):
            with patch("devspace.git_inventory.observe_lineage", side_effect=failure):
                report = self.owner().review_scope(config, mode="global", assessment=assessment, git_lineage=request)
            self.assertEqual(report["cancelled"], isinstance(failure, (inventory.InspectionCancelled, KeyboardInterrupt)))
            self.assertFalse(report["coverage"]["complete"])
            for key in ("candidates", "scope_roots", "plan", "size"):
                self.assertEqual(report[key], control[key], key)
        self.assertEqual((test_git_inventory.lineage_snapshot(fixture.fixture), test_git_inventory.lineage_snapshot(self.base)), before)


    def test_git_lineage_requested_claim_failure_paths(self):
        # Catches loss/mislabeling of requested claims on every outer skip/exception route.
        import test_git_inventory
        from devspace import git_inventory as inventory
        from devspace.report import render_text
        fixture = test_git_inventory.GitInventory()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        linked, request, record = fixture.integration_fixture("squash")
        # Reuse the accepted claim-failure matrix and actual Git fixture for
        # both contracts. The v5 arm has a real independent exact-file candidate.
        from test_exact_file import ExactFileFixture
        file_fixture = ExactFileFixture(); file_fixture.setUp(); self.addCleanup(file_fixture.doCleanups)
        for version in (1, 5):
            config = {"schema_version": 1, "roots": [str(self.project), str(fixture.project)]}
            assessment = copy.deepcopy(self.assessment)
            for row in assessment["candidates"]: row["path"] = str(self.project / row["path"])
            if version == 5:
                assessment = copy.deepcopy(file_fixture.assessment)
                assessment["candidates"][0]["path"] = str(file_fixture.target)
                config["roots"].append(str(file_fixture.project))
            control = self.owner().review_scope(config, mode="global", assessment=assessment)
            self.assertTrue(any(row["assessment"] == "Eligible" for row in control["candidates"]))
            if version == 5:
                self.assertTrue(any(row.get("operation") == "file-remove" and row["assessment"] == "Eligible" for row in control["candidates"]))
            positive = self.owner().review_scope(config, mode="global", assessment=assessment, git_lineage=request)
            self.assertEqual(positive["git_lineage"]["status"], "observed")
            for key in ("candidates", "scope_roots", "plan", "size"):
                self.assertEqual(positive[key], control[key], key)
            file_before = test_git_inventory.lineage_snapshot(file_fixture.base)
            before = (test_git_inventory.lineage_snapshot(fixture.fixture), test_git_inventory.lineage_snapshot(self.base))
            failures = ("unmatched", "budget", "scope", "host", "already-cancelled", "cancelled", "interrupt", "unavailable")
            for kind in ("squash", "merge", "absent"):
                trial = copy.deepcopy(request)
                if kind == "merge":
                    trial["integration"]["kind"] = "merge"
                    trial["integration"].pop("source_base_commit")
                elif kind == "absent": trial.pop("integration")
                for failure in failures:
                    ordinary = copy.deepcopy(control)
                    selected = copy.deepcopy(config)
                    supplied = copy.deepcopy(trial)
                    if failure == "unmatched": supplied["path"] = str(fixture.fixture / "unmatched")
                    if failure == "scope": ordinary["invalid_scope"] = True
                    if failure == "host": selected["host_identity"] = "different-host"
                    if failure == "already-cancelled": ordinary["cancelled"] = True
                    error = {"cancelled": inventory.InspectionCancelled("cancelled"), "interrupt": KeyboardInterrupt(),
                             "unavailable": inventory.InspectionUnavailable("unavailable")}.get(failure)
                    skipped = error is None
                    with self.subTest(version=version, kind=kind, failure=failure), \
                            patch("devspace.plans._review_docker_scope", return_value=ordinary), \
                            patch("devspace.plans.time.monotonic", side_effect=[100, 120] if failure == "budget" else lambda: 100), \
                            patch("devspace.git_inventory.observe_lineage", side_effect=error or AssertionError("skipped observer acquired")) as observer, \
                            patch("devspace.git_inventory._git", side_effect=AssertionError("unexpected native acquisition")), \
                            patch("devspace.git_worktree._metadata_file", side_effect=AssertionError("unexpected metadata acquisition")), \
                            patch("devspace.git_worktree._administration_state", side_effect=AssertionError("unexpected admin acquisition")), \
                            patch("devspace.plans._open_parent", side_effect=AssertionError("unexpected descriptor acquisition")), \
                            patch("devspace.exact_file.review_file", side_effect=AssertionError("unexpected advisory file payload acquisition")), \
                            patch("devspace.npm_cache.inspect", side_effect=AssertionError("unexpected advisory cache acquisition")), \
                            patch("devspace.docker_cleanup.LocalDocker", side_effect=AssertionError("unexpected advisory provider acquisition")):
                        report = self.owner().review_scope(selected, mode="global", assessment=assessment, git_lineage=supplied)
                    self.assertEqual(observer.call_count, 0 if skipped else 1)
                    self.assertEqual(report["cancelled"], failure in ("already-cancelled", "cancelled", "interrupt"))
                    lineage = report["git_lineage"]
                    self.assertEqual(lineage["status"], "unavailable" if failure == "unavailable" else "not_examined")
                    if kind == "absent":
                        self.assertEqual(lineage["integration"], {"status": "not_requested"})
                        self.assertEqual(lineage["patch_equivalence"], {"status": "not_requested"})
                    else:
                        evidence = lineage["integration"]
                        self.assertEqual(evidence["status"], "unavailable")
                        for field, value in trial["integration"].items(): self.assertEqual(evidence[field], value)
                        self.assertEqual(evidence["claim_authenticity"], "unverified")
                        self.assertEqual(evidence["current_content_preservation"], "unestablished")
                        for field in ("source_matches_head", "source_in_head", "source_in_parents", "destination_parent_count",
                                      "destination_in_current_destination", "current_destination_matches_claim",
                                      "current_destination_tree_matches_claim", "current_destination_commit"):
                            self.assertIsNone(evidence[field], field)
                        if kind == "squash":
                            self.assertEqual(evidence["squash_provenance"], "unverified")
                            self.assertEqual(lineage["patch_equivalence"]["status"], "unavailable")
                            for field in ("equal", "source_path_count", "destination_path_count", "destination_base_commit"):
                                self.assertIsNone(lineage["patch_equivalence"][field], field)
                            self.assertIn('"squash_provenance": "unverified"', render_text(report))
                        else: self.assertEqual(lineage["patch_equivalence"], {"status": "not_requested"})
                        self.assertTrue(any("authenticate" in limitation for limitation in lineage["limitations"]))
                    expected = inventory._lineage_result(claim=supplied.get("integration"))
                    self.assertEqual(lineage["limitations"], expected["limitations"])
                    self.assertEqual(lineage["binding"], {})
                    self.assertFalse(report["coverage"]["complete"])
                    for key in ("candidates", "scope_roots", "plan", "size"):
                        self.assertEqual(report[key], control[key], key)
            self.assertEqual((test_git_inventory.lineage_snapshot(fixture.fixture), test_git_inventory.lineage_snapshot(self.base)), before)

            self.assertEqual(test_git_inventory.lineage_snapshot(file_fixture.base), file_before)

    def test_git_lineage_last_administration_read_preserves_cancellation(self):
        # Catches final drift/read-failure returning incomplete instead of cancelled.
        import time
        import test_git_inventory
        from devspace import git_inventory as inventory, git_worktree as adapter
        fixture = test_git_inventory.GitInventory()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        linked, request, record = fixture.integration_fixture("squash")
        config = {"schema_version": 1, "roots": [str(self.project), str(fixture.project)]}
        assessment = copy.deepcopy(self.assessment)
        for row in assessment["candidates"]: row["path"] = str(self.project / row["path"])
        control = self.owner().review_scope(config, mode="global", assessment=assessment)
        self.assertTrue(any(row["assessment"] == "Eligible" for row in control["candidates"]))
        original = adapter._administration_state
        native = inventory._git
        exclusions = inventory._check_exclusions
        for outcome, cancel_after in (("unchanged", False), ("unchanged", True), ("drift", False),
                                      ("drift", True), ("ValueError", False), ("ValueError", True),
                                      ("OSError", False), ("OSError", True), ("deadline", False)):
            reads, deltas = 0, 0
            clock = [time.monotonic()]
            completed = False
            drift_path = None
            drift_original = None
            expected_git = test_git_inventory.lineage_snapshot(fixture.fixture)
            before_ordinary = test_git_inventory.lineage_snapshot(self.base)
            def final_read(path):
                nonlocal reads, completed, drift_path, drift_original, expected_git
                reads += 1
                if reads == 2 and outcome == "drift":
                    drift_path = path / "ORIG_HEAD"
                    drift_original = drift_path.read_bytes() if drift_path.exists() else None
                    changed_root = request["integration"]["destination_commit"]
                    if drift_original == (changed_root+"\n").encode(): changed_root = request["expected_head"]
                    drift_path.write_text(changed_root+"\n")
                value = original(path)
                if reads == 2:
                    completed = True
                    expected_git = test_git_inventory.lineage_snapshot(fixture.fixture)
                    if outcome == "deadline": clock[0] += 11
                    if outcome == "ValueError": raise ValueError("controlled final read failure")
                    if outcome == "OSError": raise OSError("controlled final read failure")
                return value
            def actual_native(*args):
                nonlocal deltas
                self.assertFalse(completed, "no native acquisition after final read")
                result = native(*args)
                if "diff-tree" in args[2]: deltas += 1
                return result
            def actual_exclusions(*args):
                self.assertFalse(completed, "completion decision must acquire no more metadata")
                return exclusions(*args)
            with self.subTest(outcome=outcome, cancelled=cancel_after):
                try:
                    with patch("devspace.plans._review_docker_scope", return_value=copy.deepcopy(control)), \
                            patch("devspace.git_worktree._administration_state", side_effect=final_read), \
                            patch("devspace.git_inventory._git", side_effect=actual_native), \
                            patch("devspace.git_inventory._check_exclusions", side_effect=actual_exclusions), \
                            patch("devspace.plans.time.monotonic", side_effect=lambda: clock[0]):
                        report = self.owner().review_scope(config, mode="global", assessment=assessment, git_lineage=request,
                                                           cancelled=lambda: completed and cancel_after, timeout=10)
                    self.assertEqual(report["cancelled"], cancel_after)
                    lineage = report["git_lineage"]
                    self.assertEqual(lineage["integration"]["source_commit"], request["integration"]["source_commit"])
                    self.assertEqual(lineage["integration"]["squash_provenance"], "unverified")
                    if outcome == "unchanged" and not cancel_after:
                        self.assertEqual(lineage["status"], "observed")
                        self.assertIs(lineage["patch_equivalence"]["equal"], True)
                    else:
                        self.assertFalse(report["coverage"]["complete"])
                        self.assertEqual(lineage["status"], "not_examined" if cancel_after else "changed")
                        self.assertIsNone(lineage["patch_equivalence"]["equal"])
                        self.assertIsNone(lineage["retention"]["head_in_ref"])
                    for key in ("candidates", "scope_roots", "plan", "size"):
                        self.assertEqual(report[key], control[key], key)
                finally:
                    self.assertEqual(reads, 2)
                    self.assertEqual(deltas, 2)
                    self.assertEqual(test_git_inventory.lineage_snapshot(fixture.fixture), expected_git)
                    self.assertEqual(test_git_inventory.lineage_snapshot(self.base), before_ordinary)
                    if drift_path is not None:
                        if drift_original is None: drift_path.unlink()
                        else: drift_path.write_bytes(drift_original)


if __name__ == "__main__":
    unittest.main()
