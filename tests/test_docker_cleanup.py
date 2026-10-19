"""Deterministic parsing, selection and native-failure contracts.

Real daemon evidence uses separately inventoried disposable fixtures, never CI's
ambient resources. Fault injection here does not certify native effects.
"""
import copy
import json
import os
from pathlib import Path
import socket
import tempfile
import sys
import subprocess
import unittest
from unittest.mock import patch, MagicMock

import test_plans
from devspace import plans, cleanup
from devspace import docker_cleanup


class InspectedDocker:
    """Fault boundary; native proof is explicitly separate."""
    def __init__(self, *unused):
        self.identity = {"daemon": "fixture-daemon", "endpoint": "unix:///private/tmp/fixture.sock",
                         "socket": {"dev": 1, "ino": 2, "mode": 0}, "executable": "/fixture/docker",
                         "configuration_directory": "/fixture/config"}
        self.record = copy.deepcopy(type(self).record)
    record = {"Id": "a" * 64, "Config": {"Labels": {"fixture.owner": "fixture"}},
              "HostConfig": {}, "State": {"Status": "exited", "Running": False, "Restarting": False},
              "Mounts": [], "SizeRw": 0, "Image": "sha256:" + "b" * 64}
    def container(self, identifier): return self.record
    def read(self, *arguments): return b""
    def listed_ids(self, kind): return ["a" * 64] if kind == "container" else []
    def container_dependencies(self, identifier, name): return []


def container_resource():
    return {"endpoint": "unix:///private/tmp/fixture.sock", "id": "a" * 64,
            "ownership_label": {"key": "fixture.owner", "value": "fixture"}}


