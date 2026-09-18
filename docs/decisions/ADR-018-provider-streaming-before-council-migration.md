# ADR-018 - Provider Streaming Before AI Council Migration

**Status:** Accepted

**Date:** 2026-09-18

## Context

The current AI Council web UI streams member responses as `member_delta` events.
Its execution path is hard-wired to LangChain's Ollama integration through
`LocalAgent`.

The provider infrastructure currently exposes only non-streaming chat completion:

```python
complete(request: AIRequest) -> AIResponse
```

Migrating the Council web path directly to `ai_provider` without provider
streaming would either remove the current streaming user experience or require a
temporary app-specific streaming adapter.

The owner also wants reusable infrastructure packages such as `ai_provider` and
`ai_orchestrator` to grow integration glue when that improves interoperability
across applications.

## Options Considered

### Add A Council Adapter Seam First

This would preserve behavior by isolating the current LangChain/Ollama code
behind a Council-owned respondent interface.

It is low risk, but it leaves streaming provider execution in the application
instead of infrastructure.

### Migrate Only Non-Streaming Council Paths To `ai_provider`

This would prove `ai_provider` integration for simple paths while leaving web
streaming on LangChain temporarily.

It creates two execution paths and defers the main web migration issue.

### Add Provider Streaming First

This adds a reusable streaming contract to `ai_provider`, then lets the Council
migrate without losing streaming behavior.

It changes the provider public API and requires careful tests, but it keeps
provider-specific streaming details out of applications.

### Drop Streaming During Migration

This is simplest technically, but it regresses the current Council UI and hides a
real provider capability need.

## Decision

Add provider streaming support before migrating the AI Council web execution path
to `ai_provider`.

The initial streaming contract should stay small and chat-focused. It should
support the existing Council need: yielding text deltas and preserving final
provider/model/usage metadata where available.

Do not add cloud adapters, usage persistence, autonomous routing, or Council
memory as part of the streaming slice.

## Rationale

The Council already has a streaming user experience, so preserving it matters.
Implementing streaming in `ai_provider` makes the capability reusable for future
apps and keeps provider-specific protocol details out of Council business logic.

This also matches the broader direction that infrastructure packages may contain
more integration glue when doing so improves interoperability and keeps apps
focused on product workflows.

## Consequences

`ai_provider` will need a small public streaming contract and an Ollama streaming
implementation.

The design should be evaluated before implementation because it affects public
provider contracts, error behavior, final metadata handling, and tests.

The AI Council migration should wait until the provider streaming contract is
implemented and validated.

## Related Decisions

- `docs/decisions.md` ADR-002 - Provider-Agnostic AI Boundary
- `docs/decisions.md` ADR-005 - Orchestrator Is Separate from Provider Infrastructure
- `docs/decisions.md` ADR-014 - Provider Contract And Dependencies
- `docs/decisions.md` ADR-015 - Provider Rollout And Prototype Privacy Classes
- `docs/decisions.md` ADR-017 - Dependency Selection Balances Simplicity And Maintenance Cost
