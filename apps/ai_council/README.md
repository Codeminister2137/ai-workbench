# Local AI Council

This project runs a private local council of AI agents. Each council member has
its own persona, model, and temperature, while conversation history is stored
locally in SQLite.

The current execution path uses the shared `ai_provider` package with the local
Ollama adapter. The Council still owns the application workflow: loading member
configuration, preserving raw member responses, streaming browser events, and
storing conversation history. Provider-specific request/response handling lives
behind `ai_provider`.

## Requirements

- Python with the dependencies from `pyproject.toml`
- uv, using the repository workspace
- Ollama running locally
- At least one local Ollama model, for example:

```powershell
ollama pull llama3.2
```

## Common Commands

One-time setup:

```powershell
.\tasks.ps1 init
.\tasks.ps1 install
.\tasks.ps1 pull-model
```

Normal startup:

```powershell
.\tasks.ps1 start
```

Then open:

```text
http://127.0.0.1:8765
```

Normal shutdown:

```powershell
.\tasks.ps1 stop
```

Install Python dependencies:

```powershell
.\tasks.ps1 install
```

Create your private local config from the public example:

```powershell
.\tasks.ps1 init
```

Download the default local model:

```powershell
.\tasks.ps1 pull-model
```

Download a different local model:

```powershell
.\tasks.ps1 pull-model -Model mistral
```

Start the browser UI:

```powershell
.\tasks.ps1 start
```

Open:

```text
http://127.0.0.1:8765
```

Check whether the browser UI is running:

```powershell
.\tasks.ps1 status
```

Stop the browser UI:

```powershell
.\tasks.ps1 stop
```

Start on a different port:

```powershell
.\tasks.ps1 start -Port 8766
```

Stop a server running on a different port:

```powershell
.\tasks.ps1 stop -Port 8766
```

Server logs are written to:

```text
logs/council.out.log
logs/council.err.log
```

Run project checks:

```powershell
.\tasks.ps1 check
```

Run only the automated tests:

```powershell
python -m uv run --project apps\ai_council pytest
```

If you have `make` installed, these wrappers are also available:

```powershell
make install
make pull-model
make start
make status
make stop
make check
```

## Ask The Council

Browser UI:

```powershell
.\tasks.ps1 start
```

Open `http://127.0.0.1:8765`.

Each configured councillor gets a separate window. The window status changes from
waiting to generating to finished, and streamed text appears as the local model
returns it.

CLI:

```powershell
.\tasks.ps1 cli -Prompt "What should I consider before changing my exercise routine?"
```

The answers are saved to `data/council.sqlite3`.

Use a named conversation:

```powershell
.\tasks.ps1 cli -Conversation health -Prompt "Summarize my last notes and suggest next questions."
```

List stored conversations:

```powershell
.\tasks.ps1 list
```

The underlying commands still work directly:

```powershell
python -m uv run --project apps\ai_council python web_app.py
python -m uv run --project apps\ai_council python main.py "Ask something"
python -m uv run --project apps\ai_council python main.py --list-conversations
```

When running `python -m uv run --project apps\ai_council python web_app.py`
directly in a terminal, close it with `Ctrl+C`. When running through
`.\tasks.ps1 start`, close it with `.\tasks.ps1 stop`.

## Execution Boundary

`LocalAgent` converts Council conversation history into neutral `ai_provider`
chat messages, then calls `ChatClient.complete(...)` for CLI responses or
`ChatClient.stream(...)` for browser streaming. The initial backend remains local
Ollama, configured from each council member's `model`, `temperature`, and the
optional `ollama_base_url`.

The Council does not currently use `ai_orchestrator` for model selection or
prompt review. That is a later integration step once the product behavior is
clear. Earlier LangChain/LangGraph prototype modules and dependencies have been
removed from the active app metadata; future graph or tool abstractions should be
introduced only when a concrete Council workflow needs them.

## Change Models Or Personas

Copy the public example to your private local config, then edit `council.json`.

```powershell
.\tasks.ps1 init
```

The important privacy and portability detail is that your durable history is not
stored inside a model. The model names live in `council.json`; prompts and answers
live in `data/council.sqlite3`. You can swap a member from `llama3.2` to another
local Ollama model without losing the conversation history.

Example member:

```json
{
  "name": "Clinician-Style Reviewer",
  "model": "llama3.2",
  "temperature": 0.2,
  "system_prompt": "Ask careful clarifying questions and avoid diagnosis."
}
```

## Privacy Boundary

This app is designed for local-first use, but privacy still depends on how you run
it:

- Use local Ollama models only.
- The active Council execution path uses `ai_provider` with local Ollama; do not
  switch to cloud or gateway-backed providers for sensitive prompts without a
  separate privacy and routing decision.
- Do not configure a remote `ollama_base_url` if the prompts contain sensitive data.
- Keep `data/council.sqlite3` private, because it contains your prompts and answers.
- Keep `council.json` private, because it may contain personal councillor prompts,
  defaults, or local endpoint details.
- Treat medical or exercise-related answers as informational, not as a replacement
  for professional care.

## Public Git Safety

The repository is prepared so generated and private files are ignored by Git:

- `council.json` is private local configuration.
- `council.example.json` is the safe public template.
- `data/` stores local SQLite conversations and should not be committed.
- `logs/` stores local server logs and should not be committed.
- Python caches, test caches, virtual environments, and IDE files are ignored.

Before publishing, check what Git would include:

```powershell
git status --short
```

If a sensitive file appears in that output, do not commit it. Add an ignore rule
or move the data out of the repository first.
