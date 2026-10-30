# Cleanup Resources Plugin: verification record

Reconciled on 29 October 2026 against source baseline `d7ead1f`. This document identifies verification owners and evidence gaps. It does not repeat historical job results as current passes.

## Behavior and existing checks

| Behavior | Existing verification owner | Limits |
| --- | --- | --- |
| Bounded traversal, identity/locality, denied or partial coverage | [test_review.py](../../../tests/test_review.py) | Simulated boundaries are not actual mount certification |
| Content/reference assessment and frozen plan semantics | [test_plans.py](../../../tests/test_plans.py) | Helper checks cannot authenticate semantic claims or historical provenance |
| Evidence size advice and protected originals | [test_evidence.py](../../../tests/test_evidence.py) | Capture comparisons are optional; less retained data is not a success criterion |
| Global selected roots/providers and unknown retention | [test_global_inventory.py](../../../tests/test_global_inventory.py) | Configured fixture coverage is not whole-host discovery |
| Git inventory and ordinary linked-worktree operations | [test_git_inventory.py](../../../tests/test_git_inventory.py), [test_worktree_cleanup.py](../../../tests/test_worktree_cleanup.py) | Local refs do not establish remote freshness; managed lifecycle stays protected |
| Confirmation, selection, drift, intent/results and reconciliation | [test_cleanup.py](../../../tests/test_cleanup.py) | Synthetic terminal input is not fresh human acceptance or atomic concurrency protection |
| Selected Docker contracts and native effects | [test_docker_cleanup.py](../../../tests/test_docker_cleanup.py), [test_docker_native.py](../../../tests/test_docker_native.py) | Optional native trials require an isolated supported endpoint and explicit fixture authority |
| Supported singleton npm cache entries | [test_npm_cache.py](../../../tests/test_npm_cache.py) | Native version/fixture requirements and skips remain material |
| Runtime allowlist and extracted task/project/global invocation | [test_package.py](../../../tests/test_package.py) | Packaging does not establish native client loading or model behavior |

Use the repository commands in [README](../../../README.md#development-and-deliverable). Run the smallest relevant checks during changes, then the full relevant suite on a coherent implementation batch. Preserve actual exit status, skips and unsupported environments; a passing command does not fill an unexercised evidence category.

The [CI workflow](../../../.github/workflows/tests.yml) configures Ubuntu/macOS moving runner labels with Python 3.12 and 3.14. Configuration alone is not evidence that a particular candidate passed or ran on a particular OS release/architecture. Record the tested commit, actual checkout, runtime and relevant skips when relying on hosted results.

## Distinct acceptance evidence

1. **Deterministic behavior:** observable reports, frozen-plan round trips/rejections, preserved fixture bytes, protected selection and interruption handling.
2. **Actual native effects:** supported local filesystem and provider versions, isolated disposable targets, survivor checks and failure/reconciliation paths. Mocked arguments cannot replace these observations.
3. **Extracted package:** inspect actual members and payloads for private material, dependencies and relocatable guide/helper access.
4. **Installed client:** identify the package and loaded skill, then distinguish discovery, explicit invocation, model interpretation, CLI behavior, desktop behavior and settings. Historical observations in README cover only their named subject.
5. **Practical human outcome:** useful supported recommendations, preserved originals and unresolved cases, clear confirmation/cancellation and recovery limitations. Do not infer safe disposal or reclaimed space from eligibility or size alone.

## Outstanding coverage

- Current combined installed-client behavior and practical acceptance remain incomplete; OpenCode v2 and Antigravity were documentation-reviewed, not exercised natively.
- Effective Codex CLI and desktop retention settings remain independently unknown. Holds cannot control another tool's automatic cleanup.
- Broader architectures, older systems, isolated HOME/PATH relocation and real mount/storage combinations remain gaps described in [compatibility-plan.md](compatibility-plan.md).
- Windows is unsupported. An early uniform refusal before optional input/output handling remains proposed.
- The paused [future QA plan](../context-aware-resource-cleanup/qa-plan.md) separately owns new investigator/model comparisons and future operation acceptance. Its historical results do not establish features in this branch.

The documentation reconciliation changes no helper behavior or test contract. Its package integration result belongs to the merge request for the actual final candidate; this record does not claim a newly run full suite, provider trial, live-model evaluation or human cleanup acceptance.
