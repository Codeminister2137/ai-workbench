# External agents, preferences and usage fallback

[CLI guide](../repo-coding-assistant.md) Â· [Privacy and permissions](permissions.md)

## Private preferences and alternate agents

Copy `user-config.example.toml` to ignored `user-config.toml` in the repo root,
or use `--user-config <path>`. Explicit CLI flags override user preferences,
which override shipped defaults. Explicitly named missing or invalid config
files fail before routing. The shipped cost ceiling is `prepaid_credits_allowed`;
an allowance-only private preference uses `allowances_allowed`:

```toml
[defaults]
cost_policy = "allowances_allowed"
```

Enum members use uppercase names such as `CostPolicyTier.ALLOWANCES_ALLOWED`;
serialized values and variables use lowercase snake_case for both cost tiers.
The same `[defaults]` section accepts `quality`, `context_budget_chars`,
`context_file_budget_chars`, `instruction_budget_chars`, `timeout_seconds`,
`validation_timeout_seconds`, and `max_repair_cycles`. See the checked-in example
for shipped values and bounds. Explicit CLI flags win, including abbreviated
options and values equal to shipped defaults. Required instructions refuse
overflow; they are never truncated. An explicitly configured request timeout
also wins over the automatic `--away-minutes` request timeout. If the key is
absent, away runs retain their existing automatic timeout. Scheduler deadlines
and admission checks remain independent limits. Privacy and approval defaults
retain their existing behavior.

Requesty remains a provider API route using `REQUESTY_API_KEY`. Paid catalog
routes require `prepaid_credits_allowed`. The separate
`requesty-free-gemma-4-31b` route uses `free_only` and verifies live zero pricing
before every inference request, including tool-loop turns and model overrides.
Missing or changed prices block inference; there is no paid fallback. Requesty
currently advertises 200 free requests per day for free models. This pricing
preflight is not an atomic service-side billing guarantee.

Run opt-in synthetic coding acceptance with
`uv run python scripts/alternate-agent-acceptance.py`. Select only the free
Requesty route with `--routes requesty-free-gemma-4-31b`. Live completion/tool
tests require `AI_PROVIDER_RUN_REQUESTY_FREE_INTEGRATION=1`; they assert reported
zero cost. Ordinary tests mock the API and do not spend requests. The tested
Gemma route reports no training but 30-day retention; acceptance sends only
synthetic fixtures. An inference key needs no Requesty admin permissions.

Antigravity, Copilot, and Kiro use official clients and native tools/sign-in.
Set `ANTIGRAVITY_COMMAND`, `GITHUB_COPILOT_COMMAND`, or `KIRO_COMMAND` to an
executable path, or install the client on PATH. Windows Kiro discovery also
checks `%LOCALAPPDATA%/Kiro-Cli/kiro-cli.exe`.
Only `--approval-policy trusted_local` is mapped for these three clients:

| Client | Native automatic approval |
| --- | --- |
| Antigravity | `--dangerously-skip-permissions` |
| Copilot | `--allow-all` |
| Kiro | `--trust-all-tools` |

Other approval modes are not mapped yet and fail before execution. These modes
grant broad native tool access without a project workspace sandbox; native
hooks/MCP servers and account permissions apply. Codex-specific image, search,
schema, MCP, output-file, and resume flags are rejected on alternate routes.
Native session retention remains client-owned; alternate ephemeral/resume
controls are not mapped yet.

```powershell
.\scripts\repo-assistant.ps1 --mode ask "Reply CONNECTED; do not call tools." `
  --execute --privacy external_allowed --route-id kiro-cli-default `
  --approval-policy trusted_local --skip-prompt-review
```

Other route IDs: `github-copilot-cli-default`,
`google-antigravity-gemini-3-1-pro`, and `requesty-openai-gpt-5-mini`.
Model slugs/entitlement may change: inspect the client's model list or use
`--model`. Kiro and Copilot default routes use native automatic selection.
Antigravity uses stream JSON input/output; Kiro uses ACP JSONL. Copilot supplies
the prompt through `-p` without shell interpolation. Its prompt appears in
process arguments but is omitted from command previews. Installed Kiro was
verified with existing sign-in; current headless docs describe `KIRO_API_KEY`.
Authentication and credits are separate from command availability. The catalog
ceiling does not enforce service-side overage settings. Live quota discovery
remains outside this implementation. Automatic continuation on reported usage
exhaustion is implemented as described below. See ADR-031 and ADR-032.

Antigravity can return process exit zero while explicitly reporting that headless
tool permissions were auto-denied and no answer was produced. The adapter treats
that diagnostic as a task failure, preserves the actual process status and any
receipts, and lets the CLI report failure. It does not grant additional permissions.

