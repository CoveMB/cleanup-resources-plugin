"""Finite global coverage using the canonical assessed review owner.

Only explicitly selected paths and an optional local Docker endpoint are read.
Provider facts never establish deletion eligibility or host reclaimable bytes.
"""
import json
import os
from pathlib import Path
import shutil
import time

from .git_inventory import inventory_git, run_readonly, InspectionUnavailable, InspectionCancelled
from .report import new_report, OPTIONAL_CAPTURE_INSTRUCTION
from . import plans


EMPTY_ASSESSMENT = {"schema_version": 1, "references": {}, "candidates": []}


def validate_config(config):
    allowed = {"schema_version", "roots", "holds", "exclusions", "codex_worktrees",
               "package_storage", "docker_host", "host_identity"}
    if (not isinstance(config, dict) or set(config) - allowed or config.get("schema_version") != 1):
        raise ValueError("unsupported global configuration")
    for field in ("roots", "holds", "exclusions", "codex_worktrees", "package_storage"):
        paths = config.get(field, [])
        if (not isinstance(paths, list) or len(paths) > 32
                or any(not isinstance(path, str) or not Path(path).is_absolute() or len(path) > 4096 for path in paths)):
            raise ValueError("global paths require bounded absolute selections")
        if field in {"roots", "codex_worktrees", "package_storage"} and any(
                plans._same_path(Path(os.path.abspath(path)), Path(Path(path).anchor))
                or plans._same_path(Path(path).resolve(strict=False), Path(Path(path).anchor))
                or plans._same_path(Path(path), Path.home()) for path in paths):
            raise ValueError("home/whole-filesystem review is unsupported")
    for field in ("docker_host", "host_identity"):
        if field in config and (not isinstance(config[field], str) or not config[field] or len(config[field]) > 4096):
            raise ValueError("unsupported provider/host selection")


def inventory_docker(endpoint, *, timeout, cancelled=None):
    result = {"kind": "docker", "path": endpoint, "status": "unavailable", "assessment": "Review",
              "locality": "local-socket; daemon/VM allocation separate from execution host",
              "usage": [], "host_allocated_bytes": None, "vm_maximum_bytes": None,
              "reason": "Docker read-only inventory unavailable", "cancelled": False}
    if not endpoint.startswith("unix:///") or "\x00" in endpoint or os.name != "posix":
        result.update(status="skipped", locality="remote-or-unsupported", reason="remote/unsupported endpoint; no provider request")
        return result
    executable = shutil.which("docker")
    if executable is None:
        result["reason"] = "Docker executable unavailable; usage unknown"
        return result
    try:
        # Explicit endpoint plus stripped context/host/TLS overrides prevents
        # inherited Docker selection from causing a remote request.
        environment = {key: value for key, value in os.environ.items() if not key.startswith("DOCKER_")}
        output = run_readonly([executable, "--host", endpoint, "system", "df", "--format", "{{json .}}"],
                              None, environment, time.monotonic() + timeout, cancelled)
        usage = []
        for line in output.splitlines():
            row = json.loads(line)
            if not isinstance(row, dict) or not all(isinstance(row.get(key), str) and len(row[key]) <= 128
                    for key in ("Type", "TotalCount", "Active", "Size", "Reclaimable")):
                raise ValueError("unsupported Docker summary")
            if row["Type"] not in {"Images", "Containers", "Local Volumes", "Build Cache"}:
                raise ValueError("unsupported Docker category")
            usage.append({key: row[key] for key in ("Type", "TotalCount", "Active", "Size", "Reclaimable")})
        if len(usage) != 4 or {row["Type"] for row in usage} != {"Images", "Containers", "Local Volumes", "Build Cache"}:
            raise ValueError("incomplete or duplicate Docker summary")
        result.update(status="examined", usage=usage,
                      reason="read-only daemon summary; shared/reclaimable estimates are not eligibility or host allocation")
    except InspectionCancelled:
        result.update(cancelled=True, reason="Docker inspection cancelled; usage unknown")
    except (InspectionUnavailable, ValueError, UnicodeError, RecursionError):
        result["reason"] = "Docker refused, unavailable, timed out or unsupported response; usage unknown"
    return result


