# Architecture

For package responsibilities, start with the [project map](project-map.md).
The repo assistant's [workflow guides](repo-coding-assistant.md) describe current
execution surfaces; [publication](publication.md) covers source/history privacy.

## 1. Overall direction

Known malformed generated tool arguments may use the neutral ToolCallFormatError
signal for shared-loop correction within the original allowance (ADR-061). This
is separate from transport retry/fallback. The initial production path stops on
repeated failures at the same observed file state, preserving prior effects and
history; it adds no live approval prompt or private-pilot approval substitution.

Provider-neutral messages may carry optional transient ProviderContinuation
metadata (ADR-055). Adapters own interpretation and replay only to the originating
provider/model/endpoint. It is not answer text or durable history; input admission
counts it. Ollama preserves multi-turn thinking without an implicit adapter cache.
See the [high-priority conformance plan](documentation-conformance-plan.md).

ADR-073 extends that contract to shared Responses tools and stateless native replay.
The adapter preserves tool-call/result identity, native output order and assistant
phase; Meta requests opaque encrypted reasoning with `store:false`. Rewritten
messages and other routes do not replay stale native state. No server-managed
conversation storage or new approval policy is introduced.

Native coding fallback may transfer complete observable messages/tool history
transiently when the destination request leaves at least 20% context headroom
after input, tools, reserved output and framing (ADR-059). Otherwise retain the
bounded observed-state handoff, including unknown effective capacity. Provider
continuation, saved handoffs and weaker preservation prompts remain excluded;
privacy, billing, quality and approval gates still precede implementation fallback.

The projects form a small ecosystem:

`Applications → AI Orchestrator decisions → execution adapter → Ollama / Requesty / direct providers`

Applications include the AI Council, Job Search Automation, and future automation/client applications.
Applications should support official AI access routes, such as local Ollama,
direct hosted provider APIs, Requesty-style gateways, subscription-backed
clients such as Codex CLI, and orchestrator-guided route selection. The choice
should be configuration or orchestration policy, not provider-specific
application branching.

Repository layout:

```text
packages/
  ai_provider/
  ai_orchestrator/
  ai_agent/
apps/
  ai_council/
  job_search/
```

Current implementation started with an Ollama-only provider slice. The first
useful coding MVP should support local Ollama, Requesty, Codex CLI, and
OpenAI-backed execution through explicit access routes, with cloud execution
remaining explicit and privacy-controlled.

Longer term, the repository is intended to support a personal AI dashboard that
can replace a meaningful share of day-to-day ChatGPT use while remaining
integrated with the owner's local projects and automation. Coding is the hardest
and most correctness-sensitive target, but the same infrastructure should also
support general chat, internet-assisted research, shopping decisions, workout
planning, project planning, prompt refinement, model comparison, and AI Council
style multi-model discussions. The dashboard should be able to route requests
across local and cloud models, test model performance, expose routing reasons,
and preserve privacy boundaries instead of hard-coding one model or provider.

This is a product direction, not a license to add speculative infrastructure.
Important parts remain open decisions: persistence, personal memory, background
job execution, web/search integrations, dashboard UI, model-evaluation storage,
and autonomous actions all require separate approval before implementation.
Achievability should be validated incrementally with measured benchmarks,
representative project tasks, and explicit comparison against the current Codex
and ChatGPT workflows.

Infrastructure packages such as `ai_provider` and `ai_orchestrator` may grow a
larger library of integration glue than individual applications. That is useful
when the glue preserves interoperability across apps, keeps provider-specific
details out of application workflows, and remains focused on infrastructure
responsibilities. Applications should still own their product workflows and
domain behavior.

Packages should compose without unnecessary hard dependencies. A package may be
designed to work naturally with another package, but it should own its local
decision contracts when callers may reasonably use another implementation. For
example, the Orchestrator returns neutral execution targets that can be adapted to
`ai_provider`, direct Ollama calls, Codex CLI, or future official client
executors.

The architecture prefers simple standard-library code when it remains clear, but
does not treat dependency avoidance as an architectural goal. Small, mature,
focused dependencies are appropriate when they reduce custom complexity,
edge-case risk, testing burden, or future maintenance cost without blurring
package boundaries. `httpx` and `pydantic` are pre-approved when a concrete task
justifies them; other focused dependencies remain allowed when they satisfy the
same criteria.

