# Platform and client compatibility

Reconciled on 29 October 2026 against source baseline `d7ead1f`. The [README](../../../README.md) owns the shipped support contract. This record separates existing capabilities from optional future verification work; it does not enable another platform.

## Current contract

| Surface | Current source/documentation support | Evidence boundary |
| --- | --- | --- |
| Python | 3.12+; standard-library helper | CI is configured for 3.12/3.14; individual results remain subject-bound |
| macOS/Linux review | Required descriptor, identity and local filesystem capabilities; explicit roots and providers | Unsupported or unknown boundaries remain report-only |
| Cleanup | Narrowly supported local macOS/APFS operations with fresh exact-plan terminal confirmation | No Linux, HFS or Windows cleanup certification |
| Native Windows | Unsupported, including assessed input/plan I/O and provider inventory | A uniform early refusal before optional I/O is still proposed |
| WSL, remote, network, FUSE and synchronized paths | No executable eligibility; unresolved storage boundaries remain protected | WSL is a separate Linux environment, not native Windows support |
| Codex | Existing manifest/UI policy and explicit invocation; historical installed CLI/desktop observations in README | Those observations identify older subjects and do not certify this combined package |
| OpenCode v2 | Complete bundle with absolute skills-directory configuration and explicit invocation | Native installation, discovery and model behavior have not been tested |
| Antigravity | Complete local plugin using the existing manifest/default skills directory | Native validation, discovery and model behavior have not been tested |
| Managed worktrees/storage | Report-only unless an existing supported lifecycle contract applies | OpenCode/Antigravity resources are held/excluded or lifecycle unknown; Codex fields keep their Codex meaning |

Configure roots/provider paths per computer and regenerate host-bound plans there. Read-only success does not certify cleanup, remote access, provider availability or semantic assessment.

## Verification backlog

These are proposed work packages, not implemented changes or authorization to run external operations.

### Portable invocation and refusal

- Extend the existing extracted-package test to Unicode/spaced installation paths with isolated HOME and PATH and absent optional tools. Verify task/project/global outcomes, unchanged fixture bytes, private output modes and honest missing-provider coverage.
- Add an early native-Windows refusal after argument parsing, before optional configuration/assessment/manifest reads or output writes, preserving help. Verify task/project/global entrypoints with no traceback, traversal or side effects. A simulated refusal check is not native Windows runtime evidence.
- Retain current unsupported-capability tests. The existing review tests already cover unavailable mount identity and zero content reads; add only demonstrated gaps rather than duplicate coverage.

### Bounded host matrix

The current workflow has four combinations using `ubuntu-latest` and `macos-latest` with Python 3.12/3.14. It does not pin OS releases or demonstrate every architecture.

For broader claims, select available explicit Intel/ARM macOS and x64/ARM Linux hosts, include justified older-system and Python 3.13 coverage, and verify current runner/interpreter access and cost before changing CI. The earlier ten-job matrix was a proposal, not a minimum support promise. Preserve pinned actions, read-only permissions and disabled credential persistence. Record actual OS, architecture, Python, checkout and skips; a green moving label is insufficient.

### Actual host/storage and installed-client evidence

- Invoke the extracted package on each newly claimed host. Record filesystem/identity capabilities, hardlink/sparse observations, case behavior and genuine permission denial where available; unknown allocation/locality stays unknown.
- Actual mount or same-device bind-mount claims require separately authorized disposable fixtures and checks that outside descendants remain absent from traversal and unchanged. Simulations are supplemental. Do not provision machines, mount storage or weaken refusal to fill this record.
- Test the actual installed combined package in each claimed client, distinguishing loading, explicit invocation, model interpretation and desktop/CLI behavior. Do not infer automatic retention or provider access from source metadata.
- Keep cleanup disabled outside the existing contract until its separate executor, failure/recovery and human-confirmation obligations are satisfied. New read-only evidence cannot enable deletion.

The skill identity, trigger description, catalog size and explicit-only UI policy remain stable. Platform changes must preserve the selected-scope/report contracts and need evidence at their canonical owner; no general portability framework or traversal fallback is implied.

## Acceptance owners

[qa-plan.md](qa-plan.md) owns evidence categories; [handoff.md](handoff.md) owns current continuation status. Historical compatibility checks are not rerun or re-certified by this reconciliation. Native Windows support remains a future direction requiring its own selected scope and native link/reparse, identity, permission and subprocess evidence.
