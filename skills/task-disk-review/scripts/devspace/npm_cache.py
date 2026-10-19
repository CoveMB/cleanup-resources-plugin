"""Optional, exact npm cache lifecycle. Shared/offline/unknown data stays protected."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from . import plans
from .git_inventory import run_readonly, InspectionUnavailable, InspectionCancelled
from .git_worktree import NativeRemovalFailed, _identity, _metadata_file
from .review import review_task


OPERATION = "npm-cache-remove"
EFFECT = "permanent native removal of this exact singleton npm cache entry; later downloads/builds may cost more and require network; no offline recovery or undo promised"
# Native API only reads the installed npm-owned index; never verify/GC/get,
# which can mutate corrupt data. Do not return response headers or payloads.
LIST_SCRIPT = """
const c = require(process.argv[1]);
const crypto = require('node:crypto');
(async () => {
  const rows = [];
  for await (const e of c.ls.stream(process.argv[2])) {
    if (rows.length >= Number(process.argv[3])) throw Error('bound');
    rows.push({key:e.key, integrity:e.integrity, size:e.size, time:e.time,
      metadata_digest:crypto.createHash('sha256').update(JSON.stringify(e.metadata ?? null)).digest('hex')});
  }
  rows.sort((a,b)=>a.key < b.key ? -1 : a.key > b.key ? 1 : 0);
  process.stdout.write(JSON.stringify(rows));
})().catch(()=>process.exit(1));
"""


def is_npm_cache(row):
    return row.get("operation") == OPERATION


def _validate_integrity(integrity):
    if not isinstance(integrity, str) or not re.fullmatch(r"sha512-[A-Za-z0-9+/]{86}==", integrity):
        raise ValueError("unsupported cache integrity; shared-content scope unknown")
    if base64.b64encode(base64.b64decode(integrity[7:], validate=True)).decode() != integrity[7:]:
        raise ValueError("noncanonical integrity")


def validate_resource(resource):
    if not isinstance(resource, dict) or set(resource) != {"cache", "key", "integrity"}:
        raise ValueError("exact npm cache/key/integrity required")
    cache, key, integrity = resource["cache"], resource["key"], resource["integrity"]
    if (not isinstance(cache, str) or not Path(cache).is_absolute() or str(Path(cache).resolve(strict=False)) != cache
            or cache in {"/", str(Path.home())} or any(plans.protection(part)[1] for part in Path(cache).parts)):
        raise ValueError("canonical explicit local npm cache required")
    if not isinstance(key, str) or not key or len(key) > 4096 or any(ord(char) < 32 for char in key):
        raise ValueError("bounded exact cache key required")
    _validate_integrity(integrity)


def effect_paths(resource):
    """Exact native body removal and index append, not the whole cache root."""
    hexadecimal = base64.b64decode(resource["integrity"][7:]).hex()
    key_hash = hashlib.sha256(resource["key"].encode()).hexdigest()
    store = Path(resource["cache"]) / "_cacache"
    return (store / "content-v2/sha512" / hexadecimal[:2] / hexadecimal[2:4] / hexadecimal[4:],
            store / "index-v5" / key_hash[:2] / key_hash[2:4] / key_hash[4:])


def overlap_protection(specification, assessment, roots, manifest):
    """Reuse physical containment for all known affected-path obligations."""
    effects = effect_paths(specification["npm"])
    related = []
    for other in assessment["candidates"]:
        if "path" not in other:
            continue
        path = Path(other["path"])
        if not path.is_absolute():
            path = Path(roots[0]) / path
        if any(plans._overlap(Path(os.path.abspath(path)), effect) for effect in effects):
            related.append(other)
    historical = [record for record in (manifest or {}).get("resources", [])
                  if any(plans._overlap(Path(record["path"]), effect) for effect in effects)]
    if (any(other.get("findings") or any(consumer["state"] == "active" for consumer in other.get("consumers", []))
            for other in related) or any(record["retention"] for record in historical)):
        return "Keep", "known active/protected/retained resource overlaps native cache effects"
    if any(other.get("consumer_scope", {}).get("unresolved") or any(consumer["state"] == "unknown" for consumer in other.get("consumers", []))
           for other in related):
        return "Review", "consumer obligations overlapping native cache effects remain unresolved"
    known = {consumer["id"] for other in related for consumer in other.get("consumers", [])}
    known.update(consumer for record in historical for consumer in record["consumers"])
    released = {consumer["id"] for consumer in specification.get("consumers", []) if consumer["state"] == "released"}
    if not known <= released:
        return "Review", "additional historical/overlapping cache consumers need evidence-backed resolution"
    return None


def validate_assessment(assessment):
    if set(assessment) != {"schema_version", "references", "candidates"} or not isinstance(assessment["candidates"], list):
        raise ValueError("unsupported version 4 assessment")
    if len(assessment["candidates"]) > plans.MAX_CANDIDATES:
        raise ValueError("candidate limit")
    other, seen = [], set()
    for specification in assessment["candidates"]:
        if not isinstance(specification, dict):
            raise ValueError("candidate must be an object")
        if not is_npm_cache(specification):
            other.append(specification)
            continue
        validate_resource(specification.get("npm"))
        resource = specification["npm"]
        identity = _identity(resource["cache"])
        selection = (identity["device"], identity["inode"], resource["key"])
        if selection in seen:
            raise ValueError("duplicate/aliased npm entry; consolidate all consumer obligations")
        seen.add(selection)
        if "path" in specification:
            raise ValueError("npm keys are not directory paths")
        candidate = {key: value for key, value in specification.items() if key not in {"npm", "operation"}}
        candidate["path"] = "/native-npm-evidence"
        plans._validate_assessment({"schema_version": 1, "references": assessment["references"], "candidates": [candidate]})
    from .docker_cleanup import validate_assessment as validate_docker
    validate_docker({**assessment, "schema_version": 3, "candidates": other})


def _environment():
    # No NODE_OPTIONS, NODE_PATH, npm_config_*, auth, proxy or project overrides.
    return {"PATH": os.defpath, "HOME": "/", "LC_ALL": "C"}


def _tools(deadline, cancelled=None):
    environment = _environment()
    paths = {}
    for name in ("npm", "node"):
        path = shutil.which(name)
        if not path:
            raise ValueError("optional npm/Node unavailable")
        if Path(path).resolve(strict=True).name == "volta-shim":
            volta = shutil.which("volta")
            if not volta:
                raise ValueError("native shim resolution unavailable")
            # Preserve only Volta's own installation selector, never Node/npm
            # options or user/project configuration; execute outside projects.
            discovery = {**environment, "HOME": str(Path.home())}
            path = os.fsdecode(run_readonly([volta, "which", name], "/", discovery, deadline, cancelled)).strip()
        paths[name] = str(Path(path).resolve(strict=True))
    root = Path(paths["npm"]).parent.parent
    if Path(paths["npm"]).name != "npm-cli.js":
        raise ValueError("unsupported installed npm executable layout")
    cacache = root / "node_modules/cacache"
    files = ("package.json", "npmrc", "bin/npm-cli.js", "lib/commands/cache.js",
             "node_modules/cacache/package.json", "node_modules/cacache/lib/index.js",
             "node_modules/cacache/lib/entry-index.js", "node_modules/cacache/lib/content/path.js",
             "node_modules/cacache/lib/content/rm.js", "node_modules/cacache/lib/get.js", "node_modules/cacache/lib/rm.js")
    identities = {}
    versions = []
    for relative in files:
        if relative == "npmrc" and not (root / relative).exists():
            identities[relative] = None
            continue
        payload, identity = _metadata_file(root / relative, limit=plans.DOCUMENT_LIMIT)
        identities[relative] = {"identity": identity, "sha256": hashlib.sha256(payload).hexdigest()}
        if relative.endswith("package.json"):
            versions.append(json.loads(payload)["version"])
    if versions != ["11.17.0", "20.0.4"]:
        raise ValueError("npm/cacache version has no verified native cleanup contract")
    return {"node": paths["node"], "node_identity": _identity(paths["node"], directory=False),
            "npm": paths["npm"], "root": str(root), "root_identity": _identity(root),
            "cacache": str(cacache), "files": identities, "versions": versions,
            "configuration": "global mode; user/global config disabled; inherited Node/npm environment stripped; offline; no logs/update notifier"}


def _check_index(path):
    # cacache intentionally ignores corrupt index lines. Unknown lines must
    # instead protect possible aliases before a destructive exact-key command.
    payload, _ = _metadata_file(path, limit=plans.DOCUMENT_LIMIT)
    # cacache appends a leading newline, and does not require a trailing one.
    for line in payload.split(b"\n"):
        if not line:
            continue
        checksum, separator, encoded = line.partition(b"\t")
        if not separator or hashlib.sha1(encoded).hexdigest().encode() != checksum:
            raise ValueError("unknown/corrupt cache index state")
        record = json.loads(encoded, object_pairs_hook=plans._unique_keys)
        if (not isinstance(record, dict) or set(record) - {"key", "integrity", "time", "size", "metadata"}
                or not isinstance(record.get("key"), str) or not record["key"]
                or record.get("integrity") is not None and not isinstance(record["integrity"], str)):
            raise ValueError("unsupported cache index state")


def _records(tools, cache, deadline, maximum, cancelled):
    payload = run_readonly([tools["node"], "-e", LIST_SCRIPT, tools["cacache"], str(Path(cache) / "_cacache"), str(maximum)],
                           "/", _environment(), deadline, cancelled)
    rows = json.loads(payload, object_pairs_hook=plans._unique_keys)
    if not isinstance(rows, list) or len(rows) > maximum:
        raise ValueError("incomplete native cache inventory")
    seen = set()
    for row in rows:
        if (set(row) != {"key", "integrity", "size", "time", "metadata_digest"}
                or not isinstance(row["key"], str) or row["key"] in seen
                or not isinstance(row["integrity"], str) or type(row["size"]) is not int or row["size"] < 0
                or type(row["time"]) is not int or not isinstance(row["metadata_digest"], str)):
            raise ValueError("unsupported native index record")
        seen.add(row["key"])
        # Alternate SRI spellings can point at the same backing file. Without
        # a verified native equivalence contract, protect the entire cache.
        _validate_integrity(row["integrity"])
    return rows


def _inspect_cache(cache, *, timeout, max_entries=2000, cancelled=None):
    cache = str(Path(cache))
    # Validate the root even for discovery, without inventing a real selection.
    validate_resource({"cache": cache, "key": "discovery", "integrity": "sha512-" + base64.b64encode(bytes(64)).decode()})
    deadline = time.monotonic() + timeout
    identity = _identity(cache)
    tools = _tools(deadline, cancelled)
    store = Path(cache) / "_cacache"
    store_identity = _identity(store)
    snapshot = review_task(store, max_entries=max_entries, timeout=max(0.001, deadline - time.monotonic()),
                           max_depth=8, cancelled=cancelled)
    if snapshot["cancelled"]:
        raise InspectionCancelled("cache inspection cancelled")
    if (not snapshot["coverage"]["complete"] or not snapshot["filesystem_local"]
            or any(entry["kind"] not in {"file", "directory"} or entry.get("assessment") == "Keep"
                   for entry in snapshot["entries"])):
        raise ValueError("cache layout unknown/linked/protected/nonlocal/incomplete")
    for entry in snapshot["entries"]:
        if time.monotonic() >= deadline:
            raise InspectionUnavailable("cache inspection budget exceeded")
        if cancelled is not None and cancelled():
            raise InspectionCancelled("cache inspection cancelled")
        observed = _identity(store / entry["path"], directory=entry["kind"] == "directory")
        if observed["device"] != identity["device"]:
            raise ValueError("cache crosses a filesystem boundary")
        if entry["kind"] == "file":
            path = store / entry["path"]
            if path.stat(follow_symlinks=False).st_nlink != 1:
                raise ValueError("shared filesystem content is protected")
            if entry["path"].startswith("index-v5/"):
                _check_index(path)
        if entry["path"].startswith("tmp/"):
            raise ValueError("cache has temporary/in-progress content")
    records = _records(tools, cache, deadline, max_entries, cancelled)
    return {"cache": cache, "cache_identity": identity, "store_identity": store_identity, "max_entries": max_entries,
            "tools": tools, "records": records}, deadline


def inventory(cache, *, timeout=10, max_entries=2000, cancelled=None):
    native, _ = _inspect_cache(cache, timeout=timeout, max_entries=max_entries, cancelled=cancelled)
    rows, groups = [], {}
    for record in native["records"]:
        groups.setdefault(record["integrity"], []).append(record["key"])
    for record in native["records"]:
        aliases = groups[record["integrity"]]
        rows.append({"key": record["key"], "integrity": record["integrity"], "logical_bytes": record["size"],
                     "aliases": aliases, "assessment": "Keep" if len(aliases) > 1 else "Review",
                     "reason": "shared backing content; exact-key clean affects aliases" if len(aliases) > 1 else "singleton content; purpose/use/release/offline recovery not assessed",
                     "consequences": "later download/build cost; network may be required; offline-only content must be kept"})
    rows.sort(key=lambda row: (-row["logical_bytes"], row["key"]))
    return {"cache": cache, "coverage": "examined", "entries": rows,
            "unique_content_bytes": sum(next(row["size"] for row in native["records"] if row["integrity"] == integrity) for integrity in groups),
            "accounting": "unique indexed logical content only; not allocated/reclaimable bytes; do not add to filesystem totals"}


def inspect(resource, *, timeout=10, max_entries=2000, max_content_bytes=256 * 1024 * 1024, cancelled=None):
    validate_resource(resource)
    native, deadline = _inspect_cache(resource["cache"], timeout=timeout, max_entries=max_entries, cancelled=cancelled)
    record = [row for row in native["records"] if row["key"] == resource["key"]]
    aliases = [row["key"] for row in native["records"] if row["integrity"] == resource["integrity"]]
    if len(record) != 1 or record[0]["integrity"] != resource["integrity"] or aliases != [resource["key"]]:
        raise ValueError("modified/missing/shared content; preserve all aliases")
    path, _ = effect_paths(resource)
    payload, identity = plans._read_file(path, limit=max_content_bytes, deadline=deadline)
    if (hashlib.sha512(payload).digest() != base64.b64decode(resource["integrity"][7:])
            or len(payload) != record[0]["size"] or path.stat(follow_symlinks=False).st_nlink != 1):
        raise ValueError("cache content modified/unknown/shared")
    if _records(native["tools"], resource["cache"], deadline, max_entries, cancelled) != native["records"]:
        raise ValueError("cache changed during inspection")
    native.update(resource=resource, content_identity=identity, content_sha256=hashlib.sha256(payload).hexdigest(),
                  size={"logical_bytes": len(payload), "allocated_bytes": path.stat(follow_symlinks=False).st_blocks * 512})
    return native


def identifier(resource):
    return plans.digest({"operation": OPERATION, **resource})[:16]


def review(specification, references, host, project, *, timeout, max_entries=2000, max_content_bytes=256 * 1024 * 1024, cancelled=None, blocked=None):
    resource = specification["npm"]
    row = {"id": identifier(resource), "path": OPERATION + ":" + resource["key"], "operation": OPERATION,
           "host": host, "project": project, "category": "cache", "purpose": specification.get("purpose"),
           "assessment": "Review", "reason": "npm cache evidence unresolved", "effect": "report only; no removal authorized",
           "references": {}, "comparison": None, "specification_digest": plans.digest(specification),
           "preconditions": ["same local cache/Node/npm/configuration/index/content/evidence/consumers",
                             "no shared aliases or offline-only content; exact terminal confirmation; new plan on drift"]}
    if blocked or specification.get("findings") or any(item["state"] == "active" for item in specification.get("consumers", [])):
        row.update(assessment="Keep", reason=blocked or "protective finding or active consumer")
        return row
    try:
        native = inspect(resource, timeout=timeout, max_entries=max_entries, max_content_bytes=max_content_bytes, cancelled=cancelled)
        row.update(native=native, observation={"complete": True, "identity": plans.digest(native), "size": native["size"]})
    except InspectionCancelled:
        raise
    except (ValueError, OSError, KeyError, TypeError, InspectionUnavailable):
        row.update(assessment="Unavailable", reason="npm inspection unsupported/incomplete or shared/modified content protected")
        return row
    deadline = time.monotonic() + timeout
    def reference(key):
        payload, checked = plans._reference(key, references, Path(resource["cache"]), [native["content_identity"]], deadline)
        row["references"][key] = checked
        return payload
    try:
        for key in ("content", "recovery", "consumer_scope", "release"):
            if not specification.get(key, {}).get("basis"):
                raise ValueError("missing ordinary contextual evidence")
            for source in specification[key]["basis"]:
                reference(source)
        content = specification["content"]
        payload = reference(content["reference"])
        if content.get("method") == "source-file":
            if hashlib.sha256(payload).hexdigest() != native["content_sha256"]:
                raise ValueError("independent selected-content comparison modified")
        elif content.get("method") == "npm-lock":
            # Existing trusted lockfile evidence supplies the expected native
            # integrity. No compulsory download or duplicate installed tree.
            lock = json.loads(payload, object_pairs_hook=plans._unique_keys)
            if type(lock.get("lockfileVersion")) is not int or lock["lockfileVersion"] not in (2, 3) or not isinstance(lock.get("packages"), dict):
                raise ValueError("supported independent npm lockfile required")
            matched = [package for package in lock["packages"].values() if isinstance(package, dict)
                       and "make-fetch-happen:request-cache:" + str(package.get("resolved", "")) == resource["key"]]
            if not matched or any(package.get("integrity") != resource["integrity"] for package in matched):
                raise ValueError("lockfile does not independently bind this exact URL/key and content")
        else:
            raise ValueError("independent selected-content comparison missing")
        recovery = specification["recovery"]
        if (recovery.get("kind") not in {"rebuild", "accepted-loss"} or not recovery.get("explanation")
                or recovery["kind"] == "rebuild" and not recovery.get("inputs")
                or specification["consumer_scope"].get("unresolved", ["unknown"])
                or not specification.get("purpose") or not specification["release"].get("checkpoint")):
            raise ValueError("purpose/use/release/recovery unresolved")
        for source in recovery.get("inputs", []):
            reference(source)
        for consumer in specification.get("consumers", []):
            if consumer["state"] != "released" or not consumer.get("basis"):
                raise ValueError("unresolved consumer")
            for source in consumer["basis"]:
                reference(source)
        row.update(assessment="Eligible", reason="singleton native entry, independent content comparison and evidence-backed use/release/recovery",
                   effect=EFFECT, comparison={"method": content["method"], "matched": True}, assessment_basis=plans.ASSESSMENT_BASIS)
    except (ValueError, OSError, KeyError, TypeError, UnicodeError):
        pass
    return row


def revalidate(row, specification, references, completed, limits):
    current = review(specification, references, row["host"], row["project"], timeout=limits["timeout_seconds"],
                     max_entries=limits["max_entries"], max_content_bytes=limits["max_content_bytes"])
    removed = {item["native"]["resource"]["key"] for item in completed if is_npm_cache(item)
               and item["native"]["cache_identity"] == row["native"]["cache_identity"]}
    expected = {**row, "native": {**row["native"], "records": [record for record in row["native"]["records"] if record["key"] not in removed]}}
    expected["observation"] = {**row["observation"], "identity": plans.digest(expected["native"])}
    if current != expected:
        raise ValueError("npm cache/tool/configuration/index/content/evidence drift")
    return current


def validate_batch(plan, selected):
    from .docker_cleanup import is_docker
    for row in selected:
        if not is_npm_cache(row):
            continue
        native, resource = row["native"], row["native"]["resource"]
        validate_resource(resource)
        if (row["id"] != identifier(resource) or row["observation"]["identity"] != plans.digest(native)
                or row["effect"] != EFFECT or row["host"] != plan["host"]):
            raise ValueError("changed native npm selection")
        protected = [resource["cache"], native["tools"]["root"], native["tools"]["node"]]
        if any(plans._overlap(Path(resource["cache"]), Path(path)) for path in (*plan["policy"]["holds"], *plan["policy"]["exclusions"])):
            raise ValueError("npm cache held/excluded")
        for target in selected:
            if not is_npm_cache(target) and not is_docker(target) and any(plans._overlap(Path(path), Path(target["path"])) for path in protected):
                raise ValueError("selected directory overlaps required npm cache/tool state")


def remove(row, limits):
    native = row["native"]
    resource = native["resource"]
    from .cleanup import _supported_filesystem
    descriptor = plans._open_parent(Path(resource["cache"]) / "_cacache")
    try:
        _supported_filesystem(descriptor)
    finally:
        os.close(descriptor)
    if inspect(resource, timeout=limits["timeout_seconds"], max_entries=limits["max_entries"], max_content_bytes=limits["max_content_bytes"]) != native:
        raise ValueError("npm cache changed immediately before removal")
    tools = native["tools"]
    # npm refuses loading the same configuration filename twice. fd 0 is
    # independently opened DEVNULL below, so both distinct sources are empty.
    command = [tools["node"], tools["npm"], "--global", "--userconfig=/dev/null", "--globalconfig=/dev/fd/0",
               "--cache=" + resource["cache"], "--logs-max=0", "--loglevel=silent", "--offline", "--ignore-scripts",
               "--update-notifier=false", "cache", "clean", "--", resource["key"]]
    try:
        result = subprocess.run(command, cwd="/", env=_environment(), stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=limits["timeout_seconds"])
    except subprocess.TimeoutExpired:
        raise NativeRemovalFailed("native-timeout-outcome-unknown") from None
    except OSError:
        raise NativeRemovalFailed("native-unavailable-outcome-unknown") from None
    if result.returncode:
        raise NativeRemovalFailed("native-refusal", result.returncode)
    if observe(row, timeout=limits["timeout_seconds"]) != "absent-cache-entry-and-content":
        raise NativeRemovalFailed("native-success-effect-unverified")


def observe(row, *, timeout=10):
    """Observation only; never retry native deletion or garbage collection."""
    try:
        native = row["native"]
        resource = native["resource"]
        validate_resource(resource)
        current, _ = _inspect_cache(resource["cache"], timeout=timeout, max_entries=native["max_entries"])
        if any(current[key] != native[key] for key in ("tools", "cache_identity", "store_identity")):
            return "unknown-cache-identity"
        records = [record for record in current["records"] if record["key"] == resource["key"]]
        path, _ = effect_paths(resource)
        if not records and not path.exists():
            return "absent-cache-entry-and-content"
        if not records or not path.exists():
            return "partial-cache-entry-or-content"
        return "same-cache-key-contents-unverified" if records[0]["integrity"] == resource["integrity"] else "replaced-cache-key"
    except (ValueError, OSError, KeyError, TypeError, InspectionUnavailable):
        return "unknown-cache-state"
