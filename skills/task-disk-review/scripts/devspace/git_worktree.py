"""Fixed native Git lifecycle for explicitly assessed ordinary linked checkouts.

No force, shell deletion, branch deletion, app database or inferred inactivity.
"""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time

from .git_inventory import _git, _worktrees, _status, GitRefused, InspectionUnavailable
from .review import file_identity, path_inside, same_path


EFFECT = "permanent native linked-worktree removal; branch retained; reconstruct tracked source from retained ref, no ignored-data undo"


class NativeRemovalFailed(ValueError):
    """Fixed, payload-free native diagnostic safe for a private receipt."""
    def __init__(self, kind, exit_code=None):
        super().__init__("native Git mutation did not establish success; reconcile without retry")
        self.diagnostic = {"kind": kind, "exit_code": exit_code}


def _metadata_file(path, limit=4096):
    from .plans import _open_parent
    parent = _open_parent(path)
    try:
        descriptor = os.open(Path(path).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(descriptor, "rb") as stream:
            before = file_identity(os.fstat(stream.fileno()))
            if not stat.S_ISREG(before["mode"]) or before["size"] > limit:
                raise ValueError("unsupported Git link metadata")
            payload = stream.read(limit + 1)
            if len(payload) > limit or before != file_identity(os.fstat(stream.fileno())):
                raise ValueError("Git link metadata changed")
            return payload, before
    finally:
        os.close(parent)


def _head_history(administration, expected_identity, oid_length):
    """Extract both recovery roots; never return identity/message text.

    Bounded record scanning consumes opaque trailing bytes locally, discards
    them, and never includes them in reports, errors or receipts.
    """
    payload, identity = _metadata_file(Path(administration) / "logs/HEAD", limit=1024 * 1024)
    if identity != expected_identity or payload and not payload.endswith(b"\n"):
        raise ValueError("HEAD reflog identity/record boundary changed or unsupported")
    records = payload.splitlines()
    if len(records) > 128:
        raise ValueError("HEAD reflog recovery exceeds supported record bound")
    history = []
    for record in records:
        fields = record.split(b" ", 2)
        if len(fields) != 3 or not fields[2]:
            raise ValueError("malformed HEAD reflog record")
        for commit in fields[:2]:
            if len(commit) != oid_length or any(character not in b"0123456789abcdef" for character in commit):
                raise ValueError("malformed HEAD reflog recovery identity")
            if commit != b"0" * oid_length:
                history.append(os.fsdecode(commit))
    return list(dict.fromkeys(history))


def _administration_state(path):
    """Bounded no-follow metadata only; unknown private state stays untouched."""
    from .plans import _open_parent
    parent = _open_parent(path)
    descriptor = None
    try:
        descriptor = os.open(Path(path).name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        state = {}
        count = 0
        with os.scandir(descriptor) as entries:
            for entry in entries:
                count += 1
                if entry.name not in {"HEAD", "index", "commondir", "gitdir", "ORIG_HEAD", "logs", "refs"} or count > 7:
                    raise ValueError("per-worktree configuration or unsupported administration state; preserve checkout")
                metadata = entry.stat(follow_symlinks=False)
                if entry.name in {"logs", "refs"}:
                    if not stat.S_ISDIR(metadata.st_mode):
                        raise ValueError("unsupported worktree log boundary")
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                    try:
                        if file_identity(os.fstat(child)) != file_identity(metadata):
                            raise ValueError("worktree log identity changed")
                        with os.scandir(child) as logs:
                            for log in logs:
                                if entry.name != "logs" or log.name != "HEAD" or "logs/HEAD" in state:
                                    raise ValueError("unsupported private worktree log state")
                                observed = log.stat(follow_symlinks=False)
                                if not stat.S_ISREG(observed.st_mode):
                                    raise ValueError("unsupported worktree log file")
                                state["logs/HEAD"] = file_identity(observed)
                    finally:
                        os.close(child)
                elif not stat.S_ISREG(metadata.st_mode):
                    raise ValueError("unsupported worktree administration file")
                state[entry.name] = file_identity(metadata)
        if not {"HEAD", "index", "commondir", "gitdir"} <= state.keys():
            raise ValueError("incomplete worktree administration state")
        return state
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)


def _identity(path, *, directory=True):
    from .plans import _open_parent
    path = Path(path)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError("native Git identity missing or linked")
    parent = _open_parent(path)
    try:
        metadata = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if not (stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)):
            raise ValueError("unsupported native Git identity")
        identity = file_identity(metadata)
        return {key: identity[key] for key in ("device", "inode", "mode")} if directory else identity
    finally:
        os.close(parent)


