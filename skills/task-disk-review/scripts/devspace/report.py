"""Shared report boundary for task review and future review callers."""
import json
import ctypes
import hashlib
import os
import platform
import socket
import sys
from pathlib import Path, PurePosixPath


def host_identity():
    """Hash an OS machine identifier and root identity; no raw identifier reported."""
    try:
        if sys.platform == "darwin":
            identifier = ctypes.create_string_buffer(16)
            # gethostuuid's timespec deadline is a pair of native longs.
            deadline = (ctypes.c_long * 2)(1, 0)
            function = ctypes.CDLL(None).gethostuuid
            function.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            function.restype = ctypes.c_int
            if function(identifier, deadline) != 0:
                return None
            machine = identifier.raw
        elif sys.platform == "linux":
            with open("/etc/machine-id", "rb") as stream:
                machine = stream.read(256).strip()
            if len(machine) != 32 or any(byte not in b"0123456789abcdef" for byte in machine):
                return None
        else:
            return None
        root = os.stat("/")
        return hashlib.sha256(machine + str((root.st_dev, root.st_ino)).encode()).hexdigest()
    except (OSError, AttributeError):
        return None


def new_report(selected, canonical, limits):
    return {
        "schema_version": 1,
        "host": {"hostname": socket.gethostname(), "system": platform.system(), "identity": host_identity()},
        "scope": {"mode": "task", "selected": selected, "canonical": canonical},
        "thread_identity": None,
        "limits": limits,
        "coverage": {"examined": 0, "skipped": 0, "inaccessible": 0,
                     "complete": True, "stop_reason": None},
        "entries": [],
        "size": {"logical_bytes": 0, "allocated_bytes": 0, "known_allocated_bytes": 0,
                 "unique_files": 0, "duplicate_hardlinks": 0, "complete": True},
        "filesystem": {"total_bytes": None, "free_bytes": None, "free_percent": None},
        "warnings": [],
        "limitations": [
            "Metadata only; file contents, purpose, consumers, recovery and release are unverified. No deletion eligibility.",
            "Sizes cover unique examined regular files only; directory metadata and skipped/unknown contents are excluded.",
            "Allocated blocks are estimates, not reclaimable bytes: hard links outside scope, sparse files, clones, snapshots and concurrent writes limit attribution.",
            "Names identify some protected state/evidence, not every credential, custom database or original failure; unknown resources remain Review.",
            "Only the actual execution host and selected directory are reviewed; remote, synchronized, network and WSL storage locality is unverified and report-only.",
            "Timeout/cancellation is cooperative between filesystem calls; a blocked OS call may delay it. No snapshot or protection against unrelated concurrent writers.",
            "Reports contain host and selected/relative path metadata; inspect before sharing. No file payloads are read or recorded.",
        ],
        "cancelled": False,
        "invalid_scope": False,
    }


def record_space(report, usage):
    total, _, free = usage
    percent = 100 * free / total if total > 0 else None
    report["filesystem"] = {"total_bytes": total, "free_bytes": free, "free_percent": percent}
    if percent is not None and percent < 5:
        report["warnings"].append("CRITICAL: filesystem free space below 5%.")
    elif percent is not None and percent < 10:
        report["warnings"].append("Warning: filesystem free space below 10%.")


EVIDENCE_WARN_BYTES = 250 * 1024 * 1024
EVIDENCE_EXPLAIN_BYTES = 1024 * 1024 * 1024
OPTIONAL_CAPTURE_INSTRUCTION = (
    "Optional for development/evidence workflows, including incremental planning: run installations, builds, "
    "tests and reproductions in a separate working directory outside finalized evidence. Preserve original failure/output "
    "before retry; keep attempts distinguishable. Select useful logs, screenshots, results, relevant source changes and "
    "necessary inputs rather than installed projects wholesale. Keep a compact manifest: purpose, source commit and "
    "local changes, versions/platform, sanitized invocation, results, references, useful checksums and retention requirements. "
    "Preserve unavailable or modified dependencies, unique inputs and exact failure-specific state when reconstruction is "
    "unreliable. A review date is not a deletion deadline. Installing this skill does not enforce the convention. "
    "Legacy packets require individual assessment; preserve necessary originals and document any separately approved reductions."
)


def validate_evidence_thresholds(warning, explanation):
    if any(type(value) is not int or not 0 < value <= 2**40 for value in (warning, explanation)) or warning > explanation:
        raise ValueError("evidence thresholds require positive byte counts, warning <= explanation <= 2**40")


