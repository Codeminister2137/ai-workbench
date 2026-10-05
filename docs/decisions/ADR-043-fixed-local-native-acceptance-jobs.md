# ADR-043 - Fixed Local Native Acceptance Jobs

**Status:** Accepted; offline implementation complete; live acceptance deferred
**Date:** 2026-10-04

## Context and owner decision

ADR-039 implements explicit, budgeted research scheduling. It is not a generic
coding queue. D3 first authorized investigation, then the owner accepted option 1
of the [concrete contract](../repo-assistant/acceptance-job-proposal.md) after its
scope was presented in the session summary. This approval permits implementing
the contract offline. It does not select a live compute window.

The accepted scope is one fixed local inspect/edit/test harness, additive tables
in the existing application SQLite database, explicit model/resource identity,
and an exclusively owned Ollama runtime at an unused numeric loopback endpoint.
No additional personal rationale was supplied; the technical trade-offs below
are the recommendation presented to the owner, not inferred owner motives.

## Alternatives and trade-offs

- Selected: local v1 with additive storage and owned processes. This confines
  writes to a generated fixture and makes cleanup verifiable. It requires an
  unused endpoint and retained operating-system ownership of the process tree.
- Generalize research definitions and include hosted acceptance. Broader coverage
  would introduce a larger migration and unresolved client/account/permission
  and cancellation contracts. Defer this option.
- Keep scheduling research-only and supervise other checks manually. Least code,
  but retains manual supervision. The owner selected the concrete local contract.
- Arbitrary commands remain excluded: the need is a fixed acceptance check,
  not a general execution service.

## Contract and implementation

`ai_provider.acceptance_jobs` validates exact v1 definitions and catalog routes,
stores immutable definitions and separate receipts, and reuses neutral
`ai_orchestrator.scheduling.admit_task`. Only explicitly selected planned jobs
with a full allocation start. Conditional claims prevent replay. Failure or
uncertain cleanup stops the sequence; restart requires explicit reconciliation.
Existing research tables and workers retain their contracts.

The supervisor reserves 15 seconds for cleanup and handoff. Runtime, worker and
validator processes remain foreground-owned; Windows v1 uses retained Job Objects
and suspended creation so roots cannot spawn descendants before assignment.
It refuses execution on platforms without this verified ownership implementation.
Birth identity and exact listener ownership are checked before metadata/inference;
only owned jobs are terminated. Occupied endpoints are refused and untouched.

The fixed harness preserves complete instructions, exposes existing read/edit
tools with a target-only boundary, and requires a successful source read before
an edit. Protected files and hardlink/symlink/junction boundaries are checked.
The host validator accepts only a tiny pure arithmetic function, so it never runs
arbitrary model-authored Python. Baseline failure, postchange success, ordered
effect receipts, protected content, timely cleanup and a durable result are all
required. A worker exit zero alone is insufficient.

Tool/effect and estimated-admission receipts are flushed before worker interruption
and imported into SQLite after cleanup. Provider usage remains separately labeled;
estimated input admission does not verify native token capacity or model quality.
Pending jobs are invalidated by catalog, runtime, model or native-contract changes.
No fallback, model download, command payload, prompt payload, hosted account,
daemon or new dependency is introduced.

## Validation and limits

Deterministic tests cover version/type/endpoint refusal, additive storage and
conditional claims, admission and deadline refusal, stale identity, protected
fixtures, actual synthetic tool effects, interrupted receipts and cleanup failure.
Owned-process tests use dummy processes and fixed validators without inference.
Live model acceptance remains deferred until the owner selects a compute window.
This single fixture cannot establish general coding quality or cross-agent parity.

2026-10-05 bounded live acceptance passed during the owner's one-hour compute
window. Actual source read/edit effects, baseline/postchange validation, protected
files and runtime/worker/validator cleanup were verified. Earlier failed startup
jobs remain preserved. The owned runtime now retains the existing model library,
disables cloud discovery/pruning and bounds transient metadata readiness retries;
real identity mismatches still refuse. See the proposal's live checkpoint for
allocation and artifact details. No broader quality/parity claim follows.
