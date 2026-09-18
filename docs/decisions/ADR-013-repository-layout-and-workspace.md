# ADR-013 - Repository Layout And Workspace

**Status:** Accepted

**Date:** 2026-09-18

## Context

The repository contains connected Python projects for provider infrastructure, orchestration, the AI Council, and job-search automation. Existing application prototypes lived in top-level folders, while the reusable provider and orchestrator packages were empty.

The owner approved restructuring before implementation so reusable packages and applications have clearer ownership boundaries.

## Options Considered

### Keep Current Top-Level Folders

This would preserve the existing layout and avoid mechanical moves, but it would make reusable library packages and application projects less explicit once local dependencies are introduced.

### Use `packages/` And `apps/`

This separates reusable infrastructure from applications:

```text
packages/
  ai_provider/
  ai_orchestrator/
apps/
  ai_council/
  job_search/
```

This fits the documented dependency direction and makes future local package dependencies clearer.

## Decision

Use `packages/` for reusable libraries and `apps/` for applications.

Use a `uv` workspace at the repository root.

Support Python `>=3.13,<3.15`, with local development on Python 3.14.

## Rationale

The owner approved restructuring because the connected-project structure should be easier to manage long-term. `uv` was chosen because the repository is becoming a monorepo with multiple local packages and apps.

The Python version range keeps the project modern while avoiding an unnecessary 3.14-only constraint.

## Consequences

Reusable infrastructure can be developed and tested independently from applications.

Existing Poetry projects become prototypes inside `apps/` and can be migrated incrementally.

The repository will use `uv.lock` instead of per-project Poetry lockfiles after migration.

## Related Decisions

- `docs/decisions.md` ADR-001 - Modular Monolith First
- `docs/decisions.md` ADR-002 - Provider-Agnostic AI Boundary
