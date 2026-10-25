# AI Workbench

**Provider-agnostic AI infrastructure, orchestration and developer automation,
built with Python.**

How can AI agents remain useful, reliable and cost-effective when models, APIs,
execution environments and usage limits keep changing?

AI Workbench explores that question through reusable provider integrations,
explicit routing and fallback, and a repository-aware coding assistant. Local
and hosted models share contracts so applications can change backends without
rewriting their business logic. Research, multi-model discussions and job-search
prototypes put those components to use.

The engineering focus is making AI execution understandable: which route runs,
what it may access, what checks actually executed, and what remains unverified.
The long-term vision is a unified workbench for coordinating agents and automated
tasks with human oversight. This is an actively developed portfolio project;
implemented components do **not** establish production readiness.

- **Try it:** the [quick start](#quick-start) includes examples without inference.
- **Explore the design:** [architecture](docs/architecture.md),
  [package ownership](docs/project-map.md), and [decisions](docs/decisions.md).
- **Develop:** [contributing](CONTRIBUTING.md) and [repository instructions](AGENTS.md).

## Key Capabilities

### Multiple providers and execution paths

Common chat, streaming, tool-call, usage and error contracts support local Ollama
and configured hosted APIs, including OpenAI and Requesty. OpenRouter's free-only
adapter is experimental and opt-in. Capabilities vary by backend.

Dedicated executors also support official Codex, Copilot, Kiro and Antigravity
clients. These are distinct from API adapters and require separate installation,
sign-in and supported permission mappings.

### Transparent orchestration and fallback

Inspect task profiles, deterministic prompt evaluation/refinement, model
recommendations and execution plans without inference. Coding workflows can
continue on eligible routes after usage exhaustion or overload, subject to
privacy, cost, capability, quality-policy and approval constraints. Fallback
can refuse continuation; catalog grades do not establish measured output quality.

### Repository-aware development

A CLI and saved coding conversations compose inspection, file editing, code
search, local Git inspection, commands, validation, review and bounded repair.
Context management and incremental summaries support conversation continuity.
Optional Python symbol refactoring previews a diff before approved writes.

The workflow distinguishes model claims from host-observed effects and checks.
Its end-to-end acceptance limits are recorded below.

### Research and application prototypes

Restricted research tools discover and fetch public sources, then write a
configured report. Local review, structural validation and foreground research
scheduling record observed work; receipts do not certify factual accuracy.

AI Council streams responses from configured local Ollama members through
browser and CLI interfaces, with SQLite conversation history. Job-search code
supports evidence-backed preparation and human-approved email delivery, with
an Openings integration bridge under validation.

## Architecture

Reusable libraries live under `packages/`; applications live under `apps/`.

```text
Applications and repository assistant CLI
                  |
                  v
ai-orchestrator: optional routing, planning and review policy
                  |
                  v
ai-provider: API adapters and dedicated native-client executors
                  |
          +-------+----------------+
          |                        |
   Ollama / hosted APIs     Official coding clients
```

| Package | Responsibility |
| --- | --- |
| [ai-provider](packages/ai_provider/README.md) | Provider protocols, API adapters, dedicated executors and usage metadata |
| [ai-orchestrator](packages/ai_orchestrator/README.md) | Task evaluation, routing/fallback decisions and neutral execution planning |
| [ai-agent](packages/ai_agent/README.md) | Agent loop, coding tools, permissions, workflow composition and CLI |

The Orchestrator returns neutral execution targets without calling providers or
requiring `ai-provider`. Callers choose an executor; applications may also use
the provider layer directly. The project favors explicit composition within a
modular monorepo.

## Implementation Status

Implemented software and successful tests are separate from model-quality or
end-to-end workflow acceptance.

| Status | Scope | Evidence and limits |
| --- | --- | --- |
| Implemented | Provider contracts/adapters, deterministic routing, fallback policies, permission-controlled tools and coding-session storage | See the package READMEs above and [CLI guides](docs/repo-coding-assistant.md). Native executors support specific client/policy mappings, not interchangeable permissions or guaranteed availability. |
| Experimental | Complete coding, fallback, scrutiny and repair workflows across models/clients | Bounded live trials exist, but clean end-to-end coding and frozen-review acceptance remains incomplete. See [baseline assessment](docs/repo-assistant/baseline-gap.md). |
| Experimental | Public-source research and foreground research jobs | Retrieval/report plumbing is implemented. Quality-first review is opt-in; sustained research-quality acceptance remains incomplete. Structure and receipts do not prove factual accuracy. See [research](docs/repo-assistant/research.md). |
| Prototype | [AI Council](apps/ai_council/README.md) and [job-search workflows](apps/job_search/README.md) | Council currently uses local Ollama. Job-search preparation and guarded delivery exist; broader automation and real Openings deployment are not established. |
| Planned | General repository egress protection and broader application workflows | The [restricted-input plan](docs/repo-assistant/restricted-input-plan.md) distinguishes the implemented single reviewed-input path from future general protection. See the [roadmap](docs/repo-assistant/development-roadmap.md) for priorities. |
| Planned direction | Unified agent/provider dashboard | The [architecture](docs/architecture.md) describes the vision. A unified management UI is not implemented; its detailed product and data decisions remain open. |
| Not implemented | Mobile-to-PC remote control | The repository has local browser/MCP endpoints, but no implemented phone controller or remote-control workflow. This would be future work, not a current capability. |

## Quick Start

Run workspace commands from the repository root. Requirements:

- Python `>=3.13,<3.15` and `uv` available to that Python interpreter.
- Optional: Ollama and installed models for local inference.
- Optional: separately provisioned official clients or API credentials for hosted
  execution. Python dependency installation does not install those runtimes.

See [installation](docs/installation.md) for environment ownership and external
prerequisites. Python dependencies belong in the `uv`-managed workspace `.venv`.

### Install and check the workspace

```powershell
python -m uv sync --locked
python -m uv run --no-sync python scripts/run-tests.py full -- -q
python -m uv run --no-sync ruff check .
python -m uv run --no-sync ruff format --check .
python -m uv run --no-sync pyright
```

The offline runner covers workspace, Council and job-search tests in separate
processes. Live model tests require explicit opt-in; these checks do not start
inference. See [test selection](docs/test-workflow.md).

### Inspect plans without inference

```powershell
python -m uv run --no-sync ai-assistant --mode plan "Summarize this repository structure."
python -m uv run --no-sync python scripts/research-acceptance.py --plan --model gpt-oss:20b
```

The first command prepares a repository-assistant plan; the second prints a
research acceptance plan without loading a model or creating run artifacts.
Neither requires model credentials. The Windows convenience launcher is also
available:

```powershell
.\scripts\repo-assistant.ps1 --mode plan "Explain the current architecture."
```

That launcher loads a local `.env` if present and configures diagnostic logs.
Use the direct command above when that convenience is unnecessary. Actual model
execution requires `--execute` and the selected route's prerequisites.

### Run the local AI Council prototype

With Ollama installed and running, use PowerShell:

```powershell
cd apps\ai_council
.\tasks.ps1 init
.\tasks.ps1 pull-model
.\tasks.ps1 start
```

`init` creates local configuration if absent. `pull-model` explicitly downloads
the default `llama3.2` model; review the configuration before using private data.
Open `http://127.0.0.1:8765`. Run `.\tasks.ps1 stop` from the same directory to
stop the prototype. See [Council setup](apps/ai_council/README.md) for details.

## Engineering Principles and Privacy

- **Separate responsibilities.** Keep provider protocols, routing decisions,
  tool execution and application behavior behind explicit contracts.
- **Prefer maintainable, incremental development.** Validate focused components
  before expanding automation; add infrastructure only for demonstrated needs.
- **Keep decisions visible.** Record architectural choices and preserve the
  owner's authority over privacy, dependencies, services and product direction.
- **Validate effects, not just claims.** Distinguish executed checks, model
  reports and reviewer advice. A review pass is not independent factual proof.
- **Use bounded execution and explicit permissions.** File tools check workspace
  boundaries. Shell permissions govern command execution but **do not create an
  OS sandbox**; external clients retain their own supported restrictions.
- **Treat external processing explicitly.** Hosted models can receive selected
  context, history and tool output. Local inference does not make web search
  private: discovery services receive queries and websites receive fetch requests.

Keep keys in the process environment or an ignored local `.env`, never in prompts
or committed files. Review exactly what context and tools can expose before
using a hosted route. General coding does not provide a comprehensive secret or
private-content filter. Start with local inference for sensitive code, and read
the [permission and privacy boundaries](docs/repo-assistant/permissions.md).

Private plans and runtime artifacts may exist locally. `.gitignore` does not
remove previously committed material from Git history; review both the current
tree and history before publication. See [environment and secrets](docs/environment.md)
and [publication guidance](docs/publication.md).

## Documentation

- [Architecture](docs/architecture.md), [project map](docs/project-map.md), and
  [decision index](docs/decisions.md)
- [CLI workflow guides](docs/repo-coding-assistant.md),
  [development roadmap](docs/repo-assistant/development-roadmap.md), and
  [acceptance criteria](docs/repo-assistant/acceptance-criteria.md)
- [Provider interface](packages/ai_provider/docs/interface.md) and
  [dated provider/source findings](packages/ai_provider/docs/source-state.md)
- [Installation](docs/installation.md), [contributing](CONTRIBUTING.md),
  [test workflow](docs/test-workflow.md), and [definition of done](docs/definition-of-done.md)
- [Repository instructions](AGENTS.md), [environment](docs/environment.md), and
  [publication/privacy review](docs/publication.md)

```text
packages/  Reusable provider, orchestrator and agent libraries
apps/      AI Council and job-search prototypes
scripts/   Workspace launchers, diagnostics and acceptance helpers
tests/     Workspace-level tests
docs/      Architecture, decisions and workflow guides
```

## License

Source-available for portfolio and review purposes only. **No open-source license
is granted.** Commercial use, redistribution and derivative works require prior
written permission from the copyright holder. See [LICENSE.md](LICENSE.md) for
the full terms, including the GitHub viewing/forking exception.