## 2. Modular monolith first

The `ai-assistant` entry point and its CLI implementation, argument parsing and
execution settings belong to `ai_agent` (ADR-048). This composes its existing
provider/orchestrator dependencies without adding a reverse provider dependency.
Provider/client adapters remain in `ai_provider`. Existing research, run-store
and fallback helpers remain there for this focused migration; earlier references
to provider-owned CLI composition describe that historical/helper placement.
Legacy CLI module imports and entry points delegate to the agent implementation.
Within `ai_agent`, validation execution, chat-context assembly, external diagnostics,
foreground run tracking, delegated-source rendering, local support, repair and scrutiny are
reusable modules. Command dispatch composes them; provider storage/adapters and
orchestrator policy keep their existing boundaries.

Delegated implementation uses the supervisor's host-bound tools and live
permissions, optional narrower grants and shared finite reply/tool/deadline
bounds. Funded children retain the exact approved client and admission guards.
This is tool-level authority, not OS isolation; see
[ADR-074](decisions/ADR-074-delegation-inherits-supervisor-authority.md).

The optional Remote AI Operator approval bridge transmits action digests and
metadata-only descriptions, without workspace paths or argument names/values.
It retains exact-action binding; the owner must inspect command/diff content
through an authorized channel. See
[ADR-075](decisions/ADR-075-metadata-only-operator-approval-descriptions.md).
The callback verifies the polled action identity/digests and unchanged tool
arguments before accepting approval. Its single round-trip deadline is capped
by the CLI execution deadline; late approval is refused. Best-effort cancellation
has a separate one-second request timeout. In-flight HTTP operations are not an
OS-enforced wall-clock bound. The current base digest identifies the workspace,
not file preimages: intervening file changes do not invalidate argument-only
approval. File-state binding is an owner decision pending investigation evidence.

ADR-049 adds a distinct foreground `coding-chat` mode. `ai_agent.coding_chat`
owns conversation continuity over injected turn execution; `coding_chat_cli`
binds existing coding-session/foreground tools to the current CLI executor.
Conversation transcripts and coding receipts share a session ID in existing
SQLite storage without a schema migration. Each turn refreshes source context
and execution scopes; history is not cached file state or approval authority.
`coding_chat_input` arbitrates in-flight terminal input: steering is durably
queued for the next turn, while approval answers name a fresh prompt ID and
remain invocation-scoped. Its polling reader joins before idle input resumes;
execution stays on the foreground thread for signal/context-variable cleanup.
Long-history reduction is local and deterministic: owner messages and host
evidence remain intact; older assistant reports become marked excerpts with
references to unchanged SQLite originals. Mandatory-context overflow refuses
execution, including after restart; no additional inference or summary store.

ADR-060 adds optional error provider/category/cause-kind and a bounded fallback
control receipt to the existing coding-chat metadata. The CLI renders the same
attribution and distinguishes unknown provider/cause from the effective route.
History includes only recognized handoff control facts, never raw observations,
save-error text or transient provider continuation. Cause type alone is not a
root-cause diagnosis; no SQL migration or fallback policy change is introduced.

The repo-assistant CLI owns shared direct-child processes through one foreground
supervisor. Its per-client MCP adapters forward to an authenticated ephemeral
loopback MCP host with invocation-scoped credentials and sessions (ADR-044).
Native tool execution uses the same supervisor. Existing optional SQLite receipts
record observations; restart does not restore live pipes or process ownership.
Read-only PyCharm wrappers use a separately imported machine-local endpoint and
an optional official MCP SDK. Neither host introduces a background daemon.

Start as a modular monolith. Extract a separately deployable service only for a demonstrated need such as independent scaling/deployment, a different security/runtime boundary, operational isolation, or a real development bottleneck.

For GitHub publication, keep the workspace as one cleaned-up monorepo with
strong internal `packages/` and `apps/` boundaries. Separate repositories remain
a future option only when a concrete extraction criterion is met, such as stable
independent releases, different access/privacy boundaries, or a real review and
development bottleneck.

## 3. Provider-agnostic AI infrastructure
The provider layer exposes common AI request/response contracts and translates them to provider APIs. It owns provider authentication, request/response translation, provider errors, streaming, model IDs, and usage metadata.

