"""Bounded local Git observations only; never establishes release or eligibility."""
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import time
from typing import Callable

from .review import path_inside


OUTPUT_LIMIT = 1024 * 1024


class InspectionUnavailable(Exception):
    """A controlled diagnostic, with no raw Git stderr or file payloads."""


class InspectionRefused(InspectionUnavailable):
    def __init__(self, returncode):
        super().__init__(f"Read-only command refused inspection (exit {returncode}); state unknown")
        self.returncode = returncode


class GitRefused(InspectionUnavailable):
    def __init__(self, returncode):
        super().__init__(f"Git refused inspection (exit {returncode}); repository/state unknown")
        self.returncode = returncode


class InspectionCancelled(InspectionUnavailable):
    pass


def _git(executable, directory, arguments, deadline, cancelled):
    if time.monotonic() >= deadline:
        raise InspectionUnavailable("Git inspection time limit; remaining state unknown")
    if cancelled is not None and cancelled():
        raise InspectionCancelled("Git inspection cancelled; remaining state unknown")
    # Inherited GIT_DIR/INDEX_FILE/WORK_TREE/config injection must not redirect scope.
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GIT_NO_LAZY_FETCH"] = "1"
    environment["GIT_ALLOW_PROTOCOL"] = ""
    command = [executable, "--no-pager", "--no-optional-locks",
               "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
               *arguments]
    try:
        return run_readonly(command, directory, environment, deadline, cancelled)
    except InspectionRefused as error:
        raise GitRefused(error.returncode) from None
    except InspectionUnavailable as error:
        raise type(error)(str(error).replace("Read-only command", "Git")) from None


def run_readonly(command, directory, environment, deadline, cancelled=None):
    """Bound an explicitly constructed read-only command; suppress raw stderr."""
    if time.monotonic() >= deadline:
        raise InspectionUnavailable("Read-only command inspection time limit; remaining state unknown")
    if cancelled is not None and cancelled():
        raise InspectionCancelled("Read-only command inspection cancelled; remaining state unknown")
    process = None
    try:
        process = subprocess.Popen(command, cwd=directory, env=environment,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL)
        output = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                if time.monotonic() >= deadline:
                    raise InspectionUnavailable("Read-only command inspection time limit; remaining state unknown")
                if cancelled is not None and cancelled():
                    raise InspectionCancelled("Read-only command inspection cancelled; remaining state unknown")
                for key, _ in selector.select(min(0.05, max(0, deadline - time.monotonic()))):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    elif len(output) + len(chunk) > OUTPUT_LIMIT:
                        raise InspectionUnavailable("Read-only command output limit; truncated state is unknown")
                    else:
                        output.extend(chunk)
        try:
            returncode = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise InspectionUnavailable("Read-only command inspection time limit; remaining state unknown") from None
        if returncode:
            raise InspectionRefused(returncode)
        return bytes(output)
    except OSError:
        raise InspectionUnavailable("Read-only command inspection unavailable on this path/runtime") from None
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()


def _worktrees(output):
    if not output.endswith(b"\0\0"):
        raise InspectionUnavailable("Incomplete Git worktree format; inventory unknown")
    records = []
    for record in output[:-2].split(b"\0\0"):
        fields = {}
        for field in record.split(b"\0"):
            key, _, value = field.partition(b" ")
            fields[os.fsdecode(key)] = os.fsdecode(value)
        if "worktree" not in fields:
            raise InspectionUnavailable("Unsupported Git worktree format; inventory unknown")
        records.append({"path": fields["worktree"], "head": fields.get("HEAD"),
                        "branch": fields.get("branch"), "locked": "locked" in fields,
                        "detached": "detached" in fields, "bare": "bare" in fields,
                        "prunable": "prunable" in fields})
    return records


def _status(output):
    if output and not output.endswith(b"\0"):
        raise InspectionUnavailable("Incomplete Git status format; state unknown")
    paths = {"staged": [], "dirty": [], "untracked": [], "ignored": []}
    entries = iter(output[:-1].split(b"\0") if output else [])
    for entry in entries:
        if len(entry) < 4 or entry[2:3] != b" ":
            raise InspectionUnavailable("Unsupported Git status format; state unknown")
        code, path = entry[:2], os.fsdecode(entry[3:])
        if code == b"??":
            paths["untracked"].append(path)
        elif code == b"!!":
            paths["ignored"].append(path)
        else:
            if code[0:1] != b" ":
                paths["staged"].append(path)
            if code[1:2] != b" ":
                paths["dirty"].append(path)
            if b"R" in code or b"C" in code:
                if next(entries, None) is None:
                    raise InspectionUnavailable("Incomplete Git rename status; state unknown")
    return {key: sorted(value) for key, value in paths.items()}


