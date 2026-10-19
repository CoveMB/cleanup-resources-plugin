"""Opt-in actual local Docker tests; never consume ambient user resources.

Set DEVSPACE_DOCKER_TEST_ENDPOINT, DEVSPACE_DOCKER_TEST_BUILDER (an explicitly
disposable, already-running single-node builder), and an evidence directory.
Fixtures and original command logs are retained for inspection. No default
context/builder changes, service start, pull, blanket prune or fixture teardown.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time
import unittest
import uuid
from unittest.mock import patch

import test_plans
from devspace import cleanup, docker_cleanup, plans


@unittest.skipUnless(sys.platform == "darwin" and os.environ.get("DEVSPACE_DOCKER_TEST_ENDPOINT")
                     and os.environ.get("DEVSPACE_DOCKER_TEST_BUILDER") and os.environ.get("DEVSPACE_DOCKER_TEST_EVIDENCE"),
                     "opt-in inventoried disposable Docker fixtures required")
class NativeDockerCleanup(unittest.TestCase):
    def setUp(self):
        self.endpoint = os.environ["DEVSPACE_DOCKER_TEST_ENDPOINT"]
        self.builder = os.environ["DEVSPACE_DOCKER_TEST_BUILDER"]
        self.owner = "cleanup-fixture-" + uuid.uuid4().hex[:12]
        self.base = Path(os.environ["DEVSPACE_DOCKER_TEST_EVIDENCE"]).resolve() / self.owner
        self.base.mkdir(parents=True)
        self.scope = self.base / "project"; self.scope.mkdir()
        self.inventory = {"owner": self.owner, "endpoint": self.endpoint, "builder": self.builder,
                          "containers": [], "images": [], "commands": []}
        self.references = {}
        decision = self.base / "decision.txt"
        decision.write_text("Exact agent-created synthetic fixtures with known input bytes and ownership labels; "
                            "sole test consumer releases selected artifacts with accepted loss. Untouched controls remain required. "
                            "No private source, user data, volumes or credentials are selected.")
        self.reference("decision", decision)
        self.environment = {key: value for key, value in os.environ.items()
                            if not key.startswith(("DOCKER_", "BUILDX_", "BUILDKIT_"))}

    def reference(self, key, path):
        self.references[key] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def save(self):
        (self.base / "inventory.json").write_text(json.dumps(self.inventory, indent=2))

    def docker(self, *arguments, input=None, expected=0):
        command = ["docker", "--host", self.endpoint, *arguments]
        result = subprocess.run(command, input=input, env=self.environment, capture_output=True, timeout=60)
        index = len(self.inventory["commands"])
        (self.base / f"command-{index}.log").write_bytes(result.stdout + result.stderr)
        self.inventory["commands"].append({"argv": command, "exit_code": result.returncode, "log": f"command-{index}.log"})
        self.save()
        self.assertEqual(result.returncode, expected, str(self.base / f"command-{index}.log"))
        return result.stdout.decode().strip()

    def image(self, name, labelled=True):
        payload = (self.owner + " " + name + " synthetic bytes\n").encode()
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            item = tarfile.TarInfo("synthetic.txt"); item.size = len(payload)
            archive.addfile(item, io.BytesIO(payload))
        labels = ["--change", "LABEL fixture.owner=" + self.owner] if labelled else []
        identifier = self.docker("image", "import", *labels,
                                 "--change", 'CMD ["/synthetic"]', "-", self.owner + "/" + name + ":fixture", input=buffer.getvalue())
        self.inventory["images"].append(identifier); self.save()
        return identifier

    def container(self, image, name, labelled=True):
        labels = ["--label", "fixture.owner=" + self.owner] if labelled else []
        identifier = self.docker("container", "create", *labels,
                                 "--network", "none", "--name", self.owner + "-" + name, image)
        self.inventory["containers"].append(identifier); self.save()
        return identifier

    def specification(self, operation, identifier, labelled=True):
        resource = {"endpoint": self.endpoint, "id": identifier}
        if operation == "docker-cache-remove":
            resource["builder"] = self.builder
        elif labelled:
            resource["ownership_label"] = {"key": "fixture.owner", "value": self.owner}
        native = docker_cleanup.inspect(resource, operation, timeout=30)
        key = str(len(self.references))
        expected = self.base / (key + "-expected.json")
        expected.write_text(json.dumps({"schema_version": 1, "native_digest": plans.digest(native)}))
        self.reference(key, expected)
        return {"operation": operation, "docker": resource, "category": "synthetic-native", "purpose": "released synthetic fixture",
                "content": {"method": "native-inspection", "reference": key, "basis": ["decision"]},
                "recovery": {"kind": "accepted-loss", "basis": ["decision"]},
                "consumer_scope": {"basis": ["decision"], "unresolved": []},
                "consumers": [{"id": self.owner, "state": "released", "basis": ["decision"]}],
                "release": {"basis": ["decision"], "checkpoint": "synthetic inputs retained, selected output released"}, "findings": []}

    def freeze(self, specifications):
        self.assessment = {"schema_version": 3, "references": self.references, "candidates": specifications}
        report = plans.review_scope(self.scope, assessment=self.assessment, timeout=120)
        self.plan = report["plan"]
        self.plan_path = self.base / "plan.json"; plans.write_plan(self.plan_path, self.plan)
        self.assessment_path = self.base / "assessment.json"; self.assessment_path.write_text(json.dumps(self.assessment))
        self.ids = [row["id"] for row in report["candidates"] if row["assessment"] == "Eligible"]
        self.assertEqual(len(self.ids), len(specifications), report["candidates"])

    def apply(self):
        with patch.object(cleanup, "_state_path", return_value=self.base / "private-state"), patch.object(cleanup, "_confirm", return_value=True):
            result = cleanup.apply(self.plan_path, self.assessment_path, self.ids)
        (self.base / "result.json").write_text(json.dumps(result, indent=2))
        return result

    def reconcile(self):
        with patch.object(cleanup, "_state_path", return_value=self.base / "private-state"), \
                patch.object(docker_cleanup, "remove", side_effect=AssertionError("reconcile cannot mutate")):
            result = cleanup.reconcile(self.plan_path)
        (self.base / "reconciliation.json").write_text(json.dumps(result, indent=2))
        return result

    def test_mixed_directory_container_image_parent_and_cache_effects(self):
        parent = self.image("parent")
        selected_container = self.container(parent, "selected")
        control = self.container(parent, "untouched")
        source = self.container(parent, "child-source")
        child = self.docker("container", "commit", "--no-pause", "--change", "LABEL fixture.owner=" + self.owner,
                            source, self.owner + "/child:fixture")
        self.inventory["images"].append(child); self.save()
        context = self.base / "synthetic-context"; context.mkdir()
        (context / "Dockerfile").write_text("FROM scratch\nCOPY payload /fixture-payload\n")
        before_cache = docker_cleanup.LocalDocker(self.endpoint, 30).cache(self.builder)
        for name in ("selected", "control"):
            (context / "payload").write_text(self.owner + " " + name)
            self.docker("buildx", "build", "--builder", self.builder, "--progress", "plain", str(context))
        cache = docker_cleanup.LocalDocker(self.endpoint, 30).cache(self.builder)
        previous = {row["id"] for row in before_cache}
        created = [row for row in cache if row["id"] not in previous and row["type"] == "regular" and row["reclaimable"]]
        self.assertEqual(len(created), 2, created)
        self.inventory["cache_ids"] = [row["id"] for row in created]; self.save()
        selected_cache = created[0]["id"]
        retained = self.base / "directory-source.txt"; retained.write_bytes(b"ordinary fixture library\n"); retained.chmod(0o644)
        self.reference("directory-source", retained)
        directory = self.scope / "generated"; directory.mkdir()
        (directory / "data.txt").write_bytes(retained.read_bytes()); (directory / "data.txt").chmod(0o644)
        directory_spec = {"path": str(directory), "operation": "directory-remove", "category": "output", "purpose": "released synthetic directory",
                          "content": {"method": "source-files", "files": {"data.txt": "directory-source"}, "basis": ["decision"]},
                          "recovery": {"kind": "accepted-loss", "basis": ["decision"]},
                          "consumer_scope": {"basis": ["decision"], "unresolved": []},
                          "consumers": [{"id": self.owner, "state": "released", "basis": ["decision"]}],
                          "release": {"basis": ["decision"], "checkpoint": "synthetic output released"}, "findings": []}
        self.freeze([directory_spec, self.specification("docker-container-remove", selected_container),
                     self.specification("docker-image-remove", child), self.specification("docker-cache-remove", selected_cache)])
        baseline = docker_cleanup.LocalDocker(self.endpoint, 30)
        before_images, before_containers = baseline.listed_ids("image"), baseline.listed_ids("container")
        result = self.apply(); self.assertEqual(result["outcome"], "completed", result)
        after = docker_cleanup.LocalDocker(self.endpoint, 30)
        self.assertEqual(set(before_images) - set(after.listed_ids("image")), {child})
        self.assertEqual(set(before_containers) - set(after.listed_ids("container")), {selected_container})
        self.assertEqual(after.cache(self.builder), [row for row in cache if row["id"] != selected_cache])
        self.assertFalse(directory.exists()); self.assertIn(parent, after.listed_ids("image")); self.assertIn(control, after.listed_ids("container"))

    def test_native_refusal_after_first_success_stops_and_reconciles(self):
        parent = self.image("parent")
        first, later = self.container(parent, "first"), self.container(parent, "later")
        image = self.image("refused")
        self.freeze([self.specification("docker-container-remove", first), self.specification("docker-image-remove", image),
                     self.specification("docker-container-remove", later)])
        real_run = subprocess.run
        def inject_conflict(command, **options):
            if "image" in command and "rm" in command:
                tagged = real_run(["docker", "--host", self.endpoint, "image", "tag", image, self.owner + "/retained-conflict:fixture"],
                                  env=self.environment, capture_output=True, timeout=30)
                self.assertEqual(tagged.returncode, 0)
            return real_run(command, **options)
        with patch.object(docker_cleanup.subprocess, "run", side_effect=inject_conflict):
            result = self.apply()
        self.assertEqual(result["outcome"], "partial-or-failed", result)
        self.assertEqual(result["native_failure"], {"kind": "native-refusal", "exit_code": 1})
        self.assertEqual([row["outcome"] for row in result["targets"]], ["removed", "started-outcome-unknown", "not-started"])
        observed = self.reconcile()
        self.assertEqual([row["outcome"] for row in observed["targets"]],
                         ["absent-provider-resource", "same-provider-id-contents-unverified", "same-provider-id-contents-unverified"])

    def test_actual_provider_name_drift_refuses_before_confirmation(self):
        parent = self.image("parent"); container = self.container(parent, "renamed")
        self.freeze([self.specification("docker-container-remove", container)])
        self.docker("container", "rename", container, self.owner + "-external-name-drift")
        with patch.object(cleanup, "_state_path", return_value=self.base / "private-state"), \
                patch.object(cleanup, "_confirm", side_effect=AssertionError("drift must precede confirmation")):
            with self.assertRaises(ValueError):
                cleanup.apply(self.plan_path, self.assessment_path, self.ids)
        self.assertIn(container, docker_cleanup.LocalDocker(self.endpoint, 30).listed_ids("container"))

    def test_unlabelled_existing_resources_qualify_from_specific_evidence(self):
        parent = self.image("unlabelled-parent", labelled=False)
        container = self.container(parent, "unlabelled", labelled=False)
        image = self.image("unlabelled-unused", labelled=False)
        docker = docker_cleanup.LocalDocker(self.endpoint, 30)
        self.assertFalse(docker.container(container)["Config"].get("Labels"))
        self.assertFalse(docker.image(image)["Config"].get("Labels"))
        self.freeze([self.specification("docker-container-remove", container, labelled=False),
                     self.specification("docker-image-remove", image, labelled=False)])
        result = self.apply()
        self.assertEqual(result["outcome"], "completed", result)
        after = docker_cleanup.LocalDocker(self.endpoint, 30)
        self.assertNotIn(container, after.listed_ids("container"))
        self.assertNotIn(image, after.listed_ids("image"))
        self.assertIn(parent, after.listed_ids("image"))

    def test_timeout_after_actual_native_success_reconciles_without_retry(self):
        parent = self.image("parent"); container = self.container(parent, "timeout")
        self.freeze([self.specification("docker-container-remove", container)])
        real_run = subprocess.run
        def timeout_after(command, **options):
            result = real_run(command, **options); self.assertEqual(result.returncode, 0)
            raise subprocess.TimeoutExpired(command, options["timeout"])
        with patch.object(docker_cleanup.subprocess, "run", side_effect=timeout_after):
            result = self.apply()
        self.assertEqual(result["outcome"], "partial-or-failed")
        self.assertEqual(result["native_failure"]["kind"], "native-timeout-outcome-unknown")
        self.assertEqual(self.reconcile()["targets"][0]["outcome"], "absent-provider-resource")

    @unittest.skipUnless(os.environ.get("DEVSPACE_DOCKER_TEST_PUBLIC_IMAGE"), "selected public immutable BusyBox fixture input required")
    def test_active_cache_records_remain_protected_during_actual_build(self):
        import re
        image = os.environ["DEVSPACE_DOCKER_TEST_PUBLIC_IMAGE"]
        self.assertRegex(image, r"^docker\.io/library/busybox@sha256:[0-9a-f]{64}$")
        context = self.base / "active-synthetic-context"; context.mkdir()
        (context / "Dockerfile").write_text("FROM " + image + "\nRUN sleep 25\n")
        command = ["docker", "--host", self.endpoint, "buildx", "build", "--builder", self.builder,
                   "--progress", "plain", str(context)]
        self.inventory["active_build"] = {"argv": command, "public_input": image}; self.save()
        with (self.base / "active-build.log").open("wb") as log:
            process = subprocess.Popen(command, env=self.environment, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 45
                active = []
                while time.monotonic() < deadline and process.poll() is None:
                    records = docker_cleanup.LocalDocker(self.endpoint, 10).cache(self.builder)
                    active = [row for row in records if row["type"] == "regular" and not row["reclaimable"]]
                    if active:
                        break
                    time.sleep(0.5)
                self.assertTrue(active, "no actual active cache observation; inspect retained build log")
                self.inventory["observed_active_cache_ids"] = [row["id"] for row in active]; self.save()
                for record in active:
                    resource = {"endpoint": self.endpoint, "builder": self.builder, "id": record["id"]}
                    with self.assertRaises(ValueError):
                        docker_cleanup.inspect(resource, "docker-cache-remove", timeout=10)
                observed = docker_cleanup.LocalDocker(self.endpoint, 10).cache(self.builder)
                self.assertTrue({row["id"] for row in active} <= {row["id"] for row in observed})
            finally:
                code = process.wait(timeout=60)
                self.inventory["active_build"]["exit_code"] = code; self.save()
            self.assertEqual(code, 0, str(self.base / "active-build.log"))

    @unittest.skipUnless(os.environ.get("DEVSPACE_DOCKER_TEST_DEFAULT_CACHE") == "1", "explicit scoped default-builder fixture trial required")
    def test_default_builder_exact_owned_markers_partial_timeout_and_reconcile(self):
        self.assertEqual(self.builder, "default")
        docker = docker_cleanup.LocalDocker(self.endpoint, 30)
        provider, worker = docker.identity, docker.builder("default")
        baseline = docker.cache("default")
        baseline_ids = {row["id"] for row in baseline}
        self.inventory["preexisting_cache_ids"] = sorted(baseline_ids)
        self.inventory["preexisting_cache_digest"] = plans.digest(baseline)
        marker = "fixture-" + uuid.uuid4().hex
        context = self.base / marker; context.mkdir()
        selected = {}
        for kind in ("first", "timeout", "control"):
            destination = "/" + marker + "-" + kind + "/payload"
            (context / "payload").write_text(marker + " " + kind + " synthetic unique input\n")
            (context / "Dockerfile").write_text("FROM scratch AS " + marker + "-" + kind + "\nCOPY payload " + destination + "\n")
            self.docker("buildx", "build", "--builder", "default", "--no-cache", "--output", "type=cacheonly",
                        "--progress", "plain", str(context))
            current = docker_cleanup.LocalDocker(self.endpoint, 30)
            self.assertEqual(current.identity, provider)
            self.assertEqual(current.builder("default"), worker)
            records = current.cache("default")
            self.assertTrue(baseline_ids <= {row["id"] for row in records}, "pre-existing record disappeared; stop fixture trial")
            raw = [json.loads(line) for line in current.read("buildx", "du", "--builder", "default", "--format=json").splitlines()]
            owned = [row for row in raw if row["ID"] not in baseline_ids and row["Type"] == "regular"
                     and marker + "-" + kind in row["Description"] and destination in row["Description"]]
            self.assertEqual(len(owned), 1, "new IDs alone cannot establish ownership; exact build marker required")
            selected[kind] = owned[0]["ID"]
            self.inventory.setdefault("attributed_cache_records", []).append({"id": owned[0]["ID"],
                "description": owned[0]["Description"], "marker": marker, "kind": kind})
            self.save()
        self.assertEqual(len(set(selected.values())), 3)
        before_removal = docker_cleanup.LocalDocker(self.endpoint, 30).cache("default")
        for kind in ("first", "timeout"):
            record = next(row for row in before_removal if row["id"] == selected[kind])
            self.assertEqual(docker_cleanup.LocalDocker(self.endpoint, 30).cache("default", selected[kind]), [record])
        self.freeze([self.specification("docker-cache-remove", selected[kind]) for kind in ("first", "timeout")])
        real_run = subprocess.run
        def timeout_after_second(command, **options):
            result = real_run(command, **options)
            self.assertEqual(result.returncode, 0)
            if docker_cleanup.cache_filter(selected["timeout"]) in command:
                raise subprocess.TimeoutExpired(command, options["timeout"])
            return result
        with patch.object(docker_cleanup.subprocess, "run", side_effect=timeout_after_second):
            result = self.apply()
        self.assertEqual(result["outcome"], "partial-or-failed", result)
        self.assertEqual([row["outcome"] for row in result["targets"]], ["removed", "started-outcome-unknown"])
        self.assertEqual(result["native_failure"]["kind"], "native-timeout-outcome-unknown")
        observed = self.reconcile()
        self.assertEqual([row["outcome"] for row in observed["targets"]], ["absent-provider-resource"] * 2)
        after = docker_cleanup.LocalDocker(self.endpoint, 30)
        self.assertEqual(after.identity, provider); self.assertEqual(after.builder("default"), worker)
        records = after.cache("default")
        removed = {selected["first"], selected["timeout"]}
        self.assertEqual(records, [row for row in before_removal if row["id"] not in removed])
        self.assertTrue(baseline_ids <= {row["id"] for row in records})
        self.assertIn(selected["control"], {row["id"] for row in records})
        self.inventory["preexisting_ids_preserved"] = True
        self.inventory["preexisting_bookkeeping_changes"] = sum(row != next(current for current in records if current["id"] == row["id"]) for row in baseline)
        self.save()
