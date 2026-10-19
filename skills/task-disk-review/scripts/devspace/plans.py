"""Shared assessed review/frozen data contract. Contains no execution or approval."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import time

from .git_inventory import inventory_git
from .report import (new_report, record_evidence_guidance, validate_evidence_thresholds,
                     EVIDENCE_WARN_BYTES, EVIDENCE_EXPLAIN_BYTES)
from .review import (descriptor_traversal_available, file_identity, protection, review_task,
                     same_path as _same_path, path_inside as _inside)


DOCUMENT_LIMIT = 1024 * 1024
MAX_CANDIDATES = 64
ASSESSMENT_BASIS = "agent evidence interpretation with mechanical checks"
BLOCKING_FINDINGS = {"required-failure", "persistent-state", "unique-state", "modified-dependency",
                     "offline-dependency", "inadequate-recovery", "hold", "active-consumer"}


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _open_parent(path):
    path = Path(os.path.abspath(os.fspath(path)))
    if not descriptor_traversal_available():
        raise ValueError("safe path inspection unavailable")
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_file(path, limit=DOCUMENT_LIMIT, deadline=None):
    """Open selected references through no-follow ancestors; never return raw errors."""
    path = Path(os.path.abspath(os.fspath(path)))
    if any(protection(component)[1] for component in path.parts):
        raise ValueError("protected input path; payload not read")
    descriptor = _open_parent(path)
    try:
        file_descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        try:
            before = os.fstat(file_descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                raise ValueError("reference must be a bounded regular file")
            data = bytearray()
            while True:
                if deadline is not None and time.monotonic() >= deadline:
                    raise ValueError("reference inspection time limit")
                chunk = os.read(file_descriptor, min(65536, limit - len(data) + 1))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > limit:
                    raise ValueError("reference byte limit")
            if file_identity(before) != file_identity(os.fstat(file_descriptor)):
                raise ValueError("reference changed during inspection")
            return bytes(data), file_identity(before)
        finally:
            os.close(file_descriptor)
    finally:
        os.close(descriptor)


def read_document(path, *, versions=(1,)):
    try:
        data, _ = _read_file(path)
        value = json.loads(data, object_pairs_hook=_unique_keys)
        if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value.get("schema_version") not in versions:
            raise ValueError("unsupported document schema")
        return value
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
        raise ValueError("document unavailable, malformed or beyond supported bounds") from None


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _overlap(first, second):
    return _inside(first, second) or _inside(second, first)


def _evidence_conflict(first, second):
    return any(_inside(Path(reference["path"]), Path(target["path"]))
               for candidate, target in ((first, second), (second, first))
               for reference in candidate.get("references", {}).values())


def _reference(identifier, references, target, observed, deadline):
    reference = references[identifier]
    if set(reference) != {"path", "sha256"}:
        raise ValueError("reference requires exact path and sha256")
    path = Path(os.path.abspath(reference["path"]))
    if _inside(path, target) or any(protection(part)[1] for part in path.parts):
        raise ValueError("protected or self-referential evidence")
    data, identity = _read_file(path, deadline=deadline)
    if any(identity["device"] == entry.get("device") and identity["inode"] == entry.get("inode")
           for entry in observed):
        raise ValueError("self-reference hardlink alias")
    if hashlib.sha256(data).hexdigest() != reference["sha256"]:
        raise ValueError("reference digest changed")
    return data, {"path": str(path), "sha256": reference["sha256"], "identity": identity}


def _entries(snapshot):
    entries = []
    for row in snapshot["entries"]:
        if "mode" not in row:
            continue
        if row["kind"] == "file":
            entries.append({"path": row["path"], "kind": "file", "mode": row["mode"],
                            "size": row["logical_bytes"], "sha256": row.get("sha256")})
        elif row["kind"] == "directory":
            entries.append({"path": row["path"], "kind": "directory", "mode": row["mode"]})
    return sorted(entries, key=lambda row: row["path"])


def tree_identity_digest(snapshot):
    """Bind descendant replacements independently of equivalent content/mode."""
    return digest(sorted(({"path": entry["path"], "identity": entry["identity"]}
                          for entry in snapshot["entries"] if "identity" in entry), key=lambda entry: entry["path"]))


def _expected_entries(entries):
    if not isinstance(entries, list) or len(entries) > 100000:
        raise ValueError("unsupported expected inventory")
    seen = set()
    for entry in entries:
        path = PurePosixPath(entry["path"])
        if path.is_absolute() or ".." in path.parts or str(path) != entry["path"] or str(path) == "." or str(path) in seen:
            raise ValueError("unsafe or duplicate inventory path")
        seen.add(str(path))
        fields = {"path", "kind", "mode"}
        if entry["kind"] == "file":
            fields |= {"size", "sha256"}
            if not isinstance(entry["sha256"], str) or len(entry["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in entry["sha256"]):
                raise ValueError("invalid expected file digest")
        elif entry["kind"] != "directory":
            raise ValueError("unsupported inventory entry type")
        if set(entry) != fields or type(entry["mode"]) is not int:
            raise ValueError("unsupported inventory fields")
    return sorted(entries, key=lambda row: row["path"])


def _validate_assessment(assessment):
    """Shape/bounds only. This deliberately does not evaluate source prose."""
    if not isinstance(assessment, dict) or type(assessment.get("schema_version")) is not int:
        raise ValueError("assessment version must be an integer")
    if isinstance(assessment, dict) and type(assessment.get("schema_version")) is int and assessment["schema_version"] == 4:
        from .npm_cache import validate_assessment
        return validate_assessment(assessment)
    if isinstance(assessment, dict) and assessment.get("schema_version") == 3:
        from .docker_cleanup import validate_assessment
        return validate_assessment(assessment)
    def fields(value, allowed):
        if not isinstance(value, dict) or set(value) - set(allowed):
            raise ValueError("unsupported assessment fields")

    def strings(value):
        if not isinstance(value, list) or len(value) > 128 or not all(isinstance(item, str) and len(item) <= 4096 for item in value):
            raise ValueError("unsupported assessment list")

    if not isinstance(assessment, dict) or set(assessment) != {"schema_version", "references", "candidates"} or assessment["schema_version"] not in (1, 2):
        raise ValueError("unsupported assessment; status/approval flags are not accepted")
    references, candidates = assessment["references"], assessment["candidates"]
    if not isinstance(references, dict) or len(references) > 128 or not isinstance(candidates, list) or len(candidates) > MAX_CANDIDATES:
        raise ValueError("assessment exceeds supported bounds")
    for identifier, reference in references.items():
        if not isinstance(identifier, str) or not isinstance(reference, dict) or set(reference) != {"path", "sha256"}:
            raise ValueError("unsupported reference")
        if not isinstance(reference["path"], str) or not Path(reference["path"]).is_absolute() or not isinstance(reference["sha256"], str):
            raise ValueError("reference requires absolute path and digest")
    for candidate in candidates:
        fields(candidate, {"path", "category", "purpose", "content", "recovery", "consumers", "consumer_scope", "release", "findings", "observed_tree_digest"} | ({"operation", "worktree"} if assessment["schema_version"] == 2 else set()))
        native = assessment["schema_version"] == 2 and candidate.get("operation") == "git-worktree-remove"
        if assessment["schema_version"] == 2:
            if candidate.get("operation") not in {"directory-remove", "git-worktree-remove"}:
                raise ValueError("unknown typed operation")
            if native:
                operation = candidate.get("worktree")
                if (not isinstance(operation, dict) or set(operation) != {"repository", "retained_ref", "lifecycle", "basis"}
                        or not isinstance(operation["repository"], str) or not Path(operation["repository"]).is_absolute()
                        or not isinstance(operation["retained_ref"], str) or operation["lifecycle"] not in {"git", "codex", "unknown"}):
                    raise ValueError("unsupported worktree lifecycle assessment")
                strings(operation["basis"])
            elif "worktree" in candidate:
                raise ValueError("directory cannot carry native worktree fields")
        if not isinstance(candidate.get("path"), str) or not candidate["path"]:
            raise ValueError("candidate path required")
        if not isinstance(candidate.get("category", "unknown"), str) or not isinstance(candidate.get("purpose", ""), str):
            raise ValueError("invalid candidate description")
        for key, allowed in {"content": {"method", "reference", "files", "directories", "basis", "explanation"},
                             "recovery": {"kind", "inputs", "basis", "explanation"},
                             "consumer_scope": {"basis", "unresolved"}, "release": {"basis", "checkpoint"}}.items():
            claim = candidate.get(key, {})
            fields(claim, allowed)
            strings(claim.get("basis", []))
            for text in ("method", "reference", "explanation", "kind", "checkpoint"):
                if text in claim and (not isinstance(claim[text], str) or len(claim[text]) > 4096):
                    raise ValueError("unsupported assessment text")
        strings(candidate.get("consumer_scope", {}).get("unresolved", []))
        strings(candidate.get("recovery", {}).get("inputs", []))
        content = candidate.get("content", {})
        if "files" in content and (not isinstance(content["files"], dict) or len(content["files"]) > 100000
                                   or not all(isinstance(path, str) and isinstance(identifier, str) for path, identifier in content["files"].items())):
            raise ValueError("unsupported source-file mapping")
        if "directories" in content:
            _expected_entries(content["directories"])
            if any(entry["kind"] != "directory" for entry in content["directories"]):
                raise ValueError("source-file comparison requires references for every file")
        consumers, findings = candidate.get("consumers", []), candidate.get("findings", [])
        if not isinstance(consumers, list) or len(consumers) > 128 or not isinstance(findings, list) or len(findings) > 128:
            raise ValueError("unsupported consumer/finding list")
        identifiers = set()
        for consumer in consumers:
            fields(consumer, {"id", "state", "basis"})
            if not isinstance(consumer.get("id"), str) or consumer["id"] in identifiers or consumer.get("state") not in {"active", "released", "unknown"}:
                raise ValueError("unsupported consumer record")
            identifiers.add(consumer["id"])
            strings(consumer.get("basis", []))
        for finding in findings:
            fields(finding, {"kind", "basis"})
            if finding.get("kind") not in BLOCKING_FINDINGS:
                raise ValueError("unsupported protective finding")
            strings(finding.get("basis", []))


def _assess(row, specification, references, snapshot, historical, deadline):
    """Mechanical gates plus explicitly attributed agent evidence interpretation.

    Reference hashes cannot adjudicate semantic truth or fabricated provenance.
    The agent must actually read/interpret sources.
    """
    row["assessment_basis"] = ASSESSMENT_BASIS
    row["specification_digest"] = digest(specification)
    row["agent_assessment"] = {"content_method": specification.get("content", {}).get("method"),
                               "recovery_kind": specification.get("recovery", {}).get("kind"),
                               "consumers": [{"id": consumer.get("id"), "state": consumer.get("state")}
                                             for consumer in specification.get("consumers", [])],
                               "release_checkpoint": specification.get("release", {}).get("checkpoint"),
                               "interpretation": "agent assessed provenance/purpose/rebuild/use/release; helper does not certify source meaning"}
    if specification.get("findings") or historical.get("retention"):
        row.update(assessment="Keep", reason="retention/protective finding; release cannot override")
        return
    consumers = specification.get("consumers", [])
    if any(consumer.get("state") == "active" for consumer in consumers):
        row.update(assessment="Keep", reason="known active consumer")
        return
    if snapshot.get("root_protection") or any(entry["assessment"] == "Keep" for entry in snapshot["entries"]):
        row.update(assessment="Keep", reason="protected content/state or original evidence")
        return
    if not row["observation"]["complete"]:
        row.update(assessment="Unavailable", reason="essential content inspection incomplete or unsupported")
        return
    if not snapshot.get("filesystem_local") or not row["host"].get("identity"):
        row.update(assessment="Unavailable", reason="execution host or local filesystem boundary unsupported/unknown")
        return
    observed = [entry.get("identity", {}) for entry in snapshot["entries"]]
    checked = {}
    payloads = {}

    def reference(identifier):
        if identifier not in checked:
            payloads[identifier], checked[identifier] = _reference(identifier, references, Path(row["path"]), observed, deadline)
        return payloads[identifier]

    def basis(claim):
        identifiers = claim.get("basis", [])
        if not identifiers:
            raise ValueError("missing contextual evidence; interpretation remains unknown")
        for identifier in identifiers:
            reference(identifier)

    try:
        content = specification.get("content", {})
        basis(content)
        actual = _entries(snapshot)
        if content.get("method") == "inventory":
            expected = json.loads(reference(content["reference"]), object_pairs_hook=_unique_keys)
            if set(expected) != {"schema_version", "entries"} or expected["schema_version"] != 1:
                raise ValueError("reference is not a target output inventory")
            expected = _expected_entries(expected["entries"])
        elif content.get("method") == "source-files":
            expected = []
            for path, identifier in content["files"].items():
                data = reference(identifier)
                expected.append({"path": path, "kind": "file", "mode": stat.S_IMODE(checked[identifier]["identity"]["mode"]),
                                 "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            expected += content.get("directories", [])
            expected = _expected_entries(expected)
        else:
            raise ValueError("no supported target-wide content comparison")
        row["comparison"] = {"method": content["method"], "matched": expected == actual,
                             "provenance": "agent interpreted; not mechanically certified"}
        if expected != actual:
            raise ValueError("extra, missing, modified or differently typed target contents")
        recovery = specification.get("recovery", {})
        basis(recovery)
        if row.get("operation") == "git-worktree-remove":
            from .git_worktree import EFFECT
            basis(specification["worktree"])
            if recovery.get("kind") != "retained-commit":
                raise ValueError("native worktree requires retained branch resume evidence")
            if row["native"]["ignored"]:
                if not recovery.get("inputs") or not recovery.get("explanation"):
                    raise ValueError("ignored generated contents need separate recovery evidence")
                for identifier in recovery["inputs"]:
                    reference(identifier)
            row["effect"] = EFFECT
        elif recovery.get("kind") == "rebuild":
            if not recovery.get("inputs"):
                raise ValueError("rebuild inputs unknown")
            for identifier in recovery["inputs"]:
                reference(identifier)
            row["effect"] = "permanent removal of this exact directory; rebuild required"
        elif recovery.get("kind") == "accepted-loss" and row["category"] != "dependencies":
            row["effect"] = "permanent removal of this exact directory; accepted loss, no undo promised"
        else:
            raise ValueError("adequate rebuild/recovery evidence unresolved")
        scope = specification.get("consumer_scope", {})
        basis(scope)
        if scope.get("unresolved", ["unknown"]):
            raise ValueError("consumer scope unresolved")
        known = set(historical.get("consumers", []))
        released = set()
        for consumer in consumers:
            basis(consumer)
            if consumer.get("state") != "released":
                raise ValueError("consumer state unresolved")
            released.add(consumer["id"])
        if not known <= released:
            raise ValueError("historical multiple consumers remain unresolved")
        release = specification.get("release", {})
        basis(release)
        if not release.get("checkpoint") or not specification.get("purpose") or row["category"] not in ({"worktree"} if row.get("operation") == "git-worktree-remove" else {"output", "dependencies"}):
            raise ValueError("purpose/category/release checkpoint unresolved")
        row.update(assessment="Eligible", reason="complete comparison and evidence-backed content/use/release/recovery assessment")
    except (ValueError, KeyError, TypeError, OSError, UnicodeError, RecursionError):
        row.update(assessment="Review", reason="content comparison or contextual evidence unresolved; inspect assessment and references")
    finally:
        row["references"] = checked


def validate_manifest(manifest):
    if set(manifest) != {"schema_version", "resources"} or manifest["schema_version"] != 1 or not isinstance(manifest["resources"], list):
        raise ValueError("unsupported manifest")
    if len(manifest["resources"]) > MAX_CANDIDATES:
        raise ValueError("manifest resource limit")
    seen = set()
    for resource in manifest["resources"]:
        if set(resource) != {"path", "origin", "purpose", "association", "consumers", "retention", "release_checkpoint"}:
            raise ValueError("manifest fields incomplete")
        if resource["origin"] != "helper-created" or not Path(resource["path"]).is_absolute():
            raise ValueError("manifests are opted-in historical helper-resource records only")
        if not isinstance(resource["consumers"], list) or not all(isinstance(item, str) for item in resource["consumers"]):
            raise ValueError("invalid manifest consumers")
        if not isinstance(resource["retention"], list) or not all(isinstance(item, str) for item in resource["retention"]):
            raise ValueError("invalid manifest retention")
        canonical = str(Path(resource["path"]).resolve(strict=False))
        if canonical in seen:
            raise ValueError("duplicate manifest resource")
        seen.add(canonical)
    return manifest


def review_scope(selected, *, npm_caches=(), **options):
    """Explicit optional cache discovery and v4 native selection, same journey."""
    from . import npm_cache
    deadline = time.monotonic() + options.get("timeout", 10.0)
    assessment = options.get("assessment")
    if assessment and assessment.get("schema_version") == 4:
        _validate_assessment(assessment)
        remaining = {**assessment, "schema_version": 3,
                     "candidates": [row for row in assessment["candidates"] if not npm_cache.is_npm_cache(row)]}
        report = _review_docker_scope(selected, **{**options, "assessment": remaining})
        old = report["plan"]
        content_remaining = max(0, old["policy"]["limits"]["max_content_bytes"] - report.get("content", {}).get("read_bytes", 0))
        for specification in assessment["candidates"]:
            if not npm_cache.is_npm_cache(specification):
                continue
            blocked = "npm cache held/excluded" if any(_overlap(Path(specification["npm"]["cache"]), Path(path))
                       for path in (*old["policy"]["holds"], *old["policy"]["exclusions"])) else None
            if options.get("mode") == "global" and selected.get("host_identity", report["host"]["identity"]) != report["host"]["identity"]:
                blocked = "configured execution host differs"
            protection = npm_cache.overlap_protection(specification, assessment, report["scope_roots"], options.get("manifest"))
            if report["cancelled"] or report["invalid_scope"]:
                raise ValueError("scope/cancellation prevents cache inspection")
            try:
                row = npm_cache.review(specification, assessment["references"], report["host"],
                                            report["scope"]["canonical"], timeout=max(0.001, deadline - time.monotonic()),
                                            max_entries=old["policy"]["limits"]["max_entries"],
                                            max_content_bytes=content_remaining,
                                            cancelled=options.get("cancelled"), blocked=blocked or (protection[1] if protection else None))
                if protection and not blocked:
                    row.update(assessment=protection[0], reason=protection[1])
                report["candidates"].append(row)
                if "native" in row:
                    consumed = row["native"]["size"]["logical_bytes"]
                    content_remaining -= consumed
                    report["content"]["read_bytes"] += consumed
            except npm_cache.InspectionCancelled:
                report["cancelled"] = True
                report["coverage"].update(complete=False, stop_reason="npm cache inspection cancelled")
                break
        freeze_review(report, assessment, options.get("manifest"), old["policy"]["holds"], old["policy"]["exclusions"], old["policy"]["limits"])
        report["limitations"] = [item.replace("Package storage remains metadata-only.", "Explicit supported npm entries use native cleanup; aggregate package storage remains metadata-only.")
                                 for item in report["limitations"]]
    else:
        report = _review_docker_scope(selected, **options)
    cache_roots = [specification["npm"]["cache"] for specification in (assessment or {}).get("candidates", [])
                   if npm_cache.is_npm_cache(specification)] + list(npm_caches)
    for row in report["candidates"]:
        if row.get("operation", "directory-remove") in {"directory-remove", "git-worktree-remove"} and any(
                _overlap(Path(row["path"]), Path(cache)) for cache in cache_roots):
            row.update(assessment="Keep", reason="selected npm cache state never enters directory/worktree removal")
    if cache_roots:
        report["plan"]["digest"] = digest({key: value for key, value in report["plan"].items() if key != "digest"})
    if len(npm_caches) > 8:
        raise ValueError("too many selected npm caches")
    if npm_caches:
        report["npm_caches"] = []
        for cache in npm_caches:
            if report["invalid_scope"] or report["cancelled"] or (options.get("mode") == "global" and selected.get("host_identity", report["host"]["identity"]) != report["host"]["identity"]):
                report["npm_caches"].append({"cache": cache, "coverage": "skipped", "reason": "scope/host unavailable or cancelled", "entries": []})
                continue
            if any(_overlap(Path(cache), Path(path)) for path in (*report["plan"]["policy"]["holds"], *report["plan"]["policy"]["exclusions"])):
                report["npm_caches"].append({"cache": cache, "coverage": "skipped", "reason": "held/excluded", "entries": []})
                continue
            try:
                report["npm_caches"].append(npm_cache.inventory(cache, timeout=max(0.001, deadline - time.monotonic()),
                                         max_entries=options.get("max_entries", 2000), cancelled=options.get("cancelled")))
            except npm_cache.InspectionCancelled:
                report["cancelled"] = True
                report["coverage"].update(complete=False, stop_reason="npm cache inspection cancelled")
                break
            except (ValueError, OSError, KeyError, TypeError, npm_cache.InspectionUnavailable):
                report["npm_caches"].append({"cache": cache, "coverage": "unavailable", "reason": "optional tool/cache inspection unsupported or incomplete", "entries": []})
        if any(item["coverage"] != "examined" for item in report["npm_caches"]):
            report["coverage"]["complete"] = False
    return report


def _review_docker_scope(selected, **options):
    """Version 3 adds separately typed provider rows; old producers stay intact."""
    assessment = options.get("assessment")
    if not assessment or assessment.get("schema_version") != 3:
        return _review_scope(selected, **options)
    from . import docker_cleanup
    _validate_assessment(assessment)
    started = time.monotonic()
    timeout = options.get("timeout", 10.0)
    filesystem = {**assessment, "schema_version": 2,
                  "candidates": [row for row in assessment["candidates"] if not docker_cleanup.is_docker(row)]}
    report = _review_scope(selected, **{**options, "assessment": filesystem})
    provider_ids = set()
    for specification in assessment["candidates"]:
        if not docker_cleanup.is_docker(specification):
            continue
        if time.monotonic() - started >= timeout or report["cancelled"] or report["invalid_scope"]:
            raise ValueError("Docker review budget/cancellation/scope prevents complete inspection")
        try:
            row = docker_cleanup.review(specification, assessment["references"], report["host"],
                                    report["scope"]["canonical"], timeout=timeout - (time.monotonic() - started),
                                    cancelled=options.get("cancelled"),
                                    blocked=("configured host differs; no provider inspection" if options.get("mode") == "global"
                                             and selected.get("host_identity", report["host"]["identity"]) != report["host"]["identity"]
                                             else "provider socket held/excluded" if any(_overlap(Path(specification["docker"]["endpoint"][7:]).resolve(strict=False), Path(path).resolve(strict=False))
                                                  for path in (*report["plan"]["policy"]["holds"], *report["plan"]["policy"]["exclusions"])) else None))
        except docker_cleanup.InspectionCancelled:
            report["cancelled"] = True
            report["coverage"].update(complete=False, stop_reason="Docker review cancelled; remaining provider state unknown")
            break
        if row["id"] in provider_ids:
            raise ValueError("duplicate Docker resource")
        provider_ids.add(row["id"])
        report["candidates"].append(row)
    old = report["plan"]
    report["limitations"] = ["Provider stores stay outside generic directory cleanup; explicitly assessed Docker resources use native lifecycle. Package storage remains metadata-only."
                             if item.startswith("Provider storage is report-only") else item for item in report["limitations"]]
    freeze_review(report, assessment, options.get("manifest"), old["policy"]["holds"],
                  old["policy"]["exclusions"], old["policy"]["limits"])
    return report


def _review_scope(selected, *, mode="task", assessment=None, manifest=None, holds=(), exclusions=(),
                 max_entries=2000, max_depth=12, timeout=10.0, max_content_bytes=256 * 1024 * 1024, cancelled=None,
                 evidence_warn_bytes=EVIDENCE_WARN_BYTES, evidence_explain_bytes=EVIDENCE_EXPLAIN_BYTES):
    validate_evidence_thresholds(evidence_warn_bytes, evidence_explain_bytes)
    if mode == "global":
        from .global_inventory import review_global
        return review_global(selected, assessment=assessment, manifest=manifest, holds=holds, exclusions=exclusions,
                             max_entries=max_entries, max_depth=max_depth, timeout=timeout,
                             max_content_bytes=max_content_bytes, cancelled=cancelled,
                             evidence_warn_bytes=evidence_warn_bytes, evidence_explain_bytes=evidence_explain_bytes)
    if mode not in {"task", "project"}:
        raise ValueError("unsupported review mode")
    started = time.monotonic()
    holds = [str(Path(value).resolve(strict=False)) for value in holds]
    exclusions = [str(Path(value).resolve(strict=False)) for value in exclusions]
    limits = {"max_entries": max_entries, "max_depth": max_depth}

    def remaining():
        return max(0.000001, timeout - (time.monotonic() - started))

    _validate_assessment(assessment or {"schema_version": 1, "references": {}, "candidates": []})
    report = review_task(selected, timeout=remaining(), exclusions=exclusions, cancelled=cancelled, **limits)
    report["scope"]["mode"] = mode
    report["candidates"] = []
    roots = [Path(report["scope"]["canonical"] or os.path.abspath(selected))]
    report["scope_roots"] = [str(roots[0])]
    report["linked_reviews"] = []
    if mode == "project" and not report["invalid_scope"] and not report["cancelled"]:
        report["git"] = inventory_git(selected, timeout=remaining(), cancelled=cancelled)
        report["cancelled"] = report["git"]["cancelled"]
        if report["cancelled"]:
            report["coverage"]["complete"] = False
            report["coverage"]["stop_reason"] = "Git inspection cancelled"
        metadata_remaining = max_entries - report["coverage"]["examined"]
        for worktree in report["git"]["worktrees"]:
            path = Path(worktree["path"])
            if path not in roots and worktree["status_complete"]:
                if metadata_remaining <= 0:
                    report["coverage"]["complete"] = False
                    report["warnings"].append("Linked metadata entry limit; remaining worktrees unexamined.")
                    break
                linked = review_task(path, timeout=remaining(), exclusions=exclusions, cancelled=cancelled,
                                     max_entries=metadata_remaining, max_depth=max_depth)
                metadata_remaining -= linked["coverage"]["examined"]
                report["linked_reviews"].append(linked)
                if linked["cancelled"]:
                    report["cancelled"] = True
                    report["coverage"]["complete"] = False
                    break
                if not linked["invalid_scope"]:
                    roots.append(path)
        report["scope_roots"] = [str(root) for root in roots]
    assessment = assessment or {"schema_version": 1, "references": {}, "candidates": []}
    specifications = assessment["candidates"]
    historical = {str(Path(resource["path"]).resolve(strict=False)): resource
                  for resource in validate_manifest(manifest)["resources"]} if manifest else {}
    seen = set()
    content_entries_remaining, content_bytes_remaining = max_entries, max_content_bytes
    content_bytes_read = 0
    for specification in specifications:
        if report["cancelled"]:
            break
        if set(specification) - {"path", "category", "purpose", "content", "recovery", "consumers", "consumer_scope", "release", "findings", "observed_tree_digest", "operation", "worktree"}:
            raise ValueError("unsupported candidate assertion/status/approval field")
        path = Path(os.path.abspath(roots[0] / specification["path"]))
        if str(path) in seen:
            raise ValueError("duplicate assessed target")
        seen.add(str(path))
        row = {"id": hashlib.sha256(os.fsencode(path)).hexdigest()[:16], "path": str(path), "host": report["host"],
               "category": specification.get("category", "unknown"), "project": str(roots[0]),
               "purpose": specification.get("purpose"), "assessment": "Review", "reason": "not assessed",
               "effect": "report only; no removal authorized", "references": {}, "comparison": None,
               "preconditions": ["same host/target/content/evidence/consumer/release conditions", "new plan on material drift", "separate exact-plan human confirmation"]}
        typed = assessment["schema_version"] == 2
        native = typed and specification["operation"] == "git-worktree-remove"
        if typed:
            row["operation"] = specification["operation"]
        if native:
            row["id"] = digest({"operation": row["operation"], "path": str(path)})[:16]
        report["candidates"].append(row)
        if (not any(_inside(path, root) for root in roots) or (not native and any(_same_path(path, root) for root in roots)) or _same_path(path, Path.home())
                or os.path.ismount(path) or any(_overlap(path, Path(os.path.abspath(value))) for value in (*holds, *exclusions))):
            row.update(assessment="Keep", reason="protected root/ancestor, hold, exclusion or outside selected scope")
            continue
        native_state = None
        if native:
            from . import git_worktree
            operation = specification["worktree"]
            try:
                if operation["lifecycle"] != "git":
                    raise ValueError("owning Codex/unknown lifecycle and resume interface unavailable")
                native_state = git_worktree.inspect(operation["repository"], str(path), operation["retained_ref"], timeout=remaining(), cancelled=cancelled)
                row["native"] = native_state
            except (ValueError, OSError) as error:
                row.update(assessment="Unavailable", reason=str(error))
                continue
        if content_bytes_remaining <= 0 or content_entries_remaining <= 0:
            row.update(assessment="Unavailable", reason="global/candidate content inspection budget exhausted; remaining contents unknown")
            report["coverage"]["complete"] = False
            continue
        snapshot = review_task(path, inspect_content=True, max_content_bytes=content_bytes_remaining, timeout=remaining(),
                               exclusions=exclusions, cancelled=cancelled, max_entries=content_entries_remaining, max_depth=max_depth,
                               worktree_marker=native_state["marker_identity"] if native_state else None)
        content_entries_remaining -= snapshot["coverage"]["examined"]
        content_bytes_read += snapshot["content"]["read_bytes"]
        content_bytes_remaining = max(0, content_bytes_remaining - snapshot["content"]["read_bytes"])
        if not snapshot["content"]["complete"]:
            report["coverage"]["complete"] = False
        actual_entries = _entries(snapshot)
        row["observation"] = {"complete": snapshot.get("content", {}).get("complete", False),
                              "identity": snapshot.get("identity"), "tree_digest": digest(actual_entries),
                              "tree_identity_digest": tree_identity_digest(snapshot),
                              "file_count": sum(entry["kind"] == "file" for entry in actual_entries),
                              "filesystem_local": snapshot.get("filesystem_local", False),
                              "size": snapshot["size"], "coverage": snapshot["coverage"]}
        if snapshot["invalid_scope"]:
            row.update(assessment="Unavailable", reason="target missing or unsupported")
            continue
        if specification.get("observed_tree_digest", row["observation"]["tree_digest"]) != row["observation"]["tree_digest"]:
            row.update(assessment="Review", reason="previous observed target contents changed")
            continue
        if snapshot["cancelled"]:
            report["cancelled"] = True
            row.update(assessment="Unavailable", reason="content inspection cancelled; remaining assessment unknown")
            break
        try:
            _assess(row, specification, assessment["references"], snapshot, historical.get(str(path), {}), started + timeout)
        except KeyboardInterrupt:
            report["cancelled"] = True
            report["coverage"]["complete"] = False
            row.update(assessment="Unavailable", reason="reference inspection cancelled; remaining assessment unknown")
            break
    # Discovery rows remain useful without model/context inputs; metadata never grants eligibility.
    for scope_report in [report, *report["linked_reviews"]]:
        for entry in scope_report["entries"]:
            if entry["kind"] != "directory":
                continue
            path = str(Path(scope_report["scope"]["canonical"]) / entry["path"])
            if path not in seen:
                report["candidates"].append({"id": hashlib.sha256(os.fsencode(path)).hexdigest()[:16], "path": path,
                    "host": report["host"], "category": "unknown", "project": str(roots[0]), "purpose": None,
                    "assessment": entry["assessment"], "reason": entry["reason"], "effect": "report only; no removal authorized"})
                seen.add(path)
    # A parent contains its child's retained state; a descendant inherits known
    # obligations of its parent. An exact-key lookup must not lose these facts.
    for row in report["candidates"]:
        if row["assessment"] != "Eligible":
            continue
        target = Path(row["path"])
        related = [specification for specification in specifications
                   if _overlap(target, Path(os.path.abspath(roots[0] / specification["path"])))]
        records = [resource for path, resource in historical.items() if _overlap(target, Path(path))]
        if (any(specification.get("findings") or any(consumer["state"] == "active"
                for consumer in specification.get("consumers", [])) for specification in related)
                or any(resource["retention"] for resource in records)):
            row.update(assessment="Keep", reason="known retained/required/active resource overlaps this target")
        else:
            released = {consumer["id"] for consumer in row["agent_assessment"]["consumers"]
                        if consumer["state"] == "released"}
            known = {consumer for resource in records for consumer in resource["consumers"]}
            if (not known <= released or any(specification.get("consumer_scope", {}).get("unresolved")
                    or any(consumer["state"] == "unknown" for consumer in specification.get("consumers", []))
                    for specification in related)):
                row.update(assessment="Review", reason="consumer obligations on an overlapping resource remain unresolved")
    report["content"] = {"read_bytes": content_bytes_read, "examined": max_entries - content_entries_remaining}
    record_evidence_guidance(report, [report, *report["linked_reviews"]], evidence_warn_bytes, evidence_explain_bytes)
    freeze_review(report, assessment, manifest, holds, exclusions, {**limits, "timeout_seconds": timeout, "max_content_bytes": max_content_bytes})
    return report


def freeze_review(report, assessment, manifest, holds, exclusions, limits):
    """Freeze the shared review contract; this never grants authorization."""
    eligible = [row for row in report["candidates"] if row["assessment"] == "Eligible"]
    for row in eligible:
        if any(other is not row and _overlap(Path(row["path"]), Path(other["path"])) for other in eligible):
            row.update(assessment="Review", reason="overlapping eligible targets; require a narrower plan")
        elif any(other is not row and _evidence_conflict(row, other) for other in eligible):
            row.update(assessment="Review", reason="eligible targets contain another candidate's evidence or rebuild inputs; require a narrower plan")
    report["limitations"][0] = "Discovery is metadata-only; separately assessed candidates include explicit bounded content comparison and agent interpretation."
    report["limitations"] = ["Reports contain metadata/digests, never inspected file payloads; inspect before sharing."
                             if item.startswith("Reports contain host and selected/relative path metadata;") else item
                             for item in report["limitations"]]
    limitation = "Assessed eligibility includes agent interpretation, not semantic certification by this helper. Frozen review data is not authorization; apply requires fresh interactive confirmation and revalidation."
    if limitation not in report["limitations"]:
        report["limitations"].append(limitation)
    plan = {"schema_version": assessment["schema_version"] if assessment else 1, "kind": "frozen-review-not-authorization", "host": report["host"],
            "scope_roots": report["scope_roots"], "candidates": report["candidates"],
            "assessment_digest": digest(assessment), "manifest_digest": digest(manifest),
            "policy": {"holds": [os.path.abspath(value) for value in holds],
                       "exclusions": [os.path.abspath(value) for value in exclusions],
                       "limits": limits}}
    plan["review_context"] = {"mode": report["scope"]["mode"], "selected": report["scope"]["selected"]}
    plan["scope_identities"] = {}
    for root in plan["scope_roots"]:
        try:
            metadata = os.lstat(root)
            plan["scope_identities"][root] = {key: file_identity(metadata)[key] for key in ("device", "inode", "mode")}
        except OSError:
            plan["scope_identities"][root] = None
    if plan["schema_version"] in (2, 3, 4):
        for row in plan["candidates"]:
            row.setdefault("operation", "directory-remove")
    plan["digest"] = digest(plan)
    report["plan"] = plan
    return report


def validate_selection(plan, selected_ids, *, host=None):
    """Validate frozen selection data only; any cleanup executor must independently revalidate current state."""
    payload = {key: value for key, value in plan.items() if key != "digest"}
    if (plan.get("digest") != digest(payload) or plan.get("kind") != "frozen-review-not-authorization"
            or type(plan.get("schema_version")) is not int or plan.get("schema_version") not in (1, 2, 3, 4)):
        raise ValueError("changed or unsupported frozen plan")
    if plan["host"] != (host or new_report("", None, {})["host"]):
        raise ValueError("execution host differs")
    if plan["schema_version"] in (2, 3, 4):
        from .docker_cleanup import OPERATIONS
        from .npm_cache import OPERATION
        allowed = {"id", "path", "host", "category", "project", "purpose", "assessment", "reason", "effect",
                   "references", "comparison", "preconditions", "operation", "native", "observation",
                   "assessment_basis", "specification_digest", "agent_assessment"}
        for row in plan["candidates"]:
            operations = {"directory-remove", "git-worktree-remove"} | (OPERATIONS if plan["schema_version"] in (3, 4) else set()) | ({OPERATION} if plan["schema_version"] == 4 else set())
            if set(row) - allowed or row.get("operation") not in operations:
                raise ValueError("unknown frozen resource fields/operation")
            if row["operation"] == "directory-remove" and "native" in row:
                raise ValueError("directory cannot carry native identity")
    rows = {row["id"]: row for row in plan["candidates"]}
    if len(rows) != len(plan["candidates"]) or not selected_ids or len(set(selected_ids)) != len(selected_ids):
        raise ValueError("invalid selection IDs")
    selected = []
    for identifier in selected_ids:
        row = rows.get(identifier)
        if row is None or row["assessment"] != "Eligible" or not row.get("observation", {}).get("complete"):
            raise ValueError("unknown or ineligible selection")
        from .docker_cleanup import is_docker, EFFECTS
        from .npm_cache import is_npm_cache
        if plan["schema_version"] == 4 and is_npm_cache(row):
            selected.append(row)
            continue
        if plan["schema_version"] in (3, 4) and is_docker(row):
            if row["effect"] != EFFECTS[row["operation"]] or row["host"] != plan["host"]:
                raise ValueError("unsupported Docker effect/host")
            selected.append(row)
            continue
        native = plan["schema_version"] in (2, 3, 4) and row.get("operation") == "git-worktree-remove"
        if plan["schema_version"] in (2, 3, 4) and row.get("operation") not in {"directory-remove", "git-worktree-remove"}:
            raise ValueError("unknown typed operation")
        path = Path(row["path"])
        if (str(path) != os.path.abspath(path) or not any(_inside(path, Path(root)) for root in plan["scope_roots"])
                or (not native and any(_same_path(path, Path(root)) for root in plan["scope_roots"]))
                or _same_path(path, Path.home()) or os.path.ismount(path)
                or any(protection(part)[1] for part in path.parts)):
            raise ValueError("protected or uncontained target")
        from .git_worktree import EFFECT
        valid_effect = row["effect"] == EFFECT if native else row["effect"].startswith("permanent removal of this exact directory;")
        if not valid_effect or row["host"] != plan["host"]:
            raise ValueError("unsupported effect/host")
        if any(not is_docker(other) and not is_npm_cache(other) and _overlap(path, Path(other["path"])) for other in selected):
            raise ValueError("overlapping selected targets")
        if _evidence_conflict(row, row) or any(_evidence_conflict(row, other) for other in selected):
            raise ValueError("selected target contains another selection's evidence or rebuild inputs")
        selected.append(row)
    # Evidence/rebuild inputs for an earlier item must survive later selections.
    # Per-item reassessment alone would drop already processed obligations.
    for row in selected:
        if any(_inside(Path(reference["path"]), Path(target["path"]))
               for reference in row.get("references", {}).values() for target in selected if not is_docker(target) and not is_npm_cache(target)):
            raise ValueError("selected batch contains required evidence/rebuild inputs")
    if plan["schema_version"] in (2, 3, 4):
        context = plan["review_context"]
        if context["mode"] in {"task", "project"} and any(
                _inside(Path(context["selected"]), Path(target["path"])) for target in selected if not is_docker(target) and not is_npm_cache(target)):
            raise ValueError("selected target contains required review context; review from a retained repository checkout")
        for row in plan["candidates"]:
            if row.get("operation") == "git-worktree-remove" and "native" in row:
                if any(_inside(Path(row["native"][key]), Path(target["path"]))
                       for key in ("repository", "common_directory", "administration") for target in selected if not is_docker(target) and not is_npm_cache(target)):
                    raise ValueError("selected batch contains required native repository/recovery state")
    if plan["schema_version"] in (3, 4):
        from .docker_cleanup import validate_batch
        validate_batch(plan, selected)
    if plan["schema_version"] == 4:
        from .npm_cache import validate_batch
        validate_batch(plan, selected)
    return selected


def _write_exclusive(destination, value, protected):
    destination = Path(os.path.abspath(destination))
    if any(_inside(destination, Path(root)) for root in protected) or any(protection(part)[1] for part in destination.parts):
        raise ValueError("output must be outside resource/protected targets")
    data = canonical_json(value) + b"\n"
    if len(data) > DOCUMENT_LIMIT:
        raise ValueError("output document limit; narrow review")
    parent = _open_parent(destination)
    try:
        descriptor = os.open(destination.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
    finally:
        os.close(parent)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)


def write_plan(destination, plan):
    if plan.get("digest") != digest({key: value for key, value in plan.items() if key != "digest"}):
        raise ValueError("invalid plan digest")
    _write_exclusive(destination, plan, [row["path"] for row in plan["candidates"]] + plan["scope_roots"])


def write_manifest(destination, manifest, scope_roots=()):
    validate_manifest(manifest)
    _write_exclusive(destination, manifest,
                     [resource["path"] for resource in manifest["resources"]] + list(scope_roots))