class DockerContracts(unittest.TestCase):
    def test_terminal_binds_provider_without_bulk_unselected_inventory(self):
        with patch.object(docker_cleanup, "LocalDocker", InspectedDocker):
            base, pp, ap, report = self.assessed()
        row = copy.deepcopy(report["candidates"][0])
        row["native"]["cache_records"] = [{"id": "SYNTHETIC_UNSELECTED_BULK_MARKER"}]
        terminal = MagicMock(); terminal.isatty.return_value = True
        opened = MagicMock(); opened.__enter__.return_value = terminal
        with patch("builtins.open", return_value=opened), patch.object(cleanup.sys.stdin, "isatty", return_value=True), \
                patch.object(cleanup.sys.stdin, "readline", return_value="CANCEL\n"):
            self.assertFalse(cleanup._confirm(report["plan"], [row]))
        displayed = "".join(call.args[0] for call in terminal.write.call_args_list)
        self.assertIn("a" * 64, displayed)
        self.assertIn("fixture-daemon", displayed)
        self.assertNotIn("SYNTHETIC_UNSELECTED_BULK_MARKER", displayed)

    def test_native_cancellation_is_an_explicit_partial_review(self):
        with patch.object(docker_cleanup, "LocalDocker", InspectedDocker):
            base, pp, ap, report = self.assessed()
        assessment = json.loads(ap.read_text())
        with patch.object(docker_cleanup, "inspect", side_effect=docker_cleanup.InspectionCancelled("fixture cancellation")):
            cancelled = plans.review_scope(base / "scope", assessment=assessment)
        self.assertTrue(cancelled["cancelled"])
        self.assertFalse(cancelled["coverage"]["complete"])
    def test_default_builder_binds_local_daemon_worker_and_plugin_without_instance_file(self):
        instance = object.__new__(docker_cleanup.LocalDocker)
        instance.config = "/fixture/config"; instance.endpoint = "unix:///private/tmp/fixture.sock"
        instance.identity = {"daemon": "fixture-daemon"}
        instance.json = lambda *args: [{"Name": "buildx", "Path": "/fixture/buildx"}]
        instance.read = lambda *args: b"Name: default\nDriver: docker\nNodes:\nName: default\nEndpoint: default\nStatus: running\nBuildKit version: v0.33.1\nLabels:\n worker.uuid: unique-worker\n"
        with patch.object(docker_cleanup.Path, "resolve", return_value=Path("/fixture/buildx")), \
                patch.object(docker_cleanup, "_identity", return_value={"inode": 123}), \
                patch.object(docker_cleanup, "_metadata_file", side_effect=AssertionError("default has no stored instance")):
            result = instance.builder("default")
        self.assertEqual(result["driver"], "docker")
        self.assertEqual(result["daemon"], "fixture-daemon")
        self.assertIn("inspection_digest", result)
    def test_existing_unlabelled_resources_use_evidence_not_registration(self):
        resource = {"endpoint": "unix:///private/tmp/fixture.sock", "id": "a" * 64}
        docker_cleanup.validate_resource(resource, "docker-container-remove")
        with patch.object(docker_cleanup, "LocalDocker", InspectedDocker), patch.dict(InspectedDocker.record, {"Config": {"Labels": None}}):
            self.assertEqual(docker_cleanup.inspect(resource, "docker-container-remove")["resource"], resource)

    def test_provider_hold_cannot_be_removed_from_a_rehashed_plan(self):
        with patch.object(docker_cleanup, "LocalDocker", InspectedDocker):
            base, pp, ap, report = self.assessed()
        plan = copy.deepcopy(report["plan"])
        plan["policy"]["holds"].append("/private/tmp/fixture.sock")
        plan["digest"] = plans.digest({key: value for key, value in plan.items() if key != "digest"})
        with self.assertRaises(ValueError):
            plans.validate_selection(plan, [report["candidates"][0]["id"]])

    def test_resource_aliases_cannot_hide_another_active_consumer(self):
        with patch.object(docker_cleanup, "LocalDocker", InspectedDocker):
            base, pp, ap, report = self.assessed()
            assessment = json.loads(ap.read_text())
            alias = copy.deepcopy(assessment["candidates"][0]); alias["docker"].pop("ownership_label")
            alias["consumers"][0]["state"] = "active"
            assessment["candidates"].append(alias)
            with self.assertRaises(ValueError):
                plans.review_scope(base / "scope", assessment=assessment)

    def test_endpoint_alias_cannot_hide_an_active_consumer(self):
        with patch.object(docker_cleanup, "LocalDocker", InspectedDocker):
            base, pp, ap, report = self.assessed()
            assessment = json.loads(ap.read_text())
            alias = copy.deepcopy(assessment["candidates"][0])
            alias["docker"]["endpoint"] = alias["docker"]["endpoint"].replace("/fixture.sock", "/./fixture.sock")
            alias["consumers"][0]["state"] = "active"
            assessment["candidates"].append(alias)
            with self.assertRaises(ValueError):
                plans.review_scope(base / "scope", assessment=assessment)

    def test_socket_inode_alias_cannot_hide_an_active_consumer(self):
        with patch.object(docker_cleanup, "LocalDocker", InspectedDocker):
            base, pp, ap, report = self.assessed()
            assessment = json.loads(ap.read_text())
            # Short Unix path; exercise case aliases on APFS, inode aliases elsewhere.
            with tempfile.TemporaryDirectory(dir="/tmp", prefix="socket-alias-") as temporary, socket.socket(socket.AF_UNIX) as provider:
                endpoint = Path(temporary).resolve() / "daemon.sock"
                provider.bind(str(endpoint))
                alias_endpoint = endpoint.with_name("DAEMON.sock")
                if not alias_endpoint.exists():
                    os.link(endpoint, alias_endpoint)
                assessment["candidates"][0]["docker"]["endpoint"] = "unix://" + str(endpoint)
                alias = copy.deepcopy(assessment["candidates"][0])
                alias["docker"]["endpoint"] = "unix://" + str(alias_endpoint)
                alias["consumers"][0]["state"] = "active"
                assessment["candidates"].append(alias)
                with self.assertRaises(ValueError):
                    plans.review_scope(base / "scope", assessment=assessment)

    def test_provider_aliases_cannot_hide_an_active_consumer(self):
        with patch.object(docker_cleanup, "LocalDocker", InspectedDocker):
            base, pp, ap, report = self.assessed()
            original = json.loads(ap.read_text())
            for operation, identifier, builder in (
                    ("docker-container-remove", "a" * 64, None),
                    ("docker-image-remove", "sha256:" + "b" * 64, None),
                    ("docker-cache-remove", "c" * 25, "worker")):
                with self.subTest(operation=operation):
                    assessment = copy.deepcopy(original)
                    candidate = assessment["candidates"][0]
                    candidate["operation"] = operation
                    candidate["docker"] = {"endpoint": "unix:///private/tmp/first.sock", "id": identifier}
                    if builder:
                        candidate["docker"]["builder"] = builder
                    alias = copy.deepcopy(candidate)
                    alias["docker"]["endpoint"] = "unix:///private/tmp/second.sock"
                    if builder:
                        alias["docker"]["builder"] = "worker-alias"
                    alias["consumers"][0]["state"] = "active"
                    assessment["candidates"].append(alias)
                    with patch.object(docker_cleanup, "inspect", side_effect=ValueError("unavailable fixture")), self.assertRaises(ValueError):
                        plans.review_scope(base / "scope", assessment=assessment)

    @unittest.skipUnless(sys.platform == "darwin", "tested macOS/APFS transaction")
    def test_provider_drift_refuses_whole_batch_before_confirmation(self):
        with patch.object(docker_cleanup, "LocalDocker", InspectedDocker):
            base, pp, ap, report = self.assessed()
            selected = report["candidates"][0]
            for key in ("daemon", "endpoint", "socket", "executable", "configuration_directory"):
                changed = copy.deepcopy(selected["native"]); changed["provider"][key] = "changed"
                with self.subTest(key=key), patch.object(docker_cleanup, "inspect", return_value=changed), \
                        patch.object(cleanup, "_state_path", return_value=base / "state"), \
                        patch.object(cleanup, "_confirm", side_effect=AssertionError("cannot confirm drift")):
                    with self.assertRaises(ValueError):
                        cleanup.apply(pp, ap, [selected["id"]])
            self.assertFalse(list((base / "state").glob("*.intent.json")))

    @unittest.skipUnless(sys.platform == "darwin", "tested macOS/APFS transaction")
    def test_permission_refusal_leaves_private_pending_intent_for_observation(self):
        with patch.object(docker_cleanup, "LocalDocker", InspectedDocker):
            base, pp, ap, report = self.assessed()
            def denied(row, limits):
                raise docker_cleanup.NativeRemovalFailed("native-refusal", 13)
            with patch.object(cleanup, "_state_path", return_value=base / "state"), patch.object(cleanup, "_confirm", return_value=True), \
                    patch.object(docker_cleanup, "remove", side_effect=denied):
                result = cleanup.apply(pp, ap, [report["candidates"][0]["id"]])
            self.assertEqual(result["native_failure"], {"kind": "native-refusal", "exit_code": 13})
            self.assertEqual(result["outcome"], "partial-or-failed")
            self.assertTrue((base / "state/pending.json").exists())
            with patch.object(cleanup, "_state_path", return_value=base / "state"), \
                    patch.object(docker_cleanup, "observe", return_value="same-provider-id-contents-unverified"), \
                    patch.object(docker_cleanup, "remove", side_effect=AssertionError("no replay")):
                observed = cleanup.reconcile(pp)
            self.assertEqual(observed["targets"][0]["outcome"], "same-provider-id-contents-unverified")
            for record in (base / "state").glob("*.json"):
                payload = record.read_text()
                self.assertNotIn("Synthetic owner", payload)
                self.assertNotIn(str(base), payload)

    def test_reconcile_discovers_tools_and_refuses_changed_provider(self):
        with patch.object(docker_cleanup, "LocalDocker", InspectedDocker):
            base, pp, ap, report = self.assessed()
            row = copy.deepcopy(report["candidates"][0])
            row["native"]["provider"]["executable"] = "/must-never-execute/from-plan"
            self.assertEqual(docker_cleanup.observe(row), "unknown-provider-identity")

    def test_text_review_distinguishes_provider_estimate_from_host_space(self):
        from devspace.report import render_text
        with patch.object(docker_cleanup, "LocalDocker", InspectedDocker):
            base, pp, ap, report = self.assessed()
        self.assertIn("Provider estimate: 0 bytes; host recovery unknown", render_text(report))

    def test_known_native_container_consumers_prevent_removal(self):
        with patch.object(docker_cleanup, "LocalDocker", InspectedDocker), \
                patch.object(InspectedDocker, "container_dependencies", return_value=["b" * 64]):
            with self.assertRaises(ValueError):
                docker_cleanup.inspect(container_resource(), "docker-container-remove")

    def test_single_local_image_tag_and_matching_digest_are_bound_not_refused(self):
        class ImageDocker(InspectedDocker):
            def image(self, identifier):
                return {"Id": identifier, "Config": {"Labels": {"fixture.owner": "fixture"}},
                        "Size": 4096, "RepoTags": self.tags, "RepoDigests": self.digests}
            def listed_ids(self, kind): return []
            tags = ["fixture/image:retired"]
            digests = ["fixture/image@sha256:" + "b" * 64]
        resource = {**container_resource(), "id": "sha256:" + "b" * 64}
        with patch.object(docker_cleanup, "LocalDocker", ImageDocker):
            native = docker_cleanup.inspect(resource, "docker-image-remove")
            self.assertEqual(native["tags"], ImageDocker.tags)
            for tags,digests in ((["fixture/image:retired", "other/image:retained"], ImageDocker.digests),
                                 (ImageDocker.tags, ["other/image@sha256:" + "b" * 64])):
                with patch.object(ImageDocker,"tags",tags), patch.object(ImageDocker,"digests",digests):
                    with self.assertRaises(ValueError):
                        docker_cleanup.inspect(resource,"docker-image-remove")

    def test_cache_parser_protects_active_shared_and_hides_description(self):
        record = {"ID": "a" * 25, "Parents": [], "CreatedAt": "2026-01-01T00:00:00Z",
                  "LastUsedAt": "2026-01-01T00:00:00Z", "Mutable": False, "Reclaimable": True,
                  "Shared": False, "Size": "4096", "Description": "SYNTHETIC_SECRET_PAYLOAD", "UsageCount": 1, "Type": "regular"}
        parsed = docker_cleanup.cache_records(json.dumps(record).encode())
        self.assertNotIn("SYNTHETIC_SECRET_PAYLOAD", json.dumps(parsed))
        self.assertEqual(parsed[0]["size"], 4096)
        docker_cleanup.reclaimable_record(parsed, "a" * 25)
        for field, value in (("Shared", True), ("Reclaimable", False)):
            with self.subTest(field=field):
                changed = {**record, field: value}
                with self.assertRaises(ValueError):
                    docker_cleanup.reclaimable_record(docker_cleanup.cache_records(json.dumps(changed).encode()), "a" * 25)

    def test_installed_cache_human_format_is_estimate_not_age_based_identity(self):
        record = {"ID": "a" * 25, "Parents": None, "CreatedAt": "2026-10-19 00:26:01 +0000 UTC",
                  "LastUsedAt": "2 minutes ago", "Mutable": True, "Reclaimable": True,
                  "Shared": False, "Size": "8.192kB", "Description": "synthetic COPY", "UsageCount": 1, "Type": "regular"}
        before = docker_cleanup.cache_records(json.dumps(record).encode())
        after = docker_cleanup.cache_records(json.dumps({**record, "LastUsedAt": "3 minutes ago"}).encode())
        self.assertEqual(before, after)
        self.assertEqual(before[0]["size"], 8192)
        docker_cleanup.reclaimable_record(before, "a" * 25)

    def test_cache_match_is_generated_anchored_literal_and_rejects_injection(self):
        self.assertEqual(docker_cleanup.cache_filter("a" * 25), "id=^" + "a" * 25 + "$")
        for identifier in ("a.*", "a" * 25 + ",inuse=false", "a" * 24):
            with self.assertRaises(ValueError):
                docker_cleanup.cache_filter(identifier)

    def test_cache_batch_accepts_only_prior_selected_success_transitions(self):
        first = {"id": "a" * 25, "parents": []}
        second = {"id": "b" * 25, "parents": []}
        old = {"operation": "docker-cache-remove", "native": {"resource": {
            "endpoint": "unix:///private/tmp/fixture.sock", "builder": "fixture", "id": "b" * 25},
            "cache_records": [first, second]}}
        completed = {"operation": "docker-cache-remove", "native": {"resource": {
            "endpoint": "unix:///private/tmp/fixture.sock", "builder": "fixture", "id": "a" * 25}}}
        expected = docker_cleanup.expected_native(old, [completed])
        self.assertEqual(expected["cache_records"], [second])
        completed["native"]["resource"]["builder"] = "other"
        self.assertEqual(docker_cleanup.expected_native(old, [completed])["cache_records"], [first, second])

    def assessed(self):
        temporary = tempfile.TemporaryDirectory(prefix="docker-contract-fixture-")
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve(); (base / "scope").mkdir()
        decision = base / "decision.txt"
        decision.write_text("Synthetic owner released mount-free unchanged-layer fixture; no consumers remain. Accepted permanent loss.")
        resource = container_resource()
        native = docker_cleanup.inspect(resource, "docker-container-remove")
        expected = base / "expected.json"
        expected.write_text(json.dumps({"schema_version": 1, "native_digest": plans.digest(native)}))
        references = {name: {"path": str(path), "sha256": plans.hashlib.sha256(path.read_bytes()).hexdigest()}
                      for name, path in (("decision", decision), ("expected", expected))}
        specification = {"operation": "docker-container-remove", "docker": resource, "category": "container", "purpose": "synthetic released fixture",
                         "content": {"method": "native-inspection", "reference": "expected", "basis": ["decision"]},
                         "recovery": {"kind": "accepted-loss", "basis": ["decision"]},
                         "consumer_scope": {"basis": ["decision"], "unresolved": []},
                         "consumers": [{"id": "fixture", "state": "released", "basis": ["decision"]}],
                         "release": {"basis": ["decision"], "checkpoint": "finished fixture"}, "findings": []}
        assessment = {"schema_version": 3, "references": references, "candidates": [specification]}
        report = plans.review_scope(base / "scope", assessment=assessment)
        self.assertEqual(report["candidates"][0]["assessment"], "Eligible", report["candidates"][0])
        plan_path=base / "plan.json"; plan_path.write_text(json.dumps(report["plan"]))
        assessment_path=base / "assessment.json"; assessment_path.write_text(json.dumps(assessment))
        return base, plan_path, assessment_path, report

    @unittest.skipUnless(sys.platform == "darwin", "mutation requires tested macOS/APFS")
    def test_docker_transaction_preserves_durable_intent_and_compact_receipt(self):
        with patch.object(docker_cleanup, "LocalDocker", InspectedDocker):
            base, plan_path, assessment_path, report = self.assessed()
            def removal(row, limits):
                self.assertTrue(list((base / "state").glob("*.intent.json")))
                self.assertTrue((base / "state/pending.json").exists())
            with patch.object(cleanup, "_state_path", return_value=base / "state"), \
                    patch.object(cleanup, "_confirm", return_value=True), \
                    patch.object(docker_cleanup, "remove", side_effect=removal):
                result = cleanup.apply(plan_path, assessment_path, [report["candidates"][0]["id"]])
            self.assertEqual(result["outcome"], "completed")
            self.assertEqual(result["targets"][0]["resource_id"], "a" * 64)
            self.assertNotIn(str(base), json.dumps(result))
            self.assertIsNone(result["targets"][0]["allocated_bytes_estimate"])

    def test_stopped_does_not_override_writable_mount_running_or_owner_guards(self):
        with patch.object(docker_cleanup, "LocalDocker", InspectedDocker):
            self.assertEqual(docker_cleanup.inspect(container_resource(), "docker-container-remove")["size"], 0)
            for key, value in (("SizeRw", None), ("Mounts", [{"Type": "volume"}]),
                               ("State", {"Status": "running", "Running": True, "Restarting": False}),
                               ("Config", {"Labels": {}})):
                with self.subTest(key=key), patch.dict(InspectedDocker.record, {key: value}):
                    with self.assertRaises(ValueError):
                        docker_cleanup.inspect(container_resource(), "docker-container-remove")
            with patch.object(InspectedDocker, "read", return_value=b"A /unique.txt\n"):
                with self.assertRaises(ValueError):
                    docker_cleanup.inspect(container_resource(), "docker-container-remove")

    def test_provider_configuration_cannot_be_directory_target(self):
        fixture = test_plans.AssessedPlans(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        target = fixture.project / ".docker"
        target.mkdir()
        (target / "data.txt").write_bytes(b"ordinary fixture library\n")
        (target / "data.txt").chmod(0o644)
        specification = copy.deepcopy(fixture.specifications[0]); specification["path"] = str(target)
        report = plans.review_scope(fixture.project, assessment={**fixture.assessment, "candidates": [specification]})
        self.assertNotEqual(report["candidates"][0]["assessment"], "Eligible")

    def test_v3_requires_explicit_docker_operation_and_rejects_commands(self):
        assessment = {"schema_version": 3, "references": {}, "candidates": [{
            "operation": "docker-container-remove", "docker": {
                "endpoint": "unix:///private/tmp/fixture.sock", "id": "a" * 64,
                "ownership_label": {"key": "fixture.owner", "value": "fixture"}},
            "purpose": "released synthetic container", "category": "container"}]}
        plans._validate_assessment(assessment)
        assessment["candidates"][0]["docker"]["command"] = "remove everything"
        with self.assertRaises(ValueError):
            plans._validate_assessment(assessment)

    def test_global_host_mismatch_and_endpoint_hold_never_probe_docker(self):
        with patch.object(docker_cleanup, "LocalDocker", InspectedDocker):
            base, plan_path, assessment_path, report = self.assessed()
        assessment = json.loads(assessment_path.read_text())
        with patch.object(docker_cleanup, "inspect", side_effect=AssertionError("must not inspect")):
            global_report = plans.review_scope({"schema_version": 1, "roots": [str(base / "scope")],
                "host_identity": "wrong-host"}, mode="global", assessment=assessment)
            self.assertNotEqual(global_report["candidates"][-1]["assessment"], "Eligible")
            held = plans.review_scope(base / "scope", assessment=assessment, holds=["/private/tmp/fixture.sock"])
            self.assertEqual(held["candidates"][-1]["assessment"], "Keep")

    def test_exact_identifiers_refuse_prefixes_and_filter_expressions(self):
        from devspace import docker_cleanup
        for operation, identifier in (("docker-container-remove", "abc"),
                                      ("docker-image-remove", "sha256:abc"),
                                      ("docker-cache-remove", "abc;other")):
            with self.subTest(operation=operation):
                with self.assertRaises(ValueError):
                    docker_cleanup.validate_resource({"endpoint": "unix:///private/tmp/fixture.sock", "id": identifier,
                        "builder": "fixture", "ownership_label": {"key": "fixture", "value": "owned"}}, operation)

    def test_v3_directory_meaning_is_preserved(self):
        fixture = test_plans.AssessedPlans(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        assessment = copy.deepcopy(fixture.assessment)
        assessment["schema_version"] = 3
        for row in assessment["candidates"]:
            row["operation"] = "directory-remove"
        report = plans.review_scope(fixture.project, assessment=assessment)
        self.assertEqual(report["plan"]["schema_version"], 3)
        eligible = [row["id"] for row in report["candidates"] if row["assessment"] == "Eligible"]
        self.assertTrue(eligible)
        self.assertTrue(plans.validate_selection(report["plan"], eligible))

    def test_mixed_batch_preserves_checked_docker_evidence_through_aliases(self):
        fixture = test_plans.AssessedPlans(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        directory_report = fixture.review()
        directory = copy.deepcopy(next(row for row in directory_report["candidates"]
                                       if row["path"] == str(fixture.project / "A")))
        with patch.object(docker_cleanup, "LocalDocker", InspectedDocker):
            base, pp, ap, report = self.assessed()
        native = copy.deepcopy(report["candidates"][0])
        alias = fixture.base / "selected-alias"
        alias.symlink_to(fixture.project / "A", target_is_directory=True)
        before = (fixture.project / "A/data.txt").read_bytes()
        for reference_path in (fixture.project / "A/data.txt", alias / "data.txt"):
            with self.subTest(reference_path=reference_path):
                candidate = copy.deepcopy(native)
                candidate["references"]["checked-evidence"] = {"path": str(reference_path),
                    "sha256": plans.hashlib.sha256(before).hexdigest()}
                combined = copy.deepcopy(directory_report)
                combined["candidates"] = [copy.deepcopy(directory), candidate]
                assessment = {"schema_version": 3, "references": {}, "candidates": []}
                plans.freeze_review(combined, assessment, None, [], [], directory_report["plan"]["policy"]["limits"])
                self.assertTrue(all(row["assessment"] == "Review" for row in combined["candidates"]))
                # An older frozen batch must also refuse both execution orders.
                plan = combined["plan"]
                for row in plan["candidates"]:
                    row["assessment"] = "Eligible"
                plan["digest"] = plans.digest({key: value for key, value in plan.items() if key != "digest"})
                identifiers = [row["id"] for row in plan["candidates"]]
                for order in (identifiers, list(reversed(identifiers))):
                    with self.subTest(order=order), self.assertRaisesRegex(ValueError, "evidence|rebuild"):
                        plans.validate_selection(plan, order)
        self.assertEqual((fixture.project / "A/data.txt").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
