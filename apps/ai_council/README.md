# Local AI Council

A local-first prototype that sends one prompt to multiple configured council
members, streams their separate answers, and stores conversation history in a
local SQLite database.

The current execution path uses `ai_provider` with local Ollama. Council owns
the application workflow: loading member configuration, preserving raw member
responses, streaming browser events, and storing history. Provider-specific API
handling stays behind `ai_provider`.

## Requirements

Investor research policy and current implementation limits are documented in
[ADR-093](../../docs/decisions/ADR-093-investor-coverage-and-paper-autonomy.md).
The [coverage and geopolitical-event research](../../docs/research/investor-coverage-20261119.md)
compares asset classes, broker access and approaches to learning from decisions.

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

The server supports loopback binding only (`127.0.0.1` or `localhost`). Requests
must use the actual loopback host/port; supplied Origin headers must match it.
The ask endpoint requires a JSON object with string prompt/conversation fields,
one Content-Length, and at most 512,000 bytes. The JSON media type is compared
case-insensitively, including when it has parameters. Request body reads have a total
five-second budget. Invalid requests are refused before inference or storage.
These controls do not provide remote-user authentication.

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

## Synthesis evaluation cadence

The weekly forgotten-items sweep review owns the synthesis quality check:
the repository maintenance agent runs it once per week, starting with the
next weekly review after 2026-11-20, and after changes to synthesis prompts,
verdict parsing, or deliberation. This is an explicit-start maintenance
cadence, not an installed timer or an inference step inside the static sweep.
If deferred, the reviewing agent queues an agent inbox follow-up with the
reason and next eligible window so the check is not silently skipped.

From `apps/ai_council`, using the workspace venv Python:

```powershell
..\..\.venv\Scripts\python.exe -m evals.run_synthesis_eval --compare
```

Use the usual live-evaluation gate before starting: announce the GPU work,
check that the owner has not requested gaming/resource time, and declare a
fresh bounded run (one suite, no automatic retries). The fixed synthetic
questions use local Ollama and `qwen3:14b`; check model availability first,
and defer rather than automatically download or substitute a provider.
Do not run against private conversations. Preserve the timestamped
`evals/runs/<stamp>/report.json` and SQLite run artifacts, and record the
date, exit status, report path and any contention in the weekly review receipt.

Compare against `evals/baselines/synthesis-v1.json`: exit 0 passes, exit 1
means overall score fell by more than 0.10, and exit 2 means evaluation
errors or an unavailable baseline. Investigate a failure before another
bounded run; file a regression follow-up rather than using `--record` to
erase it. Baseline replacement needs a separately reviewed explanation.
Offline scorer tests are software checks, not evidence of model quality.

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

## Persistence

Messages require an existing conversation. The store enables its declared SQLite
foreign key on every connection, including resumed databases. Historical rows
are preserved; this enforcement does not repair or delete old orphan rows.
See [SQLite's enforcement requirement](https://www.sqlite.org/foreignkeys.html#fk_enable).

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
