# Context-aware resource cleanup: proposed requirements

Status: paused future work. Reconciled on 29 October 2026 against source baseline `d7ead1f`; the date in this filename identifies the original design, not an implementation release. This is the canonical requirements owner for the follow-up. The [current README](../../../README.md) remains authoritative for shipped behavior.

The [incremental plan](../../incremental-and-test-plans/context-aware-resource-cleanup/plan.md) maps these requirements to future increments and current gaps. Its [QA plan](../../incremental-and-test-plans/context-aware-resource-cleanup/qa-plan.md) owns behavioral acceptance. Neither this proposal nor historical work on another branch authorizes resumption, resource mutation or external evaluation.

## 1. Task-context assessment

For an explicitly invoked task review, use the invoking conversation and relevant earlier turns available through supported native access. Establish task/resource identity from trusted metadata and actual repository/resource bindings, not titles, path names or environment guesses.

Investigate provenance, failed attempts, outputs/evidence, checkouts, containers/caches, handoffs, holds, active consumers and recovery. Inspect the current candidate and relevant retained replacement; reconcile later contradictory evidence and post-handoff changes. Missing earlier context remains explicit uncertainty. Do not ask the user to certify technical facts the investigator should establish.

Bind user holds and exclusions before the first discovery. Resolve any agent-prepared relative policy paths to the intended scope before invoking the helper; preserve existing CLI relative-path semantics. Never discover an excluded resource first and promise to filter it afterward.

## 2. General and historical investigation

An explicit general disk-cleanup request may authorize bounded metadata investigation under the current user's home and relevant accessible development, application/cache, temporary, Downloads, archive and provider locations. A task request must never silently become a general scan. Disk troubleshooting, performance investigation and repair remain outside this cleanup-routing boundary. The helper continues to receive explicit roots/provider configuration; no implicit whole-disk CLI mode is added.

Exclude other users, remote/external/cloud/system scope and unrelated personal contents or secrets by default. Start with metadata, rank by relevance, size and consequence, and inspect payloads only when needed and authorized. Age, names and native reclaimable labels are not disposal evidence.

Use supported recent/archive APIs for relevant history; no private databases/transcripts, whole-account dumps, recursive conversation crawl or messaging. Bound metadata before acquiring it, including all pinned entries a listing returns. If the API cannot bound the total returned metadata, skip that listing and use already-known relevant IDs or bounded archive pages; do not over-fetch and truncate afterward.

The initial history budget is at most eight related conversations, three pages of up to twenty turns each, plus at most two additional targeted page reads for a named material unresolved fact in the same authorized scope. Stop on resolution or exhaustion and disclose pagination, truncation, access failures and unavailable tools. No result does not prove no owner. CLI operation without native history tools remains useful with reduced coverage.

## 3. Worktree and branch lineage

Distinguish the checkout from retained branch/history. Bind the actual repository/common directory, checkout path, full HEAD, retained ref and destination before interpreting integration.

Report ancestry, patch equivalence, verified source/destination merge or squash evidence, retained-but-unintegrated history and unresolved lineage separately. Neither retention nor patch similarity establishes release. Check the current candidate HEAD/ref, later commits, reverts, detached state, shallow/missing objects, stale refs, dirty/untracked/ignored state, private refs or reflog-only recovery, locks and consumers. Validate ref arguments and distinguish command errors from a negative ancestry result.

Local refs stay explicitly local unless a refresh is separately authorized. Reuse existing ordinary linked-worktree removal only when its current guards apply. Primary, managed, pinned, shared, dirty or unknown-lifecycle resources remain protected; no relabeling as ordinary Git. Respect attachment-scoped lifecycle capabilities. Do not add cross-chat archive, transfer, branch deletion or owner messaging authority.

## 4. Evidence, questions and reporting

Separate current observed facts, historical claims, model interpretations and human decisions. Keep compact locators, identity/time, rationale, contradictions and consequences. Hashing a model note does not authenticate history, prove independent content or resolve ownership.

Reuse the existing assessment/reference contract where adequate. Persist only explicitly requested compact private assessments outside targets; no automatic history/evidence registry. Do not export private context to new providers or public documentation.

Ask at most one grouped question about ownership, use, release or accepted loss. Unanswered uncertainty protects affected resources while the rest of the useful report proceeds. Explain the specific unmet obligation rather than a generic technical attestation request.

Keep recommendations distinct from executable eligibility. Unsupported or unresolved resources are not ready-to-remove savings. Do not create new backups, rebuilds or copied baselines just to make candidates qualify; explain the obligations and cost of existing retained recovery material.

## 5. Proposed operation contracts

Each extension needs an explicit versioned contract. Existing saved v1–v4 plans keep their meaning; old readers must reject unknown operations/versions. Contract, validation, dispatcher, executor, documentation and preservation checks must ship together. Use fresh review/confirmation and retain cross-operation evidence and recovery dependencies.

### Exact regular files

