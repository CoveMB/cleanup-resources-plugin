# Context-aware resource cleanup: proposed QA plan

Status: paused; no new implementation or evaluation is reported here. Reconciled on 29 October 2026 against `d7ead1f`. The [design](../../superpowers/specs/2026-10-19-context-aware-resource-cleanup-design.md) owns requirements and [plan.md](plan.md) maps the proposed increments.

## Behavioral acceptance matrix

| ID | Required observation | Material negative cases |
| --- | --- | --- |
| Q01: task context | Trusted task/resource binding, current-versus-historical attribution, specific missing obligation and useful report | Original failure, shared use, later hold, missing earlier turns, fabricated note, injection, abandoned versus pending work, vanished/replaced resources |
| Q02: general/history | Authorized categories, relevance ranking, examined/skipped/unavailable coverage and useful fallback | Troubleshooting/performance/repair requests, title collisions, archived handoff followed by reuse, truncation/permission failure, unrelated personal storage, unavailable APIs |
| Q03: lineage | Bound repo/common directory, full HEAD/ref/destination; separate ancestry, patch/squash evidence, retention and release | Later unmerged commit, revert, stale/shallow refs, missing objects, detached HEAD, dirty/ignored data, private recovery, path/branch reuse, active reviewer |
| Q04: exact file | Only the selected independently evidenced regular file is removed on a supported fixture | Preserve parent/useful sibling/secret/link/hardlink alias and reference sources; reject content/ancestor drift, overlaps, unsupported storage and unknown schema |
| Q05: generated output | Complete inspection, resolved purpose/consumers/release and exact accepted-loss basis; truthful absence of independent baseline | Partial bytes, source/secret/database/dependency disguised as output, required failure evidence, fabricated origin, unknown owner or generic cleanup request |
| Q06: assessed container | Supported full-ID removal after complete changed-content/mount assessment; survivor checks | Running/restarted state, unique DB, unreadable paths, unknown mounts, timeout; bind sources and all named/anonymous volumes survive |
| Q07: pnpm store | Tested version confines effects to the selected store/policy; consent describes store-level/offline consequences | Shared/offline/modified/unknown needs, server/concurrency, ambiguous path, unsupported version, partial/timeout result; projects, lockfiles, dependencies and other stores survive |
| Q08: combined journey | Actual installed candidate connects investigation, assessment, selection and documented handoff | Mixed files, retained worktree/branch, changed post-handoff state, writable container, shared/offline cache and unavailable history |
| Q09: paired investigator comparison | Baseline and revised investigator see the same sanitized cases and independent expected decisions | Missing baseline, unequal context or changed configuration cannot be presented as a measured improvement |
| Q10: existing-resource trials | Separate task and general read-only reviews on existing resources with independent non-leading expectations | All-Review with an evidenced supported miss, manufactured baseline, invented source, unsafe recommendation or scope expansion cannot pass |

## Scope and privacy invariants

Bind holds/exclusions before any discovery. Agent-prepared paths must resolve to the intended review scope while existing CLI relative-path behavior stays compatible. Check that excluded resources are never traversed, not merely omitted from the final report.

Bound total native metadata before acquisition, including every pinned item a listing may return. If the API cannot guarantee the bound, use known relevant IDs or bounded archive pages instead. Do not over-fetch and truncate. History limits are owned by design section 2; test exhaustion, missing pagination and unavailable access honestly.

Do not read private databases/transcripts, expose unrelated secrets, manufacture ownership from titles or forward private contexts to an unapproved provider. Attribute observed facts, history, interpretation and human decisions separately. One useful grouped human question cannot become a technical questionnaire.

## Deterministic and native verification

Reuse existing application tests and fixtures where their contracts apply. Assert observable reports, preserved bytes/identities, exact operations and outcomes; do not substitute source-text assertions for reasoning or user behavior.

New operations must preserve old plan semantics, reject unknown contracts and maintain batch/confirmation/per-item revalidation. Exercise cross-operation evidence/recovery dependencies, unsupported platforms, drift, cancellation, interrupted or partial outcomes and observation-only reconciliation. Unknown outcomes never permit retry.

Native feature trials require separately authorized isolated disposable fixtures on the actual supported tool/host combination. Verify survivors after success and preservation after negative paths. Mocked calls or skipped native tests cannot establish these effects. Retain needed failure evidence; fixture cleanup is a separate scoped action with final-state verification.

Inspect the actual runtime ZIP after any allowlist/module change for complete dependencies, private/local data and VCS material. Exercise the extracted package. Then distinguish native discovery, explicit invocation, model interpretation, CLI behavior, desktop behavior and effective settings for the actual installed subject.

## Paired model comparison

Freeze independent expected protected/eligible outcomes before evaluation. Record baseline/revised source or package subjects, model/tool configuration, permitted context, scope and differences. Use the same sanitized cases and expectations, including missing context, contradictory later evidence, injection and unavailable tools.

Measure supported useful candidacy, protected/unknown preservation, source coverage, missed candidates, unnecessary questions and cost separately. Do not optimize reclaimable bytes or fewer questions at the expense of correctness. Static desk-checks and fixture tests supplement, but cannot replace, changed investigator behavior evidence.

Historical work did not establish a complete matched baseline/revised general-history comparison. Treat that as an outstanding obligation; do not infer missing baseline results from revised-only runs. Refresh only changed inputs or unresolved coverage and reuse still-applicable evidence.

## Two practical read-only trials

Separately evaluate one selected completed task and one selected general scope using existing resources and ordinary accessible records. Across the two trials, require an actual supported disposable candidate plus protected/unknown resources. Do not create copies, manifests or baseline trees to manufacture qualification.

Freeze private independent expected decisions before a non-leading prompt containing only authorized scope and exclusions. Compare actual versus expected decisions, source coverage, supported misses, questions and cost. All-Review does not pass when useful supported candidacy was missed; unsafe recommendations, invented provenance, injection compliance or permission expansion block acceptance.

If suitable resources, source/history access or an authorized evaluation route are absent, report acceptance pending. These trials establish assessment only, not removal, reclaimed space or general safety certification.

## Evidence and review closure

Apply the separate independent implementation assignments and reports required by design section 7; distinct headings in one review do not satisfy that requirement. The final combined candidate must reconcile feature-native results, package/installed observations, Q09 paired comparisons and Q10 practical trials. Historical tests on other branches do not validate absent code.

Real workspaces remain read-only. Installation, external payload transfer, live-model cost and native mutations require applicable separate authority; this paused plan supplies none. The user is the practical acceptance decision-maker. No test result authorizes production cleanup or automatic publication.
