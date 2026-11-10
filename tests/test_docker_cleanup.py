"""Deterministic parsing, selection and native-failure contracts.

Real daemon evidence uses separately inventoried disposable fixtures, never CI's
ambient resources. Fault injection here does not certify native effects.
"""
import copy
import base64
from contextlib import ExitStack
import json
import os
from pathlib import Path
import socket
import tempfile
import sys
import subprocess
import time
import unittest
from unittest.mock import patch, MagicMock

import test_plans
from devspace import plans, cleanup
from devspace import docker_cleanup, npm_cache, git_worktree


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


IMAGE_ID = "sha256:" + "b" * 64
REFUSAL_REASON = "Container removal unavailable: complete absence of writable changes cannot be established; preserve this container."


class SupportedDocker(InspectedDocker):
    """Read-only provider boundary double for supported image/cache contracts."""
    environment = {}
    present = True
    def image(self, identifier):
        return {"Id": identifier, "Config": {"Labels": {"fixture.owner": "fixture"}}, "Size": 4096,
                "RepoTags": ["fixture/image:retired"], "RepoDigests": ["fixture/image@" + IMAGE_ID]}
    def listed_ids(self, kind):
        return [IMAGE_ID] if kind == "image" and self.present else []
    def builder(self, name):
        return {"name": name, "driver": "docker", "daemon": "fixture-daemon", "inspection_digest": "f" * 64}
    def cache(self, builder, identifier=None):
        return [{"id": "c" * 25, "parents": [], "created": "2026-01-01T00:00:00Z", "last_used": None,
                 "mutable": False, "reclaimable": True, "shared": False, "size": 2048,
                 "usage_count": 1, "type": "regular"}] if self.present else []
    def command(self, *arguments):
        return ["/fixture/docker", "--host", "unix:///private/tmp/fixture.sock", *arguments]


