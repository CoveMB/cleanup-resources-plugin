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
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/task-disk-review/scripts"))


def snapshot(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


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
        """Project review observes linked checkout content without changing Git state."""
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
        """Excluding selected content or metadata prevents all native Git probes."""
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
        """An excluded linked checkout remains unknown while the selected checkout is observed."""
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
        """Case-insensitive aliases cannot bypass selected or linked exclusions."""
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
        """Linked selections refuse excluded common metadata before running Git."""
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
        """Ambiguous metadata links never bypass exclusions through symlink-parent traversal."""
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


if __name__ == "__main__":
    unittest.main()
