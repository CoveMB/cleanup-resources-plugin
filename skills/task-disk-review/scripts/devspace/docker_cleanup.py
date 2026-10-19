"""Exact local Docker lifecycle; no shell, force-removal or filesystem fallback."""
import json
from decimal import Decimal
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time

from . import plans
from .git_inventory import run_readonly, InspectionUnavailable, InspectionCancelled
from .git_worktree import NativeRemovalFailed, _identity, _metadata_file


OPERATIONS = {"docker-container-remove", "docker-image-remove", "docker-cache-remove"}
EFFECTS = {
    "docker-container-remove": "permanent native removal of this exact stopped container; no volumes removed; no writable-data undo",
    "docker-image-remove": "permanent native removal of this exact unused image and its sole tag; unselected parents retained; rebuild or download required",
    "docker-cache-remove": "permanent native removal of this exact reclaimable builder-cache record; later builds may cost more; no host-space guarantee",
}


def is_docker(row):
    return row.get("operation") in OPERATIONS


def resource_identifier(resource, operation):
    return plans.digest({"operation": operation, "endpoint": resource["endpoint"],
                         "builder": resource.get("builder"), "id": resource["id"]})[:16]


def _selection_identity(resource, operation):
    # Different sockets or builder names can address the same provider. Never
    # split known consumer obligations by an alias, even for protected rows.
    return (operation, resource["id"])