It does not own application-specific task strategy or high-level model-routing policy.

## 4. AI Orchestrator
The Orchestrator makes AI-request decisions without requiring a specific executor:
- task classification;
- prompt evaluation/refinement;
- model and request configuration;
- routing;
- fallback/retry;
- privacy constraints;
- latency/reliability considerations;
- cost/quota awareness;
- usage integration;
- eventually adaptive routing based on measured performance.

It should expose neutral orchestration contracts. It may integrate with
`ai_provider` through adapters/examples, but the core package must not require
`ai_provider` merely to make routing decisions.

The Orchestrator selects access routes, not provider/model pairs alone. A route
represents one official execution path with its own provider, product/service,
access method, authentication method, billing source, cost-policy tier,
capabilities, availability, and model.

Keep separate concepts:
- **Capability:** what a model can do.
- **Performance:** how it performs on this user's workload.
- **Economics:** cost, quotas, rate limits, and resource constraints.
- **Access route:** whether execution uses a provider API, local runtime, Codex
  CLI, or another executor.
- **Authentication:** whether the route uses an API key, ChatGPT sign-in, no
  credential, or a future token/session mechanism.
- **Billing source:** whether usage consumes API billing, Requesty billing,
  local resources, a ChatGPT subscription allowance, or workspace credits.
- **Cost policy:** the maximum financial boundary a task may cross. Current
  tiers are `LOCAL_ONLY`, `FREE_ONLY`, `ALLOWANCES_ALLOWED`,
  `PREPAID_CREDITS_ALLOWED`, and `BILLING_ALLOWED`.

Auxiliary AI work should be routed separately from the primary task. Response
scrutiny, context extraction, summarization, prompt refinement, and similar
support passes should derive child task profiles that prefer local or cheaper
routes by default. A support pass must not silently reuse an expensive,
allowance-backed, prepaid-credit, or metered primary route unless the task
explicitly needs that escalation and the route/cost boundary is reported.

Evolution should be incremental: manual model choice → static rules → capability-aware selector → quota-aware selector → adaptive selector.

The opt-in research policy uses `ai_orchestrator.review` for explainable neutral
reviewer/mode plans and resource admission. `ai_provider.research_review` checks
installed native controls and maps boolean thinking separately from named effort.
It preserves full evidence, clamps generation/time, and permits one stronger
output-truncation retry. Legacy selection remains the default. Representative
evaluation precedes conditional research-only default activation;
public-source excerpt persistence is permitted only for local evaluation artifacts.
Production excerpts remain process-local. See ADR-038 for accepted limits and gates.

The optional provider-owned local tokenizer file supplies complete research-review
input counts only for fingerprint-verified framing. The renderer is shared with
the offline diagnostic. Unsupported or unavailable profiles retain conservative
byte admission; assets are never automatically downloaded and no private runner
endpoint is required. See the research runbook for the intentionally bounded scope.

`ai_orchestrator.scheduling` implements pure foreground time-admission contracts:
tasks stay planned
until an explicit command supplies an execution window, then sequential time
admission checks each required allocation against remaining time. No background
daemon or distributed service is approved. `ai_provider.task_scheduler` persists
immutable executable research definitions and lifecycle state in an additive table
in the existing run SQLite database. Its foreground CLI starts explicitly selected
tasks through the existing research supervisor and stops at the first refusal or
failure, preserving waiting tasks. Local-only/free-only research controls apply;
planning/listing load no models. Per-definition claims prevent duplicate starts,
but independent foreground invocations are not a global queue. Generic executor
cancellation remains unsupported. See ADR-039.

## 4.1 Authorization and approval policy

Declared tool parameter types are checked before authorization and execution.
Authenticated provider requests refuse redirects, recursive inspection validates
resolved file paths, and public fetch/search share a response deadline watchdog.
Council's local HTTP surface validates origins and bounded JSON bodies before
inference. Job application approval binds exact reviewed materials and guarded
delivery uses verified attachment bytes. These bounded hardening changes are
recorded in [ADR-047](decisions/ADR-047-fail-closed-execution-boundaries.md);
remote authentication remains a separate decision. CLI ownership is resolved by
[ADR-048](decisions/ADR-048-agent-owned-assistant-cli.md).

