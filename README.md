# AI Workbench

A Python workspace for local-first AI tooling, provider-agnostic model access,
transparent orchestration, and small AI-assisted applications.

The repository is organized as a modular monorepo. Reusable libraries live under
`packages/`; applications and prototypes live under `apps/`.

## Current Status

| Area | Location | Status |
| --- | --- | --- |
| Provider layer | [ai-provider](packages/ai_provider/README.md) | Local and hosted adapters, streaming, native-client executors, persistent chat, and CLI composition. |
| Orchestrator | [ai-orchestrator](packages/ai_orchestrator/README.md) | Neutral routing, same-tier fallback, reviewer selection, repair progress and time-admission contracts. |
| Agent tooling | [ai-agent](packages/ai_agent/README.md) | Permission-controlled coding tools, protected public research, report validation and source evidence. |
| AI Council | `apps/ai_council/` | Local prototype using Ollama through the provider layer, with browser and CLI entry points. |
| Job search automation | [Job-search prototypes](apps/job_search/README.md) | Early email prototype only; broader automation is not production-ready. |

## What Works Today

- Run local model requests through a provider-neutral interface.
- Route hosted requests through OpenAI-compatible APIs when credentials are
  explicitly configured.
- Use a CLI-first repo-aware coding assistant:

```powershell
.\scripts\repo-assistant.ps1 "Explain the current architecture."
```

- Run deterministic orchestration passes without contacting a provider.
- Produce public-source research reports using local inference, retrieval receipts
  and bounded advisory review.
- Plan research jobs offline and explicitly start a foreground sequence only when
  each task fits its full allocation.
- Run a local AI Council prototype with Ollama.

Most hosted or external-provider paths are opt-in and require explicit privacy,
cost-policy, and credential configuration.

Research quality-first review remains opt-in. Deterministic validation establishes
structure and executed receipts, not factual accuracy. Sustained live acceptance
is still incomplete; the software tests and model-quality evaluation are separate.

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
uv run --no-sync ai-assistant --mode plan "Summarize this repository structure."
```

Inspect a research acceptance plan without loading models or creating run state:

```powershell
uv run --no-sync python scripts/research-acceptance.py --plan --model gpt-oss:20b
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

- [Architecture](docs/architecture.md) and package boundaries
- [Decision index](docs/decisions.md) and ADRs
- [Environment](docs/environment.md) and secret handling
- [Repo assistant](docs/repo-coding-assistant.md) workflow guides
- [Project map](docs/project-map.md) and responsibility ownership
- [Definition of done](docs/definition-of-done.md)
- [Publication and privacy review](docs/publication.md)

Private planning notes may exist locally under `docs/plans/`, but that
directory is ignored in the current source tree. Ignoring a file does not remove
previously committed copies from Git history; publication requires a history review.

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
