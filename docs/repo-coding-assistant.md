# Repo Coding Assistant CLI

This is a practical guide for using the local repo-aware coding assistant CLI
when the PyCharm AI Assistant / Codex quota is unavailable.

The main startup command is:

```powershell
.\scripts\repo-assistant.ps1 "YOUR REQUEST" --provider ollama --model qwen2.5-coder:14b --execute --start-ollama
```

The workspace also exposes a stable command entry point:

```powershell
python -m uv run ai-assistant --mode plan "Review this module."
```

On Windows, `scripts\repo-assistant.ps1` remains the convenient wrapper because
it loads `.env`, starts the command from the repository root, and adds a
timestamped transcript log under `logs\` when `--log-file` is not supplied.

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

# Permit approved native tools or legacy actions for implementation
.\scripts\repo-assistant.ps1 --mode implement "Implement the approved fix." `
  --execute --native-tools --start-ollama

# Print local capability and provider readiness information
.\scripts\repo-assistant.ps1 --mode diagnose
```

`ask` is the default for backward compatibility. `plan` never contacts a
provider. `ask` and `review` reject action flags. `implement` requires
`--execute` plus either `--native-tools` or `--apply-actions`.

Every run prints an `execution_status` line. It distinguishes planned runs,
completed responses, completed runs with tool/action errors, and failed
orchestration. A response is not reported as a fully successful implementation
when an approved tool or action returned an error.

`--scrutinize-response` is an opt-in second provider call for `ask` or `review`.
It evaluates the completed answer against the original request and repository
context, then prints a structured verdict, score, issues, recommended next
action, and revised response. It does not edit files or execute actions. The
CLI parses and validates Markdown-compatible report headings with the required
labels, including case and underscore/space variants for known labels, or a JSON
object with the same required keys, before marking scrutiny as completed. It
emits normalized `scrutiny_verdict` and `scrutiny_score` lines for log
inspection. A malformed scrutiny report is reported as
`scrutiny_status: invalid`; a non-pass verdict leaves the primary answer intact
but marks the run as
`execution_status: completed_with_scrutiny_findings`. The additional report is
included in the same `--log-file` transcript, so this is the recommended
broad-repository response-quality command.

For repeated manual live acceptance checks, use
`scripts\repo-assistant-broad-analysis.ps1`. This is not a unit test: it makes
two real provider calls and the final answer remains subject to human
evaluation. The script is the canonical, evolvable version of the command; its
default prompt, provider/model, timestamped transcript/runtime logs, full-prompt
evaluation capture, and quality flags are kept together.
Pass `-Prompt`, `-Model`, `-LogFile`, or `-OllamaLogFile` when a test needs a
different value without duplicating the workflow:

```powershell
.\scripts\repo-assistant-broad-analysis.ps1 `
  -Prompt "Review the latest provider change and identify the smallest next milestone." `
  -LogFile logs\provider-change-analysis.log
```

When adding a CLI feature that should be part of the standard broad-analysis
workflow, update `scripts\repo-assistant-broad-analysis.ps1` rather than
creating a separate one-off command. Keep the command synchronized with the
**Canonical Manual Live Acceptance Check** section in `CURRENT_CONTEXT.md`;
future sessions should read that section first.

To use the new provider-native tool-calling loop, add `--native-tools`:

```powershell
.\scripts\repo-assistant.ps1 "YOUR REQUEST" --provider ollama --model qwen2.5-coder:14b --execute --native-tools --start-ollama
```

Native mode uses the shared `ai_provider` tool-call contract and `ai_agent.AgentLoop`.
Reads are allowed automatically; file writes and shell commands ask for interactive
approval. `--apply-actions` remains available as the legacy fenced-JSON action protocol.

That wrapper loads `.env` for the run and starts the Python CLI.

The CLI prints phase headers so metadata and the model response are easy to
scan. To preserve a complete local transcript for later analysis, opt in with
`--log-file`; transcript files may contain the request and repository context,
so keep them local:

```powershell
.\scripts\repo-assistant.ps1 `
  "Review the selected file." `
  --file packages\ai_provider\examples\repo_coding_assistant.py `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --start-ollama `
  --log-file logs\repo-assistant-latest.log
