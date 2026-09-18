# ADR-014 - Provider Contract And Dependencies

**Status:** Accepted

**Date:** 2026-09-18

## Context

The provider-agnostic infrastructure needs a common contract for applications and future orchestration without leaking provider-specific APIs into application code.

The existing AI Council prototype uses LangChain and Ollama directly. That is useful prototype code, but it does not match the target provider boundary.

## Options Considered

### Mirror OpenAI-Style Schemas

This would be familiar and easy to map to OpenAI-compatible gateways, but it risks making OpenAI's schema the implicit core abstraction.

### Use LangChain Or LangGraph In The Provider Core

This could speed some integrations, but provider-specific behavior, metadata, errors, streaming details, and gateway routing data can be hidden or flattened by framework wrappers.

### Define A Neutral Chat-First Contract

This keeps the internal schema small and provider-independent, while allowing provider-specific child schemas and adapters such as Ollama, OpenAI, or Requesty.

## Decision

Define a neutral chat-first provider contract.

The base schema should be designed so provider-specific child schemas and adapter translations can depend on it.

Do not use LangChain or LangGraph in the provider core initially. They may remain in application prototypes or be considered later for orchestration/application layers if they materially simplify real requirements.

## Rationale

The owner agreed that consistency and provider boundaries matter more than reusing prototype framework assumptions. LangChain and LangGraph are not banned from the repository, but the foundational provider package should remain small, explicit, and testable.

## Consequences

The first provider package will implement its own request, response, usage, backend, error, capability, and privacy models.

Provider adapters retain raw provider metadata where useful instead of forcing everything into a single provider's schema.

Additional providers can be added later without changing application-facing contracts unnecessarily.

## Related Decisions

- `docs/decisions.md` ADR-002 - Provider-Agnostic AI Boundary
- `docs/decisions.md` ADR-003 - Requesty Is an Integration, Not the Core Architecture
- `docs/decisions.md` ADR-005 - Orchestrator Is Separate from Provider Infrastructure