Task profiles default to `PREPAID_CREDITS_ALLOWED`. The repo assistant overlays
private TOML user preferences before routing; explicit CLI flags take precedence.
Paid Requesty catalog routes require prepaid authorization; the separate free
route checks live zero prices before each inference request. See ADR-031 for the
user-preference format and alternate official CLI adapters.

Default usage-limit fallback policy belongs to `ai_orchestrator.fallback`.
The CLI preflights eligible executors, preserves the working tree, and supplies
an observed-state handoff. Replacement routes stay on the same billing tier,
retain privacy/approval constraints, and default to preserving the original/task
declared quality floor for implementation. Default `emergency_preserve` permits
weaker routes only for read-only inspection and reporting after saving a deterministic
handoff. Explicit `prefer_quality` admits weaker implementation after stronger
routes are unavailable; legacy `task_minimum` retains the task quality floor.
Exhausted billing buckets and temporarily overloaded routes are tracked separately
for the run; no persistent quota registry is introduced. No suitable replacement
produces a saved handoff even when no model remains. Preservation reporting cannot
turn the original failure into task success. See ADR-032, ADR-042 and ADR-052.

External user authorization is a shared infrastructure concern, not a per-tool
implementation detail. GitHub, Codex plugins/apps, cloud deployment targets,
document/control tools, issue trackers, and similar services should use one
reusable authorization boundary for sign-in/token discovery, permission
summaries, diagnostics, and revocation guidance.

Individual tools and adapters should consume that boundary rather than reading
credentials or managing OAuth/session state independently. Adding a new
authorized service must explicitly identify what data can be read, what actions
can be written, what credentials or sessions are used, and what approval policy
applies.

Approval modes should be model-neutral. Codex is the baseline execution
experience, but the project-owned policy should also work for Ollama, hosted
providers, direct provider APIs, and future executors. Tool contracts should
model read and write capabilities together when writes are foreseeable, even
when write actions are disabled by default or require a stricter approval mode.

## 4.2 Shared agent tools and development continuity

ADR-040 approves common project-owned tools exposed through MCP and native
adapters while retaining official clients and allowance routes. The initial
foundation covers repository/local Git operations, portable skills/instructions,
Python validation, documentation/public research, semantic code tools and
process/session continuity. This is an accepted target, not implemented parity.

Reuse `ai_agent` contracts and execution boundaries; keep route selection in
`ai_orchestrator` and provider/client translation in execution adapters. PyCharm
may initially host semantic tools, but the eventual target is independent tooling
with PyCharm serving only as human editor/viewer. Fallback should preserve access
to the required common tools and observed task progress without broadening
permissions or replaying uncertain effects.

ADR-053 defines `--away-minutes` as one fixed foreground allowance shared by
coding-chat turns, delegation, fallback and host stages within a launch.
`--turn-timeout-seconds` can shorten a turn; provider request timeouts remain
separate. Each launch explicitly supplying an away allowance grants fresh time,
including saved-session resume. No persisted deadline or restart-reason policy
is introduced. Expiry blocks new actions and late success; it does not forcibly
interrupt running tools.

ADR-054 keeps coding-chat's terminal reader separate from authentication:
official-client sign-in happens outside the conversation. Readiness checks do
not launch login or collect login answers; retry/resume/restart refreshes readiness.
Standalone CLI preflight retains its existing interaction.

Concrete session/process persistence, host lifecycle, approval transport and
dependencies remain open decisions. No new daemon, connector, paid escalation or
general scheduler is implicitly authorized. See the tracked
[development roadmap](repo-assistant/development-roadmap.md) for milestones,
acceptance conditions and the next implementation action.

## 5. Prompt evaluation vs optimization
A prompt evaluator judges whether a request is adequate and identifies ambiguity/missing context. A prompt optimizer produces improved wording or variants.

Initial flow:
`User prompt → judge → suggested refinement → user approval → target model`

Do not begin with autonomous optimization. Later, benchmark prompt variants automatically.

## 6. Usage tracking
Track, where available:
- timestamp;
- application/task;
- provider/model;
- input/output tokens;
- estimated cost;
- quota/resource consumed;
- latency;
- success/failure/error category.

