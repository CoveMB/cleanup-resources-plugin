"""Destructive checks use only NEW agent-created temporary fixtures.

Terminal responses here are synthetic mechanical fixtures, never human acceptance.
"""
import copy
import hashlib
import json
import os
import re
import select
import signal
import stat
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import test_plans
CLI = test_plans.CLI


class GuardedCleanup(unittest.TestCase):
    def setUp(self):
        self.fixture = test_plans.AssessedPlans()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base
        self.project = self.fixture.project
        self.state_path = self.base / "private-state"
        self.assessment_path = self.base / "assessment.json"
        self.assessment_path.write_text(json.dumps(self.fixture.assessment))
        self.plan_path = self.base / "plan.json"
        self.plan = self.fixture.review()["plan"]
        self.fixture.owner().write_plan(self.plan_path, self.plan)
        self.ids = [row["id"] for row in self.plan["candidates"]
                    if Path(row["path"]).relative_to(self.project).as_posix() in {"A", "packet/C"}]
        self.before = self.resources()

    def resources(self):
        return {name: data for name, data in self.fixture.bytes().items()
                if name.startswith(("project/", "records/"))}

    def owner(self):
        from devspace import cleanup
        return cleanup

    def apply(self, ids=None, **options):
        owner = self.owner()
        with patch.object(owner, "_state_path", return_value=self.state_path), \
                patch.object(owner, "_confirm", return_value=True):
            return owner.apply(self.plan_path, self.assessment_path, self.ids if ids is None else ids, **options)

    def receipts(self):
        return {path.name: json.loads(path.read_bytes()) for path in self.state_path.glob("*.json")}

    def test_selected_exact_removal_and_private_durable_receipts(self):
        owner = self.owner()
        if sys.platform != "darwin":
            with self.assertRaises(ValueError):
                self.apply()
            self.assertEqual(self.before, self.resources())
            return
        result = self.apply()
        self.assertEqual(result["outcome"], "completed")
        self.assertEqual([item["outcome"] for item in result["targets"]], ["removed", "removed"])
        self.assertFalse((self.project / "A").exists())
        self.assertFalse((self.project / "packet/C").exists())
        for path, data in self.before.items():
            if not path.startswith(("project/A/", "project/packet/C/")):
                self.assertEqual((self.base / path).read_bytes(), data)
        records = self.receipts()
        self.assertEqual(len(records), 2)
        self.assertFalse((self.state_path / "pending.json").exists())
        for name, record in records.items():
            self.assertEqual((self.state_path / name).stat().st_mode & 0o777, 0o600)
            self.assertEqual(record["plan_digest"], self.plan["digest"])
            self.assertEqual(record["operation"], "permanent-exact-directory-removal")
            self.assertTrue(record["warnings"])
            self.assertEqual([row["id"] for row in record["targets"]], self.ids)
            self.assertNotIn(str(self.base), json.dumps(record))
        self.assertIn("attribution", result["measurement"])

    def test_missing_interactive_confirmation_never_removes(self):
        owner = self.owner()
        with patch.object(owner, "_state_path", return_value=self.state_path), \
                patch.object(owner.sys.stdin, "isatty", return_value=False):
            with self.assertRaises(ValueError):
                owner.apply(self.plan_path, self.assessment_path, self.ids)
        self.assertEqual(self.before, self.resources())

    def test_plan_and_selection_refusals_do_not_promote(self):
        owner = self.owner()
        variants = [([], None), (["missing"], None), (self.ids + [self.ids[0]], None)]
        noneligible = next(row["id"] for row in self.plan["candidates"] if row["assessment"] != "Eligible")
        variants.append(([noneligible], None))
        for change in ("digest", "host", "effect", "approved"):
            plan = copy.deepcopy(self.plan)
            if change == "digest":
                plan["digest"] = "0" * 64
            elif change == "host":
                plan["host"]["identity"] = "another host"
            elif change == "effect":
                next(row for row in plan["candidates"] if row["id"] == self.ids[0])["effect"] = "remove everything"
            else:
                plan["approved"] = True
            if change != "digest":
                plan["digest"] = self.fixture.owner().digest({k: v for k, v in plan.items() if k != "digest"})
            variants.append((self.ids, plan))
        for ids, plan in variants:
            with self.subTest(ids=ids, changed=plan is not None):
                self.plan_path.write_text(json.dumps(plan or self.plan))
                with self.assertRaises((ValueError, OSError)):
                    self.apply(ids)
                self.assertEqual(self.before, self.resources())

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only mutation route")
    def test_all_eligible_and_cancel(self):
        owner = self.owner()
        with patch.object(owner, "_state_path", return_value=self.state_path), \
                patch.object(owner, "_confirm", return_value=False):
            result = owner.apply(self.plan_path, self.assessment_path, self.ids)
        self.assertEqual(result["outcome"], "cancelled")
        self.assertEqual(self.before, self.resources())
        result = self.apply([], all_eligible=True)
        self.assertEqual(len(result["targets"]), 3)
        self.assertFalse((self.project / "legacy").exists())
        self.assertTrue((self.project / "D/retained.txt").exists())

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only mutation route")
    def test_whole_batch_drift_zero_mutation(self):
        for mode in ("content", "consumer", "retention", "rebuild", "identity", "symlink", "nested-protected"):
            with self.subTest(mode=mode):
                # New independent inventoried fixture per adverse scenario.
                case = GuardedCleanup(); case.setUp()
                try:
                    if mode == "content":
                        (case.project / "packet/C/data.txt").write_bytes(b"changed disposable fixture")
                    elif mode in {"consumer", "retention", "rebuild"}:
                        assessment = copy.deepcopy(case.fixture.assessment)
                        if mode == "consumer":
                            assessment["candidates"][1]["consumers"][0]["state"] = "active"
                        elif mode == "retention":
                            assessment["candidates"][1]["findings"] = [{"kind": "hold", "basis": ["decision"]}]
                        else:
                            (case.fixture.records / "source.txt").write_bytes(b"changed rebuild source")
                        case.assessment_path.write_text(json.dumps(assessment))
                    elif mode == "identity":
                        (case.project / "packet/C").rename(case.project / "packet/old-C")
                        (case.project / "packet/C").mkdir()
                        (case.project / "packet/C/data.txt").write_bytes(b"replacement preserved")
                    elif mode == "symlink":
                        (case.project / "packet/C").rename(case.project / "packet/old-C")
                        (case.project / "packet/C").symlink_to(case.project / "legacy", target_is_directory=True)
                    else:
                        (case.project / "packet/C/.env").write_bytes(b"SYNTHETIC_SECRET_MARKER")
                    with self.assertRaises((ValueError, OSError)):
                        case.apply()
                    self.assertTrue((case.project / "A/data.txt").exists())
                    self.assertTrue((case.project / "packet/C/data.txt").exists())
                    self.assertFalse((case.state_path / "pending.json").exists())
                finally:
                    case.doCleanups()

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only mutation route")
    def test_later_item_drift_stops_and_preserves_replacement(self):
        owner = self.owner()
        original = owner._remove
        def remove_then_replace(row, limits):
            original(row, limits)
            path = self.project / "packet/C"
            path.rename(self.project / "packet/old-C")
            path.mkdir()
            (path / "data.txt").write_bytes(b"replacement must survive")
        with patch.object(owner, "_remove", side_effect=remove_then_replace):
            result = self.apply()
        self.assertEqual(result["outcome"], "partial-or-failed")
        self.assertEqual([row["outcome"] for row in result["targets"]], ["removed", "not-started"])
        self.assertEqual((self.project / "packet/C/data.txt").read_bytes(), b"replacement must survive")
        self.assertTrue((self.state_path / "pending.json").exists())
        with self.assertRaises(ValueError):
            self.apply()
        with patch.object(owner, "_state_path", return_value=self.state_path):
            reconciled = owner.reconcile(self.plan_path)
        self.assertEqual([row["outcome"] for row in reconciled["targets"]], ["absent", "replaced"])
        self.assertEqual((self.project / "packet/C/data.txt").read_bytes(), b"replacement must survive")

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only mutation route")
    def test_refused_intent_and_result_write_failure(self):
        owner = self.owner()
        original = owner.State.write
        def refuse_intent(state, name, value):
            raise OSError("SYNTHETIC_SECRET_MARKER")
        with patch.object(owner.State, "write", new=refuse_intent):
            with self.assertRaises(OSError):
                self.apply()
        self.assertEqual(self.before, self.resources())
        def refuse_result(state, name, value):
            if name.endswith(".result.json"):
                raise OSError("SYNTHETIC_TRANSCRIPT_MARKER")
            return original(state, name, value)
        with patch.object(owner.State, "write", new=refuse_result):
            result = self.apply()
        self.assertEqual(result["outcome"], "result-unavailable")
        self.assertFalse((self.project / "A").exists())
        self.assertTrue((self.state_path / "pending.json").exists())
        with patch.object(owner, "_state_path", return_value=self.state_path):
            result = owner.reconcile(self.plan_path)
        self.assertEqual([row["outcome"] for row in result["targets"]], ["absent", "absent"])
        for record in self.receipts().values():
            self.assertNotIn("SYNTHETIC_", json.dumps(record))

    def test_cli_rejects_approval_flags_and_cancel_is_nonmutating(self):
        for arguments in (("--approved", "true"), ("--yes",), ("--permission", "all")):
            result = subprocess.run([sys.executable, "-B", str(CLI), "apply", "--plan", str(self.plan_path),
                                     "--assessment", str(self.assessment_path), "--select", ",".join(self.ids), *arguments],
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 2)
        result = subprocess.run([sys.executable, "-B", str(CLI), "apply", "--plan", str(self.plan_path), "--cancel"],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "cancelled")
        self.assertEqual(self.before, self.resources())

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only mutation route")
    def test_unproven_filesystem_and_missing_capability_refuse(self):
        owner = self.owner()
        from devspace import review
        with patch.object(review, "darwin_filesystem", return_value=(0x1000, b"hfs")):
            with self.assertRaises(ValueError):
                self.apply()
        with patch.object(owner, "descriptor_traversal_available", return_value=False):
            with self.assertRaises(ValueError):
                self.apply()
        self.assertEqual(self.before, self.resources())

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only mutation route")
    def test_durable_state_path_substitution_prevents_mutation(self):
        owner = self.owner()
        def substitute_state(plan, selected):
            self.state_path.rename(self.base / "moved-state")
            self.state_path.mkdir(mode=0o700)
            return True
        with patch.object(owner, "_state_path", return_value=self.state_path), \
                patch.object(owner, "_confirm", side_effect=substitute_state):
            with self.assertRaises(ValueError):
                owner.apply(self.plan_path, self.assessment_path, self.ids)
        self.assertEqual(self.before, self.resources())

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only mutation route")
    def test_permission_refusal_preflights_entire_batch(self):
        directory = self.project / "packet/C"
        directory.chmod(0o500)
        self.addCleanup(directory.chmod, 0o755)
        # Review may read a directory that cannot be mutated; it is not a deletion capability proof.
        self.plan = self.fixture.review()["plan"]
        self.plan_path.write_text(json.dumps(self.plan))
        with self.assertRaises((OSError, ValueError)):
            self.apply()
        self.assertTrue((self.project / "A/data.txt").exists())
        self.assertTrue((directory / "data.txt").exists())

    def test_accounting_uses_observed_net_change_with_unknowns(self):
        owner = self.owner()
        measured = owner._measurement({11: 1000, 12: 3000, 13: None}, {11: 1600, 12: 2800, 13: 500})
        self.assertEqual([row["net_free_change_bytes"] for row in measured["filesystems"]], [600, -200, None])
        self.assertIn("not guaranteed", measured["attribution"])

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only mutation route")
    def test_nested_descriptor_deletion_and_allocated_fixture(self):
        self.fixture.nested_outputs()
        # Add actual allocated data from a retained independent source, not a sparse size-only claim.
        source = self.fixture.records / "allocated.bin"
        source.write_bytes(os.urandom(2 * 1024 * 1024))
        source.chmod(0o644)
        data = source.read_bytes()
        (self.project / "A/allocated.bin").write_bytes(data)
        (self.project / "A/allocated.bin").chmod(0o644)
        expected = json.loads((self.fixture.records / "parent-outputs.json").read_text())
        expected["entries"].append({"path": "allocated.bin", "kind": "file", "mode": 420,
                                    "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        expected_path = self.fixture.records / "parent-outputs.json"
        expected_path.write_text(json.dumps(expected))
        self.fixture.references["parent-outputs"]["sha256"] = hashlib.sha256(expected_path.read_bytes()).hexdigest()
        self.assessment_path.write_text(json.dumps(self.fixture.assessment))
        self.plan = self.fixture.review()["plan"]
        self.plan_path.write_text(json.dumps(self.plan))
        row = next(row for row in self.plan["candidates"] if row["id"] == self.ids[0])
        self.assertGreaterEqual(row["observation"]["size"]["allocated_bytes"], 2 * 1024 * 1024)
        result = self.apply()
        self.assertEqual(result["outcome"], "completed")
        self.assertFalse((self.project / "A").exists())
        measured = result["measurement"]["filesystems"][0]
        self.assertIsInstance(measured["before_free_bytes"], int)
        self.assertIsInstance(measured["after_free_bytes"], int)
        self.assertEqual(measured["net_free_change_bytes"], measured["after_free_bytes"] - measured["before_free_bytes"])
        self.assertEqual(source.read_bytes(), data)

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only mutation route")
    def test_partial_unlink_failure_preserves_other_items(self):
        owner = self.owner()
        original = owner.os.unlink
        calls = []
        def unlink_then_fail(name, **options):
            calls.append(name)
            original(name, **options)
            if name == "data.txt":
                raise OSError("SYNTHETIC_SECRET_FILE_CONTENT_TRANSCRIPT_BULK_LISTING")
        remove = owner._remove
        def remove_with_io_failure(row, limits):
            # Install the syscall failure only after unchanged real capability preflight.
            with patch.object(owner.os, "unlink", side_effect=unlink_then_fail):
                return remove(row, limits)
        with patch.object(owner, "_remove", side_effect=remove_with_io_failure):
            result = self.apply()
        self.assertEqual(result["outcome"], "partial-or-failed")
        self.assertEqual([row["outcome"] for row in result["targets"]], ["started-outcome-unknown", "not-started"])
        self.assertTrue((self.project / "A").exists())
        self.assertFalse((self.project / "A/data.txt").exists())
        self.assertTrue((self.project / "packet/C/data.txt").exists())
        with patch.object(owner, "_state_path", return_value=self.state_path):
            reconciled = owner.reconcile(self.plan_path)
        self.assertEqual(reconciled["targets"][0]["outcome"], "same-identity-contents-unverified")
        for record in self.receipts().values():
            self.assertNotIn("SYNTHETIC_", json.dumps(record))

    def child_script(self, boundary):
        # Internal fixture instrumentation only; no runtime CLI bypass is added.
        return ("import sys,os,json\nfrom pathlib import Path\n"
                f"sys.path.insert(0,{str(CLI.parent)!r})\nfrom devspace import cleanup\n"
                f"cleanup._state_path=lambda:Path({str(self.state_path)!r})\n"
                "cleanup._confirm=lambda *args:True\n"
                f"boundary={boundary!r}\n"
                "original=cleanup._remove\n"
                "def stop(row,limits):\n"
                " if boundary=='after-item': original(row,limits)\n"
                " print('FIXTURE_BOUNDARY',flush=True)\n"
                " sys.stdin.readline()\n"
                "cleanup._remove=stop\n"
                f"result=cleanup.apply({str(self.plan_path)!r},{str(self.assessment_path)!r},{self.ids!r})\n"
                "print(json.dumps(result),flush=True)\n")

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only mutation route")
    def test_real_process_kill_after_durable_intent_and_competing_helper(self):
        owner = self.owner()
        child = subprocess.Popen([sys.executable, "-B", "-c", self.child_script("before-item")],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            ready, _, _ = select.select([child.stdout], [], [], 10)
            self.assertTrue(ready, "fixture process did not reach durable-intent boundary")
            self.assertEqual(child.stdout.readline().strip(), "FIXTURE_BOUNDARY")
            receipts = self.receipts()
            self.assertTrue(any(name.endswith(".intent.json") for name in receipts))
            self.assertIn("pending.json", receipts)
            self.assertTrue((self.project / "A/data.txt").exists())
            competitor = self.child_script("before-item")
            second = subprocess.run([sys.executable, "-B", "-c", competitor], input="", capture_output=True,
                                    text=True, timeout=10)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("BlockingIOError", second.stderr)
            child.kill()
            child.wait(timeout=10)
            self.assertEqual(child.returncode, -signal.SIGKILL)
        finally:
            if child.poll() is None:
                child.kill(); child.wait(timeout=10)
            child.stdin.close(); child.stdout.close(); child.stderr.close()
        with patch.object(owner, "_state_path", return_value=self.state_path):
            result = owner.reconcile(self.plan_path)
        self.assertEqual([row["outcome"] for row in result["targets"]], ["same-identity-contents-unverified"] * 2)
        self.assertEqual(self.before, self.resources())

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only mutation route")
    def test_real_process_kill_after_first_item_never_retries_replacement(self):
        owner = self.owner()
        child = subprocess.Popen([sys.executable, "-B", "-c", self.child_script("after-item")],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            ready, _, _ = select.select([child.stdout], [], [], 10)
            self.assertTrue(ready)
            self.assertEqual(child.stdout.readline().strip(), "FIXTURE_BOUNDARY")
            self.assertFalse((self.project / "A").exists())
            child.kill(); child.wait(timeout=10)
            self.assertEqual(child.returncode, -signal.SIGKILL)
        finally:
            if child.poll() is None:
                child.kill(); child.wait(timeout=10)
            child.stdin.close(); child.stdout.close(); child.stderr.close()
        (self.project / "A").mkdir()
        (self.project / "A/replacement.txt").write_bytes(b"replacement survives reconciliation")
        with patch.object(owner, "_state_path", return_value=self.state_path):
            result = owner.reconcile(self.plan_path)
        self.assertEqual(result["targets"][0]["outcome"], "replaced")
        self.assertEqual((self.project / "A/replacement.txt").read_bytes(), b"replacement survives reconciliation")
        self.assertTrue((self.project / "packet/C/data.txt").exists())

    @unittest.skipUnless(sys.platform == "darwin", "macOS controlling-terminal fixture")
    def test_synthetic_terminal_binds_displayed_effects_and_refuses_wrong_response(self):
        import pty
        owner = self.owner()
        # This is a synthetic PTY fixture, explicitly not human acceptance.
        for response in ("CANCEL", "REMOVE wrong", "exact"):
            pid, descriptor = pty.fork()
            if pid == 0:
                try:
                    null = os.open(os.devnull, os.O_WRONLY)
                    os.dup2(null, 1); os.dup2(null, 2); os.close(null)
                    selected = self.fixture.owner().validate_selection(self.plan, self.ids)
                    confirmed = owner._confirm(self.plan, selected)
                    with open("/dev/tty", "w") as terminal:
                        terminal.write("FIXTURE_CONFIRMED=" + str(confirmed) + "\n")
                    os._exit(0)
                except BaseException as error:
                    print("FIXTURE_TERMINAL_ERROR=" + type(error).__name__, flush=True)
                    os._exit(3)
            output = b""
            status = None
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and b"or type CANCEL:" not in output:
                    ready, _, _ = select.select([descriptor], [], [], 1)
                    if ready:
                        try:
                            output += os.read(descriptor, 65536)
                        except OSError:
                            break
                self.assertIn(b"or type CANCEL:", output, output.decode(errors="replace"))
                for marker in (self.plan["digest"], self.plan["host"]["identity"], *self.ids,
                               "permanent removal of this exact directory", "preconditions"):
                    self.assertIn(marker.encode(), output)
                exact = re.search(rb"Type exactly (REMOVE [0-9a-f]{64})", output).group(1)
                os.write(descriptor, (exact if response == "exact" else response.encode()) + b"\n")
                while time.monotonic() < deadline:
                    ready, _, _ = select.select([descriptor], [], [], 1)
                    if ready:
                        try:
                            data = os.read(descriptor, 65536)
                        except OSError:
                            break
                        if not data:
                            break
                        output += data
                    finished, status = os.waitpid(pid, os.WNOHANG)
                    if finished:
                        break
                self.assertIn(b"FIXTURE_CONFIRMED=" + (b"True" if response == "exact" else b"False"), output)
            finally:
                try:
                    finished, status = os.waitpid(pid, os.WNOHANG)
                    if not finished:
                        os.kill(pid, signal.SIGKILL); os.waitpid(pid, 0)
                except ChildProcessError:
                    pass
                os.close(descriptor)
        self.assertEqual(self.before, self.resources())

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only mutation route")
    def test_global_original_context_revalidation_and_protected_configured_root(self):
        owner = self.owner()
        assessment = copy.deepcopy(self.fixture.assessment)
        for specification in assessment["candidates"]:
            specification["path"] = str(self.project / specification["path"])
        config = {"schema_version": 1, "roots": [str(self.project), str(self.project / "legacy")]}
        config_path = self.base / "config.json"
        config_path.write_text(json.dumps(config))
        self.assessment_path.write_text(json.dumps(assessment))
        self.plan = self.fixture.owner().review_scope(config, mode="global", assessment=assessment)["plan"]
        self.plan_path.write_text(json.dumps(self.plan))
        legacy = next(row for row in self.plan["candidates"] if row["path"] == str(self.project / "legacy"))
        self.assertEqual(legacy["assessment"], "Keep")
        with self.assertRaises(ValueError):
            self.apply([legacy["id"]], config_path=config_path)
        result = self.apply(config_path=config_path)
        self.assertEqual(result["outcome"], "completed")
        self.assertTrue((self.project / "legacy/data.txt").exists())

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only mutation route")
    def test_actual_entry_replacement_after_snapshot_preserves_bytes(self):
        owner = self.owner()
        original = owner._snapshot
        def snapshot_then_replace(row, limits):
            snapshot = original(row, limits)
            if row["id"] == self.ids[0]:
                data = self.project / "A/data.txt"
                data.rename(self.project / "A/original.txt")
                data.write_bytes(b"entry replacement preserved")
            return snapshot
        remove = owner._remove
        def interleaved_remove(row, limits):
            with patch.object(owner, "_snapshot", side_effect=snapshot_then_replace):
                return remove(row, limits)
        with patch.object(owner, "_remove", side_effect=interleaved_remove):
            result = self.apply()
        self.assertEqual(result["outcome"], "partial-or-failed")
        self.assertEqual((self.project / "A/data.txt").read_bytes(), b"entry replacement preserved")
        self.assertTrue((self.project / "A/original.txt").exists())
        self.assertTrue((self.project / "packet/C/data.txt").exists())

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only mutation route")
    def test_retention_manifest_and_original_context_are_required(self):
        manifest = {"schema_version": 1, "resources": [{"path": str(self.project / "A"), "origin": "helper-created",
                    "purpose": "synthetic generated output", "association": "fixture", "consumers": ["fixture-consumer"],
                    "retention": [], "release_checkpoint": "successful fixture completion"}]}
        manifest_path = self.base / "manifest.json"
        manifest_path.write_text(json.dumps(manifest))
        self.plan = self.fixture.review(manifest=manifest)["plan"]
        self.plan_path.write_text(json.dumps(self.plan))
        with self.assertRaises(ValueError):
            self.apply()  # Original manifest cannot be silently omitted.
        manifest["resources"][0]["retention"] = ["new fixture hold"]
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            self.apply(manifest_path=manifest_path)
        self.assertEqual(self.before, self.resources())

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only mutation route")
    def test_corrupt_reconciliation_state_is_not_returned_as_a_receipt(self):
        owner = self.owner()
        with patch.object(owner, "_remove", side_effect=OSError("synthetic stop")):
            self.apply()
        intent = next(self.state_path.glob("*.intent.json"))
        payload = json.loads(intent.read_text())
        payload["targets"][0]["transcript"] = "SYNTHETIC_SECRET_PAYLOAD"
        intent.write_text(json.dumps(payload))
        with patch.object(owner, "_state_path", return_value=self.state_path):
            with self.assertRaises(ValueError):
                owner.reconcile(self.plan_path)
        self.assertTrue((self.state_path / "pending.json").exists())

    def test_protected_roots_provider_holds_and_overlap_reject_without_traversal(self):
        owner = self.owner()
        for kind in ("project", "home", "provider", "ancestor", "overlap", "mount"):
            plan = copy.deepcopy(self.plan)
            selected = [row for row in plan["candidates"] if row["id"] in self.ids]
            if kind == "project":
                selected[0]["path"] = str(self.project)
            elif kind == "home":
                selected[0]["path"] = str(Path.home())
            elif kind == "provider":
                plan["policy"]["holds"].append(selected[0]["path"])
            elif kind == "ancestor":
                plan["scope_roots"].append(str(self.project / "A/data"))
            elif kind == "overlap":
                selected[1]["path"] = str(self.project / "A/nested")
            plan["digest"] = self.fixture.owner().digest({k: v for k, v in plan.items() if k != "digest"})
            self.plan_path.write_text(json.dumps(plan))
            with self.subTest(kind=kind):
                # Mount creation is not exercised/certified. This checks refusal only.
                mount = patch.object(owner.os.path, "ismount", return_value=True) if kind == "mount" else patch.object(owner, "_revalidate", side_effect=AssertionError("protected target reached assessment"))
                with mount, self.assertRaises((OSError, ValueError)):
                    self.apply()
                self.assertEqual(self.before, self.resources())

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only mutation route")
    def test_known_git_worktree_nested_state_stays_noneligible(self):
        (self.project / "A/.git").write_text("gitdir: /synthetic/unavailable-worktree\n")
        self.plan = self.fixture.review()["plan"]
        self.plan_path.write_text(json.dumps(self.plan))
        with self.assertRaises(ValueError):
            self.apply()
        self.assertTrue((self.project / "A/.git").exists())
        self.assertTrue((self.project / "packet/C/data.txt").exists())

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only mutation route")
    def test_real_private_state_mode_denial_and_failed_full_sync_stop(self):
        owner = self.owner()
        self.state_path.mkdir(mode=0o755)
        with self.assertRaises(ValueError):
            self.apply()
        self.state_path.chmod(0o700)
        with patch.object(owner, "_sync_file", side_effect=OSError("synthetic drive-flush refusal")):
            with self.assertRaises(OSError):
                self.apply()
        self.assertEqual(self.before, self.resources())
        self.assertFalse((self.state_path / "pending.json").exists())

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only mutation route")
    def test_privacy_markers_absent_from_actual_success_failure_reconciliation_receipts(self):
        owner = self.owner()
        markers = ("SYNTHETIC_SECRET_PAYLOAD", "SYNTHETIC_FILE_CONTENT", "SYNTHETIC_TRANSCRIPT", "SYNTHETIC_BULK_LISTING")
        payload = ("\n".join(markers) + "\n").encode()
        # Independent literal contents stress receipt privacy, not semantic certification.
        (self.fixture.records / "source.txt").write_bytes(payload)
        for target in ("A", "packet/C", "legacy"):
            (self.project / target / "data.txt").write_bytes(payload)
        expected = {"schema_version": 1, "entries": [{"path": "data.txt", "kind": "file", "mode": 420,
                    "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}]}
        (self.fixture.records / "outputs.json").write_text(json.dumps(expected))
        for key in ("source", "outputs"):
            reference = self.fixture.references[key]
            reference["sha256"] = hashlib.sha256(Path(reference["path"]).read_bytes()).hexdigest()
        self.fixture.specifications[0]["purpose"] = " ".join(markers)
        self.assessment_path.write_text(json.dumps(self.fixture.assessment))
        self.plan = self.fixture.review()["plan"]
        self.plan_path.write_text(json.dumps(self.plan))
        remove = owner._remove
        count = 0
        def first_only(row, limits):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError(" ".join(markers))
            return remove(row, limits)
        with patch.object(owner, "_remove", side_effect=first_only):
            result = self.apply()
        self.assertEqual(result["targets"][0]["outcome"], "removed")
        self.assertEqual(result["outcome"], "partial-or-failed")
        with patch.object(owner, "_state_path", return_value=self.state_path):
            owner.reconcile(self.plan_path)
        records = self.receipts()
        self.assertTrue(any(name.endswith(".intent.json") for name in records))
        self.assertTrue(any(name.endswith(".result.json") for name in records))
        self.assertTrue(any(name.endswith(".reconciliation.json") for name in records))
        for record in records.values():
            for marker in markers:
                self.assertNotIn(marker, json.dumps(record))
            for key in ("operation", "host", "warnings", "outcome", "measurement", "targets"):
                self.assertIn(key, record)
            self.assertEqual(len(record["targets"]), 2)
            self.assertIn("identity", record["targets"][0])
            self.assertNotIn(str(self.base), json.dumps(record))

    @unittest.skipUnless(sys.platform == "darwin", "macOS immutable-directory fixture")
    def test_immutable_parent_preflight_preserves_entire_batch(self):
        parent = self.project / "packet"
        os.chflags(parent, stat.UF_IMMUTABLE)
        self.addCleanup(os.chflags, parent, 0)
        self.plan = self.fixture.review()["plan"]
        self.plan_path.write_text(json.dumps(self.plan))
        with self.assertRaises((OSError, ValueError)):
            self.apply()
        self.assertTrue((self.project / "A/data.txt").exists())
        self.assertTrue((parent / "C/data.txt").exists())

    @unittest.skipUnless(sys.platform == "darwin", "macOS durability contract")
    def test_real_directory_sync_precedes_final_drive_flush(self):
        import fcntl
        owner = self.owner()
        sync = os.fsync
        control = fcntl.fcntl
        events = []
        def observed_sync(descriptor):
            events.append("directory-sync" if stat.S_ISDIR(os.fstat(descriptor).st_mode) else "file-sync")
            return sync(descriptor)
        def observed_control(descriptor, command, *arguments):
            if command == 51:
                events.append("drive-flush")
            return control(descriptor, command, *arguments)
        with patch.object(owner, "_state_path", return_value=self.state_path):
            with owner.State([self.project]) as state:
                with patch.object(os, "fsync", side_effect=observed_sync), \
                        patch.object(fcntl, "fcntl", side_effect=observed_control):
                    state.write("durability-fixture.json", {"schema_version": 1, "fixture": "owned"})
                self.assertEqual(state.read("durability-fixture.json")["fixture"], "owned")
        self.assertIn("directory-sync", events)
        self.assertEqual(events[-1], "drive-flush", events)

    def test_changed_displayed_size_is_rejected_before_mutation(self):
        row = next(row for row in self.plan["candidates"] if row["id"] == self.ids[0])
        row["observation"]["size"]["logical_bytes"] = -999
        self.plan["digest"] = self.fixture.owner().digest({k: v for k, v in self.plan.items() if k != "digest"})
        self.plan_path.write_text(json.dumps(self.plan))
        with self.assertRaises(ValueError):
            self.apply()
        self.assertEqual(self.before, self.resources())

    @unittest.skipUnless(sys.platform == "darwin", "macOS batch recovery invariant")
    def test_later_selected_target_cannot_remove_earlier_rebuild_input(self):
        seed = self.project / "packet/C/data.txt"
        self.fixture.references["selected-seed"] = {"path": str(seed), "sha256": hashlib.sha256(seed.read_bytes()).hexdigest()}
        self.fixture.specifications[0]["recovery"]["inputs"] = ["selected-seed"]
        self.fixture.specifications[1]["category"] = "output"
        self.fixture.specifications[1]["recovery"] = {"kind": "accepted-loss", "basis": ["decision"]}
        self.assessment_path.write_text(json.dumps(self.fixture.assessment))
        self.plan = self.fixture.review()["plan"]
        self.plan_path.write_text(json.dumps(self.plan))
        selected = [row for row in self.plan["candidates"] if row["id"] in self.ids]
        self.assertEqual([row["assessment"] for row in selected], ["Eligible", "Eligible"])
        before = self.resources()
        with self.assertRaises(ValueError):
            self.apply()
        self.assertEqual(before, self.resources())

    def prepare_nested_plan(self):
        self.fixture.nested_outputs()
        self.assessment_path.write_text(json.dumps(self.fixture.assessment))
        self.plan = self.fixture.review()["plan"]
        self.plan_path.write_text(json.dumps(self.plan))

    def replace_nested_with_same_bytes(self):
        target = self.project / "A/nested/data.txt"
        data = target.read_bytes()
        original_inode = target.stat().st_ino
        target.rename(self.fixture.records / "held-original-nested.txt")
        target.write_bytes(data)
        target.chmod(0o644)
        self.assertNotEqual(target.stat().st_ino, original_inode)
        return data

    @unittest.skipUnless(sys.platform == "darwin", "macOS frozen descendant identity")
    def test_identical_nested_replacement_before_apply_preserves_entire_batch(self):
        owner = self.owner()
        self.prepare_nested_plan()
        root_identity = owner.file_identity((self.project / "A").stat())
        data = self.replace_nested_with_same_bytes()
        self.assertEqual(owner.file_identity((self.project / "A").stat()), root_identity)
        before = self.resources()
        with self.assertRaises(ValueError):
            self.apply()
        self.assertEqual(before, self.resources())
        self.assertEqual((self.project / "A/nested/data.txt").read_bytes(), data)

    @unittest.skipUnless(sys.platform == "darwin", "macOS frozen descendant identity")
    def test_identical_nested_replacement_between_items_stops_and_survives(self):
        owner = self.owner()
        self.prepare_nested_plan()
        remove = owner._remove
        data = (self.project / "A/nested/data.txt").read_bytes()
        def replace_after_first(row, limits):
            remove(row, limits)
            if row["id"] == self.ids[1]:
                self.replace_nested_with_same_bytes()
        with patch.object(owner, "_remove", side_effect=replace_after_first):
            result = self.apply(list(reversed(self.ids)))
        self.assertEqual(result["outcome"], "partial-or-failed")
        self.assertEqual([row["outcome"] for row in result["targets"]], ["removed", "not-started"])
        self.assertTrue((self.project / "A/data.txt").exists())
        self.assertEqual((self.project / "A/nested/data.txt").read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
