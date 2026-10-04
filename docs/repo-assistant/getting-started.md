# Repo assistant: getting started

[CLI guide](../repo-coding-assistant.md) Â· [Privacy and permissions](permissions.md)

## Moving Work From PyCharm Chat To The CLI

For this repository's current local-only workflow, the CLI is ready to take over
routine coding-assistant work. It is strongest for bounded repository tasks:
planning, asking, reviewing, implementation with explicit local tools, Codex CLI
runs, diagnostics, transcript capture, and validation loops.

Use this default flow when starting a task:

```powershell
# 1. Inspect routing/context without contacting a model
.\scripts\repo-assistant.ps1 --mode plan "YOUR TASK" --file path\to\relevant.py

# 2. Ask for analysis or review without actions
.\scripts\repo-assistant.ps1 --mode review "YOUR TASK" `
  --file path\to\relevant.py `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --start-ollama

# 3. Implement only after the intended change is clear
.\scripts\repo-assistant.ps1 --mode implement "Implement the approved change." `
  --file path\to\relevant.py `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --native-tools --approval-policy interactive --start-ollama

# 4. Verify from the terminal
git diff
git status --short
python -m uv run pytest
python -m uv run ruff check .
python -m uv run ruff format --check .
python -m uv run pyright
```

Use the Codex route when you want the native Codex execution workflow:

```powershell
.\scripts\repo-assistant.ps1 `
  "Review this repository and identify the smallest safe next change." `
  --privacy external_allowed `
  --route-id openai-codex-gpt-5-5 `
  --provider openai --model gpt-5.5 `
  --execute --skip-prompt-review
```

Use `--codex-search`, `--codex-mcp-tools`, `--codex-image`,
`--codex-output-schema`, or `--codex-persist-session` only when the specific
task needs them. They are opt-in because they change network behavior, expose
project-local tools to the Codex run, attach local files, constrain output, or
write Codex session state outside the repository.

Keep PyCharm AI Assistant chat for now when the work depends on IDE-only
context, managed IDE or app/document-control tools, or a material product
or architecture decision that needs discussion before implementation.

Current parity status:

- Ready for local repo coding workflows: yes.
- Ready for Codex CLI-backed coding workflows: mostly, with explicit opt-ins.
- Ready for GitHub, deployment, document-control, or broad connected-app work:
  intentionally no, because this repository is still local-only and those
  connectors require separate authorization decisions.

The workspace also exposes a stable command entry point:

```powershell
python -m uv run ai-assistant --mode plan "Review this module."
```

On Windows, `scripts\repo-assistant.ps1` remains the convenient wrapper because
it loads `.env`, starts the command from the repository root, and adds a
timestamped transcript under `artifacts/repo-assistant-<timestamp>/` when `--log-file` is not supplied.

The CLI supports explicit modes:

```powershell
# Show routing/context/delegation without contacting a model
.\scripts\repo-assistant.ps1 --mode plan "Review this module." --file path\to\module.py

# Answer or review without permitting file/command actions
.\scripts\repo-assistant.ps1 --mode ask "Explain this module." --execute
.\scripts\repo-assistant.ps1 --mode review "Find concrete issues." --execute

# Run a second model pass that scrutinizes the answer quality
.\scripts\repo-assistant.ps1 --mode ask "Investigate the next action for this repository." `
  --provider ollama --model deepseek-coder-v2:16b --execute --start-ollama `
  --scrutinize-response --log-file logs\repo-assistant-next-action.log `
  --ollama-log-file logs\ollama-next-action.log

# Recommended manual live acceptance check for broad repository analysis
.\scripts\repo-assistant-broad-analysis.ps1

# Foreground unattended run with a visible one-hour budget
.\scripts\repo-assistant.ps1 --mode implement "Implement the approved next slice." `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --start-ollama --away-minutes 60 --orchestrated `
  --approval-policy trusted_local

# Dry-run the staged unattended workflow without contacting a provider
.\scripts\repo-assistant.ps1 --mode plan "Implement the approved next slice." `
  --provider ollama --model qwen2.5-coder:14b `
  --away-minutes 60 --orchestrated `
  --approval-policy trusted_local

# Permit approved native tools or legacy actions for implementation
.\scripts\repo-assistant.ps1 --mode implement "Implement the approved fix." `
  --execute --native-tools --start-ollama

# Print local capability and provider readiness information
.\scripts\repo-assistant.ps1 --mode diagnose
```



## Where To Run Commands

Use either:

- the PyCharm Terminal tab; or
- a normal Windows PowerShell window.

Both are fine. The important part is the current directory.

Run commands from the repository root:

```powershell
cd C:\path\to\ai-workbench
```

You can confirm you are in the right place with:

```powershell
git status --short
```

If that command works and shows this repository's status, you are in the right
directory.

## What Is Already Set Up

Already implemented in this repository:

