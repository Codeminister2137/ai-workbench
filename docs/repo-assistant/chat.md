# Persistent local chat

[CLI guide](../repo-coding-assistant.md) · [Privacy and permissions](permissions.md)

## Chat transcripts

`--mode chat` starts the first persistent local chat workflow. It stores ordered
provider-neutral messages in SQLite so later turns can resume the same chat:

```powershell
.\scripts\repo-assistant.ps1 `
  "Explain the selected module." `
  --mode chat --execute `
  --provider ollama --model qwen2.5-coder:14b
```

By default transcripts are stored in `data/repo-assistant-chats.sqlite3`. Use
`--chat-db PATH` to choose another local database, `--chat-session last` to
resume the latest chat for the repository, or `--chat-session <session-id>` to
resume a specific session. `--chat-list` prints recent sessions without
contacting a provider.

When a resumed chat grows beyond `--chat-history-budget-chars`, the default
`--chat-context-mode rolling_summary` stores a local rolling summary for older
turns and sends that summary plus the recent raw transcript tail. The CLI prints
whether a summary was used or updated, how many raw messages were sent, how many
were omitted, and the assembled character count. Use
`--chat-context-mode hard_fail` to fail instead of summarizing when the budget is
exceeded, `--chat-context-mode full_history` or `--chat-history-budget-chars 0`
to send the full local transcript, and `--chat-recent-message-count N` to choose
how many recent non-system messages are kept raw.

Chat transcripts may contain the request and selected repository context because
they preserve the provider-neutral messages that were actually sent to the
model. Keep them local and private.

For external-agent routes such as Codex CLI, `--timeout-seconds` is treated as
an inactivity timeout. Model output resets the timer. During execution, the CLI
prints bounded `external_agent_activity` and `external_agent_status` lines so a
foreground run shows that work is still happening without dumping raw JSONL.
The diagnostics block then prints parsed event counts, usage, delegation
status, failure reasons, and concise stderr summaries. Hidden reasoning-summary
events remain type-only and raw JSONL stays in the transcript-only section. The
CLI prints the exact
`external_agent_command_line_json` before execution and adds the effective
approval policy and Codex sandbox to the prompt so the external agent does not
infer a read-only environment when the requested sandbox is `workspace-write` or
stronger. Fresh and resumed Codex exec commands both forward the repository root
with `--cd` and the selected sandbox with `--sandbox` as `codex exec` options
before any resume subcommand. It also includes the repo-assistant system prompt
in the external agent stdin prompt so external routes receive the same
high-level repo-aware contract as provider-native routes. If a timeout or
process error occurs after
partial output, the CLI
summarizes parsed JSONL events and keeps raw JSONL in the transcript-only
section rather than dumping it to the console. Known noisy Codex model-refresh
stderr is filtered out of the main stderr summary. When a transcript log is
active, complete external stderr is saved beside it as `*.stderr.log` and the
transcript prints that path.

Local execution paths use equivalent bounded activity prefixes:
`local_agent_activity` for local provider/native tool-loop model calls,
`delegated_agent_activity` for local context extraction, `scrutiny_activity`
for response scrutiny, and `local_tool_activity` for native-tool or legacy
action follow-up work.

By default, transcript logs do not include the complete assembled model prompt.
Use `--log-full-prompt` with `--log-file` when building evaluation data that
needs exact instructions and repository context. For provider API routes, this
records the exact system prompt and user prompt. For external-agent routes such
as Codex CLI, this records the exact stdin prompt passed to the agent. These
sections may contain `AGENTS.md`, `CURRENT_CONTEXT.md`, selected source files,
and the original request, so keep them local unless reviewed.

Every run also ends with `=== Run metrics ===`. These fields are intended for
comparing CLI changes, model behavior, and local settings over time:

- `total_wall_seconds` and `process_cpu_seconds`;
- `python_memory_current_bytes` and `python_memory_peak_bytes`;
- `primary_elapsed_seconds` and `scrutiny_elapsed_seconds`;
- provider-reported primary and scrutiny token usage when available:
  `*_usage_source`, `*_input_tokens`, `*_output_tokens`, `*_total_tokens`;
- provider-reported latency when available: `*_provider_latency_ms`.

Token and provider-latency fields are `None` or `unavailable` when the backend
does not report them. The memory metrics are Python-process memory observed by
the CLI, not total GPU, Ollama server, IDE, or external-provider resource use.

When using `scripts\repo-assistant.ps1`, transcript logging is on by default.
Each run without an explicit `--log-file` writes to
`artifacts/repo-assistant-YYYYMMDD-HHMMSS/assistant.log`. The canonical broad-analysis
script groups `assistant.log` and `ollama.log` under
`artifacts/repo-assistant-broad-analysis-YYYYMMDD-HHMMSS/` by default. Pass
`--log-file` or `-LogFile` when you intentionally want a fixed path.

When `--start-ollama` is used, Ollama server output is written to
`artifacts/ollama-runtime/ollama-serve.log` by default when calling the Python CLI
directly; the PowerShell launchers supply their run's `ollama.log`.
Change it with `--ollama-log-file`.
The CLI also reports whether the Ollama API is reachable after startup. The
`artifacts/` directory is ignored by Git; legacy/custom `logs/` is also ignored.

To collect a local machine/provider report without sending anything to a model:

```powershell
.\scripts\repo-assistant.ps1 --local-capabilities
```

The report includes OS, CPU count, total/available RAM, detected GPU names and
memory where Windows exposes it, Ollama availability/version, model storage,
and installed/running Ollama models. It is intended as the first stable
onboarding and diagnostics contract for a future app UI or database.

Use `--ollama-profile gaming`, `--ollama-profile balanced`, or
`--ollama-profile full` when the CLI needs to start Ollama with a different
local allocation:

```powershell
.\scripts\repo-assistant.ps1 `
  "Review this file." `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --start-ollama --ollama-profile gaming
