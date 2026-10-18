Simple Codex cleanup plugin plan — revised
Revision: 16 October 2026
Status: Implementation-ready design, subject to host and platform compatibility checks.
Objective
Create a small, portable, on-demand Codex plugin that shows where development disk space is being used, identifies resources that can safely be released, performs only selected and authorized cleanup, reports observed recovery, and discourages unnecessarily large evidence captures.
The priorities are:
- Substantial practical disk savings.
- Minimal implementation and maintenance complexity.
- Preservation of required work, local data, and task resumability.
- Compatibility across projects and computers.
- Clear human approval before deletion.
Design rule: Inspect broadly; delete narrowly.
The larger Portable Codex development disk management plan remains background research, not an additional implementation checklist.
1. Architecture
Distribute one Codex skill and one bundled local CLI helper as a plugin. Keep the helper independently usable from a terminal.
Use Python standard-library code, small internal modules, and short JSON plans and receipts. Python 3.12+ is the proposed minimum, subject to compatibility testing.
The skill handles conversational instructions, scope selection, explanation, and evidence guidance. The helper handles discovery, classification, revalidation, deletion, and reporting.
Keep: Task/project/global review, unregistered-resource discovery, exact plans, selected approval, exact directory cleanup, compact receipts, optional resource manifests, and evidence-capture guidance.
Exclude: Background services, schedulers, MCP servers, databases, custom dashboards, automatic deletion, blanket cache pruning, automatic backups, hooks, activity heartbeats, remote cleanup, process stopping, and automatic history reconstruction.
Git worktree and Docker deletion are excluded from the first release.
The plugin reduces accidental loss. It is not a security boundary against other processes running with the same user privileges.
2. User interaction and approval
The everyday workflow has two steps:
1. Review: “Review cleanup for this task,” “Review this project,” or “Review development disk space globally.”
2. Choose: “Clean A and C,” “Clean all eligible items,” or “Cancel.”
Proposed commands (illustrative, not installed):
- devspace review --task [path]
- devspace review --project <path>
- devspace review --global
- devspace apply --plan <plan-file> --select A,C
- devspace apply --plan <plan-file> --all-eligible
The helper must not execute because an agent supplied approved: true, a flag, or broad shell permission.
Prefer a verified Codex confirmation tied to the exact displayed plan. Otherwise, the agent stops after review and the user confirms directly in their own interactive terminal. Terminal interaction is a practical fallback, not cryptographic proof of human presence.
Approval is bound to the frozen plan, execution host, exact target identities, intended operations, consequences, and preconditions.
“All eligible” covers only entries marked Eligible in that plan. Reject overlapping parent/child targets, changed paths, and materially changed conditions. Require a new plan rather than silently expanding the selection.
3. Discovery modes
Task mode inspects the selected directory or worktree, relevant outputs, and any available task manifest. It uses a verified thread identity only when actually available.
Project mode inspects the selected Git or non-Git project, its relevant build/dependency/evidence directories, and Git-discovered linked worktrees. Discovery never authorizes deletion.
Global mode scans configured development roots plus supported read-only provider inventories, such as Codex/Git worktree locations, package-manager storage, and Docker disk usage.
Global coverage must be explicit: examined, skipped, inaccessible, and unconfigured locations. It does not claim a complete whole-disk audit.
For helper-created resources, an optional small manifest records exact path, purpose, project/task association, known consumers, retention requirements, and release checkpoint. Multiple consumers are supported. A manifest is historical evidence, not proof of inactivity.
Keep discovery bounded and cancellable. Avoid following symlinks, crossing unselected mounts, and repeatedly scanning large nested dependencies. Use metadata first. Denied access means unknown coverage, not zero usage.
Identify the actual execution host. Remote resources, synchronized storage, network mounts, and WSL boundary aliases remain report-only until separately supported.
4. Eligibility and legacy cleanup
Each candidate report contains its ID, exact path or provider ID, host, category, project association, meaningful size estimate, purpose/use evidence, retention requirements, rebuild implications, and assessment.
Four statuses:
- Eligible: Supported and adequately inspected, with a release decision, no known active consumers, no unresolved valuable state, and documented rebuild or accepted loss.
- Keep: Required or actively used, protected by a hold, or lacking adequate recovery.
- Review: Purpose, retention, ownership, release, or recovery needs further assessment.
- Unavailable: Essential inspection is denied or unsupported.
Existing unregistered resources can qualify after a specific assessment. Do not require historical manifests that never existed.
User confirmation may establish ownership, purpose, release, and accepted rebuild cost, but cannot override missing content inspection, known consumers, or required unrecoverable evidence.
Example:
ID	Candidate	Status
A	Verified rebuildable output in completed example	Eligible
B	Original failed-install reproduction	Keep
C	Verified ordinary dependency directory inside an old evidence packet	Eligible
D	Older evidence packet with unknown contents	Review


