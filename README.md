# AI Workbench

**Provider-agnostic AI infrastructure, agent orchestration, and developer automation — built with Python.**

AI Workbench is a modular platform for integrating multiple AI providers, coordinating intelligent agents, and building reliable AI-powered developer tools.

The project explores a practical question:

**How can we make AI agents useful, reliable, and cost-effective when models, APIs, execution environments, and usage limits are constantly changing?**

Rather than depending on a single model or service, AI Workbench separates provider integrations, orchestration decisions, and agent execution into reusable components.

The long-term vision is a unified environment where developers can coordinate AI agents, delegate coding tasks, manage provider availability, and maintain human oversight over automated operations.

> **Development status:** Active development / portfolio project. Core infrastructure, agent tools, and selected applications are implemented. Broader autonomous workflows and sustained live acceptance remain in progress.

## Key Capabilities

### Multi-Provider AI Integration

A common interface for accessing AI models across different execution environments.

- Local inference through Ollama.
- Hosted LLMs through OpenAI-compatible APIs.
- Provider integrations including OpenAI, Requesty, and experimental OpenRouter free-tier routing.
- Native coding-agent execution paths for tools such as Codex CLI, Copilot, Antigravity, and Kiro.
- Streaming responses, usage metadata, and normalized provider errors.

Provider access is kept separate from model selection and application logic, making it easier to add or replace backends.

[Explore the provider package](packages/ai_provider/README.md)

### Intelligent Orchestration and Fallback

An independent orchestration layer designed to make model selection and execution decisions transparent and configurable.

Current capabilities include:

- Task profiling and model recommendations.
- Deterministic prompt evaluation and refinement.
- Capability-, privacy-, and cost-aware route selection.
- Same-tier fallback when usage limits are exhausted.
- Execution planning and subtask delegation contracts.
- Support for bounded repair and review workflows.

An important design principle is that **fallback should preserve task requirements and user-defined constraints**, rather than blindly switching to any available model.

[Explore the orchestrator](packages/ai_orchestrator/README.md)

### Agentic Coding Tools

A repository-aware AI coding assistant with controlled access to development tools.

Capabilities include:

- Multi-turn agent execution and conversational coding.
- File operations, code search, local Git inspection, and shell commands.
- Configurable permission and approval policies.
- Workspace boundaries for filesystem operations.
- Execution tracking and validation receipts.
- Context management and incremental conversation summaries.
- Repair workflows informed by observed validation results.
- Optional preview-first Python symbol refactoring.

The system distinguishes between **a model claiming success and an operation being verified through actual execution evidence**.

[Explore the agent package](packages/ai_agent/README.md)

### Local AI Council

An experimental application that sends a prompt to multiple configured local AI models, streams their individual responses, and stores conversation history.

Current implementation uses Ollama and SQLite, with browser and CLI interfaces.

The Council serves as a practical application of the shared provider infrastructure and a foundation for future multi-model collaboration.

[Explore AI Council](apps/ai_council/README.md)

## Architecture

AI Workbench is organized as a modular Python monorepo.

```text
Applications & Interfaces
├── Repository-aware Coding Assistant
├── Local AI Council
└── Job Search Automation (prototype)
             │
             ▼
      AI Orchestrator
  ├── Task Profiling
  ├── Model Selection
  ├── Execution Planning
  ├── Provider Fallback
  └── Review / Repair Policies
             │
             ▼
       AI Provider Layer
  ├── Local Ollama Models
  ├── Hosted Model APIs
  └── Native Coding Agents
```

The three core packages have distinct responsibilities:

| Package | Responsibility |
|---|---|
| `ai_provider` | Provider communication, adapters, execution backends, and usage metadata |
| `ai_orchestrator` | Task evaluation, routing decisions, fallback, and execution planning |
| `ai_agent` | Agent loops, coding tools, permissions, workflow composition, and CLI execution |

Orchestration does not directly implement provider APIs. Execution components interact with models through appropriate provider interfaces and executors.