- repo-aware CLI script;
- automatic loading of root `AGENTS.md`;
- automatic loading of root `CURRENT_CONTEXT.md` when present;
- selected file context through `--file`;
- manual provider/model selection for `ollama`, `openai`, and `requesty`;
- local Ollama startup helper through `--start-ollama`;
- explicit execution through `--execute`;
- optional source-grounded local context delegation through `--delegate-context`;
- optional action loop through `--apply-actions`;
- repo-internal files and command working directories are allowed automatically;
- outside-repo files and command working directories ask first unless
  `--allow-outside-files` is passed.

No separate install step is currently needed beyond using the existing repo
environment with `uv`.

The normal startup script is already set up:

```text
scripts/repo-assistant.ps1
```

Use that script for day-to-day commands. It loads `.env` if present and then
starts the Python CLI.

## Local Ollama Use

This is the simplest path. It does not need an API key.

Choose a model installed in your own Ollama runtime, for example:

- `qwen2.5-coder:14b`
- `qwen3:14b`
- `deepseek-coder-v2:16b`
- `gpt-oss:20b`

Dry run without contacting a model:

```powershell
.\scripts\repo-assistant.ps1 `
  "Explain the selected file briefly." `
  --file packages\ai_provider\src\ai_provider\contracts.py `
  --provider ollama --model qwen2.5-coder:14b `
  --skip-prompt-review
```

Ask the local model for an answer:

```powershell
.\scripts\repo-assistant.ps1 `
  "Review this file and suggest the smallest maintainable fix." `
  --file packages\ai_provider\src\ai_provider\contracts.py `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --start-ollama
```

Allow the assistant to use local repo tools:

```powershell
.\scripts\repo-assistant.ps1 `
  "Inspect the selected tests and implement the smallest fix if needed." `
  --file tests\repo_assistant\test_cli_basics.py `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --apply-actions --start-ollama
```

## OpenAI Use

OpenAI is not automatically authorized by the repository. You need an API key.
See `docs/environment.md` for the `.env` policy and setup details.

One-time local setup:

```powershell
Copy-Item .env.example .env
```

Then edit `.env` yourself and set `OPENAI_API_KEY=...`.

Run:

```powershell
.\scripts\repo-assistant.ps1 `
  "Review this code and propose the smallest maintainable change." `
  --file packages\ai_provider\examples\repo_coding_assistant.py `
  --privacy external_allowed `
  --provider openai --model gpt-5-mini `
  --cost-policy billing_allowed --execute --apply-actions
```

Notes:

- `--privacy external_allowed` is required for hosted providers.
- `--cost-policy billing_allowed` is required for OpenAI direct API routes in
  the sample catalog because they can incur metered API billing.
- Do not commit API keys.
- The wrapper script loads `.env` for the run.

## Adding More Context

Pass `--file` more than once:

```powershell
.\scripts\repo-assistant.ps1 `
  "Explain how these files work together." `
  --file packages\ai_provider\examples\repo_coding_assistant.py `
  --file tests\repo_assistant\test_cli_basics.py `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --start-ollama
```

The CLI always tries to include root `AGENTS.md` and `CURRENT_CONTEXT.md`
automatically. You do not need to pass those manually.

For explicitly selected paths inside the repository, it also includes applicable
nested `AGENTS.md` files, ordered from outer directories to inner directories.
Selecting a file outside the repository does not load its neighboring instructions.
Context still has per-file and total character budgets. The CLI prints
`context_file_truncated` or `context_budget_omitted` diagnostics when these limits
cut or exclude a file; these warnings do not guarantee complete instructions or
refuse execution. Check them before relying on the supplied context.

## Quick Command Templates

Local answer only:

```powershell
.\scripts\repo-assistant.ps1 `
  "YOUR REQUEST" `
  --file path\to\file.py `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --start-ollama
```

Local with file/command actions:

```powershell
.\scripts\repo-assistant.ps1 `
  "YOUR REQUEST" `
  --file path\to\file.py `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --apply-actions --start-ollama
```

OpenAI with file/command actions:

```powershell
.\scripts\repo-assistant.ps1 `
  "YOUR REQUEST" `
  --file path\to\file.py `
  --privacy external_allowed `
  --provider openai --model gpt-5-mini `
  --execute --apply-actions
```

Requesty with file/command actions:

```powershell
.\scripts\repo-assistant.ps1 `
  "YOUR REQUEST" `
  --file path\to\file.py `
  --privacy external_allowed `
  --provider requesty --model openai/gpt-5.1 `
  --execute --apply-actions
```

## Implemented scope and remaining work

The stable CLI supports planning, ask/review, permission-controlled implementation,
provider-native tools, native external agents, local transcript chat, rolling
summaries, deterministic validation and repair, public research, advisory review
and user-started foreground research scheduling.

Model-neutral approval presets and secret-free authorization diagnostics are
implemented. Concrete external connectors, OAuth workflows, generic executor
cancellation, automatic background scheduling and a repo-assistant dashboard
remain outside the current scope. CLI chat is implemented; broader persistent
knowledge or autonomous external actions are separate future decisions.

Use [research](research.md), [chat](chat.md) and [scheduling](scheduling.md) for
those workflows. Additional tool bridges require a concrete approved use case;
do not infer automatic access to the IDE's managed tools or external accounts.
