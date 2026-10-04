# ADR-040 - Shared Agent Tools and CLI Development Foundation

**Status:** Accepted direction and scope; implementation incomplete
**Date:** 2026-10-04

## Context

The owner wants the repo assistant CLI to become the daily development assistant.
Usage-limit fallback already exists, but client-specific feature and permission
mappings can exclude replacements. Shared tool access and development continuity
are not yet verified across official clients and provider-native execution.

ADR-024 established model-neutral approvals and explicit development tool bridges.
ADR-031 retained official clients as execution routes, and ADR-032 established
same-tier usage-limit recovery. This decision extends those directions rather
than replacing their privacy, cost or authorization boundaries.

## Options considered

1. Share project-owned tool implementations through MCP and native adapters,
   retaining official client execution and allowance access.
2. Replace all client execution with one project-owned agent loop. This offers
   more control but requires more implementation; subscription allowances do
   not necessarily expose direct model API access.
3. Keep separate client tool sets and translate flags only. This is smaller but
   does not meet the owner's common-tool objective.

## Decision

The owner approved option 1 and the six-capability development foundation:

- repository inspection, search, edits and local Git;
- portable skills and repository instructions;
- Python environment selection, tests and diagnostics;
- documentation lookup and public research;
- semantic code navigation and safe refactoring;
- process control and development-session continuity.

Retain existing `ai_agent` tool contracts and implementations as the foundation.
Expose common operations through native provider tools and MCP/client adapters.
Keep route decisions in `ai_orchestrator` and provider/client translation in
execution adapters. Do not merge these packages into one provider-specific layer.

PyCharm may initially host tools. The eventual target is that it serves only as
the human code editor/viewer; migrate tools independently while preserving their
project-owned contracts. Supported agents should retain access to the required
common tools when fallback occurs. Model performance differences are acceptable.

Preserve task context and observed progress through a visible handoff. Do not
promise transferable private reasoning, identical model behavior or exact-once
effects. Reconcile uncertain in-flight operations before retrying them.
Approvals retain their original scope; changing clients does not broaden grants.

Deliver this scope through the milestones in the
[development roadmap](../repo-assistant/development-roadmap.md), starting with
deterministic readiness and adapter checks. Separate offline correctness from
live client compatibility and model-quality evidence.

## Rationale

The owner's stated intent is to move development interaction to the project CLI,
eventually remove its dependence on PyCharm as an agent tool host, and keep tools
available through agent switches. Different model performance is acceptable.
The owner also requested durable decisions and milestones for session continuity.

The technical recommendation accepted with this scope was to preserve existing
official allowance clients, reuse shared tools, and replace IDE-backed operations
incrementally. This is the engineering rationale presented for the recommendation;
no additional personal rationale is inferred.

## Boundaries and unresolved implementation choices

This approves the architectural direction and capability scope, not a particular
session schema, storage migration, daemon, SDK, language server, dependency or
approval transport. Investigate these choices before implementation; stop only
the affected work at a material decision boundary and continue independent work.

Browser testing, notebooks, debugger control, GitHub account operations, visual
document analysis, image generation and expanded delegation/scheduling remain
separately selectable. None was selected by the foundation approval. Local Git
is included; external GitHub access is not implicitly included.

New external services, credentials, transmissions, stronger permissions and
external writes still follow ADR-024 and the repository's approval boundaries.
Shared tool availability does not authorize every tool invocation. Native client
tools also need verified permission mappings; MCP annotations alone are not
security enforcement.

ADR-032's same-tier/different-billing-source rule remains in force. Do not add
paid escalation or loosen privacy/quality requirements to fill a capability gap.

Long local model work remains planned for a selected compute window. ADR-039's
scheduler remains bounded to supported research tasks; no generic job queue or
automatic live execution is approved by this decision.

## Consequences

- Agent capability mapping and portable skills become explicit development work.
- Daily development continuity is an outcome with acceptance criteria, not merely
  a native client's resume flag.
- IDE independence is achieved by replacing capabilities in stages.
- Client-native features may coexist with common tools; identical complete
  client menus are not required or guaranteed.
- Unsupported capability or approval combinations must fail with an actionable
  explanation before work, rather than silently degrading the required tool set.
- Implemented behavior remains documented separately from this accepted target.
