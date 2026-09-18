# ADR-015 - Provider Rollout And Prototype Privacy Classes

**Status:** Accepted

**Date:** 2026-09-18

## Context

The provider infrastructure needs to start with a small working vertical slice while preserving future compatibility with local and cloud backends.

Privacy boundaries matter because local inference is trusted differently from cloud providers and gateways.

## Options Considered

### Implement Multiple Backends Immediately

This would prove the abstraction across Ollama, Requesty, and a direct hosted provider early, but it would require credentials, external data transmission rules, and broader adapter design before the local slice is validated.

### Start With Ollama Only

This keeps the first milestone local and testable while still requiring the interface to be shaped for future backends.

### Defer Privacy Classes

This avoids premature policy design, but it risks adding cloud support later without an explicit privacy vocabulary.

### Define Prototype Privacy Classes Now

This creates a cautious initial privacy vocabulary while marking it provisional until real cloud adapters exist.

## Decision

Implement Ollama first.

Shape the infrastructure for multiple future backends, including Requesty and direct providers, but do not implement cloud adapters in the first milestone.

Define prototype privacy classes now:

- `LOCAL_ONLY`
- `EXTERNAL_ALLOWED`
- `SENSITIVE_REVIEW_REQUIRED`
- `PUBLIC_OR_LOW_RISK`

Treat these classes as provisional until cloud routing and real external providers are implemented.

## Rationale

The owner chose Ollama first while allowing placeholders and extension points for multiple backends. The owner also requested privacy classes now, explicitly marked as prototypes to avoid overcommitting to an early policy model.

## Consequences

The first implementation can run locally without cloud credentials.

Local-only requests must not silently leave the machine.

Future Requesty and direct-provider adapters can be added behind the same contract.

Privacy policy names may change later after real cloud behavior is implemented and evaluated.

## Related Decisions

- `docs/decisions.md` ADR-004 - Local and Cloud Backends Must Be Switchable
- `docs/decisions.md` ADR-010 - Usage Tracking Is a Separate Concern
