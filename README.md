# Cleanup Resources Plugin

Task, project and general local disk-cleanup investigation through one Codex skill and a standalone Python helper. Reviews produce assessed frozen plans. Separately confirmed cleanup supports exact eligible directories, ordinary linked Git worktrees, selected local Docker resources and supported singleton npm cache entries on tested local macOS/APFS capabilities. The agent stops after review; the user operates cleanup in their own terminal. Installed observations apply only to their identified runtime subject. Start with a prioritized read-only review; selected cleanup and practical outcomes are recorded only when actually performed.

## Run a review

Requires Python 3.12+ and its standard library. Git is optional for project worktree inventory. From the repository or extracted runtime package:

```sh
python3 skills/task-disk-review/scripts/devspace.py review --task "/path/to/task"
python3 skills/task-disk-review/scripts/devspace.py review --project "/path/to/project" --json
python3 skills/task-disk-review/scripts/devspace.py review --project "/path/to/project" \
  --assessment "/path/to/assessment.json" --plan-output "/outside/review-plan.json"
```

Without assessment/context inputs, the terminal helper still reports observations and unknowns. It needs no model, account, chat history or package manager. The packaged `task-disk-review` skill uses the same helper and can gather selected contextual evidence. Follow [OpenAI's installation documentation](https://developers.openai.com/plugins/build/plugins). No installer, hook, settings change or background process is bundled. See the bounded installed CLI/desktop invocation observations below; they cover the identified runtime subject only.

Task mode stays within its selected directory. Project mode supports non-Git projects and inventories Git-discovered linked worktrees when the selected project is itself a worktree root. Nested selections do not expand into their parent repository. Discovery alone leaves worktrees report-only. Explicitly assessed ordinary linked Git checkouts support native removal below; branches are always retained. Status includes staged, dirty, untracked, ignored, locked, detached and locally unpushed states; missing upstream/activity stays unknown. No fetch occurs. Git status inspection refuses configured clean/process filters because even status can execute them, including unused global LFS filters. Submodule contents and collapsed ignored-directory contents are not inspected by Git inventory.

## Task context and explanations

A task cleanup request starts from the invoking conversation and current resources. The skill uses trusted runtime/native identity and available relevant earlier turns or linked records to explain creation, purpose, consumers, later holds and recovery. It reports missing context and contradictory evidence explicitly; completion, matching names and historical release alone do not establish current disposability. Applicable exclusions survive discovery. The [skill procedure](skills/task-disk-review/SKILL.md) owns this investigation; the Python helper has no conversation loader or general history search.

Candidate reasons identify the first unmet mechanical obligation, such as an absent independent baseline, unknown consumer, changed reference or missing recovery evidence. Further investigation may reveal other obligations. These explanations do not change eligibility: protected resources stay Keep, incomplete essential inspection stays Unavailable, and unresolved evidence stays Review. The agent resolves technical questions from evidence and asks only remaining human ownership, need, release or loss decisions.

A conversational read-only review need not save context. When a saved assessment or cleanup plan is requested, minimal private reference notes may record source locators and attributed interpretation outside all selected targets. Distinguish current observations, historical claims, agent interpretation and human decisions. A note's hash does not authenticate its meaning or turn it into independent content comparison. Never persist raw conversations in these notes or publish private context. Explain existing recovery copies and their costs without making surprise backups; absent resources are not evidence of plugin cleanup savings.

## General investigation

A request such as “help me free local disk space” can investigate relevant development, temporary, application/cache, Downloads/archive and selected provider storage. The skill starts from bounded metadata, prepares explicit helper scopes, and follows relevant recent or archived native conversation records when available. It uses actual source identities and current resource observations to distinguish creation, handoff, later reuse and unresolved need. A task request stays within its selected task context. Disk troubleshooting, performance diagnosis and filesystem repair remain outside this skill.

The [skill procedure](skills/task-disk-review/SKILL.md) owns category selection, relevance and finite history-read limits. Missing tools, denied/truncated history and reached limits remain visible; they preserve affected uncertain resources without preventing useful recommendations elsewhere. Native context coverage is separate from the helper's configured filesystem/provider coverage. Supplied fictional records can demonstrate interpretation, not native retrieval or desktop invocation. Existing installed observations below retain their original subjects and do not establish this broader journey.

Broader investigation adds no cleanup operation. Specialized application-cache and whole-project/source deletion, individual-file/archive removal, pnpm maintenance and unsupported provider operations remain unavailable. The report distinguishes these from existing guarded operations and excludes them from executable savings. No whole-account dump, private conversation-store scan, owner messaging or historical consent reuse is introduced.

## Global coverage and provider storage

```sh
python3 skills/task-disk-review/scripts/devspace.py review --global --config "/selected/global-config.json" --json
```

Select a small JSON file, prepared by the agent when using the skill, including for a general investigation. `roots` contains the exact selected directories; existing provider fields retain their meanings. Application-cache locations stay held for metadata review. All paths are absolute; no default home/whole-disk scan or package-manager installation. Example placeholders:

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

Codex-worktree and package-storage integrations inspect only selected metadata paths, without reading settings databases, transcripts or credentials. Package locations must come from relevant existing configuration/known storage. Aggregate package-storage discovery runs no package-manager command; explicit npm entry discovery/cleanup follows the supported contract below. Never infer global pruning from a usage report. Git roots discovered in configured development/Codex locations use the existing finite status inventory, with no fetch; linked worktrees outside configured roots are inventoried by Git but not recursively scanned. Clean/stale/archived state never establishes release. Accepted handoff must retain required dirty/untracked/ignored state and an agreed resume path; tracked commits alone are insufficient.

Docker is optional. Global discovery queries the installed CLI's `--host unix:///... system df --format '{{json .}}'` summary; explicitly assessed selected Docker resources use the native cleanup path below. Inherited Docker context/host/TLS overrides are stripped; non-Unix endpoints are refused before any request. No account/credential probe, daemon start, installation or VM manipulation. A local socket can proxy a daemon/VM elsewhere, so its usage is not execution-host allocation. Shared layers and native reclaimable labels are provider estimates; neither is summed into host file totals. Docker VM maximum and actual host allocation remain unknown. A supported summary includes all four categories: images, containers, local volumes and build cache. Missing categories remain unavailable, never zero. Unsupported format/version, refusal, timeout or unavailable CLI yields partial coverage with no fallback.

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

Frozen plans bind host identity, exact target/contents, a separate descendant-identity digest, evidence/assessment digests, effects, holds/exclusions, review scope identities and preconditions. Candidates containing another eligible candidate’s checked evidence or rebuild inputs stay Review; narrow the plan to preserve those references. Keep the original assessment, optional manifest/configuration and referenced sources outside every selected target for revalidation and recovery. A batch that contains another selected item's required evidence or rebuild input refuses before mutation. Plans contain compact metadata/digests, not inspected payloads or bulk content inventories. Material changes require a new plan, including identical-content nested replacements or changed shared-file identities. Existing v1 directory plans retain their original meaning and apply/reconcile semantics; incomplete older review plans still require regeneration. V2 explicitly distinguishes directory and native operations and rejects unknown types/versions. Data validation alone cannot authorize removal. Separate exact-plan human confirmation remains mandatory. No automatic backup or universal undo is promised.

## Selected cleanup in your terminal

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

## Native linked-worktree cleanup

Use the same review, exact selection, terminal confirmation, apply and reconcile commands. Start a project review from a retained checkout: a selection containing its required review context or any known native repository/recovery state refuses before mutation. Git is optional except for this operation. Ordinary linked checkouts require an explicit v2 assessment; native discovery never establishes ownership or release. Git 2.50.1 on local macOS/APFS is the tested native baseline. The [Git worktree manual](https://git-scm.com/docs/git-worktree/2.48.0) is unchanged through 2.51.2; fixture results, rather than version assumptions, establish this enabled path.

The agent must establish the actual owner and lifecycle from selected relevant context, resolve all consumers (including open PRs/reviewers), and explain an agreed resume route. A clean/old checkout, completed chat or local upstream comparison is insufficient. Codex-managed checkouts remain **Unavailable** for removal: the helper cannot verify their current app ownership, configurable managed root or supported snapshot/restore lifecycle. The default managed-root guard is additional protection, never an ownership detector. Do not label a checkout `git` merely because it is outside that root. Use the app's owning lifecycle separately only after its exact scope and ignored-data preservation are verified; no app database/settings inspection or automatic chat-resume promise.

A v2 assessment retains `references` and `candidates`. Every candidate supplies `operation`: `directory-remove` uses the existing directory evidence contract; `git-worktree-remove` uses `category: "worktree"`, an absolute target path and this additional shape:

```json
{
  "worktree": {
    "repository": "/selected/retained-repository-worktree",
    "retained_ref": "refs/heads/released-topic",
    "lifecycle": "git",
    "basis": ["owner-release-resume-record"]
  },
  "recovery": {"kind": "retained-commit", "basis": ["owner-release-resume-record"]}
}
```

The remaining content/purpose/consumer/release/findings fields follow the evidence-input contract below. The complete independent content inventory covers checkout files and directories, excluding only the independently verified root `.git` link metadata. The helper binds the executable, repository/common directory, linked administration, marker, HEAD/ref, current status, topology and full inspected contents. It refuses main/current/locked/detached/dirty/staged/untracked, hidden index flags, submodules/nested repositories, protected or incomplete content, active/unknown consumers, holds and uncertain recovery. Native removal also deletes private Git administration. A bounded no-follow metadata check refuses per-worktree configuration, private refs and other unsupported administration files without reading their payloads; only the supported standard link/index/HEAD/log metadata and empty private refs directory are accepted. Both old and new HEAD reflog commit IDs, plus ORIG_HEAD, must remain reachable from the bound retained branch. A no-follow reader accepts at most 128 HEAD-log records and 1 MiB, rejects malformed/changed logs, consumes opaque trailing record bytes locally and retains no author/message text. Rewritten or unresolved history and unsupported administration, including commit-message scratch state, remain unavailable. Unknown ignored content stays protected. Explicitly compared ordinary generated ignored contents also need separate retained `recovery.inputs` references and an explanation; retained commits do not preserve ignored files. Ignored `.env` is always protected and its payload is never read.

The helper constructs only native `git worktree remove -- <exact-path>`, without force, branch deletion or filesystem fallback. Two selected checkouts and nonoverlapping directory/worktree selections share the same lock, confirmation and private durable intent/results. Revalidation permits only topology/root transitions caused by earlier successful selections; external changes stop the batch. Native Git still has a same-account race window between inspection and mutation. Timeout/refusal leaves an uncertain outcome and pending intent; reconciliation observes path, Git registration and retained branch, never retries removal. A successful result preserves the branch and tracked reconstruction route; no ignored-data undo or automatic chat resume is promised.

V1 directory receipts/pending reconciliation retain their original operation and warning semantics. V2 receipts bind each operation and a digest of native identity without copying paths or Git payloads. Disposable repository tests exercise native success, refusal, ignored-secret preservation, retained-branch reconstruction, mixed batches, drift, interrupted outcomes and v1 regressions. These component checks do not establish installed-agent routing or a real-project pilot; combined CLI/desktop/practical acceptance remains separate.

## Selected native Docker cleanup

Use the same review, assessed frozen plan, exact terminal selection, apply and observation-only reconcile commands. Version 3 adds `docker-container-remove`, `docker-image-remove` and `docker-cache-remove`; versions 1/2 keep their original directory/worktree meanings. Docker rows carry a `docker` object instead of a filesystem `path`. Never pass Docker stores or configuration to directory removal. A missing CLI, denied socket, remote endpoint, unsupported response or unsupported builder stays Unavailable; the helper does not install tools, bootstrap builders, stop resources, change contexts/settings or broaden cleanup.

The agent prepares the evidence from scoped ownership, purpose, current consumers, release and recovery facts. A label or stopped state alone is insufficient. Each container/image selection supplies `endpoint: "unix:///selected/docker.sock"` and its full `id` (64 hex characters for containers, `sha256:` plus 64 hex for images). An existing `ownership_label: {"key": "project.owner", "value": "selected-project"}` may additionally bind a known label. Labels and historical helper registration are optional: ordinary existing unlabelled resources can qualify from adequate independent ownership/provenance evidence and complete current inspection. Unknown ownership remains Review; never add labels merely to qualify user resources. Cache selection supplies the endpoint, full 25-character cache ID and an explicit named `builder`. No source-supplied command, flag, prefix, regex or broad age/space predicate is accepted.

Reuse the assessment's `purpose`, `category`, `consumers`, `consumer_scope`, `release`, `recovery` and `findings` fields. Docker content uses `method: "native-inspection"`, `reference` and contextual `basis` references. The referenced compact JSON is `{"schema_version":1,"native_digest":"<digest of the inspected native record>"}`. This snapshot binds drift; it does not independently establish provenance or disposability. Actually interpret the relevant generation/configuration evidence, mounts, writable changes and loss/rebuild consequences. Unknown ownership/data/recovery/use remains protected. Users do not author this JSON or certify technical facts.

Each operation/full-ID pair may occur only once per assessment and selected batch, even through different socket spellings, daemon endpoints or builder names. Consolidate every consumer obligation before review: provider aliases must not hide an active consumer. Identical image IDs on genuinely separate daemons require separate review scopes.

Container eligibility requires a created/exited, non-running, non-restarting, mount-free container, no bind/volume inheritance or declared persistent volumes, complete size/configuration inspection, an empty native writable-change inventory and no known namespace/link/volume consumers. Empty layers can still allocate metadata blocks. Any writable file changes or mounts stay protected. Removal constructs only `docker --host ENDPOINT container rm FULL_ID`, without force or volume removal. Images require no stopped/running container consumers, at most one tag and no other repository digest references. The plan binds tags/digests, complete inspect identity and image inventory. Removal uses `image rm --no-prune FULL_ID`, retaining unselected parents; native conflicts, including additional tags/legacy children, stop the batch without force.

Cache cleanup supports the **explicit local `default` Docker driver** and already-running **single-node local `docker-container` builders** with their exact Unix endpoint; support is not restricted to helper-created builders. Remote, multi-node, inactive and unknown builders remain unavailable. The default driver binds the explicit daemon, single worker inspection and buildx executable; named docker-container builders additionally bind selected instance configuration and actual builder-container/volume identity. The local default driver (BuildKit 0.33.1) was exercised using only provably new synthetic records, preserving every pre-existing ID and an unselected synthetic control. No default-builder/context switch, private build input or real-cache cleanup occurred. Only individually assessed reclaimable, non-shared regular records qualify; active, source, frontend and cache-mount records remain protected. Mutable regular records may qualify only with current exact inspection and release evidence; they can change during another build, which remains an external race the helper cannot lock.

The tested buildx 0.37.2 translates `id=` into a regex internally. The helper validates the full ID's fixed alphabet and generates `id=^FULL_ID$` itself, verifies that filtered `du` matches exactly that record on the selected builder, then uses the same anchored literal for `buildx prune --builder NAME --filter ... --force`. Here buildx's `--force` skips its own prompt; it does not force removal of active data or bypass this helper's exact-plan terminal confirmation. No `--all`, global prune, threshold predicate or arbitrary expression is used. Provider sizes can be rounded display estimates; relative “last used” text is never an inactivity or identity rule. Creation, usage count, ownership, state, configuration and remaining inventory are revalidated.

One lock and private durable intent cover mixed nonoverlapping directory/worktree/Docker selections. Whole-batch and immediate per-item revalidation accept only expected inventory transitions from earlier successful selected operations. Conflicting selections, protected provider state, external drift, denial, native refusal or interruption stop remaining work. Killed/timed-out clients do not prove daemon rollback or completion. Keep the pending intent and original plan; `reconcile` observes current full provider IDs under the same daemon/builder identity without retrying deletion. Receipts retain compact resource IDs/identity digests, outcomes and provider estimates; no raw inspect/configuration payload, labels, paths, transcripts or contents.

Docker client/server 29.8.2 and buildx 0.37.2 on the tested local macOS/APFS host have disposable native fixture evidence. Opt-in native tests require an explicitly disposable running builder and retained fixture inventory; ordinary CI never touches ambient Docker resources. Component evidence does not certify installed-agent behavior or a real-project pilot. Net host free-space change is measured separately from daemon/shared/cache estimates, can be negative, and never promises Docker VM compaction. See Docker's [container removal](https://docs.docker.com/reference/cli/docker/container/rm/), [image removal](https://docs.docker.com/reference/cli/docker/image/rm/), [buildx disk usage](https://docs.docker.com/reference/cli/docker/buildx/du/) and [prune](https://docs.docker.com/reference/cli/docker/buildx/prune/) references; installed behavior and actual fixtures determine supported scope.

## Selected npm cache and generated/temp cleanup

Add an explicitly selected cache to the same review; nothing is removed:

```sh
python3 skills/task-disk-review/scripts/devspace.py review --project "/selected/project" \
  --npm-cache "/selected/npm-cache"
```

Entries are ranked by logical size, with shared-content aliases kept and unassessed singleton entries marked Review. Indexed content is counted once per integrity; it is separate from development-root totals and is not an allocation or reclaimable-space promise. Metadata discovery does not establish ownership, inactivity or offline recovery. Coverage remains candid when the optional tool, version, bounds, permissions or filesystem is unavailable. Multiple selected cache roots share the review deadline; no default home/cache scan occurs.

Native cleanup currently supports installed **npm 11.17.0 with its bundled cacache 20.0.4**, ordinary symlink installations or resolvable Volta shims, and canonical local cache roots. Other layouts/versions remain unavailable until verified. Node/npm are optional; no dependency is downloaded or installed. Read-only index enumeration uses npm's existing bundled cacache API. It never runs `npm cache verify`, which garbage-collects, or reads cache response headers into reports. User/project/global npm configuration and inherited Node/npm overrides cannot redirect the native operation: global mode skips project configuration, user/global config read distinct empty device sources, environment is reduced, and execution is offline with logs/update notification disabled. Installed executable/package/configuration identities are frozen. No credentials or user `.npmrc` are inspected.

The agent prepares a **v4** assessment with the existing `references`, `candidates`, consumer, finding, release and recovery vocabulary. V4 can also contain the established v2 directory/worktree and v3 Docker candidate forms. A cache candidate has no directory `path`:

```json
{
  "operation": "npm-cache-remove",
  "npm": {"cache": "/selected/npm-cache", "key": "make-fetch-happen:request-cache:https://registry.npmjs.org/example/-/example-1.0.0.tgz", "integrity": "sha512-<actual canonical integrity>"},
  "category": "cache", "purpose": "released ordinary package download",
  "content": {"method": "npm-lock", "reference": "trusted-lockfile", "basis": ["source-provenance"]},
  "recovery": {"kind": "rebuild", "inputs": ["trusted-lockfile", "package-inputs"], "basis": ["recovery-record"], "explanation": "Later installation may download again; network access and download cost are acceptable for this released use."},
  "consumer_scope": {"basis": ["release-record"], "unresolved": []},
  "consumers": [{"id": "completed-task", "state": "released", "basis": ["release-record"]}],
  "release": {"checkpoint": "accepted completion", "basis": ["release-record"]},
  "findings": []
}
```

Placeholders are not evidence. `npm-lock` compares actual cached bytes against an independently trusted v2/v3 npm lockfile's exact resolved URL and SHA-512 integrity; no compulsory redownload, duplicate tree or human technical form. A lockfile does not establish current use, provenance, continued registry access or offline availability: the agent interprets those separate scoped facts. Private/unavailable or offline-only data stays protected. Alternatively `source-file` compares a retained independent source reference; do not create a copy of the target and call it an independent baseline. Missing recovery/release/use evidence remains Review. Active consumers and protective findings remain Keep.

Only a single SHA-512 entry with **no other live key sharing its integrity** is executable. Native `npm cache clean <key>` removes backing content as well as index metadata; shared groups are protected because subsequent alias removal can stop at a missing body. Complete bounded index/layout inspection rejects links, hardlinks, in-progress temporary content and corrupt/unknown index records. A live unsupported or multi-hash integrity makes cache inspection unavailable, because different integrity strings can share backing content. Active/protective/unresolved and historical consumer/retention obligations propagate from cache ancestors or the selected entry's actual content/index paths, including physical APFS case aliases. Unrelated neighboring files remain independently protected. The frozen inventory binds all live keys, integrity, timestamps and metadata digests; new entries/aliases, modified content or tool/cache/configuration/evidence drift require a new review. Two selected independent entries in one cache allow only their expected successful transitions. Caches/tool state cannot enter a mixed generic directory/worktree removal.

Use the existing exact selection, user-operated terminal confirmation, durable private receipts and observation-only `reconcile` commands. The native operation constructs one literal key argument internally, without force, broad purge, GC or filesystem fallback. Timeouts/refusals leave uncertain results and stop remaining work. Reconciliation distinguishes absent key/content, partial effects and replacement/unknown identity; it never retries removal. Receipts contain digests, sizes and outcomes, excluding raw keys, URLs, headers, paths and payloads. There is no universal undo; later builds/downloads may cost more and need a network connection.

Ordinary generated/temp outputs, including unregistered resources, use the existing independent complete-content comparison and guarded exact-directory path. Names/age never establish eligibility. Preserve active, modified, offline-only, original-failure, unique and uncertain neighboring data. Pip HTTP stores, editor/application caches, arbitrary toolchains and unsupported npm layouts remain report-only. Disposable native fixtures establish this component's effects and controls; combined installed CLI/desktop behavior and real-project usefulness remain separate acceptance work.

## Evidence input

Assessment JSON has `schema_version: 1`, a `references` dictionary and a `candidates` list. For a requested saved assessment or cleanup plan, the agent prepares it from the task investigation above and relevant existing records; users need no form or technical attestation. Context notes are attributed interpretation, never an independent content baseline. Relevant native history follows the skill's bounded investigation procedure; the Python helper has no history loader and private transcript/database access remains unsupported.

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

For example, keep work in a separate `working/` directory and selected proof in `evidence/attempt-01/`, preserving the first failure before `attempt-02/`. A short manifest can reference the source commit and local patch, runtime/platform, sanitized command and exit/result, selected log/screenshot/input checksums and consumer/retention requirements. Preserve exact modified/offline dependencies or failure-specific state when those references cannot reconstruct it. This is an optional example, not required layout or historical registration. Legacy packets still need individual assessment; a review date is not a deletion deadline. Representative capture comparisons are optional secondary evidence; fewer files never justify losing required originals. Broader installed cleanup and practical user experience remain separate acceptance work.

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
