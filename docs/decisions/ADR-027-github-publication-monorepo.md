# ADR-027 - GitHub Publication Keeps The Workspace Monorepo

**Status:** Accepted

**Date:** 2026-09-28

## Context

The repository is being prepared for GitHub publication. It contains several
related but independently useful projects: provider-agnostic AI infrastructure,
AI orchestration, agent tooling, AI Council, job-search automation, and future
automation work.

The projects should be able to work together, but individual packages and apps
should remain understandable and usable on their own. Splitting into multiple
repositories could make each project smaller, but it would also make cross-cutting
architecture work, shared validation, and Codex-assisted placement of broad
ideas more expensive.

ADR-013 already established a `uv` workspace with `packages/` for reusable
libraries and `apps/` for applications. This decision clarifies that the same
workspace structure remains the GitHub publication strategy.

## Options Considered

### Keep One Public Monorepo

Publish the current workspace as one cleaned-up repository. Maintain clear
internal package and app boundaries, and make each meaningful package or app
independently documented and testable.

### Split Into Multiple Repositories Now

Create separate repositories for infrastructure packages, applications, and
future automation tracks before publication.

### Hybrid Extraction Later

Publish as one monorepo now, then extract mature packages or applications later
when their contracts, release cadence, and ownership boundaries justify it.

## Decision

Keep the project as one GitHub monorepo for now.

The repository should remain organized as a workspace:

```text
packages/
  ai_provider/
  ai_orchestrator/
  ai_agent/
apps/
  ai_council/
  job_search/
```

Each package or app should continue moving toward independent usefulness through
its own README, `pyproject.toml`, tests, examples, and explicit dependency
boundaries. Physical repository extraction is deferred until there is a concrete
need.

## Rationale

The current development style benefits from a shared workspace: broad product or
architecture ideas can be placed into the correct package or application without
requiring cross-repository coordination. The projects are intentionally related,
and the shared provider, orchestrator, and agent boundaries are still evolving.

Separate repositories would add versioning, dependency publication, CI, issue
tracking, and cross-repo change-management overhead before the public APIs are
stable enough to make that cost worthwhile.

Keeping the monorepo does not mean the projects may become tangled. The internal
boundary remains important: packages should compose through explicit contracts,
applications should own their product workflows, and shared code should exist
only where reuse is real.

## Consequences

- GitHub publication should focus on sanitizing and documenting one repository,
  not creating several repositories.
- Workspace-level validation remains useful for cross-package compatibility.
- Individual package and app READMEs become more important because they provide
  the standalone entry points that separate repositories would otherwise provide.
- Future extraction remains possible if package boundaries stay clean.
- ADR-013 remains accepted and is clarified rather than superseded.

## Extraction Criteria

Consider extracting a package or app into its own repository only when at least
one concrete signal appears:

- it has a stable public API and separate release cadence;
- it is useful to develop, version, or publish independently;
- its issue tracking or CI requirements are meaningfully different from the rest
  of the workspace;
- its audience is separate enough that the full monorepo harms understanding;
- repository size, privacy boundaries, or review workflow creates a real
  development bottleneck;
- it needs a different license, publication policy, or access boundary.

Before extraction, record a superseding ADR that identifies the repository split,
dependency strategy, migration path, release ownership, and what history or
documentation moves with the extracted project.

## GitHub Readiness Notes

Before making the repository public, perform a dedicated publication-readiness
pass:

- review tracked files for personal data, private strategy, local config, and
  generated artifacts;
- keep secrets, logs, SQLite files, PDFs, email history, local context, caches,
  and IDE metadata ignored;
- decide whether private planning documents in `docs/plans/` should remain in
  the public repository, be summarized, or stay private;
- ensure each published package or app has a clear README and safe example
  configuration.
