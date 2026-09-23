# ADR-016 - Optional Package Composition And Neutral Orchestrator Contracts

**Status:** Accepted

**Date:** 2026-09-18

## Context

The AI projects are intended to work together for the owner's common workflows,
but they should not be unnecessarily coupled. The Orchestrator should be usable
with `ai_provider`, but it should also be usable with direct Ollama calls or a
future executor if the owner chooses that path.

The initial Orchestrator implementation imported `ai_provider` contracts for
backend identity, privacy class, model capabilities, and execution planning. That
made the Orchestrator preparation-only, but not package-independent.

## Options Considered

### Orchestrator Depends On Provider Contracts But Not Provider Execution

This keeps one shared set of backend/privacy/provider types and is simple for the
current workspace.

The drawback is that `ai_orchestrator` cannot be installed or used without
`ai_provider`, even for use cases where a caller wants to adapt decisions to a
different executor.

### Orchestrator Owns Neutral Orchestration Contracts

This lets `ai_orchestrator` return its own execution target, model metadata,
capability, location, and privacy-policy types. Callers can adapt those decisions
to `ai_provider`, direct Ollama calls, or another executor.

The drawback is some overlap with provider-layer concepts, and adapters must map
between orchestration contracts and executor-specific contracts.

### Extract A Shared Contracts Package

This would avoid duplicated concepts while keeping both packages independent from
each other.

The drawback is another package and abstraction layer before there is enough
evidence that shared contracts are stable.

## Decision

Use neutral orchestration-owned contracts in `ai_orchestrator`.

The Orchestrator may be used with `ai_provider`, but must not require it for core
prompt judging, model recommendation, or execution planning. `ExecutionPlan`
returns a neutral `ExecutionTarget`, not an `ai_provider.BackendConfig`.

Use this design philosophy going forward: packages may be designed to compose, but
should not explicitly depend on each other unless the dependency is essential to
the package's responsibility.

## Rationale

The owner chose this because the packages and apps are intended to function
together for personal workflows, while remaining independently useful. In
particular, the owner wants to be able to run `ai_orchestrator` with
`ai_provider`, but also retain the option to use direct Ollama or another executor
without making `ai_provider` mandatory.

## Consequences

`ai_orchestrator` owns its local backend, capability, privacy, and execution-target
contracts.

Adapters or caller code are responsible for translating an Orchestrator
`ExecutionTarget` into `ai_provider.BackendConfig`, direct Ollama request
configuration, or another executor-specific shape.

Some concepts may exist in both `ai_orchestrator` and `ai_provider`. That
duplication is acceptable while the contracts are still evolving. A shared
contracts package remains a future option if multiple packages need the same
stable contract and the duplication becomes harmful.

## Follow-up: Access, Auth, And Billing Metadata

On 2026-09-21, `ModelBackend` and `ExecutionTarget` gained explicit
`access_method`, `auth_method`, and `billing_source` metadata. This preserves the
same optional-composition decision while making execution routes explicit.

Provider API routes can still be adapted to `ai_provider.BackendConfig`. Agent or
client surfaces such as Codex CLI are represented as different access methods and
should use dedicated executors rather than being forced through provider API
adapters.

## Related Decisions

- `docs/decisions.md` ADR-002 - Provider-Agnostic AI Boundary
- `docs/decisions.md` ADR-005 - Orchestrator Is Separate from Provider Infrastructure
- `docs/decisions.md` ADR-012 - No Speculative Infrastructure
- `docs/decisions/ADR-014-provider-contract-and-dependencies.md`
- `docs/decisions/ADR-015-provider-rollout-and-privacy-classes.md`
