"""Bounded local Git observations only; never establishes release or eligibility."""
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import time


OUTPUT_LIMIT = 1024 * 1024


class InspectionUnavailable(Exception):
    """A controlled diagnostic, with no raw Git stderr or file payloads."""


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
                    raise InspectionUnavailable("Git inspection time limit; remaining state unknown")
                if cancelled is not None and cancelled():
                    raise InspectionCancelled("Git inspection cancelled; remaining state unknown")
                for key, _ in selector.select(min(0.05, max(0, deadline - time.monotonic()))):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    elif len(output) + len(chunk) > OUTPUT_LIMIT:
                        raise InspectionUnavailable("Git output limit; truncated state is unknown")
                    else:
                        output.extend(chunk)
        try:
            returncode = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise InspectionUnavailable("Git inspection time limit; remaining state unknown") from None
        if returncode:
            raise GitRefused(returncode)
        return bytes(output)
    except OSError:
        raise InspectionUnavailable("Git inspection unavailable on this path/runtime") from None
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


def inventory_git(selected, *, max_worktrees=32, timeout=10.0, cancelled=None):
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

    try:
        selected = Path(os.path.abspath(os.fspath(selected)))
        if selected.resolve(strict=True) != selected or not selected.is_dir():
            raise InspectionUnavailable("Selected Git scope is missing or linked; not inspected")
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
                if record["bare"] or directory.resolve(strict=True) != directory or not directory.is_dir():
                    raise InspectionUnavailable("Bare, missing or linked worktree; status unknown")
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
