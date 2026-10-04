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

Next usage-diagnostics slice: summarize already available provider/client usage
receipts per acceptance run, mark missing measurements unknown, and distinguish
local inference from each subscription bucket. Measure a representative long wait
before deciding whether extra instrumentation is warranted. Reuse existing run
metadata/artifacts; new quota polling, account APIs, persistence or automatic budget
switching need investigation and approval. Do not spend allowance to exhaust it
as a test. Exact IDE supervisor usage remains unmeasured.

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

Save repository files and the handoff, finish or stop owned operations, inspect
Git status/diff and preserve validation evidence before executing. This helper does
not save editor buffers, commit files, kill other applications or stop unrelated
jobs. Use it only when the owner has authorized sleeping this computer.

An optional delay of up to 60 seconds permits a hidden helper to start after final
reporting. The optional receipt is written before the request; success can return
only after wake. Report a scheduled/requested action honestly rather than claiming
sleep was observed before the PC resumes.

The helper uses Microsoft's
[Application.SetSuspendState](https://learn.microsoft.com/en-us/dotnet/api/system.windows.forms.application.setsuspendstate?view=netframework-4.8.1)
with suspend, force false and wake events enabled. Applications get the normal
suspend request. Wake timers/devices and system policy can affect how long the PC
stays asleep. It requests sleep rather than shutdown or hibernation.
