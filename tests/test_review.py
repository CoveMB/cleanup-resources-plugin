"""Disposable synthetic fixtures only; subprocesses exercise the user's CLI."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/task-disk-review/scripts"))

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills/task-disk-review/scripts/devspace.py"


class ReviewCLI(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="task-review-test-")
        self.addCleanup(self.temporary.cleanup)
        self.fixture = Path(self.temporary.name).resolve()
        self.task = self.fixture / "selected"
        self.task.mkdir()

    def run_cli(self, *arguments):
        return subprocess.run([sys.executable, "-B", str(CLI), *arguments],
                              text=True, capture_output=True, timeout=15)

    def review(self, *arguments):
        result = self.run_cli("review", "--task", str(self.task), "--json", *arguments)
        self.assertIn(result.returncode, (0, 2), result.stderr)
        return result, json.loads(result.stdout)

    def test_selected_nested_scope_protects_state_and_failure_without_payloads(self):
        for name in (".env", "cache.db", ".wrangler/state/store", "evidence/original-failure/log", "dist/output", "source.py"):
            path = self.task / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("SYNTHETIC_SECRET_PAYLOAD")
        (self.fixture / "outside.txt").write_text("OUTSIDE_PAYLOAD")
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in self.fixture.rglob("*") if p.is_file()}
        result, report = self.review()
        self.assertEqual(result.returncode, 2)  # protected state is skipped, not zero
        rows = {row["path"]: row for row in report["entries"]}
        for name in (".env", "cache.db", ".wrangler", "evidence/original-failure/log"):
            self.assertEqual(rows[name]["assessment"], "Keep")
        self.assertEqual(rows["dist/output"]["assessment"], "Review")
        self.assertNotIn("SYNTHETIC_SECRET_PAYLOAD", result.stdout)
        self.assertNotIn("outside.txt", result.stdout)
        self.assertIsNone(report["thread_identity"])
        self.assertEqual(report["scope"]["mode"], "task")
        self.assertTrue(report["host"]["system"])
        self.assertEqual(before, {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in self.fixture.rglob("*") if p.is_file()})

    def test_text_report_reaches_terminal(self):
        (self.task / "build").mkdir()
        (self.task / "build/output").write_bytes(b"1234567")
        result = self.run_cli("review", "--task", str(self.task))
        self.assertEqual(result.returncode, 0, result.stderr)
        for phrase in ("Read-only task review", "Thread: unknown", "Examined:", "Skipped:",
                       "Inaccessible:", "Logical", "Allocated", "Review", "build/output"):
            self.assertIn(phrase, result.stdout)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_links_never_enumerate_target(self):
        outside = self.fixture / "outside"
        outside.mkdir()
        (outside / "outside-secret-name").write_text("OUTSIDE")
        try:
            (self.task / "link").symlink_to(outside, target_is_directory=True)
            (self.task / "loop").symlink_to(self.task, target_is_directory=True)
        except OSError:
            self.skipTest("symlink creation unavailable")
        result, report = self.review()
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("outside-secret-name", result.stdout)
        self.assertEqual(report["coverage"]["skipped"], 2)
        self.assertTrue(all(row["coverage"] == "skipped" for row in report["entries"]))
        selected_link = self.run_cli("review", "--task", str(self.task / "link"), "--json")
        self.assertEqual(selected_link.returncode, 1)
        self.assertNotIn("outside-secret-name", selected_link.stdout)

    def test_bounds_report_unexamined_usage(self):
        for number in range(8):
            (self.task / str(number)).write_bytes(b"payload")
        result, report = self.review("--max-entries", "3")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report["coverage"]["examined"], 3)
        self.assertEqual(len(report["entries"]), 3)
        self.assertFalse(report["coverage"]["complete"])
        self.assertIn("entry limit", report["coverage"]["stop_reason"])
        self.assertFalse(report["size"]["complete"])
        deep = self.task / "nested/deeper"
        deep.mkdir(parents=True)
        (deep / "hidden-by-depth").write_text("x")
        result, report = self.review("--max-depth", "1")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("hidden-by-depth", result.stdout)

    @unittest.skipUnless(hasattr(os, "link"), "hardlinks unavailable")
    def test_hardlinks_count_once_and_sparse_allocation_is_separate(self):
        first = self.task / "one"
        first.write_bytes(b"x" * 8192)
        try:
            os.link(first, self.task / "two")
        except OSError:
            self.skipTest("hardlink creation unavailable")
        sparse = self.task / "sparse"
        with sparse.open("wb") as stream:
            stream.seek(4 * 1024 * 1024)
            stream.write(b"x")
        _, report = self.review()
        self.assertEqual(report["size"]["logical_bytes"], 8192 + 4 * 1024 * 1024 + 1)
        self.assertEqual(report["size"]["duplicate_hardlinks"], 1)
        if hasattr(first.stat(), "st_blocks"):
            self.assertEqual(report["size"]["allocated_bytes"],
                             (first.stat().st_blocks + sparse.stat().st_blocks) * 512)
        self.assertIn("hard links", " ".join(report["limitations"]))

    def test_invalid_scope_and_no_apply(self):
        missing = self.run_cli("review", "--task", str(self.fixture / "missing"), "--json")
        self.assertEqual(missing.returncode, 1)
        self.assertEqual(json.loads(missing.stdout)["coverage"]["inaccessible"], 1)
        self.assertNotIn("Traceback", missing.stderr)
        apply = self.run_cli("apply", "--task", str(self.task))
        self.assertNotEqual(apply.returncode, 0)
        self.assertTrue(self.task.is_dir())

    def test_unsafe_filename_is_escaped_in_terminal(self):
        if os.name == "nt":
            self.skipTest("Windows forbids control characters in filenames")
        (self.task / "name\x1b[31m\nforge").write_text("x")
        result = self.run_cli("review", "--task", str(self.task))
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("\x1b", result.stdout)
        self.assertIn("\\u001b", result.stdout)


class ReviewFailures(unittest.TestCase):
    setUp = ReviewCLI.setUp
    run_cli = ReviewCLI.run_cli
    review = ReviewCLI.review
    # Kernel failures/capabilities are simulated only where real setup would require mounts or a second host.
    def test_permission_denial_is_unknown_and_files_survive(self):
        denied = self.task / "denied"
        denied.mkdir()
        payload = denied / "private-name"
        payload.write_text("SYNTHETIC_DENIED_PAYLOAD")
        denied.chmod(0)
        self.addCleanup(denied.chmod, 0o700)
        if os.access(denied, os.R_OK):
            self.skipTest("host identity can bypass mode bits")
        result, report = self.review()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report["coverage"]["inaccessible"], 1)
        self.assertFalse(report["size"]["complete"])
        self.assertNotIn("private-name", result.stdout)
        self.assertNotIn("SYNTHETIC_DENIED_PAYLOAD", result.stdout)
        denied.chmod(0o700)
        self.assertEqual(payload.read_text(), "SYNTHETIC_DENIED_PAYLOAD")

    def test_direct_selection_inside_protected_state_does_not_enumerate(self):
        state = self.task / ".wrangler/state"
        state.mkdir(parents=True)
        (state / "private-state-name").write_text("SYNTHETIC_STATE_SECRET")
        result = self.run_cli("review", "--task", str(state), "--json")
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["coverage"]["skipped"], 1)
        self.assertFalse(report["size"]["complete"])
        self.assertNotIn("private-state-name", result.stdout)
        self.assertEqual(report["entries"][0]["assessment"], "Keep")
        self.assertEqual((state / "private-state-name").read_text(), "SYNTHETIC_STATE_SECRET")

    def test_direct_selection_inside_evidence_retains_descendants(self):
        evidence = self.task / "evidence/run"
        evidence.mkdir(parents=True)
        (evidence / "dependency").write_text("synthetic original input")
        result = self.run_cli("review", "--task", str(evidence), "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["entries"][0]["assessment"], "Keep")
        self.assertEqual(report["size"]["logical_bytes"], 24)

    def test_same_device_bind_mount_is_not_enumerated(self):
        from devspace.review import review_task
        from devspace.report import render_text
        (self.task / "bound").mkdir()
        (self.task / "bound/hidden").write_text("x")
        root = self.task.stat()
        def observed_mount(descriptor):
            metadata = os.fstat(descriptor)
            return 10 if (metadata.st_dev, metadata.st_ino) == (root.st_dev, root.st_ino) else 11
        with patch("devspace.review.mount_identity", side_effect=observed_mount), patch("devspace.review.os.path.ismount", return_value=False):
            report = review_task(self.task)
        self.assertEqual(report["coverage"]["skipped"], 1)
        self.assertNotIn("hidden", render_text(report))

    def test_content_never_reads_a_file_across_mount_boundaries(self):
        from devspace.review import review_task
        payload = self.task / "bound-file"
        payload.write_bytes(b"SYNTHETIC_OTHER_MOUNT_PAYLOAD")
        for observed_mount in (11, OSError(5, "mount identity unavailable")):
            with self.subTest(mount=observed_mount):
                with patch("devspace.review.mount_identity", side_effect=(10, observed_mount)), \
                        patch("devspace.review.local_filesystem", return_value=True), \
                        patch("devspace.review.os.read", wraps=os.read) as read:
                    report = review_task(self.task, inspect_content=True)
                read.assert_not_called()
                self.assertEqual(report["entries"][0]["assessment"], "Unavailable")
                self.assertFalse(report["content"]["complete"])
                self.assertEqual(report["content"]["read_bytes"], 0)
                self.assertNotIn("sha256", report["entries"][0])
                self.assertEqual(payload.read_bytes(), b"SYNTHETIC_OTHER_MOUNT_PAYLOAD")

    def test_mount_boundary_stays_report_only(self):
        from devspace.review import review_task
        from devspace.report import render_text
        mounted = self.task / "mounted"
        mounted.mkdir()
        (mounted / "outside-mount-name").write_text("x")
        with patch("devspace.review.os.path.ismount", side_effect=lambda path: Path(path) == mounted):
            report = review_task(self.task)
        self.assertEqual(report["coverage"]["skipped"], 1)
        self.assertNotIn("outside-mount-name", render_text(report))
        self.assertIn("mount", report["entries"][0]["reason"])

    def test_cancel_and_timeout_preserve_partial_output(self):
        from devspace.review import review_task
        from devspace.report import render_text
        (self.task / "file").write_text("unchanged")
        report = review_task(self.task, cancelled=lambda: True)
        self.assertTrue(report["cancelled"])
        self.assertFalse(report["coverage"]["complete"])
        self.assertIn("cancelled", render_text(report))
        report = review_task(self.task, timeout=0.000000001)
        self.assertFalse(report["coverage"]["complete"])
        self.assertIn("time limit", render_text(report))
        self.assertEqual((self.task / "file").read_text(), "unchanged")

    @unittest.skipUnless(os.name == "posix", "SIGINT subprocess fixture requires POSIX")
    def test_sigint_mid_scan_prints_partial_report_and_returns_130(self):
        for number in range(3):
            (self.task / str(number)).write_text("unchanged")
        wrapper = """
