# ADR-025: Local-First Auxiliary AI Work

## Status
Accepted

## Date
2026-09-27

## Context
The repo assistant is intended to improve coding quality without increasing
cost, and preferably while reducing paid or allowance-backed model usage. The
CLI already supports high-capability primary routes such as Codex CLI and
hosted provider APIs, plus local Ollama routes and delegated context
extraction.

Auxiliary AI work can easily double cost if it blindly reuses the same primary
route. Examples include response scrutiny, prompt refinement, context
summarization, test-case generation, and other support passes. Those calls are
valuable, but they should not silently consume the same expensive or limited
capacity as the primary model when a local or cheaper model is good enough.

## Options Considered

### Reuse The Primary Route For All Auxiliary Passes
This maximizes capability consistency and is simple to implement.

The drawback is predictable cost and allowance growth. A broad review with
scrutiny becomes at least two expensive calls, even when the scrutiny task is
well suited to local evaluation.

### Disable Auxiliary Passes By Default
This minimizes extra calls.

The drawback is lower answer quality and weaker evaluation loops. It also does
not use available local compute effectively.

### Prefer Local Or Cheaper Routes For Auxiliary Passes
This keeps auxiliary quality checks and support work available while respecting
cost boundaries. It matches the existing `derive_subtask_profile` default where
subtasks use `LOCAL_ONLY` cost policy unless explicitly overridden.

The drawback is that local models may miss issues on high-stakes tasks. Those
cases need an explicit escalation path rather than silent reuse of the primary
route.

## Decision
Auxiliary AI work should be local-first and cost-minimizing by default.

For coding assistant workflows:

- Primary task routing may use the route selected by the task profile, privacy
  class, quality threshold, and cost-policy tier.
- Auxiliary support passes should derive their own child task profiles instead
  of inheriting the primary route.
- Child profiles default to `LOCAL_ONLY` cost policy and should avoid inheriting
  primary user provider/model overrides unless the caller explicitly supplies
  auxiliary overrides.
- Response scrutiny uses a local-only child profile by default.
- Context extraction, summarization, prompt refinement, and similar support
  work should prefer local/free/cheaper models when they are suitable.
- Escalating an auxiliary pass to Codex, hosted APIs, prepaid credits, or
  metered billing requires an explicit task need and should remain visible in
  route/cost reporting.

## Rationale
The owner wants higher-quality coding assistance without increasing costs. Local
or cheaper models are usually sufficient for bounded support tasks, especially
when their outputs are source-grounded or used as critique rather than as final
architecture authority. High-capability models should be reserved for work that
actually needs them.

## Consequences
- `ai_orchestrator` remains responsible for deriving separate child profiles
  for support tasks.
- CLI features that add model calls must document whether they use the primary
  route or a derived auxiliary route.
- A second model pass is not automatically a second high-cost pass.
- Important or high-risk support checks may still use stronger routes, but that
  escalation is an explicit routing/cost decision.

## Related Decisions
- ADR-021 - Access Routes And Cost Policy Boundaries
- ADR-022 - Subtask Profile Derivation And Local Delegation
- ADR-023 - Google / Antigravity Access Routes And Live Multi-Model Delegation
