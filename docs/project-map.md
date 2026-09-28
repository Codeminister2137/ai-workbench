# Project Map

Use this file to decide where a change belongs before adding new abstractions.

## Root
- `AGENTS.md` — general Codex rules; especially the requirement to ask the user at material decision boundaries.
- `CURRENT_CONTEXT.md` — local ignored immediate handoff, when present: last completed work, open conflicts/risks, validation status, and next plan.
- `pyproject.toml` — uv workspace and shared validation configuration.
- `uv.lock` — workspace dependency lockfile.
- `scripts/repo-assistant.ps1` — one-command launcher that loads `.env` and
  starts the repo-aware coding assistant CLI.
- `scripts/session-boundary.ps1` - read-only helper for deciding whether to
  continue the current Codex/PyCharm chat or refresh the handoff and start a new
  one.

## `docs/`
- `architecture.md` — current architecture and boundaries.
- `decisions.md` — durable decisions and their history.
- `workflow.md` — investigation, approval, implementation, validation, and Git workflow.
- `git-workflow.md` — branch, commit, validation, and history hygiene guidance.
- `environment.md` — environment variables, `.env`, secrets, and privacy policy.
- `codex-toolkit.md` — reusable local Codex/PyCharm environment notes, including
  approval-mode workarounds.
- `ideas.md` — parked future product/architecture ideas that are useful but not
  active implementation context.
- `prompt-library.md` — canonical full Codex prompt library, usage guide, and PyCharm sync guidance.
- `project-map.md` — this navigation index.
- `definition-of-done.md` — completion checklist.
- `api-docs.md` — generated Python API documentation workflow using `pdoc`.
- `repo-coding-assistant.md` — practical runbook for the repo-aware coding
  assistant CLI, including setup, commands, provider selection, and precautions.
- `plans/` — ignored private local project plans, when present. They are not
  part of the public repository.

## Layout

- `packages/` — reusable Python libraries.
- `apps/` — applications and prototypes.
- `tests/` — repository-level integration and contract tests.

## Projects

### Provider-Agnostic AI Infrastructure
Location: `packages/ai_provider/`

Owns common AI contracts, provider adapters, local/cloud switching, provider API handling, and usage metadata. It does not own application-specific routing strategy.

### AI Orchestrator
Location: `packages/ai_orchestrator/`

Owns task classification, prompt evaluation/refinement, model selection, request configuration, routing, fallback, quota/economics awareness, and usage integration. It owns neutral orchestration contracts and does not directly implement provider APIs or require `ai_provider` for core decision-making.

### AI Council
Location: `apps/ai_council/`

Owns multi-model querying, raw response preservation, comparison/synthesis, and local/cloud/hybrid user-facing behavior. It is an application, not the provider layer. The current implementation is a prototype to migrate after the provider contract exists.
It should be able to use ordinary provider connections or orchestrator-guided
routing through the provider/orchestrator boundaries, without provider-specific
logic leaking into Council business logic.

### Future AI Dashboard / General Chat

Potential future app that brings together provider-backed chat, model routing,
prompt refinement, model benchmarking, AI Council discussions, and project-aware
workflows. It is intended to cover both high-accuracy coding help and broader
daily use cases such as research, planning, shopping decisions, workout plans,
and general chat. It should consume `ai_provider`, `ai_orchestrator`, and
application-specific modules rather than owning provider APIs or replacing
package boundaries.

Do not implement persistence, personal memory, background job scheduling,
web-search integrations, or autonomous external actions for this app without a
separate decision.

### Job Search Automation
Location: `apps/job_search/`

Owns ingestion, normalization, matching, evidence-based analysis, CV/message suggestions, skill-gap analysis, human review, application support, and tracking. It must never invent candidate experience. The current `job_email` tool is a pre-existing prototype to migrate later.

### Future IT Services / Automation
Owns client-facing automation/integration experiments and future business applications. Share code only when there is a genuine stable common need.

### Future Personal AI Assistant / Context
Potential future app or module for local personal context, preferences, habits,
skills, coding style, job-search profile, and mentor-style growth suggestions.
This must remain local/private by default and should not be implemented until a
separate privacy, persistence, and product-scope decision is made.

## Placement rule
If a new component does not clearly fit:
1. define its responsibility;
2. check whether an existing boundary is sufficient;
3. prefer optional composition over unnecessary package dependencies;
4. avoid speculative abstractions;
5. ask the user if architectural placement is materially ambiguous;
6. update this map after the decision.
