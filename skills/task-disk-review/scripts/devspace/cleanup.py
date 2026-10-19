"""One guarded local transaction; terminal interaction is not human authentication.

Descriptor checks reduce substitution risk, but cannot make check/unlink atomic
against unrelated processes with this account's privileges. No shell fallback.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
import uuid

from . import plans
from . import review
from .docker_cleanup import is_docker
from .npm_cache import is_npm_cache
from .review import (descriptor_traversal_available, file_identity, local_filesystem,
                     mount_identity, review_task)


OPERATION = "permanent-exact-directory-removal"
WARNINGS = ["Permanent removal; only previously established rebuild or accepted loss applies; no undo or backup.",
            "Lock controls cooperating helpers in this account, not unrelated writers; check/unlink is not atomic.",
            "Free-space change is a net filesystem observation, not exact item attribution; snapshots, hardlinks and other activity affect recovery."]
PLAN_FIELDS = {"schema_version", "kind", "host", "scope_roots", "candidates", "assessment_digest",
               "manifest_digest", "policy", "digest", "review_context", "scope_identities"}


def _capabilities():
    if (sys.platform != "darwin" or not descriptor_traversal_available()
            or any(function not in os.supports_dir_fd for function in (os.stat, os.unlink, os.rmdir))
            or os.stat not in os.supports_follow_symlinks or os.access not in os.supports_dir_fd
            or os.access not in os.supports_effective_ids or os.access not in os.supports_follow_symlinks
            or os.listdir not in os.supports_fd):
        raise ValueError("mutation unsupported: requires tested macOS descriptor/local-filesystem/durability capabilities")
    import fcntl
    if not hasattr(fcntl, "flock"):
        raise ValueError("helper lock capability unavailable")


def _state_path():
    import pwd
    # HOME overrides must not create alternate cooperating-helper lock domains.
    return Path(pwd.getpwuid(os.getuid()).pw_dir) / "Library/Application Support/cleanup-resources-plugin"


def _stable(metadata):
    return {key: file_identity(metadata)[key] for key in ("device", "inode", "mode")}


def _sync_file(descriptor):
    import fcntl
    os.fsync(descriptor)
    # macOS fsync alone need not flush drive caches. Refusal disables mutation.
    fcntl.fcntl(descriptor, 51)  # F_FULLFSYNC, Darwin SDK sys/fcntl.h


def _supported_filesystem(descriptor):
    # HFS can be reviewed but is not certified by APFS fixture evidence.
    flags, name = review.darwin_filesystem(descriptor)
    if not flags & 0x1000 or name != b"apfs" or not local_filesystem(descriptor):
        raise ValueError("mutation filesystem unsupported; tested local APFS required")


class State:
    """Private fixed-location receipts and one advisory account-local host lock."""
    def __init__(self, targets):
        self.path = _state_path()
        self.directory = None
        self.lock = None
        if any(plans._overlap(self.path, Path(path)) for path in targets):
            raise ValueError("state location overlaps protected selection")

    def __enter__(self):
        import fcntl
        parent = plans._open_parent(self.path)
        try:
            try:
                os.mkdir(self.path.name, mode=0o700, dir_fd=parent)
                os.fsync(parent)
            except FileExistsError:
                pass
            self.directory = os.open(self.path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        finally:
            os.close(parent)
        try:
            metadata = os.fstat(self.directory)
            if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
                raise ValueError("private local state directory ownership/mode/capability refused")
            _supported_filesystem(self.directory)
            self.lock = os.open("helper.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=self.directory)
            metadata = os.fstat(self.lock)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                    or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1):
                raise ValueError("unsafe helper lock")
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.fsync(self.directory)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *unused):
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None
        if self.directory is not None:
            os.close(self.directory)
            self.directory = None

    def verify(self):
        metadata = os.fstat(self.directory)
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise ValueError("private state permissions changed")
        parent = plans._open_parent(self.path)
        try:
            if _stable(os.stat(self.path.name, dir_fd=parent, follow_symlinks=False)) != _stable(os.fstat(self.directory)):
                raise ValueError("state path identity changed")
            if file_identity(os.stat("helper.lock", dir_fd=self.directory, follow_symlinks=False)) != file_identity(os.fstat(self.lock)):
                raise ValueError("helper lock substituted")
        finally:
            os.close(parent)

    def read(self, name):
        self.verify()
        try:
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.directory)
        except FileNotFoundError:
            return None
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                    or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1 or metadata.st_size > 65536):
                raise ValueError("unsafe state record")
            data = stream.read(65537)
            if len(data) > 65536 or file_identity(metadata) != file_identity(os.fstat(stream.fileno())):
                raise ValueError("state changed or exceeded bounds")
            return json.loads(data, object_pairs_hook=plans._unique_keys)

    def write(self, name, value):
        self.verify()
        data = plans.canonical_json(value) + b"\n"
        if len(data) > 65536:
            raise ValueError("compact state record limit exceeded")
        descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.directory)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(self.directory)
            _sync_file(stream.fileno())

    def clear_pending(self):
        self.verify()
        os.unlink("pending.json", dir_fd=self.directory)
        os.fsync(self.directory)
        _sync_file(self.lock)


def _load_plan(path, selected_ids, all_eligible=False):
    plan = plans.read_document(path, versions=(1, 2, 3, 4))
    if set(plan) != PLAN_FIELDS or set(plan["review_context"]) != {"mode", "selected"}:
        raise ValueError("unsupported frozen plan; regenerate review with this helper")
    if all_eligible:
        if selected_ids:
            raise ValueError("selection modes are mutually exclusive")
        selected_ids = [row["id"] for row in plan["candidates"] if row["assessment"] == "Eligible"]
    selected = plans.validate_selection(plan, selected_ids)
    for row in selected:
        if is_docker(row) or is_npm_cache(row):
            continue
        target = Path(row["path"])
        native = plan["schema_version"] in (2, 3, 4) and row.get("operation") == "git-worktree-remove"
        if (any(plans._inside(Path(root), target) and not (native and plans._same_path(Path(root), target))
                for root in plan["scope_roots"])
                or any(plans._overlap(target, Path(root)) for root in (*plan["policy"]["holds"], *plan["policy"]["exclusions"]))):
            raise ValueError("protected root/ancestor or policy overlap")
    return plan, selected


def _confirm(plan, selected):
    if not sys.stdin.isatty():
        raise ValueError("use your own interactive terminal; piped input refused")
    binding = {"plan_digest": plan["digest"], "host": plan["host"],
               "targets": [{key: row[key] for key in ("id", "path", "effect", "preconditions", "observation")} for row in selected]}
    if plan["schema_version"] in (2, 3, 4):
        for displayed, row in zip(binding["targets"], selected):
            displayed["operation"] = row["operation"]
            if row["operation"] == "git-worktree-remove":
                displayed["native"] = {key: row["native"][key] for key in
                                       ("repository", "common_directory", "head", "retained_ref")}
            elif is_npm_cache(row):
                displayed["native"] = {key: row["native"][key] for key in ("resource", "cache_identity", "store_identity")}
                displayed["native"]["tools"] = {key: row["native"]["tools"][key] for key in ("node", "npm", "versions", "configuration")}
            elif is_docker(row):
                # Full plan/observation digests bind preserved inventories;
                # the terminal shows selected resource/provider facts only.
                displayed["native"] = {key: value for key, value in row["native"].items()
                                       if key not in {"cache_records", "image_ids"}}
    response = "REMOVE " + plans.digest(binding)
    # RTK can capture stdout/stderr. Display directly on the controlling terminal.
    with open("/dev/tty", "w", encoding="utf-8", buffering=1) as terminal:
        if not terminal.isatty():
            raise ValueError("controlling terminal unavailable")
        terminal.write("Permanent selected-resource cleanup. Inspect the complete binding below.\n")
        terminal.write(json.dumps(binding, ensure_ascii=True, indent=2) + "\n")
        terminal.write(json.dumps({"policy": plan["policy"], "warnings": _warnings(plan)}, ensure_ascii=True, indent=2) + "\n")
        terminal.write("Type exactly " + response + " or type CANCEL:\n")
        answer = sys.stdin.readline(256).rstrip("\r\n")
    return answer == response


def _revalidate(plan, selected, assessment_path, manifest_path, config_path, completed=()):
    for row in completed:
        if is_npm_cache(row):
            from .npm_cache import observe
            if observe(row) != "absent-cache-entry-and-content":
                raise ValueError("completed cache resource changed; remaining actions stopped")
        if is_docker(row):
            from .docker_cleanup import observe
            if observe(row) != "absent-provider-resource":
                raise ValueError("completed Docker resource/provider changed; remaining actions stopped")
        if row.get("operation") == "git-worktree-remove":
            from .git_worktree import observe
            if observe(row) != "absent-and-unregistered-branch-retained":
                raise ValueError("completed worktree recovery/registration changed; remaining actions stopped")
    assessment = plans.read_document(assessment_path, versions=(1, 2, 3, 4))
    manifest = plans.read_document(manifest_path) if manifest_path else None
    if plans.digest(assessment) != plan["assessment_digest"] or plans.digest(manifest) != plan["manifest_digest"]:
        raise ValueError("original assessment/consumer/retention inputs changed")
    context = plan["review_context"]
    selected_scope = context["selected"]
    limits = plan["policy"]["limits"]
    if context["mode"] == "global":
        if not config_path:
            raise ValueError("original global configuration required")
        selected_scope = plans.read_document(config_path)
        if plans.digest(selected_scope) != limits["global_config_digest"]:
            raise ValueError("global configuration changed")
        if selected_scope.get("host_identity", plan["host"]["identity"]) != plan["host"]["identity"]:
            raise ValueError("configured execution host differs")
    elif config_path or context["mode"] not in {"task", "project"}:
        raise ValueError("unsupported review context")
    review_assessment = assessment
    if plan["schema_version"] in (3, 4):
        review_assessment = {**assessment, "candidates": [row for row in assessment["candidates"] if not is_docker(row) and not is_npm_cache(row)]}
    report = plans.review_scope(selected_scope, mode=context["mode"], assessment=review_assessment, manifest=manifest,
                                holds=plan["policy"]["holds"], exclusions=plan["policy"]["exclusions"],
                                max_entries=limits["max_entries"], max_depth=limits["max_depth"],
                                timeout=limits["timeout_seconds"], max_content_bytes=limits["max_content_bytes"])
    if report["cancelled"] or report["invalid_scope"]:
        raise ValueError("current assessment unavailable or cancelled")
    current = report["plan"]
    if plan["schema_version"] in (2, 3, 4) and (current["schema_version"] != plan["schema_version"] or current["policy"] != plan["policy"]):
        raise ValueError("unknown or changed typed policy")
    removed = {row["path"] for row in completed if row.get("operation") == "git-worktree-remove"}
    expected_roots = [root for root in plan["scope_roots"] if root not in removed]
    expected_identities = {root: value for root, value in plan["scope_identities"].items() if root not in removed}
    if current["scope_roots"] != expected_roots or current["scope_identities"] != expected_identities:
        raise ValueError("scope/worktree/root identity changed")
    rows = {row["id"]: row for row in current["candidates"]}
    for old in selected:
        if is_npm_cache(old):
            from .npm_cache import revalidate, overlap_protection
            specifications = [item for item in assessment["candidates"] if plans.digest(item) == old["specification_digest"]]
            if len(specifications) != 1:
                raise ValueError("original npm assessment missing")
            if overlap_protection(specifications[0], assessment, expected_roots, manifest):
                raise ValueError("overlapping cache consumer/retention obligations prevent removal")
            rows[old["id"]] = revalidate(old, specifications[0], assessment["references"], completed, limits)
            continue
        if is_docker(old):
            from .docker_cleanup import revalidate
            specifications = [row for row in assessment["candidates"] if plans.digest(row) == old["specification_digest"]]
            if len(specifications) != 1:
                raise ValueError("original Docker assessment missing")
            rows[old["id"]] = revalidate(old, specifications[0], assessment["references"], completed, limits["timeout_seconds"])
            continue
        new = rows.get(old["id"])
        if new is None or new["assessment"] != "Eligible":
            raise ValueError("selected candidate no longer eligible")
        if plan["schema_version"] in (2, 3, 4):
            expected = dict(old)
            native = old["operation"] == "git-worktree-remove"
            if native:
                expected["native"] = {**old["native"], "worktrees": [record for record in old["native"]["worktrees"]
                                                                    if record["path"] not in removed]}
            if new != expected:
                raise ValueError("unknown or changed typed resource/evidence/content/identity fields")
            if not is_docker(old):
                _snapshot(old, limits, native=new["native"] if native else None)
            continue
        for key in ("path", "host", "category", "project", "effect", "preconditions", "specification_digest", "references", "agent_assessment"):
            if new[key] != old[key]:
                raise ValueError("selected evidence/effect/identity changed")
        for key in ("complete", "identity", "tree_digest", "tree_identity_digest", "filesystem_local", "file_count", "size"):
            if new["observation"][key] != old["observation"][key]:
                raise ValueError("selected content/identity changed")
        _snapshot(old, limits)
    return [rows[row["id"]] for row in selected]


def _snapshot(row, limits, *, native=None):
    """Canonical inspected tree plus current mutation capabilities, never eligibility."""
    if native:
        for source in ("repository", "common_directory", "administration"):
            native_path = Path(native[source])
            parent = plans._open_parent(native_path)
            descriptor = None
            try:
                descriptor = os.open(native_path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                _supported_filesystem(descriptor)
            finally:
                if descriptor is not None:
                    os.close(descriptor)
                os.close(parent)
    path = Path(row["path"])
    snapshot = review_task(path, inspect_content=True, max_entries=limits["max_entries"],
                           max_depth=limits["max_depth"], timeout=limits["timeout_seconds"],
                           max_content_bytes=limits["max_content_bytes"],
                           worktree_marker=native["marker_identity"] if native else None)
    if (not snapshot["content"]["complete"] or not snapshot.get("filesystem_local")
            or snapshot.get("identity") != row["observation"]["identity"]
            or plans.digest(plans._entries(snapshot)) != row["observation"]["tree_digest"]
            or plans.tree_identity_digest(snapshot) != row["observation"]["tree_identity_digest"]
            or snapshot.get("root_protection") or any(entry["assessment"] == "Keep" for entry in snapshot["entries"])):
        raise ValueError("tree changed immediately before removal")
    # Preflight all mutation permissions before any selected item is touched.
    # access() observes current effective-user ACL/mode facts, not future rights.
    for candidate in (path, *(path / entry["path"] for entry in snapshot["entries"])):
        parent = plans._open_parent(candidate)
        try:
            metadata = os.stat(candidate.name, dir_fd=parent, follow_symlinks=False)
            flags = getattr(stat, "UF_IMMUTABLE", 0) | getattr(stat, "UF_APPEND", 0) | getattr(stat, "SF_IMMUTABLE", 0) | getattr(stat, "SF_APPEND", 0)
            if getattr(metadata, "st_flags", 0) & flags:
                raise ValueError("immutable/append-only resource")
            if not os.access(".", os.W_OK | os.X_OK, dir_fd=parent, effective_ids=True, follow_symlinks=False):
                raise ValueError("directory mutation permission unavailable")
            if candidate == path:
                _sync_file(parent)  # prove final directory/drive flush capability before mutation
            if stat.S_ISDIR(metadata.st_mode):
                child = os.open(candidate.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                try:
                    _supported_filesystem(child)
                    if (not os.access(".", os.W_OK | os.X_OK, dir_fd=child, effective_ids=True, follow_symlinks=False)
                            or mount_identity(child) != metadata.st_dev):
                        raise ValueError("directory permission/mount capability unavailable")
                finally:
                    os.close(child)
        finally:
            os.close(parent)
    return snapshot


def _remove(row, limits):
    """Delete only the enumerated original tree, checking identity before each action.

    Names are never followed; replacement detection is best effort, not an atomic
    inode-conditional unlink. Open descriptors alone cannot prevent same-user races.
    """
    path = Path(row["path"])
    snapshot = _snapshot(row, limits)
    entries = {entry["path"]: entry for entry in snapshot["entries"]}
    parent = plans._open_parent(path)
    root = None
    started = time.monotonic()
    try:
        root = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        _supported_filesystem(root)
        if file_identity(os.fstat(root)) != snapshot["identity"] or not local_filesystem(root):
            raise ValueError("root replaced or capability unavailable")
        root_mount = mount_identity(root)
        guards = [(parent, path.name, root)]

        def unchanged_paths():
            if time.monotonic() - started >= limits["timeout_seconds"]:
                raise ValueError("removal time budget exhausted; remaining items stopped")
            check_parent = plans._open_parent(path)
            try:
                if _stable(os.stat(path.name, dir_fd=check_parent, follow_symlinks=False)) != _stable(os.fstat(root)):
                    raise ValueError("root path substituted")
            finally:
                os.close(check_parent)
            for directory, name, opened in guards:
                if (_stable(os.stat(name, dir_fd=directory, follow_symlinks=False)) != _stable(os.fstat(opened))
                        or mount_identity(opened) != root_mount):
                    raise ValueError("directory path or mount substituted")

        def walk(descriptor, relative):
            children = {Path(name).name: entry for name, entry in entries.items() if str(Path(name).parent) == (relative or ".")}
            for name, entry in list(children.items()):
                unchanged_paths()
                if set(os.listdir(descriptor)) != set(children):
                    raise ValueError("directory contents changed")
                metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if file_identity(metadata) != entry["identity"]:
                    raise ValueError("entry identity changed")
                if entry["kind"] == "directory":
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                    try:
                        if file_identity(os.fstat(child)) != entry["identity"]:
                            raise ValueError("directory replaced before open")
                        guards.append((descriptor, name, child))
                        walk(child, entry["path"])
                        unchanged_paths()
                        if os.listdir(child):
                            raise ValueError("new nested content; remaining actions stopped")
                        os.rmdir(name, dir_fd=descriptor)
                        guards.pop()
                    finally:
                        os.close(child)
                elif entry["kind"] == "file":
                    child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
                    try:
                        if file_identity(os.fstat(child)) != entry["identity"]:
                            raise ValueError("file replaced before open")
                        if mount_identity(child) != root_mount:
                            raise ValueError("file mount substituted before removal read")
                        checksum = hashlib.sha256()
                        read_bytes = 0
                        while True:
                            chunk = os.read(child, 65536)
                            if not chunk:
                                break
                            read_bytes += len(chunk)
                            if read_bytes > entry["logical_bytes"]:
                                raise ValueError("file grew during revalidation")
                            checksum.update(chunk)
                            unchanged_paths()
                        unchanged_paths()
                        if (checksum.hexdigest() != entry["sha256"] or file_identity(os.fstat(child)) != entry["identity"]
                                or file_identity(os.stat(name, dir_fd=descriptor, follow_symlinks=False)) != entry["identity"]):
                            raise ValueError("file content or identity changed")
                        os.unlink(name, dir_fd=descriptor)
                    finally:
                        os.close(child)
                else:
                    raise ValueError("unsupported entry type")
                del children[name]
                os.fsync(descriptor)
            if os.listdir(descriptor):
                raise ValueError("new contents after removal; directory retained")

        walk(root, "")
        unchanged_paths()
        os.rmdir(path.name, dir_fd=parent)
        _sync_file(parent)
    finally:
        if root is not None:
            os.close(root)
        os.close(parent)


def _measurement(before, after):
    return {"filesystems": [{"device": device, "before_free_bytes": value,
                             "after_free_bytes": after.get(device),
                             "net_free_change_bytes": None if value is None or after.get(device) is None else after[device] - value}
                            for device, value in before.items()],
            "attribution": "net observed filesystem change; not guaranteed recovery or exact target attribution"}


def _free(selected):
    values = {}
    for row in selected:
        device = _device(row)
        if device not in values:
            try:
                # Parent persists after exact target removal.
                path = row["native"]["resource"]["endpoint"][7:] if is_docker(row) else row["native"]["resource"]["cache"] if is_npm_cache(row) else row["path"]
                metadata = os.statvfs(Path(path).parent)
                values[device] = metadata.f_bavail * metadata.f_frsize
            except OSError:
                values[device] = None
    return values


def _device(row):
    if is_npm_cache(row):
        return row["native"]["cache_identity"]["device"]
    return row["native"]["provider"]["socket"]["dev"] if is_docker(row) else row["observation"]["identity"]["device"]


def _receipt_host(plan):
    return {key: plan["host"][key] for key in ("identity", "system")}


def _operation(plan):
    return OPERATION if plan["schema_version"] == 1 else "permanent-selected-resource-removal"


def _warnings(plan):
    if plan["schema_version"] == 1:
        return WARNINGS
    warnings = [*WARNINGS, "Native Git removal retains branches; ignored data has no automatic undo. Refusal/timeout stops the batch; reconcile without retry."]
    if plan["schema_version"] in (3, 4):
        warnings.append("Docker estimates are daemon/shared storage, separate from observed host filesystem change. No volume removal or VM compaction; native timeout leaves unknown effects.")
    if plan["schema_version"] == 4:
        warnings.append("Npm removal can require later downloads/network and increase build cost; no offline recovery or universal undo. Shared aliases are protected.")
    return warnings


def _target_record(row, outcome):
    # Fixed schema prevents assessed purpose/paths/source payloads entering receipts.
    if is_docker(row):
        return {"id": row["id"], "identity": row["observation"]["identity"],
                "operation": row["operation"], "resource_id": row["native"]["resource"]["id"],
                "native_identity_digest": plans.digest(row["native"]),
                "provider_size_bytes_estimate": row["native"]["size"],
                "logical_bytes_estimate": None, "allocated_bytes_estimate": None, "outcome": outcome}
    if is_npm_cache(row):
        return {"id": row["id"], "identity": row["observation"]["identity"], "operation": row["operation"],
                "native_identity_digest": plans.digest(row["native"]),
                "logical_bytes_estimate": row["native"]["size"]["logical_bytes"],
                "allocated_bytes_estimate": row["native"]["size"]["allocated_bytes"], "outcome": outcome}
    target = {"id": row["id"], "identity": row["observation"]["identity"],
            "logical_bytes_estimate": row["observation"]["size"]["logical_bytes"],
            "allocated_bytes_estimate": row["observation"]["size"]["allocated_bytes"], "outcome": outcome}
    if "operation" in row:
        target["operation"] = row["operation"]
        if row["operation"] == "git-worktree-remove":
            target["native_identity_digest"] = plans.digest(row["native"])
    return target


def _validated_intent(state, pending, plan):
    host = _receipt_host(plan)
    if (set(pending) != {"schema_version", "operation_id", "plan_digest", "host", "intent_digest"}
            or pending["schema_version"] != plan["schema_version"] or pending["plan_digest"] != plan["digest"] or pending["host"] != host):
        raise ValueError("pending state does not match original plan")
    operation_id = pending["operation_id"]
    if not isinstance(operation_id, str) or len(operation_id) != 32 or any(c not in "0123456789abcdef" for c in operation_id):
        raise ValueError("invalid pending operation identity")
    intent = state.read(operation_id + ".intent.json")
    if intent is None or plans.digest(intent) != pending["intent_digest"]:
        raise ValueError("durable intent missing/changed; preserve pending state, do not retry")
    rows = {row["id"]: row for row in plan["candidates"]}
    identifiers = [target["id"] for target in intent["targets"]]
    if not identifiers or len(identifiers) != len(set(identifiers)) or any(identifier not in rows for identifier in identifiers):
        raise ValueError("invalid intent selection")
    selected = [rows[identifier] for identifier in identifiers]
    if any(row["assessment"] != "Eligible" for row in selected):
        raise ValueError("intent contains ineligible original row")
    before = {}
    for measurement in intent["measurement"]["filesystems"]:
        value = measurement["before_free_bytes"]
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError("invalid intent measurement")
        before[measurement["device"]] = value
    if set(before) != {_device(row) for row in selected}:
        raise ValueError("intent filesystem identity mismatch")
    expected = {"schema_version": plan["schema_version"], "operation_id": operation_id, "operation": _operation(plan),
                "plan_digest": plan["digest"], "host": host, "warnings": _warnings(plan),
                "outcome": "intent", "targets": [_target_record(row, "not-started") for row in selected],
                "measurement": _measurement(before, {})}
    if intent != expected:
        raise ValueError("unsupported/corrupted intent fields; preserve state")
    return intent


def apply(plan_path, assessment_path, selected_ids, *, all_eligible=False, manifest_path=None, config_path=None):
    _capabilities()
    plan, selected = _load_plan(plan_path, selected_ids, all_eligible)
    for source in (plan_path, assessment_path, manifest_path, config_path):
        if source and any(not is_docker(row) and not is_npm_cache(row) and plans._inside(Path(os.path.abspath(source)), Path(row["path"])) for row in selected):
            raise ValueError("original transaction inputs must remain outside every selected target")
    # No public confirmation callback/flag/receipt parameter.
    with State([row["native"]["resource"]["cache"] if is_npm_cache(row) and "native" in row else row["path"]
                for row in plan["candidates"] if not is_docker(row)] + plan["scope_roots"]) as state:
        if state.read("pending.json") is not None:
            raise ValueError("interrupted operation pending; reconcile with its original plan before new review/confirmation")
        _revalidate(plan, selected, assessment_path, manifest_path, config_path)
        if not _confirm(plan, selected):
            return {"schema_version": 1, "outcome": "cancelled", "targets": []}
        # Confirmation can take arbitrarily long. Recheck the entire batch afterward.
        _revalidate(plan, selected, assessment_path, manifest_path, config_path)
        operation_id = uuid.uuid4().hex
        targets = [_target_record(row, "not-started") for row in selected]
        before = _free(selected)
        intent = {"schema_version": plan["schema_version"], "operation_id": operation_id, "operation": _operation(plan),
                  "plan_digest": plan["digest"], "host": _receipt_host(plan), "warnings": _warnings(plan),
                  "outcome": "intent", "targets": targets, "measurement": _measurement(before, {})}
        state.write(operation_id + ".intent.json", intent)
        state.write("pending.json", {"schema_version": plan["schema_version"], "operation_id": operation_id,
                                     "plan_digest": plan["digest"], "host": _receipt_host(plan),
                                     "intent_digest": plans.digest(intent)})
        result = {**intent, "targets": [dict(target) for target in targets], "outcome": "completed"}
        try:
            for index, row in enumerate(selected):
                current_rows = _revalidate(plan, selected[index:], assessment_path, manifest_path, config_path, selected[:index])
                state.verify()
                result["targets"][index]["outcome"] = "started-outcome-unknown"
                if is_npm_cache(row):
                    from .npm_cache import remove
                    remove(current_rows[0], plan["policy"]["limits"])
                elif is_docker(row):
                    from .docker_cleanup import remove
                    remove(current_rows[0], plan["policy"]["limits"])
                elif plan["schema_version"] in (2, 3, 4) and row["operation"] == "git-worktree-remove":
                    from .git_worktree import remove
                    remove(current_rows[0], plan["policy"]["limits"])
                else:
                    _remove(row, plan["policy"]["limits"])
                result["targets"][index]["outcome"] = "removed"
        except (OSError, ValueError, KeyError, TypeError, KeyboardInterrupt) as error:
            result["outcome"] = "partial-or-failed"
            from .git_worktree import NativeRemovalFailed
            if isinstance(error, NativeRemovalFailed):
                result["native_failure"] = error.diagnostic
        result["measurement"] = _measurement(before, _free(selected))
        try:
            state.write(operation_id + ".result.json", result)
            if result["outcome"] == "completed":
                state.clear_pending()
        except (OSError, ValueError, KeyboardInterrupt):
            result["outcome"] = "result-unavailable"
        return result


def reconcile(plan_path):
    """Inspect interrupted identities only. Never continue or retry deletion."""
    _capabilities()
    plan = plans.read_document(plan_path, versions=(1, 2, 3, 4))
    if set(plan) != PLAN_FIELDS or plan["digest"] != plans.digest({key: value for key, value in plan.items() if key != "digest"}):
        raise ValueError("original frozen plan required")
    with State([row["native"]["resource"]["cache"] if is_npm_cache(row) and "native" in row else row["path"]
                for row in plan["candidates"] if not is_docker(row)] + plan["scope_roots"]) as state:
        pending = state.read("pending.json")
        if pending is None or plan["host"] != plans.new_report("", None, {})["host"]:
            raise ValueError("no matching same-host pending operation")
        intent = _validated_intent(state, pending, plan)
        if plan["schema_version"] in (2, 3, 4):
            plans.validate_selection(plan, [target["id"] for target in intent["targets"]])
        rows = {row["id"]: row for row in plan["candidates"]}
        observed = []
        for target in intent["targets"]:
            row = rows[target["id"]]
            if is_npm_cache(row):
                from .npm_cache import observe
                observed.append({**target, "outcome": observe(row)})
                continue
            if is_docker(row):
                from .docker_cleanup import observe
                observed.append({**target, "outcome": observe(row)})
                continue
            if plan["schema_version"] in (2, 3, 4) and row.get("operation") == "git-worktree-remove":
                from .git_worktree import observe
                observed.append({**target, "outcome": observe(row)})
                continue
            outcome = "unknown"
            parent = None
            try:
                parent = plans._open_parent(row["path"])
                metadata = os.stat(Path(row["path"]).name, dir_fd=parent, follow_symlinks=False)
                outcome = "same-identity-contents-unverified" if _stable(metadata) == {key: target["identity"][key] for key in ("device", "inode", "mode")} else "replaced"
            except FileNotFoundError:
                # A missing ancestor is not evidence the exact target was removed.
                outcome = "absent" if parent is not None else "unknown"
            except OSError:
                pass
            finally:
                if parent is not None:
                    os.close(parent)
            observed.append({**target, "outcome": outcome})
        result = {**intent, "targets": observed, "outcome": "reconciled-no-retry",
                  "measurement": {"attribution": "interruption prevents causal attribution; prior before-values retained", "before": intent["measurement"]}}
        # A crash after a previous reconciliation write must not overwrite it or
        # return stale observations. Each explicit inspection gets its own record.
        name = intent["operation_id"] + "." + uuid.uuid4().hex + ".reconciliation.json"
        state.write(name, result)
        state.clear_pending()
        return result
