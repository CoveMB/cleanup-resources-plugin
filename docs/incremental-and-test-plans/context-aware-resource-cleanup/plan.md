# Context-aware resource cleanup: proposed incremental plan

Status: paused future program. Reconciled on 29 October 2026 against source baseline `d7ead1f`. The current branch is the prospective merged baseline; implementation recorded on other branches is not current support and is not adopted by this document.

The [design](../../superpowers/specs/2026-10-19-context-aware-resource-cleanup-design.md) owns requirements. The [QA plan](qa-plan.md) owns acceptance and the [handoff](handoff.md) owns continuation status. Current runtime behavior remains in [README](../../../README.md).

## Current support versus proposal

| Area | Current branch | Proposed change |
| --- | --- | --- |
| Task assessment | Explicit scope and supplied/current context; helper validates content/reference evidence | Reconstruct relevant task context through trusted native access and explain specific missing obligations |
| General/history investigation | Explicit configured global roots/providers; no automatic history discovery | Metadata-first bounded scope and relevant recent/archive history |
| Worktree lineage | Bounded Git inventory and ordinary linked-worktree safeguards | Distinguish ancestry, patch/squash evidence, retained history and release |
| Exact files | No top-level exact-file removal operation | Versioned file operation preserving mixed-directory siblings |
| Generated output without baseline | Existing inventory/source comparison required | Narrow truthful assessed-output method with scoped accepted loss |
| Writable/mounted containers | Current contracts reject mounts and writable changes | Separate assessed-container contract with safe inspection and mount/volume preservation |
| pnpm | No selected-store prune | Version-verified store-level contract and separate consent |
| Combined acceptance | Historical subject-specific observations only | Paired investigator comparison, installed journey and two existing-resource read-only trials |

## Increment scopes and dependency order

These scopes describe future work, not permission to execute or claims of completion. Reinspect actual callers and schema allocation before selecting files or helper names; earlier proposed identifiers are not architectural commitments.

| Increment | Outcome and likely canonical owners | Required boundary |
| --- | --- | --- |
| I01: task-context assessment | Skill/README and existing assessment/report diagnostics | Keep evidence classes distinct, bind holds/exclusions before discovery, no new eligibility method |
| I02: general/history investigation | Skill and explicit root/provider preparation; existing global/report paths only if needed | Build on I01; bound total metadata including pinned entries before acquisition; no private storage scan |
| I03: worktree lineage | Existing Git inventory/report owner and skill interpretation | Build on I01/I02; local refs disclosed, retained history is not release, no new removal authority |
| I04: exact-file cleanup | Existing review/plan/cleanup/CLI dispatch | After I03 in shared-contract delivery order; new version, full no-follow/content checks, preserved siblings/references |
| I05: assessed generated outputs | Existing assessment owner and affected file/directory operations | Build on I04; generated-output-only exception, explicit loss, no fake comparison or override of protected state |
| I06: assessed containers | Existing Docker/plan/cleanup contracts | After I05; supported daemon/version, full changed-content assessment, preserved bind/volume sources |
| I07: pnpm store maintenance | Narrow provider adapter plus existing configuration/plan/cleanup and package allowlist | After I06 and using I02 selected scope; native confinement/version proof, store-level policy/consent |
| I08: combined installed/practical acceptance | Final package and shared behavior scenarios | I01–I07 applicable results, paired comparison reconciled, complete synthetic journey and separate practical trials |

The shared dispatcher/schema paths require sequential integration unless write scopes are demonstrably independent. Each operation ships its complete validation/execution/documentation/preservation contract together. Code rollback cannot restore deleted bytes or retract disclosed context.

## Delivery requirements

- Start from the actual candidate and preserve existing work. Identify current investigator/package subjects before changing them so baseline comparisons remain possible.
- Reuse current assessment, report, native-provider and recovery owners. Keep v1–v4 semantics; choose unused versions only after current source inspection.
- Retain exact selection, cross-operation evidence/recovery dependencies, confirmation, drift checks, private durable results, cancellation and observation-only reconciliation.
- Keep changed behavior's deterministic and actual native/model evidence with its increment. I08 combines and reconciles that evidence; it does not excuse deferring feature safety checks.
- Apply design section 7's separate independent implementation-review assignments and reports. Renew only materially affected coverage after changes.
- Treat public package/repository privacy separately from local operational evidence. No historical user approval, private payload transfer or live evaluation budget is inherited here.

## Completion boundary

None of I01–I08 is asserted delivered by this branch. Historical implementation and reviews elsewhere may be inputs to a separately authorized comparison, not substitutes for source inclusion or acceptance.

Future closure needs the [QA obligations](qa-plan.md), explicit unsupported/gap reporting and the user's practical acceptance. A merge request, passing fixture suite or installed discovery alone cannot close investigation quality, provider safety or real-user usefulness.
