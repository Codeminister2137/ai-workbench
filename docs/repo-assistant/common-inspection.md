# Common inspection and selected skills

`--shared-tools inspection` selects the same six project-owned Git/read/search
operations for provider-native execution, Codex, Copilot and Kiro. Antigravity is
excluded until scoped MCP access is verified. This profile cannot edit or run
commands; it sets the read-only approval preset. Existing coding defaults and
the older Codex-only delegation option remain separate.

```powershell
.\scripts\repo-assistant.ps1 "Review the change" --mode review --shared-tools inspection --execute
.\scripts\repo-assistant.ps1 "Review the change" --mode review --skill review-repo-change --execute
```

Select privacy, cost and route settings appropriate to the task; the examples use
the existing local-only defaults. Selecting a supported skill implies inspection
unless a common profile was explicitly selected. Sources are project `.agents/skills`
and `packages/ai_agent/skills`, or repeat `--skill-dir PATH` to use explicit sources.
Exactly one source must match each name. Current prerequisite contracts support
`review-repo-change`; unknown skills are refused rather than claiming dependencies
were checked. Skill selection passes complete instructions to every route. It is
not evidence that a client's separate native skill menu was invoked.

Required root and selected-path nested `AGENTS.md` instructions are loaded intact,
before optional snippets. Their independent limit defaults to 64,000 characters;
`--instruction-budget-chars` changes it. Optional context retains its own total and
per-file limits. An instruction overflow or unreadable instructions refuses before
route preparation. Character limits alone do not establish model token capacity.
Native repairs and delegated requests retain the loaded instructions.

Common MCP configuration is passed per run. Kiro needs a generated project-local
agent file; the adapter uses a unique name and removes its unchanged file afterward,
including on failure. Existing configuration and changed generated files are
preserved. No user-wide grants or skill installations are performed. The native
client may also expose its own tools under its restrictions; required common
tools are the shared contract, not a promise of identical complete client menus.

2026-10-04 acceptance: synthetic Codex quota failure continued through real Copilot,
preserving inspection and selected instructions and finding the planted regression.
Fixture content stayed unchanged; Copilot reported one premium request. Real Kiro
used the production mapping to read a marker and removed its generated configuration.
These checks do not establish shared mutation permissions or complete coding parity.

## Shared coding and terminal approvals

`--shared-tools coding` adds the existing `create_file`, `edit_file` and
`run_command` tools to inspection. It preserves the selected approval preset:

| Preset | File writes | Shell |
| --- | --- | --- |
| `read_only` | Deny | Deny |
| `interactive` | Ask per operation | Ask per operation |
| `workspace_write` | Allow within existing file boundary | Ask per operation |
| `trusted_local` | Allow | Allow |

```powershell
.\scripts\repo-assistant.ps1 "Edit the fixture and review its diff" --mode implement --shared-tools coding --approval-policy interactive --coding-session new --execute
```

This example can perform inference and mutations; it is not an offline check.
Select privacy/cost/route settings appropriate to the task. Hosted clients still
receive the selected repository context under the existing privacy policy.

For official clients, the shared server enforces permissions. The adapter enables
human prompts only when the launching CLI has terminal input. The server uses
the controlling terminal (`CONIN$/CONOUT$` on Windows, `/dev/tty` on POSIX), never
MCP stdin/stdout. It displays task/run identity, workspace and the complete exact
operation, with control characters escaped. Only `yes` approves once. Operations
too large to preview intact are refused. With no usable terminal, requests that
need a human are denied; automatic preset grants retain their existing meaning.

Each external invocation has a fresh run ID. PID and process birth identity bind
the server to its foreground owner and are checked before and after human approval.
Owner exit or unverifiable identity refuses further operations. No approval cache
or restart inheritance exists. Native client restrictions remain an additional
boundary; Codex uses a read-only native sandbox, and alternate mappings expose
only named shared tools without global bypass flags. Antigravity stays excluded.

Tool results include observed scope, authorization/error status, timestamp and
argument/output digests. With `--coding-session`, the server writes start/finish
receipts into the existing session database, including task/run/operation identity
and argument digest. It stores neither raw arguments nor outputs. Missing or
mismatched sessions refuse startup. Interrupted receipts require reconciliation;
they never authorize replay. Without a coding session, receipts are returned in
tool results and durable session recovery is not provided.

The file tools retain their existing workspace boundary. Shell cwd containment
does not sandbox a command's effects. A shell grant remains broader than a file
grant. Client discovery, terminal propagation, mutations and fallback need bounded
live acceptance; offline contract tests do not establish cross-agent coding parity.