2026-10-06 verification: Antigravity CLI 1.2.16 loaded a workspace-local
`.agents/mcp_config.json` server, but default headless `request-review` denied
`mcp(repo_shared/read_file)` before execution. The CLI diagnostic directs users
to a matching `permissions.allow` rule in `settings.json`; official docs describe
global and project-level permissions, but the CLI does not expose a project
permission command or document a project-local permission file. Creating
`settings.json` at the workspace root or `.agents/settings.json` in isolated
fixtures did not grant the tool. The documented CLI settings file is a
user-level profile, not a project-scoped grant. Separate `--sandbox` probes also
showed headless mode denying a native
`write_to_file` request and a harmless native `run_command`; the write sentinel
remained unchanged and the command produced no marker. Thus `--sandbox` did not
grant either tested action, and a narrowly scoped MCP read grant can be evaluated
without granting native writes or commands. The project-only scope is approved,
but cannot be applied through the installed CLI environment; keep shared-tool
routes excluded until it is configured in Antigravity's project settings and
verified. Never substitute
`--dangerously-skip-permissions`, which auto-approves every tool request.

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

Non-Codex external-agent routes are discovered but not executed yet. Diagnostic
mode checks common command names without reading tokens or config contents:
Antigravity via `ANTIGRAVITY_COMMAND`, `agy`, or `antigravity`; GitHub Copilot
via `GITHUB_COPILOT_COMMAND` or `copilot`; and Kiro via `KIRO_COMMAND`,
`kiro-cli`, or `kiro`. Execution adapters for those routes must map each
client's native permission, session, output, and capability behavior before they
can be enabled safely.

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

For a model-free inspection surface, start the same stdio server with
`--read-search-only`. It exposes `read_file`, `list_dir`, `find_files` and
`grep_search`, plus bounded local `git_status` and `git_diff`, without constructing
the delegation runner:

```powershell
python -m uv run --no-sync python -m ai_agent.mcp_server `
  --workspace-root . --read-search-only
```

An MCP client launches this command and owns its stdio connection; it is not a
background service. This opt-in profile does not change the existing Codex
injection defaults or register another client. Client discovery and permissions
still need independent verification.

The Git tools use fixed arguments, require the repository root inside the selected
workspace, disable external diff/text-conversion helpers and trim output at 30,000
characters with a truncation notice. They do not offer arbitrary Git commands,
commits or remote operations. Native provider coding tools expose the same Git
implementations under the existing READ permission category. The default Codex
MCP/delegation profile keeps its original tool set.

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
tools, document-control tools, IDE-private state, and managed IDE
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

| Capability | Repository CLI via Codex CLI | Current status |
| --- | --- | --- |
| Repository instructions | The repo assistant includes bounded `AGENTS.md`/`CURRENT_CONTEXT.md` context in the stdin prompt; Codex CLI also has its own `AGENTS.md`/config behavior. | Implemented, with bounded prompt context. |
| Shell/file coding work | `codex --ask-for-approval never exec --json --sandbox workspace-write --ephemeral -` runs inside the repo root for noninteractive workspace-write runs. | Implemented for Codex route. |
| Machine-readable execution events | JSONL stdout is parsed for final answer, command/tool/file-change events, failures, and usage. | Implemented with tolerant parsing. |
| Raw transcripts/event logs | CLI transcript logs preserve invocation metadata, full prompts when requested, run metrics, and raw Codex JSONL. | Implemented as local files under `artifacts/<run>/` by default. |
| Final-answer artifact | `--codex-output-last-message` writes Codex's last assistant message to an explicit local file and uses it as a JSONL fallback. | Implemented as opt-in local file output. |
| Structured final response | `--codex-output-schema` passes an explicit JSON Schema file to `codex exec`. | Implemented as opt-in schema file input. |
| Approval/sandbox policy | `--approval-policy` selects model-neutral presets for native tools and legacy actions. Codex routes map `read_only` to `--sandbox read-only`, `interactive`/`workspace_write` to `--sandbox workspace-write`, and `trusted_local` to `--sandbox danger-full-access` for commit-capable local runs. Codex approval is forwarded as top-level `--ask-for-approval`. | Implemented first preset slice; Codex CLI still lacks exact managed approval UI parity. |
| MCP tools | `--codex-mcp-tools` injects the local `repo_assistant_tools` MCP server for one Codex run; `--codex-mcp-setup` can also write project config. The server exposes read/search repository tools plus bounded local `delegate_task`. | Implemented for selected local read/search tools and local-only delegation. |
| Plugins/apps | Diagnostics list Codex plugin marketplace/install status and structured plugin counts. Explicit install/remove is available through repeated `--codex-plugin-install` / `--codex-plugin-remove` with `--execute`. | Initial approved plugin install set implemented; future connectors one at a time behind reusable authorization. |
| Document/app-control tools | Not inherited automatically by `codex exec`. Development-relevant bridges may be added as needed, with read/write capability designed together and writes gated by policy. | Accepted direction in ADR-024; implementation deferred until a concrete development workflow needs it. |
| Web/search | `--codex-search` invokes `codex --search exec ...` for one explicit Codex CLI run. Default runs omit search. | Implemented as explicit opt-in only. |
| Images/multimodal input | Repeated `--codex-image PATH` flags forward local images to `codex exec --image PATH`. | Implemented as explicit opt-in image attachments for Codex CLI routes. |
| Multi-turn resume | Default runs remain ephemeral. `--codex-persist-session` starts a resumable session, and `--codex-resume last|<session-id>` resumes one through Codex CLI. | Implemented as explicit opt-in Codex persistence. |

## Automatic Usage-Limit Continuation

Inspect catalog eligibility and executor-option compatibility without inference,
authentication checks, tool connections or provider probes:

```powershell
uv run --no-sync ai-assistant --fallback-readiness `
  --route-id openai-codex-gpt-5-5 --privacy public_or_low_risk `
  --cost-policy allowances_allowed