```

The profiles currently configure Ollama's default context length to 4,096,
8,192, or 32,768 tokens respectively, while keeping one model and one request
slot active. They control memory pressure and concurrency, not a precise
percentage of GPU utilization. A profile only applies when this command starts
Ollama; stop/restart an already-running Ollama server before changing profiles.

Repository context is deliberately bounded by default: the CLI includes at most
5,000 characters total and 2,500 characters from any one file. Large
`AGENTS.md`, `CURRENT_CONTEXT.md`, or selected source files are shortened from
both ends with a truncation marker, preventing the local model's context window
from being consumed by repository instructions alone. Increase the limits for
a focused task when needed:

```powershell
.\scripts\repo-assistant.ps1 `
  "Analyze this module in detail." `
  --file packages\ai_provider\src\ai_provider\contracts.py `
  --context-budget-chars 12000 `
  --context-file-budget-chars 8000
```

Use `--context-budget-chars 0` only when targeting a model with a known larger
context window.

For a primary request that needs more repository context than the primary model
should receive directly, enable bounded local context delegation:

```powershell
.\scripts\repo-assistant.ps1 `
  "Review this implementation and identify concrete issues." `
  --file packages\ai_provider\examples\repo_coding_assistant.py `
  --provider ollama --model qwen2.5-coder:14b `
  --delegate-context --execute --start-ollama
```

This sends a bounded, line-numbered copy of the loaded context to a local
Ollama model first. The summary must cite supplied sources using
`[source:path:line]` references before it is injected into the primary prompt.
Uncited summaries are discarded. Local delegation is restricted to bounded
support work; architecture and implementation decisions remain with the
primary model. Use `--delegation-context-budget-chars` to adjust the local
context budget. Without `--execute`, the option only reports that delegation is
planned and does not contact a model.

If Windows blocks direct script execution, use this form instead:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\repo-assistant.ps1 "YOUR REQUEST" --provider ollama --model qwen2.5-coder:14b --execute --start-ollama
```

The underlying Python CLI lives at:

```text
packages/ai_provider/src/ai_provider/repo_coding_assistant.py
```

The coding orchestration helpers used by that CLI live in
`packages/ai_provider/src/ai_provider/coding_assist.py`. The older
`packages/ai_provider/examples/coding_assist.py` path remains a compatibility
export, and the example repo-assistant path remains available during the
migration.

Provider-layer failures are reported with `status: failed` and
`execution_status: failed`; the command returns a non-zero exit code instead
of emitting a success-shaped response.
