# Working on AI Workbench

The workspace contains independently useful libraries and application prototypes.
Start with the [project map](docs/project-map.md) to find the owner of a change,
then check [architecture](docs/architecture.md) and relevant
[decisions](docs/decisions.md). The [README](README.md) distinguishes implemented
software from incomplete model-quality acceptance.

## Set up and check the workspace

Use Python `>=3.13,<3.15` and `uv`. From the repository root:

```powershell
python -m uv sync --locked
python -m uv run --no-sync ai-assistant --help
python -m uv run --no-sync ai-assistant --mode plan "Explain the package boundaries."
```

These CLI commands do not request inference. Ollama, model files and external
native clients are separate, optional prerequisites; see
[installation](docs/installation.md). Private configuration belongs in ignored
local files, using the committed examples as templates. See
[environment and secrets](docs/environment.md).

Run focused checks while implementing, then the full offline gate:

```powershell
python -m uv run --no-sync python scripts/run-tests.py full -- -q
python -m uv run --no-sync ruff check .
python -m uv run --no-sync ruff format --check .
python -m uv run --no-sync pyright
```

The runner checks test ownership and includes workspace, Council and job-search
suites in separate processes. It excludes live integrations. See
[test selection and timing](docs/test-workflow.md) for component groups, JUnit
reports and live-test boundaries. Passing software tests does not certify model
quality, provider availability or factual accuracy.

## Make a focused change

Create a branch from `develop`. Keep provider translation in `ai_provider`,
routing policy in `ai_orchestrator`, and CLI/tool execution in `ai_agent`.
Applications own their product behavior. Reuse existing contracts before adding
another abstraction, dependency or service.

Explain the problem, resulting behavior, checks and remaining limits in the
change description. Update user-facing documentation when behavior changes.
Material architecture, privacy, persistence and product choices belong to the
owner; [AGENTS.md](AGENTS.md) defines that decision process. Check the
[definition of done](docs/definition-of-done.md) before handing work back.

Merge completed, validated work into `develop`. `master` is the portfolio-facing
stable branch and needs explicit promotion. The
[Git workflow](docs/git-workflow.md) covers commits, hooks and branch cleanup;
[publication checks](docs/publication.md) cover both source and outgoing history.
The repository's [source-available license](LICENSE.md) applies; this guide does
not grant an open-source contribution or redistribution license.

## Context for AI assistants

Read [AGENTS.md](AGENTS.md) first. Inspect Git state and the local
`CURRENT_CONTEXT.md` when present; verify a handoff against the actual diff after
an interruption. Read the relevant plan and code before implementing, preserve
owner decisions, and investigate unexplained failures instead of retrying blindly.

Use [the prompt library](docs/prompt-library.md) for named Codex workflows.
Keep durable decisions in the decision index/ADRs and immediate local handoffs
in `CURRENT_CONTEXT.md`. Private plans, prompts, reports and credentials do not
belong in a commit. Follow the standing resource, inference and approval rules;
do not infer authorization from an example command or a previous model report.
