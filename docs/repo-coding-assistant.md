# Repo Coding Assistant CLI

This is a practical guide for using the local repo-aware coding assistant CLI
when the PyCharm AI Assistant / Codex quota is unavailable.

The main startup command is:

```powershell
.\scripts\repo-assistant.ps1 "YOUR REQUEST" --provider ollama --model qwen2.5-coder:14b --execute --start-ollama
```

That wrapper loads `.env` for the run and starts the Python CLI.

If Windows blocks direct script execution, use this form instead:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\repo-assistant.ps1 "YOUR REQUEST" --provider ollama --model qwen2.5-coder:14b --execute --start-ollama
```

The underlying Python CLI lives at:

```text
packages/ai_provider/examples/repo_coding_assistant.py
```

It is intentionally smaller than the PyCharm AI Assistant tab. It can load repo
context, call Ollama/OpenAI/Requesty, and optionally run explicit local file and
command actions proposed by the model. It does not have IDE integration,
persistent memory, a dashboard UI, web/search, background jobs, or autonomous
external actions.

## Where To Run Commands

Use either:

- the PyCharm Terminal tab; or
- a normal Windows PowerShell window.

Both are fine. The important part is the current directory.

Run commands from the repository root:

```powershell
cd C:\Users\Jakub\PycharmProjects\AI-projects
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

Use one of the local models already installed in Ollama, for example:

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
  --file tests\test_repo_coding_assistant_example.py `
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
  --execute --apply-actions
```

Notes:

- `--privacy external_allowed` is required for hosted providers.
- Do not commit API keys.
- The wrapper script loads `.env` for the run.

## Requesty Use

Requesty is also not automatically authorized by the repository. You need a
Requesty API key.
See `docs/environment.md` for the `.env` policy and setup details.

One-time local setup:

```powershell
Copy-Item .env.example .env
```

Then edit `.env` yourself and set `REQUESTY_API_KEY=...`.

Run:

```powershell
.\scripts\repo-assistant.ps1 `
  "Review this code and propose the smallest maintainable change." `
  --file packages\ai_provider\examples\repo_coding_assistant.py `
  --privacy external_allowed `
  --provider requesty --model openai/gpt-5.1 `
  --execute --apply-actions
```

## Adding More Context

Pass `--file` more than once:

```powershell
.\scripts\repo-assistant.ps1 `
  "Explain how these files work together." `
  --file packages\ai_provider\examples\repo_coding_assistant.py `
  --file tests\test_repo_coding_assistant_example.py `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --start-ollama
```

The CLI always tries to include root `AGENTS.md` and `CURRENT_CONTEXT.md`
automatically. You do not need to pass those manually.

## Permission Boundary

Default behavior:

- selected files inside the repo are read automatically;
- assistant actions inside the repo are allowed automatically;
- selected files outside the repo ask first;
- assistant action paths or command working directories outside the repo ask
  first;
- provider calls happen only with `--execute`;
- local file/command actions happen only with `--apply-actions`.

Avoid `--allow-outside-files` unless you deliberately want to allow outside-repo
paths without a prompt.

## Important Precautions

- Review `git diff` after any run that used `--apply-actions`.
- Start with local Ollama for private or sensitive code.
- Use hosted providers only when you are comfortable sending the selected
  context to that external provider.
- Keep API keys in environment variables, not files.
- Do not pass broad directories or secrets as context.
- The action loop can write files and run commands inside the repo. Treat it as
  a coding assistant, not as a fully trusted autonomous agent.

Useful checks after a run:

```powershell
git diff
git status --short
python -m uv run pytest tests\test_repo_coding_assistant_example.py
```

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
