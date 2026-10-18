"""Bounded metadata traversal; never opens a regular file or follows a link."""
import errno
import os
from pathlib import Path
import shutil
import stat
import sys
import time

from .report import new_report, record_space


PRIVATE_DIRECTORIES = {".git", ".aws", ".ssh", ".wrangler", "databases"}
PRIVATE_FILES = {".netrc", ".npmrc", ".pypirc", "credentials", ".bash_history", ".zsh_history"}


def protection(name, inherited=False):
    lower = name.lower()
    if lower in PRIVATE_DIRECTORIES:
        return "protected state; descendants not enumerated", True
    if lower == ".env" or lower.startswith(".env.") or lower in PRIVATE_FILES:
        return "protected credentials or application history", True
    if lower.endswith((".db", ".sqlite", ".sqlite3", ".mdb", ".db-wal", ".db-shm", ".sqlite-wal", ".sqlite-shm")):
        return "protected database/state", True
    if inherited or any(word in lower for word in ("evidence", "failure", "snapshot")) or lower in {"logs", "log"}:
        return "protected evidence/original failure; retention unverified", False
    return None, False


def descriptor_traversal_available():
    return (sys.platform in {"darwin", "linux"} and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY")
            and os.open in os.supports_dir_fd and os.scandir in os.supports_fd)


def mount_identity(descriptor):
    if sys.platform == "linux":
        # Kernel descriptor metadata, not selected file contents. st_dev alone misses bind mounts.
        with open(f"/proc/self/fdinfo/{descriptor}", encoding="ascii") as stream:
            fields = stream.read(4096).splitlines()
        for field in fields:
            if field.startswith("mnt_id:"):
                return int(field.split()[1])
        raise OSError(errno.ENOTSUP, "mount identity unavailable")
    return os.fstat(descriptor).st_dev


