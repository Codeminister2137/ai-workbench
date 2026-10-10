# Continuous coding chat

The `coding-chat` mode keeps a development conversation open across requests,
using the existing coding tools, permissions and execution routes. Its initial
implementation is verified offline and with synthetic clients. An installed
Codex pilot passed three matched full/reduced-history fixture pairs, with scoped
edits and unchanged host tests; see [acceptance evidence](coding-chat-acceptance-results.md).
Comparable model quality and delegation savings have not yet been established.

## Start and continue

For an already available, compatible local model:

```powershell
.\scripts\repo-assistant.ps1 --mode coding-chat --execute `
  --provider ollama --model gpt-oss:20b `
  --approval-policy interactive --skip-prompt-review
```

The optional positional prompt executes the first turn immediately; otherwise
the terminal displays `You>`. Enter subsequent questions, clarifications, plans
or implementation requests at that prompt. Available coding tools do not grant
permission for unrequested changes. Interactive approvals identify the operation
and are requested separately from conversation input.

Official-client prompts distinguish the native client sandbox from the shared
tool host's policy. A read-only native sandbox can coexist with a coding profile
whose shared operations have separate workspace and approval enforcement. The
profile does not grant permission for an edit; task restrictions, required
approvals and actual tool denials still apply on every call.

`/multiline` collects a request until a line containing only `.`. `/status`
prints the coding-session ID; `/help` lists commands. `/exit` or EOF closes the
conversation and its owned processes. During a running turn, terminal text (or
`/steer TEXT`) queues a follow-up and is recorded immediately in the local
transcript. It applies after the active turn; it does not preempt a model call,
command or edit already running. Use Ctrl+C when interruption is required.
Multiple queued owner messages become one follow-up: the latest is the current
request, with earlier messages retained in history. This prevents execution of
an older queued request that a newer correction has already changed.
In-flight `/exit` or EOF finishes the active turn, denies pending approvals and
suppresses queued execution. Queued messages remain recovery evidence.
Ctrl+C ends the foreground session,
records interruption and requires effect reconciliation before resume. It does
not automatically continue or replay the interrupted request.

An in-flight approval displays the complete operation and a fresh prompt ID.
Reply `/approve PROMPT_ID yes` or `/approve PROMPT_ID no`. Ordinary `yes`,
queued chat text and expired IDs cannot approve it. The terminal reader is
separate from provider/MCP streams, and shared-tool approvals still require a
controlling reader and active invocation scope. Noninteractive native input
retains its existing sequential approval interface. `/multiline` is available
at the idle `You>` prompt. Partial Windows input is retained when a turn ends.
Typing bare `yes` or `no` while a ticket is pending displays the complete command
to use; the bare text remains queued chat and does not grant permission.

The session ID printed at startup links conversation turns and coding receipts
in `data/repo-assistant-chats.sqlite3`. Choose another existing-storage location
with `--coding-session-db PATH`. Resume with the same privacy/cost boundaries:

```powershell
.\scripts\repo-assistant.ps1 --mode coding-chat --execute `
  --coding-session SESSION_ID `
  --provider ollama --model gpt-oss:20b `
  --approval-policy interactive --skip-prompt-review
```

After interruption, inspect changed files and process observations first. Add
`--coding-session-reconciled` only after verifying effects and that no other CLI
owns the session. Saved receipts are evidence, not permission to replay effects.
Saved process handles cannot attach to arbitrary processes after restart.
External-client timeout reasons omit the process command and arguments, keeping
prompt-bearing arguments out of default failure logs and mandatory history.
Timeouts remain failures; inspect partial effects before continuing. Structured
partial event summaries and explicitly requested raw diagnostic files remain
available under their existing logging rules.

## Tools, routes and evidence

The mode requires the common coding tool profile; existing `--skill` and `--file`
options apply. Selected files, complete applicable repository instructions and
skills are loaded again on every turn. Questions can use tools for inspection,
while edits/commands remain subject to the selected permission policy.

Existing official-client routes can also execute turns, subject to account
readiness, route compatibility and explicit external-processing permission.
Select an eligible `--route-id`, appropriate `--privacy`/`--cost-policy` and
any required client configuration. Do not treat this as installed-client
acceptance evidence or a recommendation to transmit private repository data.
Required tools must remain available during eligible fallback. Codex's native
`--codex-resume`/`--codex-persist-session` are excluded here: the project-owned
conversation and coding-session handoff are authoritative.

`--validation-python` controls the existing default validation interpreter.
For host-run validation/repair/scrutiny use the existing `--orchestrated` and
`--away-minutes` options; the supplied budget applies to each turn. Regular turns
can invoke permitted validation tools, but the CLI does not claim host validation
ran unless its deterministic stage recorded results.

Conversation history retains user requests, final agent reports and the
host-observed execution outcome, including failed validation or tool errors.
It does not persist raw tool arguments/output as additional conversation turns.
Private user text and final responses are stored locally, so protect that file.
When a transcript log is enabled, each turn gets a distinct file beside the
requested log path. Interruption closes that file and restores terminal output.

## Current limits

- In-flight steering queues the next turn; immediate injection into an active
  model/client and preemptive cancellation by chat text are not implemented.
  Restart shows saved queued messages as unexecuted evidence, without replay.
- `--coding-chat-history-budget-chars` (default 64,000) covers rendered history
  plus the current request. If needed, deterministic local reduction visibly
  shortens assistant reports oldest first. Every owner message, host outcome,
  return code, failure reason and host interruption notice remains intact.
  Excerpts are not summaries; older agreed plans may require retrieval.
  `/history` lists message IDs; `/history MESSAGE_ID` displays the full original
  locally without execution. These commands require the idle prompt. Full
  transcripts remain in SQLite; reduction is rebuilt identically after restart.
  If mandatory context still cannot fit, execution refuses without deleting
  history. Resume with an appropriate explicit budget if capacity permits;
  `0` disables reduction and this character limit, not provider input limits.
- The current runtime configuration is frozen for the foreground conversation.
  Configuration-file changes do not silently alter privacy or permissions.
  Restart explicitly to change the route/configuration; stored privacy/cost
  boundaries still apply.
- Existing `--mode chat` remains provider-only and action-free. Coding
  conversations resume through `--coding-session`, not `--chat-session`.
- Full C1-C6 installed-client coverage, long-conversation quality comparisons
  and measured delegation economics remain migration acceptance work.
