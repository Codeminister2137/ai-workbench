# ADR-045 — IDE-Independent Semantic Rename

**Status:** Accepted; bounded native/shared MCP acceptance passed; installed-client acceptance pending
**Date:** 2026-10-06

## Context

ADR-040 sets the long-term direction that project-owned development tools should
work independently of PyCharm, while allowing PyCharm to host tools during the
transition. The existing PyCharm rename operation applies changes immediately
and does not provide the preview contract needed for guarded, review-first
mutation. Deferring rename would leave this semantic capability dependent on the
IDE or unavailable through the project-owned tool contract.

The owner selected option A from the
[semantic rename proposal](../repo-assistant/semantic-refactoring-proposal.md).
Their stated reason is IDE independence: PyCharm is permissible for now, but
eventually the tools should work independently of it.

## Options considered

- **A.** Add an optional standalone Python semantic rename preview/apply pair.
  This advances IDE independence and lets the owner review exact changes before
  writes, at the cost of an optional dependency and a new two-step contract.
- **B.** Use PyCharm's immediate rename, followed by diff review. This reuses the
  current host but does not provide preview-before-write and retains IDE
  dependence for semantic rename.
- **C.** Keep the read-only IDE bridge and use ordinary reviewed file edits.
  This avoids a new dependency and mutation surface but leaves semantic rename
  unfinished.

## Decision

Choose **A** for a narrow Python symbol rename implementation backed by optional
Jedi. Expose preview and apply through the project-owned native and shared coding
tool contracts. Keep the PyCharm tool host available during migration; this
decision does not require its immediate removal or prohibit using it for other
capabilities.

Preview is read-only and produces a bounded complete diff and short-lived,
owner/task/workspace-scoped plan. Apply remains a WRITE operation, uses the
selected approval policy, and presents the immutable diff for interactive
approval. It checks Jedi's source snapshot and file digests, uses atomic
per-file replacements, and reports partial effects without automatic rollback.
The Jedi dependency is optional; no project code is executed during preview.
Detailed limits and behavior are specified in the
[implementation contract](../repo-assistant/semantic-refactoring-proposal.md).

## Consequences

- Python semantic rename no longer requires PyCharm's rename host, and can be
  exposed consistently through native and shared tool routes.
- PyCharm may continue to provide other tools during the transition; IDE
  independence is achieved by replacing capabilities in stages, not by
  removing the IDE integration prematurely.
- The implementation is intentionally limited to Python and Jedi's supported
  references. Dynamic references may be missed; this is not a general
  refactoring framework or proof that all C5 capabilities work without PyCharm.
- Offline tests and a disposable native/shared MCP transport fixture validate
  the guarded contract. The fixture used a synthetic MCP client; installed
  third-party-client and physical terminal interaction remain unverified.
  Broader C5/M3 acceptance and ADR-040's M5 independence acceptance remain
  separate.
