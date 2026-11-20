# ADR-096 - Accept existing provider/orchestrator import placement

**Status:** Accepted

**Date:** 2026-11-18

## Owner decision and context

The owner answered B on inbox `d9854413c7044281b5e5dc5ffff06ec2`:
"Document reality + keep ratchet". No additional rationale was supplied.
The decision brief recommended B because shared vocabulary is stable and
extraction would create regression surface without changing behavior.
That recommendation is context, not an inferred personal rationale.

The conceptual provider-below-orchestrator diagram had been read as a strict
import rule. In practice, provider integration/composition helpers consume
orchestrator-owned access, billing and execution-target contracts, catalog
loading, scheduling, review and fallback policy. ADR-048 already left research
and fallback composition helpers in their existing provider modules.

## Decision

Accept the existing placement and document the difference between responsibility
flow and imports. `ai_orchestrator` remains independent of provider and agent
implementations; `ai_agent` composes both. Provider adapters retain provider
translation and authentication; orchestration policy remains orchestrator-owned.

Keep `tests/test_package_layering.py` and its existing pinned up-importer set.
Its 21 entries cover provider imports of orchestrator **or agent**, not 21
orchestrator-only modules. The current ratchet scans unindented `from` imports;
it is not proof that all nested, dynamic or plain `import` statements are absent.
This decision neither widens the pin nor authorizes new crossings by precedent.
New boundary crossings require an explicit owner decision.

This clarifies the conceptual diagram's interpretation and accepts a placement
exception; it does not merge package responsibilities, add dependencies or
change runtime behavior. No shared-contract extraction is required.

## Alternatives and consequences

- A: extract shared contracts into a neutral home. This would clean up the
  import direction, but requires broad caller/re-export migration and regression
  testing across existing modules.
- B (selected): document existing placement and retain the ratchet. This keeps
  compatibility and prevents silent growth in the checked surface, but accepts
  the inversion and leaves integration helpers coupled to orchestrator contracts.
- C: leave documentation unchanged. This costs no implementation work, but
  continues to mislead future contributors about the actual import graph.

Extraction may be reconsidered through a new owner decision if this coupling
creates a concrete maintenance problem. Existing historical decisions remain
intact; ADR-048's focused CLI ownership and compatibility rules still apply.

## Proving checks

Run `python -m pytest tests/test_package_layering.py` to verify orchestrator
independence, permitted agent composition and the unchanged provider ratchet.
Review the final diff to confirm this is a documentation-only decision with
no expansion of the pinned importer set.