def review_task(selected, *, max_entries=2000, max_depth=12, timeout=10.0, cancelled=None):
    selected = os.path.abspath(os.fspath(selected))
    report = new_report(selected, None, {"max_entries": max_entries, "max_depth": max_depth, "timeout_seconds": timeout})
    coverage, size = report["coverage"], report["size"]
    seen_files = set()
    started = time.monotonic()
    stopped = False

    def partial():
        coverage["complete"] = False
        size["complete"] = False

    def stop_if_needed():
        nonlocal stopped
        if stopped:
            return True
        if cancelled is not None and cancelled():
            report["cancelled"] = True
            coverage["stop_reason"] = "cancelled"
        elif time.monotonic() - started >= timeout:
            coverage["stop_reason"] = "time limit; remaining coverage unknown"
        else:
            return False
        stopped = True
        partial()
        return True

    def unavailable(relative, reason, row=None):
        partial()
        coverage["inaccessible"] += 1
        if row is None:
            row = {"path": relative, "kind": "unknown"}
            report["entries"].append(row)
        row.update(assessment="Unavailable", coverage="inaccessible", reason=reason)

    def skip(row, reason):
        partial()
        coverage["skipped"] += 1
        row.update(coverage="skipped", reason=reason)

    def walk(descriptor, relative, depth, inherited_keep):
        nonlocal stopped
        with os.scandir(descriptor) as entries:
            for entry in entries:
                if stop_if_needed():
                    break
                if coverage["examined"] >= max_entries:
                    coverage["stop_reason"] = "entry limit; remaining coverage unknown"
                    partial()
                    stopped = True
                    break
                path = relative / entry.name
                row = {"path": path.as_posix(), "kind": "unknown", "assessment": "Review",
                       "coverage": "examined", "reason": "contents/use/release/recovery unverified"}
                report["entries"].append(row)
                coverage["examined"] += 1
                try:
                    metadata = os.stat(entry.name, dir_fd=descriptor, follow_symlinks=False)
                except OSError as error:
                    unavailable(row["path"], "metadata unavailable: " + error_code(error), row)
                    continue
                reason, private_directory = protection(entry.name, inherited_keep)
                if reason:
                    row.update(assessment="Keep", reason=reason)
                mode = metadata.st_mode
                if stat.S_ISLNK(mode) or getattr(metadata, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                    row["kind"] = "link"
                    skip(row, "link/reparse boundary; target not inspected")
                elif stat.S_ISDIR(mode):
                    row["kind"] = "directory"
                    if metadata.st_dev != root_device or os.path.ismount(canonical / path):
                        skip(row, "mount/device boundary; descendants not inspected")
                    elif private_directory:
                        skip(row, reason)
                    elif depth >= max_depth:
                        skip(row, "depth limit; descendants unknown")
                    else:
                        child = None
                        try:
                            child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                            opened = os.fstat(child)
                            if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                                unavailable(row["path"], "directory identity changed; descendants unknown", row)
                            elif mount_identity(child) != root_mount:
                                skip(row, "mount boundary; descendants not inspected")
                            else:
                                walk(child, path, depth + 1, bool(reason))
                        except OSError as error:
                            unavailable(row["path"], "directory unavailable: " + error_code(error), row)
                        finally:
                            if child is not None:
                                os.close(child)
                elif stat.S_ISREG(mode):
                    row.update(kind="file", logical_bytes=metadata.st_size,
                               allocated_bytes=metadata.st_blocks * 512 if hasattr(metadata, "st_blocks") else None)
                    identity = (metadata.st_dev, metadata.st_ino)
                    if metadata.st_ino and identity in seen_files:
                        size["duplicate_hardlinks"] += 1
                        row["counted"] = False
                    else:
                        seen_files.add(identity)
                        row["counted"] = True
                        size["unique_files"] += 1
                        size["logical_bytes"] += metadata.st_size
                        allocated = row["allocated_bytes"]
                        if allocated is None:
                            size["allocated_bytes"] = None
                        else:
                            size["known_allocated_bytes"] += allocated
                            if size["allocated_bytes"] is not None:
                                size["allocated_bytes"] += allocated
                else:
                    row["kind"] = "special"
                    skip(row, "special filesystem entry; not opened")

    descriptor = None
    try:
        root_metadata = os.lstat(selected)
        if not stat.S_ISDIR(root_metadata.st_mode) or stat.S_ISLNK(root_metadata.st_mode):
            report["invalid_scope"] = True
            unavailable(".", "selected scope must be a real directory, not a link")
            return report
        canonical = Path(selected).resolve(strict=True)
        report["scope"]["canonical"] = str(canonical)
        try:
            record_space(report, shutil.disk_usage(canonical))
        except OSError:
            report["warnings"].append("Filesystem free space unavailable; low-space state unknown.")
        if stop_if_needed():
            return report
        reason = None
        private_directory = False
        # Preserve both selected alias and canonical ancestry: selection depth must
        # never turn protected state/evidence into ordinary unknown resources.
        for component in (*Path(selected).parts, *canonical.parts):
            reason, private_component = protection(component, bool(reason))
            private_directory = private_directory or private_component
        if private_directory:
            row = {"path": ".", "kind": "directory", "assessment": "Keep"}
            report["entries"].append(row)
            skip(row, "protected state/credentials ancestor; descendants not enumerated")
            return report
        if not descriptor_traversal_available():
            unavailable(".", "safe no-follow descriptor traversal unavailable on this runtime/platform")
            return report
        descriptor = os.open(canonical, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (root_metadata.st_dev, root_metadata.st_ino):
            unavailable(".", "selected directory identity changed; descendants unknown")
            return report
        root_device = opened.st_dev
        root_mount = mount_identity(descriptor)
        walk(descriptor, Path(), 1, bool(reason))
    except KeyboardInterrupt:
        partial()
        report["cancelled"] = True
        coverage["stop_reason"] = "cancelled"
    except OSError as error:
        report["invalid_scope"] = descriptor is None
        unavailable(".", "scope unavailable: " + error_code(error))
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return report


def error_code(error):
    # Never print exception filenames, payloads or platform-provided detail.
    return errno.errorcode.get(error.errno, "OS_ERROR")