def inventory_git(selected, *, exclusions=(), max_worktrees=32, timeout=10.0, cancelled=None):
    """Inventory Git-discovered worktrees without network access or index refresh.

    `complete` means these finite Git observations succeeded. It never describes
    content inspection, absence of current activity, recovery, or release.
    """
    result = {"complete": False, "cancelled": False, "worktrees": [], "limitations": [
        "Worktrees and branches are report-only; no removal or release authorization.",
        "Activity and consumers are unknown; clean status and completion/age do not establish release.",
        "Upstream comparisons use local refs only; no fetch or remote freshness claim.",
        "Ignored directory paths may be collapsed by Git; payloads and submodule contents are not inspected.",
    ]}
    if os.name != "posix":
        result["limitations"].append("Bounded Git pipe inspection unavailable on this platform")
        return result
    executable = shutil.which("git")
    if executable is None:
        result["limitations"].append("Git executable unavailable; repository/state unknown")
        return result
    deadline = time.monotonic() + timeout

    def git(directory, *arguments):
        return _git(executable, directory, arguments, deadline, cancelled)

    excluded_paths = [Path(os.path.abspath(value)) for value in exclusions]

    def check_exclusions(directory):
        _check_exclusions(directory, excluded_paths)


    def metadata_target(path, prefix=b""):
        # Reuse bounded, descriptor-based Git metadata reads after module loading.
        from .git_worktree import _metadata_file
        check_exclusions(path)
        try:
            payload, _ = _metadata_file(path)
        except ValueError:
            raise InspectionUnavailable("Git link metadata unavailable; inspection skipped and state unknown") from None
        if not payload.startswith(prefix):
            raise InspectionUnavailable("Unsupported Git metadata link; inspection skipped and state unknown")
        value = payload[len(prefix):].removesuffix(b"\n")
        if not value or b"\n" in value or b"\0" in value:
            raise InspectionUnavailable("Unsupported Git metadata link; inspection skipped and state unknown")
        target = path.parent / os.fsdecode(value)
        check_exclusions(target)
        try:
            resolved = target.resolve(strict=True)
        except (OSError, RuntimeError):
            raise InspectionUnavailable("Git metadata target unavailable; inspection skipped and state unknown") from None
        # A symlink before .. can make Git use a different directory than abspath.
        if resolved != Path(os.path.abspath(target)):
            raise InspectionUnavailable("Git metadata target traverses a linked path; inspection skipped and state unknown")
        return resolved

    def check_metadata(directory):
        if not excluded_paths:
            return
        metadata = directory / ".git"
        check_exclusions(metadata)
        if not metadata.is_dir():
            metadata = metadata_target(metadata, b"gitdir: ")
        check_exclusions(metadata)
        if metadata.resolve(strict=True) != metadata or not metadata.is_dir():
            raise InspectionUnavailable("Git metadata directory unavailable or linked; state unknown")
        try:
            common = metadata_target(metadata / "commondir")
        except FileNotFoundError:
            return
        check_exclusions(common)
        if common.resolve(strict=True) != common or not common.is_dir():
            raise InspectionUnavailable("Common Git metadata directory unavailable or linked; state unknown")

    try:
        selected = Path(os.path.abspath(os.fspath(selected)))
        check_exclusions(selected)
        if selected.resolve(strict=True) != selected or not selected.is_dir():
            raise InspectionUnavailable("Selected Git scope is missing or linked; not inspected")
        check_metadata(selected)
        records = _worktrees(git(selected, "worktree", "list", "--porcelain", "-z"))
        if str(selected) not in {record["path"] for record in records}:
            raise InspectionUnavailable("Selected directory is not a worktree root; parent/linked scope not expanded")
        result["complete"] = True
        if len(records) > max_worktrees:
            result["complete"] = False
            result["limitations"].append("Worktree limit; additional worktree state unknown")
        for record in records[:max_worktrees]:
            record.update(activity="unknown", report_only=True, status_complete=False,
                          staged=None, dirty=None, untracked=None, ignored=None,
                          upstream=None, ahead_of_local_upstream=None,
                          upstream_reason="Upstream/unpushed state unknown",
                          guidance="Preserve this checkout and ignored/dirty work for resume. "
                                   "Resume in the existing isolated checkout, or reconstruct a new one only "
                                   "with separately preserved local state. Recommend release only after "
                                   "accepted completion/handoff, normally review/merge, and consumer assessment.")
            result["worktrees"].append(record)
            try:
                directory = Path(record["path"])
                check_exclusions(directory)
                if record["bare"] or directory.resolve(strict=True) != directory or not directory.is_dir():
                    raise InspectionUnavailable("Bare, missing or linked worktree; status unknown")
                check_metadata(directory)
                try:
                    filters = git(directory, "config", "--null", "--name-only", "--get-regexp",
                                  r"^filter\..*\.(clean|process)$")
                except GitRefused as error:
                    if error.returncode != 1:  # git config: 1 means no matching keys.
                        raise
                    filters = b""
                if filters:
                    # Even status can run clean/process commands. Never execute user
                    # code or silently change filter semantics to obtain a clean view.
                    raise InspectionUnavailable("Configured Git content filter; status not inspected")
                record.update(_status(git(directory, "status", "--porcelain=v1", "-z",
                                          "--untracked-files=all", "--ignored=matching",
                                          "--ignore-submodules=all")))
                record["status_complete"] = True
                record["status_reason"] = "Local Git status observed; content/use unverified"
                if not record["detached"]:
                    try:
                        upstream = git(directory, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
                        ahead = git(directory, "rev-list", "--count", "@{upstream}..HEAD")
                        record["upstream"] = os.fsdecode(upstream.removesuffix(b"\n"))
                        record["ahead_of_local_upstream"] = int(ahead)
                        record["upstream_reason"] = "Compared with local upstream ref only; remote freshness unknown"
                    except (GitRefused, ValueError):
                        # No upstream (including unborn branches) is common, never zero unpushed.
                        record["upstream_reason"] = "No inspectable local upstream; unpushed state unknown"
            except InspectionCancelled:
                raise
            except (InspectionUnavailable, OSError) as error:
                result["complete"] = False
                record["status_reason"] = str(error) if isinstance(error, InspectionUnavailable) else "Worktree unavailable; status unknown"
    except (KeyboardInterrupt, InspectionCancelled):
        result["complete"] = False
        result["cancelled"] = True
        result["limitations"].append("Git inspection cancelled; remaining state unknown")
    except (InspectionUnavailable, OSError) as error:
        result["complete"] = False
        result["limitations"].append(str(error) if isinstance(error, InspectionUnavailable) else "Selected Git scope unavailable")
    return result

def _check_exclusions(directory: Path, excluded_paths: tuple[Path, ...]) -> None:
    # Broad Git commands can enumerate descendants or read repository metadata.
    if any(path_inside(directory, excluded) or path_inside(excluded, directory)
           for excluded in excluded_paths):
        raise InspectionUnavailable("Git scope overlaps an exclusion; inspection skipped and state unknown")


def validate_lineage_request(document: dict) -> dict:
    """Validate only the bounded literal input shape; acquire no paths or refs."""
    fields = {"schema_version", "repository", "path", "expected_head", "retained_ref", "destination_ref"}
    if (not isinstance(document, dict) or set(document) != fields
            or type(document.get("schema_version")) is not int or document["schema_version"] != 1):
        raise ValueError("unsupported Git lineage document")
    for name in ("repository", "path"):
        value = document[name]
        if (not isinstance(value, str) or not value or len(value) > 4096 or "\0" in value
                or not Path(value).is_absolute() or os.path.normpath(value) != value):
            raise ValueError("Git lineage requires bounded normalized absolute paths")
    oid = document["expected_head"]
    if not isinstance(oid, str) or len(oid) not in (40, 64) or any(c not in "0123456789abcdef" for c in oid):
        raise ValueError("Git lineage requires a full lowercase commit identity")
    for name in ("retained_ref", "destination_ref"):
        value = document[name]
        if (not isinstance(value, str) or len(value) > 1024 or "\0" in value
                or not value.startswith(("refs/heads/", "refs/remotes/"))
                or any(c in value for c in ("~", "^", ":", "?", "*", "[", "\\", " ", "\n", "\r", "\t", "@{"))):
            raise ValueError("Git lineage requires bounded literal full refs")
    return dict(document)


def _lineage_result(status="not_examined", reason="scope_or_budget_unavailable"):
    from datetime import datetime, timezone
    return {"status": status, "reason": reason,
            "observed_at": datetime.now(timezone.utc).isoformat(), "binding": {},
            "retention": {"head_in_ref": None}, "ancestry": {"head_in_destination": None},
            "recovery": {"retained": None, "root_count": None, "coverage": "unknown",
                         "reason": "recovery_not_observed", "content_availability": "not_certified"},
            "integration": {"status": "not_requested"}, "patch_equivalence": {"status": "not_requested"},
            "report_only": True, "refs_local_only": True, "remote_freshness": "unknown",
            "release": "not_established", "current_use": "unknown",
            "limitations": ["Before/after binding checks are not an atomic snapshot.",
                            "Recovery reachability does not certify all content availability.",
                            "Primary/private administration recovery is unsupported; consumers and release need scoped evidence."]}


def observe_lineage(repository: Path, record: dict, request: dict, *, exclusions: tuple[str, ...] = (),
                    deadline: float, cancelled: Callable[[], bool] | None = None) -> dict:
    """One explicitly matched checkout, advisory only, under the outer deadline."""
    from .git_worktree import _identity, _metadata_file, _administration_state, _head_history
    from .plans import _open_parent
    from .review import file_identity
    import stat

    request = validate_lineage_request(request)
    result = _lineage_result()
    repository, target = Path(repository), Path(request["path"])
    excluded = tuple(Path(os.path.abspath(path)) for path in exclusions)
    boundaries = [repository, target]
    binding_started = False
    invalid_ref = False

    def guard(path):
        if cancelled is not None and cancelled():
            raise InspectionCancelled("Git lineage cancelled; remaining state unknown")
        if time.monotonic() >= deadline:
            raise InspectionUnavailable("Git lineage time limit; remaining state unknown")
        _check_exclusions(Path(path), excluded)

    def identity(path, *, directory=True):
        guard(path)
        return _identity(path, directory=directory)

    def metadata(path):
        guard(path)
        return _metadata_file(Path(path))

    def lstat(path):
        guard(path)
        parent = _open_parent(path)
        try:
            try:
                return os.stat(Path(path).name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                return None
        finally:
            os.close(parent)

    def link(path, prefix=b""):
        payload, observed = metadata(path)
        if not payload.startswith(prefix):
            raise InspectionUnavailable("Git lineage metadata unsupported")
        value = payload[len(prefix):].removesuffix(b"\n")
        if not value or b"\n" in value or b"\0" in value:
            raise InspectionUnavailable("Git lineage metadata unsupported")
        destination = Path(os.path.abspath(Path(path).parent / os.fsdecode(value)))
        # _identity rejects symlinks and _open_parent rejects linked ancestors.
        # Also reject .. link traversal rather than normalizing it into authority.
        raw = Path(path).parent / os.fsdecode(value)
        guard(raw)
        if raw.resolve(strict=True) != destination:
            raise InspectionUnavailable("Git lineage metadata linked or changed")
        identity(destination)
        return destination, observed

    def paths(directory):
        directory_identity = identity(directory)
        marker = directory / ".git"
        entry = lstat(marker)
        if entry is None:
            raise InspectionUnavailable("Git lineage marker unavailable")
        if stat.S_ISDIR(entry.st_mode):
            admin = common = marker
            marker_identity = identity(marker)
            links = None
        elif stat.S_ISREG(entry.st_mode):
            admin, marker_identity = link(marker, b"gitdir: ")
            common, common_marker = link(admin / "commondir")
            reverse, reverse_identity = metadata(admin / "gitdir")
            if reverse != os.fsencode(str(marker) + "\n"):
                raise InspectionUnavailable("Git lineage reverse binding unavailable")
            links = {"commondir": common_marker, "gitdir": reverse_identity}
        else:
            raise InspectionUnavailable("Git lineage marker unsupported")
        return {"path": str(directory), "identity": directory_identity,
                "marker_identity": marker_identity, "administration": str(admin),
                "administration_identity": identity(admin), "common_directory": str(common),
                "common_identity": identity(common), "links": links}

    try:
        # No executable/path acquisition until successful ordinary scope matching.
        if (str(repository) != request["repository"] or record.get("path") != str(target)
                or not record.get("status_complete") or record.get("bare") or record.get("prunable")):
            return result
        for path in boundaries:
            guard(path)
        initial_paths = [paths(directory) for directory in (repository, target)]
        if initial_paths[0]["common_directory"] != initial_paths[1]["common_directory"]:
            raise InspectionUnavailable("Git lineage common binding unavailable")
        common = Path(initial_paths[0]["common_directory"])
        admin = Path(initial_paths[1]["administration"])
        boundaries.extend((common, admin))
        executable = shutil.which("git")
        if os.name != "posix" or not executable:
            raise InspectionUnavailable("Git lineage executable unavailable")
        guard(executable)
        executable = str(Path(executable).resolve(strict=True))
        executable_identity = identity(executable, directory=False)

        def git(directory, *arguments):
            for boundary in boundaries:
                guard(boundary)
            return _git(executable, directory, ["--no-replace-objects", *arguments], deadline, cancelled)

        def text(directory, *arguments):
            return os.fsdecode(git(directory, *arguments)).removesuffix("\n")

        for directory in (repository, target):
            if text(directory, "rev-parse", "--show-toplevel") != str(directory):
                raise InspectionUnavailable("Git lineage top-level binding unavailable")
            for flag, expected in (("--git-common-dir", common),
                                   ("--git-dir", Path(initial_paths[(repository, target).index(directory)]["administration"]))):
                if text(directory, "rev-parse", "--path-format=absolute", flag) != str(expected):
                    raise InspectionUnavailable("Git lineage metadata binding unavailable")
        records = _worktrees(git(repository, "worktree", "list", "--porcelain", "-z"))
        registered = [row for row in records if row["path"] == str(target)]
        if len(registered) != 1:
            raise InspectionUnavailable("Git lineage registration unavailable")
        object_format = text(repository, "rev-parse", "--show-object-format")
        oid_length = {"sha1": 40, "sha256": 64}.get(object_format)
        if oid_length is None or len(request["expected_head"]) != oid_length:
            raise InspectionUnavailable("Git lineage object format unavailable")

        def oid(value):
            if len(value) != oid_length or any(c not in "0123456789abcdef" for c in value):
                raise InspectionUnavailable("Git lineage object identity unavailable")
            return value

        def branch():
            try:
                return text(target, "symbolic-ref", "--quiet", "HEAD")
            except GitRefused as error:
                if error.returncode == 1:
                    return None
                raise

        def resolve(ref):
            value = oid(text(repository, "rev-parse", "--verify", ref))
            if git(repository, "cat-file", "-t", value) != b"commit\n":
                raise InspectionUnavailable("Git lineage endpoint is not a commit")
            return value

        for ref in (request["retained_ref"], request["destination_ref"]):
            try:
                git(repository, "check-ref-format", ref)
            except GitRefused as error:
                if error.returncode == 1:
                    invalid_ref = True
                    raise ValueError("invalid Git lineage full ref syntax") from None
                raise
        head = resolve("HEAD") if target == repository else oid(text(target, "rev-parse", "--verify", "HEAD"))
        if git(target, "cat-file", "-t", head) != b"commit\n":
            raise InspectionUnavailable("Git lineage HEAD is not a commit")
        current_branch = branch()
        result["binding"] = {"repository": str(repository), "repository_identity": initial_paths[0]["identity"],
                             "repository_administration": initial_paths[0]["administration"],
                             "repository_administration_identity": initial_paths[0]["administration_identity"],
                             "repository_marker_identity": initial_paths[0]["marker_identity"],
                             **initial_paths[1], "head": head, "branch": current_branch,
                             "detached": current_branch is None, "retained_ref": request["retained_ref"],
                             "destination_ref": request["destination_ref"], "object_format": object_format,
                             "executable": executable, "executable_identity": executable_identity}
        if head != request["expected_head"] or head != record.get("head") or current_branch != record.get("branch"):
            result.update(status="changed", reason="binding_changed")
            return result
        retained, destination = resolve(request["retained_ref"]), resolve(request["destination_ref"])
        result["binding"].update(retained_oid=retained, destination_oid=destination)

        def graph_policy():
            shallow = lstat(common / "shallow")
            if shallow is not None and not stat.S_ISREG(shallow.st_mode):
                raise InspectionUnavailable("Git lineage shallow policy unavailable")
            # Grafts are refused by metadata existence only, never payload reads.
            if lstat(common / "info/grafts") is not None:
                raise InspectionUnavailable("Git lineage graft policy unsupported")
            state = text(repository, "rev-parse", "--is-shallow-repository")
            if state not in ("true", "false"):
                raise InspectionUnavailable("Git lineage graph policy unavailable")
            return (file_identity(shallow) if shallow else None, state)

        policy = graph_policy()
        binding_started = True
        complete = policy[1] == "false" and policy[0] is None

        def ancestor(first, second):
            if not complete:
                return None
            try:
                git(repository, "merge-base", "--is-ancestor", first, second)
                return True
            except GitRefused as error:
                return False if error.returncode == 1 else None

        result["retention"]["head_in_ref"] = ancestor(head, retained)
        result["ancestry"]["head_in_destination"] = ancestor(head, destination)
        administration_state = None
        try:
            if admin.parent != common / "worktrees":
                raise ValueError("primary recovery unsupported")
            guard(admin)
            administration_state = _administration_state(admin)
            roots = [head]
            if "logs/HEAD" in administration_state:
                guard(admin / "logs/HEAD")
                roots.extend(_head_history(admin, administration_state["logs/HEAD"], oid_length))
            if "ORIG_HEAD" in administration_state:
                payload, observed = metadata(admin / "ORIG_HEAD")
                original = os.fsdecode(payload.removesuffix(b"\n"))
                oid(original)
                if original == "0" * oid_length or observed != administration_state["ORIG_HEAD"]:
                    raise ValueError("unsupported recovery root")
                roots.append(original)
            roots = list(dict.fromkeys(roots))
            result["recovery"]["root_count"] = len(roots)
            valid = True
            for root in roots:
                # Check every distinct nonzero root directly; never peel a tag.
                try:
                    if git(repository, "cat-file", "-t", root) != b"commit\n":
                        valid = False
                except GitRefused:
                    valid = False
            if valid and complete:
                unretained = git(repository, "rev-list", "--max-count=1", *roots, "--not", retained)
                if unretained:
                    oid(os.fsdecode(unretained).removesuffix("\n"))
                result["recovery"].update(retained=not bool(unretained), coverage="supported_linked_roots",
                                          reason="supported_roots_observed")
        except InspectionCancelled:
            raise
        except (ValueError, OSError, InspectionUnavailable):
            pass

        # All derived observations depend on the final binding and graph policy.
        final_paths = [paths(directory) for directory in (repository, target)]
        current_executable = shutil.which("git")
        if current_executable:
            guard(current_executable)
            current_executable = str(Path(current_executable).resolve(strict=True))
        if (final_paths != initial_paths or identity(executable, directory=False) != executable_identity
                or current_executable != executable
                or text(target, "rev-parse", "--verify", "HEAD") != head or branch() != current_branch
                or resolve(request["retained_ref"]) != retained or resolve(request["destination_ref"]) != destination
                or graph_policy() != policy):
            raise InspectionUnavailable("Git lineage binding changed")
        if administration_state is not None:
            guard(admin)
            if _administration_state(admin) != administration_state:
                raise InspectionUnavailable("Git lineage administration changed")
        result.update(status="observed" if all(value is not None for value in
                      (result["retention"]["head_in_ref"], result["ancestry"]["head_in_destination"],
                       result["recovery"]["retained"])) else "partial", reason="local_observation")
        return result
    except InspectionCancelled:
        raise
    except (InspectionUnavailable, OSError, RuntimeError, ValueError):
        if invalid_ref:
            raise
        result["retention"]["head_in_ref"] = None
        result["ancestry"]["head_in_destination"] = None
        result["recovery"]["retained"] = None
        result.update(status="changed" if binding_started else "unavailable",
                      reason="binding_or_policy_unavailable" if binding_started else "inspection_unavailable")
        return result