Avoid sensitive prompt content by default. Usage tracking should inform routing but remain conceptually separate from provider adapters.

Under [ADR-050](decisions/ADR-050-usage-measurement-and-automatic-integration.md),
external economics use allowance consumption or API spend. Local execution records
total tokens and elapsed time; time informs evaluation without a hard median-time
migration rejection gate. Automatic usage/allowance integration is the accepted
direction, growing supported provider adapters incrementally. Provider-specific
collection stays behind adapters; neutral routing policy stays in the Orchestrator.
Existing receipt diagnostics do not yet provide automatic account balances/resets.
The first automatic source is now `ai_provider.codex_usage`, selected because
Codex is the owner's main source. It reads account quota windows through a
temporary native stdio app-server and existing login, retains observation time
and separate buckets in memory, and verifies owned process-tree cleanup. It
does not change routing or infer per-task consumption from account-wide windows.
Copilot's `account.getQuota` reader is also supported through native headless
stdio. It preserves quota types, request units, remaining percentage and native
ISO reset dates; BYOK subscription overrides remain unknown. A provider-layer
dispatcher selects supported access/billing pairs; the collectors share owned
native process deadlines and cleanup. Kiro CLI 2.24.0 additionally supports a
temporary V2 quota-only session with empty tools/resources/hooks/MCP, outside
repository ancestry. Its plan-credit output is explicitly a native estimate;
remaining balance and percentage semantics are not inferred. Other Kiro versions
and Antigravity startup isolation remain unverified. No reader creates model turns
or discovers credential files; Kiro may retain ordinary native session state under
the owner's isolated-session approval.
The execution CLI collects once before the first supported subscription attempt
per execution scope; coding chat creates one scope per owner turn. Unknown
observations remain diagnostic and offline readiness does not perform account calls.

## 7. AI Council
The Council is an application on top of the AI infrastructure:
`user question → council router → multiple models → raw responses → synthesis → final answer`

Preserve raw responses so synthesis does not erase disagreement. Initial modes may be LOCAL, CLOUD, and HYBRID. The UI should make local vs external processing understandable.
Its implementation should allow ordinary provider connections and
orchestrator-guided routing without hard-coding Ollama, OpenAI, Requesty, or any
other provider into Council-specific business logic.

## 8. Job Search Automation

Openings is the owner-selected discovery/tracking candidate. The accepted
integration boundary is an external API bridge plus a reviewed pinned fix for
manual-import mirrors, rather than its internal collector interface. The offline
client exports one page and intakes source postings explicitly as `new`, using
only an operator-configured numeric loopback endpoint and token. Writes require
verified patch deployment; tracker status never grants delivery approval. No app
deployment or candidate-profile transmission has occurred. See ADR-051 and
`integrations/openings/` for the patch and remaining runtime checks.
Flow:
`job sources → ingestion → normalization → matching → application analysis → CV/message suggestions → human review → application → tracking`

Use a normalized internal job schema. Matching should preserve evidence. CV tailoring may rephrase and prioritize genuine experience but must never invent experience or qualifications. Human approval remains the default before external applications are sent.

## 9. Privacy boundary
Local inference is the trusted privacy tier. Cloud providers and gateways are
external processors. Future controls may include task-level privacy requirements,
local-only routing, sensitive-data detection, optional redaction, and
provider/backend audit information.

Application chats should be represented as provider-neutral local transcripts.
When a model changes, the application should keep the same chat and send the
relevant retained context to the newly selected backend. Future truncation or
summarization must be visible when a model's context window cannot fit the full
history.

Prototype privacy classes are currently:
- `LOCAL_ONLY`;
- `EXTERNAL_ALLOWED`;
- `SENSITIVE_REVIEW_REQUIRED`;
- `PUBLIC_OR_LOW_RISK`.

These labels are provisional until cloud routing and real external provider adapters are implemented.

ADR-063 adds an opt-in OpenRouter exception for explicitly public/synthetic
requests: the low-risk class alone is insufficient; the caller must attest the
complete input through exact boolean request metadata. Only uncertain privacy-
filter entitlement is relaxed; private/default request gates, zero-price/quota
checks and requested data-policy filters remain. This is not automatic CLI
classification, persistent consent or a guarantee of provider retention terms.

