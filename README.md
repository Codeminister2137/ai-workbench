# AI Workbench

A Python workspace for local-first AI tooling, provider-agnostic model access,
transparent orchestration, and small AI-assisted applications.

The repository is organized as a modular monorepo. Reusable libraries live under
`packages/`; applications and prototypes live under `apps/`.

## Current Status

| Area | Location | Status |
| --- | --- | --- |
| Provider layer | `packages/ai_provider/` | Working local Ollama, OpenAI-compatible, Requesty, streaming, usage metadata, local capability, and repo-assistant support. |
| Orchestrator | `packages/ai_orchestrator/` | Working prompt review, model catalog, route recommendation, execution planning, prompt refinement, and delegation planning primitives. |
| Agent tooling | `packages/ai_agent/` | Working provider-neutral tool contracts, permission policies, coding tools, authorization diagnostics, and multi-turn tool loop. |
| AI Council | `apps/ai_council/` | Local prototype using Ollama through the provider layer, with browser and CLI entry points. |
| Job search automation | `apps/job_search/` | Early prototype code only. Broader automation is not production-ready. |

## What Works Today

- Run local model requests through a provider-neutral interface.
- Route hosted requests through OpenAI-compatible APIs when credentials are
  explicitly configured.
- Use a CLI-first repo-aware coding assistant:

```powershell
.\scripts\repo-assistant.ps1 "Explain the current architecture."
```

- Run deterministic orchestration passes without contacting a provider.
- Run a local AI Council prototype with Ollama.

Most hosted or external-provider paths are opt-in and require explicit privacy,
cost-policy, and credential configuration.

## Quick Start

Requirements:

- Python `>=3.13,<3.15`
- `uv`
- Optional: Ollama for local model execution

Install and validate:

```powershell
python -m uv sync
python -m uv run pytest
python -m uv run ruff check .
python -m uv run pyright
```

Run a dry repo-assistant request:

```powershell
.\scripts\repo-assistant.ps1 "Summarize this repository structure."
```

Run the AI Council prototype:

```powershell
cd apps\ai_council
.\tasks.ps1 init
.\tasks.ps1 pull-model
.\tasks.ps1 start
```

Then open `http://127.0.0.1:8765`.

## Architecture

```text
Applications
  AI Council
  Job Search Automation
  Future tools
    |
    v
AI Orchestrator
    |
    v
Provider-Agnostic AI Infrastructure
  Ollama
  Requesty
  Direct provider APIs
  Dedicated executors such as Codex CLI
```

The default architecture is a modular monorepo, not microservices. Packages are
designed to compose through explicit contracts while remaining independently
understandable.

Key docs:

- `docs/architecture.md` - architecture and boundaries
- `docs/decisions.md` - decision index and ADR links
- `docs/environment.md` - environment variables and secret handling
- `docs/repo-coding-assistant.md` - repo-aware coding assistant guide
- `docs/project-map.md` - where responsibilities belong
- `docs/definition-of-done.md` - validation checklist

Private planning notes may exist locally under `docs/plans/`, but that
directory is ignored and is not part of the public repository.

## Repository Layout

```text
packages/
  ai_provider/       # provider contracts, adapters, runtime helpers
  ai_orchestrator/   # prompt review, routing, planning, refinement
  ai_agent/          # tool contracts, permissions, agent loop
apps/
  ai_council/        # local multi-agent council prototype
  job_search/        # early job-search automation prototypes
scripts/             # workspace helper scripts
tests/               # workspace-level tests
docs/                # architecture, decisions, and runbooks
```

## Development

Useful commands:

```powershell
python -m uv run pytest
python -m uv run ruff check .
python -m uv run ruff format --check .
python -m uv run pyright
```

For contributor and agent workflow rules, see `AGENTS.md`.

## License

This repository is source-available for portfolio and review purposes only. No
open-source license is granted. See `LICENSE.md`.
