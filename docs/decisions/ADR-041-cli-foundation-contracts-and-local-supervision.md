# ADR-041 - CLI Foundation Contracts and Local Supervision

**Status:** Accepted; implementation in progress
**Date:** 2026-10-04

## Context and alternatives

ADR-040 approved common tools and the C1-C6 development foundation. Implementation
exposed concrete choices around profile configuration, instruction limits, shared
permissions, IDE transport, process recovery and native model compatibility.
The owner approved all six recommendations in the recorded
[decision brief](../repo-assistant/foundation-decisions.md).

Alternatives considered were user-editable capability manifests, retaining small
instruction limits, changing global client grants, direct per-client IDE access,
memory-only sessions or a daemon, and leaving automatic model selection unchanged.

## Decision

- Use built-in profiles backed by existing tool contracts, project-local skill
  discovery and per-run native client mappings. Validate prerequisites; do not
  install skills globally automatically.
- Load complete applicable repository instructions separately from optional file
  snippets, with a configurable 64,000-character ceiling. Refuse rather than
  truncate instructions. Enforce known input limits when capacity can be checked;
  character counts alone are not proof of tokenizer/model capacity.
- Establish shared inspection first, then terminal mutation approvals using
  existing presets. Identify task, workspace and operation. Interactive requests
  need a human; approvals expire on CLI restart. Exclude Antigravity from
  tool-requiring fallback until scoped access is verified; do not alter global
  grants or bypass native restrictions.
- Expose project-owned wrappers over explicitly configured local PyCharm MCP,
  initially interpreter selection, diagnostics and navigation. The official Python
  MCP SDK is approved as an optional dependency, with a compatible release chosen
  after environment/transport checks. Keep mutating refactors under shared approval.
- Use a foreground process supervisor and additive records in existing application
  SQLite storage. Retain records until explicit deletion. Preserve objectives,
  explicit decisions and observed receipts, never credentials or private reasoning.
  Reconcile uncertain effects after restart; do not blindly replay them or promise
  restoration of dead pipes. No daemon is approved.
- Prefer verified native tool support for automatic coding routes, initially the
  tested GPT-OSS route. Never silently override explicit model choices. Refuse
  incompatible native requests with an explanation. Version compatibility evidence
  and invalidate it after relevant runtime/model changes. Investigate Qwen separately.

The owner additionally requests investigation of local-model monitoring to reduce
hosted allowance usage. Use ordinary process/status checks for deterministic
completion; use a bounded local model only where interpretation is useful. This
does not approve an autonomous model deciding permissions, architecture, retries of
uncertain mutations, or changing acceptance criteria.

## Rationale and execution window

The owner wants to develop through this CLI, keep common tools across account
fallback and avoid spending hosted allowance on idle monitoring. The accepted
recommendations favor existing contracts, explicit permissions and recoverable
foreground execution rather than global grants or a background service.

The owner authorized five hours starting at 13:10:29 UTC, ending at 18:10:29 UTC,
including local compute and bounded live acceptance. Stop new heavy work with
enough time to validate, clean up owned processes, save changes and CURRENT_CONTEXT,
then invoke the already verified and owner-authorized sleep helper. Continue other
approved implementation when a material choice blocks one slice; collect new
decisions for the owner's return. Do not consume time through idle model polling.

## Consequences and remaining boundaries

Implement and verify these contracts incrementally; approval is not evidence that
client permissions, fallback parity, IDE access or recovery already work. Existing
privacy/cost rules continue to apply. The scheduler remains research-only; generic
coding/evaluation jobs, optional capabilities and new external services still need
separate decisions. Hosted account limits can interrupt the supervisor itself.
