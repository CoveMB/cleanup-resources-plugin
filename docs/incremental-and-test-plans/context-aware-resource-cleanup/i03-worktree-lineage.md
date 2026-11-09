# I03 Local Worktree Lineage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give project/global reviews explicitly bound, local Git lineage observations without changing removal eligibility or saved plans.

**Architecture:** Add one optional review input for one checkout. After all ordinary discovery, candidate/provider assessment and plan construction, the outer `review_scope` routes an already-matched observation to `git_inventory.py` using only the remaining top-level time. Reuse its bounded runner and existing no-follow metadata readers; present one advisory result without changing candidates, scope roots or the frozen plan. Keep retention separate from historical integration comparisons.

**Tech Stack:** Python 3.12+ standard library; optional local Git; existing `unittest` disposable Git fixtures.

**Spec:** [Canonical design](../../superpowers/specs/2026-10-19-context-aware-resource-cleanup-design.md) §§3, 4, 6, 7; [incremental plan](plan.md) I03; [QA plan](qa-plan.md) Q03. Historical implementation baseline: `07e4407`, tree-identical to the reviewed I02 guidance repair `7023da9`; its 23 Python files remain byte-identical to `9bdec7e`/`76251ea`. Reconcile later edits before any continuation; this baseline does not replace the actual implemented subjects below.

