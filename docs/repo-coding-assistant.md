# Repo Coding Assistant CLI

This is a practical guide for using the local repo-aware coding assistant CLI
when the PyCharm AI Assistant / Codex quota is unavailable.

The main startup command is:

```powershell
.\scripts\repo-assistant.ps1 "YOUR REQUEST" --provider ollama --model qwen2.5-coder:14b --execute --start-ollama
```

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

Use the Codex route when you want behavior closest to this chat's coding model:

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
context, this chat's managed app/document-control tools, or a material product
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

`ask` is the default for backward compatibility. `plan` never contacts a
provider. `ask` and `review` reject action flags. `implement` requires
`--execute` plus either `--native-tools` or `--apply-actions`.

Use `--away-minutes N` when starting a foreground run that should keep working
while you are away. The flag prints `away_budget_*` fields in the transcript,
adds explicit unattended-run guidance to the model prompt, and, unless
`--timeout-seconds` is supplied, sets provider and external-agent timeouts to
`N * 60` seconds. Add `--orchestrated` to plan or run the staged unattended
workflow rather than only extending the timeout and prompt guidance. Orchestrated
runs create a local SQLite run record and planned stage rows in
`data/repo-assistant-runs.sqlite3` by default; use `--away-run-db PATH` to
override the local database path.

In `--mode plan`, `--away-minutes N --orchestrated` prints the intended
foreground stages, the primary route, the local/cheap auxiliary route policy,
and the approval boundary without contacting a provider. The stages are prompt
review, planning, auxiliary panel, implementation, validation, scrutiny,
bounded repair, and final handoff. This is not a background scheduler, daemon,
or job queue, but the SQLite records give later foreground stages and a future
resume/background runner a stable run ID and stage-tracking surface. External
Codex-style routes still report their timeout as an inactivity timeout because
model output resets the timer. For unattended implementation runs, choose the
approval boundary deliberately: `interactive` may pause for a prompt, while
`trusted_local` permits local read/write/shell actions under the repo
assistant's existing tool policies.

Executed orchestrated runs now update deterministic validation and final
handoff stages before the run is marked complete. The validation stage runs
`python -m pytest -q` by default, records command output previews and return
codes, and can be changed with repeated `--validation-command CMD` flags or
disabled with `--skip-validation`. Ruff and Pyright remain available through the
repository's pre-commit hooks; pass a pre-commit command explicitly when an
orchestrated run should include that broader gate. The final handoff stage
records the execution status, validation status, concise `git status --short`
output, response availability, blockers, risks, and next action fields in the
local SQLite stage details. Failed deterministic validation changes the final
run record to `completed_with_validation_errors` instead of clean completion.

The staged workflow exposes a default repair policy of three repair cycles. Use
`--max-repair-cycles N` to choose a different limit,
`--max-repair-cycles 0` to disable repair attempts, or
`--max-repair-cycles -1` to remove the cycle cap while still respecting the
`--away-minutes` wall-clock budget. When unresolved failures remain at the end
of the run, the final handoff is responsible for preserving the validation
details, blockers, and next action for the returning user.

Every run prints an `execution_status` line. It distinguishes planned runs,
completed responses, completed runs with tool/action errors, and failed
orchestration. A response is not reported as a fully successful implementation
when an approved tool or action returned an error.

`--scrutinize-response` is an opt-in second provider call for `ask` or `review`.
It evaluates the completed answer against the original request and repository
context, then prints a structured verdict, score, issues, recommended next
action, and revised response. It uses a derived local-only child task profile by
default, so scrutiny does not silently reuse an expensive or allowance-backed
primary route. It does not edit files or execute actions. The
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

The same policy applies to future auxiliary calls: context extraction,
summarization, prompt refinement, test-case generation, and response critique
should prefer local or cheaper models unless the task is important enough to
justify an explicit stronger route. Primary model routing remains governed by
the task profile, privacy class, quality threshold, selected route, and
cost-policy tier.

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
creating a separate one-off command. Keep this runbook synchronized with that
script; `CURRENT_CONTEXT.md` may point here as a short handoff, but it is not
the durable source of the command.

Executed implementation-mode provider routes use the provider-native
tool-calling loop by default:

```powershell
.\scripts\repo-assistant.ps1 "YOUR REQUEST" --mode implement --provider ollama --model qwen2.5-coder:14b --execute --start-ollama
```