```

Logged transcripts start with a `=== CLI invocation ===` section containing the
UTC timestamp, current working directory, argv as JSON, and the original request
text. The rest of the file mirrors the CLI output, including route metadata,
assistant response, action-loop output, scrutiny output, normalized scrutiny
status, and final `execution_status`.

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
`logs\repo-assistant-YYYYMMDD-HHMMSS.log`. The canonical broad-analysis script
uses timestamped `logs\repo-assistant-broad-analysis-YYYYMMDD-HHMMSS.log` and
`logs\ollama-broad-analysis-YYYYMMDD-HHMMSS.log` paths by default. Pass
`--log-file` or `-LogFile` when you intentionally want a fixed path.

When `--start-ollama` is used, Ollama server output is written to
`logs\ollama-serve.log` by default. Change it with `--ollama-log-file`.
The CLI also reports whether the Ollama API is reachable after startup. The
`logs/` directory is ignored by Git.

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

## External Coding Agent Routes

The catalog includes subscription/client-backed coding-agent routes alongside
provider API routes:

- Codex CLI: `openai-codex-gpt-5-5`, access method `codex_cli`;
- Google Antigravity: `google-antigravity-gemini-3-1-pro` and
  `google-antigravity-gemini-3-8-flash`, access method `antigravity_cli`;
- GitHub Copilot placeholder: `github-copilot-cli-default`, access method
  `copilot_cli`;
- Kiro placeholder: `kiro-cli-default`, access method `kiro_cli`.

Codex execution is wired first. The CLI discovers the Codex command from
`CODEX_COMMAND`, then PATH, then the PyCharm bundled Codex binary. Example:

```powershell
.\scripts\repo-assistant.ps1 `
  "Review this repository and identify the smallest safe next change." `
  --privacy external_allowed `
  --route-id openai-codex-gpt-5-5 `
  --provider openai --model gpt-5.5 `
  --execute --skip-prompt-review
```

Codex is invoked as `codex exec --json` with repository cwd, stdin prompt,
workspace sandbox, and ephemeral session state by default. The CLI parses the
JSONL event stream enough to report the final answer, command/tool/file-change
event counts, web-search event counts, failure status, and usage payloads when
Codex emits them. Raw JSONL is preserved in transcript logs under
`=== External agent raw JSONL ===` for debugging and evaluation without dumping
the full event stream to the terminal.

Use `--codex-persist-session` when intentionally starting a resumable Codex
session. This omits `--ephemeral`, allowing Codex to write its normal session
state outside the repository. Resume with `--codex-resume last` or
`--codex-resume <session-id-or-name>`, which invokes `codex exec resume --json`.
Use `--codex-output-last-message path\to\last-message.txt` when you also want
Codex's `--output-last-message` artifact. The CLI creates the parent directory,
passes the path to Codex, and uses the file as a final-answer fallback when the
JSONL stream does not contain a final-answer event.
Use `--codex-output-schema path\to\schema.json` to pass Codex an explicit JSON
Schema via `--output-schema` for structured final responses.
Use `--codex-search` to enable Codex web search for one run. This is deliberately
off by default because it allows external web/search activity in addition to
sending the selected repository context to Codex. The verified local Codex CLI
expects search as a top-level flag, so the repository CLI invokes
`codex --search exec ...` rather than the unsupported `codex exec --search ...`.

`--mode diagnose` and `--local-capabilities` include Codex diagnostics when a
Codex command is discoverable: command path, version, login-status text,
`exec --json` support, MCP list output, plugin list output, and the relevant
config path. The report does not read or print auth files, config contents, or
tokens.

The PyCharm-bundled Codex CLI verified in this repository is `codex-cli
0.137.0`. On 2026-09-26, `gpt-5.5` completed a low-risk JSONL execution through
ChatGPT sign-in, while `gpt-5.1` returned an upstream invalid-request error for
this account. Keep both facts in mind when selecting routes.

This is not full parity with the Codex IDE/ChatGPT environment: app/plugin
tools, document-control tools, IDE-private state, and this chat's managed
approval surface are not automatically available through `codex exec`.
Antigravity, Copilot, and Kiro are represented for route planning and
diagnostics, but their execution adapters remain disabled until their official
noninteractive command contracts and local executable paths are confirmed.

