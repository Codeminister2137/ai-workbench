# ADR-060 — Structured CLI error attribution

**Status:** Accepted (2026-10-18).

## Context and owner decision

ProviderError retains provider, normalized category and cause information through
the agent loop, but CLI closeout and conversational persistence previously kept
only its message. Fallback could leave the originally selected provider visible
while a different route actually failed. Generic messages made attribution hard.

The owner approved the recommendation of optional structured error metadata plus
readable terminal attribution, with a limited safe handoff summary. The stated
goal is to identify the breaking service and preserve known causes; unexplained
errors must trigger immediate investigation. This approval does not authorize
raw exception bodies, prompt/private-reasoning logging or inference.

## Decision

Reuse ProviderError, CodingTurnResult, the fixed CLI summary and the existing
SQLite transcript metadata JSON column. Add optional provider/category/cause_kind
and fallback_handoff fields to CodingTurnResult. No SQL migration, new store,
service or dependency is needed. Old transcripts without these keys still load.

Provider/category come from the caught error. cause_kind is only the class name
of its explicit chained cause, or raw_error when no explicit cause exists. Do
not serialize the cause message, object, traceback, implicit exception context,
partial model messages or provider continuation. A cause class identifies a
diagnostic type, not necessarily the root cause. Missing attribution is shown
as unknown in failure summaries; never infer a failure's provider from the
selected route. Retain effective_route_id separately.

Diagnostic identifiers accept at most 160 ASCII letters, digits and identifier
punctuation (`_.:/@+-`). Project fallback handoffs onto status, reason,
failure_kind, quality_policy and failed_route_id. The first four accept only
known control values; the route uses the identifier bound. Omit observations,
objectives, save-error text and unrecognized fields. Apply this projection when
creating turn results, persisting and rendering history, including old records.
The bounded projection is available to subsequent turns as host outcome data,
never as permission or proof of current effects. Existing failure_reason text
and existing route/attempt reporting retain their contracts.

## Alternatives and consequences

- **Structured fields plus visible attribution, selected:** supports stable
  programmatic access and readable errors without parsing decorated messages;
  requires additive-reader compatibility and privacy/bounds checks.
- **Context only in failure_reason text:** smaller contract surface and easy
  compatibility with existing readers; mixes identifiers with prose, makes
  programmatic queries fragile and does not preserve a structured handoff.

Fallback routing, quality, billing, privacy and approval policy are unchanged.
This slice retains final-error attribution and existing route-attempt statuses;
it does not add a complete exception chain for every primary/recovery attempt.
Tool/worker/scrutiny errors and safe provider-body detail remain wider-review
work. The historical discarded HTTP500 body cannot be reconstructed by this fix.

## Validation

Deterministic tests use actual CLI/native-loop/fallback/chat boundaries with
synthetic transport/admission/readiness. Cover direct failure, secondary timeout,
quota exhaustion, missing attribution and recovery. Reopen SQLite and check
actual return codes, metadata and history. Separate checks cover old records,
bounded projection, omitted private sentinels and normal request catch paths.
These are software checks, not model-quality or live-service acceptance.