def inspect(repository, target, retained_ref, *, timeout=10, cancelled=None):
    """Bind native identities and local state; never evaluates release evidence."""
    repository, target = Path(repository), Path(target)
    executable = shutil.which("git")
    if not executable:
        raise ValueError("Git executable unavailable")
    executable = str(Path(executable).resolve(strict=True))
    executable_identity = _identity(executable, directory=False)
    repository_identity = _identity(repository)
    target_identity = _identity(target)
    if same_path(repository, target) or path_inside(Path.cwd(), target):
        raise ValueError("selected/current worktree is protected")
    # A known app-managed location cannot be released through an ordinary Git
    # assertion. Its supported owning lifecycle/resume interface is required.
    managed_roots = {Path.home() / ".codex" / "worktrees"}
    if os.environ.get("CODEX_HOME"):
        managed_roots.add(Path(os.environ["CODEX_HOME"]) / "worktrees")
    if any(path_inside(target, root) for root in managed_roots):
        raise ValueError("Codex-managed worktree requires verified owning lifecycle; unavailable")
    deadline = time.monotonic() + timeout

    def git(directory, *arguments):
        return _git(executable, directory, arguments, deadline, cancelled)

    try:
        for directory in (repository, target):
            if os.fsdecode(git(directory, "rev-parse", "--show-toplevel")).rstrip("\n") != str(directory):
                raise ValueError("Git worktree configuration redirects the selected root")
        records = _worktrees(git(repository, "worktree", "list", "--porcelain", "-z"))
        matches = [record for record in records if record["path"] == str(target)]
        if len(matches) != 1 or str(repository) not in {record["path"] for record in records}:
            raise ValueError("not an exact Git-discovered linked worktree")
        record = matches[0]
        if (records[0]["path"] == str(target) or any(record[key] for key in ("locked", "bare", "prunable", "detached"))
                or not record["branch"] or record["branch"] != retained_ref or not retained_ref.startswith("refs/heads/")):
            raise ValueError("main/locked/detached/unknown retained branch is protected")
        def absolute(directory, flag):
            value = os.fsdecode(git(directory, "rev-parse", "--path-format=absolute", flag)).rstrip("\n")
            return str(Path(value))
        common = absolute(repository, "--git-common-dir")
        if absolute(target, "--git-common-dir") != common:
            raise ValueError("common repository mismatch")
        administration = absolute(target, "--git-dir")
        if Path(administration).parent != Path(common) / "worktrees":
            raise ValueError("unsupported linked worktree administration")
        administration_state = _administration_state(administration)
        marker = target / ".git"
        marker_identity = _identity(marker, directory=False)
        # rev-parse verified the .git link; content is metadata, never receipt data.
        payload, observed_marker = _metadata_file(marker)
        if observed_marker != marker_identity or payload != os.fsencode("gitdir: " + administration + "\n"):
            raise ValueError("unsupported or changed worktree marker")
        reverse, _ = _metadata_file(Path(administration) / "gitdir")
        if reverse != os.fsencode(str(marker) + "\n"):
            raise ValueError("worktree administration reverse identity mismatch")
        try:
            filters = git(target, "config", "--null", "--name-only", "--get-regexp", r"^filter\..*\.(clean|process)$")
        except GitRefused as error:
            if error.returncode != 1:
                raise
            filters = b""
        if filters:
            raise ValueError("configured Git content filters; inspection unavailable")
        local_status = _status(git(target, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignored=matching", "--ignore-submodules=none"))
        if any(local_status[key] for key in ("staged", "dirty", "untracked")):
            raise ValueError("dirty/staged/untracked worktree remains protected")
        tracked = git(target, "ls-files", "-v", "-z")
        if any(not entry.startswith(b"H ") for entry in tracked.split(b"\0") if entry):
            raise ValueError("assume-unchanged/skip-worktree/unmerged index unsupported")
        tree = git(target, "ls-tree", "-r", "-z", "HEAD")
        if any(entry.startswith(b"160000 ") for entry in tree.split(b"\0")):
            raise ValueError("submodule worktree unsupported")
        retained_head = os.fsdecode(git(repository, "rev-parse", "--verify", retained_ref + "^{commit}")).strip()
        head = os.fsdecode(git(target, "rev-parse", "--verify", "HEAD")).strip()
        if head != retained_head or head != record["head"]:
            raise ValueError("retained branch/HEAD changed")
        # Native removal also deletes the private HEAD reflog. Its commits must
        # remain reconstructible from the bound retained branch, not just HEAD.
        history = _head_history(administration, administration_state["logs/HEAD"], len(head)) if "logs/HEAD" in administration_state else []
        if "ORIG_HEAD" in administration_state:
            history.append(os.fsdecode(git(target, "rev-parse", "--verify", "ORIG_HEAD^{commit}")).strip())
        if history and int(git(repository, "rev-list", "--count", *history, "--not", retained_ref)):
            raise ValueError("worktree HEAD reflog contains unretained commits; preserve checkout")
        if _administration_state(administration) != administration_state:
            raise ValueError("worktree administration changed during inspection")
        return {"repository": str(repository), "repository_identity": repository_identity,
                "common_directory": common, "common_identity": _identity(common),
                "administration": administration, "administration_identity": _identity(administration),
                "administration_state": administration_state,
                "marker_identity": marker_identity, "target_identity": target_identity,
                "head": head, "retained_ref": retained_ref, "worktrees": records,
                "executable": executable, "executable_identity": executable_identity,
                "ignored": local_status["ignored"]}
    except InspectionUnavailable as error:
        raise ValueError(str(error)) from None


def remove(row, limits):
    """One fixed argument vector. Timeout/refusal never invokes another remover."""
    native = row["native"]
    current = inspect(native["repository"], row["path"], native["retained_ref"], timeout=limits["timeout_seconds"])
    if current != native:
        raise ValueError("native Git state changed immediately before command")
    from .cleanup import _snapshot
    _snapshot(row, limits, native=current)
    # Recheck topology/refs after potentially long content inspection.
    if inspect(native["repository"], row["path"], native["retained_ref"], timeout=limits["timeout_seconds"]) != native:
        raise ValueError("native Git state changed after content inspection")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="")
    try:
        result = subprocess.run([native["executable"], "--no-pager", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
                                 "worktree", "remove", "--", row["path"]],
                                cwd=native["repository"], env=environment, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=limits["timeout_seconds"])
    except subprocess.TimeoutExpired:
        raise NativeRemovalFailed("timeout-outcome-unknown") from None
    if result.returncode:
        raise NativeRemovalFailed("native-refusal", result.returncode)
    if observe(row) != "absent-and-unregistered-branch-retained":
        raise NativeRemovalFailed("observation-outcome-unknown", result.returncode)


def observe(row):
    """Read-only reconciliation checks both provider registration and retained ref."""
    native = row["native"]
    try:
        executable = shutil.which("git")
        if (not executable or str(Path(executable).resolve(strict=True)) != native["executable"]
                or not native["retained_ref"].startswith("refs/heads/")
                or _identity(native["repository"]) != native["repository_identity"]
                or _identity(native["common_directory"]) != native["common_identity"]
                or _identity(native["executable"], directory=False) != native["executable_identity"]):
            return "unknown-native-identity"
        deadline = time.monotonic() + 10
        records = _worktrees(_git(native["executable"], native["repository"], ["worktree", "list", "--porcelain", "-z"], deadline, None))
        head = os.fsdecode(_git(native["executable"], native["repository"], ["rev-parse", "--verify", native["retained_ref"] + "^{commit}"], deadline, None)).strip()
        if head != native["head"]:
            return "retained-ref-changed"
        registered = [record for record in records if record["path"] == row["path"]]
        if not os.path.lexists(row["path"]):
            return "absent-and-unregistered-branch-retained" if not registered else "absent-still-registered"
        if _identity(row["path"]) != native["target_identity"]:
            return "replaced"
        return "same-identity-contents-unverified" if registered else "present-unregistered"
    except (OSError, ValueError, InspectionUnavailable):
        return "unknown"