Approval of A and C does not authorize deletion of their parents, B, D, or newly discovered resources.
5. Resource policy
Category	First-release treatment
Scratch/build outputs	Exact cleanup only after content, purpose, consumers, release, and recovery checks
Generated-project dependencies and virtual environments	Exact cleanup where ordinary rebuildability and absence of unique modifications are established
Evidence/logs/source snapshots	Protect initially; individually assess disposable nested contents
Git/Codex worktrees and branches	Read-only inventory and release recommendations
Docker containers/images/caches/volumes	Read-only inventory when accessible
Shared package caches, browsers, toolchains	Report and explain supported native maintenance; no global pruning
Credentials, .env, databases, .wrangler/state, application history	Protected
Unknown or unrelated resources	Review-only or outside scope


Names such as tmp, dist, .next, and node_modules do not establish disposability.
No generic deletion fallback after a supported operation refuses. Add provider-specific cleanup only when measured usefulness and dedicated tests justify it.
6. Prevent evidence growth
The audit identified substantial accumulation inside implementation-review evidence. This indicates a prevention opportunity, but does not establish how many bytes are reclaimable.
Provide an optional capture convention:
1. Run installations, builds, tests, and reproductions in a separate working directory outside finalized evidence.
2. Preserve original failure/output before retrying. Keep attempts distinguishable.
3. Copy selected logs, screenshots, results, relevant source changes, and necessary inputs—not installed projects wholesale by default.
4. Keep a compact manifest: purpose, source commit/local changes, versions/platform, sanitized invocation, results, references, checksums when useful, and retention requirements.
5. Preserve unavailable/modified dependencies, unique inputs, and exact failure-specific state where reconstruction would otherwise be unreliable.
6. Warn about oversized packets or nested installed environments during later reviews. A review date is not a deletion deadline.
Offer a short opt-in instruction for existing development/evidence workflows, including the incremental-plan workflow. Installing the cleanup skill alone does not enforce the convention.
Do not automatically modify AGENTS.md, existing plugin instructions, or application settings. Do not add general compression, deduplication, or reproduction machinery.
Legacy packets require individual assessment; preserve necessary original evidence and document approved reductions.
7. Git worktrees and Codex retention
A PR, completed turn, or archived chat does not establish that a checkout is disposable. Commits do not preserve dirty, untracked, or ignored files.
Verified edge case: In an isolated Git 2.47.3 Linux test, a worktree with an ignored .env was clean under ordinary git status --porcelain, and non-forced git worktree remove deleted the ignored file.
Therefore, clean Git status and absence of --force are insufficient worktree-preservation guarantees.
In v1:
- Inventory worktrees and associated activity, status, ignored files, locked state, detached/unpushed commits, and potential consumers.
- Recommend release only after accepted completion or handoff, normally after review/merge.
- Explain isolated-checkout resume options.
- Never pass worktree roots to the generic directory executor.
- Never delete branches or worktrees.
Inspect effective Codex CLI/desktop automatic-retention settings read-only where supported. Warn when independent Codex cleanup could remove something the plugin recommends retaining.
Do not alter retention settings, or promise ignored evidence survives native snapshots, without verified installed-version behavior.
Future worktree removal must have its own native lifecycle adapter and ignored-file/recovery tests.
8. Essential safety and resilience
The executor may remove only individually approved, exact local directories with verified disposable contents.
Never permit generic deletion of a project root, worktree root, home directory, configured development root, mount, provider-managed state directory, or protected ancestor.
Before plan creation and apply, validate root containment, target identity, resource classification, retained/ignored contents, consumers, release, recovery consequences, and platform support.
Known consumers block cleanup. Unknown activity is not proof of inactivity; unresolved cases remain Keep or Review.
Apply sequence:
1. Validate saved plan, host, digest, selected IDs, intended effects, and absence of overlapping targets.
2. Acquire one host-local helper lock, recognizing that it cannot control unrelated agents, editors, or builds.
3. Revalidate the entire selected batch and each item immediately before deletion.
4. Reject replaced paths, link/mount traversal, changed contents, unsupported filesystem operations, or material consumer/retention drift.
5. Use tested filesystem protections, including appropriate descriptor-based operations. Check platform-specific symlink-attack resistance instead of assuming Python is universally safe.
6. Write a durable, compact intent record outside the target before mutation and a result afterward.
7. Stop remaining actions on failure/cancellation. Reconcile interrupted operations before retrying.
8. Never switch to force or arbitrary shell deletion after a refusal.
Keep receipts small: identity, operation, warnings, result, and measured outcomes. Do not store raw transcripts, large listings, secrets, or file contents.
If receipts cannot be safely written, deletion must not start.
These safeguards reduce risk; they do not guarantee detection of all concurrent changes.
9. Recovery and space accounting
The cleanup offers Keep or permanent removal with disclosed loss/rebuild implications. It does not promise automatic backups or universal undo.
Same-disk Trash/quarantine commonly retains occupied blocks and is not an immediate disk-saving strategy.
Differentiate restoring tracked source, reinstalling dependencies, and reproducing an exact original failure.
Report logical and allocated size when meaningful, with uncertainty around hard links, APFS clones/snapshots, shared layers, and concurrent writes.
Avoid parent/child double-counting. Measure host filesystem free space before and after cleanup and present observed net change, not perfect resource-by-resource attribution.
Do not manipulate Docker VM images directly. Treat VM maximum capacity separately from actual allocated storage.
10. Defaults and portability
Small settings only: development roots, exclusions, holds, and optional thresholds.
Setting	Initial default
Execution	Manual; no automatic deletion
Evidence warnings	Above 250 MiB; request explanation above 1 GiB
Low-space warnings	Below 10%, emphasized below 5%, when invoked
Retention	Review after completion/handoff; no age-based deletion
Backups	None automatically
Global scope	Configured development roots plus supported provider inventories


