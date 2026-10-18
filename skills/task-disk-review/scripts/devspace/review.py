"""Bounded no-follow traversal; content reads require an explicit assessment."""
import errno
import ctypes
import hashlib
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


def same_path(first, second):
    if first == second:
        return True
    try:
        return first.samefile(second)
    except OSError:
        return False


def path_inside(path, root):
    if path == root or root in path.parents:
        return True
    # realpath does not normalize case aliases on case-insensitive POSIX filesystems.
    # Retention, containment and overlap must also recognize the actual directory.
    try:
        identity = root.stat()
    except OSError:
        return False
    for ancestor in (path, *path.parents):
        try:
            observed = ancestor.stat()
            if (identity.st_dev, identity.st_ino) == (observed.st_dev, observed.st_ino):
                return True
        except OSError:
            continue
    return False



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


def file_identity(metadata):
    return {"device": metadata.st_dev, "inode": metadata.st_ino, "mode": metadata.st_mode,
            "size": metadata.st_size, "mtime_ns": metadata.st_mtime_ns, "ctime_ns": metadata.st_ctime_ns}


def darwin_filesystem(descriptor):
    """Kernel flags/type for an open Darwin descriptor, shared by read/apply gates."""
    library = ctypes.CDLL(None)
    function = getattr(library, "fstatfs64", None) or getattr(library, "fstatfs$INODE64", None) or library.fstatfs
    function.argtypes = [ctypes.c_int, ctypes.c_void_p]
    function.restype = ctypes.c_int
    buffer = ctypes.create_string_buffer(4096)
    if function(descriptor, buffer) != 0:
        raise OSError(errno.ENOTSUP, "filesystem capability unavailable")
    # Darwin statfs64 prefix, verified against SDK sys/mount.h.
    return ctypes.c_uint32.from_buffer(buffer, 64).value, buffer.raw[72:88].split(b"\0", 1)[0]


def local_filesystem(descriptor):
    """Selected descriptor's kernel mount fact, never a sync/activity certificate."""
    try:
        if sys.platform == "linux":
            identifier = str(mount_identity(descriptor))
            with open("/proc/self/mountinfo", encoding="utf-8") as stream:
                for line in stream:
                    fields = line.split()
                    if fields[0] == identifier:
                        return fields[fields.index("-") + 1] in {"ext2", "ext3", "ext4", "xfs", "btrfs", "tmpfs", "overlay", "zfs"}
            return False
        if sys.platform == "darwin":
            flags, name = darwin_filesystem(descriptor)
            return bool(flags & 0x1000) and name in {b"apfs", b"hfs"}
    except (OSError, AttributeError, ValueError, IndexError):
        pass
    return False