Native mode uses the shared `ai_provider` tool-call contract and
`ai_agent.AgentLoop`. `--native-tools` is still accepted for explicitness and
compatibility. Use `--no-native-tools` to opt into the older text-only provider
response path. Use
`--approval-policy read_only|interactive|workspace_write|trusted_local` to
choose the model-neutral local action policy. The default is `interactive`.

- `read_only`: allow read/search tools, deny local writes and shell commands.
- `interactive`: allow read/search tools, ask before local writes and shell
  commands.
- `workspace_write`: allow workspace file writes, but deny legacy shell actions
  and continue asking before provider-native shell/custom tools.
- `trusted_local`: allow local read/write/shell tool actions without asking.

When provider-native tools are active, the transcript prints secret-free policy
diagnostics before the assistant response. The diagnostic block includes the
active approval preset, the read/search/write/shell/custom action mapping,
whether interactive approval can be requested, and whether `delegate_task` is
available to the primary agent.

The primary native agent also receives `delegate_task`, a bounded delegation
tool for handing focused support work to a derived local/cheaper child route.
The child agent can inspect files, run the standard coding tools, and write
small code changes when the active approval policy permits writes. Nested
delegation is disabled so runs remain bounded and reviewable. Delegated task
results are returned to the primary agent as a bounded handoff containing child
status, iteration count, tool-result counts, a short tool-result summary, and
the child final response.

For Codex CLI routes, the current local CLI exposes sandbox modes and a
top-level approval flag rather than the full managed ChatGPT approval surface:
`read_only` maps to Codex `--sandbox read-only`, `interactive` and
`workspace_write` map to `--sandbox workspace-write`, and `trusted_local` maps
to Codex `--sandbox danger-full-access`. `interactive` forwards
`--ask-for-approval on-request`; the noninteractive presets forward
`--ask-for-approval never`. Git metadata writes such as `git add` and
`git commit` require `trusted_local`; use `--approval-policy trusted_local`
when the requested external Codex run should stage or commit changes. The CLI
rejects explicit commit-like Codex requests under weaker presets before
contacting the model. `--apply-actions` remains available as the legacy
fenced-JSON action protocol and now uses the same approval policy presets.

That wrapper loads `.env` for the run and starts the Python CLI.

The CLI prints phase headers so metadata and the model response are easy to
scan. To preserve a complete local transcript for later analysis, opt in with
`--log-file`; transcript files may contain the request and repository context,
so keep them local:

External-agent JSONL stdout is summarized in an `=== External agent diagnostics
===` block while the raw JSONL is kept in the transcript only. The final
assistant answer is printed after diagnostics, run status, and metrics so user
summaries do not have raw failures or activity previews appended below them. If
the external agent writes stderr, the console shows a concise stderr summary and
an `external_agent_stderr_file` path for the full filtered stderr. Non-zero
external-agent exits also print an explicit `external_agent_failure_reason`, so
stderr is supporting diagnostic detail rather than the only failure explanation.

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

### Local Chat Transcripts

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
stronger. It also includes the repo-assistant system prompt in the external
agent stdin prompt so external routes receive the same high-level repo-aware
contract as provider-native routes. If a timeout or process error occurs after
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
Use `--codex-mcp-tools` to inject this repository's project-local MCP server
into one Codex route via Codex `-c` config overrides. This exposes
`read_file`, `list_dir`, `find_files`, `grep_search`, and the local-only
`delegate_task` bridge for that run without requiring global MCP registration.
Use repeated `--codex-image path\to\screenshot.png` flags to attach local image
files to the initial Codex prompt. This is useful for screenshots, diagrams, or
visual regressions; the prompt should still state what Codex should inspect and
what output you want.

`--mode diagnose` and `--local-capabilities` include Codex diagnostics when a
Codex command is discoverable: command path, version, login-status text,
`exec --json` support, MCP list output, plugin list output, a structured plugin
summary, and the relevant config path. The report does not read or print auth
files, config contents, or tokens.

The same diagnostics also include an `authorization` registry summary. For the
Codex CLI bridge, this maps local command discovery, login status, plugin
summary, and MCP status into the shared `ai_agent.authorization` contracts.
Read scopes cover secret-free local diagnostics. Write scopes are modeled for
Codex workspace execution, resumable session state, plugin install/remove, and
MCP registration, but those actions still require their existing explicit CLI
flags and approval-policy gates.

