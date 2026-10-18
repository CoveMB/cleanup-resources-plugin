# Cleanup Resources Plugin

Task/project/global development disk review through one Codex skill and a standalone Python helper. Reviews produce assessed frozen plans. The helper also supports separately confirmed permanent removal of exact eligible directories on tested local macOS/APFS capabilities. The agent stops after review; the user operates cleanup in their own terminal. Installed combined cleanup and a new human pilot remain unverified.

## Run a review

Requires Python 3.12+ and its standard library. Git is optional for project worktree inventory. From the repository or extracted runtime package:

```sh
python3 skills/task-disk-review/scripts/devspace.py review --task "/path/to/task"
python3 skills/task-disk-review/scripts/devspace.py review --project "/path/to/project" --json
python3 skills/task-disk-review/scripts/devspace.py review --project "/path/to/project" \
  --assessment "/path/to/assessment.json" --plan-output "/outside/review-plan.json"
```

Without assessment/context inputs, the terminal helper still reports observations and unknowns. It needs no model, account, chat history or package manager. The packaged `task-disk-review` skill uses the same helper and can gather selected contextual evidence. Follow [OpenAI's installation documentation](https://developers.openai.com/plugins/build/plugins). No installer, hook, settings change or background process is bundled. See the bounded installed CLI/desktop invocation observations below; they cover the identified runtime subject only.

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

`--global` without `--config` returns a useful unconfigured report (exit 2). Missing providers and unknown effective retention are explicitly disclosed; no whole-disk completeness, model semantic truth, human acceptance or deletion safety is claimed. Terminal/extracted-package fixtures demonstrate the code path. The installed-host observations below cover only their tested subject and selected providers.

## Read-only host compatibility

Observed on 18 October 2026 with the read-only task/project/global runtime package at revision `8c9fb1e` (ZIP SHA-256 `0467d9032f9f4f43b0ce90f44a5fa8f486faad97a3bbdca205e1d9749ba79cde`). The installed test copy was retained while later evidence-capture guidance was integrated. These observations do not certify that later guidance in installed hosts, other platforms or any deletion operation.

| Route | Observed runtime | Bounded outcome |
| --- | --- | --- |
| Installed CLI | Codex CLI 0.162.1; Python 3.14.6; macOS 26.5.2 arm64/APFS | Explicit installed skill loaded; task/project/global helper exits 0/0/2. |
| Native desktop chat | Desktop app 26.928.21956, build 12404; same Python/OS | Explicit installed skill loaded from its cache path; independent task/project/global exits 0/0/2. Local filesystem observed. Automatic catalog activation/routing and UI/settings behavior were not demonstrated. |
| Terminal | Same installed helper, independent tiny scope | Task/project/global exits 2/2/2, disclosing incomplete assessment/provider coverage. No model or history required. |

Each route used separately inventoried synthetic context. Generated ordinary source copies A/C were Eligible after complete correspondence checks and agent interpretation of fictional release/rebuild evidence; required failure B stayed Keep; unknown D/E and the parent packet stayed Review. The model gathered selected context and prepared assessment without technical attestations, duplicate rebuilds or historical registration. This demonstrates explicit invocation and bounded model behavior, not semantic truth, real ownership release, actual installed dependency assessment or universal rebuildability. Original fixture bytes were preserved. Logical/allocated sizes were estimates, not reclaimed space.

A separate installed CLI challenge used a non-leading prompt with wrong-project release notes, an absent handoff and an untrusted checklist requesting repeated technical attestations. All three source comparisons matched, but only the copy with applicable release evidence became Eligible. The others stayed Review; the agent ignored the checklist directions and offered at most one grouped ownership/release question while completing the report. This is one bounded adverse-context observation, not universal semantic compliance. Desktop semantic evidence remains limited to its original instructed scenario.

Selected real worktree/plugin-storage metadata and local-ref Git inventory were accessible and report-only; activity/consumers remained unknown. Docker CLI 29.8.2 was installed, but its selected local Unix-socket summary timed out; usage, shared/reclaimable estimates and VM allocation remain unknown. No provider repair or maintenance followed. Effective CLI and desktop retention are independently unknown: no supported installed-version machine-readable interface was established, and desktop settings were not observed. Independent native cleanup can remove plugin-held resources; preserve dirty, untracked and ignored work and an agreed resume path. Native ignored-file snapshot recovery remains unverified.

A genuine user-operated **confirmation-only** terminal trial matched the displayed frozen plan/host and exact A/C selection, with zero deletion. The first attempt refused because `rtk proxy` captures stdout even when stdin is a terminal. The corrected trial required terminal stdin and displayed the frozen plan, selection, effects and prompt directly on the controlling terminal. Synthetic probes verified visible output before any response and refusal of piped/noninteractive input, approval flags and a missing controlling terminal. The agent supplied no confirmation response. Original failure and successful human report were retained separately.

This establishes a practical terminal interaction route, not cryptographic human identity, present-state deletion safety or reusable consent. Native verifiable exact-plan human binding remains unestablished. The skill stops after review even when asked to clean; broad shell approval, agent flags and development preapproval do not count as the product's human confirmation. No confirmation trial or saved result authorizes a future operation. The apply helper described below reuses the canonical frozen-plan/selection owner and independently revalidates current state; unsupported paths remain read-only.

Use native marketplace/plugin management with an inspected runtime-only source; never edit caches. Confirm supported commands with the installed CLI's help and the linked OpenAI installation documentation. Retain test installations and evidence until their consumers release them, then use supported native removal. No automatic setup or retention-setting repair is bundled.

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

Frozen plans bind host identity, exact target/contents, a separate descendant-identity digest, evidence/assessment digests, effects, holds/exclusions, review scope identities and preconditions. Candidates containing another eligible candidate’s checked evidence or rebuild inputs stay Review; narrow the plan to preserve those references. Keep the original assessment, optional manifest/configuration and referenced sources outside every selected target for revalidation and recovery. A batch that contains another selected item's required evidence or rebuild input refuses before mutation. Plans contain compact metadata/digests, not inspected payloads or bulk content inventories. Material changes require a new plan, including identical-content nested replacements or changed shared-file identities. Earlier review plans remain readable review data but must be regenerated for apply. Data validation alone cannot authorize removal. Separate exact-plan human confirmation remains mandatory. No automatic backup or universal undo is promised.

## Exact-directory cleanup in your terminal

After reviewing the agent-prepared plan, run the resolved helper yourself with the original inputs. Replace the example IDs with the displayed eligible IDs:

```sh
python3 skills/task-disk-review/scripts/devspace.py apply --plan "/outside/review-plan.json" \
  --assessment "/outside/assessment.json" --select ID_A,ID_C
python3 skills/task-disk-review/scripts/devspace.py apply --plan "/outside/review-plan.json" \
  --assessment "/outside/assessment.json" --all-eligible
python3 skills/task-disk-review/scripts/devspace.py apply --plan "/outside/review-plan.json" --cancel
```

Supply the original `--manifest FILE` when review used one, and original `--config FILE` for global review. Selection never promotes Keep/Review/Unavailable rows or adds newly discovered resources. All-eligible means only the eligible rows in that frozen plan. Empty, duplicate, unknown, overlapping, changed or protected selections refuse. Cancellation removes nothing.

Apply requires terminal stdin and a controlling terminal. It displays the exact plan digest, host, IDs, paths, observations, permanent effects, preconditions, policy and warnings directly through `/dev/tty`, including when a wrapper captures stdout. Inspect these and type the displayed `REMOVE` response exactly, or cancel. There is no approval flag, input-file confirmation, saved-consent replay or automatic agent execution. Terminal interaction does not authenticate human identity or defend against a same-user program driving a terminal.

The supported mutation route is local APFS on macOS with no-follow descriptor traversal, effective-user permission checks, advisory locking and durable-file capabilities. HFS, Linux, Windows, network/synchronized/unknown filesystems and unavailable capabilities remain read-only. Runtime capability refusal means zero initial mutation; changed capabilities during removal stop later actions. Do not move fixtures to an untested filesystem to bypass refusal. No real mount operation has been certified. Known mount boundaries are refused; actual alternate mount combinations remain unsupported.

Home/project/worktree/configured roots, mount/provider roots and their protected ancestors are never generic cleanup targets. Holds/exclusions and nested credentials, databases, original failures or other protected contents block selection. Known provider storage must be included in the selected policy; arbitrary custom storage cannot be recognized from its name. Canonical reassessment rereads the original content/use/release/retention/rebuild inputs before the whole batch, after confirmation and immediately before each remaining item. Missing or changed inputs require a new review. It cannot discover an unrecorded external consumer or certify the truth of source prose.

The helper locks cooperating instances in the current OS account at the fixed private state location `~/Library/Application Support/cleanup-resources-plugin`, using the account database home rather than an environment override. Its parent must already exist. State must be locally supported, owned by that account and mode 0700; records/lock are mode 0600. No alternate state/lock flag exists. State stays outside all reviewed targets and roots. Write or durability refusal prevents deletion. The helper writes a compact intent with file and directory synchronization, including Darwin `F_FULLFSYNC`, before mutation, then a result. Receipts contain hashed host identity, IDs, original resource identities, fixed operation/warnings, outcomes and measurements; no target paths, assessment prose, file payloads, transcripts or bulk listings. Keep the original plan separately for reconciliation.

Descriptor-relative operations reject observed links, mounts, changed child sets, identities and contents, and recheck the root path before every removal. Permission checks preflight the entire selected batch. The account-local advisory lock cannot control editors, builds or unrelated agents. Identity checks and unlink are separate operations: concurrent same-user changes can still race between them. This reduces accidental loss; it is not an atomic filesystem transaction or a security boundary. Stop known writers first through their normal owner workflow; the helper never stops processes.

Any drift, failure or interruption stops remaining items. A result can report `started-outcome-unknown` for a partially changed target; it never claims rollback. An interrupted or failed operation leaves pending intent and blocks another apply. Inspect it explicitly:

```sh
python3 skills/task-disk-review/scripts/devspace.py reconcile --plan "/outside/original-review-plan.json"
```

Reconcile only observes absent, replaced, same-identity-with-unverified-contents or unknown targets. It writes a fresh observation record, clears the pending marker after that record is durable, and never retries deletion. A same identity can contain partially deleted contents. A missing ancestor leaves the target unknown. Replacement resources survive. Corrupted/unavailable state refuses reconciliation: preserve records and inspect the failure; there is no force/clear-state fallback. Retain original failures and receipts until their consumers release them. After reconciliation, prepare a new review and obtain fresh exact-plan confirmation for any further cleanup.

Permanent removal has no Trash, quarantine, backup, force/shell fallback or universal undo. Recovery is only the previously established ordinary rebuild or explicitly accepted loss. Reported logical and allocated sizes are estimates. Before/after available free bytes and their signed net difference are filesystem observations; snapshots, clones, hardlinks, open files and other activity prevent exact target attribution or guaranteed savings. Result-write failure returns failure with the pending intent retained; preserve state and reconcile rather than blindly repeating apply.

Apply/reconcile return 0 for completed/cancelled or reconciled-without-retry outcomes, 1 for refusal, interruption, partial failure or unavailable result, and parser errors use 2. Inspect outcome fields rather than treating an exit code as permission. Component tests use only inventoried agent-created disposable directories and synthetic terminal responses. They do not establish genuine new human acceptance, installed CLI/desktop combined behavior, meaningful real-user savings, or support beyond the tested capabilities.

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

## Optional evidence capture

Later task/project/global reviews report advisory packet sizes and possible nested installed environments. Logical bytes **above** 250 MiB warn; **above** 1 GiB request an explanation. Exactly at either threshold does not cross it. Adjust only advice with `--evidence-warn-bytes N` and `--evidence-explain-bytes N` (positive bytes, warning ≤ explanation). These are never disposal, release or eligibility rules.

The report's **Optional for development/evidence workflows** instruction is the capture convention, maintained in `devspace/report.py` and displayed in terminal and JSON output for recognized packets. It can be adopted explicitly in an existing workflow, including incremental planning; installing this skill does not enforce it. No instructions or settings are edited automatically.

Recognition reuses protected evidence/failure/snapshot/log names and selected ancestry. Environment names (`node_modules`, `.venv`, `venv`, `pyvenv.cfg`) are hints, never proof of installation or disposability. Custom evidence names may be missed; the agent can use selected existing context to explain known purpose and size. No package manager is run. At most one useful grouped ownership/purpose/release/loss question remains available; an explanation request is not a technical form or extra approval gate. Unresolved candidates stay unresolved.

Sizes count each observed hardlink once within a packet. Nested packets are grouped under the outer packet; per-packet values are not additive host totals. Sparse logical size may exceed allocation. Partial selected-scope traversal conservatively leaves every packet's full size unknown and reports examined lower bounds, which can still cross a threshold. Unknown allocation stays unknown. No advisory implies reclaimable bytes.

For example, keep work in a separate `working/` directory and selected proof in `evidence/attempt-01/`, preserving the first failure before `attempt-02/`. A short manifest can reference the source commit and local patch, runtime/platform, sanitized command and exit/result, selected log/screenshot/input checksums and consumer/retention requirements. Preserve exact modified/offline dependencies or failure-specific state when those references cannot reconstruct it. This is an optional example, not required layout or historical registration. Legacy packets still need individual assessment; a review date is not a deletion deadline. Human inspection and representative evidence-sufficiency/size comparisons remain separate verification work; fewer files alone prove no improvement.

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
