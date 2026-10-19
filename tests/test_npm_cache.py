"""Actual isolated npm effects; no network, credentials or ambient cache mutation."""
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_plans
from devspace import plans, cleanup


def native_tools():
    npm = shutil.which("npm")
    node = shutil.which("node")
    if not npm or not node:
        return None
    if Path(npm).resolve().name == "volta-shim":
        npm = subprocess.check_output(["volta", "which", "npm"], cwd="/", text=True).strip()
    cli = Path(npm).resolve()
    root = cli.parent.parent
    if not (root / "package.json").is_file() or json.loads((root / "package.json").read_bytes()).get("version") != "11.17.0":
        return None
    cacache = root / "node_modules/cacache"
    if json.loads((cacache / "package.json").read_bytes()).get("version") != "20.0.4":
        return None
    node = subprocess.check_output([node, "-p", "process.execPath"], cwd="/", text=True).strip()
    return node, str(cli), str(cacache)


TOOLS = native_tools()


@unittest.skipUnless(TOOLS, "optional verified npm 11.17.0/cacache 20.0.4 unavailable")
class NativeCache(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="npm-cleanup-native-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.cache = self.base / "cache"
        self.cache.mkdir()
        self.project = self.base / "project"
        self.project.mkdir()
        self.records = self.base / "records"
        self.records.mkdir()
        # Independent synthetic source bytes; never derive a baseline from cache.
        self.payloads = {"selected": b"selected generated download\n" * 8192,
                         "second": b"second generated download\n" * 4096,
                         "shared": b"shared retained download\n",
                         "active": b"required active download\n",
                         "offline": b"only offline download\n",
                         "unknown": b"unknown ownership download\n"}
        for key, payload in self.payloads.items():
            (self.records / key).write_bytes(payload)
            self.put(key, payload)
        self.put("shared-alias", self.payloads["shared"])
        (self.cache / "unrelated.txt").write_bytes(b"retained neighboring application data")
        (self.cache / ".npmrc").write_bytes(b"synthetic credential marker never read")
        self.context = self.records / "context.txt"
        self.context.write_text("Synthetic fixture owner released selected and second. Sources are retained; downloads can be regenerated locally. Shared aliases, active and offline data are required; unknown has no ownership decision. No consumer remains for selected/second. No human technical form or duplicate build.")

    def put(self, key, payload):
        script = "require(process.argv[1]).put(process.argv[2],process.argv[3],Buffer.from(process.argv[4],'base64')).catch(()=>process.exit(1))"
        result = subprocess.run([TOOLS[0], "-e", script, TOOLS[2], str(self.cache / "_cacache"), key,
                                 base64.b64encode(payload).decode()], capture_output=True, timeout=10,
                                env={"PATH": os.defpath, "HOME": str(self.base)}, cwd="/")
        self.assertEqual(result.returncode, 0, result.stderr)

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec("devspace.npm_cache"), "native npm cache operation is missing")
        from devspace import npm_cache
        return npm_cache

    def assessment(self, keys=("selected", "second")):
        references = {}
        candidates = []
        for key in (*keys, "context"):
            path = self.records / key if key != "context" else self.context
            references[key] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for key in keys:
            candidates.append({"operation": "npm-cache-remove", "npm": {
                "cache": str(self.cache), "key": key,
                "integrity": "sha512-" + base64.b64encode(hashlib.sha512(self.payloads[key]).digest()).decode()},
                "category": "cache", "purpose": "released reproducible download " + key,
                "content": {"method": "source-file", "reference": key, "basis": ["context"]},
                "recovery": {"kind": "rebuild", "inputs": [key], "basis": ["context"],
                             "explanation": "Retained source regenerates fixture; ordinary caches may need network downloads and lose offline availability."},
                "consumer_scope": {"basis": ["context"], "unresolved": []},
                "consumers": [{"id": "fixture", "state": "released", "basis": ["context"]}],
                "release": {"checkpoint": "synthetic download completed", "basis": ["context"]}, "findings": []})
        return {"schema_version": 4, "references": references, "candidates": candidates}

    def freeze(self, assessment=None):
        assessment = assessment or self.assessment()
        report = plans.review_scope(self.project, assessment=assessment, timeout=30)
        ap, pp = self.base / "assessment.json", self.base / "plan.json"
        ap.write_bytes(plans.canonical_json(assessment))
        plans.write_plan(pp, report["plan"])
        return ap, pp, report

    def test_discovery_reports_ranked_unique_content_and_shared_preservation(self):
        # Missing native discovery must fail before any production implementation.
        report = plans.review_scope(self.project, npm_caches=[str(self.cache)], timeout=30)
        inventory = report["npm_caches"][0]
        self.assertEqual(inventory["coverage"], "examined")
        self.assertEqual(inventory["entries"][0]["key"], "selected")
        shared = next(row for row in inventory["entries"] if row["key"] == "shared")
        self.assertEqual(shared["assessment"], "Keep")
        self.assertEqual(shared["aliases"], ["shared", "shared-alias"])
        self.assertEqual(inventory["unique_content_bytes"], sum(map(len, self.payloads.values())))

    @unittest.skipUnless(sys.platform == "darwin", "enabled macOS/APFS mutation")
    def test_two_selected_native_entries_removed_with_all_retained_controls(self):
        module = self.module()
        ap, pp, report = self.freeze()
        self.assertEqual([row["assessment"] for row in report["candidates"]], ["Eligible", "Eligible"])
        with patch.object(cleanup, "_state_path", return_value=self.base / "state"), patch.object(cleanup, "_confirm", return_value=True):
            result = cleanup.apply(pp, ap, [], all_eligible=True)
        self.assertEqual(result["outcome"], "completed", result)
        self.assertEqual([row["outcome"] for row in result["targets"]], ["removed", "removed"])
        remaining = module.inventory(str(self.cache), timeout=30)
        self.assertEqual({row["key"] for row in remaining["entries"]}, {"active", "offline", "unknown", "shared", "shared-alias"})
        for key in ("active", "offline", "unknown", "shared"):
            content = next(row for row in remaining["entries"] if row["key"] == key)
            self.assertEqual(content["integrity"], "sha512-" + base64.b64encode(hashlib.sha512(self.payloads[key]).digest()).decode())
            hexadecimal = hashlib.sha512(self.payloads[key]).hexdigest()
            backing = self.cache / "_cacache/content-v2/sha512" / hexadecimal[:2] / hexadecimal[2:4] / hexadecimal[4:]
            self.assertEqual(backing.read_bytes(), self.payloads[key])
        self.assertEqual((self.cache / "unrelated.txt").read_bytes(), b"retained neighboring application data")
        self.assertEqual((self.cache / ".npmrc").read_bytes(), b"synthetic credential marker never read")
        serialized = json.dumps(result)
        self.assertNotIn(str(self.base), serialized)
        self.assertNotIn("synthetic credential", serialized)
        self.assertNotIn("released reproducible", serialized)

    def test_shared_aliases_active_offline_unknown_and_modified_are_protected(self):
        self.module()
        assessment = self.assessment(("shared", "active", "offline", "unknown", "selected"))
        assessment["candidates"][1]["consumers"][0]["state"] = "active"
        assessment["candidates"][2]["findings"] = [{"kind": "offline-dependency", "basis": ["context"]}]
        assessment["candidates"][3]["consumer_scope"]["unresolved"] = ["owner need unknown"]
        self.put("selected", b"modified unknown bytes")
        report = plans.review_scope(self.project, assessment=assessment, timeout=30)
        self.assertTrue(all(row["assessment"] != "Eligible" for row in report["candidates"]))
        self.assertEqual(report["candidates"][1]["assessment"], "Keep")
        self.assertEqual(report["candidates"][2]["assessment"], "Keep")

    def test_trusted_lockfile_avoids_duplicate_payload_or_redownload_requirement(self):
        key = "make-fetch-happen:request-cache:https://registry.npmjs.org/fixture/-/fixture-1.0.0.tgz"
        self.put(key, b"independent fixture tarball\n")
        integrity = "sha512-" + base64.b64encode(hashlib.sha512(b"independent fixture tarball\n").digest()).decode()
        lock = self.records / "package-lock.json"
        lock.write_text(json.dumps({"lockfileVersion": 3, "packages": {"node_modules/fixture": {
            "version": "1.0.0", "resolved": key.split("request-cache:", 1)[1], "integrity": integrity}}}))
        assessment = self.assessment(("selected",))
        assessment["references"]["lock"] = {"path": str(lock), "sha256": hashlib.sha256(lock.read_bytes()).hexdigest()}
        candidate = assessment["candidates"][0]
        candidate["npm"].update(key=key, integrity=integrity)
        candidate["content"].update(method="npm-lock", reference="lock")
        candidate["recovery"]["inputs"] = ["lock"]
        assessment["references"].pop("selected")
        (self.records / "selected").unlink()
        report = plans.review_scope(self.project, assessment=assessment, timeout=30)
        self.assertEqual(report["candidates"][0]["assessment"], "Eligible")
        lock.write_text(json.dumps({"lockfileVersion": 3, "packages": {"node_modules/fixture": {
            "resolved": "https://different.invalid/unrelated.tgz", "integrity": integrity}}}))
        assessment["references"]["lock"]["sha256"] = hashlib.sha256(lock.read_bytes()).hexdigest()
        self.assertEqual(plans.review_scope(self.project, assessment=assessment, timeout=30)["candidates"][0]["assessment"], "Review")

    @unittest.skipUnless(sys.platform == "darwin", "enabled macOS/APFS mutation")
    def test_new_unselected_entry_and_alias_drift_prevent_confirmation(self):
        for key, payload in (("newer-unselected", b"new unrelated bytes"), ("new-alias", self.payloads["selected"])):
            with self.subTest(key=key):
                ap, pp, report = self.freeze()
                self.put(key, payload)
                with patch.object(cleanup, "_state_path", return_value=self.base / "state"), \
                        patch.object(cleanup, "_confirm", side_effect=AssertionError("drift must refuse before confirmation")):
                    with self.assertRaises(ValueError):
                        cleanup.apply(pp, ap, [], all_eligible=True)
                pp.unlink()

    @unittest.skipUnless(sys.platform == "darwin", "enabled macOS/APFS mutation")
    def test_partial_native_timeout_reconciles_observations_without_retry(self):
        module = self.module()
        ap, pp, report = self.freeze()
        original = subprocess.run
        def timed_out(command, **options):
            if "clean" in command:
                result = original(command, **options)
                self.assertEqual(result.returncode, 0)
                raise subprocess.TimeoutExpired(command, 1)
            return original(command, **options)
        with patch.object(cleanup, "_state_path", return_value=self.base / "state"), patch.object(cleanup, "_confirm", return_value=True):
            with patch.object(module.subprocess, "run", side_effect=timed_out):
                result = cleanup.apply(pp, ap, [], all_eligible=True)
            self.assertEqual(result["outcome"], "partial-or-failed")
            self.assertEqual(result["native_failure"]["kind"], "native-timeout-outcome-unknown")
            self.assertTrue((self.base / "state/pending.json").exists())
            with patch.object(module, "remove", side_effect=AssertionError("reconcile must not delete")):
                reconciled = cleanup.reconcile(pp)
            self.assertEqual([row["outcome"] for row in reconciled["targets"]],
                             ["absent-cache-entry-and-content", "same-cache-key-contents-unverified"])
        self.assertEqual({row["key"] for row in module.inventory(str(self.cache), timeout=30)["entries"]},
                         {"second", "active", "offline", "unknown", "shared", "shared-alias"})

    def test_symlinks_hardlinks_and_active_temporary_content_refuse(self):
        module = self.module()
        control = self.records / "retained-control"
        control.write_bytes(b"required protected data")
        link = self.cache / "_cacache/tmp/untrusted"
        link.symlink_to(control)
        with self.assertRaises(ValueError):
            module.inspect(self.assessment()["candidates"][0]["npm"], timeout=30)
        link.unlink()
        os.link(control, link)
        with self.assertRaises(ValueError):
            module.inspect(self.assessment()["candidates"][0]["npm"], timeout=30)
        self.assertEqual(control.read_bytes(), b"required protected data")

    def test_corrupt_index_cannot_hide_unknown_content_alias(self):
        module = self.module()
        bucket = next(path for path in (self.cache / "_cacache/index-v5").rglob("*") if path.is_file())
        with bucket.open("ab") as stream:
            stream.write(b'\ninvalid-checksum\t{"key":"unknown-alias","integrity":"unknown"}\n')
        with self.assertRaises(ValueError):
            module.inspect(self.assessment()["candidates"][0]["npm"], timeout=30)

    def test_alternate_integrity_spelling_cannot_hide_shared_backing_content(self):
        import time
        module = self.module()
        resource = self.assessment()["candidates"][0]["npm"]
        key = "alternate-integrity-alias"
        integrity = resource["integrity"] + " sha256-" + base64.b64encode(hashlib.sha256(self.payloads["selected"]).digest()).decode()
        record = {"key": key, "integrity": integrity, "time": int(time.time()*1000), "size": len(self.payloads["selected"])}
        encoded = json.dumps(record, separators=(",", ":")).encode()
        hexadecimal = hashlib.sha256(key.encode()).hexdigest()
        bucket = self.cache / "_cacache/index-v5" / hexadecimal[:2] / hexadecimal[2:4] / hexadecimal[4:]
        bucket.parent.mkdir(parents=True, exist_ok=True)
        bucket.write_bytes(b"\n" + hashlib.sha1(encoded).hexdigest().encode() + b"\t" + encoded)
        with self.assertRaises(ValueError):
            module.inspect(resource, timeout=30)

    @unittest.skipUnless(sys.platform == "darwin", "enabled macOS/APFS mutation")
    def test_native_key_cannot_be_interpreted_as_force_option(self):
        self.payloads["--force"] = b"literal key starting with dashes"
        self.put("--force", self.payloads["--force"])
        (self.records / "--force").write_bytes(self.payloads["--force"])
        ap, pp, report = self.freeze(self.assessment(("--force",)))
        with patch.object(cleanup, "_state_path", return_value=self.base / "state"), patch.object(cleanup, "_confirm", return_value=True):
            result = cleanup.apply(pp, ap, [], all_eligible=True)
        self.assertEqual(result["outcome"], "completed", result)
        remaining = self.module().inventory(str(self.cache), timeout=30)
        self.assertEqual({row["key"] for row in remaining["entries"]}, {"selected", "second", "shared", "shared-alias", "active", "offline", "unknown"})

    @unittest.skipUnless(sys.platform == "darwin", "enabled macOS/APFS mutation")
    def test_receipt_durability_failure_prevents_native_mutation(self):
        module = self.module()
        ap, pp, report = self.freeze()
        with patch.object(cleanup, "_state_path", return_value=self.base / "state"), patch.object(cleanup, "_confirm", return_value=True), \
                patch.object(cleanup.State, "write", side_effect=OSError("fixture durable intent refused")):
            with self.assertRaises(OSError):
                cleanup.apply(pp, ap, [], all_eligible=True)
        self.assertEqual({row["key"] for row in module.inventory(str(self.cache), timeout=30)["entries"]},
                         {"selected", "second", "shared", "shared-alias", "active", "offline", "unknown"})

    @unittest.skipUnless(sys.platform == "darwin", "enabled macOS/APFS mutation")
    def test_unregistered_generated_directory_and_native_cache_share_transaction(self):
        generated = self.project / "unregistered-generated"
        generated.mkdir()
        (generated / "download").write_bytes(self.payloads["selected"])
        (generated / "download").chmod(0o644)
        assessment = self.assessment(("selected",))
        assessment["candidates"].insert(0, {"operation": "directory-remove", "path": "unregistered-generated", "category": "output",
            "purpose": "unregistered ordinary generated fixture",
            "content": {"method": "source-files", "files": {"download": "selected"}, "directories": [], "basis": ["context"]},
            "recovery": {"kind": "rebuild", "inputs": ["selected"], "basis": ["context"], "explanation": "retained source rebuilds output"},
            "consumer_scope": {"basis": ["context"], "unresolved": []},
            "consumers": [{"id": "fixture", "state": "released", "basis": ["context"]}],
            "release": {"checkpoint": "fixture output completed", "basis": ["context"]}, "findings": []})
        ap, pp, report = self.freeze(assessment)
        self.assertEqual([row["assessment"] for row in report["candidates"]], ["Eligible", "Eligible"])
        with patch.object(cleanup, "_state_path", return_value=self.base / "state"), patch.object(cleanup, "_confirm", return_value=True):
            result = cleanup.apply(pp, ap, [], all_eligible=True)
        self.assertEqual(result["outcome"], "completed", result)
        self.assertFalse(generated.exists())
        self.assertEqual((self.records / "selected").read_bytes(), self.payloads["selected"])

    @unittest.skipUnless(sys.platform == "darwin", "enabled macOS/APFS mutation")
    def test_root_and_builtin_configuration_drift_stop_before_confirmation(self):
        module = self.module()
        ap, pp, report = self.freeze()
        actual_tools = module._tools
        def changed_tools(*args, **kwargs):
            tools = actual_tools(*args, **kwargs)
            tools["configuration"] = "unexpected configuration drift"
            return tools
        with patch.object(cleanup, "_state_path", return_value=self.base / "state"), \
                patch.object(cleanup, "_confirm", side_effect=AssertionError("drift must refuse before confirmation")):
            with patch.object(module, "_tools", side_effect=changed_tools), self.assertRaises(ValueError):
                cleanup.apply(pp, ap, [], all_eligible=True)
            old = self.base / "retained-cache"
            self.cache.rename(old)
            self.cache.mkdir()
            shutil.copytree(old / "_cacache", self.cache / "_cacache")
            with self.assertRaises(ValueError):
                cleanup.apply(pp, ap, [], all_eligible=True)

    def test_cli_discovery_preserves_payloads_and_explains_consequences(self):
        result = subprocess.run([sys.executable, "-B", str(test_plans.CLI), "review", "--project", str(self.project),
                                 "--npm-cache", str(self.cache)], capture_output=True, timeout=30, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("singleton", result.stdout)
        self.assertIn("offline", result.stdout)
        self.assertIn("229376", result.stdout)

    @unittest.skipUnless(sys.platform == "darwin", "enabled macOS/APFS mutation")
    def test_native_refusal_never_falls_back_to_filesystem_deletion(self):
        module = self.module()
        ap, pp, report = self.freeze(self.assessment(("selected",)))
        original = subprocess.run
        native_codes = []
        def refused(command, **options):
            if "clean" not in command:
                return original(command, **options)
            buckets = [path for path in (self.cache / "_cacache/index-v5").rglob("*") if path.is_file()]
            for path in buckets:
                path.chmod(0o444)
            try:
                result = original(command, **options)
                native_codes.append(result.returncode)
                return result
            finally:
                for path in buckets:
                    path.chmod(0o644)
        with patch.object(cleanup, "_state_path", return_value=self.base / "state"), patch.object(cleanup, "_confirm", return_value=True), \
                patch.object(module.subprocess, "run", side_effect=refused):
            result = cleanup.apply(pp, ap, [], all_eligible=True)
        self.assertEqual(result["outcome"], "partial-or-failed")
        self.assertEqual(result["native_failure"]["kind"], "native-refusal")
        self.assertEqual(result["native_failure"]["exit_code"], native_codes[0])
        self.assertNotEqual(native_codes[0], 0)
        self.assertEqual({row["key"] for row in module.inventory(str(self.cache), timeout=30)["entries"]},
                         {"selected", "second", "shared", "shared-alias", "active", "offline", "unknown"})

    @unittest.skipUnless(sys.platform == "darwin", "enabled macOS/APFS mutation")
    def test_inherited_node_and_npm_overrides_cannot_redirect_or_expand_removal(self):
        module = self.module()
        ap, pp, report = self.freeze(self.assessment(("selected",)))
        with patch.object(cleanup, "_state_path", return_value=self.base / "state"), patch.object(cleanup, "_confirm", return_value=True), \
                patch.dict(os.environ, {"NODE_OPTIONS": "--require=/unselected/private-code", "NODE_PATH": "/unselected/modules",
                                        "npm_config_cache": "/unselected/other-cache", "npm_config_force": "true",
                                        "npm_config_userconfig": str(self.cache / ".npmrc")}):
            result = cleanup.apply(pp, ap, [], all_eligible=True)
        self.assertEqual(result["outcome"], "completed", result)
        self.assertEqual({row["key"] for row in module.inventory(str(self.cache), timeout=30)["entries"]},
                         {"second", "shared", "shared-alias", "active", "offline", "unknown"})

    def test_overlapping_active_unknown_and_historical_obligations_protect_cache_entries(self):
        scenarios = ("active", "finding", "unresolved", "unknown-consumer", "retention", "historical-consumer", "content-retention", "index-retention", "case-alias")
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                assessment = self.assessment(("selected",))
                surrounding = {"operation": "directory-remove", "path": str(self.cache), "category": "output", "purpose": "surrounding resource"}
                manifest = None
                if scenario in {"active", "case-alias"}:
                    if scenario == "case-alias":
                        alias = self.cache.with_name("CACHE")
                        if not alias.exists():
                            continue  # this fixture filesystem has no physical case alias
                        self.assertTrue(alias.samefile(self.cache))
                        surrounding["path"] = str(alias)
                    surrounding["consumers"] = [{"id": "surrounding-owner", "state": "active", "basis": ["context"]}]
                elif scenario == "finding":
                    surrounding["findings"] = [{"kind": "unique-state", "basis": ["context"]}]
                elif scenario == "unresolved":
                    surrounding["consumer_scope"] = {"basis": ["context"], "unresolved": ["surrounding owner need unknown"]}
                elif scenario == "unknown-consumer":
                    surrounding["consumers"] = [{"id": "surrounding-owner", "state": "unknown", "basis": ["context"]}]
                else:
                    path = self.cache
                    if scenario == "content-retention":
                        hexadecimal = hashlib.sha512(self.payloads["selected"]).hexdigest()
                        path = self.cache / "_cacache/content-v2/sha512" / hexadecimal[:2] / hexadecimal[2:4] / hexadecimal[4:]
                    elif scenario == "index-retention":
                        hexadecimal = hashlib.sha256(b"selected").hexdigest()
                        path = self.cache / "_cacache/index-v5" / hexadecimal[:2] / hexadecimal[2:4] / hexadecimal[4:]
                    manifest = {"schema_version": 1, "resources": [{"path": str(path), "origin": "helper-created",
                        "purpose": "historical surrounding cache", "association": "fixture", "consumers": ["historical-owner"],
                        "retention": ["required retained download"] if scenario != "historical-consumer" else [], "release_checkpoint": "unknown"}]}
                assessment["candidates"].insert(0, surrounding)
                report = plans.review_scope(self.base, assessment=assessment, manifest=manifest, timeout=30)
                native = next(row for row in report["candidates"] if row["operation"] == "npm-cache-remove")
                self.assertEqual(native["assessment"], "Keep" if scenario in {"active", "finding", "retention", "content-retention", "index-retention", "case-alias"} else "Review")
                with self.assertRaises(ValueError):
                    plans.validate_selection(report["plan"], [native["id"]])

    def test_unrelated_neighbor_retention_does_not_block_independent_native_entry(self):
        manifest = {"schema_version": 1, "resources": [{"path": str(self.cache / "unrelated.txt"), "origin": "helper-created",
            "purpose": "retained neighboring file", "association": "fixture", "consumers": ["active-other-owner"],
            "retention": ["required neighbor"], "release_checkpoint": "none"}]}
        report = plans.review_scope(self.project, assessment=self.assessment(("selected",)), manifest=manifest, timeout=30)
        self.assertEqual(report["candidates"][0]["assessment"], "Eligible")

    def test_revalidation_refuses_older_frozen_native_row_with_overlapping_active_obligation(self):
        assessment = self.assessment(("selected",))
        ap, pp, report = self.freeze(assessment)
        row = report["candidates"][0]
        assessment["candidates"].insert(0, {"operation": "directory-remove", "path": str(self.cache), "category": "output",
            "purpose": "known active surrounding resource", "consumers": [{"id": "other-owner", "state": "active", "basis": ["context"]}]})
        ap.write_bytes(plans.canonical_json(assessment))
        plan = copy.deepcopy(report["plan"])
        plan["assessment_digest"] = plans.digest(assessment)
        plan["digest"] = plans.digest({key: value for key, value in plan.items() if key != "digest"})
        with self.assertRaises(ValueError):
            cleanup._revalidate(plan, [row], ap, None, None)


class CacheInputContracts(unittest.TestCase):
    def test_unknown_fields_types_commands_versions_refuse(self):
        from devspace import npm_cache
        with tempfile.TemporaryDirectory(prefix="cache-contract-") as temporary:
            cache = str(Path(temporary).resolve())
            resource = {"cache": cache, "key": "exact", "integrity": "sha512-" + base64.b64encode(bytes(64)).decode()}
            invalid = [{**resource, "command": "rm -rf"}, {**resource, "key": 7}, {**resource, "key": "injected\nflag"},
                       {**resource, "cache": cache + "/../"}, {**resource, "integrity": True}, {**resource, "integrity": "sha1-unsupported"}]
            for candidate in invalid:
                with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                    npm_cache.validate_resource(candidate)
            for version in (True, 4.0, "4", 5):
                with self.subTest(version=version), self.assertRaises(ValueError):
                    plans._validate_assessment({"schema_version": version, "references": {}, "candidates": []})


if __name__ == "__main__":
    unittest.main()