Use `--codex-plugin-install PLUGIN@MARKETPLACE --execute` to explicitly install
one or more Codex plugins through `codex plugin add`. The flag may be repeated:

```powershell
python -m uv run ai-assistant `
  --codex-plugin-install openai-developers@openai-curated `
  --codex-plugin-install codex-security@openai-curated `
  --execute
```

Use `--codex-plugin-remove PLUGIN@MARKETPLACE --execute` to explicitly remove
installed plugins through `codex plugin remove`. Plugin management cannot be
combined with a prompt request. The CLI reports before/after `codex plugin list`
output, prints the exact command for every operation, and emits
`codex_plugin_expected_status_json` for the requested selectors. Install runs
fail when a requested plugin is not installed in the parsed after-list; removal
runs fail when a requested plugin still appears installed.

The plugin command only installs or removes local Codex plugin bundles. It does
not authorize external services, complete OAuth, approve app permissions, enable
write actions in connected services, or import/sync marketplaces. Review any
plugin apps, MCP servers, and hooks separately, then start a new Codex CLI
session before relying on newly installed skills or tools.

For plugin parity checks, treat parsed `codex plugin list` / `codex mcp list`
output as the source of truth. A live Codex model response may self-report
plugin visibility, but that is weaker evidence and can be misleading when the
prompt asks about the runtime's own tools or skills.

Initial approved Codex plugin set for this repository:

- `openai-developers@openai-curated`
- `codex-security@openai-curated`
- `superpowers@openai-curated`
- `plugin-eval@openai-curated`
- `build-web-apps@openai-curated`

See `docs/codex-plugin-review.md` for the point-in-time review of deferred
plugins and why they were not installed in the first batch.

Use `--codex-mcp-setup` to expose this repository's selected local inspection
and delegation tools to Codex through MCP:

```powershell
python -m uv run ai-assistant --codex-mcp-setup
```

The setup command writes local `.codex\config.toml` for project-scoped Codex
config. The file contains this checkout's absolute workspace path and is ignored
by Git; rerun the setup command for each local checkout. It does not change
user-level Codex MCP configuration by default. For single repo-assistant runs,
prefer `--codex-mcp-tools`; it passes the same project-local server definition
to Codex via per-run `-c` overrides.

To also register the server persistently with the official Codex MCP CLI, pass
the explicit global-registration flag:

```powershell
python -m uv run ai-assistant --codex-mcp-setup --codex-mcp-register-global
```

That command runs `codex mcp add repo_assistant_tools -- ...`, so
`codex mcp list` can see the server outside this project-scoped config. Use it
only when you intentionally want to update the broader Codex environment.

The exposed MCP server is intentionally limited to read/search tools plus
bounded local delegation: `read_file`, `list_dir`, `find_files`, `grep_search`,
and `delegate_task`. It does not expose write or shell tools. Tool calls are
bounded to the configured workspace root. `delegate_task` routes to a local-only
child agent with the same read/search tool surface, nested delegation disabled,
and no MCP write or shell capability.

The PyCharm-bundled Codex CLI verified in this repository is `codex-cli
0.137.0`. On 2026-09-26, `gpt-5.5` completed a low-risk JSONL execution through
ChatGPT sign-in, while `gpt-5.1` returned an upstream invalid-request error for
this account. Keep both facts in mind when selecting routes.

If a Codex CLI run fails with `401 Unauthorized` or `Missing bearer or basic
authentication`, the repo assistant reached the Codex executable but Codex's
local session was rejected by OpenAI. This is different from missing
`OPENAI_API_KEY`: Codex CLI routes normally use the Codex/ChatGPT login, not
the repository `.env` API key. Run Codex login diagnostics, refresh the local
Codex login through the CLI or PyCharm/Codex, or set `CODEX_COMMAND` to a
separately authenticated Codex CLI. Until that is fixed, use local Ollama or a
direct hosted provider route with the relevant API key.

To refresh Codex authentication through the repository CLI, run:

```powershell
.\scripts\repo-assistant.ps1 --codex-login
```

For device-code authentication, run:

```powershell
.\scripts\repo-assistant.ps1 --codex-login-device
```

These commands call the official Codex CLI login flow and may open a browser or
print a device-code link. They mutate local Codex auth state, cannot be
combined with a prompt, and do not read or print token values. The PowerShell
wrapper does not create a transcript log for these auth-refresh commands.

This is not full parity with the Codex IDE/ChatGPT environment: app/plugin
tools, document-control tools, IDE-private state, and this chat's managed
approval surface are not automatically available through `codex exec`.
Antigravity, Copilot, and Kiro are represented for route planning and
diagnostics, but their execution adapters remain disabled until their official
noninteractive command contracts and local executable paths are confirmed.

The accepted parity direction is recorded in
`docs/decisions/ADR-024-codex-cli-parity-authorization-and-dev-tool-policy.md`.
Codex remains the baseline capability target, but approval policy, tool
authorization, and development tool contracts should stay model-neutral so
alternate executors can use the same policy.

### Codex Capability Matrix

| Capability | This ChatGPT/Codex session | Repository CLI via Codex CLI | Current status |
| --- | --- | --- | --- |
| Repository instructions | Root `AGENTS.md` and runtime instructions are loaded by this session. | The repo assistant includes bounded `AGENTS.md`/`CURRENT_CONTEXT.md` context in the stdin prompt; Codex CLI also has its own `AGENTS.md`/config behavior. | Implemented, with bounded prompt context. |
| Shell/file coding work | Managed tools can inspect and edit the shared workspace. | `codex --ask-for-approval never exec --json --sandbox workspace-write --ephemeral -` runs inside the repo root for noninteractive workspace-write runs. | Implemented for Codex route. |
| Machine-readable execution events | Tool calls are available to this runtime. | JSONL stdout is parsed for final answer, command/tool/file-change events, failures, and usage. | Implemented with tolerant parsing. |
| Raw transcripts/event logs | Conversation and tool output exist in the managed session. | CLI transcript logs preserve invocation metadata, full prompts when requested, run metrics, and raw Codex JSONL. | Implemented as local files under `logs\`. |
| Final-answer artifact | The managed session displays the final answer in chat. | `--codex-output-last-message` writes Codex's last assistant message to an explicit local file and uses it as a JSONL fallback. | Implemented as opt-in local file output. |
| Structured final response | This runtime can constrain some outputs through tool/runtime mechanisms. | `--codex-output-schema` passes an explicit JSON Schema file to `codex exec`. | Implemented as opt-in schema file input. |
| Approval/sandbox policy | Managed by the active ChatGPT/Codex runtime. | `--approval-policy` selects model-neutral presets for native tools and legacy actions. Codex routes map `read_only` to `--sandbox read-only`, `interactive`/`workspace_write` to `--sandbox workspace-write`, and `trusted_local` to `--sandbox danger-full-access` for commit-capable local runs. Codex approval is forwarded as top-level `--ask-for-approval`. | Implemented first preset slice; Codex CLI still lacks exact managed approval UI parity. |
| MCP tools | Available here through the current managed runtime. | `--codex-mcp-tools` injects the local `repo_assistant_tools` MCP server for one Codex run; `--codex-mcp-setup` can also write project config. The server exposes read/search repository tools plus bounded local `delegate_task`. | Implemented for selected local read/search tools and local-only delegation. |
| Plugins/apps | This session has installed app/plugin tools exposed by ChatGPT. | Diagnostics list Codex plugin marketplace/install status and structured plugin counts. Explicit install/remove is available through repeated `--codex-plugin-install` / `--codex-plugin-remove` with `--execute`. | Initial approved plugin install set implemented; future connectors one at a time behind reusable authorization. |
| Document/app-control tools | Available here when connected document sessions expose tools. | Not inherited automatically by `codex exec`. Development-relevant bridges may be added as needed, with read/write capability designed together and writes gated by policy. | Accepted direction in ADR-024; implementation deferred until a concrete development workflow needs it. |
| Web/search | This runtime may have managed browsing tools. | `--codex-search` invokes `codex --search exec ...` for one explicit Codex CLI run. Default runs omit search. | Implemented as explicit opt-in only. |
| Images/multimodal input | This runtime can receive images when tools/context allow it. | Repeated `--codex-image PATH` flags forward local images to `codex exec --image PATH`. | Implemented as explicit opt-in image attachments for Codex CLI routes. |
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

The next parity-specific roadmap is:

1. define model-neutral approval policy presets;
2. introduce a reusable authorization boundary for Codex/GitHub/app connectors;
3. add development-relevant tool bridges only as concrete workflows require
   them;
4. design read and write capability contracts together, even when writes remain
   disabled by default;
5. approve external connectors one at a time.

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
