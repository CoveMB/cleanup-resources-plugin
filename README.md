# Cleanup plugin

Read-only disk usage review of **one selected task directory**, through one Codex skill or a standalone Python helper. I1 is implemented; assessed plans, project/global inventory, installed-host certification and cleanup remain future work. No deletion/apply command exists.

## Run from a terminal

Requires Python 3.12+ and no third-party Python packages or package manager. From the extracted package/repository root:

```sh
python3 skills/task-disk-review/scripts/devspace.py review --task "/path/to/task"
python3 skills/task-disk-review/scripts/devspace.py review --task "/path/to/task" --json
```

The packaged `task-disk-review` skill uses the same helper. Its intended prompt is “Review cleanup for this task directory: /path/to/task.” Follow [OpenAI's plugin installation documentation](https://developers.openai.com/plugins/build/plugins) for the root `plugin.json` package. No installer, hook, settings change or background scan is bundled. Actual installed Codex CLI/desktop invocation remains unverified until the host compatibility increment.

Traversal requires no-follow directory descriptors: macOS and Linux are capability checked. Linux additionally reads its own kernel descriptor mount IDs to detect same-device bind mounts. Missing capabilities or mount metadata produce Unavailable coverage; Windows currently reports unavailable traversal. Python 3.12 is the declared minimum, with runtime verification recorded separately in the implementation evidence; version alone does not certify a host.

## Understand the report

The report identifies its actual execution host, selected/canonical directory and unknown thread identity. It never assumes a cloud session can inspect another computer. Entries show Keep, Review or Unavailable, with examined/skipped/inaccessible coverage. **No entry is Eligible.** Complete means metadata traversal only, never content, current-use, recovery or deletion assessment.

Common credentials/`.env`, databases, `.wrangler`, application history and evidence/original-failure names are protected. Protected state directories are skipped rather than enumerated; file payloads are never opened. Names cannot identify every custom database, credential or required failure, so unknown resources remain Review. Build/dependency names do not establish disposability.

Logical and allocated totals count unique examined regular files once, including hardlinks. Directory metadata, links, special files and skipped descendants are excluded. Partial totals cover known files only; unknown usage is **not zero**. Sparse allocation may be smaller than logical size. Allocated blocks are not reclaimable bytes: hardlinks outside scope, clones, snapshots, shared storage and concurrent writes prevent perfect attribution. No disk-space recovery is claimed.

Free filesystem space is checked when invoked: below 10% warns, below 5% emphasizes the warning. Unknown free space stays unknown. Remote/synchronized/network/WSL locality remains unverified and report-only. Reports contain host/path metadata; inspect before sharing. File contents, credentials and raw transcripts are never captured.

## Bounds, cancellation and errors

Defaults: 2,000 metadata entries, depth 12, cooperative 10 seconds. Set `--max-entries` (1–100000), `--max-depth` (1–64) or `--timeout` (positive seconds, at most 3600) for the selected task. Traversal uses filesystem enumeration order, so a bounded partial result is not a stable ranking. Ctrl-C returns a partial report; blocked filesystem calls may delay cancellation/timeout. Links and unselected mounts are not traversed. Concurrent filesystem changes can still make metadata stale; this tool is not a security boundary against other processes with the same privileges.

Exit codes: 0 complete metadata traversal; 2 partial coverage; 1 invalid/unavailable selected scope; 130 cancelled. Argument errors use 2 with a parser diagnostic instead of a report. Inaccessible/skipped rows and stop reasons explain gaps. Select a real directory, check permissions, or narrow scope if a limit is reached. Do not infer zero use from missing coverage or retry through arbitrary shell tools. The helper writes no report/state files and disables Python bytecode writes; filesystem access timestamps may change during metadata enumeration.

## Development and package contents

```sh
python3 -B -m unittest discover -s tests -v
python3 -B scripts/build_package.py /path/to/new-cleanup-plugin.zip
```

Tests create explicitly disposable temporary fixtures: nested task/sibling files, protected state and failure evidence, denied directories, links, hardlinks, sparse files and extracted packages. Only those test-owned temporary roots are removed. Mount/unsupported-host failure cases are simulated; no real mounts or user resources are altered.

The ZIP builder includes only the manifest, this README, one skill/UI metadata and the stdlib helper modules. It excludes the source design, local plans/evidence, tests, Git metadata and bytecode, and refuses to overwrite an existing archive. Inspect the actual archive before installation/distribution. The repository's unchanged source design (`cleanup-plugin-plan.md`) is developer context and is deliberately absent from the runtime ZIP. Distribution licensing has not been selected; no public release or installed-host certification is implied.