Thresholds are adjustable warnings, not universal safety limits.
No hard-coded usernames, project paths, machine-specific assumptions, or mandatory package manager.
Design for macOS, Linux, and Windows through capability detection. Pilot mutation on macOS first; other hosts may remain read-only until their platform-specific deletion safety and failure tests pass.
A Python runtime is a documented prerequisite. A cloud Codex session has access only to its actual execution environment, not implicitly the user's Mac.
11. Delivery milestones
Milestone A — Read-only inventory and compatibility proof
Package and test skill/helper invocation in the installed Codex CLI and desktop. Implement task/project/global inventory, finite reports and plans, unregistered evidence detection, ignored-file inspection, provider coverage reporting, and read-only Codex retention checks.
Verify actual host-confirmation behavior. If human approval cannot be reliably linked to the plan, use a separately confirmed terminal workflow.
Milestone B — First usable release
Enable only tested exact local-directory cleanup on supported platforms. Include selection, confirmation, guards, current-use/release checks, lock, revalidation, intent/results receipts, failure handling, evidence guidance, and measured-space reports.
The first usable release must be able to reclaim space from existing, individually assessed build/dependency/evidence subdirectories, not only future resources.
Optional later modules
Add Git/Codex worktree lifecycle cleanup, exact Docker container/image cleanup, or additional platform executors only when measured needs and independent tests justify them. No mandatory expansion roadmap.
12. Acceptance tests and workflow
All destructive tests must use disposable fixtures—not real user work.
Required cases:
- Ignored .env in an otherwise clean Git worktree is detected and preserved; worktree roots are never passed to the directory executor.
- Dirty, staged, untracked, detached, locked, and unpushed states are assessed correctly without mutation.
- .env, databases, Wrangler state, modified dependencies, original failures and required evidence are not mistaken for ordinary disposable files.
- Known consumers and unresolved use prevent inappropriate deletion.
- Existing unregistered but individually validated resources can become eligible.
- Path substitution, symlinks, mounts, overlapping targets, content changes, permission denials, unsupported filesystem semantics, and competing helper instances fail closed.
- Approval includes only selected eligible rows; agent flags do not constitute human confirmation.
- Cancellation, partial deletion, crashes and retries leave reconcilable receipts; replacement resources survive.
- Unavailable provider access is shown as incomplete coverage.
- Disposable cleanup demonstrates observed allocated-space recovery where supported.
- Actual CLI and desktop integration are tested independently on mutation-enabled host/platform combinations.
End-to-end example
1. The user requests a project review.
2. The report identifies a rebuildable .next directory (A), an original failed reproduction (B), verified nested node_modules (C), and an unknown evidence packet (D).
3. A and C are Eligible, B is Keep, and D is Review.
4. The user approves A and C through a verified confirmation flow or their own terminal.
5. The helper revalidates, records intent, removes only A and C, and records outcomes.
6. The report shows observed free-space change, limitations of attribution, and how ordinary dependencies can be rebuilt later.
7. A later review flags new oversized evidence and provides the optional capture convention.
B and D remain untouched.
13. Deliverables and definition of done
Deliver:
- Bundled Codex skill and terminal helper.
- Automated disposable-fixture tests.
- Example reports, plans, approvals, and receipts.
- One concise README covering installation, requirements, scope, configuration, operations, approval, evidence practices, recovery, and troubleshooting.
Do not create additional services, dashboards, extension frameworks, or a large operations manual.
Acceptance: The real Codex host or terminal confirmation works; the supported platform passes destructive safety tests; a user-reviewed pilot demonstrates meaningful measured recovery without losing required work or the agreed resume path; and evidence produced under the capture convention becomes measurably smaller in representative workflows.
Do not promise a fixed GiB savings target from historical audit totals.
References and remaining verification
- Codex plugin documentation
- Git worktree documentation
- Python shutil.rmtree documentation
- pnpm store
- Docker resource pruning
- Docker Desktop storage on Mac
- Cloudflare local development data
Remaining implementation gates are Codex confirmation compatibility, actual retention settings, host filesystem protections, and provider accessibility. These are validation tasks, not reasons to expand the architecture.
Uncertainty: The design and Git edge-case test have been reviewed, but the plugin has not been implemented or validated on the user's Mac. The principal risk of an incorrect assumption lies in Codex-host behavior and platform-specific filesystem semantics.