import importlib.util, os, signal, sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
spec = importlib.util.spec_from_file_location("cli", sys.argv[1] + "/devspace.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
original = os.scandir
class InterruptedEntries:
    def __init__(self, descriptor):
        self.entries = original(descriptor)
    def __enter__(self):
        return self
    def __exit__(self, *ignored):
        self.entries.close()
    def __iter__(self):
        yield next(self.entries)
        os.kill(os.getpid(), signal.SIGINT)
sys.argv = ["devspace.py", "review", "--task", sys.argv[2], "--json"]
with patch("devspace.review.descriptor_traversal_available", return_value=True), patch("devspace.review.os.scandir", InterruptedEntries):
    raise SystemExit(cli.main())
"""
        result = subprocess.run([sys.executable, "-B", "-c", wrapper, str(CLI.parent), str(self.task)],
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 130, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["cancelled"])
        self.assertEqual(report["coverage"]["examined"], 1)
        self.assertEqual(report["size"]["logical_bytes"], 9)
        self.assertEqual([p.read_text() for p in self.task.iterdir()], ["unchanged"] * 3)

    def test_unsupported_traversal_is_unavailable_not_zero(self):
        from devspace.review import review_task
        from devspace.report import render_text
        (self.task / "not-inspected").write_text("x")
        with patch("devspace.review.descriptor_traversal_available", return_value=False):
            report = review_task(self.task)
        self.assertEqual(report["coverage"]["inaccessible"], 1)
        self.assertFalse(report["size"]["complete"])
        self.assertNotIn("not-inspected", render_text(report))

    def test_low_space_thresholds_and_unknown_space_in_actual_output(self):
        from devspace.review import review_task
        from devspace.report import render_text
        for free, expected in ((10, None), (9, "below 10%"), (5, "below 10%"), (4, "CRITICAL")):
            with self.subTest(free=free), patch("devspace.review.shutil.disk_usage", return_value=(100, 100-free, free)):
                report = review_task(self.task)
            if expected:
                self.assertIn(expected, render_text(report))
            else:
                self.assertEqual(report["warnings"], [])
        with patch("devspace.review.shutil.disk_usage", side_effect=PermissionError):
            report = review_task(self.task)
        self.assertIsNone(report["filesystem"]["free_percent"])
        self.assertIn("unknown", render_text(report))


if __name__ == "__main__":
    unittest.main()
