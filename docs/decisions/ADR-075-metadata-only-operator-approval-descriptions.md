# ADR-075: Metadata-only Operator approval descriptions

Status: Accepted and implemented, 2026-10-28.

## Owner decision and rationale

The owner approved the recommended metadata-only bridge description. Workbench
source, command arguments and secrets must not reach the Operator through an
apparently harmless approval summary. The previous 400-character truncation
could transmit those values and was not a privacy boundary.

Descriptions now contain the tool/category, SHA256 workspace fingerprint and
top-level argument types/sizes. Argument names are omitted too: callers can put
private data in dictionary keys. Nested values, string contents, numeric/boolean
values and workspace paths are not included. Existing candidate/base/evidence
digests and the approval/rejection/cancellation protocol are unchanged.

## Alternatives and consequences

- Metadata-only descriptions keep argument content out of the remote review UI,
  but the owner cannot inspect the exact command or diff there. Exact content
  must be reviewed through another authorized channel before approval.
- Explicit trusted-local detailed summaries would improve phone review, but
  transmit private values and require an owner-selected destination/data scope.
  This mode is not implemented or implicitly approved.

Same-sized actions can have identical descriptions; their candidate digests still
differ. Metadata is not encryption or anonymization, and this change does not
implement general tool-output protection, change production approval authority,
or claim that arbitrary local commands are isolated.

## Evidence

Mock HTTP transport tests inspect actual submission JSON, including nested values,
arbitrary argument names, workspace paths and same-sized distinct actions. Existing
client-lifetime, approval, rejection and transport-failure coverage remains active.
