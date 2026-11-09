"""Agent-created disposable Git fixtures, no external fixture remotes."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import copy
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/task-disk-review/scripts"))


def snapshot(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def lineage_snapshot(root):
    """Fixture bytes plus inode identities, independent of product binding helpers."""
    return snapshot(root), {str(path.relative_to(root)): (path.stat().st_dev, path.stat().st_ino)
                            for path in (root, *root.rglob("*"))}


class GitInventory(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="git-inventory-test-")
        self.addCleanup(self.temporary.cleanup)
        self.fixture = Path(self.temporary.name).resolve()
        self.project = self.fixture / "project"
        self.project.mkdir()
        self.environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                                GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
                                GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid")
        # The product deliberately drops inherited GIT_* overrides. Isolate the
        # real Git child at its executable boundary, without changing host config
        # or masking repository-local filter behavior under test.
        executable = shutil.which("git")
        self.assertIsNotNone(executable)
        wrapper = self.fixture / "fixture-git"
        wrapper.write_text("#!/bin/sh\nGIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null exec "
                           + shlex.quote(executable) + ' "$@"\n')
        wrapper.chmod(0o700)
        discovery = patch("devspace.git_inventory.shutil.which", return_value=str(wrapper))
        discovery.start()
        self.addCleanup(discovery.stop)
        self.git("init", "--initial-branch=fixture-main")
        (self.project / ".gitignore").write_text(".env\nignored/\n")
        for name in ("staged.txt", "dirty.txt", "rename-before.txt"):
            (self.project / name).write_text("original " + name)
        self.git("add", ".gitignore", "staged.txt", "dirty.txt", "rename-before.txt")
        self.git("-c", "commit.gpgsign=false", "commit", "-m", "Fixture baseline")

    def git(self, *arguments, cwd=None):
        result = subprocess.run(["git", "--no-optional-locks", *arguments],
                                cwd=cwd or self.project, env=self.environment,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        return result.stdout

    def inventory(self, **limits):
        self.assertIsNotNone(importlib.util.find_spec("devspace.git_inventory"),
                             "read-only Git inventory is not implemented")
        from devspace.git_inventory import inventory_git
        # User Git environment must not redirect discovery to an unrelated repository.
        with patch.dict(os.environ, self.environment, clear=True):
            return inventory_git(self.project, **limits)

    def test_linked_state_and_local_unpushed_commits_preserve_all_bytes(self):
        upstream = self.git("rev-parse", "HEAD").strip().decode()
        self.git("update-ref", "refs/remotes/fixture/main", upstream)
        self.git("config", "branch.fixture-main.remote", "fixture")
        self.git("config", "branch.fixture-main.merge", "refs/heads/main")
        self.git("config", "remote.fixture.fetch", "+refs/heads/*:refs/remotes/fixture/*")
        (self.project / "committed.txt").write_text("local-only commit")
        self.git("add", "committed.txt")
        self.git("-c", "commit.gpgsign=false", "commit", "-m", "Local fixture commit")
        linked = self.fixture / "linked\nworktree"
        self.git("worktree", "add", "--detach", str(linked), upstream)
        self.git("worktree", "lock", "--reason", "SYNTHETIC_PRIVATE_LOCK_REASON", str(linked))
        (linked / ".env").write_text("SYNTHETIC_IGNORED_SECRET")
        self.assertEqual(self.git("status", "--porcelain", cwd=linked), b"")
        (self.project / "staged.txt").write_text("staged new bytes")
        self.git("add", "staged.txt")
        (self.project / "dirty.txt").write_text("unstaged new bytes")
        (self.project / "untracked\nfile.txt").write_text("untracked bytes")
        (self.project / ".env").write_text("SYNTHETIC_IGNORED_SECRET")
        self.git("mv", "rename-before.txt", "rename-after.txt")
        before = snapshot(self.fixture)
        result = self.inventory()
        self.assertTrue(result["complete"], result)
        rows = {row["path"]: row for row in result["worktrees"]}
        project, other = rows[str(self.project)], rows[str(linked)]
        self.assertEqual(project["ahead_of_local_upstream"], 1)
        self.assertEqual(project["upstream"], "fixture/main")
        self.assertEqual(project["staged"], ["rename-after.txt", "staged.txt"])
        self.assertEqual(project["dirty"], ["dirty.txt"])
        self.assertEqual(project["untracked"], ["untracked\nfile.txt"])
        self.assertIn(".env", project["ignored"])
        self.assertTrue(other["locked"])
        self.assertTrue(other["detached"])
        self.assertEqual(other["ignored"], [".env"])
        self.assertIsNone(other["ahead_of_local_upstream"])
        for row in rows.values():
            self.assertEqual(row["activity"], "unknown")
            self.assertTrue(row["report_only"])
            self.assertIn("resume", row["guidance"].lower())
        printed = json.dumps(result)
        self.assertNotIn("SYNTHETIC_IGNORED_SECRET", printed)
        self.assertNotIn("SYNTHETIC_PRIVATE_LOCK_REASON", printed)
        self.assertEqual(snapshot(self.fixture), before)

    def test_missing_upstream_is_unknown_not_zero_unpushed(self):
        result = self.inventory()
        row = result["worktrees"][0]
        self.assertIsNone(row["ahead_of_local_upstream"])
        self.assertIsNone(row["upstream"])
        self.assertIn("unknown", row["upstream_reason"].lower())
        self.assertEqual(row["activity"], "unknown")

    def test_configured_content_filter_is_not_executed_by_inventory(self):
        marker = self.fixture / "filter-executed"
        script = self.fixture / "filter.py"
        script.write_text("import sys\nfrom pathlib import Path\n"
                          "Path(sys.argv[1]).write_text('executed')\n"
                          "sys.stdout.buffer.write(sys.stdin.buffer.read())\n")
        (self.project / ".gitattributes").write_text("*.txt filter=fixture\n")
        self.git("config", "filter.fixture.clean", shlex.join([sys.executable, str(script), str(marker)]))
        # Same size, different bytes forces Git to inspect rather than trust index stat data.
        (self.project / "dirty.txt").write_text("changed! dirty.txt")
        before = snapshot(self.fixture)
        result = self.inventory()
        self.assertFalse(marker.exists(), "Git clean filter ran during read-only inventory")
        row = result["worktrees"][0]
        self.assertFalse(result["complete"])
        self.assertFalse(row["status_complete"])
        self.assertIn("filter", row["status_reason"])
        self.assertEqual(snapshot(self.fixture), before)

    def test_upstream_timeout_marks_inventory_incomplete(self):
        self.assertIsNotNone(importlib.util.find_spec("devspace.git_inventory"),
                             "read-only Git inventory is not implemented")
        from devspace.git_inventory import _git, InspectionUnavailable

        def timeout_on_upstream(executable, directory, arguments, deadline, cancelled):
            if arguments[0] == "rev-parse":
                raise InspectionUnavailable("Git inspection time limit; remaining state unknown")
            return _git(executable, directory, arguments, deadline, cancelled)

        with patch("devspace.git_inventory._git", side_effect=timeout_on_upstream):
            result = self.inventory()
        self.assertFalse(result["complete"])
        self.assertIsNone(result["worktrees"][0]["ahead_of_local_upstream"])

    def test_worktree_budget_exposes_partial_inventory(self):
        linked = self.fixture / "linked"
        self.git("worktree", "add", "--detach", str(linked), "HEAD")
        before = snapshot(self.fixture)
        result = self.inventory(max_worktrees=1)
        self.assertFalse(result["complete"])
        self.assertEqual(len(result["worktrees"]), 1)
        self.assertIn("limit", " ".join(result["limitations"]).lower())
        self.assertEqual(snapshot(self.fixture), before)

    def test_output_budget_never_reports_truncated_status_as_clean(self):
        for number in range(10):
            (self.project / (str(number) + "-" + "x" * 100)).write_text("fixture")
        self.assertIsNotNone(importlib.util.find_spec("devspace.git_inventory"),
                             "read-only Git inventory is not implemented")
        with patch("devspace.git_inventory.OUTPUT_LIMIT", 512):
            result = self.inventory()
        row = result["worktrees"][0]
        self.assertFalse(result["complete"])
        self.assertFalse(row["status_complete"])
        self.assertIsNone(row["staged"])
        self.assertIsNone(row["ignored"])
        self.assertIn("output limit", row["status_reason"])

    def test_non_git_and_cancelled_inventory_are_explicitly_incomplete(self):
        self.assertIsNotNone(importlib.util.find_spec("devspace.git_inventory"),
                             "read-only Git inventory is not implemented")
        from devspace.git_inventory import inventory_git
        non_git = self.fixture / "non-git"
        non_git.mkdir()
        for result in (inventory_git(non_git), inventory_git(self.project, cancelled=lambda: True)):
            self.assertFalse(result["complete"])
            self.assertEqual(result["worktrees"], [])
            self.assertTrue(result["limitations"])

    def test_project_review_includes_linked_contents_without_mutating_git_state(self):
        from devspace.plans import review_scope
        linked = self.fixture / "linked"
        self.git("worktree", "add", "--detach", str(linked), "HEAD")
        (linked / ".env").write_text("SYNTHETIC_LINKED_SECRET")
        (linked / "nested").mkdir()
        (linked / "nested/output").write_text("fixture output")
        (linked / "evidence/node_modules").mkdir(parents=True)
        (linked / "evidence/original-failure.txt").write_text("first attempt")
        before = snapshot(self.fixture)
        with patch.dict(os.environ, self.environment, clear=True):
            report = review_scope(self.project, mode="project")
        self.assertIn(str(linked), report["scope_roots"])
        packet = report["evidence_capture"]["packets"][0]
        self.assertEqual(packet["path"], str(linked / "evidence"))
        self.assertEqual(packet["known_logical_bytes"], len("first attempt"))
        self.assertTrue(packet["environment_hints"])
        from devspace.report import render_text
        self.assertIn("possible nested installed environment", render_text(report))
        rows = {row["path"]: row for row in report["candidates"]}
        self.assertEqual(rows[str(linked / "nested")]["assessment"], "Review")
        self.assertTrue(any(entry["path"] == ".env" and entry["assessment"] == "Keep"
                            for entry in report["linked_reviews"][0]["entries"]))
        self.assertNotIn("SYNTHETIC_LINKED_SECRET", json.dumps(report))
        self.assertEqual(snapshot(self.fixture), before)


    def test_project_exclusions_block_the_first_native_git_command(self):
        from devspace.git_inventory import _git
        from devspace.plans import review_scope
        excluded = self.project / "private"
        excluded.mkdir()
        (excluded / "hidden-name.txt").write_bytes(b"excluded bytes")
        (self.project / "visible.txt").write_bytes(b"useful sibling")
        before = snapshot(self.fixture)
        for exclusion in (self.project, self.fixture, excluded, self.project / ".git",
                          self.project / ".git/index", self.project / "missing/child"):
            with self.subTest(exclusion=exclusion), \
                    patch("devspace.git_inventory._git", wraps=_git) as native:
                report = review_scope(self.project, mode="project", exclusions=[str(exclusion)])
                native.assert_not_called()
                self.assertFalse(report["git"]["complete"])
                self.assertEqual(report["git"]["worktrees"], [])
                self.assertIn("exclu", " ".join(report["git"]["limitations"]).lower())
                if exclusion == excluded:
                    self.assertNotIn("hidden-name.txt", json.dumps(report))
                    self.assertTrue(any(entry["path"] == "visible.txt" for entry in report["entries"]))
                self.assertEqual(snapshot(self.fixture), before)

    def test_linked_exclusions_prevent_probes_and_preserve_unaffected_status(self):
        from devspace.git_inventory import _git
        from devspace.plans import review_scope
        linked = self.fixture / "linked"
        self.git("worktree", "add", "--detach", str(linked), "HEAD")
        private = linked / "private"
        private.mkdir()
        (private / "hidden-name.txt").write_bytes(b"excluded bytes")
        (self.project / "visible.txt").write_bytes(b"useful sibling")
        before = snapshot(self.fixture)
        for exclusion in (linked, private, linked / ".git"):
            with self.subTest(exclusion=exclusion), \
                    patch("devspace.git_inventory._git", wraps=_git) as native:
                report = review_scope(self.project, mode="project", exclusions=[str(exclusion)])
                self.assertFalse(any(call.args[1] == linked for call in native.call_args_list))
                rows = {row["path"]: row for row in report["git"]["worktrees"]}
                self.assertTrue(rows[str(self.project)]["status_complete"])
                self.assertIn("visible.txt", rows[str(self.project)]["untracked"])
                self.assertFalse(rows[str(linked)]["status_complete"])
                self.assertIsNone(rows[str(linked)]["untracked"])
                self.assertIn("exclu", rows[str(linked)]["status_reason"].lower())
                self.assertFalse(report["git"]["complete"])
                self.assertNotIn("hidden-name.txt", json.dumps(report))
                self.assertFalse(any(row["scope"]["canonical"] == str(linked)
                                     for row in report["linked_reviews"]))
                self.assertEqual(snapshot(self.fixture), before)

    def test_exclusion_case_aliases_block_selected_and_linked_probes(self):
        from devspace.git_inventory import _git
        from devspace.plans import review_scope
        selected_alias = self.project.with_name("PROJECT")
        if not selected_alias.exists() or not selected_alias.samefile(self.project):
            self.skipTest("case-sensitive filesystem; exclusion case alias unavailable")
        linked = self.fixture / "Retained"
        self.git("worktree", "add", "--detach", str(linked), "HEAD")
        linked_alias = self.fixture / "retained"
        self.assertTrue(linked_alias.samefile(linked))
        before = snapshot(self.fixture)
        with patch("devspace.git_inventory._git", wraps=_git) as native:
            selected_report = review_scope(self.project, mode="project", exclusions=[str(selected_alias)])
            native.assert_not_called()
        self.assertFalse(selected_report["git"]["complete"])
        with patch("devspace.git_inventory._git", wraps=_git) as native:
            linked_report = review_scope(self.project, mode="project", exclusions=[str(linked_alias)])
            self.assertFalse(any(call.args[1] == linked for call in native.call_args_list))
        rows = {row["path"]: row for row in linked_report["git"]["worktrees"]}
        self.assertTrue(rows[str(self.project)]["status_complete"])
        self.assertFalse(rows[str(linked)]["status_complete"])
        self.assertEqual(snapshot(self.fixture), before)


    def test_linked_selection_excludes_external_git_metadata_before_native_calls(self):
        from devspace.git_inventory import _git
        from devspace.plans import review_scope
        linked = self.fixture / "linked"
        self.git("worktree", "add", "--detach", str(linked), "HEAD")
        (linked / "visible.txt").write_bytes(b"useful linked filesystem observation")
        before = snapshot(self.fixture)
        for exclusion in (self.project, self.project / ".git", self.project / ".git/config",
                          self.project / ".git/worktrees/linked"):
            with self.subTest(exclusion=exclusion), \
                    patch("devspace.git_inventory._git", wraps=_git) as native:
                report = review_scope(linked, mode="project", exclusions=[str(exclusion)])
                native.assert_not_called()
                self.assertFalse(report["git"]["complete"])
                self.assertEqual(report["git"]["worktrees"], [])
                self.assertIn("exclu", " ".join(report["git"]["limitations"]).lower())
                self.assertTrue(any(entry["path"] == "visible.txt" for entry in report["entries"]))
                self.assertEqual(snapshot(self.fixture), before)
        unrelated = self.fixture / "unrelated"
        unrelated.mkdir()
        report = review_scope(linked, mode="project", exclusions=[str(unrelated)])
        self.assertTrue(report["git"]["complete"])
        self.assertTrue(all(row["status_complete"] for row in report["git"]["worktrees"]))


    def test_metadata_symlink_parent_resolution_matches_native_git_before_exclusion(self):
        from devspace.git_inventory import _git
        from devspace.plans import review_scope
        linked = self.fixture / "linked"
        self.git("worktree", "add", "--detach", str(linked), "HEAD")
        (linked / "visible.txt").write_bytes(b"unaffected filesystem observation")
        administration = Path(os.fsdecode(self.git(
            "rev-parse", "--path-format=absolute", "--git-dir", cwd=linked)).removesuffix("\n"))
        common = self.project / ".git"
        marker, common_marker = linked / ".git", administration / "commondir"
        marker_before, common_before = marker.read_bytes(), common_marker.read_bytes()
        decoy = self.fixture / "decoy"
        decoy.mkdir()
        cases = []
        for name, target, metadata_file, prefix, flag in (
                ("gitdir", administration, marker, b"gitdir: ", "--git-dir"),
                ("commondir", common, common_marker, b"", "--git-common-dir")):
            child = target / "path-resolution-child"
            child.mkdir()
            alias = decoy / (name + "-hop")
            alias.symlink_to(child, target_is_directory=True)
            cases.append((name, target, metadata_file, prefix, flag, alias / ".."))
        for name, target, metadata_file, prefix, flag, raw_target in cases:
            marker.write_bytes(marker_before)
            common_marker.write_bytes(common_before)
            metadata_file.write_bytes(prefix + os.fsencode(raw_target) + b"\n")
            native_target = Path(os.fsdecode(self.git(
                "rev-parse", "--path-format=absolute", flag, cwd=linked)).removesuffix("\n")).resolve(strict=True)
            lexical_target = Path(os.path.abspath(raw_target))
            self.assertEqual(native_target, target)
            self.assertEqual(lexical_target, decoy)
            self.assertNotEqual(native_target, lexical_target)
            exclusion = target if name == "gitdir" else common / "config"
            before = snapshot(self.fixture)
            with self.subTest(metadata=name, native_target=native_target, lexical_target=lexical_target), \
                    patch("devspace.git_inventory._git", wraps=_git) as native:
                report = review_scope(linked, mode="project", exclusions=[str(exclusion)])
                native.assert_not_called()
                self.assertFalse(report["git"]["complete"])
                self.assertEqual(report["git"]["worktrees"], [])
                self.assertTrue(any(entry["path"] == "visible.txt" for entry in report["entries"]))
                self.assertEqual(snapshot(self.fixture), before)

    def test_nested_project_does_not_expand_to_parent_repository(self):
        from devspace.plans import review_scope
        nested = self.project / "nested"
        nested.mkdir()
        with patch.dict(os.environ, self.environment, clear=True):
            report = review_scope(nested, mode="project")
        self.assertEqual(report["scope_roots"], [str(nested)])



    def lineage_fixture(self, *, linked_name="lineage\ncheckout"):
        base = self.git("rev-parse", "HEAD").strip().decode()
        self.git("update-ref", "refs/heads/destination", base)
        (self.project / "later.txt").write_text("later primary commit")
        self.git("add", "later.txt")
        self.git("-c", "commit.gpgsign=false", "commit", "-m", "Later")
        head = self.git("rev-parse", "HEAD").strip().decode()
        self.git("update-ref", "refs/heads/retained", head)
        self.git("update-ref", "refs/remotes/misleading/main", head)
        linked = self.fixture / linked_name
        self.git("worktree", "add", "--detach", str(linked), base)
        self.git("checkout", "--detach", head, cwd=linked)
        request = {"schema_version": 1, "repository": str(self.project), "path": str(linked),
                   "expected_head": head, "retained_ref": "refs/heads/retained",
                   "destination_ref": "refs/heads/destination"}
        record = next(r for r in self.inventory()["worktrees"] if r["path"] == str(linked))
        return linked, request, record

    def lineage_trial(self, request, record, **options):
        import devspace.git_inventory as module
        self.assertTrue(hasattr(module, "observe_lineage"), "lineage observer is missing")
        from devspace.git_inventory import observe_lineage
        before = lineage_snapshot(self.fixture)
        original = copy.deepcopy(record)
        try:
            result = observe_lineage(self.project, record, request, deadline=time.monotonic()+10, **options)
        finally:
            self.assertEqual(lineage_snapshot(self.fixture), before)
            self.assertEqual(record, original)
        self.assertNotIn("SYNTHETIC_REFLOG_SECRET", json.dumps(result))
        return result

    def test_lineage_retained_not_integrated(self):
        from devspace.git_inventory import _git
        linked, request, record = self.lineage_fixture()
        self.git("checkout", "-b", "lineage-topic", cwd=linked)
        self.git("config", "remote.misleading.fetch", "+refs/heads/*:refs/remotes/misleading/*")
        self.git("config", "branch.lineage-topic.remote", "misleading")
        self.git("config", "branch.lineage-topic.merge", "refs/heads/main")
        record = next(r for r in self.inventory()["worktrees"] if r["path"] == str(linked))
        self.assertEqual(record["upstream"], "misleading/main")
        self.assertEqual(record["ahead_of_local_upstream"], 0)
        with patch("devspace.git_inventory._git", wraps=_git) as native:
            self.inventory()
            self.assertFalse(any("merge-base" in c.args[2] or "cat-file" in c.args[2] for c in native.call_args_list))
        with patch("devspace.git_inventory._git", wraps=_git) as native:
            result = self.lineage_trial(request, record)
        self.assertEqual(result["status"], "observed", result)
        self.assertIs(result["retention"]["head_in_ref"], True)
        self.assertIs(result["ancestry"]["head_in_destination"], False)
        self.assertIs(result["recovery"]["retained"], True)
        self.assertEqual(result["binding"]["head"], request["expected_head"])
        self.assertEqual(result["binding"]["path"], str(linked))
        self.assertEqual(result["binding"]["retained_oid"], request["expected_head"])
        self.assertEqual(len(result["binding"]["destination_oid"]), 40)
        self.assertEqual(result["release"], "not_established")
        self.assertTrue(all("--no-replace-objects" in c.args[2] for c in native.call_args_list))

    def test_lineage_bound_scope_and_refs(self):
        from devspace.git_inventory import validate_lineage_request
        from devspace.plans import review_scope
        linked, request, record = self.lineage_fixture()
        for delta in ({"extra": 1}, {"expected_head": "HEAD"}, {"schema_version": True},
                      {"path": "relative"}, {"path": str(linked)+"/../x"},
                      {"retained_ref": "main"}, {"destination_ref": "refs/heads/main~1"}):
            with self.subTest(delta=delta), patch("devspace.plans._review_docker_scope", side_effect=AssertionError("discovery")):
                with self.assertRaises(ValueError):
                    review_scope(self.project, mode="project", git_lineage={**request, **delta})
        with patch("devspace.plans._review_docker_scope", side_effect=AssertionError("discovery")):
            with self.assertRaises(ValueError):
                review_scope(self.project, mode="task", git_lineage=request)
        self.assertEqual(validate_lineage_request(request), request)
        for ref in ("refs/heads/missing", "refs/heads/blob"):
            if ref.endswith("blob"):
                blob = self.git("rev-parse", "HEAD:later.txt").strip().decode()
                self.git("update-ref", "refs/remotes/blob", blob)
                ref = "refs/remotes/blob"
            result = self.lineage_trial({**request, "retained_ref": ref}, record)
            self.assertIsNone(result["retention"]["head_in_ref"])
            self.assertNotEqual(result["status"], "observed")
        for delta in ({"path": str(self.fixture / "unregistered")}, {"repository": str(self.fixture / "unrelated")}):
            with patch("devspace.git_inventory.observe_lineage", side_effect=AssertionError("unmatched acquisition")):
                result = review_scope(self.project, mode="project", git_lineage={**request, **delta})
            self.assertEqual(result["git_lineage"]["status"], "not_examined")
        with self.assertRaises(ValueError):
            self.lineage_trial({**request, "retained_ref": "refs/heads/bad..name"}, record)

    def test_lineage_exclusions_before_acquisition(self):
        from devspace.git_inventory import _git
        import devspace.git_worktree as adapter
        linked, request, record = self.lineage_fixture(linked_name="linked")
        admin = self.project / ".git/worktrees/linked"
        for excluded in (self.project, linked, linked / "private", self.project / ".git",
                         admin, admin / "logs/HEAD", self.project / ".git/config"):
            with self.subTest(excluded=excluded), \
                    patch("devspace.git_inventory._git", side_effect=AssertionError("excluded native probe")), \
                    patch("devspace.git_worktree._metadata_file", side_effect=AssertionError("excluded metadata read")), \
                    patch("devspace.git_worktree._administration_state", side_effect=AssertionError("excluded admin read")), \
                    patch("devspace.git_worktree._head_history", side_effect=AssertionError("excluded reflog read")), \
                    patch("devspace.plans._open_parent", side_effect=AssertionError("excluded descriptor acquisition")):
                result = self.lineage_trial(request, record, exclusions=(str(excluded),))
            self.assertNotEqual(result["status"], "observed")
        alias = linked.with_name("LINKED")
        if alias.exists() and alias.samefile(linked):
            self.assertNotEqual(self.lineage_trial(request, record, exclusions=(str(alias),))["status"], "observed")

    def test_lineage_unknown_is_not_negative(self):
        from devspace.git_inventory import _git, GitRefused, InspectionUnavailable, InspectionCancelled
        linked, request, record = self.lineage_fixture(linked_name="linked")
        for code, want in ((1, False), (128, None)):
            def refused(executable, directory, arguments, deadline, cancelled):
                if "merge-base" in arguments:
                    raise GitRefused(code)
                return _git(executable, directory, arguments, deadline, cancelled)
            with patch("devspace.git_inventory._git", side_effect=refused):
                result = self.lineage_trial(request, record)
            self.assertIs(result["ancestry"]["head_in_destination"], want)
        self.git("replace", request["expected_head"], self.git("rev-parse", "refs/heads/destination").strip().decode())
        result = self.lineage_trial(request, record)
        self.assertIs(result["ancestry"]["head_in_destination"], False)
        shallow = self.project / ".git/shallow"
        shallow.write_text(request["expected_head"]+"\n")
        result = self.lineage_trial(request, record)
        self.assertIsNone(result["ancestry"]["head_in_destination"])
        shallow.unlink()
        graft = self.project / ".git/info/grafts"
        graft.write_text("SYNTHETIC_REFLOG_SECRET")
        result = self.lineage_trial(request, record)
        self.assertIsNone(result["ancestry"]["head_in_destination"])
        graft.unlink()
        with patch("devspace.git_inventory.OUTPUT_LIMIT", 1):
            result = self.lineage_trial(request, record)
        self.assertIsNone(result["retention"]["head_in_ref"])
        with self.assertRaises(InspectionCancelled):
            self.lineage_trial(request, record, cancelled=lambda: True)

    def test_lineage_private_recovery_and_status(self):
        linked, request, record = self.lineage_fixture(linked_name="linked")
        admin = self.project / ".git/worktrees/linked"
        self.git("worktree", "lock", str(linked))
        (linked / "dirty.txt").write_text("dirty local bytes")
        (linked / "untracked").write_text("local bytes")
        (linked / ".env").write_text("SYNTHETIC_REFLOG_SECRET")
        record = next(r for r in self.inventory()["worktrees"] if r["path"] == str(linked))
        self.assertTrue(record["locked"])
        self.assertTrue(record["detached"])
        self.assertEqual(record["dirty"], ["dirty.txt"])
        self.assertEqual(record["untracked"], ["untracked"])
        self.assertEqual(record["ignored"], [".env"])
        result = self.lineage_trial(request, record)
        self.assertIsNone(result["recovery"]["retained"], "lock-file private administration is unsupported")
        self.git("worktree", "unlock", str(linked))
        result = self.lineage_trial(request, record)
        self.assertIs(result["recovery"]["retained"], True)
        self.git("update-ref", "refs/heads/retained", "refs/heads/destination")
        result = self.lineage_trial(request, record)
        self.assertIs(result["recovery"]["retained"], False)
        for name, payload in (("config.worktree", b"private"), ("logs/HEAD", b"malformed\n"),
                              ("logs/HEAD", ((request["expected_head"]+" "+request["expected_head"]+" SYNTHETIC_REFLOG_SECRET\n")*129).encode())):
            target = admin / name
            old = target.read_bytes() if target.exists() else None
            target.write_bytes(payload)
            result = self.lineage_trial(request, record)
            self.assertIsNone(result["recovery"]["retained"])
            if old is None: target.unlink()
            else: target.write_bytes(old)
        primary = next(r for r in self.inventory()["worktrees"] if r["path"] == str(self.project))
        result = self.lineage_trial({**request, "path": str(self.project)}, primary)
        self.assertIsNone(result["recovery"]["retained"])

    def test_lineage_recovery_roots_are_commits(self):
        from devspace.git_inventory import _git
        linked, request, record = self.lineage_fixture(linked_name="linked")
        admin = self.project / ".git/worktrees/linked"
        blob = self.git("rev-parse", "HEAD:later.txt").strip().decode()
        tree = self.git("rev-parse", "HEAD^{tree}").strip().decode()
        missing = "1" * 40
        self.git("-c", "tag.gpgSign=false", "tag", "-a", "recovery-tag", "-m", "SYNTHETIC_REFLOG_SECRET")
        tag = self.git("rev-parse", "refs/tags/recovery-tag").strip().decode()
        log = admin / "logs/HEAD"
        original = log.read_bytes()
        for bad in (blob, tree, tag, missing):
            for location in ("old", "new", "ORIG_HEAD"):
                log.write_bytes(original)
                orig = admin / "ORIG_HEAD"
                orig.unlink(missing_ok=True)
                if location == "ORIG_HEAD": orig.write_text(bad+"\n")
                else:
                    roots = [bad, request["expected_head"]] if location == "old" else [request["expected_head"], bad]
                    log.write_text(" ".join(roots)+" SYNTHETIC_REFLOG_SECRET\n")
                with patch("devspace.git_inventory._git", wraps=_git) as native:
                    result = self.lineage_trial(request, record)
                self.assertIsNone(result["recovery"]["retained"], (bad, location, result))
                self.assertIs(result["retention"]["head_in_ref"], True)
                self.assertIs(result["ancestry"]["head_in_destination"], False)
                commands = [list(c.args[2]) for c in native.call_args_list]
                self.assertTrue(any(c[-3:] == ["cat-file", "-t", bad] for c in commands), commands)
                self.assertFalse(any("rev-list" in c for c in commands))
        log.write_bytes(original)
        for malformed in ("HEAD", "0"*40, request["expected_head"]+" extra", request["expected_head"]+"\n\n"):
            (admin / "ORIG_HEAD").write_text(malformed+"\n")
            self.assertIsNone(self.lineage_trial(request, record)["recovery"]["retained"])
        (admin / "ORIG_HEAD").write_text(request["expected_head"]+"\n")
        with patch("devspace.git_inventory._git", wraps=_git) as native:
            result = self.lineage_trial(request, record)
        self.assertIs(result["recovery"]["retained"], True)
        types = [c.args[2][-1] for c in native.call_args_list if "cat-file" in c.args[2]]
        self.assertTrue(set([request["expected_head"], self.git("rev-parse", "refs/heads/destination").strip().decode()]) <= set(types))

    def test_lineage_binding_drift(self):
        from devspace.git_inventory import _git
        linked, request, record = self.lineage_fixture(linked_name="linked")
        mismatch = self.lineage_trial({**request, "expected_head": "1"*40}, record)
        self.assertEqual(mismatch["status"], "changed")
        fired = False
        def drift(executable, directory, arguments, deadline, cancelled):
            nonlocal fired
            output = _git(executable, directory, arguments, deadline, cancelled)
            if "merge-base" in arguments and not fired:
                fired = True
                self.git("update-ref", "refs/heads/destination", request["expected_head"])
            return output
        with patch("devspace.git_inventory._git", side_effect=drift):
            from devspace.git_inventory import observe_lineage
            result = observe_lineage(self.project, record, request, deadline=time.monotonic()+10)
        self.assertTrue(fired)
        self.assertEqual(result["status"], "changed", result)
        self.assertIsNone(result["retention"]["head_in_ref"])
        self.assertIsNone(result["ancestry"]["head_in_destination"])
        self.assertIsNone(result["recovery"]["retained"])

    def test_lineage_graph_policy_drift(self):
        from devspace.git_inventory import _git, observe_lineage
        linked, request, record = self.lineage_fixture(linked_name="linked")
        for relative in ("shallow", "info/grafts"):
            target = self.project / ".git" / relative
            fired = False
            def drift(executable, directory, arguments, deadline, cancelled):
                nonlocal fired
                if "merge-base" in arguments and not fired:
                    fired = True
                    target.write_text(request["expected_head"]+"\n")
                return _git(executable, directory, arguments, deadline, cancelled)
            with patch("devspace.git_inventory._git", side_effect=drift):
                result = observe_lineage(self.project, record, request, deadline=time.monotonic()+10)
            self.assertTrue(fired)
            self.assertIn(result["status"], ("changed", "unavailable"))
            self.assertIsNone(result["retention"]["head_in_ref"])
            self.assertIsNone(result["ancestry"]["head_in_destination"])
            target.unlink()



    def test_lineage_external_exclusions_and_unmatched_acquisition(self):
        import devspace.git_worktree as adapter
        import devspace.plans as plans
        from devspace.git_inventory import observe_lineage
        linked, request, record = self.lineage_fixture(linked_name="linked")
        admin = self.project / ".git/worktrees/linked"
        common = self.project / ".git"
        # Selecting a linked checkout must identify external administration before native work.
        selected = {**request, "repository": str(linked)}
        for excluded in (admin, admin / "logs/HEAD", common / "config", common):
            def metadata(path, *args, **kwargs):
                self.assertFalse(Path(path) == excluded or excluded in Path(path).parents, "excluded metadata acquired")
                return original_metadata(path, *args, **kwargs)
            def parent(path):
                self.assertFalse(Path(path) == excluded or excluded in Path(path).parents, "excluded descriptor traversal")
                return original_parent(path)
            original_metadata, original_parent = adapter._metadata_file, plans._open_parent
            before = lineage_snapshot(self.fixture)
            with self.subTest(excluded=excluded), \
                    patch("devspace.git_inventory._git", side_effect=AssertionError("excluded native")), \
                    patch("devspace.git_worktree._metadata_file", side_effect=metadata), \
                    patch("devspace.git_worktree._administration_state", side_effect=AssertionError("excluded admin")), \
                    patch("devspace.git_worktree._head_history", side_effect=AssertionError("excluded history")), \
                    patch("devspace.plans._open_parent", side_effect=parent):
                result = observe_lineage(linked, record, selected, exclusions=(str(excluded),), deadline=time.monotonic()+10)
            self.assertNotEqual(result["status"], "observed")
            self.assertEqual(lineage_snapshot(self.fixture), before)
        for delta in ({"path": str(self.fixture / "never-open")}, {"repository": str(self.fixture / "never-probe")}):
            with patch("devspace.git_worktree._metadata_file", side_effect=AssertionError("unmatched read")), \
                    patch("devspace.plans._open_parent", side_effect=AssertionError("unmatched traversal")), \
                    patch("devspace.git_inventory._git", side_effect=AssertionError("unmatched native")):
                result = observe_lineage(self.project, record, {**request, **delta}, deadline=time.monotonic()+10)
            self.assertEqual(result["status"], "not_examined")

    def test_lineage_native_shallow_missing_object_and_filter(self):
        from devspace.git_inventory import inventory_git, observe_lineage, _git, InspectionUnavailable
        linked, request, record = self.lineage_fixture(linked_name="linked")
        clone = self.fixture / "shallow"
        self.git("clone", "--no-local", "--depth=1", self.project.as_uri(), str(clone))
        self.assertEqual(self.git("rev-parse", "--is-shallow-repository", cwd=clone), b"true\n")
        self.git("update-ref", "refs/heads/retained", "HEAD", cwd=clone)
        self.git("update-ref", "refs/heads/destination", "HEAD", cwd=clone)
        with patch.dict(os.environ, self.environment, clear=True):
            clone_record = inventory_git(clone)["worktrees"][0]
        before = lineage_snapshot(self.fixture)
        result = observe_lineage(clone, clone_record, {**request, "repository": str(clone), "path": str(clone)},
                                 deadline=time.monotonic()+10)
        self.assertIsNone(result["retention"]["head_in_ref"])
        self.assertIsNone(result["ancestry"]["head_in_destination"])
        self.assertEqual(lineage_snapshot(self.fixture), before)
        dest = self.git("rev-parse", "refs/heads/destination").strip().decode()
        loose = self.project / ".git/objects" / dest[:2] / dest[2:]
        loose.unlink()
        from devspace.git_inventory import run_readonly
        with patch("devspace.git_inventory.run_readonly", wraps=run_readonly) as runner:
            result = self.lineage_trial(request, record)
        for call in runner.call_args_list:
            self.assertNotIn("fetch", call.args[0])
            self.assertEqual(call.args[2]["GIT_NO_LAZY_FETCH"], "1")
            self.assertEqual(call.args[2]["GIT_ALLOW_PROTOCOL"], "")
        self.assertIsNone(result["ancestry"]["head_in_destination"])
        self.assertNotEqual(result["status"], "observed")
        # Configured clean/process content is refused by ordinary inventory; observer cannot seed from it.
        marker = self.fixture / "filter-ran"
        self.git("config", "filter.fixture.clean", "touch " + shlex.quote(str(marker)))
        bad_record = next(r for r in self.inventory()["worktrees"] if r["path"] == str(linked))
        self.assertFalse(bad_record["status_complete"])
        with patch("devspace.git_inventory._git", side_effect=AssertionError("failed status acquisition")):
            result = self.lineage_trial(request, bad_record)
        self.assertEqual(result["status"], "not_examined")
        self.assertFalse(marker.exists())

    def test_lineage_stable_executable_alias(self):
        linked, request, record = self.lineage_fixture(linked_name="linked")
        alias = self.fixture / "git-alias"
        alias.symlink_to(self.fixture / "fixture-git")
        with patch("devspace.git_inventory.shutil.which", return_value=str(alias)):
            result = self.lineage_trial(request, record)
        self.assertEqual(result["status"], "observed", result)
        self.assertEqual(result["binding"]["executable"], str(self.fixture / "fixture-git"))

    def test_lineage_sha256_and_unsupported_runtime(self):
        from devspace.git_inventory import inventory_git, observe_lineage, _git
        linked, request, record = self.lineage_fixture(linked_name="linked")
        for format_result in (b"future-format\n", b"sha256\n"):
            def unsupported(executable, directory, arguments, deadline, cancelled):
                if "--show-object-format" in arguments: return format_result
                return _git(executable, directory, arguments, deadline, cancelled)
            with patch("devspace.git_inventory._git", side_effect=unsupported):
                result = self.lineage_trial(request, record)
            self.assertEqual(result["status"], "unavailable")
        with patch("devspace.git_inventory.shutil.which", return_value=None):
            self.assertEqual(self.lineage_trial(request, record)["status"], "unavailable")
        repo = self.fixture / "sha256"
        repo.mkdir()
        init = subprocess.run(["git", "init", "--object-format=sha256", "--initial-branch=fixture-main"],
                              cwd=repo, env=self.environment, capture_output=True, timeout=10)
        if init.returncode:
            self.skipTest("installed Git does not support SHA-256 repository initialization")
        (repo / "data").write_text("sha256 fixture")
        self.git("add", "data", cwd=repo)
        self.git("-c", "commit.gpgsign=false", "commit", "-m", "SHA256", cwd=repo)
        head = self.git("rev-parse", "HEAD", cwd=repo).strip().decode()
        self.assertEqual(len(head), 64)
        self.git("update-ref", "refs/heads/retained", head, cwd=repo)
        self.git("update-ref", "refs/heads/destination", head, cwd=repo)
        other = self.fixture / "sha256-linked"
        self.git("worktree", "add", "--detach", str(other), head, cwd=repo)
        with patch.dict(os.environ, self.environment, clear=True):
            row = next(r for r in inventory_git(repo)["worktrees"] if r["path"] == str(other))
        before = lineage_snapshot(self.fixture)
        result = observe_lineage(repo, row, {**request, "repository": str(repo), "path": str(other), "expected_head": head},
                                 deadline=time.monotonic()+10)
        self.assertEqual(result["status"], "observed", result)
        self.assertEqual(result["binding"]["head"], head)
        self.assertEqual(result["binding"]["object_format"], "sha256")
        self.assertIs(result["retention"]["head_in_ref"], True)
        self.assertIs(result["ancestry"]["head_in_destination"], True)
        self.assertEqual(lineage_snapshot(self.fixture), before)

    def test_lineage_metadata_failure_and_all_binding_drift(self):
        from devspace.git_inventory import _git, observe_lineage
        linked, request, record = self.lineage_fixture(linked_name="linked")
        # Inaccessible/linked metadata must be advisory, including _identity's ValueError.
        with patch("devspace.git_worktree._identity", side_effect=ValueError("SYNTHETIC_REFLOG_SECRET")):
            result = self.lineage_trial(request, record)
        self.assertEqual(result["status"], "unavailable")
        base = self.git("rev-parse", "refs/heads/destination").strip().decode()
        for kind in ("head", "branch", "retained", "checkout", "marker", "common"):
            fired = False
            saved = {}
            def drift(executable, directory, arguments, deadline, cancelled):
                nonlocal fired
                output = _git(executable, directory, arguments, deadline, cancelled)
                if "merge-base" in arguments and not fired:
                    fired = True
                    if kind == "head": self.git("checkout", "--detach", base, cwd=linked)
                    elif kind == "branch": self.git("checkout", "-b", "attached", cwd=linked)
                    elif kind == "retained": self.git("update-ref", request["retained_ref"], base)
                    elif kind == "checkout":
                        linked.rename(linked.with_name("moved")); linked.mkdir()
                    elif kind == "marker":
                        saved["marker"] = (linked / ".git").read_bytes()
                        (linked / ".git").unlink()
                        (linked / ".git").write_bytes(saved["marker"])
                    else:
                        saved["common"] = (self.project / ".git/worktrees/linked/commondir").read_bytes()
                        (self.project / ".git/worktrees/linked/commondir").write_text("../..//\n")
                return output
            with self.subTest(kind=kind), patch("devspace.git_inventory._git", side_effect=drift):
                result = observe_lineage(self.project, record, request, deadline=time.monotonic()+10)
            self.assertTrue(fired)
            self.assertEqual(result["status"], "changed", result)
            self.assertIsNone(result["retention"]["head_in_ref"])
            self.assertIsNone(result["ancestry"]["head_in_destination"])
            self.assertIsNone(result["recovery"]["retained"])
            if kind == "checkout":
                linked.rmdir(); linked.with_name("moved").rename(linked)
            if kind == "common": (self.project / ".git/worktrees/linked/commondir").write_bytes(saved["common"])
            self.git("checkout", "--detach", request["expected_head"], cwd=linked)
            self.git("update-ref", request["retained_ref"], request["expected_head"])



    def test_lineage_old_reflog_and_orig_roots_independent_of_head(self):
        from devspace.git_inventory import _git
        linked, request, record = self.lineage_fixture(linked_name="linked")
        admin = self.project / ".git/worktrees/linked"
        head = request["expected_head"]
        base = self.git("rev-parse", "refs/heads/destination").strip().decode()
        self.git("checkout", "-b", "side-history", base)
        (self.project / "side.txt").write_text("side commit")
        self.git("add", "side.txt")
        self.git("-c", "commit.gpgsign=false", "commit", "-m", "SYNTHETIC_REFLOG_SECRET")
        side = self.git("rev-parse", "HEAD").strip().decode()
        self.git("checkout", "fixture-main")
        log = admin / "logs/HEAD"
        original = log.read_bytes()
        # Both syntactic old/new roots matter even when the actual current HEAD is retained.
        for old, new, orig in ((side, head, None), (head, side, None), (base, head, side)):
            log.write_text(old+" "+new+" SYNTHETIC_REFLOG_SECRET\n")
            (admin / "ORIG_HEAD").unlink(missing_ok=True)
            if orig: (admin / "ORIG_HEAD").write_text(orig+"\n")
            with patch("devspace.git_inventory._git", wraps=_git) as native:
                result = self.lineage_trial(request, record)
            self.assertIs(result["retention"]["head_in_ref"], True)
            self.assertIs(result["recovery"]["retained"], False)
            self.assertEqual(result["recovery"]["root_count"], len({head, old, new, orig}-{None}))
            commands = [list(call.args[2]) for call in native.call_args_list]
            query = next(i for i,c in enumerate(commands) if "--max-count=1" in c)
            types = {c[-1] for c in commands[:query] if c[-3:-1] == ["cat-file", "-t"]}
            self.assertTrue({head, old, new, orig}-{None} <= types)
        # Private refs are refused without enumerating their payloads as recovery.
        (admin / "refs").mkdir(exist_ok=True)
        (admin / "refs/private").write_text("SYNTHETIC_REFLOG_SECRET")
        self.assertIsNone(self.lineage_trial(request, record)["recovery"]["retained"])

    def test_lineage_exclusion_case_alias(self):
        linked, request, record = self.lineage_fixture(linked_name="Linked")
        alias = linked.with_name("linked")
        if not alias.exists() or not alias.samefile(linked):
            self.skipTest("case-sensitive filesystem; lineage exclusion case alias unavailable")
        with patch("devspace.git_inventory._git", side_effect=AssertionError("case-alias native acquisition")), \
                patch("devspace.plans._open_parent", side_effect=AssertionError("case-alias descriptor acquisition")):
            result = self.lineage_trial(request, record, exclusions=(str(alias),))
        self.assertNotEqual(result["status"], "observed")

    def test_lineage_timeout_and_final_revalidation_exhaustion(self):
        from devspace.git_inventory import _git, InspectionUnavailable, observe_lineage
        linked, request, record = self.lineage_fixture(linked_name="linked")
        for boundary in ("merge-base", "rev-list", "final-head"):
            clock = [time.monotonic()]
            head_reads = 0
            def exhausted(executable, directory, arguments, deadline, cancelled):
                nonlocal head_reads
                if arguments[-3:] == ["rev-parse", "--verify", "HEAD"]: head_reads += 1
                if boundary in arguments or boundary == "final-head" and head_reads == 2:
                    clock[0] = deadline + 1
                    raise InspectionUnavailable("SYNTHETIC_REFLOG_SECRET")
                return _git(executable, directory, arguments, deadline, cancelled)
            with patch("devspace.git_inventory.time.monotonic", side_effect=lambda: clock[0]), \
                    patch("devspace.git_inventory._git", side_effect=exhausted):
                result = self.lineage_trial(request, record)
            self.assertNotEqual(result["status"], "observed")
            self.assertIsNone(result["retention"]["head_in_ref"])
            self.assertIsNone(result["ancestry"]["head_in_destination"])
            self.assertIsNone(result["recovery"]["retained"])
        with patch("devspace.plans._open_parent", side_effect=AssertionError("expired descriptor acquisition")), \
                patch("devspace.git_inventory._git", side_effect=AssertionError("expired native acquisition")):
            result = observe_lineage(self.project, record, request, deadline=time.monotonic()-1)
        self.assertNotEqual(result["status"], "observed")


if __name__ == "__main__":
    unittest.main()
