# ADR-055 - Explicit provider continuation metadata

**Status:** Accepted and implemented; coding-workflow acceptance incomplete
**Date:** 2026-10-11

## Decision and rationale

The owner chose explicit message metadata over an adapter-local cache. Add an
optional ProviderContinuation to AIMessage, carrying an adapter-owned payload
and originating provider/model/endpoint. Existing callers need no change. Only
the originating target's adapter may replay it; other adapters omit it.

State is transient, separate from answer text. Do not add reasoning persistence,
print it as progress/answers or transfer it to another provider/model/endpoint.
Normal message representations hide it. Native input admission counts it;
unsupported exact-token profiles refuse instead of silently undercounting.
Existing storage still persists answers/host outcomes, not continuation state.
Restart/fallback does not promise restoration of internal provider reasoning.

The owner's concurrent priority is repo-wide documentation conformance: differences
confuse humans and AI and create later problems. Explicit flow and deterministic
session isolation were the technical recommendation; no additional personal
rationale for this implementation choice is invented.

## Alternatives

- Explicit metadata: clear flow/lifecycle, but expands the shared contract and
  requires privacy, sizing and serialization checks.
- Adapter-local cache: preserves the message interface, but hides mutable state
  and requires reliable history matching and session isolation.

## Evidence and consequences

Synthetic normalization confirmed that raw message.thinking was retained in
raw_metadata but omitted from follow-up requests. Official Ollama examples preserve
it. Both normal and streaming paths must roundtrip it with native tool calls.
This is not proof that the loss caused the installed model's invalid paths or
argument-only final reply, or that the repair guarantees a successful edit.

Changed native request semantics require reviewing compatibility receipts; old
evidence must not silently certify the new contract. Bounded tool compatibility
checks remain distinct from representative model-quality evaluation. No new
dependency, cache, service, database schema or provider routing is introduced.

See [conformance plan](../documentation-conformance-plan.md) and
[official tool-calling contract](https://docs.ollama.com/capabilities/tool-calling).

## Validation

2026-10-15 extension within the existing decision: OpenRouter captures and replays
its documented reasoning fields using the same explicit transient origin-bound
contract, including streaming. Returned raw metadata excludes those fields.
Synthetic route/role isolation, admission and answer-only persistence checks pass.
Other hosted routes are not assumed compatible. No live quality or privacy
promotion is implied; settings gaps are tracked in the CLI roadmap.

Offline adapter/loop/admission/history/counting and CLI checks passed: 166 tests,
three existing skips; a separate adapter/chat/counting slice passed 33 tests.
Ruff, formatting and targeted type checks passed. A bounded local fixture received
and replayed thinking and performed the correct edit without tool errors, but
missed its required final-report marker: overall fixture acceptance is incomplete.
Native contract version 2 records tool compatibility separately from quality.

The subsequent owned-terminal pilot produced real regression-test edits. Host
checks passed 36 tests including unchanged frozen acceptance checks. However,
the model initially damaged indentation, generated weaker coverage than requested,
and repeated reads exhausted estimated context during repairs. It did not finish
the requested review. The pilot stopped at that failure condition within its
original allowance; owned runtime cleanup was verified. Do not claim a model
quality improvement or a completed live edit/test/review workflow from these runs.

A fresh owner-requested follow-up pilot added useful fake completed-process checks
for return codes 0 and 7, but weakened existing exception assertions during repair
and resumed reads during a review-only request. Host restored those assertions,
kept the useful edits and verified 38 passing checks and runtime cleanup. Overall
workflow acceptance remains incomplete; further generic live retries are deferred
in favor of focused offline diagnosis. This does not overturn the metadata choice.

The final repository-wide gate exposed an acceptance-job validator still pinning
native contract 1. It now validates the active native contract independently of
payload schema/harness revision 1, preserving stale-job refusal without a storage
migration. Fixtures follow the active receipt and retain strict version/type checks.
