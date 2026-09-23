# Architecture Decisions

This is the canonical lightweight record of durable architecture decisions. Do not silently rewrite history when a decision changes.

## Statuses
- Proposed
- Accepted
- Superseded
- Rejected

## ADR-001 — Modular Monolith First
**Status:** Accepted

Start with a modular monolith. Extract services only when a concrete operational or architectural need exists.

## ADR-002 — Provider-Agnostic AI Boundary
**Status:** Accepted

Applications use a provider-agnostic AI layer so local inference, gateways, and direct providers can be exchanged without application rewrites.

## ADR-003 — Requesty Is an Integration, Not the Core Architecture
**Status:** Accepted

Requesty may be used as a backend/gateway, but the project will not reproduce Requesty's gateway functionality.

## ADR-004 — Local and Cloud Backends Must Be Switchable
**Status:** Accepted

AI-enabled applications should switch backend through configuration/architecture rather than application rewrites.

## ADR-005 — Orchestrator Is Separate from Provider Infrastructure
**Status:** Accepted

The Orchestrator makes task/model/prompt/routing decisions. Provider infrastructure communicates with providers.

## ADR-006 — Prompt Optimization Starts With Human Approval
**Status:** Accepted

Initial prompt refinement proposes a change and lets the user approve it before execution.

## ADR-007 — AI Evaluation Uses Representative Real Tasks
**Status:** Accepted

Start with approximately 20–50 representative real tasks rather than a large synthetic dataset.

## ADR-008 — Human Approval Before Automated Job Applications
**Status:** Accepted

Keep a human review step before sending applications or taking consequential external actions.

## ADR-009 — CV Tailoring Must Not Invent Experience
**Status:** Accepted

The system may rephrase, prioritize, and reorganize genuine experience, but must not fabricate qualifications, projects, employment, achievements, or skills.

## ADR-010 — Usage Tracking Is a Separate Concern
**Status:** Accepted

Usage tracking supplies data for routing/economics decisions without being tightly coupled to provider adapters.

## ADR-011 — Codex Must Ask at Decision Boundaries
**Status:** Accepted

Codex must ask the user before material product, architecture, dependency, privacy, data-model, or scope decisions. When requirements do not determine the choice, Codex should stop rather than silently invent a requirement.

## ADR-012 — No Speculative Infrastructure
**Status:** Accepted

Do not add Redis, message brokers, vector databases, Kubernetes, agent frameworks, microservices, or similar infrastructure without a demonstrated need.

## ADR-013 — Repository Layout And Workspace
**Status:** Accepted
**Date:** 2026-09-18

Use `packages/` for reusable libraries and `apps/` for applications. Use a root `uv` workspace. Support Python `>=3.13,<3.15`, with local development on Python 3.14.

Detailed ADR: `docs/decisions/ADR-013-repository-layout-and-workspace.md`

## ADR-014 — Provider Contract And Dependencies
**Status:** Accepted
**Date:** 2026-09-18

Use a neutral chat-first provider contract designed for provider-specific child schemas/adapters. Do not put LangChain or LangGraph in the provider core initially.

Detailed ADR: `docs/decisions/ADR-014-provider-contract-and-dependencies.md`

## ADR-015 — Provider Rollout And Prototype Privacy Classes
**Status:** Accepted
**Date:** 2026-09-18

Implement Ollama first while shaping the provider infrastructure for future Requesty and direct-provider adapters. Define prototype privacy classes now and treat them as provisional.

Detailed ADR: `docs/decisions/ADR-015-provider-rollout-and-privacy-classes.md`

## ADR-016 — Optional Package Composition And Neutral Orchestrator Contracts
**Status:** Accepted
**Date:** 2026-09-18

Packages may be designed to work together, but should not require direct
dependencies unless one package cannot usefully exist without the other's
contract. `ai_orchestrator` owns neutral execution-target and model-selection
contracts rather than depending on `ai_provider` contracts.

Detailed ADR: `docs/decisions/ADR-016-optional-package-composition-and-neutral-orchestrator-contracts.md`

## ADR-017 - Dependency Selection Balances Simplicity And Maintenance Cost
**Status:** Accepted
**Date:** 2026-09-18

Prefer standard-library implementations when they are simple, but do not avoid
dependencies when a small, mature, focused library materially reduces custom
complexity, edge-case risk, testing burden, or future maintenance cost. `httpx`
and `pydantic` are pre-approved when concretely justified; other focused
dependencies are permitted when needed.

Detailed ADR: `docs/decisions/ADR-017-dependency-selection-maintenance-cost.md`

## ADR-018 - Provider Streaming Before AI Council Migration
**Status:** Accepted
**Date:** 2026-09-18

Before migrating the AI Council web execution path to `ai_provider`, add a
provider-level streaming contract. This preserves the current Council streaming
UI while moving provider-specific execution behind reusable infrastructure.

Detailed ADR: `docs/decisions/ADR-018-provider-streaming-before-council-migration.md`

## ADR-019 - API Documentation With pdoc And Targeted Docstrings
**Status:** Accepted
**Date:** 2026-09-19

Use `pdoc` as the initial generated Python API documentation tool and add
targeted PEP 257-style docstrings to high-value public surfaces. Do not enable
strict docstring linting until the public API has a clean baseline.

Detailed ADR: `docs/decisions/ADR-019-api-documentation-with-pdoc-and-targeted-docstrings.md`

## ADR-020 - Coding MVP Supports Local Requesty And OpenAI Backends
**Status:** Accepted
**Date:** 2026-09-20

The first useful provider/orchestrator coding assistant should support local
Ollama, Requesty, and OpenAI-backed execution, while preserving explicit privacy,
credential, configuration, and provider-neutral transcript boundaries.

Detailed ADR: `docs/decisions/ADR-020-coding-mvp-local-requesty-openai-backends.md`

## ADR-021 - Access Routes And Cost Policy Boundaries
**Status:** Accepted
**Date:** 2026-09-21

Use access routes, not provider/model pairs alone, as the selectable execution
unit. Enforce tiered cost-policy boundaries before fallback so the system never
silently crosses from local/free/subscription allowance usage into prepaid
credits or metered billing.

Detailed ADR: `docs/decisions/ADR-021-access-routes-and-cost-policy.md`

## Template
```text
## ADR-NNN — Short Name
**Status:** Proposed / Accepted / Superseded / Rejected
**Date:** YYYY-MM-DD

**Context**
What problem required a decision?

**Options considered**
- Option A
- Option B

**Decision**
What was chosen?

**Reason**
Why?

**Consequences**
What becomes easier, harder, or constrained?

**Related**
Relevant plans/issues/ADRs.
```

When an accepted decision changes, mark the old ADR **Superseded** and add a new ADR explaining the change.
