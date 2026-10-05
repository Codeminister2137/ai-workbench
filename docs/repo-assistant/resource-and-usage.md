# Resource windows, usage and completion

## Model usage versus process waiting

In plain terms: running tests or a local Ollama model uses this PC. Asking a
hosted AI model to do work uses that model account's allowance. A process can wait
without asking an AI model anything. Repeatedly asking the assistant whether that
process has finished creates extra AI requests; the passing minutes do not.

The context window is how much text the model can read in one request. It is not
the account's usage limit. New messages and command results add text; waiting does
not. Exact allowance charged to the IDE assistant was not measured in this run.

A session's cached-input total can accumulate reuse of the same history across
many model requests. A reported 55M total does not establish a 55M current context
or a particular remaining subscription allowance. Prompt caching is reuse of
input, not a promise of free model work. Check IDE `/status` for current context
and account signals. Switching at a saved, committed milestone can reduce old
history carried forward, but does not reset account limits or guarantee savings.
See [prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)
and [usage guidance](https://learn.chatgpt.com/docs/pricing). This interpretation
does not verify how a particular PyCharm counter aggregates its events.

Local Ollama inference, foreground scheduler waits, subprocess polling and test
execution run locally. They do not themselves make Codex subscription requests.
The existing scheduler and external-client process readers already wait in ordinary
application code; replacing them with another service is unnecessary.

Running an official cloud agent for an acceptance task consumes that client's
applicable usage. Local fixtures do not make its model inference local. Additional
Codex subagents also perform model work; they are not a way to avoid allowance.
No Codex subagents were spawned in this implementation window.

Tool waiting itself is not model inference. Returning repeatedly to the assistant
to poll, interpret results or issue another wait can create more model work with
conversation/tool context. Avoid idle model-driven polling when there is nothing
independent left to implement. A compute window is a maximum authorized opportunity,
not a requirement to keep a chat busy until its deadline.

[OpenAI's pricing guidance](https://learn.chatgpt.com/docs/pricing) explains that
model choice, context, reasoning, tool use and caching affect usage; message history
and tool results use tokens. Exact subscription accounting for an IDE wait is not
established by those docs and cannot be inferred from elapsed wall time. Read the
client's usage/status view for the account; do not fabricate a per-minute cost.

The 2026-10-04 acceptance recorded one premium request for the real Copilot fallback.
Other bounded official-client checks also used their respective allowances; the
remaining allowance was not measured. Local research/GPT-OSS/Qwen checks used PC
resources rather than a hosted subscription. Keep correctness, integration and
model-quality checks distinct to avoid unnecessary repeated model calls.

Saved client receipts provide concrete examples: the bounded Codex shared-review
fixture reported 53,926 input tokens, including 42,496 cached, and 702 output tokens.
The Copilot portable-skill review reported one premium request. These are separate
fixtures, not the current IDE supervisor's meter or an aggregate cost for the window.
Do not count cached inputs twice or convert token totals into subscription credits
without the applicable account accounting rules.

## Priority follow-up

On 2026-10-04 the hosted supervisor stopped at 14:02:04.319 UTC (16:02 local).
Its session event recorded the displayed capacity message with
`codex_error_info: server_overloaded`. This was a hosted availability error;
it was not a recorded subscription-limit or local-memory failure. OpenAI has
[documented this exact message during service incidents](https://status.openai.com/incidents/01KX46HHYJ0YB8VPBZTB0KZ03V).
That historical incident explains the wording, not the cause of today's outage.

An already-started local scheduler worker continued independently and saved its
final handoff at 14:05:08 UTC. Its separate failure was a local repair context
budget overflow. No worker remained when the owner returned. The idle owned
Ollama server was fingerprint-checked and stopped at 17:00:53 UTC; port 11434
had no listener afterward. No new live run or sleep request followed the return.

Treat avoidable idle model turns as an immediate workflow priority. Wait in the
existing process supervisor while a task runs, do independent work, and return on
completion. Finish once independent authorized work is exhausted instead of making
repeated model turns solely to occupy the owner's absence.
For an explicitly timed unattended implementation request, record its deadline
and keep a candidate ledger. Before claiming exhaustion, freshly compare all
relevant plans with code/tests and name the evidence or exact decision blocking
each remaining candidate. A finished immediate slice or old blanket blocker is
insufficient. Continue independent approved work. Distinguish useful work from
waiting, and preserve any owner-requested earliest sleep time.

Next usage-diagnostics slice: summarize already available provider/client usage
receipts per acceptance run, mark missing measurements unknown, and distinguish
local inference from each subscription bucket. Measure a representative long wait
before deciding whether extra instrumentation is warranted. Reuse existing run
metadata/artifacts; new quota polling, account APIs, persistence or automatic budget
switching need investigation and approval. Do not spend allowance to exhaust it
as a test. Exact IDE supervisor usage remains unmeasured.

### Saved receipt summary

The read-only receipt diagnostic is implemented. Select each acceptance directory
and its known billing source explicitly; nothing is inferred from authentication,
directory names or missing balances:

```powershell
python -m uv run --no-sync python -m ai_provider.acceptance_usage --run local_free artifacts\acceptance-jobs\RUN_ID
python -m uv run --no-sync python -m ai_provider.acceptance_usage --run chatgpt_subscription_allowance artifacts\CODEX_RUN --run github_copilot_subscription_allowance artifacts\COPILOT_RUN
```

Local `worker-result.json` counters are summed separately for provider-reported
and estimated calls, with the measured-call fraction shown. External `stdout.jsonl`
uses the existing client parser and displays its latest usage receipt without
summing cumulative checkpoints. Copilot premium-request/nano-AIU checkpoints are
now recognized. Kiro exports recognized numeric meter units; repeated entries
are displayed individually and their aggregate remains unknown. Cached/reasoning
counters are separate and never added to input/output totals. No currency or
credit conversion is inferred.

The diagnostic reads only named bounded files in the selected directories and
prints recognized numeric counters. It creates no state, calls no account API,
loads no model and exports no prompt/raw client event/cache state. Missing receipts
or unsupported formats remain unknown; malformed/unreadable admitted files return
a failure. A declared source is a caller label, not verified account identity.
Remaining allowance and the current IDE supervisor's usage remain unknown.

## Explicit Windows sleep after work

Live acceptance confirmed: the owner reported on 2026-10-04 that the computer
slept successfully. The saved receipt also records `sleep_api_returned_success`
at 12:54:29 UTC. This confirms the explicit helper worked on this workstation;
automatic completion integration remains separate.

`scripts/workstation-sleep.ps1` is a small Windows PowerShell helper. Default
invocation only describes the planned action. `-Sleep` explicitly requests suspend;
`-WhatIf` exercises setup without suspending. No service, scheduled task, dependency,
automatic task-completion hook or global power setting is installed.

```powershell
.\scripts\workstation-sleep.ps1
.\scripts\workstation-sleep.ps1 -Sleep -WhatIf
.\scripts\workstation-sleep.ps1 -Sleep -ReceiptPath artifacts\sleep-receipt.json
```

For a timed unattended run, also pass its recorded UTC deadline using
`-NotBeforeUtc 'YYYY-MM-DDTHH:MM:SSZ'`. The helper refuses an early request rather
than waiting or sleeping. The deadline is preserved in the receipt; the default
without this argument retains explicitly authorized immediate sleep behavior.

Save repository files and the handoff, finish or stop owned operations, inspect
Git status/diff and preserve validation evidence before executing. This helper does
not save editor buffers, commit files, kill other applications or stop unrelated
jobs. Use it only when the owner has authorized sleeping this computer.

An optional delay of up to 60 seconds permits a hidden helper to start after final
reporting. The optional receipt is written before the request; success can return
only after wake. Report a scheduled/requested action honestly rather than claiming
sleep was observed before the PC resumes.

Final sleep reports must include the date and time in `Europe/Warsaw`, with
daylight saving applied. The helper prints the estimated scheduled time and the
request time; its receipt preserves UTC and Warsaw timestamps for every stage.
The API return timestamp can occur after wake and must not replace the request
time when reporting when work ended. A Windows Kernel-Power event can establish
the actual sleep transition afterwards. Record the unattended work start in the
handoff so elapsed work time can be reported from reliable evidence.

The helper uses Microsoft's
[Application.SetSuspendState](https://learn.microsoft.com/en-us/dotnet/api/system.windows.forms.application.setsuspendstate?view=netframework-4.8.1)
with suspend, force false and wake events enabled. Applications get the normal
suspend request. Wake timers/devices and system policy can affect how long the PC
stays asleep. It requests sleep rather than shutdown or hibernation.
