# Cleanup Resources Plugin

Read-only task/project/global development disk review through one Codex skill and a standalone Python helper. Reviews can produce assessed frozen plans. **No apply, approval-execution or deletion command exists.**

## Run a review

Requires Python 3.12+ and its standard library. Git is optional for project worktree inventory. From the repository or extracted runtime package:

```sh
python3 skills/task-disk-review/scripts/devspace.py review --task "/path/to/task"
python3 skills/task-disk-review/scripts/devspace.py review --project "/path/to/project" --json
python3 skills/task-disk-review/scripts/devspace.py review --project "/path/to/project" \
  --assessment "/path/to/assessment.json" --plan-output "/outside/review-plan.json"
```

Without assessment/context inputs, the terminal helper still reports observations and unknowns. It needs no model, account, chat history or package manager. The packaged `task-disk-review` skill uses the same helper and can gather selected contextual evidence. Follow [OpenAI's installation documentation](https://developers.openai.com/plugins/build/plugins). No installer, hook, settings change or background process is bundled. Actual installed CLI/desktop invocation remains unverified.

Task mode stays within its selected directory. Project mode supports non-Git projects and inventories Git-discovered linked worktrees when the selected project is itself a worktree root. Nested selections do not expand into their parent repository. Worktrees/branches remain report-only. Status includes staged, dirty, untracked, ignored, locked, detached and locally unpushed states; missing upstream/activity stays unknown. No fetch occurs. Git status inspection refuses configured clean/process filters because even status can execute them, including unused global LFS filters. Submodule contents and collapsed ignored-directory contents are not inspected by Git inventory.

## Global coverage and provider storage

```sh
python3 skills/task-disk-review/scripts/devspace.py review --global --config "/selected/global-config.json" --json
```

Select a small JSON file, prepared by the agent when using the skill. All paths are absolute; no default home/whole-disk scan or package-manager installation. Example placeholders:

```json
{
  "schema_version": 1,
  "roots": ["/selected/development"],
  "holds": ["/selected/development/retained-output"],
  "exclusions": ["/selected/development/unrelated"],
  "codex_worktrees": ["/selected/managed-worktrees"],
  "package_storage": ["/selected/package-store"],
  "docker_host": "unix:///selected/docker.sock"
}
```

Only `schema_version` is required; omitted lists/providers are explicitly unconfigured, never inferred empty or successfully inspected. Lists accept at most 32 paths each; inputs retain the 1 MiB document bound. Optional `host_identity` binds configuration to the report's hashed execution-host identity; mismatch skips filesystem/provider probes. This is a locality safeguard, not authenticity. Relative global assessment paths are rejected; use exact absolute paths with the existing assessment contract.

Global reuses the task/project assessment and frozen-plan owner. It protects every configured development root, Git-discovered worktree root and selected provider storage path, including skipped/unavailable locations. Provider paths/ancestors are held/excluded from development assessment. Plan/manifest output must stay outside these scopes. For task/project reviews, pass known provider-managed paths through `--hold` and `--exclude`; storage names and arbitrary custom provider paths cannot all be recognized automatically.

Coverage locations distinguish examined, skipped, inaccessible, unavailable and unconfigured. “Examined” may still have partial metadata coverage; inspect its coverage field. One deadline and entry/content budgets bound global work; cancellation stops later locations. Nested/alias roots are skipped, and physical hardlinks across disjoint development roots count once. Host file totals cover examined development-root files; provider storage sizes remain separate, with overlapping provider roots skipped. Unknown bytes stay unknown. Selected network/sync/unsupported filesystems may yield read-only metadata, never executable eligibility; known synchronization boundaries are detected, but a local-filesystem observation does not prove absence of sync or consumers.

Codex-worktree and package-storage integrations inspect only selected metadata paths, without reading settings databases, transcripts or credentials. Package locations must come from relevant existing configuration/known storage; the helper runs no package-manager commands. Use the owning tool's documented maintenance after separately reviewing its effect, never a global prune inferred from this report. Git roots discovered in configured development/Codex locations use the existing finite status inventory, with no fetch; linked worktrees outside configured roots are inventoried by Git but not recursively scanned. Clean/stale/archived state never establishes release. Accepted handoff must retain required dirty/untracked/ignored state and an agreed resume path; tracked commits alone are insufficient.

Docker is optional: only the installed CLI's `--host unix:///... system df --format '{{json .}}'` summary is queried. Inherited Docker context/host/TLS overrides are stripped; explicit non-Unix endpoints are refused before any request. No context/account/credential probe, daemon start, install, mutation, prune or VM access. A local socket can proxy a daemon/VM elsewhere, so its usage is not execution-host allocation. Shared layers and native reclaimable labels are provider estimates; neither is summed into host file totals. Docker VM maximum and actual host allocation remain unknown. A supported summary includes all four categories: images, containers, local volumes and build cache. Missing categories remain unavailable, never zero. Unsupported format/version, refusal, timeout or unavailable CLI yields partial coverage with no fallback.

Effective Codex CLI and desktop automatic-retention settings are **independently unknown**: no supported installed-version machine-readable interface is established here. No default count, inferred disabled setting or guarantee of ignored-file snapshot recovery is reported. Independent Codex cleanup may remove worktrees the plugin recommends retaining; plugin holds cannot control it. Consult installed settings and verify actual behavior during host certification. Current official [worktree documentation](https://learn.chatgpt.com/docs/environments/git-worktrees) describes handoff/restore and independent cleanup; it does not establish this host's effective configuration. [Docker usage](https://docs.docker.com/reference/cli/docker/system/df/) and [Desktop storage](https://docs.docker.com/desktop/troubleshoot-and-support/faqs/macfaqs/) explain summary/shared sizes and maximum versus actual allocation. These references do not certify actual provider access or installed-host behavior.

`--global` without `--config` returns a useful unconfigured report (exit 2). Missing providers and unknown effective retention are explicitly disclosed; no whole-disk completeness, model semantic truth, human acceptance or deletion safety is claimed. Actual terminal/extracted-package fixtures demonstrate the code path; installed CLI/desktop/provider behavior remains unverified.

## Understand the results

| Status | Meaning |
| --- | --- |
| Eligible | Full supported content comparison plus agent-interpreted purpose, consumer, retention, release and recovery evidence |
| Keep | Protected/required/held content, known active consumers or inadequate recovery |
| Review | Missing or unresolved content correspondence, purpose, ownership, use, release or recovery evidence |
| Unavailable | Essential content/identity inspection is denied, incomplete or unsupported |

Metadata-only discovery never establishes eligibility. Names, age, clean Git, historical manifests, completed chats, lockfiles and package-store integrity do not prove a target disposable or unmodified. The helper checks current contents, exact comparison coverage and reference identities. **The agent interprets provenance and source meaning; the helper cannot semantically verify prose or detect a fabricated baseline origin.** A digest is neither authenticity nor permission. Unknown candidates are skipped rather than repeatedly asking users to certify technical facts.

Source examples: A rebuildable output and C ordinary nested dependencies can qualify with relevant target-wide proof; B required original-failure evidence stays Keep, D unknown contents stays Review. Existing unregistered resources need no historical manifest or duplicate rebuilt tree. A specific comparison can match current bytes against retained ordinary source files when the documented generator copies them verbatim. Opaque legacy environments often remain Review without adequate correspondence/rebuild evidence. No universal rebuildability or inactivity detector is promised.

Common credentials/`.env`, databases, `.wrangler`, history, required originals, unique/modified/offline dependencies and unresolved consumers cannot be overridden by accepted loss or release statements. Protected state payloads are not read. Generic evidence is initially Keep; an explicitly assessed disposable nested output can qualify while required originals remain protected. Custom sensitive state may be unrecognized and must be preserved by assessment.

Frozen plans bind host identity, exact target/contents, evidence/assessment digests, effects, holds/exclusions and preconditions. Candidates containing another eligible candidate’s checked evidence or rebuild inputs stay Review; narrow the plan to preserve those references. Keep the assessment and referenced sources for later revalidation. Plans contain compact metadata/digests, not inspected payloads or bulk content inventories. Material changes require a new plan. A future executor must reuse this owner and revalidate actual state; data validation alone cannot authorize removal. Separate exact-plan human confirmation remains mandatory. No automatic backup or universal undo is promised.

## Evidence input

Assessment JSON has `schema_version: 1`, a `references` dictionary and a `candidates` list. The agent prepares it from the current conversation, user-selected references and relevant existing project records; users need no form or technical attestation. No automatic chat/history discovery or reconstruction.

References map IDs to `{"path":"/selected/record","sha256":"actual-64-hex-digest"}`. Paths are selected absolute regular files outside targets. One candidate's shape is illustrated below; placeholders are not evidence:

```json
{
  "path": "build/output", "category": "output", "purpose": "completed generated output",
  "content": {"method": "inventory", "reference": "outputs", "basis": ["generator", "result"]},
  "recovery": {"kind": "rebuild", "inputs": ["source", "generator"], "basis": ["result"]},
  "consumer_scope": {"basis": ["release-record"], "unresolved": []},
  "consumers": [{"id": "task", "state": "released", "basis": ["release-record"]}],
  "release": {"checkpoint": "accepted handoff", "basis": ["release-record"]},
  "findings": []
}
```

An `inventory` reference is JSON with `schema_version: 1` and `entries`: files have `path`, `kind: "file"`, numeric `mode`/`size` and SHA-256; directories have `path`, `kind: "directory"` and `mode`. Paths are normalized relative paths. Compare the entire current target, including extras, types, permissions and topology. A partial/unrelated inventory cannot establish target-wide proof; the agent must check provenance even if bytes match. A freshly created target inventory is drift evidence, not an independent baseline. Direct self-reference/hardlink aliases are rejected; disguised copies require interpretation of their actual origin.

Alternatively content uses `method: "source-files"`, `files: {"relative/file":"reference-id"}`, `directories: []` (or directory inventory entries), and `basis`. Every current file must match an independently relevant retained source's bytes/mode; all topology must be accounted for. No build/install is executed. Optional `observed_tree_digest` binds an earlier observation; mismatch rejects it.

Consumer states are `released`, `active` or `unknown`. A scoped evidence basis is required even for no identified consumers; a manifest never closes that scope. Reuse existing human release/loss choices only when demonstrably applicable. Non-dependency disposable output may use recovery `kind: "accepted-loss"` with a basis; protective facts still win. Findings use `kind` and `basis`: `required-failure`, `persistent-state`, `unique-state`, `modified-dependency`, `offline-dependency`, `inadequate-recovery`, `hold` or `active-consumer`. Content/recovery may include short `explanation` text for agent interpretation, never machine semantic proof. Arbitrary status/approval/inspection booleans are rejected.

If useful, the skill asks at most one grouped ownership/purpose/release/loss question. It never asks users to certify technical facts. Without an answer it preserves unresolved rows and finishes the useful report. Requested cleanup stops after review; no shell/provider/worktree-removal fallback.

## Bounds, settings and persistence

Defaults: 2,000 entries per metadata/content phase, depth 12, a cooperative 10-second overall budget, and 256 MiB total content reads across explicitly assessed candidates. Metadata comes first; only selected candidates are reread for content. Reports disclose actual target bytes read separately from deduplicated size. One extra byte detects an over-budget candidate; exhaustion stops further candidate payload reads. Flags `--max-entries`, `--max-depth`, `--timeout`, `--max-content-bytes`, repeated `--hold PATH` and `--exclude PATH` adjust the selected review. Exclusions prevent traversal and eligibility; holds protect ancestors/descendants from selection. Denied/skipped/limited coverage is unknown usage, never zero.

Assessment/plan documents and each selected reference are limited to 1 MiB; at most 64 explicitly assessed candidates and 128 reference IDs are accepted. A larger source file requires a different adequate inventory/evidence path or remains Review; the helper does not silently sample it.

macOS/Linux descriptor and kernel filesystem capabilities are checked. Content reads also check each file descriptor’s mount identity; unknown or different mounts are not read. Content assessment recognizes local APFS/HFS on macOS and selected common local Linux filesystems; unsupported/network/FUSE/known sync boundaries stay report-only. A local filesystem flag does not prove a directory unsynchronized: preserve unresolved storage/use boundaries in assessment. WSL/remote aliases are unsupported for executable eligibility. Windows traversal is unavailable. OS machine identity is hashed with root identity; absent identity blocks eligibility. These observations do not certify deletion safety; cleanup execution and confirmation require separate verification.

Logical/allocated totals count unique examined regular files once; unknown descendants and directory metadata are excluded. Allocated blocks are estimates, not reclaimable bytes: external hardlinks, sparse files, clones/snapshots and concurrent writes limit attribution. Free space below 10% warns, below 5% emphasizes. No recovery is claimed. Links/unselected mounts are not traversed; Ctrl-C returns partial output. Blocked OS calls/process termination can delay cooperative limits. The plugin cannot control unrelated concurrent writers.

JSON reports include plans; text reports show digests/effects. `--plan-output` creates a new mode-0600 file outside reviewed roots/targets and never overwrites. No implicit runtime state directory. Reports expose host/path metadata/digests: inspect before sharing. Never include secrets, file payloads, transcripts or bulk listings in assessment descriptions or published reports.

Optional `--manifest FILE` reads historical helper-created resource records: `schema_version: 1`, `resources`, and for each resource absolute `path`, `origin: "helper-created"`, `purpose`, `association`, `consumers` (IDs), `retention` (holds), `release_checkpoint`. `--manifest-output NEW-FILE` explicitly copies supplied records outside reviewed roots and resource targets, privately/exclusively. It never invents history or automatically registers legacy resources. Every historical consumer needs current resolution. Origin is input history, not certified creation/inactivity.

Exit codes: 0 complete observed coverage, 2 partial/unknown coverage including unavailable safe traversal, 1 invalid/inaccessible selected directory or input/output failure, 130 cancelled. Parser errors also use 2 with a diagnostic. Review rows may coexist with complete traversal; no exit code authorizes cleanup. Narrow selection or check permissions/evidence on failure; do not retry through arbitrary shell tools.

## Development and deliverable

```sh
python3 -B -m unittest discover -s tests -v
python3 -B scripts/build_package.py /path/to/new-cleanup-resources-plugin.zip
```

Tests create disposable filesystem/Git fixtures with local refs and no external remotes, check preserved bytes and actual printed/serialized output, and invoke the extracted package. Simulated boundaries are distinguished from actual host observations.

The ZIP's explicit allowlist includes the manifest, README, one skill/UI resource and stdlib helper modules. It excludes source design, private planning/evidence, tests, Git and bytecode; the builder never overwrites. Inspect actual contents before distribution/installation. Licensing remains undecided; an open PR is not a release, host certification or human acceptance.