```

The JSON report separates policy exclusions (different tiers, shared billing
sources or task constraints) from executor incompatibility. It explains unsupported
approval and option mappings. Authentication and tool connections remain
`not_checked`, allowance remains `unknown`, and no candidate is asserted
`execution_ready`. Even a declared compatible executor still needs live checks.
The report respects private preferences; disabled fallback stays disabled.
Execution, runtime startup and setup/sign-in actions cannot be combined with this
offline flag. The PowerShell launcher may still create its usual transcript
directory; the diagnostic itself does not load repository context or write state.

During normal execution, incompatible fallback routes now retain their specific
option/approval reason. The existing compatibility gate and authentication checks
still decide whether execution is permitted; explanations do not authorize routes.

Coding runs automatically try an authenticated, compatible route on the same
billing tier after an allowance/quota limit or recognized model overload. An explicit Codex route/model
selects the first attempt; fallback may change it. Task privacy, required tools,
minimum quality and latency remain constraints. The default `preserve_quality`
also requires the original declared quality grade. Explicit `task_minimum` permits
a weaker route meeting the task requirements. Unknown original model-grade evidence
refuses continuation. No paid escalation or lower-tier switch occurs automatically.
Usage exhaustion excludes billing buckets; overload excludes only affected routes.

Before the primary run, primary and eligible fallback native clients receive
non-inference authentication checks. An interactive terminal offers sign-in for missing accounts. In a
noninteractive terminal, sign-in instructions are printed and those routes are
excluded. Available fallbacks are reported before execution. An unverified
primary login stops startup before task execution. A stored login or
successful preflight does not guarantee future entitlement or remaining quota.

Continuation preserves existing edits and uses the original objective plus
observed progress counts. The replacement inspects current files and validates
the final artifacts. Raw tool arguments/outputs and private native session state
are not transferred. A replacement remains selected for repair attempts.
Orchestrated implementation records include its route and attempt history.
Other errors retain existing failure handling. If no suitable route or time remains,
the CLI reports `fallback_exhausted`, preserves edits and writes a metadata handoff
under `artifacts/fallback-handoffs/`, then returns failure. The handoff contains the
objective, observations and next action, not private reasoning or full instruction
packets. A weaker model is not called solely to summarize. Save failures are reported
explicitly. Login/readiness is not proof of remaining credits or actual quality.

Only `trusted_local` currently permits cross-client fallback to Copilot,
Antigravity, and Kiro; their other approval mappings remain unavailable.
Required client-specific capabilities/options also restrict eligibility.
Provider-native coding and one-shot coding modes participate; external-client
chat and recovery after process restart remain deferred.

The default can be disabled in private `user-config.toml`:

```toml
[fallback]
enabled = false
quality_policy = "preserve_quality"
```

Use `--fallback-quality-policy task_minimum` for an explicit per-run override.
These preferences apply to both usage-limit and overload continuation. Catalog
quality grades are declared estimates; they do not substitute for representative
model evaluations. See ADR-042 for the updated decision.

Run `uv run python scripts/fallback-acceptance.py` for a synthetic Codex-limit
simulation followed by a real Copilot continuation. This consumes a Copilot
allowance request; it does not deliberately exhaust Codex or use paid APIs.
See ADR-032 for the policy and known continuation limits.

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
