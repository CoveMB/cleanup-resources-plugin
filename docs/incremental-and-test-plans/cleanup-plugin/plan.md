# Cleanup Resources Plugin: implementation status

Reconciled on 29 October 2026 against source baseline `d7ead1f`. This branch is the baseline for the proposed merge; work on other branches is not part of it. This record replaces accumulated delivery checkpoints, not the product's runtime contract.

## Owners and delivered scope

The [README](../../../README.md) owns installation, supported operations, configuration and limitations. The [skill](../../../skills/task-disk-review/SKILL.md) owns agent behavior; its helper implements mechanical checks. The original [source plan](../../../cleanup-plugin-plan.md) is historical design, not a statement of present support.

| Original increment | Present in this source tree | Acceptance boundary |
| --- | --- | --- |
| I1: portable task review | Bounded, read-only task discovery and explicit unknown coverage | macOS/Linux capability limits apply |
| I2: assessed project plans | Selected project review, independent content evidence, frozen host-bound plans | Agent interpretation is not authenticated by a digest |
| I3: global coverage and retention | Explicit configured roots, selected provider inventory and reported retention unknowns | No automatic whole-disk or conversation-history discovery |
| I4: read-only host certification | Historical installed Codex CLI/desktop observations are identified in README | They do not certify the current combined package or other clients |
| I5: exact-directory cleanup | Eligible assessed directories, terminal confirmation, durable intent/results and observation-only reconciliation | Supported local macOS/APFS only; the agent stops after review |
| I6: evidence capture guidance | Optional size advice and capture convention in reports | Smaller packets are not mandatory acceptance or evidence of safe disposal |
| I7: combined release acceptance | Some historical installed observations exist | Combined installed journey, practical usefulness and human acceptance remain incomplete |
| I8: native worktree cleanup | Selected ordinary linked Git worktrees with lifecycle/recovery guards | Managed, primary, pinned, shared or unknown lifecycle resources cannot be relabeled ordinary Git |
| I9: native Docker cleanup | Selected local resources through narrow versioned native contracts | Current containers with mounts or writable changes are blocked |
| I10: cache and temporary cleanup | Exact eligible directory cases and supported singleton npm cache entries | No general package-store pruning or pnpm operation |

OpenCode v2 and Antigravity installation instructions and explicit-only skill metadata are included. Native client discovery and model behavior remain untested. These client routes do not broaden filesystem, provider or cleanup support.

## Durable safeguards

- Keep explicit scope, holds and exclusions; unknown, denied or unsupported coverage is never empty usage.
- Separate observed content/identity checks from the agent's interpretation of purpose, ownership, consumers, release and recovery. Names, age, clean Git, completion or reclaimable labels do not establish disposability.
- Preserve originals, credentials, persistent/unique state, modified or offline dependencies, active consumers and unresolved obligations. Ask at most one useful grouped human question; do not ask for technical attestations.
- Review produces recommendations and frozen plans, not consent. Cleanup requires a fresh exact-plan interaction in the user's own terminal; no agent execution, approval flag or inherited consent.
- Preserve batch and per-item revalidation, cross-selection evidence/recovery dependencies, durable intent before mutation, stop-on-drift and observation-only reconciliation. No force, automatic backup, process stop, branch deletion or generic shell fallback.
- Inspect the actual allowlisted runtime package. Repository publication has a separate privacy boundary even though development records are excluded from that package.

## Remaining work

The [QA plan](qa-plan.md) maps current behavior to existing checks and separates test results from installed/native/human evidence. The [compatibility record](compatibility-plan.md) owns platform and client gaps. Neither document authorizes new host provisioning, installation, provider operations or cleanup.

The [context-aware follow-up](../context-aware-resource-cleanup/plan.md) is paused and proposed. Its task-history investigation, richer lineage, exact-file cleanup, generated-output assessment exception, assessed containers and pnpm maintenance are not delivered by this branch. Any resumption must compare the actual source tree with those requirements first.

Licensing remains undecided. Implementation presence, an open merge request and historical green checks do not establish release readiness or new cleanup permission.
