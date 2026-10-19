"""Advisory reporting on isolated sparse fixtures; no installed environments."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills/task-disk-review/scripts/devspace.py"
sys.path.insert(0, str(CLI.parent))
from devspace.plans import review_scope
from devspace.report import render_text


class EvidenceGuidance(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="capture-guidance-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.task = self.base / "selected"
        self.packet = self.task / "evidence"
        self.packet.mkdir(parents=True)
        self.failure = self.packet / "original-failure.txt"
        self.failure.write_bytes(b"first attempt failed\n")

    def cli(self, *arguments):
        return subprocess.run([sys.executable, "-B", str(CLI), "review", *arguments],
                              capture_output=True, text=True, timeout=15)

    def sparse_packet(self, size):
        with (self.packet / "result.bin").open("wb") as stream:
            stream.truncate(size - self.failure.stat().st_size)

    def test_strict_default_boundaries_use_logical_not_allocated_bytes(self):
        for size, level in ((250*2**20-1, "none"), (250*2**20, "none"),
                            (250*2**20+1, "warning"), (2**30-1, "warning"),
                            (2**30, "warning"), (2**30+1, "explanation")):
            with self.subTest(size=size):
                self.sparse_packet(size)
                result = self.cli("--task", str(self.task), "--json")
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                packet = report.get("evidence_capture", {}).get("packets", [{}])[0]
                self.assertEqual(packet.get("level"), level)
                self.assertEqual(packet["logical_bytes"], size)
                self.assertEqual(packet["allocated_bytes"], report["size"]["allocated_bytes"])
                self.assertTrue(packet["complete"])
                text = render_text(report)
                if level == "explanation":
                    self.assertIn("explain", text.lower())
                self.assertNotIn("Eligible", {row["assessment"] for row in report["candidates"]})
                self.assertEqual(self.failure.read_bytes(), b"first attempt failed\n")

    def test_hardlinks_and_nested_packets_do_not_duplicate_packet_size(self):
        nested = self.packet / "review-evidence"
        nested.mkdir()
        os.link(self.failure, nested / "copy.txt")
        report = review_scope(self.task)
        packets = report.get("evidence_capture", {}).get("packets", [])
        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0]["logical_bytes"], self.failure.stat().st_size)
        self.assertEqual(report["size"]["unique_files"], 1)

    def test_partial_packet_is_unknown_not_zero_or_below_budget(self):
        report = review_scope(self.task, max_depth=1)
        packets = report.get("evidence_capture", {}).get("packets", [])
        self.assertEqual(len(packets), 1)
        self.assertIsNone(packets[0]["logical_bytes"])
        self.assertIsNone(packets[0]["allocated_bytes"])
        self.assertEqual(packets[0]["known_logical_bytes"], 0)
        self.assertFalse(packets[0]["complete"])
        self.assertEqual(packets[0]["level"], "unknown")
        self.assertIn("unknown", render_text(report))
        self.sparse_packet(2**30+1)
        (self.packet / "nested").mkdir()
        partial = review_scope(self.task, max_depth=2)
        packet = partial["evidence_capture"]["packets"][0]
        self.assertEqual(packet["level"], "explanation")
        self.assertIsNone(packet["logical_bytes"])
        self.assertEqual(packet["known_logical_bytes"], 2**30+1)

    def test_environment_hints_and_direct_evidence_selection_preserve_keep(self):
        for name in ("node_modules/lib", ".venv", "venv"):
            (self.packet / name).mkdir(parents=True)
        (self.packet / ".venv/pyvenv.cfg").write_text("synthetic version only")
        for selected in (self.task, self.packet, self.packet / ".venv"):
            with self.subTest(selected=selected):
                result = self.cli("--task", str(selected), "--json")
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                packet = report.get("evidence_capture", {}).get("packets", [{}])[0]
                self.assertTrue(packet.get("environment_hints"))
                self.assertIn("possible nested installed environment", render_text(report).lower())
                self.assertTrue(all(row["assessment"] == "Keep" for row in report["entries"]))
        ordinary = self.base / "ordinary"
        (ordinary / "node_modules").mkdir(parents=True)
        self.assertEqual(review_scope(ordinary)["evidence_capture"]["packets"], [])

    def test_adjustable_thresholds_change_advice_only_and_validate_order(self):
        default = review_scope(self.task)
        result = self.cli("--task", str(self.task), "--json", "--evidence-warn-bytes", "1", "--evidence-explain-bytes", "2")
        self.assertEqual(result.returncode, 0, result.stderr)
        changed = json.loads(result.stdout)
        self.assertEqual(changed.get("evidence_capture", {}).get("packets", [{}])[0].get("level"), "explanation")
        self.assertEqual(default["candidates"], changed["candidates"])
        self.assertEqual(default["plan"], changed["plan"])
        for warning, explanation in (("0", "2"), ("3", "2"), ("x", "4")):
            invalid = self.cli("--task", str(self.task), "--evidence-warn-bytes", warning, "--evidence-explain-bytes", explanation)
            self.assertNotEqual(invalid.returncode, 0)
        self.assertEqual(self.failure.read_bytes(), b"first attempt failed\n")

    def test_task_project_global_display_same_optional_instruction(self):
        config = self.base / "config.json"
        config.write_text(json.dumps({"schema_version": 1, "roots": [str(self.task)]}))
        for arguments in (("--task", str(self.task)), ("--project", str(self.task)), ("--global", "--config", str(config))):
            result = self.cli(*arguments, "--json")
            self.assertIn(result.returncode, (0, 2), result.stderr)
            report = json.loads(result.stdout)
            capture = report.get("evidence_capture", {})
            self.assertEqual(len(capture.get("packets", [])), 1)
            instruction = capture["optional_instruction"]
            for requirement in ("Optional", "incremental planning", "working directory", "original failure/output",
                                "attempts", "screenshots", "source changes", "necessary inputs", "purpose", "commit",
                                "local changes", "versions/platform", "sanitized invocation", "results", "references",
                                "checksums", "retention", "unavailable", "modified dependencies", "unique inputs",
                                "failure-specific state", "review date", "deletion deadline"):
                self.assertIn(requirement, instruction)
            text = self.cli(*arguments)
            self.assertIn(instruction, text.stdout)
            self.assertEqual(text.returncode, result.returncode)
            self.assertIn("advisory", text.stdout.lower())

    def test_excluded_evidence_is_not_traversed_or_reported_as_zero_packet(self):
        report = review_scope(self.task, exclusions=[self.packet])
        self.assertEqual(report.get("evidence_capture", {}).get("packets"), [])
        self.assertFalse(report["coverage"]["complete"])
        self.assertEqual(self.failure.read_bytes(), b"first attempt failed\n")


if __name__ == "__main__":
    unittest.main()