### Codex Capability Matrix

| Capability | This ChatGPT/Codex session | Repository CLI via Codex CLI | Current status |
| --- | --- | --- | --- |
| Repository instructions | Root `AGENTS.md` and runtime instructions are loaded by this session. | The repo assistant includes bounded `AGENTS.md`/`CURRENT_CONTEXT.md` context in the stdin prompt; Codex CLI also has its own `AGENTS.md`/config behavior. | Implemented, with bounded prompt context. |
| Shell/file coding work | Managed tools can inspect and edit the shared workspace. | `codex exec --json --sandbox workspace-write --ephemeral -` runs inside the repo root. | Implemented for Codex route. |
| Machine-readable execution events | Tool calls are available to this runtime. | JSONL stdout is parsed for final answer, command/tool/file-change events, failures, and usage. | Implemented with tolerant parsing. |
| Raw transcripts/event logs | Conversation and tool output exist in the managed session. | CLI transcript logs preserve invocation metadata, full prompts when requested, run metrics, and raw Codex JSONL. | Implemented as local files under `logs\`. |
| Final-answer artifact | The managed session displays the final answer in chat. | `--codex-output-last-message` writes Codex's last assistant message to an explicit local file and uses it as a JSONL fallback. | Implemented as opt-in local file output. |
| Structured final response | This runtime can constrain some outputs through tool/runtime mechanisms. | `--codex-output-schema` passes an explicit JSON Schema file to `codex exec`. | Implemented as opt-in schema file input. |
| Approval/sandbox policy | Managed by the active ChatGPT/Codex runtime. | Uses Codex CLI sandbox flags. This installed `codex exec` supports `--json`, `--sandbox`, and `--ephemeral`; `--ask-for-approval` must not be assumed unless local help confirms it. | Partially implemented; human approval parity is a known gap. |
| MCP tools | Available here through the current managed runtime. | Diagnostics list configured Codex MCP servers. Actually reproducing tools requires Codex MCP config/design. | Feasible, decision required before adding MCP/tool design. |
| Plugins/apps | This session has installed app/plugin tools exposed by ChatGPT. | Diagnostics list Codex plugin marketplace/install status. Installing or authorizing plugins is outside this CLI slice. | Feasible through Codex plugins, separate auth/product decision required. |
| Document/app-control tools | Available here when connected document sessions expose tools. | Not inherited automatically by `codex exec`. Would require MCP/plugin equivalents and authorization. | Gap; decision required before design. |
| Web/search | This runtime may have managed browsing tools. | `--codex-search` invokes `codex --search exec ...` for one explicit Codex CLI run. Default runs omit search. | Implemented as explicit opt-in only. |
| Images/multimodal input | This runtime can receive images when tools/context allow it. | Codex CLI help exposes image attachment flags, but the repo assistant route currently sends text prompts only. | Feasible later through CLI-layer input design. |
| Multi-turn resume | This chat preserves conversation state. | Default runs remain ephemeral. `--codex-persist-session` starts a resumable session, and `--codex-resume last|<session-id>` resumes one through Codex CLI. | Implemented as explicit opt-in Codex persistence. |

## CLI-First Roadmap

The current CLI is the execution foundation for the project. The next steps
are intentionally CLI-first:

1. stabilize the existing one-shot request, review, tool, delegation, and
   diagnostics behavior;
2. expose explicit `plan`, `ask`, `review`, `implement`, and `diagnose` modes;
3. add CLI-level integration tests for routing, delegation, permissions, and
   verified final status;
4. move the implementation behind a stable `ai-assistant` package command while
   retaining this PowerShell launcher;
5. build interactive chat as a thin multi-turn interface over that stable
   execution service.

Chat is deliberately deferred until the CLI has a predictable execution and
approval contract. Persistent memory, background jobs, web/search integrations,
and autonomous external actions are also out of scope for the current CLI
milestone.

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
  --cost-policy billing_allowed --execute --apply-actions
```

Notes:

- `--privacy external_allowed` is required for hosted providers.
- `--cost-policy billing_allowed` is required for OpenAI direct API routes in
  the sample catalog because they can incur metered API billing.
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
