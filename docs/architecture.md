# Architecture

## 1. Overall direction
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

## 4.1 Authorization and approval policy
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

## 7. AI Council
The Council is an application on top of the AI infrastructure:
`user question → council router → multiple models → raw responses → synthesis → final answer`

Preserve raw responses so synthesis does not erase disagreement. Initial modes may be LOCAL, CLOUD, and HYBRID. The UI should make local vs external processing understandable.
Its implementation should allow ordinary provider connections and
orchestrator-guided routing without hard-coding Ollama, OpenAI, Requesty, or any
other provider into Council-specific business logic.

## 8. Job Search Automation
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
Codex must ask before making material decisions involving new services, persistent storage, major dependencies, microservice extraction, public API/schema changes, provider policy, privacy/data routing, automatic external actions, autonomous AI optimization, or significant shared-interface changes.

## 12. Architecture change process
1. Describe current architecture.
2. Describe proposed change.
3. Explain why it is needed.
4. Identify meaningful alternatives.
5. Explain consequences.
6. Ask the user when the decision is material.
7. Record the accepted decision in `docs/decisions.md`.