def validate_resource(resource, operation):
    allowed = {"endpoint", "id", "ownership_label"} if operation != "docker-cache-remove" else {"endpoint", "id", "builder"}
    required = {"endpoint", "id"} if operation != "docker-cache-remove" else allowed
    if not isinstance(resource, dict) or set(resource) - allowed or not required <= set(resource):
        raise ValueError("unsupported Docker selection fields")
    endpoint = resource["endpoint"]
    if not isinstance(endpoint, str) or not endpoint.startswith("unix:///") or "\x00" in endpoint or len(endpoint) > 4096:
        raise ValueError("Docker requires an explicit local Unix socket")
    if endpoint != "unix://" + str(Path(endpoint[7:]).resolve(strict=False)):
        raise ValueError("Docker endpoint must use its canonical local socket spelling")
    identifier = resource["id"]
    pattern = r"[a-z0-9]{25}" if operation == "docker-cache-remove" else r"sha256:[0-9a-f]{64}" if operation == "docker-image-remove" else r"[0-9a-f]{64}"
    if not isinstance(identifier, str) or not re.fullmatch(pattern, identifier):
        raise ValueError("full exact Docker resource ID required")
    if operation == "docker-cache-remove":
        if not isinstance(resource["builder"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", resource["builder"]):
            raise ValueError("explicit named local builder required")
    elif "ownership_label" in resource:
        label = resource["ownership_label"]
        if (not isinstance(label, dict) or set(label) != {"key", "value"}
                or any(not isinstance(value, str) or not value or len(value) > 256 for value in label.values())):
            raise ValueError("explicit ownership label required, with separate provenance evidence")


def validate_assessment(assessment):
    if set(assessment) != {"schema_version", "references", "candidates"} or not isinstance(assessment["candidates"], list):
        raise ValueError("unsupported version 3 assessment")
    if len(assessment["candidates"]) > plans.MAX_CANDIDATES:
        raise ValueError("candidate limit")
    filesystem, seen = [], set()
    for specification in assessment["candidates"]:
        if not is_docker(specification):
            filesystem.append(specification)
            continue
        validate_resource(specification.get("docker"), specification["operation"])
        identifier = _selection_identity(specification["docker"], specification["operation"])
        if identifier in seen:
            raise ValueError("duplicate/aliased Docker resource; consolidate every consumer obligation")
        seen.add(identifier)
        # Reuse the established bounded evidence/consumer/release vocabulary.
        candidate = {key: value for key, value in specification.items() if key not in {"docker", "operation"}}
        candidate["path"] = "/native-docker-evidence"
        if "path" in specification:
            raise ValueError("Docker IDs are not directory paths")
        plans._validate_assessment({"schema_version": 1, "references": assessment["references"], "candidates": [candidate]})
    plans._validate_assessment({"schema_version": 2, "references": assessment["references"], "candidates": filesystem})


class LocalDocker:
    def __init__(self, endpoint, timeout=10, cancelled=None):
        self.deadline = time.monotonic() + timeout
        self.cancelled = cancelled
        if not isinstance(endpoint, str) or not endpoint.startswith("unix:///"):
            raise ValueError("remote Docker is unavailable")
        socket = Path(endpoint[7:])
        if socket.resolve(strict=True) != socket or not stat.S_ISSOCK(socket.stat().st_mode):
            raise ValueError("Docker endpoint must be a canonical local socket")
        self.endpoint = endpoint
        executable = shutil.which("docker")
        if executable is None:
            raise ValueError("Docker executable unavailable")
        self.executable = str(Path(executable).resolve(strict=True))
        self.environment = {key: value for key, value in os.environ.items()
                            if not key.startswith(("DOCKER_", "BUILDX_", "BUILDKIT_"))}
        # Use selected configuration directory but never read credentials/config.json.
        self.config = str(Path(os.environ.get("DOCKER_CONFIG", str(Path.home() / ".docker"))).resolve(strict=True))
        self.environment["DOCKER_CONFIG"] = self.config
        self.identity = {"endpoint": endpoint, "socket": {key: getattr(socket.stat(), "st_" + key) for key in ("dev", "ino", "mode")},
                         "executable": self.executable, "executable_identity": _identity(self.executable, directory=False),
                         "configuration_directory": self.config,
                         "daemon": self.json("info", "--format", '{{json .ID}}'),
                         "version": self.json("version", "--format", '{{json .Server.Version}}')}
        if not isinstance(self.identity["daemon"], str) or not self.identity["daemon"]:
            raise ValueError("daemon identity unavailable")

    def command(self, *arguments):
        return [self.executable, "--host", self.endpoint, *arguments]

    def read(self, *arguments):
        return run_readonly(self.command(*arguments), None, self.environment, self.deadline, self.cancelled)

    def json(self, *arguments):
        return json.loads(self.read(*arguments), object_pairs_hook=plans._unique_keys)

    def listed_ids(self, kind):
        arguments = ("container", "ls", "--all", "--no-trunc", "--quiet") if kind == "container" else ("image", "ls", "--all", "--no-trunc", "--quiet")
        return sorted(set(self.read(*arguments).decode().splitlines()))

    def container(self, identifier):
        records = self.json("container", "inspect", "--size", identifier)
        if len(records) != 1 or records[0]["Id"] != identifier:
            raise ValueError("container ID mismatch")
        return records[0]

    def image(self, identifier):
        records = self.json("image", "inspect", identifier)
        if len(records) != 1 or records[0]["Id"] != identifier:
            raise ValueError("image ID mismatch")
        return records[0]

    def container_dependencies(self, identifier, name):
        identifiers = [item for item in self.listed_ids("container") if item != identifier]
        if len(identifiers) > 2000:
            raise ValueError("container consumer inventory bound exceeded")
        if not identifiers:
            return []
        template = ('{"id":{{json .Id}},"network":{{json .HostConfig.NetworkMode}},'
                    '"ipc":{{json .HostConfig.IpcMode}},"pid":{{json .HostConfig.PidMode}},'
                    '"links":{{json .HostConfig.Links}},"volumes":{{json .HostConfig.VolumesFrom}}}')
        output = self.read("container", "inspect", "--format", template, *identifiers)
        records = [json.loads(line, object_pairs_hook=plans._unique_keys) for line in output.splitlines()]
        if {record["id"] for record in records} != set(identifiers):
            raise ValueError("container consumer inventory incomplete")
        def matches(value):
            value = value.lstrip("/").split(":", 1)[0]
            return bool(value) and (identifier.startswith(value) or name and value == name.lstrip("/"))
        dependents = []
        for record in records:
            modes = [record[key][10:] for key in ("network", "ipc", "pid")
                     if isinstance(record[key], str) and record[key].startswith("container:")]
            references = modes + (record["links"] or []) + (record["volumes"] or [])
            if any(matches(value) for value in references):
                dependents.append(record["id"])
        return sorted(dependents)

    def builder(self, name):
        # Inspect only the selected instance; global `buildx ls` can contact
        # unrelated remote builders. Never read Docker credentials/config.json.
        plugins = self.json("info", "--format", '{{json .ClientInfo.Plugins}}')
        plugin = [item for item in plugins if item.get("Name") == "buildx"]
        if len(plugin) != 1:
            raise ValueError("buildx executable identity unavailable")
        plugin_path = str(Path(plugin[0]["Path"]).resolve(strict=True))
        plugin_identity = _identity(plugin_path, directory=False)
        if name == "default":
            inspected = self.read("buildx", "inspect", "default").decode()
            inspected = "\n".join(line.rstrip() for line in inspected.splitlines() if not line.startswith("Last Activity:"))
            # --host plus stripped context overrides pins this dynamic Docker
            # driver to our already verified local daemon. No saved instance,
            # context switch or service bootstrap is used.
            fields = {key: re.findall(r"^" + key + r":\s+(\S+)\s*$", inspected, re.MULTILINE)
                      for key in ("Name", "Driver", "Endpoint", "Status")}
            if fields != {"Name": ["default", "default"], "Driver": ["docker"], "Endpoint": ["default"], "Status": ["running"]} or "Error:" in inspected:
                raise ValueError("default local Docker worker identity unavailable")
            return {"name": name, "driver": "docker", "daemon": self.identity["daemon"], "endpoint": self.endpoint,
                    "plugin": plugin_path, "plugin_identity": plugin_identity, "inspection_digest": plans.digest(inspected)}
        path = Path(self.config) / "buildx/instances" / name
        payload, identity = _metadata_file(path, limit=plans.DOCUMENT_LIMIT)
        configuration = json.loads(payload, object_pairs_hook=plans._unique_keys)
        nodes = configuration["Nodes"]
        if (configuration["Name"] != name or configuration["Driver"] != "docker-container" or len(nodes) != 1
                or nodes[0]["Endpoint"] != self.endpoint or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", nodes[0]["Name"])):
            raise ValueError("only a selected single-node local docker-container builder is supported")
        container = self.json("container", "inspect", "--size", "buildx_buildkit_" + nodes[0]["Name"])
        if len(container) != 1 or not container[0]["State"]["Running"] or container[0]["State"]["Restarting"]:
            raise ValueError("selected builder must already be running; no bootstrap")
        # Docker inspect binds the actual builder container/configuration/volume.
        # Size and volatile process timestamps are excluded; private config is hashed.
        record = container[0]
        container_state = {key: record[key] for key in ("Id", "Created", "Image", "Config", "HostConfig", "Mounts")}
        inspected = self.read("buildx", "inspect", name).decode()
        # Last Activity is bookkeeping, not worker/config identity. All worker,
        # status, version, label and GC policy lines remain bound as a digest.
        inspected = "\n".join(line.rstrip() for line in inspected.splitlines() if not line.startswith("Last Activity:"))
        if "Status:" not in inspected or not re.search(r"^Status:\s+running$", inspected, re.MULTILINE) or "Error:" in inspected:
            raise ValueError("selected builder inspection unavailable")
        return {"name": name, "configuration_digest": plans.hashlib.sha256(payload).hexdigest(),
                "configuration_identity": identity, "plugin": plugin_path, "plugin_identity": plugin_identity,
                "container_id": record["Id"], "container_state_digest": plans.digest(container_state),
                "inspection_digest": plans.digest(inspected)}

    def cache(self, name, identifier=None):
        arguments = ["buildx", "du", "--builder", name, "--format=json"]
        if identifier is not None:
            arguments += ["--filter", cache_filter(identifier)]
        return cache_records(self.read(*arguments))


def cache_filter(identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9]{25}", identifier):
        raise ValueError("full literal cache ID required")
    # Buildx 0.37.2 translates id= to BuildKit regex, not equality. Anchors and
    # the strict alphabet produce one exact literal match; never accept regex.
    return "id=^" + identifier + "$"


def cache_records(output):
    records = []
    seen = set()
    for line in output.splitlines():
        row = json.loads(line, object_pairs_hook=plans._unique_keys)
        required = {"ID", "Parents", "CreatedAt", "Mutable", "Reclaimable", "Shared", "Size", "Description", "UsageCount", "Type"}
        if (not isinstance(row, dict) or not required <= set(row) or set(row) - required - {"LastUsedAt"}
                or not re.fullmatch(r"[a-z0-9]{25}", row["ID"]) or row["ID"] in seen
                or any(type(row[field]) is not bool for field in ("Mutable", "Reclaimable", "Shared"))
                or type(row["UsageCount"]) is not int or row["UsageCount"] < 0
                or row["Parents"] is not None and (not isinstance(row["Parents"], list) or len(row["Parents"]) > 128
                or any(not isinstance(parent, str) or not re.fullmatch(r"[a-z0-9]{25}", parent) for parent in row["Parents"]))):
            raise ValueError("unsupported/incomplete cache record")
        size = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(B|kB|MB|GB|TB|PB)?", str(row["Size"]))
        if not size:
            raise ValueError("unsupported provider size estimate")
        multiplier = {None: 1, "B": 1, "kB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4, "PB": 1000**5}[size[2]]
        seen.add(row["ID"])
        records.append({"id": row["ID"], "parents": row["Parents"] or [], "created": row["CreatedAt"],
                        "mutable": row["Mutable"], "reclaimable": row["Reclaimable"], "shared": row["Shared"],
                        "size": int(Decimal(size[1]) * multiplier), "usage_count": row["UsageCount"],
                        "type": row["Type"], "description_digest": plans.digest(row["Description"])})
        if len(records) > 2000:
            raise ValueError("cache inventory limit")
    return sorted(records, key=lambda row: row["id"])


def reclaimable_record(records, identifier):
    selected = [row for row in records if row["id"] == identifier]
    if (len(selected) != 1 or not selected[0]["reclaimable"] or selected[0]["shared"]
            or selected[0]["type"] != "regular"):
        raise ValueError("active/shared/unsupported cache stays protected")
    if any(identifier in row["parents"] for row in records):
        raise ValueError("cache has retained child records")
    return selected[0]


def inspect(resource, operation, *, timeout=10, cancelled=None):
    validate_resource(resource, operation)
    docker = LocalDocker(resource["endpoint"], timeout, cancelled)
    identifier = resource["id"]
    native = {"provider": docker.identity, "resource": resource, "operation": operation}
    if operation == "docker-container-remove":
        record = docker.container(identifier)
        label = resource.get("ownership_label")
        if label and (record["Config"].get("Labels") or {}).get(label["key"]) != label["value"]:
            raise ValueError("container ownership label missing/changed")
        if (record["State"]["Status"] not in {"created", "exited"} or record["State"]["Running"]
                or record["State"]["Restarting"] or record["Mounts"] or record["HostConfig"].get("Binds")
                or record["HostConfig"].get("VolumesFrom") or record["Config"].get("Volumes")
                or type(record.get("SizeRw")) is not int or record["SizeRw"] < 0
                or docker.read("container", "diff", identifier).strip()):
            raise ValueError("running/mounted/changed writable data stays protected")
        if docker.container_dependencies(identifier, record.get("Name", "")):
            raise ValueError("container has retained native consumers")
        native.update(state_digest=plans.digest(record), image=record["Image"], size=record["SizeRw"])
    elif operation == "docker-image-remove":
        record = docker.image(identifier)
        label = resource.get("ownership_label")
        if label and (record["Config"].get("Labels") or {}).get(label["key"]) != label["value"]:
            raise ValueError("image ownership label missing/changed")
        tags = record.get("RepoTags") or []
        digests = record.get("RepoDigests") or []
        repository = tags[0].rsplit(":", 1)[0] if len(tags) == 1 else None
        if len(tags) > 1 or any(reference.split("@", 1)[0] != repository for reference in digests):
            raise ValueError("multiple tags or other repository digest references stay protected")
        # Native ancestor lookup includes stopped containers and descendants;
        # avoid size/config inspection of unrelated user containers.
        consumers = docker.read("container", "ls", "--all", "--no-trunc", "--quiet", "--filter", "ancestor=" + identifier)
        if consumers.strip():
            raise ValueError("image has retained container consumers")
        # Bind image inventory without scanning unrelated layer contents. Native
        # non-forced removal refuses legacy child conflicts; --no-prune retains parents.
        native.update(state_digest=plans.digest(record), tags=tags, digests=digests,
                      image_ids=docker.listed_ids("image"), size=record["Size"])
    else:
        builder = docker.builder(resource["builder"])
        records = docker.cache(resource["builder"])
        selected = reclaimable_record(records, identifier)
        if docker.cache(resource["builder"], identifier) != [selected]:
            raise ValueError("builder exact-ID filter unavailable or broadened")
        native.update(builder=builder, cache_records=records, size=selected["size"])
    return native


def review(specification, references, host, project, *, timeout, cancelled=None, baseline_native=None, blocked=None):
    operation, resource = specification["operation"], specification["docker"]
    identifier = resource_identifier(resource, operation)
    row = {"id": identifier, "path": operation + ":" + resource["id"], "host": host,
           "project": project, "category": specification.get("category", "unknown"), "purpose": specification.get("purpose"),
           "operation": operation, "assessment": "Review", "reason": "Docker evidence unresolved",
           "effect": "report only; no removal authorized", "references": {}, "comparison": None,
           "preconditions": ["same local daemon/socket/executable/resource/configuration and evidence",
                             "separate exact-plan terminal confirmation; new plan on drift"],
           "specification_digest": plans.digest(specification)}
    if blocked or specification.get("findings") or any(consumer["state"] == "active" for consumer in specification.get("consumers", [])):
        row.update(assessment="Keep", reason=blocked or "protective finding or active consumer")
        return row
    try:
        native = inspect(resource, operation, timeout=timeout, cancelled=cancelled)
        row["native"] = native
        row["observation"] = {"complete": True, "provider_size_bytes_estimate": native["size"], "identity": plans.digest(native)}
    except InspectionCancelled:
        raise
    except (ValueError, OSError, KeyError, TypeError, InspectionUnavailable):
        row.update(assessment="Unavailable", reason="Docker inspection unavailable or resource protected; preserve it")
        return row
    deadline = time.monotonic() + timeout
    def reference(identifier):
        data, checked = plans._reference(identifier, references, Path("/native-docker-evidence"), [], deadline)
        row["references"][identifier] = checked
        return data
    def basis(claim):
        if not claim.get("basis"):
            raise ValueError("contextual evidence missing")
        for identifier in claim["basis"]:
            reference(identifier)
    try:
        for key in ("content", "consumer_scope", "recovery", "release"):
            basis(specification.get(key, {}))
        content = specification["content"]
        expected = json.loads(reference(content["reference"]), object_pairs_hook=plans._unique_keys)
        if content.get("method") != "native-inspection" or expected != {"schema_version": 1, "native_digest": plans.digest(baseline_native or native)}:
            raise ValueError("inspected native resource differs from assessed inventory")
        if (specification["consumer_scope"].get("unresolved", ["unknown"])
                or not specification.get("purpose") or not specification["release"].get("checkpoint")
                or specification["recovery"].get("kind") not in {"accepted-loss", "rebuild"}):
            raise ValueError("purpose/use/release/recovery unresolved")
        for consumer in specification.get("consumers", []):
            basis(consumer)
            if consumer["state"] != "released":
                raise ValueError("unknown consumer")
        if specification["recovery"]["kind"] == "rebuild" and not specification["recovery"].get("inputs"):
            raise ValueError("missing rebuild inputs")
        for identifier in specification["recovery"].get("inputs", []):
            reference(identifier)
        row.update(assessment="Eligible", reason="exact native inspection and evidence-backed ownership/use/release/recovery",
                   effect=EFFECTS[operation], comparison={"method": "native-inspection", "matched": True})
    except (ValueError, KeyError, TypeError, OSError, UnicodeError):
        pass
    return row


def expected_native(row, completed):
    native = row["native"]
    if row["operation"] == "docker-image-remove":
        removed = {item["native"]["resource"]["id"] for item in completed
                   if item.get("operation") == "docker-image-remove"
                   and item["native"]["resource"]["endpoint"] == native["resource"]["endpoint"]}
        return {**native, "image_ids": [identifier for identifier in native["image_ids"] if identifier not in removed]}
    if row["operation"] != "docker-cache-remove":
        return native
    resource = native["resource"]
    removed = {item["native"]["resource"]["id"] for item in completed
               if item.get("operation") == "docker-cache-remove"
               and item["native"]["resource"]["endpoint"] == resource["endpoint"]
               and item["native"]["resource"]["builder"] == resource["builder"]}
    return {**native, "cache_records": [item for item in native["cache_records"] if item["id"] not in removed]}


def revalidate(row, specification, references, completed, timeout):
    current = review(specification, references, row["host"], row["project"], timeout=timeout, baseline_native=row["native"])
    expected = {**row, "native": expected_native(row, completed)}
    expected["observation"] = {**row["observation"], "identity": plans.digest(expected["native"])}
    if current != expected:
        raise ValueError("Docker identity/content/configuration/evidence/consumer drift")
    return current


def validate_batch(plan, selected):
    """Provider identity is separate from filesystem containment and accounting."""
    seen = set()
    for row in selected:
        if not is_docker(row):
            continue
        native = row["native"]
        resource = native["resource"]
        validate_resource(resource, row["operation"])
        identity = _selection_identity(resource, row["operation"])
        if identity in seen:
            raise ValueError("duplicate exact provider resource")
        seen.add(identity)
        if (row["id"] != resource_identifier(resource, row["operation"])
                or native["operation"] != row["operation"] or row["observation"]["identity"] != plans.digest(native)):
            raise ValueError("changed typed provider identity")
        protected = [resource["endpoint"][7:], native["provider"]["executable"], native["provider"]["configuration_directory"]]
        if any(plans._overlap(Path(resource["endpoint"][7:]).resolve(strict=False), Path(path).resolve(strict=False))
               for path in (*plan["policy"]["holds"], *plan["policy"]["exclusions"])):
            raise ValueError("Docker endpoint is held/excluded")
        for target in selected:
            if not is_docker(target) and any(plans._overlap(Path(path), Path(target["path"])) for path in protected):
                raise ValueError("selected directory overlaps required Docker state")


def remove(row, limits):
    """Native refusal/timeout never establishes rollback; caller retains intent."""
    native = row["native"]
    resource = native["resource"]
    timeout = limits["timeout_seconds"]
    current = inspect(resource, row["operation"], timeout=timeout)
    if current != native:
        raise ValueError("Docker resource/provider changed immediately before native mutation")
    docker = LocalDocker(resource["endpoint"], timeout)
    if docker.identity != native["provider"]:
        raise ValueError("Docker executable/endpoint/daemon changed")
    if row["operation"] == "docker-container-remove":
        arguments = ("container", "rm", resource["id"])
    elif row["operation"] == "docker-image-remove":
        arguments = ("image", "rm", "--no-prune", resource["id"])
    else:
        arguments = ("buildx", "prune", "--builder", resource["builder"], "--filter", cache_filter(resource["id"]), "--force")
    try:
        result = subprocess.run(docker.command(*arguments), env=docker.environment,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise NativeRemovalFailed("native-timeout-outcome-unknown") from None
    except OSError:
        raise NativeRemovalFailed("native-unavailable-outcome-unknown") from None
    if result.returncode:
        raise NativeRemovalFailed("native-refusal", result.returncode)
    if observe(row, timeout=timeout) != "absent-provider-resource":
        raise NativeRemovalFailed("native-success-effect-unverified")


def observe(row, *, timeout=10):
    """Discover current tools; never execute plan-supplied paths or retry removal."""
    try:
        native = row["native"]
        resource = native["resource"]
        validate_resource(resource, row["operation"])
        docker = LocalDocker(resource["endpoint"], timeout)
        if docker.identity != native["provider"]:
            return "unknown-provider-identity"
        if row["operation"] == "docker-cache-remove":
            if docker.builder(resource["builder"]) != native["builder"]:
                return "unknown-builder-identity"
            records = docker.cache(resource["builder"])
            return "absent-provider-resource" if resource["id"] not in {item["id"] for item in records} else "same-provider-id-contents-unverified"
        kind = "container" if row["operation"] == "docker-container-remove" else "image"
        identifiers = docker.listed_ids(kind)
        if resource["id"] not in identifiers:
            return "absent-provider-resource"
        return "same-provider-id-contents-unverified"
    except (ValueError, OSError, KeyError, TypeError, InspectionUnavailable):
        return "unknown-provider-state"