def review_global(config, *, assessment=None, manifest=None, holds=(), exclusions=(), max_entries=2000,
                  max_depth=12, timeout=10.0, max_content_bytes=256 * 1024 * 1024, cancelled=None,
                  evidence_warn_bytes=plans.EVIDENCE_WARN_BYTES, evidence_explain_bytes=plans.EVIDENCE_EXPLAIN_BYTES):
    plans.validate_evidence_thresholds(evidence_warn_bytes, evidence_explain_bytes)
    validate_config(config)
    assessment = assessment or EMPTY_ASSESSMENT
    plans._validate_assessment(assessment)
    if any(not Path(row["path"]).is_absolute() for row in assessment["candidates"]):
        raise ValueError("global candidate paths must be absolute")
    if manifest is not None:
        plans.validate_manifest(manifest)
    started = time.monotonic()
    report = new_report("configured development roots and providers", None,
                        {"max_entries": max_entries, "max_depth": max_depth, "timeout_seconds": timeout})
    report.update(scope={"mode": "global", "selected": "configured development roots and providers", "canonical": None},
                  scope_roots=[], candidates=[], root_reviews=[], locations=[], git_inventories=[],
                  content={"read_bytes": 0, "examined": 0})
    report["coverage"]["unconfigured"] = 0
    report["retention"] = {
        "cli": {"effective": None, "status": "unsupported", "reason": "effective installed CLI retention interface unverified"},
        "desktop": {"effective": None, "status": "unsupported", "reason": "effective desktop settings interface unverified"},
        "risk": "Independent Codex cleanup may remove retained worktrees; plugin holds do not control it.",
        "resume": "Accepted handoff/release must preserve dirty, untracked and ignored state and an agreed resume path; tracked commits alone are insufficient. Native snapshots and ignored-file recovery are unverified."}
    report["warnings"].append(report["retention"]["risk"])
    report["limitations"].extend([
        "Global covers configured locations only, never a whole-disk audit. Unconfigured/unavailable usage is unknown.",
        "Provider storage is report-only and excluded from assessed targets. Package storage uses selected metadata paths, no package-manager commands.",
        "Docker usage is separate from host totals: shared layers/reclaimable labels are estimates; VM maximum and actual allocated host storage are unknown.",
        "Effective CLI and desktop retention settings are independently unknown; no settings/database or history scan, and no settings changes.",
        "Filesystem locality cannot establish absence of synchronization or consumers; unresolved boundaries must remain report-only in assessment."])
    selected_exclusions = list(exclusions) + config.get("exclusions", [])
    provider_paths = config.get("codex_worktrees", []) + config.get("package_storage", [])
    holds = list(holds) + config.get("holds", []) + provider_paths
    exclusions = list(exclusions) + config.get("exclusions", []) + provider_paths
    # Protect every configured root, including roots skipped as overlapping.
    configured_roots = [Path(os.path.abspath(path)) for path in config.get("roots", [])]
    report["scope_roots"] = list(dict.fromkeys([str(path) for path in configured_roots] + provider_paths))
    host_matches = config.get("host_identity", report["host"]["identity"]) == report["host"]["identity"]
    entries_remaining, bytes_remaining = max_entries, max_content_bytes
    seen_paths, seen_provider_paths, seen_files, seen_candidates = [], [], set(), set()
    assigned = set()

    def remaining():
        return max(0.000001, timeout - (time.monotonic() - started))

    def stopped():
        if report["cancelled"]:
            return True
        if cancelled is not None and cancelled():
            report["cancelled"] = True
            return True
        return time.monotonic() - started >= timeout or entries_remaining <= 0

    def location(kind, path=None, status="unconfigured", reason="no location configured; usage unknown"):
        row = {"kind": kind, "path": path, "host": report["host"], "status": status,
               "assessment": "Review", "reason": reason, "locality": "unknown"}
        report["locations"].append(row)
        return row

    def count(snapshot):
        # Root metadata entries have physical file identities. Provider estimates
        # stay separate; cross-root links are counted exactly once here.
        for entry in snapshot["entries"]:
            if entry["kind"] != "file" or "accounting_identity" not in entry:
                continue
            identity = tuple(entry["accounting_identity"])
            if identity in seen_files:
                report["size"]["duplicate_hardlinks"] += 1
                continue
            seen_files.add(identity)
            report["size"]["unique_files"] += 1
            report["size"]["logical_bytes"] += entry["logical_bytes"]
            if entry["allocated_bytes"] is None:
                report["size"]["allocated_bytes"] = None
            else:
                report["size"]["known_allocated_bytes"] += entry["allocated_bytes"]
                if report["size"]["allocated_bytes"] is not None:
                    report["size"]["allocated_bytes"] += entry["allocated_bytes"]

    for kind, paths in (("development", config.get("roots", [])),
                        ("codex-worktrees", config.get("codex_worktrees", [])),
                        ("package-storage", config.get("package_storage", []))):
        if not paths:
            location(kind)
        for value in sorted(paths, key=lambda value: len(Path(value).parts)):
            path = Path(os.path.abspath(value))
            row = location(kind, str(path), "skipped")
            if not host_matches:
                row["reason"] = "configured host mismatch; no local/provider inspection"
                continue
            if stopped():
                row["reason"] = "global limit/cancellation; remaining usage unknown"
                continue
            if any(plans._overlap(path, prior) for prior in (seen_paths if kind == "development" else seen_provider_paths)):
                row["reason"] = "overlapping/alias location already covered; estimate not added again"
                continue
            if any(plans._inside(path, Path(os.path.abspath(value))) for value in selected_exclusions):
                row["reason"] = "excluded location; contents unknown"
                continue
            if kind == "development":
                specifications = []
                for index, specification in enumerate(assessment["candidates"]):
                    if index not in assigned and plans._inside(Path(specification["path"]), path):
                        assigned.add(index)
                        specifications.append(specification)
                scoped = {**assessment, "candidates": specifications}
                snapshot = plans.review_scope(path, mode="task", assessment=scoped, manifest=manifest, holds=holds,
                                              exclusions=exclusions, max_entries=entries_remaining, max_depth=max_depth,
                                              timeout=remaining(), max_content_bytes=bytes_remaining, cancelled=cancelled,
                                              evidence_warn_bytes=evidence_warn_bytes, evidence_explain_bytes=evidence_explain_bytes)
                bytes_remaining = max(0, bytes_remaining - snapshot["content"]["read_bytes"])
                report["content"]["read_bytes"] += snapshot["content"]["read_bytes"]
                report["content"]["examined"] += snapshot["content"]["examined"]
                report["root_reviews"].append(snapshot)
                report["warnings"].extend(json.dumps(str(path)) + ": " + warning for warning in snapshot["warnings"])
                entries_remaining -= sum(candidate.get("observation", {}).get("coverage", {}).get("examined", 0) for candidate in snapshot["candidates"])
                for candidate in snapshot["candidates"]:
                    candidate = dict(candidate)
                    if candidate["id"] not in seen_candidates:
                        if any(plans._same_path(Path(candidate["path"]), root) for root in configured_roots):
                            candidate.update(assessment="Keep", reason="configured development root")
                        report["candidates"].append(candidate)
                        seen_candidates.add(candidate["id"])
                count(snapshot)
            else:
                # Provider roots are explicit opt-in metadata-only locations,
                # never content assessment or generic executor candidates.
                from .review import review_task
                snapshot = review_task(path, max_entries=entries_remaining, max_depth=max_depth,
                                       timeout=remaining(), cancelled=cancelled,
                                       exclusions=selected_exclusions)
                row["size"] = snapshot["size"]
            (seen_paths if kind == "development" else seen_provider_paths).append(path)
            entries_remaining -= snapshot["coverage"]["examined"]
            report["coverage"]["examined"] += snapshot["coverage"]["examined"]
            report["coverage"]["skipped"] += snapshot["coverage"]["skipped"]
            report["coverage"]["inaccessible"] += snapshot["coverage"]["inaccessible"]
            report["cancelled"] |= snapshot["cancelled"]
            row.update(status="examined" if not snapshot["invalid_scope"] else "unavailable",
                       reason="bounded metadata inspection" if snapshot["coverage"]["complete"] else "partial coverage; unexamined usage unknown",
                       locality="local-filesystem-observed" if snapshot.get("filesystem_local") else "unsupported-or-unknown",
                       coverage=snapshot["coverage"])
            if any("EACCES" in entry.get("reason", "") or "EPERM" in entry.get("reason", "") for entry in snapshot["entries"]):
                row["status"] = "inaccessible"
            if kind != "package-storage" and not snapshot["invalid_scope"]:
                git_roots = list(dict.fromkeys((path / entry["path"]).parent for entry in snapshot["entries"]
                                               if Path(entry["path"]).name == ".git" and entry["kind"] in {"file", "directory"}))
                for git_root in git_roots[:32]:
                    if stopped():
                        row["reason"] = "Git inventory budget exhausted; worktree state unknown"
                        row["coverage"]["complete"] = False
                        break
                    inventory = inventory_git(git_root, timeout=remaining(), cancelled=cancelled)
                    report["git_inventories"].append({"path": str(git_root), **inventory})
                    report["scope_roots"] = list(dict.fromkeys(report["scope_roots"] + [str(git_root)] + [item["path"] for item in inventory["worktrees"]]))
                    report["cancelled"] |= inventory["cancelled"]
                    if not inventory["complete"]:
                        row["coverage"]["complete"] = False
                if len(git_roots) > 32:
                    row["coverage"]["complete"] = False
                    row["reason"] = "Git repository limit; remaining worktrees unknown"
    if not config.get("docker_host"):
        location("docker")
    elif not host_matches or stopped():
        location("docker", config["docker_host"], "skipped", "host mismatch or global limit/cancellation; no provider request")
    else:
        row = inventory_docker(config["docker_host"], timeout=remaining(), cancelled=cancelled)
        row["host"] = report["host"]
        report["locations"].append(row)
        report["cancelled"] |= row["cancelled"]
    for index, specification in enumerate(assessment["candidates"]):
        if index not in assigned:
            path = os.path.abspath(specification["path"])
            identifier = plans.hashlib.sha256(os.fsencode(path)).hexdigest()[:16]
            if identifier in seen_candidates:
                continue
            seen_candidates.add(identifier)
            report["candidates"].append({"id": identifier, "path": path,
                "host": report["host"], "category": specification.get("category", "unknown"), "project": None,
                "assessment": "Keep", "reason": "outside examined configured roots; never selected",
                "effect": "report only; no removal authorized"})
    report["coverage"]["unconfigured"] = sum(row["status"] == "unconfigured" for row in report["locations"])
    report["coverage"]["complete"] = not report["cancelled"] and all(
        row["status"] == "examined" and row.get("coverage", {}).get("complete", True) for row in report["locations"])
    report["size"]["complete"] = report["coverage"]["complete"]
    if report["cancelled"]:
        report["coverage"]["stop_reason"] = "global review cancelled"
    report["evidence_capture"] = {"warning_bytes": evidence_warn_bytes, "explanation_bytes": evidence_explain_bytes,
        "packets": [packet for snapshot in report["root_reviews"] for packet in snapshot["evidence_capture"]["packets"]],
        "optional_instruction": OPTIONAL_CAPTURE_INSTRUCTION}
    # The same frozen data owner protects future selection. Provider paths and
    # configured roots remain explicit even when unavailable or overlapping.
    plans.freeze_review(report, assessment, manifest, holds, exclusions,
                        {**report["limits"], "max_content_bytes": max_content_bytes, "global_config_digest": plans.digest(config)})
    return report