**Status:** Both tasks are implemented. Task 1 local `21d1e11` was published as `85cd34e`; Task 2 production repair local `1753e55` was published as `38a1e76`. The later `ae27f0e` fixture repair changes tests only; all 15 runtime members match `1753e55`/`38a1e76`. Three independent source reports per task and affected production-repair reviews closed before CI. The test-only repair requirements and safety reviews approved, with architecture carried for the unchanged runtime; affected source-review gates are closed. It was published as tree-identical `d26d3c2`; the final hosted matrix passed all four jobs. See [QA evidence reconciliation](qa-plan.md#i03-evidence-reconciliation--9-november-2026) for exact source/tree/publication attribution, original hosted failures, finite paired model evidence and remaining acceptance.

The task checklists below preserve the reviewed execution instructions and their original granularity. Their unchecked state is historical plan notation, not a claim that source is absent; this reconciliation does not infer every original procedural step from source presence or mechanically mark it complete. The agentic-worker instruction above applies to implementation execution, not to this evidence reconciliation.

## Global Constraints

- “Preserve plugin/skill identity, explicit-only invocation, Python 3.12+ standard-library operation and optional native providers.”
- “Bind the actual repository/common directory, checkout path, full HEAD, retained ref and destination before interpreting integration.”
- “Local refs stay explicitly local unless a refresh is separately authorized.”
- “Neither retention nor patch similarity establishes release.”
- “Primary, managed, pinned, shared, dirty or unknown-lifecycle resources remain protected”; retain attachment-scoped lifecycle, consumer and existing executor guards.
- No new module, dependency, removal operation, plan version, registry, fetch, automatic destination, installation, provider payload transfer, branch deletion or owner messaging. Do not change `git_worktree.inspect/remove`, `_assess`, `freeze_review`, apply or reconcile semantics.

## Review Focus

1. Path/ref drift or persistent shallow/graft-policy changes must invalidate derived relations, including after integration comparisons (Tasks 1/2 drift tests).
2. Excluded metadata, unmatched inputs and global host/scope failures must cause neither native probing nor direct acquisition of prohibited targets (Task 1 acquisition tests).
3. Exit 1, shallow history, unavailable/noncommit objects and private recovery must not become false integration or recovery assurances (Task 1 uncertainty/type tests).
4. An older source, cherry-pick, squash or later revert must not become integration of the current HEAD or proof of current semantic preservation (Task 2 history tests).
5. Lineage exhaustion must preserve ordinary candidates/scope/plan across v1–v4 wrappers; CLI/package/text must expose advisory incompleteness separately (Task 1 final-phase tests and both tasks' end-to-end checks).

---

## Small input and output contract

Use only `review --git-lineage FILE`, loaded by existing `read_document`. Support `--project` and `--global`; reject task-mode use before discovery. One requested checkout per invocation deliberately avoids mapping/registry machinery:

```json
{
  "schema_version": 1,
  "repository": "/already-selected-or-discovered/repository",
  "path": "/registered/checkout",
  "expected_head": "FULL_CURRENT_COMMIT_OID",
  "retained_ref": "refs/heads/retained-topic",
  "destination_ref": "refs/heads/integration-destination"
}
```

Task 2 additionally permits `integration`: either `{ "kind": "merge", "source_commit": FULL_OID, "destination_commit": FULL_OID }` or the same with `kind: "squash"` and mandatory `source_base_commit: FULL_OID`. These are caller-supplied historical claims, not authenticated records. The current expected HEAD need not equal the older claimed source.

Validation is exact-key/type validation, the existing 1 MiB document limit, absolute lexically normalized paths of at most 4096 characters, bounded full refs (at most 1024 characters, only `refs/heads/…` or `refs/remotes/…`), and lowercase full 40/64-character hex OIDs. Reject NULs, unknown fields and shorthand/option-shaped refs. Validate full ref syntax using `git check-ref-format` only after scope/exclusion checks; format rejection is invalid input (`ValueError`), whereas unavailable/noncommit refs are unavailable observations. Resolve only validated literal refs. Match OID length to observed `sha1`/`sha256`; unsupported formats stay unavailable. Resolve a ref to its OID and require `cat-file -t` to say `commit`, rather than silently peeling arbitrary objects.

Keep `inventory_git`'s signature and ordinary call placement unchanged. The public `plans.review_scope(..., git_lineage=None, **options)` consumes/validates this input without forwarding it to `_review_scope`, `_review_docker_scope`, nested root reviews or `review_global`. Immediately before its final return—after v3 Docker, v4 npm, optional cache discovery, aggregation and the last ordinary plan/digest update—initialize `report["git_lineage"]` to `not_examined`. Match the request using only the returned project's `scope.canonical`/`git.worktrees` or global `git_inventories[].path/worktrees`. Require one exact repository/checkout match with successful ordinary status; absent a match, perform no acquisition. Carry only that record to `observe_lineage`, at most once. Recheck scope/exclusions and identities before probing; a prior match is not fresh authority.

Use the already-created outer `review_scope` deadline, not a new budget. If no time remains, or ordinary scope/host/cancellation prevents inspection, leave `not_examined` without filesystem/native acquisition. Use the final plan's policy exclusions for this extra advisory phase; this may conservatively skip provider storage already excluded by ordinary policy. No global owner/signature change or intermediate lineage work is needed.

The advisory result contains:

| Field | Contract |
| --- | --- |
| `status`, `reason`, `observed_at` | `observed`, `partial`, `unavailable`, `changed`, or `not_examined`; fixed payload-free reason and UTC observation time |
| `binding` | Actual repository/common/admin paths and identities; checkout/marker identity; actual full HEAD and branch/detached state; supplied refs and resolved full OIDs; executable identity and object format |
| `retention.head_in_ref`, `ancestry.head_in_destination` | Independent `true`/`false`/`null` facts; errors never mean false |
| `recovery` | Supported private HEAD/ORIG_HEAD/reflog roots retained: `true`/`false`/`null`, count and explicit coverage/reason; no author/message payload |
| `integration`, `patch_equivalence` | `not_requested` in Task 1; Task 2's exact facts and limitations below |
| Fixed limits | `report_only: true`, `refs_local_only: true`, `remote_freshness: "unknown"`, `release: "not_established"`, `current_use: "unknown"`; recovery reachability does not certify all content availability |

No requested input means no new lineage fields/probes or completeness penalty. After ordinary aggregation, any requested status other than `observed` makes outward `report.coverage.complete` false (CLI exit 2 unless invalid input/cancellation takes precedence). `not_requested` comparisons and fixed unknown remote freshness alone are not incomplete observations. Preserve ordinary status, candidates, scope roots, plan/digest and byte-accounting completeness exactly; do not rerun aggregation, assessment or `freeze_review` after lineage. Never put the advisory object/input into the plan or consult it during apply.

### Task 1: Ship usable bound current-state lineage and recovery reporting

**Files:** Modify `skills/task-disk-review/scripts/devspace/{git_inventory,plans,report}.py`, `skills/task-disk-review/scripts/devspace.py`, `README.md`, `skills/task-disk-review/SKILL.md`, `tests/test_git_inventory.py`, `tests/test_plans.py`, `tests/test_global_inventory.py`, `tests/test_package.py`. Reuse, without changing destructive behavior, `git_worktree._identity`, `_metadata_file`, `_administration_state`, `_head_history` and `plans._open_parent` through local imports.

**Interfaces:**

- Add `validate_lineage_request(document: dict) -> dict` in `git_inventory.py`; no filesystem/native access in shape validation.
- Add `observe_lineage(repository: Path, record: dict, request: dict, *, exclusions: tuple[str, ...] = (), deadline: float, cancelled: Callable[[], bool] | None = None) -> dict` there. It never mutates the supplied ordinary record; its local `_git` wrapper uses the passed absolute deadline and existing cancellation/output cap.
- Extract only the existing overlap predicate as `_check_exclusions(directory: Path, excluded_paths: tuple[Path, ...]) -> None`; ordinary inventory's local check and the new observer share it. Keep `inventory_git`'s public signature unchanged.
- Extend only public `plans.review_scope(selected, *, npm_caches=(), git_lineage=None, **options)` and finalize there as specified above. Catch advisory cancellation there with the existing `report.cancelled`/exit-130 precedence. Add `_lineage_text(observation: dict) -> list[str]` in `report.py`, called by `render_text`.

- [ ] **Step 1 — Write real-Git failing tests using `GitInventory.git`, its isolated executable wrapper and `snapshot`.** Add the following `test_lineage_*` cases; construct histories with ordinary `git worktree add`, `commit`, `update-ref`, `checkout` and, only within fixtures, `reset`. Every read-only trial compares before/after fixture bytes plus checkout/admin inode identities; report/error text must omit secret/filter/reflog sentinels.

| Test suffix / fixture | Required assertions |
| --- | --- |
| `retained_not_integrated` | Retained topic contains HEAD; explicit destination does not; misleading upstream does contain HEAD. Assert `retention.head_in_ref is True`, `ancestry.head_in_destination is False`, full bound OIDs and `release == "not_established"`. Default inventory issues no lineage commands. |
| `bound_scope_and_refs` | Malformed document/task mode rejects before discovery. Missing ref, noncommit ref, shorthand/revision expression, unrelated repository and unregistered target produce the specified invalid/unknown result, without opening unmatched targets. A newline checkout path survives exact binding. SHA-1 and locally supported SHA-256 retain full IDs; unsupported Git/format reports unavailable. |
| `exclusions_before_acquisition` | Cover selected/linked/descendant/case-alias exclusions, external common/admin paths, an excluded `logs/HEAD`, and unmatched repository/checkout inputs. Alongside `_git`, instrument/fail at `_metadata_file`, `_administration_state`, `_head_history` and targeted descriptor open/traversal boundaries for the prohibited resource. No excluded/unmatched acquisition may occur, even if discarded. Allow nonexcluded link/parent metadata needed to identify the boundary. Scope spies to product execution; take preservation snapshots outside them. Unaffected status stays useful; global host/budget failures stay `not_examined`. |
| `unknown_is_not_negative` | Genuine shallow local clone; removed required loose object; graft metadata; replacement ref; `GitRefused(1)` versus `GitRefused(128)` at the ancestry boundary; timeout/output cap/cancellation. Only the valid complete ancestry query's exit 1 yields false. Verify no fetch/lazy hydration or external filter execution, and preserve existing status. |
| `private_recovery_and_status` | Detached/locked/dirty/untracked/ignored facts remain visible and report-only. Supported linked HEAD old/new reflog roots and ORIG_HEAD retained/unretained give true/false; private refs/config, malformed/over-128-record log and primary administration give unknown. Report no reflog author/message text. |
| `recovery_roots_are_commits` | Put existing blob/tree OIDs in syntactically well-formed old/new reflog records and separately in ORIG_HEAD; include malformed ORIG_HEAD and a full OID naming a missing object. Assert recovery null/unknown, while valid retention/ancestry facts survive. Verify each distinct nonzero root is directly type-checked before any reachability conclusion; no peeling. Preserve fixture bytes and suppress author/message sentinels. Ordinary absence of ORIG_HEAD is allowed. |
| `binding_drift` | Move HEAD, branch, retained/destination ref, checkout inode or `.git`/common linkage at a deterministic patched native-call boundary. Assert `status == "changed"` and all derived relation values null; a preexisting `expected_head` mismatch gives the same result. |
| `graph_policy_drift` | In a real nonshallow fixture, persistently create `common/shallow` between initial policy inspection and ancestry, leaving HEAD/refs/directory inodes unchanged; separately introduce graft metadata. Assert changed/unavailable lineage and null derived relations, never a valid negative. Verify the final policy check executes. |

Add `test_git_lineage_final_phase_preserves_review` in `test_plans.py`: with an otherwise eligible assessed fixture, deterministically exhaust the remaining deadline inside lineage and compare candidates, scope roots, plan/digest and size completeness exactly to a no-lineage control. Include v3/v4 provider-review fakes using existing fixture patterns; assert all ordinary assessments, optional cache discovery and final plan updates finish before lineage begins. Also exhaust time before finalization and assert no advisory acquisition. Add `test_git_lineage_global_later_root_survives_exhaustion` with a later independently assessable root and the same equality assertions. Outward coverage alone becomes incomplete; cancellation retains precedence.

Add `test_git_lineage_global_scope_and_text` in `test_global_inventory.py` using its existing Git fixture, and `test_git_lineage_extracted_cli_contract` in `test_package.py`: invoke extracted JSON/text/project/global paths, including advisory timeout/exit 2 and assessed-plan equality. Isolate the CLI child's Git executable/config explicitly; the fixture's process-local `shutil.which` patch does not reach a subprocess. Existing status-only behavior remains compatible.

- [ ] **Step 2 — Establish red.** Run `python3 -B -m unittest discover -s tests -p test_git_inventory.py -k lineage -v`; then run the same discovery command with `-p test_plans.py -k git_lineage`, `-p test_global_inventory.py -k git_lineage`, and `-p test_package.py -k git_lineage`. Expect absent argument/field/CLI failures, not fixture setup failures.

- [ ] **Step 3 — Implement the final advisory phase and observer.** Validate input before discovery, then leave the ordinary call flow untouched until the public wrapper's final phase. Match from returned observations before resolving/statting any requested path; check remaining time, scope and policy before acquisition. Run shared exclusions before every new metadata boundary or native command, including ref validation. Resolve/check `.git`/common metadata without following links, bind identities, require each top-level root to equal its checkout path, and require both common directories to agree. Reuse the status/filter refusal; an unsuccessful ordinary status does not seed usable lineage.

Use `--no-replace-objects` on every new lineage command. Before graph queries, capture graph policy: exclusion-guarded no-follow `common/shallow` identity-or-absence, `--is-shallow-repository`, and continued absence of `common/info/grafts` (refuse grafts without reading contents). Obtain actual HEAD/branch, validated refs and object format; compare HEAD with the request and ordinary record. Use resolved OIDs thereafter. `merge-base --is-ancestor A B` yields true on exit 0, false on exit 1 only while the nonshallow premise survives final revalidation, and null on other errors. Shallow queries remain unknown; missing objects never trigger fetch. Do not alter shared `_git` exception semantics.

For ordinary linked administration, reuse the bounded readers for both old/new HEAD roots and ORIG_HEAD. When ORIG_HEAD exists, require one full nonzero OID, not a revision expression. Directly run `cat-file -t <oid>` for every distinct nonzero recovery root under the same runner/budget/policy and require exactly `commit`; never peel types. A blob/tree/tag, missing object, malformed/unvalidated root or error leaves recovery unknown, while independent valid retention/ancestry may survive. Only after all roots pass may `rev-list --max-count=1 <roots> --not <retained-oid>` distinguish retained/unretained history. Incomplete/private administration or shallow history stays unknown; primary recovery is unsupported. Construct supported fixtures using primary-checkout commits and linked HEAD moves; do not relax scratch/private-state refusals or change the destructive adapter.

After all observations—including Task 2 comparisons—reread checkout/repository/common/admin/marker/executable identities, HEAD/branch, refs, inspected administration and graph policy (shallow metadata/state and graft absence), using the same exclusion/no-follow guards. Persistent policy drift invalidates derived relations even with unchanged HEAD/refs/inodes. If revalidation cannot finish within budget, derived facts lack a valid final binding and stay unknown. This remains a before/after check, not atomicity. Keep failures local to the final advisory result and outward coverage; preserve ordinary status, candidates/scope/plan and size completeness. Render the bound facts and limitations in both formats.

- [ ] **Step 4 — Document the working surface.** Add one README invocation/schema example and concise skill guidance: the agent supplies bindings/destination from scoped evidence, distinguishes retained history from integration, checks current lifecycle/active reviewers and keeps missing evidence unresolved. Do not ask users to fill in technical Git facts or infer a default destination.

- [ ] **Step 5 — Establish green.** Run the focused red commands, then `python3 -B -m unittest discover -s tests -p test_git_inventory.py -v`, `-p test_plans.py -v`, `-p test_global_inventory.py -v`, and `-p test_package.py -v`. Require new actual-Git/acquisition/final-phase/CLI cases and preservation assertions to pass; record format skips explicitly. Assessed candidates, scope roots and frozen plans must equal controls for both successful and deadline-exhausted lineage, including later global roots and v3/v4 wrappers.

- [ ] **Step 6 — Commit this independently usable outcome.** Stage only Task 1's named files; `git commit -m "feat: report explicitly bound local worktree lineage"`.

### Task 2: Add explicit merge and exact squash-comparison evidence

**Files:** Modify `skills/task-disk-review/scripts/devspace/git_inventory.py`, `skills/task-disk-review/scripts/devspace/report.py`, `tests/test_git_inventory.py`, `tests/test_package.py`, `README.md`, `skills/task-disk-review/SKILL.md`, `tests/scenarios/context-aware-cleanup.md`.

**Interfaces:** Extend Task 1's validator with the optional `integration` shape above. Add `_integration_evidence(claim: dict, binding: dict, *, git: Callable[..., bytes], repository: Path) -> tuple[dict, dict]`, returning `integration` and `patch_equivalence`. `observe_lineage` calls it within the final advisory phase, before Task 1's final identity/graph-policy recheck; no earlier ordinary-review call site is added.

- [ ] **Step 1 — Write failing `test_lineage_integration_*` cases.** Build a real two-parent `git merge --no-ff`; an old merged source followed by another source commit; `git cherry-pick`; a multi-commit `git merge --squash` plus commit; and `git revert -m 1 <merge>` on the destination. Include a changed-base/whitespace-only similarity case, missing/wrong base, unrelated source, missing object and noncommit endpoint. Assert the following exact distinctions, plus fixture preservation:

| Case | Assertions |
| --- | --- |
| Current versus old merge | Record source/current-HEAD equality and source ancestry to HEAD separately. Verify source reachability through the second parent and claimed destination reachability from current destination. Later source HEAD remains not-in-destination; never promote an old claim. |
| Explicit squash/cherry-pick delta | `patch_equivalence.method == "exact-tree-entry-delta"`; matching nonempty object deltas yield `equal is True` although HEAD ancestry may be false. `integration.squash_provenance == "unverified"` regardless. Different base/object deltas are false for this exact comparison, not evidence that a squash did not happen. |
| Reverted/later destination | HEAD ancestry may stay true; current destination OID and committed-tree equality to the claimed destination are reported separately. A real revert produces a changed tree and `current_content_preservation == "unestablished"`; never emit a semantic `reverted` or released verdict. |
| Invalid/limited evidence | Omitted squash base rejects input; unrelated/noncommit/missing endpoints, root/merge squash destination, shallow/error/oversized delta are unresolved. Existing retention facts survive a comparison failure. |
| Policy drift after comparison | `test_lineage_integration_graph_policy_drift` introduces a persistent shallow boundary or graft after comparison work but before final revalidation, with HEAD/refs/inodes unchanged. Assert changed/unavailable lineage and null derived relations. No comparison result bypasses the final policy gate. |

- [ ] **Step 2 — Establish red.** Run `python3 -B -m unittest discover -s tests -p test_git_inventory.py -k lineage_integration -v`; expect absent/rejected integration support. Add the claim to the extracted CLI test and require its JSON/text distinctions.

- [ ] **Step 3 — Implement only these local comparisons.** Require all supplied endpoints to be full commit OIDs. Record `source_matches_head`, `source_in_head`, `destination_in_current_destination`, `current_destination_matches_claim` and `current_destination_tree_matches_claim` as separate facts. For `merge`, support exactly two parents and report source reachability in each parent; other topology is unresolved. This verifies graph relations, not the authenticity or intent of a supplied historical record.

For `squash`, require the explicit base to be ancestral to source and the destination to have exactly one parent. Compare the two nonempty aggregate changes using `diff-tree --no-commit-id --raw -r -z --no-renames --no-ext-diff --no-textconv --abbrev=<observed-OID-length> <base> <source> --` and the destination's parent/commit pair. Compare parsed, path-sorted `(old_mode, new_mode, old_oid, new_oid, path)` records; retain only endpoints/method/result/count. Accept at most 128 changed paths per side alongside the existing 1 MiB/time acquisition limits; this does not bound Git's internal traversal to 128 paths. Unsupported gitlinks or malformed/truncated output stay unknown. Do not acquire patches/messages/authors, execute textconv/filters, search candidate commits, run `git cherry`, or add runner stdin/pipeline support. Exercise configured external-diff/textconv sentinels in the actual comparison fixture. Git accepts these switches; fixtures must establish their semantics.

This is deliberately **exact tree-entry delta equality**, not whitespace-insensitive patch-ID similarity or proven squash provenance. Tree entries do not establish blob availability, semantic preservation or recoverability; disclose those limits. Compare the current destination's committed tree with the claimed integration tree, but leave semantic preservation unestablished even when equality/ancestry holds.

- [ ] **Step 4 — Update interpretation and evaluation cases.** Describe the exact comparison and limits in README/skill. An actual squash claim needs an independently attributable record binding the repository and exact source/base/destination endpoints; without that record report only the observed comparison and unverified provenance. Add non-leading paired scenario expectations for old merged source, genuine squash, merge-then-revert, stale local remote ref and active reviewer; independently protect held/managed/private-recovery cases. This prepares model evaluation; actual evaluations remain outside these implementation steps.

- [ ] **Step 5 — Establish green and check compatibility.** Run the focused command, then `python3 -B -m unittest discover -s tests -p test_git_inventory.py -v`, `-p test_package.py -v`, `-p test_plans.py -v`, and `-p test_worktree_cleanup.py -v`. Finally run `python3 -B -m unittest discover -s tests -v` once on the combined candidate. Require new cases and applicable regressions to pass; preserve/report the known socket restriction and native/platform skips rather than weakening assertions. The package test inspects/exercises the actual extracted ZIP; no allowlist expansion is planned.

- [ ] **Step 6 — Commit the completed comparison outcome.** Stage only Task 2's named files; `git commit -m "feat: separate explicit integration evidence from retention"`.

## Remaining obligations and review boundary

The two tasks can be accepted separately: Task 1 is a usable current-state review; Task 2 adds a narrower historical comparison. The reviewed scope uses the single-checkout input and exact object-delta comparison as I03's bounded machine support. Do not expand it into automatic destination selection, patch-ID search or provider provenance verification.

This plan does **not** fully machine-verify authenticated squash provenance, detect semantic reverts, inspect every missing blob, certify primary/private-ref recovery, refresh stale refs, establish current consumers/attachment lifecycle, or make snapshots atomic. It exposes those limits; the investigator must resolve applicable scoped evidence or preserve uncertainty. A finite authorized baseline/candidate model pair now supplies subject-specific interpretation evidence, with both satisfying its finite obligations and no candidate recommendation advantage established. Canonical Q03's broader interpretation and §7 acceptance remain incomplete; the [QA reconciliation](qa-plan.md#i03-evidence-reconciliation--9-november-2026) preserves the invocation difference, telemetry limits and missing practical evidence. A fixture pass or one synthetic pair cannot close them.

Three separate sequential independent plan reviews and the affected repair reviews are complete. Task 1 and Task 2 each completed those three separate sequential independent source assignments before repairs, with affected production coverage renewed as specified by the [design](../../superpowers/specs/2026-10-19-context-aware-resource-cleanup-design.md#7-acceptance-principles). The latest test-only repair has requirements and verification/safety approval, with architecture carried for the unchanged runtime; affected source-review gates are closed. The final hosted matrix passed all four jobs. Keep still-applicable I01/I02 evidence attributed to its tested subject. These implementation steps supply no installation, live-evaluation, cleanup or publication authority; separately authorized completed observations and publication remain attributed to their actual subjects.

**Verification limits:** Assuming wider Git-format support than exercised or presenting exact tree metadata as authenticated squash history would overstate the evidence. Keep the explicit limits and require actual fixture evidence.
