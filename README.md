# Cleanup plugin

A planned, on-demand Codex skill and Python helper for reviewing development disk usage and cleaning individually approved, disposable directories.

**Status:** Planning and repository preparation. The skill, helper, and cleanup executor are not implemented. Commands in the plan are illustrative and cannot be run yet.

## Plan review

The [revised plan dated 16 October 2026](cleanup-plugin-plan.md) is the source design and is preserved unchanged.

Review outcome, 16 October 2026: sufficient to begin **Milestone A, read-only inventory and compatibility proof**. No material improvements recommended to the architecture. The plan's implementation-ready status remains conditional on its validation gates; deletion readiness has not been established.

Before enabling Milestone B cleanup, resolve and demonstrate:

- **Human confirmation:** Bind confirmation to the displayed frozen plan and selected eligible items on each supported host. General command permission or automatic approval is insufficient. The [official approval documentation](https://learn.chatgpt.com/docs/agent-approvals-security) describes execution permissions; it does not establish the helper's required plan-bound confirmation contract. Use the plan's user-operated terminal fallback if host integration cannot prove that contract.
- **Filesystem protection and eligibility:** Define concrete target identity, content-change, consumer, and rebuild-evidence checks. Prove refusal and interrupted-operation behavior using disposable fixtures. Python documents that [`shutil.rmtree` symlink protection](https://docs.python.org/3.12/library/shutil.html#shutil.rmtree) depends on platform capabilities; selecting Python 3.12 alone does not establish safe deletion.
- **Retention and coverage:** Verify installed-host settings and provider access. [Official worktree documentation](https://learn.chatgpt.com/docs/environments/git-worktrees) describes independent automatic cleanup, so a plugin hold cannot guarantee host retention. The plan's historical Git edge-case test was not reproduced during this review.
- **Packaging and invocation:** Verify bundled helper paths and actual CLI and desktop activation independently. [Current packaging documentation](https://developers.openai.com/plugins/build/plugins) recommends root `plugin.json` for new portable plugins and retains `.codex-plugin/plugin.json` compatibility support. Confirm the target versions before choosing the package format.

These are implementation gates within the existing scope, not an expanded roadmap. Python 3.12+ remains a proposed prerequisite pending compatibility checks.

## Repository hygiene

[.gitignore](.gitignore) excludes Python bytecode, the root virtual environment, distribution output, operating-system metadata, root-local environment files, and `.local/` scratch output. Root `.env.example` is permitted for placeholder values only. Nested fixture paths remain visible for deliberate review.

Use `.local/` for developer-only inventories and probe output that may contain local paths. This convention does not choose the helper's eventual runtime state location. Curated synthetic fixtures, example plans, receipts, and necessary failure evidence should remain reviewable in Git. Ignored files are not backups and are not automatically eligible for cleanup.

When packaging is implemented, include only intended runtime files and inspect the actual bundle for secrets, local state, planning material, and undeclared dependencies. `.gitignore` does not define package contents.

Installation, runtime configuration, executable commands, and application test instructions will be added with the working implementation. Licensing remains undecided.
