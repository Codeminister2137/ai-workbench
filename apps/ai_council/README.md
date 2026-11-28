# Local AI Council

A local-first prototype that sends one prompt to multiple configured council
members, streams their separate answers, and stores conversation history in a
local SQLite database.

The current execution path uses `ai_provider` with local Ollama. Council owns
the application workflow: loading member configuration, preserving raw member
responses, streaming browser events, and storing history. Provider-specific API
handling stays behind `ai_provider`.

## Investor

Investor research policy and current implementation limits are documented in
[ADR-093](../../docs/decisions/ADR-093-investor-coverage-and-paper-autonomy.md).
The [coverage and geopolitical-event research](../../docs/research/investor-coverage-20261119.md)
compares asset classes, broker access and approaches to learning from decisions.

### Investor expansion: reconciled scope

The original broker-API-versus-scraping blocker is resolved: ADR-092 selects
Alpaca paper as the first broker. ADR-093 permits autonomous simulated decisions
and requires inspectable records, including holds, rejections and failures.
It does not select an execution universe or authorize paid services/live orders.

Implemented: three profiles, synthetic fixtures, stub judging, portfolio metrics,
and an offline decision journal in Council SQLite (owner answer A, inbox
`713fe10d90de4e20abf32e175006c234`). See
[ADR-097](../../docs/decisions/ADR-097-investor-offline-journal.md).

`investor.replay.record_decision` accepts an injected callback returning a
`Proposal`, explicit run/profile/prompt versions and timestamped `Observation`
fixtures. Only observations available at decision time reach the callback.
Records retain profile/model configuration, evidence, rationale, uncertainty,
alternatives, risk checks and simulation assumptions. Empty allocations mean
hold; unknown symbols, negative weights, excessive total allocation and profile
position-limit breaches are rejected. Callback failures record the exception
class, excluding its potentially sensitive message.

`replay(store, run_id)` evaluates saved allocations without invoking deliberation;
profiles at the same decision time must use identical observations. Accepted
weights are complete targets (omitted fixture symbols become zero); holds,
rejections and failures retain existing holdings. Fixtures must retain the held
symbol universe. `assess` appends later outcomes/lessons linked to immutable
original decisions. Both tables prohibit updates/deletes; this is application
integrity, not protection from someone who can modify the SQLite file.

This slice has no council-backed judge. Tests establish software correctness,
not model quality or paper profitability. Injected callbacks own their privacy
and inference authorization; the built-in fixture tests use deterministic
callbacks. Do not put secrets/private transcripts in proposals or assessments.

`investor.guards` proves the paper-only contract a future connected trial must
pass first: https endpoints on the paper trading host only (live hosts fail
with their own message, data hosts stay rejected), credentials from the
paper-named sources only, and simulated orders within a positive notional cap.
Pure checks, no network; slice 2 wires them in front of any broker call.

### Slice 2: bounded loop (owner A, inbox `472cea09`)

`investor.loop.run_day` runs one bounded decision round per call against an
injected `BrokerTransport`: max 5 orders/day, $1,000 max notional per order,
$5,000 max open exposure, fixed SPY/QQQ universe, 5 trading days max, no
shorts. Every round journals exactly one decision; submits, rejects, errors
and halt markers attach as outcome assessments via `replay.assess`, and
`replay.outcomes` reads them back. Any guard trip, broker refusal or journal
failure halts the run with a journaled marker; later calls stay halted.

`investor/` stays offline-pure (`test_investor_stays_offline` bans network
imports there). `OfflineBroker` fills deterministically at configured prices
for tests and the harness. The single Alpaca-paper HTTPS transport
(`alpaca_paper.HttpsTransport`, outside `investor/`) submits market-notional
orders, so no price feed and no market-data exception is needed. Trial state
derives from the journal, so daily invocations need no daemon: run once per
trading day and the loop enforces day caps, the day limit and halts itself.

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

Use `--rounds 2` for member reactions or `--rounds 3` for chair synthesis.
Single-round requests remain the default for compatibility. In `council.json`,
`max_rounds` defaults to 2; set it to 3 to permit synthesis. Optional `chair`
selects a member by name and otherwise uses the first member. Each reaction
receives the other members' R1 answers, truncated to `reaction_cap_chars`
(default 2000) per answer, and is prompted to reply in at most 150 words.
The chair receives answers and reactions and must preserve named disagreements
rather than invent consensus.

`max_tokens_per_question` defaults to 0 (unlimited). The cap uses a rough
characters/4 estimate of conversation and peer inputs plus returned text,
not provider billing usage or a hard generation limit. It is checked between
rounds: the current round finishes, subsequent rounds stop, and results are
marked partial. Streamed cap stops emit `synthesis_finished` with `partial: true`
when synthesis was requested. Stored messages carry a nullable round number;
legacy NULL values read as round 1 without rewriting historical messages.

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