ADR-069 adds a separate narrow path for explicitly reviewed non-sensitive input:
one digest-bound USER message without tools, history or continuation. The owner
permits non-sensitive repository material even when it is not public. This
exception does not classify arbitrary agent-loop data or alter ADR-063's public
attestation. General repository protection remains planned, not enabled.

## 10. Shared code
Share code only when multiple projects genuinely need the same stable behavior. Good candidates are common AI contracts, provider adapters, and stable usage/configuration primitives. Avoid shared packages for experimental or application-specific logic.

Prefer interoperable infrastructure seams over app-specific glue. A reusable
provider adapter, orchestration contract, config bridge, streaming contract, or
request/response translation belongs in infrastructure when more than one app
can plausibly use it or when keeping it in an app would leak provider assumptions
into business logic.

Prefer optional composition between packages. Do not introduce a direct package
dependency just because two components are expected to work together in the common
workflow. Add the dependency only when the dependent package cannot usefully exist
without the other package's contract.

## 11. Architecture decision boundary
Generated run output is grouped under ignored `artifacts/<run>/`, including
reports, logs, acceptance workspaces, and dedicated run databases. Shared ongoing
application state stays in `data/`. Authorized artifact relocations preserve
original write receipts and add digest-bound path mappings in existing stage
metadata; see ADR-035.

The explicit research tool profile uses neutral selection in `ai_orchestrator`,
public fetching/report tools and deterministic report checks in `ai_agent`, and
agent-owned CLI composition over existing research/run-store helpers in
`ai_provider` (ADR-048). Actual tool receipts reuse existing
SQLite implementation-stage metadata. Research requires local provider-native
execution; external clients own their registries and cannot preserve this
restricted surface. See ADR-033 for fetching, permission, and evidence boundaries.
`ai_provider.research_runner` supervises one foreground research worker, enforces
its elapsed budget, and records timeout handoffs without a daemon or new store.
The foreground scheduler persists typed research settings in the existing
application SQLite store and admits explicitly selected jobs sequentially. Its fixed
acceptance adapter reuses this supervisor and the standalone harness's public prompt
and postchecks, with dedicated task artifacts; it exposes no arbitrary command
executor. Old task states/defaults survive the additive migration. See ADR-039.
ADR-043 adds `ai_provider.acceptance_jobs` with immutable local native coding
definitions and receipts in separate additive SQLite tables. It reuses neutral
time admission and a fixed, source-scoped fixture. Its foreground supervisor
owns Windows runtime/worker/validator trees, verifies listener identity and
records cleanup before completion. This does not generalize research payloads
or introduce arbitrary-command or hosted jobs. Live execution requires a new
explicit selected window; planning is offline and never starts a runtime.
`ai_provider.research_refinement` composes repeated report review, native execution,
and validation through existing stages after structural success. It shares repair
limits, reserves final-review time, and detects repeated report/source no-progress.
Research model requests also respect the remaining attempt allocation.
ADR-036 composes Tavily, Brave, and SearXNG discovery with bounded free-only
fallback. Neutral route eligibility belongs to `ai_orchestrator.search_policy`,
HTTP adapters/tool execution to `ai_agent.tools.research_search`, and CLI/run
evidence helpers to `ai_provider.research_execution`, invoked by the agent-owned
CLI (ADR-048). Reduced tracking stays
on SearXNG; local inference is independent of public search transmission.
Full query/attempt receipts remain separate from source-fetch evidence.
ADR-037 adds process-local source excerpt retention in `ai_agent.research_evidence`,
composed by `ai_provider.research_execution` for advisory local review. An optional
run-wide successful-final-URL maximum is checked by the HTTP fetcher before body
reads. Receipts and the configured maximum reuse existing stage metadata; source
text does not receive a new persistent store or reviewer retrieval tools.

Codex must ask before making material decisions involving new services, persistent storage, major dependencies, microservice extraction, public API/schema changes, provider policy, privacy/data routing, automatic external actions, autonomous AI optimization, or significant shared-interface changes.

## 12. Architecture change process
1. Describe current architecture.
2. Describe proposed change.
3. Explain why it is needed.
4. Identify meaningful alternatives.
5. Explain consequences.
6. Ask the user when the decision is material.
7. Record the accepted decision in `docs/decisions.md`.
