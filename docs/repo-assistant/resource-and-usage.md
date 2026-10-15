# Resource windows, usage and completion

## CLI response and cumulative usage

Provider CLI metrics label `primary` and `scrutiny` usage as `final_response`.
Those numbers describe the selected response, not every call made to obtain it.
`cumulative_usage_json` separately covers instrumented Ollama and compatible
provider adapter calls within one CLI invocation (one coding-chat turn), including
prompt preparation, tool turns, support calls and fallback when they use those
adapters. External native-client allowance receipts remain separately reported;
this ledger does not claim their usage or the account's remaining allowance.

The transient ledger stores numeric per-call observations only. Each field has
`known_sum`, `observed_calls` and `coverage`: `complete`, `partial` or `unknown`.
No observations gives null, never zero. A reported zero cost is a known zero;
zero-price admission alone does not prove that an unobserved failed call cost zero.
Token and cost coverage can differ. Estimated tokens do not become provider totals.
`reported_cost_usd` normalizes a finite nonnegative numeric `usage.cost`, without
estimating prices. [Requesty documents this field as USD](https://docs.requesty.ai/).

Attempts count adapter invocations, including admission or transport failures;
they are not certified HTTP POST counts. Responses count normalized responses.
Numeric usage received before a malformed final response or stream failure remains
observed, with partial coverage even if every call supplied some numbers. Complete
coverage requires a normalized response and that field for every adapter call;
it does not certify tool/task success. Missing failed-call usage makes coverage
partial or unknown. The scope ends even on errors; no cross-turn cumulative
session total or new storage is introduced.

If an unexpected host/tool exception bypasses the normal metrics footer, the CLI
still prints any unreported cumulative numeric observations before transcript
cleanup. The exception remains a failure; no final response usage is invented.
An already printed report is not duplicated at exit, and broken output does not
replace the original error. This fallback introduces no reasoning or prompt logging.

## Hosted continuation and settings conformance

The OpenRouter adapter reuses ADR-055's transient `ProviderContinuation`: preserve
the full `reasoning_details` sequence when present, otherwise the returned
`reasoning` text. Stream fragments are assembled before replay. Only assistant
messages sent back to the same provider/model/endpoint replay these fields;
other targets omit them. Raw response/delta metadata excludes those fields, and
ordinary representations, numeric receipts and persisted answer history omit them.
Complete-input admission includes continuation; unsupported exact-count profiles
refuse it. This follows the [OpenRouter continuation contract](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).

This is offline protocol conformance, not proof of changed model quality or a
reasoning-generation setting. It leaves the Production Free privacy guard intact.
Requesty/OpenAI/Google continuation remains unverified. Inspection of Requesty's
[reasoning guidance](https://docs.requesty.ai/features/reasoning) and
[Chat Completions reference](https://docs.requesty.ai/api-reference/endpoint/chat-completions-create)
did not establish the named Nemotron route's continuation replay contract; do not
infer that contract from OpenRouter or general protocol compatibility.

Under [ADR-058](../decisions/ADR-058-opt-in-task-sampling-controls.md), opt-in
`--temperature` (finite 0–2) and `--top-p` (finite 0–1) configure task requests for
one invocation, including native tool turns, task repairs, scrutiny, provider chat
and API/native fallback or preservation. For example, append
`--temperature 1.0 --top-p 0.95` to an existing provider-native invocation.
Omitted flags preserve omission on the wire; explicit zero is forwarded. Native
delegated loops inherit the task options; separately configured context delegation
and rolling summaries retain their own behavior. External native-agent clients
are refused with explicit sampling because equivalent mappings are unverified.
`requested_sampling_json` records requested values, not confirmed effective hosted
settings. These options are not persisted defaults and confer no model-quality
or live-trial approval. Temperature/top_p/output forwarding is tested; native
template settings and the hosted endpoint's actual behavior remain unmatched.
NVIDIA recommends [temperature 1.0 and
top_p 0.95](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16);
the [Cohere card](https://huggingface.co/CohereLabs/North-Mini-Code-1.0) gives the
same recommendation. Native template options are not assumed to be gateway
options. The owner accepted opt-in controls with existing defaults preserved;
no automatic preset or template override has been selected here.

## Periodic workstation snapshots

On Windows, `scripts/workstation-resources.ps1` performs a read-only CIM snapshot.
It reports CPU load, available physical RAM, GPU dedicated/shared memory use and
an estimate from the busiest GPU engine. It emits no process names, commands or
model prompts. Missing counters produce null values and explicit unavailable
labels. Free dedicated VRAM remains unknown; these counters expose usage without
a trustworthy allocation budget.

Run once, or use `-SampleCount 60 -IntervalSeconds 60` for a bounded series of
JSON lines. `-NotAfterUtc` stops further samples at a selected deadline. The
collector changes no process priority, model profile or running call and starts
no background service. A future dashboard can request snapshots independently
of model execution. Gaming-mode transitions remain an owner decision.

The owner reported gaming during the 2026-10-12 CLI pilots. Those historical
timings are confounded and must not justify model-routing or hardware changes.
Slow successful work under contention is acceptable; correctness, cleanup and
deadline evidence remain distinct from speed. New evaluations record snapshots,
which do not by themselves identify game activity or establish a controlled
performance comparison.

RAM fields use the documented [Windows operating-system counters](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-operatingsystem).
The GPU estimate aggregates each engine's process instances, then selects the
busiest engine following the [Task Manager measurement approach](https://devblogs.microsoft.com/directx/gpus-in-the-task-manager/).

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

For matched external economics comparisons, ADR-050 records the owner's 20%
savings target, including primary/delegated work, failures and retries. Below
target means case-by-case owner review, not automatic rejection. Missing or
incomparable billing measurements cannot establish savings. Local tokens and
elapsed time remain diagnostic evidence without a hard runtime-reduction gate.

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

New local fixed-harness receipts include elapsed seconds for the complete fixture
(including validation) and each attempted model call. The diagnostic reports
those separately, including failed calls whose token usage remains unknown.
Responses received after the deadline retain their reported token counters even
though the operation fails. Older receipts without timing remain readable and
their elapsed time stays unknown. Timing informs comparison under ADR-050; it
does not impose a hard completion-time acceptance threshold.

The diagnostic reads only named bounded files in the selected directories and
prints recognized numeric counters. It creates no state, calls no account API,
loads no model and exports no prompt/raw client event/cache state. Missing receipts
or unsupported formats remain unknown; malformed/unreadable admitted files return
a failure. A declared source is a caller label, not verified account identity.
Remaining allowance and the current IDE supervisor's usage remain unknown.

### First automatic allowance source: Codex selected and implemented

The owner accepted automatic integration under ADR-050. Investigation on
2026-10-10 found two documented first-source candidates:

- Copilot `account.getQuota`: exposes entitlement/used request counts, remaining
  percentage and reset date by quota type. Reuses the headless RPC transport
  already used for authentication readiness; does not cover Codex allowance.
- Codex `account/rateLimits/read`: exposes quota windows and Unix reset timestamps,
  with a multi-bucket view when available. Covers the baseline client, but needs
  an app-server handshake and preserves separate buckets rather than inventing a
  global remaining balance.

The initial recommendation was Copilot first to reuse the existing transport.
The owner selected Codex first because it is their main source. The implemented
slice is a bounded read through the installed client's existing login, retaining
normalized measurements in memory and leaving routing unchanged. The native
client makes an authenticated provider request; no prompts or repository content
are sent by the collector. Missing/unsupported responses remain unknown. No new
credential discovery, SDK dependency, persistent snapshots or background monitor
is introduced.

```powershell
python -m uv run --no-sync python -m ai_provider.codex_usage --timeout-seconds 15
```

The command returns normalized JSON: observation time, separate bucket/window
identities, used percentages, durations and Unix reset timestamps. Unknown numeric
fields remain null. It exports no raw errors, account identity, optional labels
or credit/reset-redemption details. Initialization and one quota read are the only
operations. Owned process-tree cleanup is checked; an unverified cleanup withholds
the measurements. Timeout covers handshake/response, with up to two extra seconds
for cleanup. The collector saves no snapshots; Codex manages its existing native
authentication, logs and state. Exit 0 means a quota-window observation was read
and cleanup verified; it does not guarantee future allowance or model availability.

References: [Copilot usage and billing](https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/usage-and-billing#account-quota-and-premium-interactions)
and [Codex app-server rate limits](https://learn.chatgpt.com/docs/app-server#6-rate-limits-chatgpt).
One authorized installed-client read succeeded at 2026-10-10 09:08:32 UTC,
reporting 20% used in the 300-minute window and 64% in the 10080-minute window, with
cleanup verified. Values are historical observations, not current remaining
allowance guarantees. Account-wide windows may include other work and are not
per-task billing measurements; no delegation savings claim follows. Quota-aware
routing, other provider readers and task-level attribution remain subsequent work.

Execution sessions now support an injected allowance observer. Observations stay
in memory, carry the collector's source and observation time, and are separate
from route eligibility, exhaustion decisions and saved continuation handoffs.
The hook observes only attempted routes and caches both available and unknown
results by billing source for the execution scope. Its collection time counts
against an existing continuation deadline. The Codex adapter supports declared
ChatGPT subscription routes only; it does not represent API spend or workspace
credits. The execution CLI automatically invokes the observer before the first
supported subscription attempt in each execution scope, including when automatic
fallback is disabled. Coding chat creates a fresh scope for each owner turn;
repairs within a turn reuse the same observation. There is no timer, end-of-task
refresh or polling of authenticated candidates that are never attempted.
This bounded default is an implementation choice under the approved automatic
observe-only integration, not a new quota-based routing policy. The observation
timestamp describes when data was read; a cached value does not guarantee current
capacity. Unknown collection results do not stop execution or trigger fallback.
An observer exception is retained as a sanitized unknown observation rather than
aborting the task; cancellation still propagates. The existing execution deadline
is rechecked after collection, including a failed collection. No raw adapter error
is included in progress output, and a failed observer is not repeatedly called
within the same execution scope.
Copilot's existing authentication preflight now reuses the same owned native
lifecycle and bounded account-RPC framing. Synthetic success, timeout and root-exit
checks verify descendant cleanup; only `auth.getStatus` is requested and account
identity fields are discarded. This software check does not establish current
installed-client authentication or remaining allowance.
The offline readiness report still performs no account calls.
An injected progress reporter can display normalized observations; the existing
explicit `--log-file` option also captures displayed progress. This adds no
quota database or automatic snapshot files.

The existing Copilot authentication-readiness transport now bounds header reads
and accepts success only from a JSON-RPC 2.0 response with the exact integer
request ID, no error field, and a boolean authenticated result. Malformed
responses remain unverified and owned pipes/processes are closed. Authentication
readiness remains distinct from the separate quota reader described below.

### Copilot automatic allowance observations

`ai_provider.account_usage` dispatches supported Codex, Copilot and pinned Kiro
subscription routes to provider-specific readers. Copilot uses the headless stdio
client's `account.getQuota` RPC with existing native global authentication.
No session, prompt, model turn, login flow or credential-file discovery is used.
GitHub receives the native authenticated account request; no repository content
is selected or transmitted by the collector. BYOK environment overrides withhold
subscription measurements. The collector creates no storage; the native client
keeps responsibility for its normal authentication/runtime state.

```powershell
python -m uv run --no-sync python -m ai_provider.copilot_usage --timeout-seconds 15
```

Configure `GITHUB_COPILOT_COMMAND` or expose `copilot` on PATH using the existing
execution configuration mechanism. The command does not automatically load `.env`.
An unavailable command returns unknown without launching a process.

Normalized windows retain quota type, entitlement/used requests, remaining percent
and the reported ISO reset date. Entitlement `-1` is the native unlimited marker,
not a negative balance. Missing values remain null; no reset timezone, available
request count, token price or task charge is inferred. Quota types remain separate.
The native request and cleanup use the same bounds/ownership machinery as Codex;
strict bounded Content-Length framing and RPC identity validation are specific to
Copilot. Unsupported/malformed responses remain unknown; unverified cleanup
invalidates measurements. The once-per-execution-scope observer and offline
readiness contracts are unchanged.

One installed-client read succeeded at 2026-10-10 10:13:37 UTC with cleanup verified:
chat reported 200 entitlement / 200 used / 0% remaining; completions 2000 / 0 /
100%; premium interactions 0 / 0 / 0%. The provider returned reset date
`2026-10-10T10:13:36.130Z`. These are historical account observations, including
the provider's reset field, not guarantees of present capacity or proof of a
particular paid plan. No model call or task-spend attribution was performed.
See [GitHub account quota documentation](https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/usage-and-billing#account-quota-and-premium-interactions).

## Kiro isolated native estimates and Antigravity investigation

`ai_provider.kiro_usage` supports the inspected Kiro CLI 2.24.0 V2 quota path.
The collector checks the version before starting a session, creates a temporary
agent with empty tools/resources/hooks/MCP, disables global MCP inclusion and
process-local auto-updates, and submits only `/usage` with stdin closed. It refuses
temporary directories inside repositories or instruction-bearing ancestry.
Version checks and quota collection share the requested time allocation; each
owned native process has up to two seconds of cleanup. Temporary profile files
are removed after collection. Kiro retains responsibility for ordinary native
authentication/session state; no new login, keys or permission grants are used.

```powershell
python -m uv run --no-sync python -m ai_provider.kiro_usage --timeout-seconds 15
```

Use existing `KIRO_COMMAND` configuration or native command discovery; `.env` is
not automatically loaded. Automatic observations include supported Kiro
subscription attempts, once per billing source per execution scope. Available
and unknown observations remain separate from routing, exhaustion and handoffs.

The native header says `Estimated Usage`: snapshots carry
`measurement_kind: native_estimate`, `covered_credits`, `plan_credits`,
`reported_percent` and the native reset date. They do not establish remaining
credits, the percentage's used/remaining semantics, a reset timezone, exact
subscription consumption or task-level savings. Unverified versions, additional
credit/organization formats, invalid output and unsafe temporary ancestry remain
unknown. Cleanup failure withholds observations. Offline tests exercise the
actual owned subprocess lifecycle and isolation configuration using synthetic
clients; they do not contact native accounts.

The final installed-adapter check at 2026-10-10 11:26:09 UTC reported estimated
50 covered / 50 plan credits, 100%, reset 2026-11-01, with cleanup verified.
Earlier diagnostics were used to establish the native output format; two strict
parser compatibility attempts returned unknown before the corrected adapter
passed. No model turns, tools, hooks or repository content were submitted.

Antigravity 1.3.0 has documented no-turn print-mode `/usage`, but installed-binary
inspection found common manager/hook/background-worker initialization before
quota dispatch. Startup isolation was not proved, so no quota diagnostic ran and
no automatic collector is advertised. A documented account-only interface or
supported startup isolation would unlock this candidate. Do not work around the
boundary through global settings, new credentials or permissions.
See [Kiro agent configuration](https://kiro.dev/docs/custom-agents/configuration-reference/)
and [Antigravity's official CLI changelog](https://github.com/google-antigravity/antigravity-cli/blob/main/CHANGELOG.md).

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

For a timed unattended run with sleep authorized only at its deadline, pass that
recorded UTC deadline using
`-NotBeforeUtc 'YYYY-MM-DDTHH:MM:SSZ'`. The helper refuses an early request rather
than waiting or sleeping. The deadline is preserved in the receipt; the default
without this argument retains explicitly authorized immediate sleep behavior.

If the owner explicitly authorizes sleep when work ends early, schedule it ten
minutes after legitimate early closeout and safe cleanup, preserving the original
deadline, actual stop time and reason in the handoff. Remaining blocked work or
an incomplete baseline does not cancel this authorization. Do not omit the guard
merely because one slice finished. An explicit return to attended mode cancels
unattended sleep not yet requested: create its cancellation marker and verify
the helper records `sleep_cancelled` before resuming work. New owner instructions
during the grace period require the same cancellation. Never issue retrospective
sleep while the owner is using the PC.

Save repository files and the handoff, finish or stop owned operations, inspect
Git status/diff and preserve validation evidence before executing. This helper does
not save editor buffers, commit files, kill other applications or stop unrelated
jobs. Use it only when the owner has authorized sleeping this computer.

An optional delay of up to 600 seconds permits a hidden helper to start after final
reporting. For authorized early sleep use `-Sleep -DelaySeconds 600 -ReceiptPath
<fresh-receipt.json> -CancelPath <fresh-cancel-marker>` with absolute paths and
`Start-Process -WindowStyle Hidden`. Save the helper identity, receipt and marker
paths in the handoff. Report the scheduled local time and an exact PowerShell
cancellation command, such as `New-Item -ItemType File -Path '<absolute-marker>'`.
The helper checks the marker each second and immediately before requesting sleep;
an existing marker cancels even a zero-delay request. Do not delete or reuse a
marker from another run. This is a bounded helper process, not a scheduled task
or service. During the grace period report sleep as scheduled, not requested.
The optional receipt is written before the request; success can return
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
