# ADR-020 - Coding MVP Supports Local Requesty And OpenAI Backends

**Status:** Accepted

**Date:** 2026-09-20

## Context

The near-term priority is to make `ai_provider` and `ai_orchestrator` useful for
real coding work, rather than integrating them into AI Council first. A useful
coding assistant needs a local path, plus cloud fallback paths when local models
are insufficient or when the owner wants Codex/OpenAI-like capability from the
same provider/orchestrator interface.

Earlier decisions kept the first provider slice local-only while shaping the
contract for future cloud backends. That first local Ollama slice now exists.
The next provider milestone can include cloud adapters, but doing so affects
privacy, credentials, configuration, provider identity, and transcript handling.

## Options Considered

### Keep The Coding MVP Local-Only

This preserves the simplest privacy boundary and avoids credentials, but it does
not satisfy the immediate fallback need for stronger hosted coding models.

### Add Requesty Or OpenAI Later

This keeps current implementation smaller, but delays the point where the system
can replace daily ad hoc use of external coding assistants.

### Support Local, Requesty, And OpenAI In The First Useful Coding MVP

This gives the provider/orchestrator stack immediate practical value for coding
work while still keeping cloud execution explicit and configuration-driven.

The drawback is that cloud adapter design must be handled deliberately rather
than treated as an incidental provider addition.

## Decision

The first useful provider/orchestrator coding MVP should support:

- local Ollama execution;
- Requesty-backed execution;
- OpenAI-backed execution.

Cloud execution must remain explicit. The provider layer owns cloud API calls,
credentials, request/response translation, provider errors, streaming, and
provider metadata. The orchestrator may recommend a backend/model, but it must
preserve privacy constraints and must not silently route local-only requests to
external processors.

Requesty and OpenAI may share implementation where protocol compatibility makes
that correct, but provider identity must remain visible so recommendations,
metadata, errors, costs, and privacy explanations do not collapse distinct
providers into a single anonymous OpenAI-compatible backend.

Hosted adapters must document which provider API shape they use, such as Chat
Completions, Responses, Anthropic Messages, or another protocol, and why that
shape was selected. When several protocol shapes are viable, prefer the
feature-rich option if it does not compromise compatibility, privacy, cost,
quality, or maintainability. For the first hosted slice, use OpenAI-compatible
Chat Completions because it is the shared protocol documented by Requesty and it
maps directly to the current neutral chat contract. OpenAI's Responses API should
remain a later OpenAI-specific adapter/capability when its richer tools,
computer-use, or agent-oriented features are needed.

Chats should be represented as provider-neutral local transcripts. Switching
models should keep the same application chat and replay the relevant retained
context into the selected backend, with future truncation or summarization made
transparent when context windows require it.

## Rationale

The owner wants provider/orchestrator infrastructure to become directly useful
for coding work. Supporting local, Requesty, and OpenAI paths lets the owner
fall back to stronger hosted coding models from the same interface instead of
relying on a separate IDE assistant workflow.

Keeping transcript ownership local and provider-neutral preserves model
switching and avoids depending on provider-specific hidden chat state.

## Consequences

The next cloud-adapter work must define environment variables, credential
handling, request data boundaries, local-only enforcement, provider identity, and
metadata retention.

The orchestrator catalog should include enough numeric and sourced metadata to
make cloud/local trade-offs understandable, including latency and cost estimates
when available.

Prompt rewriting remains a separate behavior. The safe initial path is prompt
review and suggested refinement with user approval, preserving the original
prompt.

Usage/result persistence remains a later decision. Public and manually curated
catalog metadata can provide initial routing priors, but personalized routing
requires local persisted observations later.

## Related Decisions

- `docs/decisions.md` ADR-002 - Provider-Agnostic AI Boundary
- `docs/decisions.md` ADR-004 - Local and Cloud Backends Must Be Switchable
- `docs/decisions.md` ADR-014 - Provider Contract And Dependencies
- `docs/decisions.md` ADR-015 - Provider Rollout And Prototype Privacy Classes
- `docs/decisions.md` ADR-016 - Optional Package Composition And Neutral Orchestrator Contracts