This separation allows individual components to evolve without tightly coupling application logic to a particular AI service.

See [Architecture](docs/architecture.md), [Project Map](docs/project-map.md), and [Architecture Decisions](docs/decisions.md).

## What Works Today

The repository currently supports:

- Provider-neutral requests to local and configured hosted models.
- Local and hosted response streaming.
- Deterministic model recommendations and execution planning.
- Policy-constrained provider fallback.
- Repository-aware coding assistance through the CLI.
- Permission-controlled tool execution.
- Research workflows with retrieval records and structural validation.
- Local multi-model conversations through AI Council.

**Important limitations:** End-to-end coding quality and sustained live acceptance are not yet fully validated. Individual components and offline tests should not be interpreted as proof of production readiness. Some provider paths require separately installed clients, credentials, or explicit opt-in.

## Development Roadmap

| Area | Status |
|---|---|
| Provider-neutral integration and adapters | Implemented |
| Core model selection and orchestration contracts | Implemented |
| Provider fallback and policy constraints | Implemented; broader live validation ongoing |
| Agentic coding CLI and controlled tools | Implemented; end-to-end acceptance ongoing |
| Local AI Council | Prototype |
| Automated research and review workflows | Experimental |
| Unified agent management dashboard | Planned |
| Remote task supervision and PC control | Under development |
| Broader job-search automation | Early prototype |

The long-term direction is to extend these foundations into a unified system for coordinating multiple specialized agents across development and automation workflows.

See the [development roadmap](docs/repo-assistant/development-roadmap.md) for detailed implementation and validation progress.

## Quick Start

### Requirements

- Python `>=3.13,<3.15`
- `uv`
- Optional: Ollama for local inference
- Optional: External provider credentials or supported native coding-agent clients

### Install

```powershell
python -m uv sync --locked
```

### Try a Repository Assistant Planning Request

```powershell
uv run --no-sync ai-assistant --mode plan "Summarize this repository structure."
```

This exercises the planning interface without starting model inference.

### Run the Repository Assistant

```powershell
.\scripts\repo-assistant.ps1 "Explain the current architecture."
```

Actual model execution requires a supported and correctly configured backend.

### Run the Local AI Council

```powershell
cd apps\ai_council
.\tasks.ps1 init
.\tasks.ps1 pull-model
.\tasks.ps1 start
```

Open `http://127.0.0.1:8765`.

See the [installation guide](docs/installation.md) for full environment setup and provider configuration.

## Testing and Code Quality

The workspace uses automated tests, static analysis, and documented engineering conventions.

```powershell
python -m uv run --no-sync python scripts/run-tests.py full -- -q
python -m uv run --no-sync ruff check .
python -m uv run --no-sync ruff format --check .
python -m uv run --no-sync pyright
```

Testing emphasizes isolated components, explicit boundaries, controlled external execution, and reproducible validation.

Live model tests require separate configuration and opt-in.

## Engineering Principles

AI Workbench is developed around several principles:

**Provider independence.** Applications should not be unnecessarily tied to one model vendor.

**Transparent decisions.** Routing and execution decisions should be understandable and inspectable.

**User control.** Automated tools must respect permissions, workspace boundaries, privacy requirements, and cost constraints.

**Evidence over claims.** Agent output is not sufficient proof of successful execution.

**Pragmatic architecture.** Prefer maintainable, modular solutions over unnecessary complexity.

**Incremental development.** Implement, test, and validate individual capabilities before expanding automation.

## Documentation

- [Architecture](docs/architecture.md)
- [Project Map](docs/project-map.md)
- [Architecture Decisions](docs/decisions.md)
- [Repository Assistant Guide](docs/repo-coding-assistant.md)
- [Installation](docs/installation.md)
- [Contributing](CONTRIBUTING.md)
- [Testing](docs/test-workflow.md)
- [Privacy and Publication](docs/publication.md)

## License

AI Workbench is **source-available for portfolio and review purposes**.

No open-source license is granted. See [LICENSE.md](LICENSE.md).
