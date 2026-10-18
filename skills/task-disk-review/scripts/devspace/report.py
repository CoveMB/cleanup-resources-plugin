"""Shared report boundary for task review and future review callers."""
import json
import ctypes
import hashlib
import os
import platform
import socket
import sys


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
    if "plan" in report:
        lines.append("Frozen plan digest: " + report["plan"]["digest"] + "; review data, not authorization")
    lines.extend("Limit: " + limitation for limitation in report["limitations"])
    return "\n".join(lines)
