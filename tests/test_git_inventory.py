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
        # Construction commits can launch detached maintenance even with optional locks disabled.
        # Keep this isolation on fixture commands; the product's Git wrapper stays unchanged.
        result = subprocess.run(["git", "--no-optional-locks", "-c", "maintenance.auto=false",
                                 "-c", "gc.auto=0", *arguments],
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

    def test_fixture_mutations_do_not_launch_auto_maintenance(self):
        # Fixture writes must finish their work before complete read-only snapshots begin.
        trace = self.fixture / "fixture-commit-trace.json"
        with patch.dict(self.environment, {"GIT_TRACE2_EVENT": str(trace)}):
            self.git("commit", "--allow-empty", "-m", "Isolated fixture empty commit")
        events = [json.loads(line) for line in trace.read_text().splitlines()]
        children = [event["argv"] for event in events if event.get("event") == "child_start"]
        self.assertFalse(any("maintenance" in command or "gc" in command for command in children), children)

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


    def integration_fixture(self, kind="merge"):
        """Real history: independent destination work, then explicit integration."""
        linked, request, record = self.lineage_fixture(linked_name="integration-checkout")
        base = self.git("rev-parse", "refs/heads/destination").strip().decode()
        if kind == "squash":
            (self.project / "second.txt").write_text("second source commit\n")
            self.git("add", "second.txt")
            self.git("commit", "-m", "Second source")
        source = self.git("rev-parse", "HEAD").strip().decode()
        self.git("update-ref", "refs/heads/retained", source)
        self.git("checkout", "--detach", source, cwd=linked)
        self.git("checkout", "destination")
        (self.project / "destination-only.txt").write_text("independent destination work\n")
        self.git("add", "destination-only.txt")
        self.git("commit", "-m", "Destination work")
        if kind == "merge":
            self.git("merge", "--no-ff", "--no-edit", source)
        elif kind == "squash":
            self.git("merge", "--squash", source)
            self.git("commit", "-m", "Squash source")
        else:
            self.git("cherry-pick", source)
        destination = self.git("rev-parse", "HEAD").strip().decode()
        request["expected_head"] = source
        request["integration"] = {"kind": "merge" if kind == "merge" else "squash",
                                  "source_commit": source, "destination_commit": destination}
        if kind != "merge": request["integration"]["source_base_commit"] = base
        record = next(r for r in self.inventory()["worktrees"] if r["path"] == str(linked))
        return linked, request, record

    def test_lineage_integration_claim_validation(self):
        # Catches accepting revision expressions, missing explicit bases or extra authority fields.
        from devspace.git_inventory import validate_lineage_request
        linked, request, record = self.lineage_fixture()
        source = request["expected_head"]
        valid = {"kind": "merge", "source_commit": source, "destination_commit": source}
        for claim in (valid, {**valid, "kind": "squash", "source_base_commit": source}):
            self.assertEqual(validate_lineage_request({**request, "integration": claim})["integration"], claim)
        for claim in (None, [], {}, {**valid, "kind": "cherry-pick"}, {**valid, "source_commit": "HEAD"},
                      {**valid, "destination_commit": "-"+"a"*39}, {**valid, "source_commit": "A"*40},
                      {**valid, "kind": "squash"}, {**valid, "source_base_commit": source},
                      {**valid, "verified": True}, {**valid, "source_commit": True}):
            with self.subTest(claim=claim), patch("devspace.git_inventory._git", side_effect=AssertionError("shape must not probe")):
                with self.assertRaises(ValueError):
                    validate_lineage_request({**request, "integration": claim})

    def test_lineage_integration_current_and_old_merge(self):
        # Catches promotion of an older merged source to integration of actual current HEAD.
        linked, request, record = self.integration_fixture()
        current = self.lineage_trial(request, record)
        evidence = current["integration"]
        self.assertEqual(evidence["status"], "observed", current)
        for field in ("source_matches_head", "source_in_head", "destination_in_current_destination",
                      "current_destination_matches_claim", "current_destination_tree_matches_claim"):
            self.assertIs(evidence[field], True, field)
        self.assertEqual(evidence["source_in_parents"], [False, True])
        self.assertEqual(evidence["destination_parent_count"], 2)
        self.assertIs(current["ancestry"]["head_in_destination"], True)
        self.assertEqual(current["patch_equivalence"]["status"], "not_requested")
        # Claim existence does not make it reachable from the bound current destination.
        self.git("update-ref", request["destination_ref"], request["expected_head"])
        outside = self.lineage_trial(request, record)
        self.assertIs(outside["integration"]["destination_in_current_destination"], False)
        self.assertIs(outside["integration"]["current_destination_matches_claim"], False)
        self.git("update-ref", request["destination_ref"], request["integration"]["destination_commit"])
        self.git("checkout", "fixture-main")
        (self.project / "after-merge.txt").write_text("new unmerged source\n")
        self.git("add", "after-merge.txt")
        self.git("commit", "-m", "New unmerged source")
        head = self.git("rev-parse", "HEAD").strip().decode()
        self.git("update-ref", "refs/heads/retained", head)
        self.git("checkout", "--detach", head, cwd=linked)
        request["expected_head"] = head
        record = next(r for r in self.inventory()["worktrees"] if r["path"] == str(linked))
        old = self.lineage_trial(request, record)
        self.assertIs(old["integration"]["source_matches_head"], False)
        self.assertIs(old["integration"]["source_in_head"], True)
        self.assertEqual(old["integration"]["source_in_parents"], [False, True])
        self.assertIs(old["ancestry"]["head_in_destination"], False)
        self.assertIs(old["retention"]["head_in_ref"], True)
        self.assertEqual(old["binding"]["head"], head)
        self.assertEqual(old["integration"]["source_commit"], request["integration"]["source_commit"])

    def test_lineage_integration_squash_exact_delta_and_sentinels(self):
        # Catches patch-ID substitution, omitted no-ext-diff/textconv and provenance promotion.
        from devspace.git_inventory import _git
        linked, request, record = self.integration_fixture("squash")
        marker = self.fixture / "external-command-executed"
        script = self.fixture / "external-command.py"
        script.write_text("from pathlib import Path\nPath("+repr(str(marker))+ ").write_text('executed')\n")
        command = shlex.join([sys.executable, str(script)])
        (self.project / ".gitattributes").write_text("*.txt diff=fixture\n")
        self.git("config", "diff.external", command)
        self.git("config", "diff.fixture.textconv", command)
        # Establish that each configured sentinel really executes when explicitly enabled.
        claim = request["integration"]
        self.git("diff", "--ext-diff", claim["source_base_commit"], claim["source_commit"], "--")
        self.assertTrue(marker.exists(), "external diff sentinel is not armed")
        marker.unlink()
        self.git("config", "--unset", "diff.external")
        self.git("diff", "--textconv", claim["source_base_commit"], claim["source_commit"], "--")
        self.assertTrue(marker.exists(), "textconv sentinel is not armed")
        marker.unlink()
        self.git("config", "diff.external", command)
        with patch("devspace.git_inventory._git", wraps=_git) as native:
            result = self.lineage_trial(request, record)
        comparison = result["patch_equivalence"]
        self.assertEqual(comparison["method"], "exact-tree-entry-delta")
        self.assertIs(comparison["equal"], True, result)
        self.assertEqual(comparison["source_path_count"], 2)
        self.assertEqual(comparison["destination_path_count"], 2)
        self.assertEqual(result["integration"]["squash_provenance"], "unverified")
        self.assertEqual(result["integration"]["current_content_preservation"], "unestablished")
        self.assertIs(result["ancestry"]["head_in_destination"], False)
        diffs = [c.args[2] for c in native.call_args_list if "diff-tree" in c.args[2]]
        self.assertEqual(len(diffs), 2)
        for args in diffs:
            for flag in ("--raw", "-r", "-z", "--no-renames", "--no-ext-diff", "--no-textconv", "--abbrev=40"):
                self.assertIn(flag, args)
        self.assertFalse(marker.exists())
        printed = json.dumps(result)
        self.assertNotIn("second source commit", printed)
        self.assertNotIn("destination-only.txt", printed)
        self.assertNotIn("external-command", printed)

    def test_lineage_integration_cherry_pick_is_delta_not_ancestry(self):
        linked, request, record = self.integration_fixture("cherry-pick")
        result = self.lineage_trial(request, record)
        self.assertIs(result["patch_equivalence"]["equal"], True, result)
        self.assertIs(result["ancestry"]["head_in_destination"], False)
        self.assertEqual(result["integration"]["squash_provenance"], "unverified")
        self.assertEqual(result["release"], "not_established")

    def test_lineage_integration_revert_and_later_destination(self):
        # Catches graph reachability being used as current semantic preservation.
        linked, request, record = self.integration_fixture()
        merge = request["integration"]["destination_commit"]
        for operation in ("later", "revert"):
            if operation == "later":
                (self.project / "later-destination.txt").write_text("later destination work\n")
                self.git("add", "later-destination.txt")
                self.git("commit", "-m", "Later destination")
            else:
                self.git("revert", "--no-edit", "-m", "1", merge)
            result = self.lineage_trial(request, record)
            evidence = result["integration"]
            self.assertIs(result["ancestry"]["head_in_destination"], True)
            self.assertIs(evidence["destination_in_current_destination"], True)
            self.assertIs(evidence["current_destination_matches_claim"], False)
            self.assertIs(evidence["current_destination_tree_matches_claim"], False)
            self.assertEqual(evidence["current_destination_commit"], self.git("rev-parse", "HEAD").strip().decode())
            self.assertEqual(evidence["current_content_preservation"], "unestablished")
            self.assertNotIn("reverted", json.dumps(result))
            self.assertEqual(result["release"], "not_established")
        # A later empty commit changes commit identity without changing its tree.
        self.git("reset", "--hard", merge)
        self.git("commit", "--allow-empty", "-m", "Same tree later")
        same_tree = self.lineage_trial(request, record)["integration"]
        self.assertIs(same_tree["current_destination_matches_claim"], False)
        self.assertIs(same_tree["current_destination_tree_matches_claim"], True)
        self.assertEqual(same_tree["current_content_preservation"], "unestablished")

    def test_lineage_integration_wrong_base_whitespace_and_nonempty(self):
        # Catches equal empty deltas, wrong-base equivalence and whitespace normalization.
        linked, request, record = self.integration_fixture("squash")
        claim = request["integration"]
        first_source = self.git("rev-parse", claim["source_commit"]+"^").strip().decode()
        for base, want in ((first_source, False), (claim["source_commit"], None)):
            trial = {**request, "integration": {**claim, "source_base_commit": base}}
            result = self.lineage_trial(trial, record)
            self.assertIs(result["patch_equivalence"]["equal"], want, result)
            self.assertIs(result["retention"]["head_in_ref"], True)
        # Same paths, whitespace-only destination change: exact blob identities differ.
        self.git("reset", "--hard", claim["destination_commit"]+"^")
        self.git("merge", "--squash", claim["source_commit"])
        (self.project / "second.txt").write_text("second  source commit\n")
        self.git("add", "second.txt")
        self.git("commit", "-m", "Whitespace variant")
        destination = self.git("rev-parse", "HEAD").strip().decode()
        result = self.lineage_trial({**request, "integration": {**claim, "destination_commit": destination}}, record)
        self.assertIs(result["patch_equivalence"]["equal"], False, result)
        self.assertEqual(result["integration"]["squash_provenance"], "unverified")
        self.git("commit", "--allow-empty", "-m", "Empty destination delta")
        empty = self.git("rev-parse", "HEAD").strip().decode()
        result = self.lineage_trial({**request, "integration": {**claim, "destination_commit": empty}}, record)
        self.assertIsNone(result["patch_equivalence"]["equal"], result)
        self.assertIs(result["retention"]["head_in_ref"], True)

    def test_lineage_integration_endpoint_and_topology_failures(self):
        # Catches missing/noncommit/unrelated endpoint promotion and unsupported parent topology.
        linked, request, record = self.integration_fixture("squash")
        claim = request["integration"]
        blob = self.git("rev-parse", "HEAD:later.txt").strip().decode()
        tree = self.git("rev-parse", "HEAD^{tree}").strip().decode()
        self.git("tag", "-a", "endpoint-tag", "-m", "Endpoint tag", claim["source_commit"])
        tag = self.git("rev-parse", "endpoint-tag").strip().decode()
        root = self.git("rev-list", "--max-parents=0", "HEAD").strip().decode()
        unrelated = self.git("commit-tree", tree, "-m", "Unrelated root").strip().decode()
        for delta in ({"source_commit": unrelated}, {"source_commit": "f"*40}, {"destination_commit": "e"*40},
                      {"source_base_commit": "d"*40}, {"source_commit": blob},
                      {"source_base_commit": tree}, {"destination_commit": tag},
                      {"source_base_commit": claim["destination_commit"]}, {"destination_commit": root},
                      {"source_commit": "a"*64}):
            with self.subTest(delta=delta):
                result = self.lineage_trial({**request, "integration": {**claim, **delta}}, record)
                self.assertIsNone(result["patch_equivalence"]["equal"], result)
                self.assertNotEqual(result["integration"]["status"], "observed")
                self.assertIs(result["retention"]["head_in_ref"], True)
                self.assertIs(result["ancestry"]["head_in_destination"], False)
                if delta.get("source_commit") == unrelated:
                    self.assertIs(result["integration"]["source_in_head"], False)
        self.git("merge", "--no-ff", "--no-edit", claim["source_commit"])
        merge = self.git("rev-parse", "HEAD").strip().decode()
        result = self.lineage_trial({**request, "integration": {**claim, "destination_commit": merge}}, record)
        self.assertIsNone(result["patch_equivalence"]["equal"])
        self.assertEqual(result["integration"]["destination_parent_count"], 2)
        # Conversely a claimed merge on a real one-parent commit is unresolved.
        merge_claim = {k: v for k, v in claim.items() if k != "source_base_commit"}
        merge_claim["kind"] = "merge"
        result = self.lineage_trial({**request, "integration": merge_claim}, record)
        self.assertEqual(result["integration"]["status"], "unavailable")
        self.assertIsNone(result["integration"]["source_in_parents"])
        # A real three-parent commit is also outside the explicitly two-parent contract.
        octopus = self.git("commit-tree", tree, "-p", claim["source_commit"], "-p", root,
                           "-p", claim["destination_commit"], "-m", "Three parents").strip().decode()
        result = self.lineage_trial({**request, "integration": {**merge_claim, "destination_commit": octopus}}, record)
        self.assertEqual(result["integration"]["status"], "unavailable")
        self.assertEqual(result["integration"]["destination_parent_count"], 3)
        self.assertIsNone(result["integration"]["source_in_parents"])

    def test_lineage_integration_changed_base_objects(self):
        # Same conceptual edit after a changed file base must not equal exact object deltas.
        linked, request, record = self.lineage_fixture(linked_name="changed-base")
        base = self.git("rev-parse", "refs/heads/destination").strip().decode()
        self.git("checkout", "-b", "changed-source", base)
        (self.project / "dirty.txt").write_text("original dirty.txt\nfeature\n")
        self.git("add", "dirty.txt")
        self.git("commit", "-m", "Source edit")
        source = self.git("rev-parse", "HEAD").strip().decode()
        self.git("update-ref", "refs/heads/retained", source)
        self.git("checkout", "--detach", source, cwd=linked)
        self.git("checkout", "destination")
        (self.project / "dirty.txt").write_text("changed base\n")
        self.git("add", "dirty.txt")
        self.git("commit", "-m", "Changed base")
        (self.project / "dirty.txt").write_text("changed base\nfeature\n")
        self.git("add", "dirty.txt")
        self.git("commit", "-m", "Same conceptual edit")
        destination = self.git("rev-parse", "HEAD").strip().decode()
        request.update(expected_head=source, integration={"kind": "squash", "source_base_commit": base,
                       "source_commit": source, "destination_commit": destination})
        record = next(r for r in self.inventory()["worktrees"] if r["path"] == str(linked))
        result = self.lineage_trial(request, record)
        self.assertIs(result["patch_equivalence"]["equal"], False, result)
        self.assertEqual(result["integration"]["squash_provenance"], "unverified")

    def test_lineage_integration_limits_and_gitlinks(self):
        # Catches actual next-size path overflow and raw gitlink entries being certified.
        from devspace.git_inventory import _git
        linked, request, record = self.integration_fixture("squash")
        claim = request["integration"]
        self.git("checkout", "fixture-main")
        # The source already adds later.txt and second.txt: 127 additions make 129 total.
        for number in range(127): (self.project / ("delta-"+str(number))).write_text("bounded\n")
        self.git("add", ".")
        self.git("commit", "-m", "129 total changed paths")
        large = self.git("rev-parse", "HEAD").strip().decode()
        self.git("update-ref", request["retained_ref"], large)
        self.git("checkout", "--detach", large, cwd=linked)
        request.update(expected_head=large, integration={**claim, "source_commit": large})
        record = next(row for row in self.inventory()["worktrees"] if row["path"] == str(linked))
        deltas = []
        def native_delta(executable, directory, arguments, deadline, cancelled):
            raw = _git(executable, directory, arguments, deadline, cancelled)
            if "diff-tree" in arguments: deltas.append(raw)
            return raw
        with patch("devspace.git_inventory._git", side_effect=native_delta):
            result = self.lineage_trial(request, record)
        self.assertEqual(len(deltas), 1, "129-path source delta must reach the real comparison")
        self.assertEqual(deltas[0].count(b"\0") // 2, 129)
        self.assertIs(result["integration"]["source_matches_head"], True)
        self.assertIs(result["integration"]["source_in_head"], True)
        self.assertEqual(result["integration"]["destination_parent_count"], 1)
        self.assertEqual(result["integration"]["reason"], "comparison_unavailable")
        self.assertIsNone(result["patch_equivalence"]["equal"], result)
        self.assertIs(result["retention"]["head_in_ref"], True)
        self.assertIs(result["ancestry"]["head_in_destination"], False)
        self.git("reset", "--hard", claim["source_commit"])
        self.git("update-index", "--add", "--cacheinfo", "160000,"+claim["source_commit"]+",module")
        self.git("commit", "-m", "Gitlink source")
        gitlink = self.git("rev-parse", "HEAD").strip().decode()
        self.git("update-ref", request["retained_ref"], gitlink)
        self.git("checkout", "--detach", gitlink, cwd=linked)
        request.update(expected_head=gitlink, integration={**claim, "source_commit": gitlink})
        record = next(row for row in self.inventory()["worktrees"] if row["path"] == str(linked))
        deltas.clear()
        with patch("devspace.git_inventory._git", side_effect=native_delta):
            result = self.lineage_trial(request, record)
        self.assertEqual(len(deltas), 1, "gitlink source delta must reach raw entry validation")
        self.assertIn(b":000000 160000 ", deltas[0])
        self.assertIs(result["integration"]["source_matches_head"], True)
        self.assertIs(result["integration"]["source_in_head"], True)
        self.assertEqual(result["integration"]["reason"], "comparison_unavailable")
        self.assertIsNone(result["patch_equivalence"]["equal"], result)
        self.assertIs(result["retention"]["head_in_ref"], True)
        self.assertIs(result["ancestry"]["head_in_destination"], False)

    def test_lineage_integration_shallow_and_comparison_errors(self):
        from devspace.git_inventory import _git, GitRefused, InspectionUnavailable
        linked, request, record = self.integration_fixture("squash")
        shallow = self.project / ".git/shallow"
        shallow.write_text(request["expected_head"]+"\n")
        result = self.lineage_trial(request, record)
        self.assertIsNone(result["patch_equivalence"]["equal"], result)
        self.assertIsNone(result["integration"]["source_in_head"])
        shallow.unlink()
        for error in (GitRefused(128), InspectionUnavailable("SYNTHETIC_REFLOG_SECRET")):
            def failed(executable, directory, arguments, deadline, cancelled):
                if "diff-tree" in arguments: raise error
                return _git(executable, directory, arguments, deadline, cancelled)
            with patch("devspace.git_inventory._git", side_effect=failed):
                result = self.lineage_trial(request, record)
            self.assertIsNone(result["patch_equivalence"]["equal"])
            self.assertIs(result["retention"]["head_in_ref"], True)
            self.assertIs(result["ancestry"]["head_in_destination"], False)
        # Prove raw fixture size independently, then reach the actual bounded runner's cap.
        # Keep this source growth distinct from the bound current destination ref.
        self.git("checkout", "-b", "oversized-source")
        # One short directory and 200-byte leaf names stay below Mac's path/component limits.
        # More records produce the real >1 MiB response without requiring deep paths.
        directory = self.project / "large-delta"
        directory.mkdir()
        self.assertLess(len(os.fsencode(directory / ("0000-"+"x"*195))), 768,
                        "large-output fixture paths must fit the supported Mac path limit")
        for number in range(3600):
            (directory / (f"{number:04d}-"+"x"*195)).write_text("metadata limit\n")
        self.git("add", ".")
        self.git("commit", "-m", "Oversized metadata delta")
        large = self.git("rev-parse", "HEAD").strip().decode()
        base = request["integration"]["destination_commit"]
        raw = self.git("diff-tree", "--no-commit-id", "--raw", "-r", "-z", "--no-renames",
                       "--no-ext-diff", "--no-textconv", "--abbrev=40", base, large, "--")
        self.assertGreater(len(raw), 1024*1024, "fixture must exceed the actual 1 MiB response cap")
        self.assertEqual(raw.count(b"\0") // 2, 3600)
        self.git("update-ref", request["retained_ref"], large)
        self.git("checkout", "--detach", large, cwd=linked)
        request.update(expected_head=large, integration={**request["integration"], "source_commit": large,
                                                        "source_base_commit": base})
        record = next(row for row in self.inventory()["worktrees"] if row["path"] == str(linked))
        self.assertTrue(record["status_complete"], "ordinary status must finish before the output-cap trial")
        attempted, refusals = [], []
        def bounded_delta(executable, directory, arguments, deadline, cancelled):
            if "diff-tree" not in arguments:
                return _git(executable, directory, arguments, deadline, cancelled)
            attempted.append(arguments)
            try:
                return _git(executable, directory, arguments, deadline, cancelled)
            except InspectionUnavailable as error:
                refusals.append(str(error))
                raise
        with patch("devspace.git_inventory._git", side_effect=bounded_delta):
            result = self.lineage_trial(request, record)
        self.assertEqual(len(attempted), 1, "oversized source delta must reach the real bounded runner")
        self.assertEqual(attempted[0][-3:], [base, large, "--"])
        self.assertEqual(refusals, ["Git output limit; truncated state is unknown"])
        self.assertIs(result["integration"]["source_matches_head"], True)
        self.assertIs(result["integration"]["source_in_head"], True)
        self.assertEqual(result["integration"]["reason"], "comparison_unavailable")
        self.assertIsNone(result["patch_equivalence"]["equal"], result)
        self.assertIs(result["retention"]["head_in_ref"], True)
        self.assertIs(result["ancestry"]["head_in_destination"], False)

    def test_lineage_integration_graph_policy_drift(self):
        # Catches comparisons performed after/bypassing final path, ref and graph-policy checks.
        from devspace.git_inventory import _git, observe_lineage, InspectionUnavailable
        linked, request, record = self.integration_fixture("squash")
        for drift in ("shallow", "info/grafts", "destination-ref", "timeout"):
            expected_after = None
            original_record = copy.deepcopy(record)
            fired = False
            clock = [time.monotonic()]
            changed_path = self.project / ".git" / drift
            original_destination = request["integration"]["destination_commit"]
            diff_count = 0
            def mutate(executable, directory, arguments, deadline, cancelled):
                nonlocal fired, diff_count, expected_after
                output = _git(executable, directory, arguments, deadline, cancelled)
                if "diff-tree" in arguments:
                    diff_count += 1
                    if diff_count == 2:
                        fired = True
                        if drift == "destination-ref":
                            self.git("update-ref", request["destination_ref"], request["expected_head"])
                        elif drift == "timeout": clock[0] = deadline + 1
                        else: changed_path.write_text(request["expected_head"]+"\n")
                        expected_after = lineage_snapshot(self.fixture)
                return output
            with patch("devspace.git_inventory._git", side_effect=mutate), \
                    patch("devspace.git_inventory.time.monotonic", side_effect=lambda: clock[0]):
                result = observe_lineage(self.project, record, request, deadline=clock[0]+10)
            self.assertTrue(fired)
            self.assertEqual(lineage_snapshot(self.fixture), expected_after)
            self.assertEqual(record, original_record)
            self.assertEqual(result["status"], "changed", result)
            for category, field in (("retention", "head_in_ref"), ("ancestry", "head_in_destination"),
                                    ("recovery", "retained"), ("patch_equivalence", "equal")):
                self.assertIsNone(result[category][field], (category, result))
            for field in ("source_matches_head", "source_in_head", "source_in_parents", "destination_parent_count",
                          "destination_in_current_destination", "current_destination_matches_claim",
                          "current_destination_tree_matches_claim", "current_destination_commit"):
                self.assertIsNone(result["integration"][field], (field, result))
            self.assertIsNone(result["patch_equivalence"]["source_path_count"])
            self.assertIsNone(result["patch_equivalence"]["destination_path_count"])
            self.assertIsNone(result["patch_equivalence"]["destination_base_commit"])
            if drift == "destination-ref": self.git("update-ref", request["destination_ref"], original_destination)
            elif drift != "timeout": changed_path.unlink()


    def test_lineage_integration_final_administration_completion_guard(self):
        # Catches final-read cancellation lost on actual drift or supported read failures.
        from devspace import git_inventory as inventory, git_worktree as adapter
        linked, request, record = self.integration_fixture("squash")
        real_administration = adapter._administration_state
        real_exclusions = inventory._check_exclusions
        for outcome, cancel_after in (("unchanged", False), ("unchanged", True), ("drift", False),
                                      ("drift", True), ("ValueError", False), ("ValueError", True),
                                      ("OSError", False), ("OSError", True), ("deadline", False)):
            reads = 0
            completed_last_read = False
            clock = [time.monotonic()]
            deadline = clock[0] + 10
            expected_after = lineage_snapshot(self.fixture)
            original_record = copy.deepcopy(record)
            drift_path = None
            drift_original = None
            def administration(path):
                nonlocal reads, completed_last_read, expected_after, drift_path, drift_original
                reads += 1
                if reads == 2 and outcome == "drift":
                    drift_path = path / "ORIG_HEAD"
                    drift_original = drift_path.read_bytes() if drift_path.exists() else None
                    changed_root = request["integration"]["destination_commit"]
                    if drift_original == (changed_root+"\n").encode(): changed_root = request["expected_head"]
                    drift_path.write_text(changed_root+"\n")
                result = real_administration(path)
                if reads == 2:
                    completed_last_read = True
                    expected_after = lineage_snapshot(self.fixture)
                    if outcome == "deadline": clock[0] = deadline + 1
                    if outcome == "ValueError": raise ValueError("controlled final metadata failure")
                    if outcome == "OSError": raise OSError("controlled final metadata failure")
                return result
            def exclusions(*args):
                self.assertFalse(completed_last_read, "completion decision must acquire no more metadata")
                return real_exclusions(*args)
            with self.subTest(outcome=outcome, cancelled=cancel_after):
                try:
                    with patch("devspace.git_worktree._administration_state", side_effect=administration), \
                            patch("devspace.git_inventory._check_exclusions", side_effect=exclusions), \
                            patch("devspace.git_inventory.time.monotonic", side_effect=lambda: clock[0]):
                        options = {"deadline": deadline, "cancelled": lambda: completed_last_read and cancel_after}
                        if cancel_after:
                            with self.assertRaises(inventory.InspectionCancelled):
                                inventory.observe_lineage(self.project, record, request, **options)
                        else:
                            result = inventory.observe_lineage(self.project, record, request, **options)
                            self.assertEqual(result["status"], "observed" if outcome == "unchanged" else "changed", result)
                            self.assertEqual(result["integration"]["source_commit"], request["integration"]["source_commit"])
                            if outcome == "unchanged":
                                self.assertIs(result["patch_equivalence"]["equal"], True)
                                self.assertIs(result["retention"]["head_in_ref"], True)
                            else:
                                for category, field in (("retention", "head_in_ref"), ("ancestry", "head_in_destination"),
                                                        ("recovery", "retained"), ("patch_equivalence", "equal")):
                                    self.assertIsNone(result[category][field])
                                for field in ("source_matches_head", "source_in_head", "source_in_parents", "destination_parent_count",
                                              "destination_in_current_destination", "current_destination_matches_claim",
                                              "current_destination_tree_matches_claim", "current_destination_commit"):
                                    self.assertIsNone(result["integration"][field], field)
                                for field in ("source_path_count", "destination_path_count", "destination_base_commit"):
                                    self.assertIsNone(result["patch_equivalence"][field], field)
                finally:
                    self.assertEqual(reads, 2)
                    self.assertEqual(lineage_snapshot(self.fixture), expected_after)
                    self.assertEqual(record, original_record)
                    if drift_path is not None:
                        if drift_original is None: drift_path.unlink()
                        else: drift_path.write_bytes(drift_original)

    def test_lineage_integration_invalid_ref_keeps_input_precedence(self):
        # Catches failure-boundary cancellation masking an already established invalid ref.
        from devspace import git_inventory as inventory
        linked, request, record = self.integration_fixture("squash")
        cancelled = [False]
        def reject_ref(executable, directory, arguments, deadline, callback):
            try:
                return inventory_git(executable, directory, arguments, deadline, callback)
            except inventory.GitRefused:
                if "check-ref-format" in arguments: cancelled[0] = True
                raise
        inventory_git = inventory._git
        with patch("devspace.git_inventory._git", side_effect=reject_ref):
            with self.assertRaises(ValueError):
                self.lineage_trial({**request, "retained_ref": "refs/heads/bad..name"}, record,
                                   cancelled=lambda: cancelled[0])
        self.assertTrue(cancelled[0])


    def test_lineage_integration_malformed_delta_stays_unknown(self):
        # Corrupt real bounded metadata output; graph commands and fixture history stay real.
        from devspace.git_inventory import _git, InspectionCancelled
        linked, request, record = self.integration_fixture("squash")
        def transform(raw, corruption):
            if corruption == "truncated": return raw[:-1]
            if corruption == "missing-path": return raw.split(b"\0", 1)[0] + b"\0"
            if corruption == "duplicate": return raw + raw
            if corruption == "bad-mode": return raw.replace(b":000000", b":999999", 1)
            return raw.replace(b":000000", b":100644", 1)
        for corruption in ("truncated", "missing-path", "duplicate", "bad-mode", "inconsistent-entry"):
            def malformed(executable, directory, arguments, deadline, cancelled):
                raw = _git(executable, directory, arguments, deadline, cancelled)
                return transform(raw, corruption) if "diff-tree" in arguments else raw
            with patch("devspace.git_inventory._git", side_effect=malformed):
                result = self.lineage_trial(request, record)
            self.assertIsNone(result["patch_equivalence"]["equal"], (corruption, result))
            self.assertIs(result["retention"]["head_in_ref"], True)
            self.assertIs(result["ancestry"]["head_in_destination"], False)
        def cancelled_comparison(executable, directory, arguments, deadline, cancelled):
            if "diff-tree" in arguments: raise InspectionCancelled("cancelled")
            return _git(executable, directory, arguments, deadline, cancelled)
        with patch("devspace.git_inventory._git", side_effect=cancelled_comparison), self.assertRaises(InspectionCancelled):
            self.lineage_trial(request, record)

    def test_lineage_integration_modes_paths_and_128_path_boundary(self):
        # Catches dropping modes/paths, rename normalization or off-by-one path limits.
        linked, request, record = self.lineage_fixture(linked_name="delta-paths")
        base = self.git("rev-parse", "refs/heads/destination").strip().decode()
        self.git("checkout", "-b", "delta-source", base)
        self.git("mv", "rename-before.txt", "renamed\nfile.txt")
        self.git("rm", "staged.txt")
        (self.project / "dirty.txt").chmod(0o755)
        for number in range(124): (self.project / ("path-"+str(number))).write_text("same literal bytes\n")
        self.git("add", ".")
        self.git("commit", "-m", "128 changes including modes and unusual path")
        source = self.git("rev-parse", "HEAD").strip().decode()
        self.git("update-ref", "refs/heads/retained", source)
        self.git("checkout", "--detach", source, cwd=linked)
        self.git("checkout", "destination")
        self.git("merge", "--squash", source)
        self.git("commit", "-m", "Exact 128 path squash")
        destination = self.git("rev-parse", "HEAD").strip().decode()
        claim = {"kind": "squash", "source_base_commit": base, "source_commit": source, "destination_commit": destination}
        request.update(expected_head=source, integration=claim)
        record = next(r for r in self.inventory()["worktrees"] if r["path"] == str(linked))
        exact = self.lineage_trial(request, record)
        self.assertIs(exact["patch_equivalence"]["equal"], True, exact)
        self.assertEqual(exact["patch_equivalence"]["source_path_count"], 128)
        self.assertEqual(exact["patch_equivalence"]["destination_path_count"], 128)
        # Keep identical file bytes but lose the executable mode in destination.
        (self.project / "dirty.txt").chmod(0o644)
        self.git("add", "dirty.txt")
        self.git("commit", "--amend", "--no-edit")
        changed = self.git("rev-parse", "HEAD").strip().decode()
        mismatch = self.lineage_trial({**request, "integration": {**claim, "destination_commit": changed}}, record)
        self.assertIs(mismatch["patch_equivalence"]["equal"], False, mismatch)
        # Same number/bytes of entries, with a different changed path.
        self.git("mv", "path-0", "different-path")
        (self.project / "dirty.txt").chmod(0o755)
        self.git("add", ".")
        self.git("commit", "--amend", "--no-edit")
        changed = self.git("rev-parse", "HEAD").strip().decode()
        mismatch = self.lineage_trial({**request, "integration": {**claim, "destination_commit": changed}}, record)
        self.assertIs(mismatch["patch_equivalence"]["equal"], False, mismatch)

    def test_lineage_integration_sha256_delta(self):
        # Catches truncated/assumed SHA-1 endpoint or raw-delta handling.
        from devspace.git_inventory import inventory_git, observe_lineage
        repo = self.fixture / "sha256-integration"
        repo.mkdir()
        init = subprocess.run(["git", "init", "--object-format=sha256", "--initial-branch=fixture-main"],
                              cwd=repo, env=self.environment, capture_output=True, timeout=10)
        if init.returncode: self.skipTest("installed Git does not support SHA-256 repository initialization")
        (repo / "data").write_text("base\n")
        self.git("add", "data", cwd=repo)
        self.git("commit", "-m", "Base", cwd=repo)
        base = self.git("rev-parse", "HEAD", cwd=repo).strip().decode()
        (repo / "data").write_text("source\n")
        self.git("commit", "-am", "Source", cwd=repo)
        source = self.git("rev-parse", "HEAD", cwd=repo).strip().decode()
        self.git("update-ref", "refs/heads/retained", source, cwd=repo)
        linked = self.fixture / "sha256-integration-linked"
        self.git("worktree", "add", "--detach", str(linked), source, cwd=repo)
        self.git("checkout", "-b", "destination", base, cwd=repo)
        self.git("cherry-pick", source, cwd=repo)
        destination = self.git("rev-parse", "HEAD", cwd=repo).strip().decode()
        request = {"schema_version": 1, "repository": str(repo), "path": str(linked), "expected_head": source,
                   "retained_ref": "refs/heads/retained", "destination_ref": "refs/heads/destination",
                   "integration": {"kind": "squash", "source_base_commit": base,
                                   "source_commit": source, "destination_commit": destination}}
        with patch.dict(os.environ, self.environment, clear=True):
            record = next(row for row in inventory_git(repo)["worktrees"] if row["path"] == str(linked))
        before = lineage_snapshot(self.fixture)
        result = observe_lineage(repo, record, request, deadline=time.monotonic()+10)
        self.assertEqual(result["status"], "observed", result)
        self.assertEqual(result["binding"]["object_format"], "sha256")
        self.assertEqual(len(result["integration"]["source_commit"]), 64)
        self.assertIs(result["patch_equivalence"]["equal"], True)
        self.assertEqual(lineage_snapshot(self.fixture), before)


if __name__ == "__main__":
    unittest.main()
