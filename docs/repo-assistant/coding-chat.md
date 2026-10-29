# Continuous coding chat

The `coding-chat` mode keeps a development conversation open across requests,
using the existing coding tools, permissions and execution routes. Its initial
implementation is verified offline and with synthetic clients. An installed
Codex pilot passed three matched full/reduced-history fixture pairs, with scoped
edits and unchanged host tests; see [acceptance evidence](coding-chat-acceptance-results.md).
Comparable model quality and delegation savings have not yet been established.

## Start and continue

For the current Codex catalog route, with an installed signed-in client and
available subscription allowance:

```powershell
.\scripts\repo-assistant.ps1 --mode coding-chat --execute `
  --route-id openai/codex-gpt-6.1-sol --shared-tools coding `
  --privacy public_or_low_risk --cost-policy allowances_allowed `
  --approval-policy interactive --skip-prompt-review
```

This explicitly permits the selected low-risk repository context and subscription
allowance. Confirm the effective route and scope; client availability, allowance
and fallback readiness are separate from catalog eligibility. Tools still require
the selected approvals. See the [current readiness limits](baseline-gap.md).

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

For native Ollama coding, `--experimental-measured-prefix` explicitly enables the
[measured-prefix admission experiment](native-admission.md#approved-experiment).
It retains complete instructions/history and the existing default when omitted.
Select it again on each launch/resume; prefix state is local to each native loop.

Tools stay enabled by default for development and review (owner clarification,
2026-10-12). Reviews may inspect diffs, sources and actual results. Disable tools
only for explicitly selected narrow cases; do not automatically interpret a
review request as tool-free. Existing task scope, permissions and approvals apply.

Each coding-chat turn currently uses the implement runner and its configured
tools. A request such as "review the supplied results; no tools" reaches the
model as an instruction, but does not remove tools or create a deterministic
report-only phase. History is marked as earlier conversation; fresh context,
the session handoff with the original objective, skills and budget guidance
precede the active user turn. The latest request appears at the end, explicitly
distinguishing it from the historical objective. This framing preserves earlier
decisions and observations without treating the initial task as a renewed edit
instruction during review. Instruction-following quality and host semantic review
remain necessary even when tests pass. A new report-only phase is not being
introduced as the remedy for the repeated-read loop.

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
with `--coding-session-db PATH`.

Saved assistant outcomes also retain the host-observed effective route ID and
ordered fallback attempts when available. `/history MESSAGE_ID` displays that
metadata; subsequent turns and restart retain it even if the agent's report omits
route names. A failed or expired outcome remains failed alongside any observed
route attempts. These records identify execution routes, not guaranteed answer
authorship or current account allowance. Private fallback handoff contents are
not copied into this metadata; older messages without route evidence stay unknown.

Resume with the same privacy/cost boundaries:

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

`edit_file` accepts literal file text, including indentation. Its schema now
explicitly says to omit added patch markers, read-output line numbers and
Markdown fences. The host preserves supplied text exactly; this clarification
does not transform malformed edits or establish a model-quality improvement.

The mode requires the common coding tool profile; existing `--skill` and `--file`
options apply. Selected files, complete applicable repository instructions and
skills are loaded again on every turn. Questions can use tools for inspection,
while edits/commands remain subject to the selected permission policy.

`read_file` includes line numbers by default. Set `line_numbers=False` to read
literal text for an exact `edit_file` anchor. Selected text retains indentation
and newline positions, using the reader's existing UTF-8 text decoding and
universal newline handling. A missing or duplicate anchor still refuses the edit;
reread the current range and include enough surrounding text to make it unique.
This option does not establish a model-quality improvement on its own.
An end bound before the resolved start bound is refused with the file's valid
line range; it does not return an empty successful read.
An empty file read without line bounds succeeds with empty output and zero lines
read in either display mode. An explicit line request on an empty file is refused.

Existing official-client routes can also execute turns, subject to account
readiness, route compatibility and explicit external-processing permission.
Select an eligible `--route-id`, appropriate `--privacy`/`--cost-policy` and
any required client configuration. Do not treat this as installed-client
acceptance evidence or a recommendation to transmit private repository data.
Required tools must remain available during eligible fallback. Codex's native
`--codex-resume`/`--codex-persist-session` are excluded here: the project-owned
conversation and coding-session handoff are authoritative.

The shared coding profile exposes `delegate_task` on native and official-client
routes. The CLI binds the original catalog snapshot, parent privacy and actual
supervisor permissions. Children can edit and validate when that grant permits it.
Optional profiles, tool/path lists and exact command lists can narrow authority.
Nested delegation shares the original reply/tool allowance and deadline, reserves
the parent's report and has maximum depth two. Live parent permission and scope
checks apply before subsequent effects. Interactive approval remains real.
Funded children must reuse the exact approved parent client and its admission
guards; unavailable execution never authorizes another billing source. External
CLI provider calls are outside the MCP host's observable descendant reply budget.
Legacy unbound local runners remain read-only. These tool restrictions are not
an OS sandbox. See [ADR-074](../decisions/ADR-074-delegation-inherits-supervisor-authority.md).
Bare shared-tool registries without a configured runner refuse delegation.
`--delegate-context` remains a separate optional preparatory extraction pass.

Offline integration preparation is available through
`scripts/hosted-delegation-acceptance.py --output-dir artifacts/<fresh-name>`.
It uses the actual Meta Responses and Baseten Chat Completions adapters over
owned loopback HTTP fixtures (eight nested cases: four scenarios per protocol),
the existing child executor and actual file/command/process tools. Scripted
parent/child/grandchild replies exercise inherited writes/validation, read-only
and protected-path refusal, and original reply-budget exhaustion with effects
retained. A host-started direct child remains owned across the nested calls and
is then stopped. The reference implementation and all model reports are scripted;
the task is a synthetic digest exercise, not full Operator HTTP-contract or
real-model acceptance. Commands are pinned fixture checks, not general CLI limits.

A ninth case invokes the actual two-turn foreground coding CLI. Scripted Meta
HTTP429 responses trigger Baseten fallback, preserving original instructions,
saved owner/report history and the same running process handle/PID. The second
turn observes and stops that child. This uses fresh deterministic fixtures;
historical C6 trials are not replayed or regraded. The controller permits at most
80 scripted HTTP calls across its declared cases and checks their exact names
and classes, not just a passing test count.

The runner permits no live activation, strips worker credentials, requires a fresh
artifact directory, archives the declared source bytes/hashes and bounds work to
90 seconds plus 5 seconds of cleanup. A zero exit cannot pass skipped/failed
required checks, duplicate/missing/unexpected case identities, changed declared
sources or unverified cleanup. Windows cleanup
was exercised through the existing retained process job. The receipts are offline
preparation evidence, never credit observations or authorization for live trials.
Live C6 protocol switching, real parent/child quality and hosted deployment still
need their separately admitted acceptance runs.

An empty or whitespace-only native final report fails the turn, including after
successful tools. Earlier effects and their receipts remain available for host
inspection; this failure does not automatically replay tools or retry the model.
Tool calls containing no answer text are valid intermediate responses, but do
not replace the final report.

A native final report stopped by the provider's output limit also fails the turn,
even when it contains text. Its partial answer and earlier tool receipts remain
available for inspection. This does not automatically extend the output allowance,
retry the model, switch routes or replay tools.

Fallback models are selected by the Orchestrator. Default `emergency_preserve`
keeps the original/task quality floor for implementation. If no ready comparable
route remains, the host first saves a metadata handoff, then eligible weaker
routes may perform read-only inspection/reporting. They cannot edit, run commands,
delegate or perform cleanup, and the original task remains failed/incomplete.
Explicit `--fallback-quality-policy prefer_quality` tries stronger routes first
and allows weaker implementation when necessary, reporting the downgrade. Both
retain privacy, billing tier, approvals, deadlines and validation. Legacy
`preserve_quality` and `task_minimum` remain available. See ADR-052.
Console output failures do not prevent fallback handoff saving or replace the
original route failure. A handoff save failure still prevents weaker reporting.

`--validation-python` controls the existing default validation interpreter.
For host-run validation/repair/scrutiny use the existing `--orchestrated` and
`--away-minutes` options. The away allowance is fixed for this launch, starting
after configuration loading and before session setup. Idle time and all turns
count; turns, task restarts, delegation, fallback and stages cannot reset it.
Each launch explicitly supplying the option grants fresh time, including saved
session resume. Resume without it does not inherit an earlier allowance.

Use `--turn-timeout-seconds N` for a separate maximum per turn; the effective
deadline is the earlier of that limit and the remaining away allowance.
`--timeout-seconds` still controls individual provider requests and is capped by
the remaining execution time. To migrate an old per-turn away budget, select
`--turn-timeout-seconds` explicitly. For example, `--away-minutes 30
--turn-timeout-seconds 300 --timeout-seconds 60` allows a thirty-minute session,
five minutes per turn and sixty seconds per request. Regular turns
can invoke permitted validation tools, but the CLI does not claim host validation
ran unless its deterministic stage recorded results.

When requested scrutiny reports unresolved findings or cannot complete, the final
CLI closeout labels the original answer as a draft and shows the concrete findings
or review limitation beside it. The Changed preview withholds an accepted outcome;
passing validation applies only to its recorded checks. Proposed reviewer revisions
are labelled as not applied or independently verified. Review findings are advisory:
this does not automatically rewrite the answer or prove every concern is valid.
Passing-review and no-review output retain the ordinary Agent report presentation.

Orchestrated scrutiny distinguishes workspace fingerprints since this invocation
started from Git diffs/status, which can include earlier edits. Missing start
snapshots leave attribution unknown. Fingerprints exclude runtime logs, databases
and caches; they do not prove those artifacts were untouched. Current-attempt tool
receipts provide bounded evidence. These labels help reviewers assess temporal
claims but do not guarantee a correct model verdict.

Primary and review instructions also distinguish observed tool actions from model
inference and host bookkeeping. Not using a network tool does not establish zero
provider traffic; not invoking an edit tool does not establish that all runtime
files were untouched. Broader negative claims require evidence for that scope.

Conversation history retains user requests, final agent reports and the
host-observed execution outcome, including failed validation or tool errors.
It does not persist raw tool arguments/output as additional conversation turns.
Bounded delegation checks its invocation and deadline before each child
operation, including multiple tools requested in one model response.
A tool already running may finish; expiry prevents subsequent tools and model
requests rather than forcibly interrupting that tool.
Native coding turns also check their absolute execution deadline around model
responses, individual tool actions and approvals. Expiry retains completed
effects and receipts; it does not authorize replay or turn a timeout into success.
Private user text and final responses are stored locally, so protect that file.
When a transcript log is enabled, each turn gets a distinct file beside the
requested log path. Interruption closes that file and restores terminal output.

## Current limits

- Teardown attempts foreground cleanup even if terminal cleanup raises. Incomplete
  teardown or process observation leaves the saved session `interrupted`, requiring
  explicit reconciliation before resume. Active caller contexts are restored and
  cleanup exceptions propagate with Python's normal exception chaining. A failed
  cleanup attempt does not prove every owned process was stopped.
- Expiry prevents subsequent requests, tools and approvals and rejects late
  success. Running tools are not forcibly interrupted. Interactive idle input
  expires automatically; blocking noninteractive input is checked when it
  returns, so process exit can wait for input or EOF.
- Fallback readiness preflight checks expiry before and after probes and sign-in
  answers, preventing subsequent setup/login after expiry. A probe or login
  already running is not forcibly interrupted. Coding-chat requires sign-in
  outside the conversation: it displays the official-client login command but
  never reads a login answer or launches login. Retry a turn or restart/resume
  after signing in to refresh readiness. Retry retains the existing deadline.
  Missing primary authentication produces a failed
  SUMMARY without execution, including with fallback disabled. Unauthenticated
  optional routes are excluded. Standalone requests retain interactive preflight.
  See [ADR-054](../decisions/ADR-054-external-sign-in-for-coding-chat.md).
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
- Prompt instructions and a passing model scrutiny verdict do not certify absence
  of host network or runtime-file effects. Explicit separation of host inference
  facts from agent tool-action narration is a proposed reporting-contract change,
  pending the owner's decision; the current format and verdict policy remain intact.
