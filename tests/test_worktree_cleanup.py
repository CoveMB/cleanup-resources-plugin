"""Actual native Git operations on newly created disposable repositories only.

Confirmation is a mechanical fixture override, never evidence of human consent.
"""
import copy
import hashlib
import json
import os
import shlex
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import test_plans
from devspace import cleanup, plans


class NativeWorktreeCleanup(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="native-worktree-fixture-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        # Product Git deliberately strips inherited GIT_* scope overrides.
        # Reuse the inventory fixture's real-executable boundary to isolate
        # hosted global/system configuration, retaining repository-local guards.
        executable = shutil.which("git")
        self.assertIsNotNone(executable)
        wrapper = self.base / "fixture-git"
        wrapper.write_text("#!/bin/sh\nGIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null exec "
                           + shlex.quote(executable) + ' "$@"\n')
        wrapper.chmod(0o700)
        discovery = patch("devspace.git_inventory.shutil.which", return_value=str(wrapper))
        discovery.start()
        self.addCleanup(discovery.stop)
        self.repository = self.base / "repository"
        self.repository.mkdir()
        self.git(self.repository, "init", "-b", "main")
        self.git(self.repository, "config", "user.name", "Fixture")
        self.git(self.repository, "config", "user.email", "fixture@example.invalid")
        (self.repository / "source.txt").write_bytes(b"retained tracked source\n")
        (self.repository / ".gitignore").write_bytes(b".env\ncache/\n")
        self.git(self.repository, "add", "source.txt", ".gitignore")
        self.git(self.repository, "commit", "-m", "Fixture baseline")
        self.head = self.git(self.repository, "rev-parse", "HEAD").strip()
        self.worktrees = [self.base / name for name in ("checkout-a", "checkout-b", "held")]
        for index, target in enumerate(self.worktrees):
            self.git(self.repository, "worktree", "add", "-b", f"topic-{index}", str(target))
        self.records = self.base / "records"
        self.records.mkdir()
        decision = self.records / "decision.txt"
        decision.write_text("Disposable fixture owner uses native Git. Sole consumer released checkout-a/b after accepted handoff; "
                            "retain topic branches and repository; resume with a new checkout from those branches. Held is required.")
        # Expected inventory comes from retained original inputs, never the target/validator.
        expected = self.records / "expected.json"
        expected.write_text(json.dumps({"schema_version": 1, "entries": [
            {"path": name, "kind": "file", "mode": 420, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in (("source.txt", b"retained tracked source\n"), (".gitignore", b".env\ncache/\n"))]}))
        self.references = {name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                           for name, path in (("decision", decision), ("expected", expected))}
        self.specifications = [self.specification(target, index) for index, target in enumerate(self.worktrees[:2])]
        self.assessment = {"schema_version": 2, "references": self.references, "candidates": self.specifications}
        self.plan_path = self.base / "plan.json"
        self.assessment_path = self.base / "assessment.json"
        self.state_path = self.base / "private-state"

    def git(self, directory, *arguments):
        environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        result = subprocess.run(["git", *arguments], cwd=directory, env=environment,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def specification(self, target, index):
        return {"path": str(target), "operation": "git-worktree-remove", "category": "worktree",
                "purpose": "released disposable native checkout",
                "worktree": {"repository": str(self.repository), "retained_ref": f"refs/heads/topic-{index}",
                             "lifecycle": "git", "basis": ["decision"]},
                "content": {"method": "inventory", "reference": "expected", "basis": ["decision"]},
                "recovery": {"kind": "retained-commit", "basis": ["decision"]},
                "consumers": [{"id": "fixture", "state": "released", "basis": ["decision"]}],
                "consumer_scope": {"basis": ["decision"], "unresolved": []},
                "release": {"checkpoint": "accepted fixture handoff", "basis": ["decision"]}, "findings": []}

    def review(self):
        with patch.dict(os.environ, {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}):
            return plans.review_scope(self.repository, mode="project", assessment=self.assessment, timeout=30)

    def freeze(self):
        report = self.review()
        self.plan = report["plan"]
        self.plan_path.write_text(json.dumps(self.plan))
        self.assessment_path.write_text(json.dumps(self.assessment))
        self.ids = [row["id"] for row in self.plan["candidates"] if row["path"] in map(str, self.worktrees[:2])]
        self.assertEqual(len(self.ids), 2)
        return report

    def apply(self, **options):
        with patch.object(cleanup, "_state_path", return_value=self.state_path), patch.object(cleanup, "_confirm", return_value=True):
            return cleanup.apply(self.plan_path, self.assessment_path, self.ids, **options)

    def retained(self):
        for index in range(3):
            self.assertEqual(self.git(self.repository, "rev-parse", f"refs/heads/topic-{index}").strip(), self.head)
        self.assertEqual((self.worktrees[2] / "source.txt").read_bytes(), b"retained tracked source\n")
        self.assertEqual((self.repository / "source.txt").read_bytes(), b"retained tracked source\n")

    def test_review_has_explicit_native_identity_and_retained_recovery(self):
        report = self.freeze()
        self.assertEqual(self.plan["schema_version"], 2)
        for row in report["candidates"][:2]:
            self.assertEqual(row["assessment"], "Eligible", row.get("reason"))
            self.assertEqual(row["operation"], "git-worktree-remove")
            self.assertEqual(row["native"]["head"], self.head)
            self.assertIn("branch retained", row["effect"])
        self.retained()

    @unittest.skipUnless(sys.platform == "darwin", "native mutation enabled only on tested macOS/APFS")
    def test_two_selected_worktrees_removed_branches_and_recovery_survive(self):
        self.freeze()
        result = self.apply()
        self.assertEqual(result["outcome"], "completed", result)
        self.assertEqual([target["outcome"] for target in result["targets"]], ["removed", "removed"])
        self.assertEqual({record.splitlines()[0] for record in self.git(self.repository, "worktree", "list", "--porcelain").strip().split("\n\n")},
                         {"worktree " + str(self.repository), "worktree " + str(self.worktrees[2])})
        self.retained()
        resumed = self.base / "resumed"
        self.git(self.repository, "worktree", "add", str(resumed), "topic-0")
        self.assertEqual((resumed / "source.txt").read_bytes(), b"retained tracked source\n")
        for record in self.state_path.glob("*.json"):
            self.assertNotIn(str(self.base), record.read_text())

    def test_ignored_secret_is_detected_preserved_without_payload(self):
        target = self.worktrees[0]
        (target / ".env").write_bytes(b"SYNTHETIC_PRIVATE_ENV")
        self.assertEqual(self.git(target, "status", "--porcelain"), "")
        report = self.review()
        self.assertNotEqual(report["candidates"][0]["assessment"], "Eligible")
        self.assertNotIn("SYNTHETIC_PRIVATE_ENV", json.dumps(report))
        self.assertEqual((target / ".env").read_bytes(), b"SYNTHETIC_PRIVATE_ENV")

    def test_protected_native_states_remain_held(self):
        cases = ("dirty", "staged", "untracked", "unknown-ignored", "locked", "detached", "assume-unchanged",
                 "skip-worktree", "nested-repository", "submodule", "active", "unknown-consumer", "codex", "unknown-owner")
        for mode in cases:
            with self.subTest(mode=mode):
                case = NativeWorktreeCleanup(); case.setUp()
                try:
                    target = case.worktrees[0]
                    if mode in {"dirty", "staged"}:
                        (target / "source.txt").write_bytes(b"unique changed source")
                        if mode == "staged":
                            case.git(target, "add", "source.txt")
                    elif mode == "untracked":
                        (target / "unique.txt").write_bytes(b"unique untracked")
                    elif mode == "unknown-ignored":
                        (target / "cache").mkdir(); (target / "cache/unique.txt").write_bytes(b"unknown ignored")
                    elif mode == "locked":
                        case.git(case.repository, "worktree", "lock", str(target))
                    elif mode == "detached":
                        case.git(target, "checkout", "--detach")
                    elif mode in {"assume-unchanged", "skip-worktree"}:
                        case.git(target, "update-index", "--" + mode, "source.txt")
                        (target / "source.txt").write_bytes(b"hidden unique change")
                    elif mode == "nested-repository":
                        nested = target / "nested"; nested.mkdir(); case.git(nested, "init")
                    elif mode == "submodule":
                        case.git(target, "update-index", "--add", "--cacheinfo", "160000," + case.head + ",nested")
                        case.git(target, "commit", "-m", "Fixture gitlink")
                    elif mode in {"active", "unknown-consumer"}:
                        case.specifications[0]["consumers"][0]["state"] = "active" if mode == "active" else "unknown"
                    else:
                        case.specifications[0]["worktree"]["lifecycle"] = "codex" if mode == "codex" else "unknown"
                    report = case.review()
                    self.assertNotEqual(report["candidates"][0]["assessment"], "Eligible", mode)
                    self.assertTrue(target.exists())
                finally:
                    case.doCleanups()

    def test_main_current_and_generic_executor_remain_protected(self):
        from devspace import git_worktree
        with self.assertRaises(ValueError):
            git_worktree.inspect(str(self.worktrees[1]), str(self.repository), "refs/heads/main")
        with patch.object(git_worktree.Path, "cwd", return_value=self.worktrees[0]):
            self.assertNotEqual(self.review()["candidates"][0]["assessment"], "Eligible")
        self.assessment = {"schema_version": 1, "references": self.references,
                           "candidates": [{key: value for key, value in self.specifications[0].items() if key not in {"operation", "worktree"}}]}
        row = self.review()["candidates"][0]
        self.assertNotEqual(row["assessment"], "Eligible")
        self.assertTrue(self.worktrees[0].exists())

    def test_unknown_versions_types_fields_and_command_text_refuse(self):
        for mode in ("version", "operation", "command", "native-command", "v1-native"):
            with self.subTest(mode=mode):
                original = copy.deepcopy(self.assessment)
                if mode == "version":
                    self.assessment["schema_version"] = 3
                elif mode == "operation":
                    self.specifications[0]["operation"] = "shell-remove"
                elif mode == "command":
                    self.specifications[0]["command"] = "rm -rf /"
                elif mode == "native-command":
                    self.specifications[0]["worktree"]["command"] = "git worktree remove --force"
                else:
                    self.assessment["schema_version"] = 1
                with self.assertRaises(ValueError):
                    self.review()
                self.assessment = original
                self.specifications = self.assessment["candidates"]
        self.retained()

    @unittest.skipUnless(sys.platform == "darwin", "macOS/APFS mutation")
    def test_mixed_directory_and_native_batch_expected_transitions(self):
        fixture = test_plans.AssessedPlans(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        directory = self.repository / "generated"
        directory.mkdir(); (directory / "data.txt").write_bytes(b"ordinary fixture library\n"); (directory / "data.txt").chmod(0o644)
        specification = copy.deepcopy(fixture.specifications[0])
        specification.update(path=str(directory), operation="directory-remove")
        self.references.update(fixture.references)
        self.specifications.insert(0, specification)
        self.freeze()
        directory_row = next(row for row in self.plan["candidates"] if row["path"] == str(directory))
        self.ids.insert(0, directory_row["id"])
        result = self.apply()
        self.assertEqual(result["outcome"], "completed", result)
        self.assertFalse(directory.exists())
        self.assertFalse(self.worktrees[0].exists()); self.assertFalse(self.worktrees[1].exists())
        self.retained()

    @unittest.skipUnless(sys.platform == "darwin", "macOS/APFS mutation")
    def test_external_drift_before_command_stops_batch(self):
        from devspace import git_worktree
        for mode in ("head", "consumer", "ignored", "replace", "topology"):
            with self.subTest(mode=mode):
                case = NativeWorktreeCleanup(); case.setUp()
                try:
                    case.freeze()
                    def drift(plan, selected):
                        target = case.worktrees[1]
                        if mode == "head":
                            (target / "source.txt").write_text("new commit")
                            case.git(target, "add", "source.txt"); case.git(target, "commit", "-m", "External drift")
                        elif mode == "consumer":
                            case.assessment["candidates"][1]["consumers"][0]["state"] = "active"
                            case.assessment_path.write_text(json.dumps(case.assessment))
                        elif mode == "ignored":
                            (target / ".env").write_text("SYNTHETIC_RETAIN")
                        elif mode == "replace":
                            target.rename(case.base / "held-original"); target.mkdir()
                        else:
                            case.git(case.repository, "worktree", "add", "-b", "new-topic", str(case.base / "new-checkout"))
                        return True
                    with patch.object(cleanup, "_state_path", return_value=case.state_path), patch.object(cleanup, "_confirm", side_effect=drift):
                        with self.assertRaises(ValueError):
                            cleanup.apply(case.plan_path, case.assessment_path, case.ids)
                    self.assertTrue(case.worktrees[0].exists()); self.assertTrue(case.worktrees[1].exists())
                finally:
                    case.doCleanups()

    @unittest.skipUnless(sys.platform == "darwin", "macOS/APFS mutation")
    def test_actual_native_refusal_has_no_fallback_and_reconciles(self):
        from devspace import git_worktree
        self.freeze()
        real_run = subprocess.run
        calls = []
        def native_refuse(command, **options):
            calls.append(command)
            lock = real_run(["git", "worktree", "lock", str(self.worktrees[0])], cwd=self.repository, capture_output=True)
            self.assertEqual(lock.returncode, 0)
            return real_run(command, **options)
        with patch.object(git_worktree.subprocess, "run", side_effect=native_refuse):
            result = self.apply()
        self.assertEqual(result["outcome"], "partial-or-failed")
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["native_failure"]["kind"], "native-refusal")
        self.assertGreater(result["native_failure"]["exit_code"], 0)
        self.assertNotIn("--force", calls[0])
        self.assertTrue(all(path.exists() for path in self.worktrees))
        with patch.object(cleanup, "_state_path", return_value=self.state_path):
            result = cleanup.reconcile(self.plan_path)
        self.assertEqual(result["outcome"], "reconciled-no-retry")
        self.retained()

    @unittest.skipUnless(sys.platform == "darwin", "macOS/APFS mutation")
    def test_timeout_after_actual_removal_is_unknown_until_observed(self):
        from devspace import git_worktree
        self.freeze()
        real_run = subprocess.run
        def timeout_after(command, **options):
            result = real_run(command, **options)
            self.assertEqual(result.returncode, 0)
            raise subprocess.TimeoutExpired(command, options["timeout"])
        with patch.object(git_worktree.subprocess, "run", side_effect=timeout_after):
            result = self.apply()
        self.assertEqual(result["outcome"], "partial-or-failed")
        self.assertEqual([target["outcome"] for target in result["targets"]], ["started-outcome-unknown", "not-started"])
        self.assertFalse(self.worktrees[0].exists()); self.assertTrue(self.worktrees[1].exists())
        with patch.object(cleanup, "_state_path", return_value=self.state_path):
            observed = cleanup.reconcile(self.plan_path)
        self.assertEqual([target["outcome"] for target in observed["targets"]],
                         ["absent-and-unregistered-branch-retained", "same-identity-contents-unverified"])
        self.retained()

    @unittest.skipUnless(sys.platform == "darwin", "macOS/APFS mutation")
    def test_result_write_interruption_leaves_durable_reconcilable_intent(self):
        self.freeze()
        original = cleanup.State.write
        def fail_result(state, name, value):
            if name.endswith(".result.json"):
                raise OSError("fixture result unavailable")
            return original(state, name, value)
        with patch.object(cleanup.State, "write", new=fail_result):
            result = self.apply()
        self.assertEqual(result["outcome"], "result-unavailable")
        self.assertTrue((self.state_path / "pending.json").exists())
        with patch.object(cleanup, "_state_path", return_value=self.state_path):
            observed = cleanup.reconcile(self.plan_path)
        self.assertEqual([row["outcome"] for row in observed["targets"]], ["absent-and-unregistered-branch-retained"] * 2)
        self.retained()

    @unittest.skipUnless(sys.platform == "darwin", "macOS/APFS mutation")
    def test_completed_selection_recovery_drift_stops_remaining_work(self):
        from devspace import git_worktree
        self.freeze()
        real_remove = git_worktree.remove
        calls = []
        def mutate_retained_branch(row, limits):
            real_remove(row, limits)
            calls.append(row["path"])
            if len(calls) == 1:
                self.git(self.repository, "branch", "-D", "topic-0")  # fixture-only external drift
        with patch.object(git_worktree, "remove", side_effect=mutate_retained_branch):
            result = self.apply()
        self.assertEqual(result["outcome"], "partial-or-failed")
        self.assertEqual(len(calls), 1)
        self.assertTrue(self.worktrees[1].exists())

    def test_reconcile_never_executes_plan_supplied_binary(self):
        from devspace import git_worktree
        self.freeze()
        row = copy.deepcopy(self.plan["candidates"][0])
        fake = self.base / "fake-git"
        fake.write_text("#!/bin/sh\nexit 0\n"); fake.chmod(0o700)
        row["native"]["executable"] = str(fake)
        row["native"]["executable_identity"] = git_worktree._identity(fake, directory=False)
        with patch.object(git_worktree, "_git", side_effect=AssertionError("must not execute supplied binary")):
            self.assertEqual(git_worktree.observe(row), "unknown-native-identity")

    @unittest.skipUnless(sys.platform == "darwin", "macOS/APFS mutation")
    def test_native_target_filesystem_refusal_precedes_every_mutation(self):
        self.freeze()
        real_filesystem = cleanup._supported_filesystem
        def refuse_target(descriptor):
            if os.fstat(descriptor).st_ino == self.worktrees[1].stat().st_ino:
                raise ValueError("fixture unsupported target filesystem")
            return real_filesystem(descriptor)
        with patch.object(cleanup, "_supported_filesystem", side_effect=refuse_target):
            with self.assertRaises(ValueError):
                self.apply()
        self.assertTrue(all(path.exists() for path in self.worktrees))
        self.retained()

    def generated_ignored(self):
        target = self.worktrees[0]
        (target / "cache").mkdir(); (target / "cache/data.txt").write_bytes(b"generated cache\n")
        (target / "cache").chmod(0o755); (target / "cache/data.txt").chmod(0o644)
        recipe = self.records / "cache-recipe.py"
        recipe.write_text("from pathlib import Path\np=Path('cache'); p.mkdir(exist_ok=True); (p/'data.txt').write_bytes(b'generated cache\\n')\n")
        self.references["recipe"] = {"path": str(recipe), "sha256": hashlib.sha256(recipe.read_bytes()).hexdigest()}
        expected = self.records / "expected-cache.json"
        entries = json.loads((self.records / "expected.json").read_text())["entries"]
        entries += [{"path": "cache", "kind": "directory", "mode": 493},
                    {"path": "cache/data.txt", "kind": "file", "mode": 420, "size": 16,
                     "sha256": hashlib.sha256(b"generated cache\n").hexdigest()}]
        expected.write_text(json.dumps({"schema_version": 1, "entries": entries}))
        self.references["expected-cache"] = {"path": str(expected), "sha256": hashlib.sha256(expected.read_bytes()).hexdigest()}
        self.specifications[0]["content"]["reference"] = "expected-cache"

    def test_ignored_generated_content_needs_separate_recovery_evidence(self):
        self.generated_ignored()
        self.assertNotEqual(self.review()["candidates"][0]["assessment"], "Eligible")
        self.specifications[0]["recovery"].update(inputs=["recipe"], explanation="Tracked source retained; ordinary generated cache can be regenerated from retained recipe.")
        self.assertEqual(self.review()["candidates"][0]["assessment"], "Eligible")

    @unittest.skipUnless(sys.platform == "darwin", "macOS/APFS mutation")
    def test_assessed_generated_ignored_contents_native_removal(self):
        self.generated_ignored()
        self.specifications[0]["recovery"].update(inputs=["recipe"], explanation="Tracked source retained; ordinary generated cache can be regenerated from retained recipe.")
        self.freeze()
        result = self.apply()
        self.assertEqual(result["outcome"], "completed", result)
        self.retained()
        self.assertTrue((self.records / "cache-recipe.py").exists())

    @unittest.skipUnless(sys.platform == "darwin", "macOS/APFS mutation")
    def test_crash_after_native_success_observes_without_replaying(self):
        from devspace import git_worktree
        self.freeze()
        real_remove = git_worktree.remove
        def crash_after(row, limits):
            real_remove(row, limits)
            raise SystemExit("fixture process crash after native success")
        with patch.object(git_worktree, "remove", side_effect=crash_after):
            with self.assertRaises(SystemExit):
                self.apply()
        self.assertFalse(self.worktrees[0].exists()); self.assertTrue(self.worktrees[1].exists())
        self.assertTrue((self.state_path / "pending.json").exists())
        with patch.object(cleanup, "_state_path", return_value=self.state_path), \
                patch.object(git_worktree, "remove", side_effect=AssertionError("reconcile cannot mutate")):
            result = cleanup.reconcile(self.plan_path)
        self.assertEqual([row["outcome"] for row in result["targets"]],
                         ["absent-and-unregistered-branch-retained", "same-identity-contents-unverified"])
        self.retained()

    def test_global_and_task_explicit_native_review_keep_scope(self):
        config = {"schema_version": 1, "roots": [str(self.base)]}
        report = plans.review_scope(config, mode="global", assessment=self.assessment, timeout=30)
        rows = {row["path"]: row for row in report["candidates"]}
        self.assertEqual([rows[str(path)]["assessment"] for path in self.worktrees[:2]], ["Eligible", "Eligible"])
        self.assertEqual(report["plan"]["schema_version"], 2)
        self.assertEqual(set(report["scope_roots"]), {str(self.base), str(self.repository), *map(str, self.worktrees)})
        # Task mode does not add sibling checkouts outside its selected directory.
        task = plans.review_scope(self.repository, mode="task", assessment=self.assessment)
        self.assertTrue(all(row["assessment"] != "Eligible" for row in task["candidates"] if row["path"] in map(str, self.worktrees[:2])))

    @unittest.skipUnless(sys.platform == "darwin", "macOS/APFS mutation")
    def test_global_native_expected_root_transitions_apply(self):
        config = {"schema_version": 1, "roots": [str(self.base)]}
        state = tempfile.TemporaryDirectory(prefix="native-private-state-fixture-")
        self.addCleanup(state.cleanup)
        self.state_path = Path(state.name).resolve() / "private-state"
        config_path = self.records / "config.json"
        config_path.write_text(json.dumps(config))
        report = plans.review_scope(config, mode="global", assessment=self.assessment, timeout=30)
        self.plan_path.write_text(json.dumps(report["plan"]))
        self.assessment_path.write_text(json.dumps(self.assessment))
        self.ids = [row["id"] for row in report["candidates"] if row["path"] in map(str, self.worktrees[:2])]
        result = self.apply(config_path=config_path)
        self.assertEqual(result["outcome"], "completed", result)
        self.retained()

    def test_terminal_displays_native_retained_ref_and_head(self):
        self.freeze()
        terminal = MagicMock()
        terminal.isatty.return_value = True
        opened = MagicMock()
        opened.__enter__.return_value = terminal
        selected = plans.validate_selection(self.plan, self.ids)
        with patch("builtins.open", return_value=opened), patch.object(cleanup.sys.stdin, "isatty", return_value=True), \
                patch.object(cleanup.sys.stdin, "readline", return_value="CANCEL\n"):
            self.assertFalse(cleanup._confirm(self.plan, selected))
        displayed = "".join(call.args[0] for call in terminal.write.call_args_list)
        self.assertIn("refs/heads/topic-0", displayed)
        self.assertIn(self.head, displayed)
        self.assertIn("git-worktree-remove", displayed)
        self.retained()

    def test_native_repository_dependency_cannot_be_another_selected_target(self):
        self.specifications[1]["worktree"]["repository"] = str(self.worktrees[0])
        self.freeze()
        self.assertEqual([row["assessment"] for row in self.plan["candidates"][:2]], ["Eligible", "Eligible"])
        with self.assertRaises(ValueError):
            plans.validate_selection(self.plan, self.ids)
        self.retained()

    def test_selected_review_context_refuses_before_mutation(self):
        report = plans.review_scope(self.worktrees[0], mode="project", assessment=self.assessment, timeout=30)
        plan = report["plan"]
        selected = [row["id"] for row in plan["candidates"] if row["path"] in map(str, self.worktrees[:2])]
        self.assertEqual([row["assessment"] for row in plan["candidates"][:2]], ["Eligible", "Eligible"])
        with self.assertRaisesRegex(ValueError, "review context"):
            plans.validate_selection(plan, selected)
        self.assertTrue(all(path.exists() for path in self.worktrees))
        self.retained()

    def test_v2_unknown_nested_fields_refuse_before_confirmation(self):
        self.freeze()
        original = copy.deepcopy(self.plan)
        for mode in ("observation", "policy", "limits"):
            with self.subTest(mode=mode):
                plan = copy.deepcopy(original)
                if mode == "observation":
                    plan["candidates"][0]["observation"]["unknown-command"] = "must never execute"
                elif mode == "policy":
                    plan["policy"]["unknown"] = True
                else:
                    plan["policy"]["limits"]["unknown"] = True
                plan["digest"] = plans.digest({key:value for key,value in plan.items() if key != "digest"})
                self.plan_path.write_text(json.dumps(plan))
                selected = [row for row in plan["candidates"] if row["id"] in self.ids]
                with self.assertRaises(ValueError):
                    cleanup._revalidate(plan, selected, self.assessment_path, None, None)
                if sys.platform == "darwin":
                    with patch.object(cleanup, "_state_path", return_value=self.state_path), \
                            patch.object(cleanup, "_confirm", side_effect=AssertionError("cannot confirm an unknown contract")):
                        with self.assertRaises(ValueError):
                            cleanup.apply(self.plan_path, self.assessment_path, self.ids)
                self.assertTrue(all(path.exists() for path in self.worktrees))
        self.retained()

    def test_per_worktree_configuration_and_unknown_administration_stay_protected(self):
        administration = Path(self.git(self.worktrees[0], "rev-parse", "--absolute-git-dir").strip())
        for name in ("config.worktree", "unique-data", "refs/unique-reference"):
            with self.subTest(name=name):
                path = administration / name
                path.write_bytes(b"SYNTHETIC_PRIVATE_ADMIN_STATE")
                before = path.read_bytes()
                report = self.review()
                self.assertNotEqual(report["candidates"][0]["assessment"], "Eligible")
                self.assertNotIn("SYNTHETIC_PRIVATE_ADMIN_STATE", json.dumps(report))
                self.assertEqual(path.read_bytes(), before)
                path.unlink()  # only this explicitly created fixture control
        self.retained()

    @unittest.skipUnless(sys.platform == "darwin", "macOS/APFS mutation")
    def test_new_administration_state_after_freeze_prevents_all_native_removal(self):
        self.freeze()
        self.git(self.repository, "config", "extensions.worktreeConfig", "true")
        self.git(self.worktrees[1], "config", "--worktree", "fixture.localSetting", "SYNTHETIC_PRIVATE_ADMIN_STATE")
        administration = Path(self.git(self.worktrees[1], "rev-parse", "--absolute-git-dir").strip())
        before = (administration / "config.worktree").read_bytes()
        from devspace import git_worktree
        with patch.object(git_worktree, "remove", side_effect=AssertionError("native removal must not run")):
            with self.assertRaises(ValueError):
                self.apply()
        self.assertTrue(all(path.exists() for path in self.worktrees))
        self.assertEqual((administration / "config.worktree").read_bytes(), before)
        self.retained()

    def test_unretained_head_reflog_commit_stays_protected(self):
        tree = self.git(self.repository, "rev-parse", "HEAD^{tree}").strip()
        orphan = self.git(self.worktrees[0], "commit-tree", tree, "-m", "Unique unretained fixture history").strip()
        self.git(self.worktrees[0], "update-ref", "HEAD", orphan)
        self.git(self.worktrees[0], "update-ref", "HEAD", self.head)
        self.assertEqual(self.git(self.worktrees[0], "status", "--porcelain"), "")
        report = self.review()
        self.assertNotEqual(report["candidates"][0]["assessment"], "Eligible")
        self.assertEqual(self.git(self.worktrees[0], "rev-parse", orphan).strip(), orphan)
        self.retained()

    def test_old_only_head_reflog_commit_stays_protected(self):
        tree = self.git(self.repository, "rev-parse", "HEAD^{tree}").strip()
        orphan = self.git(self.worktrees[0], "commit-tree", tree, "-m", "Old-only fixture history").strip()
        administration = Path(self.git(self.worktrees[0], "rev-parse", "--absolute-git-dir").strip())
        # Synthetic surviving record after prefix expiry; old OID is not a new OID
        # in any surviving record. Both header IDs are required recovery roots.
        log = administration / "logs/HEAD"
        log.write_bytes((orphan + " " + self.head + " Fixture <fixture@example.invalid> 1700000000 +0000\tSYNTHETIC_SECRET_REFLOG_TRAILER\n").encode())
        self.assertEqual(self.git(self.worktrees[0], "reflog", "show", "--format=%H", "HEAD").strip(), self.head)
        report = self.review()
        self.assertNotEqual(report["candidates"][0]["assessment"], "Eligible")
        self.assertNotIn("SYNTHETIC_SECRET_REFLOG_TRAILER", json.dumps(report))
        self.assertTrue(log.exists())
        self.retained()

    def test_malformed_oversized_and_unterminated_head_logs_stay_unavailable(self):
        administration = Path(self.git(self.worktrees[0], "rev-parse", "--absolute-git-dir").strip())
        log = administration / "logs/HEAD"
        for payload in (b"invalid header\n", b"x" * (1024 * 1024 + 1),
                        (self.head + " " + self.head + " Fixture <fixture@example.invalid> 1700000000 +0000\tunterminated").encode()):
            log.write_bytes(payload)
            report = self.review()
            self.assertNotEqual(report["candidates"][0]["assessment"], "Eligible")
            self.assertEqual(log.read_bytes(), payload)

    def test_fixture_host_configuration_isolation_keeps_repository_filter_protection(self):
        home = self.base / "fixture-home"
        home.mkdir()
        (home / ".gitconfig").write_text('[filter "hosted"]\n clean = cat\n')
        with patch.dict(os.environ, {"HOME": str(home)}):
            report = self.review()
        self.assertEqual([row["assessment"] for row in report["candidates"][:2]], ["Eligible", "Eligible"])
        marker = self.base / "filter-executed"
        script = self.records / "filter.py"
        script.write_text("from pathlib import Path\nimport sys\nPath(sys.argv[1]).write_text('unexpected execution')\nsys.stdout.buffer.write(sys.stdin.buffer.read())\n")
        self.git(self.worktrees[0], "config", "filter.fixture.clean", shlex.join([sys.executable, str(script), str(marker)]))
        (self.worktrees[0] / ".gitattributes").write_text("*.txt filter=fixture\n")
        from devspace import git_worktree
        with self.assertRaisesRegex(ValueError, "content filters"):
            git_worktree.inspect(str(self.repository), str(self.worktrees[0]), "refs/heads/topic-0")
        self.assertFalse(marker.exists())
        self.retained()