class DockerContracts(unittest.TestCase):
    def test_terminal_binds_provider_without_bulk_unselected_inventory(self):
        with patch.object(docker_cleanup, "LocalDocker", SupportedDocker):
            base, pp, ap, report = self.assessed()
        row = copy.deepcopy(report["candidates"][0])
        row["native"]["cache_records"] = [{"id": "SYNTHETIC_UNSELECTED_BULK_MARKER"}]
        terminal = MagicMock(); terminal.isatty.return_value = True
        opened = MagicMock(); opened.__enter__.return_value = terminal
        with patch("builtins.open", return_value=opened), patch.object(cleanup.sys.stdin, "isatty", return_value=True), \
                patch.object(cleanup.sys.stdin, "readline", return_value="CANCEL\n"):
            self.assertFalse(cleanup._confirm(report["plan"], [row]))
        displayed = "".join(call.args[0] for call in terminal.write.call_args_list)
        self.assertIn(IMAGE_ID, displayed)
        self.assertIn("fixture-daemon", displayed)
        self.assertNotIn("SYNTHETIC_UNSELECTED_BULK_MARKER", displayed)

    def test_native_cancellation_is_an_explicit_partial_review(self):
        with patch.object(docker_cleanup, "LocalDocker", SupportedDocker):
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
        with patch.object(docker_cleanup, "LocalDocker", side_effect=AssertionError("no provider")) as provider:
            with self.assertRaises(docker_cleanup._ContainerRemovalUnavailable) as refused:
                docker_cleanup.inspect(resource, "docker-container-remove")
            self.assertEqual(str(refused.exception), REFUSAL_REASON)
            provider.assert_not_called()
        with patch.object(docker_cleanup, "LocalDocker", SupportedDocker):
            image = {**resource, "id": IMAGE_ID}
            self.assertEqual(docker_cleanup.inspect(image, "docker-image-remove")["resource"], image)

    def test_provider_hold_cannot_be_removed_from_a_rehashed_plan(self):
        with patch.object(docker_cleanup, "LocalDocker", SupportedDocker):
            base, pp, ap, report = self.assessed()
        plan = copy.deepcopy(report["plan"])
        plan["policy"]["holds"].append("/private/tmp/fixture.sock")
        plan["digest"] = plans.digest({key: value for key, value in plan.items() if key != "digest"})
        with self.assertRaises(ValueError):
            plans.validate_selection(plan, [report["candidates"][0]["id"]])

    def test_resource_aliases_cannot_hide_another_active_consumer(self):
        with patch.object(docker_cleanup, "LocalDocker", SupportedDocker):
            base, pp, ap, report = self.assessed()
            assessment = json.loads(ap.read_text())
            alias = copy.deepcopy(assessment["candidates"][0]); alias["docker"].pop("ownership_label")
            alias["consumers"][0]["state"] = "active"
            assessment["candidates"].append(alias)
            with self.assertRaises(ValueError):
                plans.review_scope(base / "scope", assessment=assessment)

    def test_endpoint_alias_cannot_hide_an_active_consumer(self):
        with patch.object(docker_cleanup, "LocalDocker", SupportedDocker):
            base, pp, ap, report = self.assessed()
            assessment = json.loads(ap.read_text())
            alias = copy.deepcopy(assessment["candidates"][0])
            alias["docker"]["endpoint"] = alias["docker"]["endpoint"].replace("/fixture.sock", "/./fixture.sock")
            alias["consumers"][0]["state"] = "active"
            assessment["candidates"].append(alias)
            with self.assertRaises(ValueError):
                plans.review_scope(base / "scope", assessment=assessment)

    def test_socket_inode_alias_cannot_hide_an_active_consumer(self):
        with patch.object(docker_cleanup, "LocalDocker", SupportedDocker):
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
        with patch.object(docker_cleanup, "LocalDocker", SupportedDocker):
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
        with patch.object(docker_cleanup, "LocalDocker", SupportedDocker):
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
        with patch.object(docker_cleanup, "LocalDocker", SupportedDocker):
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
        with patch.object(docker_cleanup, "LocalDocker", SupportedDocker):
            base, pp, ap, report = self.assessed()
            row = copy.deepcopy(report["candidates"][0])
            row["native"]["provider"]["executable"] = "/must-never-execute/from-plan"
            self.assertEqual(docker_cleanup.observe(row), "unknown-provider-identity")

    def test_text_review_distinguishes_provider_estimate_from_host_space(self):
        from devspace.report import render_text
        with patch.object(docker_cleanup, "LocalDocker", SupportedDocker):
            base, pp, ap, report = self.assessed()
        self.assertIn("Provider estimate: 4096 bytes; host recovery unknown", render_text(report))

    def test_known_native_container_consumers_prevent_removal(self):
        # Refusal now precedes even dependency inspection; no consumer claim enables it.
        with patch.object(docker_cleanup, "LocalDocker", side_effect=AssertionError("no provider")):
            with self.assertRaises(docker_cleanup._ContainerRemovalUnavailable) as refused:
                docker_cleanup.inspect(container_resource(), "docker-container-remove")
            self.assertEqual(str(refused.exception), REFUSAL_REASON)

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
        decision.write_text("Synthetic owner released unused single-tag image fixture; no consumers remain. Accepted permanent loss.")
        resource = {**container_resource(), "id": IMAGE_ID}
        native = docker_cleanup.inspect(resource, "docker-image-remove")
        expected = base / "expected.json"
        expected.write_text(json.dumps({"schema_version": 1, "native_digest": plans.digest(native)}))
        references = {name: {"path": str(path), "sha256": plans.hashlib.sha256(path.read_bytes()).hexdigest()}
                      for name, path in (("decision", decision), ("expected", expected))}
        specification = {"operation": "docker-image-remove", "docker": resource, "category": "image", "purpose": "synthetic released fixture",
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
        with patch.object(docker_cleanup, "LocalDocker", SupportedDocker):
            base, plan_path, assessment_path, report = self.assessed()
            def removal(row, limits):
                self.assertTrue(list((base / "state").glob("*.intent.json")))
                self.assertTrue((base / "state/pending.json").exists())
            with patch.object(cleanup, "_state_path", return_value=base / "state"), \
                    patch.object(cleanup, "_confirm", return_value=True), \
                    patch.object(docker_cleanup, "remove", side_effect=removal):
                result = cleanup.apply(plan_path, assessment_path, [report["candidates"][0]["id"]])
            self.assertEqual(result["outcome"], "completed")
            self.assertEqual(result["targets"][0]["resource_id"], IMAGE_ID)
            self.assertNotIn(str(base), json.dumps(result))
            self.assertIsNone(result["targets"][0]["allocated_bytes_estimate"])

    def test_stopped_does_not_override_unproved_writable_contents(self):
        with patch.object(docker_cleanup, "LocalDocker", side_effect=AssertionError("no provider acquisition")):
            for key, value in (("SizeRw", None), ("Mounts", [{"Type": "volume"}]),
                               ("State", {"Status": "running", "Running": True, "Restarting": False}),
                               ("Config", {"Labels": {}})):
                with self.subTest(key=key), patch.dict(InspectedDocker.record, {key: value}):
                    with self.assertRaises(docker_cleanup._ContainerRemovalUnavailable):
                        docker_cleanup.inspect(container_resource(), "docker-container-remove")
            with patch.object(InspectedDocker, "read", return_value=b"A /unique.txt\n"):
                with self.assertRaises(docker_cleanup._ContainerRemovalUnavailable):
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
        with patch.object(docker_cleanup, "LocalDocker", SupportedDocker):
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
        with patch.object(docker_cleanup, "LocalDocker", SupportedDocker):
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


class LegacyContainerContracts(unittest.TestCase):
    """Catch late admission, fabricated inspection and stranded historical intents."""
    def specification(self, operation, resource, reference="expected"):
        return {"operation": operation, "docker": resource, "category": "container", "purpose": "synthetic released fixture",
                "content": {"method": "native-inspection", "reference": reference, "basis": ["decision"]},
                "recovery": {"kind": "accepted-loss", "basis": ["decision"]},
                "consumer_scope": {"basis": ["decision"], "unresolved": []},
                "consumers": [{"id": "fixture", "state": "released", "basis": ["decision"]}],
                "release": {"basis": ["decision"], "checkpoint": "finished fixture"}, "findings": []}

    def historical_row(self, specification, references, host, project, record=None):
        # Documented pre-correction v3/v4 shape, never a current Eligible observation.
        record = copy.deepcopy(record or InspectedDocker.record)
        resource = specification["docker"]
        native = {"provider": InspectedDocker().identity, "resource": resource, "operation": "docker-container-remove",
                  "state_digest": plans.digest(record), "image": record["Image"], "size": record["SizeRw"]}
        checked = {key: plans._reference(key, references, Path("/native-docker-evidence"), [], time.monotonic() + 10)[1]
                   for key in ("decision", specification["content"]["reference"])}
        return {"id": docker_cleanup.resource_identifier(resource, "docker-container-remove"),
                "path": "docker-container-remove:" + resource["id"], "host": host, "project": project,
                "category": specification["category"], "purpose": specification["purpose"], "operation": "docker-container-remove",
                "assessment": "Eligible", "reason": "exact native inspection and evidence-backed ownership/use/release/recovery",
                "effect": "permanent native removal of this exact stopped container; no volumes removed; no writable-data undo",
                "references": checked, "comparison": {"method": "native-inspection", "matched": True},
                "preconditions": ["same local daemon/socket/executable/resource/configuration and evidence",
                                  "separate exact-plan terminal confirmation; new plan on drift"],
                "specification_digest": plans.digest(specification), "native": native,
                "observation": {"complete": True, "provider_size_bytes_estimate": record["SizeRw"], "identity": plans.digest(native)}}

    def fixture(self, version=3, companion="directory-remove"):
        fixture = test_plans.AssessedPlans(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        references = copy.deepcopy(fixture.references)
        expected = fixture.records / "historical-native.json"
        resource = container_resource()
        old_native = {"provider": InspectedDocker().identity, "resource": resource, "operation": "docker-container-remove",
                      "state_digest": plans.digest(InspectedDocker.record), "image": IMAGE_ID, "size": 0}
        expected.write_text(json.dumps({"schema_version": 1, "native_digest": plans.digest(old_native)}))
        references["historical"] = {"path": str(expected), "sha256": plans.hashlib.sha256(expected.read_bytes()).hexdigest()}
        container = self.specification("docker-container-remove", resource, "historical")
        native_npm = None
        if companion == "directory-remove":
            other = {**copy.deepcopy(fixture.specifications[0]), "operation": "directory-remove"}
        elif companion in ("docker-image-remove", "docker-cache-remove"):
            selected_resource = {"endpoint": resource["endpoint"], "id": IMAGE_ID} if companion == "docker-image-remove" else {
                "endpoint": resource["endpoint"], "id": "c" * 25, "builder": "fixture"}
            with patch.object(docker_cleanup, "LocalDocker", SupportedDocker):
                native = docker_cleanup.inspect(selected_resource, companion)
            baseline = fixture.records / "supported-native.json"
            baseline.write_text(json.dumps({"schema_version": 1, "native_digest": plans.digest(native)}))
            references["supported"] = {"path": str(baseline), "sha256": plans.hashlib.sha256(baseline.read_bytes()).hexdigest()}
            other = self.specification(companion, selected_resource, "supported")
        else:
            self.assertEqual(companion, "npm-cache-remove")
            cache = fixture.base / "cache"; cache.mkdir(); (cache / "_cacache").mkdir()
            payload = b"ordinary fixture library\n"
            npm_resource = {"cache": str(cache), "key": "fixture-key", "integrity": "sha512-" + base64.b64encode(plans.hashlib.sha512(payload).digest()).decode()}
            content_path, _ = npm_cache.effect_paths(npm_resource)
            content_path.parent.mkdir(parents=True); content_path.write_bytes(payload)
            # Explicit synthetic native shape: no Node/npm inspection or native fixture import.
            native_npm = {"cache": str(cache), "resource": npm_resource,
                          "cache_identity": plans.file_identity(cache.stat()), "store_identity": plans.file_identity((cache / "_cacache").stat()),
                          "max_entries": 2000, "tools": {"node": "/fixture/node", "npm": "/fixture/npm-cli.js", "root": "/fixture/npm"},
                          "records": [{"key": "fixture-key", "integrity": npm_resource["integrity"], "size": len(payload), "time": 1}],
                          "content_identity": plans.file_identity(content_path.stat()), "content_sha256": plans.hashlib.sha256(payload).hexdigest(),
                          "size": {"logical_bytes": len(payload), "allocated_bytes": content_path.stat().st_blocks * 512}}
            other = {key: value for key, value in copy.deepcopy(container).items() if key not in {"docker", "operation"}}
            other.update(operation=companion, npm=npm_resource,
                         content={"method": "source-file", "reference": "source", "basis": ["decision"]},
                         recovery={"kind": "accepted-loss", "basis": ["decision"], "explanation": "synthetic bounded fixture loss"})
        assessment = {"schema_version": version, "references": references, "candidates": [container, other]}
        plans._validate_assessment(assessment)
        with patch.object(docker_cleanup, "LocalDocker", SupportedDocker), patch.object(npm_cache, "inspect", return_value=native_npm):
            report = plans.review_scope(fixture.project, assessment=assessment)
        legacy = self.historical_row(container, references, report["host"], report["scope"]["canonical"])
        other_row = next(row for row in report["candidates"] if row.get("specification_digest") == plans.digest(other))
        report["candidates"] = [legacy, other_row]
        old = report["plan"]
        plans.freeze_review(report, assessment, None, old["policy"]["holds"], old["policy"]["exclusions"], old["policy"]["limits"])
        plan = report["plan"]
        self.assertEqual([row["assessment"] for row in plan["candidates"]], ["Eligible", "Eligible"])
        pp, ap = fixture.base / "legacy-plan.json", fixture.base / "assessment.json"
        pp.write_text(json.dumps(plan)); ap.write_text(json.dumps(assessment))
        return fixture, plan, pp, ap, assessment, native_npm

    def preservation(self, fixture):
        return {str(path.relative_to(fixture.base)): (path.read_bytes(), plans.file_identity(path.stat()))
                for path in fixture.base.rglob("*") if path.is_file() and "state" not in path.parts}

    def fail_acquisition(self, stack, *, batch=False):
        boundaries = [(docker_cleanup, "LocalDocker"), (docker_cleanup, "run_readonly"),
                      (docker_cleanup.subprocess, "run"), (plans, "_reference")]
        if batch:
            boundaries += [(plans, "read_document"), (plans, "review_scope"), (cleanup, "_snapshot"),
                           (docker_cleanup, "inspect"), (docker_cleanup, "revalidate"), (docker_cleanup, "observe"),
                           (npm_cache, "revalidate"), (npm_cache, "observe"), (git_worktree, "inspect"),
                           (git_worktree, "observe"), (git_worktree, "_git")]
        return [stack.enter_context(patch.object(owner, name, side_effect=AssertionError("forbidden acquisition: " + name)))
                for owner, name in boundaries]

    def test_container_removal_unavailable_before_provider_for_all_entrypoints(self):
        fixture, plan, pp, ap, assessment, _ = self.fixture()
        original = assessment["candidates"][0]
        variants = [({}, {}), ({"SizeRw": 4096}, {}), ({"State": {"Status": "created", "Running": False, "Restarting": False}}, {}),
                    ({"State": {"Status": "running", "Running": True, "Restarting": False}}, {}),
                    ({"State": {"Status": "restarting", "Running": False, "Restarting": True}}, {}),
                    ({"Mounts": [{"Type": "volume"}]}, {}), ({"HostConfig": {"Binds": ["/fictional:/data"]}}, {}),
                    ({"Config": {"Volumes": {"/data": {}}}}, {}), ({"HostConfig": {"ReadonlyRootfs": True}}, {}),
                    ({"reported_diff": "A /fictional"}, {}), ({}, {"unlabelled": True}), ({}, {"rebuild": True})]
        for record_changes, options in variants:
            with self.subTest(record_changes=record_changes, options=options):
                spec = copy.deepcopy(original)
                if options.get("unlabelled"): spec["docker"].pop("ownership_label")
                if options.get("rebuild"): spec["recovery"] = {"kind": "rebuild", "basis": ["decision"], "inputs": ["decision"]}
                historical = self.historical_row(spec, assessment["references"], plan["host"], plan["review_context"]["selected"],
                                                 {**InspectedDocker.record, **record_changes})
                with ExitStack() as stack:
                    guards = self.fail_acquisition(stack)
                    policy = stack.enter_context(patch.object(docker_cleanup, "require_removal_supported", wraps=docker_cleanup.require_removal_supported))
                    inspect_spy = stack.enter_context(patch.object(docker_cleanup, "inspect", wraps=docker_cleanup.inspect))
                    review_spy = stack.enter_context(patch.object(docker_cleanup, "review", wraps=docker_cleanup.review))
                    with self.assertRaises(docker_cleanup._ContainerRemovalUnavailable) as refused:
                        docker_cleanup.inspect(spec["docker"], spec["operation"])
                    self.assertEqual(str(refused.exception), REFUSAL_REASON)
                    row = docker_cleanup.review(spec, assessment["references"], plan["host"], plan["review_context"]["selected"], timeout=10)
                    self.assertEqual((row["assessment"], row["reason"], row["references"]), ("Unavailable", REFUSAL_REASON, {}))
                    self.assertNotIn("native", row); self.assertNotIn("observation", row)
                    with self.assertRaisesRegex(ValueError, "^Docker identity/content/configuration/evidence/consumer drift$"):
                        docker_cleanup.revalidate(historical, spec, assessment["references"], (), 10)
                    with self.assertRaises(docker_cleanup._ContainerRemovalUnavailable) as refused:
                        docker_cleanup.remove(historical, plan["policy"]["limits"])
                    self.assertEqual(str(refused.exception), REFUSAL_REASON)
                    self.assertEqual([call.args for call in policy.call_args_list], [("docker-container-remove",)] * 4)
                    self.assertEqual(inspect_spy.call_count, 4); self.assertEqual(review_spy.call_count, 2)
                    for call in inspect_spy.call_args_list: self.assertEqual(call.args[:2], (spec["docker"], "docker-container-remove"))
                    for guard in guards: guard.assert_not_called()

    def test_container_refusal_preserves_validation_and_protective_precedence(self):
        fixture, plan, pp, ap, assessment, _ = self.fixture()
        for version in (3, 4):
            valid = {**assessment, "schema_version": version}
            plans._validate_assessment(valid)
            for change in ("operation", "field", "id", "endpoint", "command", "duplicate", "alias"):
                bad = copy.deepcopy(valid); spec = bad["candidates"][0]
                if change == "operation": spec["operation"] = "docker-unknown-remove"
                elif change == "field": spec["injected"] = "value"
                elif change == "id": spec["docker"]["id"] = "abc"
                elif change == "endpoint": spec["docker"]["endpoint"] = "tcp://remote:2375"
                elif change == "command": spec["docker"]["command"] = "remove"
                else:
                    alias = copy.deepcopy(spec)
                    if change == "alias": alias["docker"]["endpoint"] = "unix:///private/tmp/another.sock"
                    bad["candidates"].append(alias)
                with self.subTest(version=version, change=change), self.assertRaises(ValueError): plans._validate_assessment(bad)
        with ExitStack() as stack:
            guards = self.fail_acquisition(stack)
            policy = stack.enter_context(patch.object(docker_cleanup, "require_removal_supported", wraps=docker_cleanup.require_removal_supported))
            with self.assertRaisesRegex(ValueError, "full exact Docker resource ID required"):
                docker_cleanup.inspect({**container_resource(), "id": "bad"}, "docker-container-remove")
            policy.assert_not_called()
            for protective in ("blocked", "finding", "active"):
                spec = copy.deepcopy(assessment["candidates"][0])
                if protective == "finding": spec["findings"] = ["protected"]
                if protective == "active": spec["consumers"][0]["state"] = "active"
                row = docker_cleanup.review(spec, assessment["references"], plan["host"], str(fixture.project), timeout=10,
                                            blocked="held" if protective == "blocked" else None)
                self.assertEqual(row["assessment"], "Keep")
            policy.assert_not_called()
            for guard in guards: guard.assert_not_called()
        with patch.object(docker_cleanup, "LocalDocker", side_effect=AssertionError("no provider")):
            for policy_name in ("holds", "exclusions"):
                report = plans.review_scope(fixture.project, assessment=assessment, **{policy_name: [container_resource()["endpoint"][7:]]})
                self.assertEqual(next(row for row in report["candidates"] if docker_cleanup.is_docker(row))["assessment"], "Keep")

    def test_legacy_container_admission_precedes_all_revalidation_acquisition(self):
        completed = {}
        for operation in ("docker-image-remove", "docker-cache-remove", "npm-cache-remove"):
            _, historical_plan, _, _, _, _ = self.fixture(4, operation)
            completed[operation] = copy.deepcopy(historical_plan["candidates"][1])
            completed["docker-container-remove"] = copy.deepcopy(historical_plan["candidates"][0])
        # Explicit historical completed-worktree shape, never an asserted Git effect.
        worktree = copy.deepcopy(completed["docker-container-remove"])
        worktree.update(operation="git-worktree-remove", path="/fixture/completed-worktree", effect=git_worktree.EFFECT,
                        native={"repository": "/fixture/repository", "repository_identity": {}, "common_directory": "/fixture/common",
                                "common_identity": {}, "administration": "/fixture/common/worktrees/completed", "administration_identity": {},
                                "administration_state": {}, "marker_identity": {}, "target_identity": {}, "head": "e" * 40,
                                "retained_ref": "refs/heads/fixture", "worktrees": [], "executable": "/fixture/git", "executable_identity": {}, "ignored": []})
        completed_rows = [(), *((row,) for row in completed.values()), (worktree,)]
        for version in (3, 4):
            companions = ["directory-remove", "docker-image-remove", "docker-cache-remove"] + (["npm-cache-remove"] if version == 4 else [])
            for companion in companions:
                fixture, plan, pp, ap, assessment, _ = self.fixture(version, companion)
                before = self.preservation(fixture)
                for reverse in (False, True):
                    ids = [row["id"] for row in plan["candidates"]][::(-1 if reverse else 1)]
                    selected = plans.validate_selection(plan, ids)
                    for completed in completed_rows:
                        with self.subTest(version=version, companion=companion, reverse=reverse, completed=completed), ExitStack() as stack:
                            guards = self.fail_acquisition(stack, batch=True)
                            policy = stack.enter_context(patch.object(docker_cleanup, "require_removal_supported", wraps=docker_cleanup.require_removal_supported))
                            with self.assertRaises(docker_cleanup._ContainerRemovalUnavailable) as refused:
                                cleanup._revalidate(plan, selected, ap, None, None, completed)
                            self.assertEqual(str(refused.exception), REFUSAL_REASON)
                            self.assertIn(("docker-container-remove",), [call.args for call in policy.call_args_list])
                            for guard in guards: guard.assert_not_called()
                self.assertEqual(self.preservation(fixture), before)

        from test_generated_output import GeneratedOutputFixture
        from devspace import exact_file
        generated=GeneratedOutputFixture(); generated.setUp(); self.addCleanup(generated.doCleanups)
        result=generated.reviewed(generated.decided()); generated_rows=generated.explicit(result)
        _,historical,_,_,_,_=self.fixture(4)
        container=historical['candidates'][0]
        for output in generated_rows:
            for selected in ([output,container],[container,output]):
                frozen=copy.deepcopy(result['plan']); frozen['candidates']=selected
                frozen['digest']=plans.digest({k:v for k,v in frozen.items() if k!='digest'})
                plans.validate_selection(frozen,[r['id'] for r in selected])
                for done in [*completed_rows,tuple(generated_rows)]:
                    with self.subTest(version=6,operation=output['operation'],completed=done),ExitStack() as stack:
                        guards=self.fail_acquisition(stack,batch=True)
                        guards.append(stack.enter_context(patch.object(exact_file,'snapshot',side_effect=AssertionError('file snapshot before admission'))))
                        guards.append(stack.enter_context(patch.object(exact_file,'observe',side_effect=AssertionError('completed file observation before admission'))))
                        policy=stack.enter_context(patch.object(docker_cleanup,'require_removal_supported',wraps=docker_cleanup.require_removal_supported))
                        with self.assertRaises(docker_cleanup._ContainerRemovalUnavailable) as refused:cleanup._revalidate(frozen,selected,None,None,None,done)
                        self.assertEqual(str(refused.exception),REFUSAL_REASON)
                        self.assertIn(('docker-container-remove',),[call.args for call in policy.call_args_list])
                        for guard in guards:guard.assert_not_called()

    def test_unselected_legacy_container_does_not_block_supported_revalidation(self):
        for version in (3, 4):
            for companion in ["directory-remove", "docker-image-remove", "docker-cache-remove"] + (["npm-cache-remove"] if version == 4 else []):
                fixture, plan, pp, ap, assessment, native_npm = self.fixture(version, companion)
                selected = plans.validate_selection(plan, [plan["candidates"][1]["id"]])
                before = self.preservation(fixture)
                with self.subTest(version=version, companion=companion), patch.object(docker_cleanup, "LocalDocker", SupportedDocker), \
                        patch.object(npm_cache, "inspect", return_value=native_npm), \
                        patch.object(cleanup, "_snapshot") as portable_directory_snapshot, \
                        patch.object(docker_cleanup, "require_removal_supported", wraps=docker_cleanup.require_removal_supported) as policy:
                    result = cleanup._revalidate(plan, selected, ap, None, None)
                    self.assertEqual(result, selected)
                    self.assertNotIn(("docker-container-remove",), [call.args for call in policy.call_args_list])
                    if companion == "directory-remove":
                        portable_directory_snapshot.assert_called_once_with(selected[0], plan["policy"]["limits"], native=None)
                    else: portable_directory_snapshot.assert_not_called()
                self.assertEqual(self.preservation(fixture), before)

    def test_supported_image_and_cache_keep_exact_review_revalidation_removal_contracts(self):
        for operation, expected_arguments in (
                ("docker-image-remove", ["image", "rm", "--no-prune", IMAGE_ID]),
                ("docker-cache-remove", ["buildx", "prune", "--builder", "fixture", "--filter", "id=^" + "c" * 25 + "$", "--force"])):
            fixture, plan, pp, ap, assessment, _ = self.fixture(3, operation)
            row = plan["candidates"][1]
            specification = assessment["candidates"][1]
            commands = []
            def success(command, **options):
                commands.append((command, options))
                SupportedDocker.present = False
                return subprocess.CompletedProcess(command, 0)
            with self.subTest(operation=operation), patch.object(docker_cleanup, "LocalDocker", SupportedDocker), \
                    patch.object(SupportedDocker, "present", True), patch.object(subprocess, "run", side_effect=success):
                self.assertEqual(docker_cleanup.revalidate(row, specification, assessment["references"], (), 10), row)
                docker_cleanup.remove(row, plan["policy"]["limits"])
            self.assertEqual(len(commands), 1)
            self.assertEqual(commands[0][0], ["/fixture/docker", "--host", "unix:///private/tmp/fixture.sock", *expected_arguments])
            self.assertEqual(commands[0][1]["stdin"], subprocess.DEVNULL)
        resource = {"endpoint": container_resource()["endpoint"], "id": IMAGE_ID}
        with patch.object(docker_cleanup, "LocalDocker", SupportedDocker), patch.object(SupportedDocker, "read", return_value=b"retained-container-id\n"):
            with self.assertRaisesRegex(ValueError, "image has retained container consumers"):
                docker_cleanup.inspect(resource, "docker-image-remove")

    @unittest.skipUnless(sys.platform == "darwin", "tested macOS/APFS transaction")
    def test_legacy_container_plan_refuses_mixed_batch_before_confirmation(self):
        for version in (3, 4):
            for companion in ["directory-remove", "docker-image-remove", "docker-cache-remove"] + (["npm-cache-remove"] if version == 4 else []):
                fixture, plan, pp, ap, assessment, _ = self.fixture(version, companion)
                before = self.preservation(fixture)
                for reverse in (False, True):
                    ids = [row["id"] for row in plan["candidates"]][::(-1 if reverse else 1)]
                    with self.subTest(version=version, companion=companion, reverse=reverse), ExitStack() as stack:
                        stack.enter_context(patch.object(cleanup, "_state_path", return_value=fixture.base / "state"))
                        guards = self.fail_acquisition(stack)
                        for owner, name in ((cleanup, "_confirm"), (cleanup, "_remove"), (docker_cleanup, "remove"), (npm_cache, "remove"), (git_worktree, "remove")):
                            guards.append(stack.enter_context(patch.object(owner, name, side_effect=AssertionError("no confirmation/removal"))))
                        review_spy = stack.enter_context(patch.object(plans, "review_scope", wraps=plans.review_scope))
                        snapshot = stack.enter_context(patch.object(cleanup, "_snapshot", wraps=cleanup._snapshot))
                        policy = stack.enter_context(patch.object(docker_cleanup, "require_removal_supported", wraps=docker_cleanup.require_removal_supported))
                        with self.assertRaises(docker_cleanup._ContainerRemovalUnavailable) as refused:
                            cleanup.apply(pp, ap, ids)
                        self.assertEqual(str(refused.exception), REFUSAL_REASON)
                        policy.assert_any_call("docker-container-remove")
                        review_spy.assert_not_called(); snapshot.assert_not_called()
                        for guard in guards: guard.assert_not_called()
                    self.assertFalse(list((fixture.base / "state").glob("*.intent.json")))
                    self.assertFalse((fixture.base / "state/pending.json").exists())
                self.assertEqual(self.preservation(fixture), before)
        # Independent real APFS ordinary control, retaining the historical container unselected.
        fixture, plan, pp, ap, assessment, _ = self.fixture(4)
        selected = plans.validate_selection(plan, [plan["candidates"][1]["id"]])
        with patch.object(docker_cleanup, "LocalDocker", side_effect=AssertionError("no provider")), \
                patch.object(cleanup, "_snapshot", wraps=cleanup._snapshot) as snapshot:
            self.assertEqual(cleanup._revalidate(plan, selected, ap, None, None), selected)
        snapshot.assert_called_once()

        from test_generated_output import GeneratedOutputFixture
        from devspace import exact_file
        generated=GeneratedOutputFixture();generated.setUp();self.addCleanup(generated.doCleanups)
        output,unused,ap=generated.saved();_,historical,_,_,_,_=self.fixture(4)
        container=historical['candidates'][0]
        for candidate in generated.explicit(output):
            for selected in ([candidate,container],[container,candidate]):
                frozen=copy.deepcopy(output['plan']);frozen['candidates']=selected
                frozen['digest']=plans.digest({k:v for k,v in frozen.items() if k!='digest'})
                pp=generated.base/'docker-native-v6.json';pp.write_text(json.dumps(frozen));before=generated.survivors()
                with ExitStack() as stack:
                    stack.enter_context(patch.object(cleanup,'_state_path',return_value=generated.base/'state'))
                    guards=self.fail_acquisition(stack)
                    for owner,name in ((cleanup,'_confirm'),(cleanup,'_remove'),(exact_file,'snapshot'),(exact_file,'remove')):
                        guards.append(stack.enter_context(patch.object(owner,name,side_effect=AssertionError('no later acquisition/effect'))))
                    with self.assertRaises(docker_cleanup._ContainerRemovalUnavailable) as refused:cleanup.apply(pp,ap,[r['id'] for r in selected])
                    self.assertEqual(str(refused.exception),REFUSAL_REASON)
                    for guard in guards:guard.assert_not_called()
                self.assertEqual(before,generated.survivors());self.assertFalse((generated.base/'state/pending.json').exists())
                self.assertFalse(list((generated.base/'state').glob('*.intent.json')))

    def test_legacy_container_observe_retains_read_only_outcomes(self):
        fixture, plan, pp, ap, assessment, _ = self.fixture()
        row = plan["candidates"][0]
        class Observer(InspectedDocker):
            ids = []
            def listed_ids(self, kind):
                self_kind.append(kind)
                return self.ids
        for ids, expected in (([], "absent-provider-resource"), (["a" * 64], "same-provider-id-contents-unverified")):
            self_kind = []
            with patch.object(docker_cleanup, "LocalDocker", Observer), patch.object(Observer, "ids", ids), \
                    patch.object(docker_cleanup, "inspect", side_effect=AssertionError("observe never inspects")), \
                    patch.object(docker_cleanup, "remove", side_effect=AssertionError("observe never removes")), \
                    patch.object(subprocess, "run", side_effect=AssertionError("no mutation")):
                self.assertEqual(docker_cleanup.observe(row), expected)
                self.assertEqual(self_kind, ["container"])
        changed = copy.deepcopy(row); changed["native"]["provider"]["daemon"] = "different"
        with patch.object(docker_cleanup, "LocalDocker", Observer):
            self.assertEqual(docker_cleanup.observe(changed), "unknown-provider-identity")
        for error in (OSError("denied"), docker_cleanup.InspectionUnavailable("missing")):
            with patch.object(docker_cleanup, "LocalDocker", side_effect=error):
                self.assertEqual(docker_cleanup.observe(row), "unknown-provider-state")

    @unittest.skipUnless(sys.platform == "darwin", "tested macOS/APFS durable reconciliation")
    def test_legacy_container_pending_reconcile_remains_observation_only(self):
        for version in (3, 4):
            for outcome in ("absent-provider-resource", "same-provider-id-contents-unverified", "unknown-provider-identity", "unknown-provider-state"):
                fixture, plan, pp, ap, assessment, _ = self.fixture(version)
                row = plans.validate_selection(plan, [plan["candidates"][0]["id"]])[0]
                operation_id = "d" * 32
                intent = {"schema_version": version, "operation_id": operation_id, "operation": cleanup._operation(plan),
                          "plan_digest": plan["digest"], "host": cleanup._receipt_host(plan), "warnings": cleanup._warnings(plan),
                          "outcome": "intent", "targets": [cleanup._target_record(row, "not-started")],
                          "measurement": cleanup._measurement({cleanup._device(row): None}, {})}
                state_path = fixture.base / "state"
                with patch.object(cleanup, "_state_path", return_value=state_path):
                    with cleanup.State(plan["scope_roots"]) as state:
                        state.write(operation_id + ".intent.json", intent)
                        state.write("pending.json", {"schema_version": version, "operation_id": operation_id, "plan_digest": plan["digest"],
                                                     "host": cleanup._receipt_host(plan), "intent_digest": plans.digest(intent)})
                    original = (state_path / (operation_id + ".intent.json")).read_bytes()
                    before = self.preservation(fixture)
                    with self.subTest(version=version, outcome=outcome), patch.object(docker_cleanup, "observe", return_value=outcome) as observer, \
                            patch.object(docker_cleanup, "inspect", side_effect=AssertionError("no inspect")), \
                            patch.object(docker_cleanup, "remove", side_effect=AssertionError("no retry")), \
                            patch.object(subprocess, "run", side_effect=AssertionError("no mutation process")):
                        result = cleanup.reconcile(pp)
                    observer.assert_called_once_with(row)
                self.assertEqual(result["outcome"], "reconciled-no-retry")
                self.assertEqual(result["targets"][0]["outcome"], outcome)
                self.assertEqual(result["targets"][0]["resource_id"], "a" * 64)
                self.assertEqual((state_path / (operation_id + ".intent.json")).read_bytes(), original)
                self.assertFalse((state_path / "pending.json").exists())
                self.assertEqual(len(list(state_path.glob("*.reconciliation.json"))), 1)
                self.assertEqual(self.preservation(fixture), before)
                for record in state_path.glob("*.json"):
                    self.assertNotIn(str(fixture.base), record.read_text()); self.assertNotIn("Fixture owner", record.read_text())


if __name__ == "__main__":
    unittest.main()