def review_task(selected, *, max_entries=2000, max_depth=12, timeout=10.0, cancelled=None,
                inspect_content=False, max_content_bytes=256 * 1024 * 1024, exclusions=()):
    selected = os.path.abspath(os.fspath(selected))
    report = new_report(selected, None, {"max_entries": max_entries, "max_depth": max_depth, "timeout_seconds": timeout})
    coverage, size = report["coverage"], report["size"]
    report["evidence_roots"] = []
    seen_files = set()
    started = time.monotonic()
    stopped = False
    excluded = [Path(os.path.abspath(value)) for value in exclusions]
    content_bytes = 0
    if inspect_content:
        report["content"] = {"complete": False, "read_bytes": 0}
        report["limitations"][0] = "Explicit candidate content reads/hash comparisons do not establish semantic value, rebuildability or current use."
        report["limitations"][-1] = "Reports contain metadata/digests, never file payloads; inspect before sharing."

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
        nonlocal stopped, content_bytes
        directory_before = file_identity(os.fstat(descriptor))
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
                full_path = canonical / path
                if any(full_path == root or root in full_path.parents for root in excluded):
                    row.update(assessment="Keep")
                    skip(row, "excluded; contents not enumerated")
                    continue
                try:
                    metadata = os.stat(entry.name, dir_fd=descriptor, follow_symlinks=False)
                except OSError as error:
                    unavailable(row["path"], "metadata unavailable: " + error_code(error), row)
                    continue
                # Physical aliases must also exclude contents; never dereference
                # a link entry to establish that match.
                if not stat.S_ISLNK(metadata.st_mode) and any(path_inside(full_path, root) for root in excluded):
                    row.update(assessment="Keep")
                    skip(row, "excluded filesystem alias; contents not enumerated")
                    continue
                reason, private_directory = protection(entry.name, inherited_keep)
                if reason:
                    row.update(assessment="Keep", reason=reason)
                mode = metadata.st_mode
                if inspect_content:
                    row["mode"] = stat.S_IMODE(mode)
                    row["identity"] = file_identity(metadata)
                if stat.S_ISLNK(mode) or getattr(metadata, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                    row["kind"] = "link"
                    skip(row, "link/reparse boundary; target not inspected")
                elif stat.S_ISDIR(mode):
                    row["kind"] = "directory"
                    if reason and not private_directory and not inherited_keep:
                        report["evidence_roots"].append(row["path"])
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
                            if ((opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)
                                    or inspect_content and file_identity(opened) != file_identity(metadata)):
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
                    row["accounting_identity"] = list(identity)
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
                    if inspect_content:
                        if reason:
                            skip(row, reason)
                            continue
                        file_descriptor = None
                        try:
                            file_descriptor = os.open(entry.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                                      dir_fd=descriptor)
                            before = os.fstat(file_descriptor)
                            if not stat.S_ISREG(before.st_mode) or file_identity(before) != file_identity(metadata):
                                unavailable(row["path"], "file identity changed before inspection", row)
                                continue
                            if mount_identity(file_descriptor) != root_mount:
                                unavailable(row["path"], "file mount boundary; contents not inspected", row)
                                continue
                            digest = hashlib.sha256()
                            while not stop_if_needed():
                                chunk = os.read(file_descriptor, min(65536, max_content_bytes - content_bytes + 1))
                                if not chunk:
                                    break
                                content_bytes += len(chunk)
                                if content_bytes > max_content_bytes:
                                    stopped = True
                                    partial()
                                    coverage["stop_reason"] = "content byte limit; remaining contents unknown"
                                    break
                                digest.update(chunk)
                            if not stopped and file_identity(os.fstat(file_descriptor)) == file_identity(before):
                                row["sha256"] = digest.hexdigest()
                            else:
                                unavailable(row["path"], "incomplete or changed file contents", row)
                        except OSError as error:
                            unavailable(row["path"], "content unavailable: " + error_code(error), row)
                        finally:
                            if file_descriptor is not None:
                                os.close(file_descriptor)
                else:
                    row["kind"] = "special"
                    skip(row, "special filesystem entry; not opened")
        if inspect_content and file_identity(os.fstat(descriptor)) != directory_before:
            unavailable(relative.as_posix() or ".", "directory changed during content inspection")

    descriptor = None
    try:
        root_metadata = os.lstat(selected)
        if not stat.S_ISDIR(root_metadata.st_mode) or stat.S_ISLNK(root_metadata.st_mode):
            report["invalid_scope"] = True
            unavailable(".", "selected scope must be a real directory, not a link")
            return report
        canonical = Path(selected).resolve(strict=True)
        report["scope"]["canonical"] = str(canonical)
        if any(path_inside(canonical, root) for root in excluded):
            report["entries"].append({"path": ".", "kind": "directory", "assessment": "Keep", "coverage": "skipped", "reason": "excluded scope"})
            partial()
            coverage["skipped"] += 1
            return report
        if inspect_content and str(canonical) != selected:
            unavailable(".", "linked ancestor in assessment path; contents not inspected")
            return report
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
        if reason:
            report["evidence_roots"].append(".")
        if inspect_content:
            # An individually assessed nested output may escape generic evidence
            # retention, but never state ancestry or its own protected name.
            reason, _ = protection(canonical.name)
            report["root_protection"] = reason
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
        report["filesystem_local"] = local_filesystem(descriptor) and not any(
            part.lower() in {"cloudstorage", "mobile documents", "onedrive", "dropbox"} for part in canonical.parts)
        if inspect_content:
            report["identity"] = file_identity(opened)
            if not report["filesystem_local"]:
                unavailable(".", "nonlocal/synchronized/unsupported filesystem boundary; contents not read")
                return report
        walk(descriptor, Path(), 1, bool(reason))
        if inspect_content:
            report["content"] = {"complete": coverage["complete"], "read_bytes": content_bytes}
    except KeyboardInterrupt:
        partial()
        report["cancelled"] = True
        coverage["stop_reason"] = "cancelled"
    except OSError as error:
        report["invalid_scope"] = descriptor is None
        unavailable(".", "scope unavailable: " + error_code(error))
    finally:
        if inspect_content:
            report["content"] = {"complete": coverage["complete"] and "identity" in report, "read_bytes": content_bytes}
        if descriptor is not None:
            os.close(descriptor)
    return report


def error_code(error):
    # Never print exception filenames, payloads or platform-provided detail.
    return errno.errorcode.get(error.errno, "OS_ERROR")
