# ADR-077: File state bound to remote Operator approvals

Status: Accepted by the owner and implemented, 2026-10-29.

## Decision and intent

After a temporary-file reproduction showed that operation-only remote approval
could overwrite an intervening owner edit, the owner approved the recommendation
to add targeted file-state checks for file mutations. Command-input protection
is a separate scope. The rationale is to preserve concurrent edits rather than
treat unchanged tool arguments as approval of changed underlying files.

Trusted tools declare their affected paths in host-only `ToolCall.approval_paths`.
Create/edit declare their requested file, research-report writes their configured
target, and rename application all files in its prepared plan. The remote bridge
refuses write-category calls without declared targets. Model arguments cannot
populate this host field through the model-to-tool conversion.

Before submitting a write approval, Workbench captures each target's existence,
resolved path, file identity, mode, size, modification time and content SHA-256,
plus parent identities/resolutions. It hashes that local evidence into the
existing `base_digest` field. Before accepting approval it recaptures the state:
different, unsafe, inaccessible or unstable state refuses the operation and needs
fresh approval. No automatic resubmission or overwrite occurs. The original
candidate digest continues to bind the tool name/arguments. Rename's independent
prepared-plan checks during application remain in force.

Only digests and the ADR-075 metadata description enter Operator. Paths, source
bytes, per-file hashes and the local evidence structure are not transmitted or
persisted by this mechanism. Credential paths and targets outside the workspace
are refused before content reads. Hashing observes the caller's approval deadline.
Windows path/handle stat can disagree on ctime after writes; ctime/atime are not
compared. Unrelated sibling-file changes do not invalidate targeted approval.

## Alternatives and trade-offs

- Targeted file-state checks (chosen) protect the affected files with bounded
  local hashing and no source disclosure. Each write tool must declare its targets;
  arbitrary shell-command inputs cannot be inferred from command text.
- Retaining operation-only approval would preserve simpler callbacks and avoid
  file reads, but would permit approval to overwrite changes made during its wait.

The public Operator schema remains unchanged: it stores opaque SHA-256 digests.
Existing records retain their original meaning; this does not regrade earlier
trials or interpret old workspace-path digests as file-state evidence. No new
dependency, persistent store or public application source change is introduced.

## Limits and separate work

This compares observed state across an approval wait, not every historical write.
It does not lock files or make the later write atomic: a concurrent change after
the callback returns remains possible. It is not an OS sandbox, general secret
isolation, workspace freeze, command-input manifest or transactional multi-file
apply guarantee. Shell/custom/read approvals retain operation identity and the
existing workspace digest; no file-input freshness claim is made for them.
The owner still reviews exact content through an authorized channel under ADR-075.
A remotely approved record can remain even when local state checks refuse it.

## Evidence

Deterministic controls exercise actual permission callbacks and file tools for
unchanged and concurrently edited/replaced/created/deleted files, restored mtimes,
unrelated changes, unstable snapshots, private-path refusal and multi-file rename.
Private local composition with actual public Operator routes covers approved,
rejected and remotely approved but locally stale actions. Decisions are scripted,
not physical owner approvals or live model-quality evidence.
