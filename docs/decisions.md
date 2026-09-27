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

## ADR-022 - Subtask Profile Derivation And Local Delegation
**Status:** Accepted
**Date:** 2026-09-23

Provide neutral subtask derivation and planning in `ai_orchestrator`. Subtasks
inherit the parent's privacy class by default, default to `LOCAL_ONLY` cost
policy to prefer free local compute for subsidiary steps, and isolate model
overrides from parent tasks.

Detailed ADR: `docs/decisions/ADR-022-subtask-profile-derivation-and-local-delegation.md`

## ADR-023 - Google / Antigravity Access Routes And Live Multi-Model Delegation
**Status:** Accepted
**Date:** 2026-09-24

Support Google Gemini and Antigravity access routes with strict route provenance
in the catalog to distinguish free studio quotas, IDE subscription allowances,
and metered routes. Provide an end-to-end multi-model delegation workflow
connecting local Ollama context extraction with hosted primary models.

Detailed ADR: `docs/decisions/ADR-023-google-antigravity-routes-and-live-delegation.md`

## ADR-024 - Codex CLI Parity, Authorization, And Development Tool Policy
**Status:** Accepted
**Date:** 2026-09-27

Use model-neutral approval policy presets for CLI parity, add only
development-relevant app/tool bridges as concrete needs appear, design read and
write capabilities together even when writes are disabled by default, expand
external connectors one at a time, and keep user authorization behind one
reusable boundary.

Detailed ADR: `docs/decisions/ADR-024-codex-cli-parity-authorization-and-dev-tool-policy.md`

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
```