def record_evidence_guidance(report, snapshots, warning, explanation):
    """Describe metadata hints, never change assessment or frozen selection data."""
    packets = []
    for snapshot in snapshots:
        groups = {}
        for relative in snapshot.get("evidence_roots", []):
            root = PurePosixPath(relative)
            groups[root] = {"path": str(Path(snapshot["scope"]["canonical"]) / relative),
                            "complete": snapshot["size"]["complete"], "known_logical_bytes": 0,
                            "known_allocated_bytes": 0, "allocation_known": True,
                            "environment_hints": [], "seen": set()}
            if Path(groups[root]["path"]).name.lower() in {"node_modules", ".venv", "venv"}:
                groups[root]["environment_hints"].append(".")
        for entry in snapshot["entries"]:
            path = PurePosixPath(entry["path"])
            root = next((ancestor for ancestor in (path, *path.parents) if ancestor in groups), None)
            if root is None:
                continue
            packet = groups[root]
            if (entry["kind"] == "directory" and path.name.lower() in {"node_modules", ".venv", "venv"}
                    or entry["kind"] == "file" and path.name.lower() == "pyvenv.cfg"):
                packet["environment_hints"].append(entry["path"])
            if entry["kind"] != "file":
                continue
            identity = tuple(entry["accounting_identity"])
            if identity in packet["seen"]:
                continue
            packet["seen"].add(identity)
            packet["known_logical_bytes"] += entry["logical_bytes"]
            if entry["allocated_bytes"] is None:
                packet["allocation_known"] = False
            else:
                packet["known_allocated_bytes"] += entry["allocated_bytes"]
        for packet in groups.values():
            packet.pop("seen")
            allocation_known = packet.pop("allocation_known")
            packet["logical_bytes"] = packet["known_logical_bytes"] if packet["complete"] else None
            packet["allocated_bytes"] = packet["known_allocated_bytes"] if packet["complete"] and allocation_known else None
            known = packet["known_logical_bytes"]
            packet["level"] = ("explanation" if known > explanation else "warning" if known > warning
                               else "none" if packet["complete"] else "unknown")
            label = json.dumps(packet["path"], ensure_ascii=True)
            if packet["level"] in {"warning", "explanation"}:
                message = f"Evidence advisory: {label}: {known} examined logical bytes"
                if not packet["complete"]:
                    message += " (lower bound; full size unknown)"
                message += "; " + ("explain retained size using known purpose/context where possible."
                                   if packet["level"] == "explanation" else "oversized packet.")
                report["warnings"].append(message)
            if packet["environment_hints"]:
                report["warnings"].append(f"Evidence advisory: {label}: possible nested installed environment from name hints; individually assess, never infer disposability.")
            packets.append(packet)
    report["evidence_capture"] = {"warning_bytes": warning, "explanation_bytes": explanation, "packets": packets,
                                  "optional_instruction": OPTIONAL_CAPTURE_INSTRUCTION}


def render_text(report):
    quote = lambda value: json.dumps(value, ensure_ascii=True)
    coverage = report["coverage"]
    size = report["size"]
    lines = ["Read-only " + report["scope"]["mode"] + " review", "Host: " + quote(report["host"]),
             "Selected: " + quote(report["scope"]["selected"]),
             "Canonical scope: " + quote(report["scope"]["canonical"]), "Thread: unknown",
             f"Examined: {coverage['examined']} metadata entries; Skipped: {coverage['skipped']}; Inaccessible: {coverage['inaccessible']}",
             "Coverage: " + ("complete metadata traversal" if coverage["complete"] else "partial; unexamined usage unknown"),
             f"Logical examined bytes: {size['logical_bytes']}; Allocated examined bytes: {size['allocated_bytes'] if size['allocated_bytes'] is not None else 'unknown'}",
             f"Unique files: {size['unique_files']}; duplicate hard links: {size['duplicate_hardlinks']}",
             "Filesystem free percent: " + (f"{report['filesystem']['free_percent']:.2f}%" if report['filesystem']['free_percent'] is not None else "unknown")]
    if "content" in report:
        lines.append(f"Assessed target bytes read: {report['content']['read_bytes']}; payloads are not recorded")
    if coverage["stop_reason"]:
        lines.append("Stopped: " + coverage["stop_reason"])
    lines.extend(report["warnings"])
    for entry in report["entries"]:
        lines.append(f"{entry['assessment']} | {quote(entry['path'])} | {entry['coverage']} | {entry['reason']}")
    for row in report.get("candidates", []):
        lines.append(f"{row['assessment']} | ID {row['id']} | {quote(row['path'])} | {row['reason']}")
        if "provider_size_bytes_estimate" in row.get("observation", {}):
            lines.append(f"Provider estimate: {row['observation']['provider_size_bytes_estimate']} bytes; host recovery unknown")
        if row.get("assessment_basis"):
            lines.append("Assessment basis: " + row["assessment_basis"])
        if row.get("comparison"):
            lines.append("Content comparison: " + quote(row["comparison"]))
        lines.append("Effect: " + row["effect"])
    if "git" in report:
        for row in report["git"]["worktrees"]:
            lines.append("Report-only worktree: " + quote(row))
        lines.extend("Git limit: " + item for item in report["git"]["limitations"])
    for location in report.get("locations", []):
        lines.append("Coverage: " + quote(location))
    for inventory in report.get("git_inventories", []):
        lines.append("Report-only Git inventory: " + quote(inventory))
    if "retention" in report:
        lines.append("Independent Codex retention: " + quote(report["retention"]))
    capture = report.get("evidence_capture", {})
    if capture.get("packets"):
        lines.append("Evidence capture advisory; logical thresholds only, never release/eligibility rules. Sizes are per packet, not additive host totals.")
        lines.extend("Evidence packet: " + quote(packet) for packet in capture["packets"])
        lines.append(capture["optional_instruction"])
    if "plan" in report:
        lines.append("Frozen plan digest: " + report["plan"]["digest"] + "; review data, not authorization")
    lines.extend("Limit: " + limitation for limitation in report["limitations"])
    return "\n".join(lines)
