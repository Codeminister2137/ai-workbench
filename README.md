# AI Projects

A connected collection of Python projects for AI infrastructure, AI orchestration, automation, job-search tooling, and future IT-service work.

The projects are designed to be:

* practical and actually useful;
* provider-agnostic;
* compatible with both local and cloud AI;
* modular without premature microservices;
* testable and maintainable;
* suitable as portfolio projects;
* developed with human-controlled architectural decisions and Codex-assisted implementation.

---

## Projects

### AI Provider-Agnostic Infrastructure

The common AI integration layer.

Its purpose is to provide a stable interface between applications and AI providers such as:

* Ollama / local models;
* Requesty;
* direct cloud providers.

Applications should not need to know provider-specific API details.

**Status:** First Ollama-backed vertical slice in progress under `packages/ai_provider/`.

The repository also has a working CLI-first coding assistant surface:
`scripts/repo-assistant.ps1` / `python -m uv run ai-assistant`. It supports
local Ollama, hosted provider routes, Codex CLI execution, bounded repository
context, transcript logs, explicit implementation modes, approval-policy
presets, Codex plugin/MCP diagnostics, and selected Codex CLI parity features.
See `docs/repo-coding-assistant.md` for the day-to-day usage guide.

---

### AI Orchestrator

The higher-level AI decision layer.

Potential responsibilities include:

* task classification;
* prompt evaluation;
* prompt refinement;
* model selection;
* request configuration;
* provider/backend routing;
* fallback;
* cost and quota awareness;
* usage tracking;
* eventually adaptive routing based on measured performance.

The Orchestrator is separate from the provider infrastructure.

**Status:** Planned under `packages/ai_orchestrator/`.

---

### AI Council

An application that sends a task to multiple AI models and presents both their individual responses and a synthesis.

Initial goals include:

* multiple model responses;
* raw-response preservation;
* synthesis;
* LOCAL / CLOUD / HYBRID modes;
* visible privacy/backend information.

**Status:** Existing local prototype under `apps/ai_council/`; migration to the provider layer comes later.

---

### Job Search Automation

A Python automation platform for:

* discovering jobs;
* normalizing vacancies;
* matching jobs against the user's experience;
* explaining matching evidence;
* suggesting CV changes;
* generating application messages;
* identifying useful skill gaps;
* tracking applications.

Human review remains part of the workflow before external applications are sent.

The system must never invent experience or qualifications.

**Status:** Existing `job_email` prototype under `apps/job_search/job-email/`; broader automation comes later.

---

### IT Services / Automation

A future business-oriented track for providing services such as:

* websites;
* business process automation;
* API integrations;
* internal tools;
* AI integrations.

This is intentionally kept separate from the personal job-search automation workflow unless a genuinely reusable component emerges.

**Status:** Exploration / future.

---

## Architecture

The intended high-level relationship is:

```text
Applications
│
├── AI Council
├── Job Search Automation
├── Future automation applications
│
└── AI Orchestrator
        │
        ▼
Provider-Agnostic AI Infrastructure
        │
        ├── Ollama
        ├── Requesty
        └── Direct providers
```

The default architecture is a **modular monolith first**.

Components should only become independently deployed services when a real requirement justifies the additional complexity.

See:

* `docs/architecture.md`
* `docs/decisions.md`
* `docs/workflow.md`

---

## Working With Codex

Codex is used as an implementation and engineering partner.

The human owner controls:

* product direction;
* scope;
* architecture;
* privacy decisions;
* provider strategy;
* significant dependencies;
* persistent data decisions;
* other material technical decisions.

Codex should:

* inspect before implementing;
* challenge assumptions;
* identify risks;
* suggest technically sound alternatives;
* ask the user when a material decision is required;
* implement the agreed direction;
* test and review its changes.

**Codex must not silently make material product or architectural decisions simply because an implementation choice seems convenient.**

See `AGENTS.md` for the detailed operating rules.

---

## Documentation

| Document                     | Purpose                                                         |
| ---------------------------- | --------------------------------------------------------------- |
| `AGENTS.md`                  | Instructions for Codex and development behavior                 |
| `CURRENT_CONTEXT.md`         | Local ignored handoff: latest work, conflicts, validation, next plan |
| `docs/architecture.md`       | Current architectural structure and boundaries                  |
| `docs/decisions.md`          | Current decision index and lightweight ADR record               |
| `docs/workflow.md`           | Investigation, decision, implementation and validation workflow |
| `docs/environment.md`        | Environment variables, `.env`, secrets, and privacy policy      |
| `docs/repo-coding-assistant.md` | How to run the repo-aware coding assistant CLI               |
| `docs/project-map.md`        | Where different responsibilities belong                         |
| `docs/definition-of-done.md` | Completion checklist                                            |
| `scripts/repo-assistant.ps1` | One-command launcher for the repo-aware coding assistant        |
| `scripts/session-boundary.ps1` | Read-only Codex/PyCharm chat boundary helper                 |

Private planning notes may exist locally under `docs/plans/`, but that
directory is ignored and is not part of the public repository.

---

## Repository Layout

```text
packages/
  ai_provider/       # shared provider contracts and adapters
  ai_orchestrator/   # future orchestration package
apps/
  ai_council/        # existing local prototype
  job_search/        # job-search applications and prototypes
tests/               # workspace-level provider/integration tests
```

---

## Development Philosophy

The projects should grow from actual requirements.

Prefer:

* simple solutions;
* explicit boundaries;
* small dependencies;
* reusable components only when reuse is real;
* tests around important behavior;
* measured AI performance;
* human control over significant decisions.

Avoid:

* speculative abstractions;
* premature microservices;
* unnecessary infrastructure;
* AI frameworks added solely because a project uses AI;
* autonomous behavior before it can be reliably evaluated.

Complexity must be justified by a real requirement.

---

## License

This repository is source-available for portfolio and review purposes only. No
open-source license is granted. See `LICENSE.md`.

---

## Current Starting Point

The first implementation target is:

**AI Provider-Agnostic Infrastructure**

The first milestone should prove that the same logical AI request can be sent through a provider-independent interface to at least one backend, initially expected to be Ollama.

Only after that foundation is working should additional providers and higher-level orchestration be built.