Support one exact independently assessed regular file within a mixed directory, initially using retained content evidence. Bind complete content/identity and no-follow parent/target identity; preserve parents, siblings and independent references. No glob, recursive parent deletion, link/hardlink removal or media/replacement matching. Reject changed ancestors/targets, incomplete reads, unsupported locality and overlapping or dependent selections.

### Assessed generated outputs

A distinct proposed content method may allow completely inspected generated output without an independent historical inventory when provenance, consumers, release and an exact accepted-loss decision are established. Limit it to generated output files/directories; do not manufacture a matching baseline or claim unchanged content or rebuildability.

Source, credentials, persistent/unique state, dependencies, required original-failure evidence, unknown ownership and partial inspection remain excluded. Bind current bytes/identity and revalidate. A hash binds selection, not semantic truth; the helper cannot certify the investigator's interpretation. Existing evidence methods and provider/worktree guards remain unchanged.

### Assessed stopped containers

Support only selected stopped containers whose writable changes are completely and safely assessed as disposable and whose mounts fit a supported contract. Bind full container ID, daemon/executable, complete diff, changed-path interpretation and consumer/release/recovery evidence. Diff paths alone do not show value or disposability; inspect without executing container code or exposing unrelated payloads.

Preserve bind sources and all named/anonymous volumes. Running/restarted containers, unique databases, unreadable/unsupported changes and unknown mounts block. Recheck immediately before native removal; no force, volume flags, image deletion, process stop, Docker-root deletion or shell fallback. Timeout or partial effects require observation-only reconciliation, not replay. Existing container/image/build-cache contracts retain their meaning.

### pnpm selected-store maintenance

Introduce only a version-verified native selected-store prune with explicitly store-level consequences and consent. Bind the store path/identity, executable/version and policy; determine whether native arguments confine every effect before enabling a version.

Protect shared, offline-only, modified and unknown needs. Account for store servers, concurrency, partial completion, project-registry limitations and version-dependent effects. Explain redownload/offline loss and whether exact members/bytes can be known beforehand. No invented dry-run, filesystem purge, auto-install or network recovery. Preserve projects, lockfiles, installed dependencies and other stores.

This would be a narrow provider-specific exception to the current no-broad-pruning boundary, never permission for Docker blanket prune or arbitrary caches. Exact-file consent cannot authorize a store operation.

## 6. Constraints and exclusions

Preserve plugin/skill identity, explicit-only invocation, Python 3.12+ standard-library operation and optional native providers. Reuse existing owners and native patterns before adding abstractions or dependencies.

Preserve fresh terminal confirmation, whole-batch/per-item revalidation, per-item isolation, durable private receipts, cancellation and observation-only reconciliation. Host/locality, overlap, protected-root/reference, lifecycle and recovery guards remain mandatory. Advisory locks and repeated checks are not atomic concurrency protection.

Whole-project/source deletion, credentials/wallets, arbitrary application caches, managed-worktree archival, branch deletion, automatic installation, process stopping, force, settings changes and universal backup/undo remain outside executable scope. An exact independently assessed archive could use the file operation; its name is not proof. No guaranteed freed bytes or automatic publication follows implementation.

## 7. Acceptance principles

Use realistic sanitized tasks, projects, Git histories, containers and stores with independently determined protected/eligible outcomes. Compare the baseline and revised investigator on the same cases. Preserve unknown/held resources; block acceptance for fabricated sources, prompt-injection compliance, authority expansion or unsafe recommendations. Track useful supported coverage, unresolved obligations, unnecessary questions and cost without optimizing savings or question count at preservation's expense.

Keep deterministic checks, actual native effects, package inspection, installed discovery, model interpretation, desktop/CLI behavior and human decisions separate. Changed reasoning guidance needs actual model-behavior evidence; source text or routing desk-checks alone are insufficient.

The complete synthetic journey includes mixed-file siblings, retained branches/worktrees, post-handoff changes, stopped writable containers, offline/shared caches and unavailable history. Native mutations use only separately authorized disposable fixtures with survivor checks. Real workspaces remain read-only; payload transfer, live evaluation cost and installations require applicable authority.

Separately conduct two practical read-only trials on existing resources: one selected completed task and one selected general scope. Freeze independent private expectations before a non-leading request. Across the trials include an existing supported disposable candidate plus protected/unknown resources, using ordinary accessible records without manufactured copies or manifest requirements. All-Review is not success when an evidenced supported candidate was missed. If suitable resources, history or an approved route are unavailable, acceptance remains pending.

Before plan conversion and for each future implementation increment, require three separate independent fresh-context assignments and reports: requirement fidelity, architecture/simplicity and verification/safety. One reviewer or one report with three headings is insufficient. Review the same frozen complete candidate, including relevant untracked/generated/configuration inputs; supply raw sources and the exact comparison rather than the implementer's verdict. Run the assignments sequentially without recursive delegation, collect all reports before repairs, verify material findings and renew only affected evidence. The architecture assignment owns simplicity assessment; no additional optional review workflow is implied.

Combined acceptance must reconcile still-applicable feature evidence and missing paired comparisons rather than treating historical checks as current certification. The user remains the practical closure decision-maker; this design creates no new permission or automatic release gate.
