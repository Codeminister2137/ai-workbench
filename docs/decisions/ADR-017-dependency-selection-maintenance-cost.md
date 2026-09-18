# ADR-017 - Dependency Selection Balances Simplicity And Maintenance Cost

**Status:** Accepted

**Date:** 2026-09-18

## Context

The repository previously emphasized standard Python and small focused
dependencies. That remains a good default, but dependency avoidance can become
counterproductive when it leads to complex custom functions, fragile edge-case
handling, excessive tests, or higher token/time cost for future work.

Maintainability also depends on what the human owner can debug comfortably and
what Codex can use reliably. Widely used, well-documented, stable, focused
libraries often reduce implementation risk compared with hand-rolled
infrastructure.

## Options Considered

### Prefer Standard Library Unless Impossible

This minimizes the dependency surface, but can push complexity into local code
and make provider/configuration behavior harder to test and maintain.

### Add Dependencies Freely For Convenience

This can speed development, but risks unnecessary lock-in, hidden behavior,
larger transitive dependency trees, and architecture drift.

### Use Dependencies When They Reduce Real Complexity

This keeps the standard library as the default for simple cases while allowing
small, mature, focused dependencies when they materially improve correctness,
readability, testability, or maintenance.

## Decision

Use dependencies when they reduce real complexity.

Prefer the standard library when the implementation remains simple and clear.
Prefer a small, mature, focused dependency when it materially reduces custom
code, edge-case risk, testing burden, or future maintenance cost.

The owner explicitly pre-approves:

- `httpx`, when HTTP behavior grows beyond simple standard-library calls, such
  as streaming, async support, connection pooling, richer timeout handling,
  cleaner tests, or more maintainable provider adapters.
- `pydantic`, when validation, parsing, configuration, or public contracts
  become noisy or error-prone with dataclasses and manual checks.

Other focused dependencies are permitted when justified by the same criteria.
Large frameworks, infrastructure dependencies, and dependencies that blur
provider/orchestrator/application boundaries still require explicit approval.

## Rationale

The owner wants the codebase to remain understandable and easy to debug, and is
already familiar with `httpx` and `pydantic`. Codex also tends to work more
reliably with widely used, well-documented, stable, focused libraries than with
large custom implementations of common behavior.

This decision prevents both extremes: avoiding useful libraries until local code
becomes complicated, and adding broad dependencies before there is a concrete
need.

## Consequences

Future implementation planning should include the cost of not adding a
dependency, including custom-code complexity, test surface, debugging time, and
future Codex token/time cost.

`httpx` and `pydantic` may be added without asking again when a concrete task
meets the criteria in this ADR. They should still be added only to the package
that needs them.

Dependencies such as LangChain, LangGraph, Redis, vector databases, message
brokers, Kubernetes, and similar infrastructure remain inappropriate unless a
specific approved decision justifies them.

## Related Decisions

- `docs/decisions.md` ADR-011 - Codex Must Ask at Decision Boundaries
- `docs/decisions.md` ADR-012 - No Speculative Infrastructure
- `docs/decisions/ADR-014-provider-contract-and-dependencies.md`
