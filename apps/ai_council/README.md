# Local AI Council

A local-first prototype that sends one prompt to multiple configured council
members, streams their separate answers, and stores conversation history in a
local SQLite database.

The current execution path uses `ai_provider` with local Ollama. Council owns
the application workflow: loading member configuration, preserving raw member
responses, streaming browser events, and storing history. Provider-specific API
handling stays behind `ai_provider`.

## Requirements

- Python dependencies from the workspace
- `uv`
- Ollama running locally
- At least one local model, for example:

```powershell
ollama pull llama3.2
```

## Setup

From `apps\ai_council`:

```powershell
.\tasks.ps1 init
.\tasks.ps1 install
.\tasks.ps1 pull-model
```

`init` creates a private local `council.json` from `council.example.json`.

## Run

Start the browser UI:

```powershell
.\tasks.ps1 start
```

Open `http://127.0.0.1:8765`.

Stop the server:

```powershell
.\tasks.ps1 stop
```

Check status:

```powershell
.\tasks.ps1 status
```

Use a different port:

```powershell
.\tasks.ps1 start -Port 8766
.\tasks.ps1 stop -Port 8766
```

Server logs are written to `logs/council.out.log` and
`logs/council.err.log`.

## CLI

Ask the configured council from the command line:

```powershell
.\tasks.ps1 cli -Prompt "What should I consider before changing my exercise routine?"
```

Use a named conversation:

```powershell
.\tasks.ps1 cli -Conversation health -Prompt "Summarize my last notes."
```

List stored conversations:

```powershell
.\tasks.ps1 list
```

Answers are saved to `data/council.sqlite3`.

Configuration, conversation history and logs are private local state. Local
inference does not make saved prompts anonymous; inspect outputs before sharing.
The private `council.json`, databases and logs are ignored. See the
[publication and privacy guide](../../docs/publication.md) before publishing.

## Checks

```powershell
.\tasks.ps1 check
```

Run only the automated tests:

```powershell
python -m uv run --project apps\ai_council pytest
```

## Configuration

Edit the private local `council.json` to change members, models, temperatures,
or system prompts.

Example member:

```json
{
  "name": "Careful Reviewer",
  "model": "llama3.2",
  "temperature": 0.2,
  "system_prompt": "Ask careful clarifying questions and state uncertainty plainly."
}
```

The model names live in `council.json`; prompts and answers live in
`data/council.sqlite3`. You can swap local Ollama models without losing
conversation history.

## Privacy

- Use local Ollama models for sensitive prompts.
- Do not configure a remote `ollama_base_url` for sensitive prompts.
- Keep `data/council.sqlite3` private; it contains prompts and answers.
- Keep `council.json` private; it may contain personal prompts or endpoint
  details.
- Treat medical, legal, financial, or exercise-related answers as informational,
  not professional advice.

## Git Safety

Generated and private files are ignored:

- `council.json`
- `data/`
- `logs/`
- Python caches, test caches, virtual environments, and IDE files

Before publishing or committing, check:

```powershell
git status --short
```
