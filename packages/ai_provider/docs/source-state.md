# Provider source state

**Checked:** 2026-10-13; Gemini individual-access retirement verified 2026-10-14.
Published limits and account observations can expire.

**Latest scoped update:** 2026-10-28, Modal/Qwen tool-calling prerequisites and
credit-only deployment admission; 2026-10-25, Go coding-agent requirements/limits rechecked
and OpenRouter credits/privacy and local CLI
payload tracing; 2026-10-24, OpenRouter free inventory and the declared
free route; capacity comparison below; OpenRouter limits/privacy, Codex
data-policy scope and the OpenRouter request-contract refresh were also checked
2026-10-21 and 2026-10-22.
This does not refresh every historical offer in the table below.

This is the shared reference for provider access findings, integration gaps and
evaluation limits. It is documentation, not a live quota registry or executable
routing configuration. The [model catalog](../../ai_orchestrator/examples/model_catalog.toml)
contains declared route capabilities; native readers report supported account
observations. Neither establishes coding quality by itself.

## Reading and refreshing provider knowledge

This file is the repository agent's first provider-knowledge entry point. Keep
reusable facts with their official source, checked date, provider/account/route
scope, evidence type and unresolved limitations. Distinguish published policy,
implementation behavior, live observation and inference. Refresh affected entries
when official information changes; preserve superseded findings as historical.
A date alone does not make a fact currently reliable: prices, model availability,
quota and entitlement need fresh admission evidence before execution. Unknown or
contradictory evidence remains explicit. Account balances, credentials, prompts
and private transcripts do not belong in this public reference.

### Modal runtime — deployment prerequisites checked 2026-10-28

[Qwen's function-calling guide](https://qwen.readthedocs.io/en/v2.5/framework/function_call.html)
and [vLLM's tool-calling reference](https://docs.vllm.ai/en/stable/features/tool_calling/)
require automatic tool choice and the Hermes parser for Qwen2.5 tool calls. The
deployment now supplies both flags; previous plain-chat probes did not exercise
that capability. A bounded synthetic coding pilot subsequently reached the live
endpoint but returned proposed tool calls as ordinary text, executing no tools
and leaving the seed unchanged. Tool-calling workflow acceptance remains missing;
this single configured task does not establish general model quality.

[Modal budgets](https://modal.com/docs/guide/budgets) distinguishes the usage
budget before credits from the net-spend limit after credits. A default spend
limit may permit out-of-pocket charges. Credit-only development must verify
remaining eligible credits and check the net-spend setting before deployment;
zero historical billed cost does not establish either. If the setting is unavailable,
record it as unknown and require the finite compute bound to fit verified eligible
credits with headroom; never assume an account cap exists. Account observations stay
in private runtime evidence. Runtime cost is compute time, not a per-token price.

[Modal Servers](https://modal.com/docs/guide/servers) do not queue requests during
zero-to-one scaling: the first request starts a container and receives HTTP503
until a replica is ready. Use an explicitly bounded readiness wait before the
task; this does not justify generic inference retries or a fallback-policy change.

The [Go guide](https://opencode.ai/v2/docs/console/go/) rechecked 2026-10-28
documents the Responses endpoint under `/inference/go/openai/v1/responses`.
The Responses subclass now uses that canonical default; caller-supplied endpoint
overrides remain supported. This correction is not a live compatibility result.

### OpenCode Go — rechecked 2026-10-25: bounded coding admission

The [official Go guide](https://opencode.ai/v2/docs/console/go/) still lists
Kimi K2.7 Code and requires typical coding-agent traffic, the client's own user
agent and a stable `x-opencode-session` conversation identifier. It lists a $60
Go monthly allowance for this model, with $0.95 input/$4 output/$0.19 cached-read
per million tokens; five-hour and weekly windows are 20% and 50% of the monthly
allowance. These published amounts are not current account headroom or token
budgets. Default workspace privacy blocks paid endpoints that train on request
data; actual route eligibility and saved settings still require scoped checks.

Fresh model-list and account-allowance metadata were checked before the bounded
October 25 coding/review trial and again afterward. Account observations remain
private runtime evidence. The completed small task supplies scoped workflow
evidence, not general model quality, independent quota pools or a spending grant.
No Extra Usage, purchase or billing-source change was enabled by this work.

### OpenRouter — refreshed 2026-10-25: credits, privacy and CLI payload

Owner requested investigation and accepts ordinary non-sensitive repository data
for now, conditional on excluding genuinely private material and API keys. This
does not authorize a purchase or establish that the current tool boundary meets
that condition. No authenticated settings change or inference was performed.

- [Pricing](https://openrouter.ai/pricing) still states 50 free requests/day,
  increasing to 1,000 after at least $10 of purchased credits, with 20/minute.
  Higher quota does not reserve upstream capacity; the prior shared-pool 429 is
  not repaired by a quota increase. The Standard credit fee is 5.5%; the official
  [fee announcement](https://openrouter.ai/blog/simplifying-our-platform-fee/)
  additionally gives a $0.80 minimum for non-crypto payments. A $10 credit top-up
  therefore suggests about $10.80 before applicable taxes; verify actual checkout
  and credited amount rather than treating this estimate as a purchase receipt.
- [Terms, section 4](https://openrouter.ai/terms) specify a $5 minimum purchase,
  possible unused-credit expiration after 365 days, unused-credit refunds only
  within 24 hours, non-refundable platform fees and no crypto refunds. Auto
  recharge is optional. No subscription or auto recharge is needed for this
  proposed manual top-up. Keep paid inference and paid fallback disabled.
- The Free/Standard data-policy-routing table versus all-plan ZDR FAQ conflict
  remains on the same pricing page. The [key schema](https://openrouter.ai/docs/api_reference/limits)
  defines `is_free_tier` as whether credits were purchased, not verified privacy
  entitlement. Buying credits changes that proxy, not downstream model terms.
- [Data collection](https://openrouter.ai/docs/guides/privacy/data-collection)
  distinguishes optional private input/output logging from optional product-use
  permission; both are documented off by default. Request metadata is retained,
  and sampled prompts undergo anonymous categorization using a ZDR model.
  Actual account opt-ins were not inspected. [Terms, section 6](https://openrouter.ai/terms)
  also grant service-operation rights and broader rights when logging is enabled;
  do not equate the default documentation with an account-setting observation.
- [Provider logging](https://openrouter.ai/docs/guides/privacy/provider-logging)
  separates OpenRouter's own handling from downstream provider training and
  retention. [ZDR guidance](https://openrouter.ai/docs/guides/features/zdr)
  explicitly says enforcing Google ZDR excludes AI Studio endpoints. Fresh public
  [route metadata](https://openrouter.ai/api/v1/models/google/gemma-4-31b-it:free/endpoints)
  still lists one zero-price endpoint, Google AI Studio, with 262,144 context.
  Inference: requiring ZDR would currently leave this particular route without
  an eligible endpoint; this is metadata reasoning, not a live inference result.
- Google's [API terms](https://ai.google.dev/gemini-api/terms) permit product/model
  improvement and human review for unpaid services, with a separate EEA/UK/Swiss
  exception applying paid data-use terms. Paid terms still allow limited abuse
  retention. These general terms alone do not establish which upstream account,
  region or special OpenRouter agreement covers this endpoint. Do not claim that
  OpenRouter credit purchase makes Google's upstream service paid, or that the
  owner's location alone resolves the gateway's data treatment.
- Local payload tracing found that `repo_context.load_prompt_context` includes
  root/nested AGENTS instructions, CURRENT_CONTEXT and selected files;
  coding-chat adds saved visible history/handoff/skills as applicable. Native
  tools append file reads and command outputs to later requests. Workspace
  location and action-category authorization do not block in-workspace `.env`
  reads or sanitize sensitive output. Shell execution inherits environment
  variables. `FallbackHistoryClient` may add prior visible history but removes
  provider-private continuation. Provider authentication belongs in the HTTP
  Authorization header, not model messages; there is no general content-secret
  filter at these composition boundaries.
- A dummy-only offline capture at
  `artifacts/openrouter-privacy-review-20261025/offline-observations.json`
  confirms synthetic `.env` content and a synthetic environment value printed
  by an authorized shell tool enter the next composed request. No provider was
  called, no real secret was read, and the temporary workspace was removed.
  Current OpenRouter entitlement refusal was neither exercised nor bypassed.
  This demonstrates a potential path, not evidence of historical exfiltration.

Subsequent owner-approved A implementation (ADR-069): one digest-bound reviewed
non-sensitive USER input without tools/context/history, separate from ADR-063's
public attestation. The first bounded synthetic live trial on 2026-10-25 passed
admission and verified exactly 253 task bytes on the wire, then returned HTTP 429
with `limit_source=upstream_provider_shared_pool` and the upstream rate-limit
signature. Its one inference POST and two metadata GETs are preserved under
`artifacts/unattended-20261025-0745/restricted-live-result.json`; no retry or paid
fallback occurred. Offline gates passed. Upstream capacity and model quality
remain separate from input-boundary acceptance.

Recommendation: do not buy credits as a substitute for the data boundary. First
prepare task-scoped, reviewed, credential-free inputs/environment and control
subsequent tool output/history. An isolated copy alone is not an OS sandbox when
arbitrary shell access remains. Broad tool access plus instructions or secret
pattern matching alone cannot guarantee exclusion. Implementing a changed
OpenRouter admission contract requires an explicit design under ADR-063.

### OpenRouter — checked 2026-10-21

- Published limits: the [limits reference](https://openrouter.ai/docs/api_reference/limits)
  defines free-model usage per UTC day and exposes the daily counter through
  `GET /api/v1/key`. Read the actual account counter; a published ceiling is not
  remaining quota, model capacity or execution authority.
- Published privacy: [provider logging](https://openrouter.ai/docs/guides/privacy/provider-logging)
  describes downstream policies and separate paid/free training controls. Training
  permission, prompt retention and zero-data-retention routing are distinct claims.
- Unresolved documentation conflict: [pricing](https://openrouter.ai/pricing)
  excludes Free-plan data-policy routing in its feature table, while its privacy
  FAQ says ZDR routing is available on every plan. Provider-logging guidance also
  describes per-request policy filtering. These statements do not establish which
  exact request filters are enforced for this Free account; do not assume parity.
- Historical blanket guard: Free-plan accounts with unverified privacy-filter
  entitlement were refused even for public inputs. The earlier end-of-day grant
  did not override this guard.
- Owner-approved exception, 2026-10-21 ([ADR-063](../../../docs/decisions/ADR-063-explicit-public-input-privacy-exception.md)):
  `PUBLIC_OR_LOW_RISK` plus literal `metadata["public_or_synthetic"] = True`
  attests the complete request is public/synthetic and approved for possible
  retention/training. Unattested/private inputs retain their gate. Every call
  still requires zero prices and valid remaining quota, and requests
  `data_collection=deny`. No automatic CLI classification or privacy guarantee.

### OpenRouter — refreshed 2026-10-22

Official pages re-read 2026-10-22. The 2026-10-21 findings above stand; the
Free-plan conflict is still open.

- **The Free-plan conflict is unchanged.** The [pricing feature table](https://openrouter.ai/pricing)
  lists "Data Policy-Based Routing" as **No** for Free and **Yes** from
  Standard upward, while the same page's privacy FAQ states that "Zero Data
  Retention routing is available on every plan". Both statements are current.
  The documentation still does not establish which request filters are enforced
  for this Free account, so the local guard remains a refusal, not evidence of
  provider denial.
- [Provider routing](https://openrouter.ai/docs/guides/routing/provider-selection)
  documents the `provider` request object. This repository sends
  `require_parameters: true`, `data_collection: "deny"` and `max_price` with
  `prompt`, `completion`, `request` and `image` all zero. Those are the
  documented field names, types and price attributes, and the request guards
  are already locked by offline regressions.
- The same page documents a **distinct** `provider.zdr` boolean that routes only
  to Zero-Data-Retention endpoints. It is not the same claim as
  `data_collection: "deny"`: `deny` excludes providers that store data
  non-transiently or may train on it, while `zdr` excludes any provider that
  retains data at all, even for abuse scanning or legal reasons. The
  [ZDR guide](https://openrouter.ai/docs/guides/features/zdr) states that a
  request-level `zdr` ORs with account and guardrail settings and can only
  add enforcement. This repository deliberately does not request `zdr`: the
  Free-plan data-policy entitlement is unresolved, and requiring ZDR could
  leave the free route with no eligible endpoint. Recorded departure, not a
  defect; changing it is a material privacy/routing decision.
- Upstream takes a conservative stance for endpoints whose policy it cannot
  establish: they are treated as retaining **and** training on data. A `deny`
  filter therefore excludes exactly those endpoints.
- `GET /api/v1/endpoints/zdr` publishes the current ZDR endpoint list, so ZDR
  eligibility can be checked without inference.
- The [limits reference](https://openrouter.ai/docs/api_reference/limits)
  confirms the `GET /api/v1/key` shape this repository reads: `is_free_tier`
  ("whether the user has paid for credits before") and
  `free_model_daily_requests.{used, limit, remaining}`. The daily `limit` tier
  is selected by all-time credits purchased **independently** of
  `is_free_tier`, and an account below the credit threshold reports
  `is_free_tier: false` together with the lower daily ceiling. `is_free_tier`
  is therefore a credits-purchased proxy, not a statement of data-policy
  entitlement; the local guard uses it only as evidence of a paying account.
- Free limits are unchanged: 20 requests/minute and 50/day, rising to
  1,000/day at $10 all-time credits. The per-minute limit is not reported by
  the key endpoint, and the daily counter does not apply to accounts or
  endpoints exempt from free-model limits.
- The [pricing page](https://openrouter.ai/pricing) now names
  `GET /api/v1/models?output_modalities=all` as the per-model price source
  ("no API key required") and publishes a per-model `llms.txt` guide.
- **Route availability, checked 2026-10-22.** The public endpoints API
  `GET /api/v1/models/{author}/{slug}/endpoints` reports, per provider
  endpoint, the provider name and tag, reported status, uptime over the last
  day/5m/30m, latency, throughput, quantization, service tier, context
  length, prices and supported parameters. It needs no key, so it is a
  first-party availability source rather than a scraped report. `ai_provider`
  reads it through `openrouter_endpoints.read_openrouter_endpoint_availability`.
  Observations so far:
  - `latency_last_30m` and `throughput_last_30m` were **null** in every
    response observed; they are not yet a usable latency signal.
  - `context_length` and `quantization` **differ per endpoint** for the same
    model (65,536 to 1,000,000 tokens; `bf16`, `fp16`, `fp8`, `fp4`, `nvfp4`,
    `unknown`). A route's real capability depends on which provider serves it,
    not on the model id.
  - `supported_parameters` differs per endpoint, and a provider may not
    support the tool-choice modes the CLI needs.
  - A `:free` variant lists the **free** endpoints only, and a free variant
    with no free provider currently serving it returns an **empty endpoint
    list**. That absence is actionable: the route cannot be used even though
    the model is still advertised. Dated free-route snapshot, 2026-10-22:
    `thinkingmachines/inkling-small:free` 1 provider (`nvfp4`, 1,048,576
    context, 100% uptime), `google/gemma-4-31b-it:free` 1 provider (262,144
    context, 99.79% uptime), `cohere/north-mini-code:free` 1 provider
    (256,000 context, 100% uptime), while `openai/gpt-oss-120b:free` and
    `qwen/qwen3.8-27b:free` advertised **no** endpoint.
  - **The free catalogue itself turns over, so an empty endpoint list is a
    reading, not a verdict.** Later the same day, about fifty minutes after
    the snapshot above, a full sweep found 17 free variants and all 17 had an
    advertised endpoint — but `openai/gpt-oss-120b:free` and
    `qwen/qwen3.8-27b:free` were **no longer in the public free catalogue**
    at all, while unrelated free models had appeared. The count staying at 17
    hides a change of membership. Checked that this is not a rate-limit
    artefact: repeated reads of those two ids returned an empty list both with
    and without delays, and the models were absent from `GET /api/v1/models`.
    Consequence: route availability must be re-read before it is relied on,
    and never cached as a property of a route.
  - Availability is a source-reported observation, not a quality judgment, and
    not acceptance evidence for this repository.

### OpenRouter — refreshed 2026-10-24

The 2026-10-21 and 2026-10-22 findings above stand, including the unresolved
Free-plan privacy-filter conflict. This entry records the free inventory and the
one route this repository now declares; it does not resolve that conflict.

- **Public free inventory, read 2026-10-24.** `GET /api/v1/models` returned 469
  models, of which 17 are `:free` variants. Sixteen advertise `tools` **and**
  report zero `prompt`/`completion` price. The one exclusion,
  `nvidia/nemotron-3.5-content-safety:free`, lists no `tools` and is therefore
  not a candidate for a tool-using CLI route.
- **Turnover continues.** `openai/gpt-oss-120b:free` and `qwen/qwen3.8-27b:free`
  are still absent from the public catalogue, while `google/gemma-4-31b-it:free`
  and `cohere/north-mini-code:free` remain. The count coinciding with the
  2026-10-22 total again hides a different membership, which confirms the earlier
  rule: re-read availability, never cache it as a route property.
- **Chosen route: `google/gemma-4-31b-it:free`.** It reports 262,144 context and
  `tools` support. Its `:free` endpoint list contained exactly one provider on
  2026-10-24 — Google AI Studio, `google-ai-studio`, status 0, 262,144 context,
  `unknown` quantization, zero prompt/completion price, `tools` supported. A
  single free endpoint is a concentration risk, not a quality claim: the route
  cannot be served if that provider stops serving the free variant.
- The paid slug `google/gemma-4-31b-it` listed 15 endpoints at non-zero prices
  (about $0.10–$1.09 per million tokens). The adapter reads the `:free` entry in
  the full model list and refuses on any non-zero price, so the paid endpoints
  cannot be reached through this route; `data_collection=deny`, zero `max_price`
  and `require_parameters` stay in the request.
- **Live admission probe, 2026-10-24.** A synthetic request with the explicit
  `public_or_synthetic` attestation (ADR-063) passed every adapter guard: the
  model list entry was exactly one match at zero price with `tools`, and
  `GET /key` reported `is_free_tier: true` with
  `free_model_daily_requests = {used: 0, limit: 50, remaining: 50}`. The
  `:free` endpoint list still showed one provider (Google AI Studio, status 0,
  100% 30-minute uptime, zero price). The POST then returned **HTTP 429** with
  upstream metadata: `"google/gemma-4-31b-it:free is temporarily rate-limited
  upstream"`, `provider_error_code: 429`,
  `limit_source: upstream_provider_shared_pool`, with remedy hints to retry,
  add a BYOK provider key, or route to another provider. Account quota was
  untouched, so this is an upstream shared-pool limit, not exhausted allowance.
  The adapter maps 429 to `RATE_LIMIT`, which a fallback walk already treats as
  a continuation signal.
- **Unattested CLI use is refused on this account.** `is_free_tier: true` means
  no credits have ever been purchased, so an ordinary CLI request without an
  attestation is rejected by the entitlement guard before inference. The CLI has
  no public/synthetic attestation flag, so this route cannot serve ordinary CLI
  work until the entitlement question is decided; it is declared and testable
  but not ordered in the local fallback priority.
- No leaderboard row measures the `:free` serving variant, so the route stays
  `unmatched` in
  [route-upstream-family-mapping.md](route-upstream-family-mapping.md) and
  carries no inherited Gemma prior. Quality is provisional and unmeasured.
- Free-plan quota, per-minute limits and the privacy-filter conflict are
  unchanged; the adapter still re-reads `/key` before every call and refuses
  without an attested public/synthetic payload when entitlement is unverified.

### Codex and cross-provider privacy — checked 2026-10-21

[Codex authentication documentation](https://learn.chatgpt.com/docs/auth) distinguishes
ChatGPT workspace policies from API-organization retention/data-sharing settings.
Do not infer an individual's effective controls from a product name or subscription
alone. This repository has not inspected the owner's account data controls.
Using an external model means selected input is sent outside the workstation;
it does not establish public disclosure, training permission or equivalent handling
by every other processor. Evaluate the task data and each additional recipient.

## Sources and readiness

### Capacity comparison — checked 2026-10-22

Published offers, not account entitlement or measured coding quality:

- [Codex pricing](https://learn.chatgpt.com/docs/pricing) lists Plus at $20/month
  and Pro tiers at $100/$200/$500. Plus/Pro can purchase additional credits;
  the account offer determines purchase price. API-key billing is separate.
  Current documentation says Pro has no five-hour limit; weekly limits may apply.
  Do not reuse older 5x/20x marketing or assume an upgrade is currently available
  from a listed tier. Current account usage/reset and checkout terms must decide.
- [Copilot plans](https://github.com/features/copilot/plans) list Pro $10/month
  with $15 included AI-credit value, Pro+ $39 with $70, and Max $100 with $200.
  Totals include variable flex allotments. CLI consumes these credits;
  [model pricing](https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing)
  meters input/output/cache tokens, including model-dependent cache writes.
  Historic premium-request counts do not describe a new monthly subscription.
  The published [trial pause](https://github.blog/changelog/2026-04-10-pausing-new-github-copilot-pro-trials/)
  remains accessible; current trial eligibility is not established.
- [OpenRouter pricing](https://openrouter.ai/pricing) confirms free models at
  20 requests/minute and 50/day, increasing to 1,000/day after $10 lifetime credits
  purchased. Standard credit purchases carry a 5.5% platform fee. Standard lists
  data-policy routing; Free does not. The limits page's extracted table omits
  numeric substitutions; its account counter and pricing FAQ are clearer here.
  This buys capacity, not proven strong-agent quality or private-input permission.
- [Kiro pricing](https://kiro.dev/pricing/) advertises $20 subscription credit
  on a first eligible paid upgrade using social login/Builder ID. Pro is $20/month
  with 1,000 credits and premium models; Free has 50. Eligibility and regional model
  availability need verification. Credits are not equivalent to requests or another
  service's credits. No subscription or add-on billing was enabled.
- [Antigravity plans](https://antigravity.google/docs/plans/) retain weekly free
  capacity and higher paid limits; no numeric usable account allowance was established.
  Existing unresolved shared-tool permission mapping remains a baseline constraint.
- [Zed](https://zed.dev/pricing) offers $5/14 days without a card, shared with Delta,
  GPT-6 Luna only. [Cerebras](https://inference-docs.cerebras.ai/support/rate-limits)
  offers $5/30 days after card verification, with no recurring free tier.
  Neither establishes a ready strong route through this CLI.
- [OpenCode Console](https://opencode.ai/v2/docs/console/models/) currently lists
  limited-time free models including GLM-5.3-Flash and DeepSeek V4.1 Flash, with
  model-specific zero-retention/no-training statements. Other free models permit
  improvement/training. Numeric usable quota, no-deposit entitlement, integration
  and baseline quality remain unverified; signup is not authorized.
- [Claude pricing](https://claude.com/pricing) lists Claude Code in $20/month Pro
  and Max from $100. It is another paid candidate, without a verified general free
  CLI trial or an accepted integration here. New processing/integration needs approval.

Technical recommendation, not an owner decision: compare a capped top-up on the
existing Codex route first for immediate baseline continuity. For recurring use,
compare Copilot's token budget and Kiro's eligible first-upgrade offer with the
actual Codex checkout. Avoid buying OpenRouter solely to obtain a strong coding
replacement: free-model quality remains unestablished. Free trials may support
small future evaluations but do not yet replace this baseline route. Preserve
required instructions/tests/history rather than shrinking the task to fit an offer.
Private observations and purchase decisions remain in local artifacts/handoff.

### Follow-up: OpenCode Go, Claude and official agent SDKs — 2026-10-22

This supplements the comparison above; recommendations remain unapproved.
OpenCode Go was previously omitted from its paid shortlist, while Antigravity
and Claude received too little assessment. No install/account/inference ran.

- [OpenCode Go](https://opencode.ai/v2/docs/console/go/): $10/month; Plus $40.
  Model-dependent allowance; five-hour/weekly caps are 20%/50% of monthly limits.
  Example Go monthly limits: Kimi K2.7 Code $60, Kimi K3 $15. These are priced-use
  allowances, not cash credits or proven completed tasks. Supports other coding
  agents, requiring client identification/session headers. No need to replace our
  whole CLI. Privacy varies by model, including training-permitted Contributor
  routes; extra usage can spend a separate balance. Keep it disabled unless approved.
- [Claude Pro](https://claude.com/pricing): $20 monthly includes Claude Code.
  [Plan access](https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan)
  shares five-hour/weekly limits with Claude; API-key authentication can select
  separate API billing. [Agent SDK policy](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan)
  currently permits subscription-limit use of the SDK and headless client.
  This repository has no accepted Claude executor/permission mapping yet.
- [Antigravity](https://www.antigravity.google/docs/plans): free weekly quota and
  paid higher baseline quotas; paid credit overages are separately configurable.
  The local binary exists, but our shared executor explicitly refuses absent MCP
  grants. [Permissions](https://www.antigravity.google/docs/permissions/) document
  narrow MCP rules; this is a concrete integration gap to investigate, not proof
  the service is unsuitable or out of quota. Windows differs from other platforms.
- [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk): stable Python package
  openai-codex controls local app-server through JSON-RPC, with a pinned runtime;
  supports explicit executable selection. [App Server](https://learn.chatgpt.com/docs/app-server)
  is the official integration surface for conversations, approvals and streamed
  events. This is distinct from the general OpenAI model API SDK.
- [Copilot SDK](https://github.com/github/copilot-sdk) also controls the local
  runtime through JSON-RPC. [Compatibility](https://docs.github.com/en/copilot/how-tos/copilot-sdk/troubleshooting/compatibility)
  includes sessions, abort, custom tools, MCP and permission/event hooks.
  The [Python README](https://github.com/github/copilot-sdk/blob/main/python/README.md)
  documents runtime downloads and an experimental in-process transport. Prefer
  an explicitly selected child-process transport for any initial assessment;
  an in-process runtime changes isolation and cannot honor per-client cwd/env.

Engineering assessment: SDK adapters may reduce hand-maintained event parsing and
improve session/approval integration. They do not fix model quality or increase
subscription allowance. Compare retained CLI adapters (no migration, existing
evidence) with optional SDK-backed executors (richer control, new dependencies,
version/runtime/lifecycle and permission verification). Recommend a focused offline
contract assessment against existing neutral execution contracts, before choosing
adoption. Keep provider details below applications/Orchestrator, retain shared-tool
guards and owned cleanup, and avoid replacing the existing provider-neutral agent
loop with one vendor's SDK. No architecture/dependency/default change is approved.

Capacity recommendation is now broader: inspect existing Antigravity capacity and
narrow mapping first for a zero-purchase option; Go is a serious low-cost paid
candidate, Claude Pro a separate native-agent candidate. Codex top-up remains the
least-change immediate continuation when checkout terms are acceptable. Quality,
privacy, exact model and account admission still require independent verification.

### OpenCode Go model starting points — checked 2026-10-22

Recommendations are provisional engineering choices, not measured model parity.
For manual IDE-assisted development, start with Kimi K2.7 Code. It can perform
implementation and separate frozen review without manual model switching; retain
GLM-5.2 as an alternative and GLM-5.3 as an optional different-model reviewer for
later automated selection. The [recommendation catalog](model-catalog.md) records
roles and evidence limits. Their published Go monthly
priced-use limits are $60/$60/$15 respectively, with five-hour/weekly caps still
applying. The [Go model/limits/privacy table](https://opencode.ai/v2/docs/console/go/)
lists no-training/zero-day retention for these routes; this is a published policy,
not an independent audit. Contributor routes can permit training and are not
recommended for this repository's private context. Keep optional paid extra usage
separate from the subscription. Reassess choices from actual task results, not
marketing estimates of requests or automatic switching to a newer model.

An IDE agent using Go is distinct from ai_provider support. A configured key does
not add a ProviderKind, executor, quota reader, or approved automatic fallback.
Manual success does not establish our CLI's acceptance or agent quality parity.
Future automation should reuse neutral route selection and the existing approval,
privacy, cost and process-ownership contracts, after explicit integration decisions.

Temporary Go follow-up, checked 2026-10-22: the [official offer](https://opencode.ai/v2/docs/console/go/)
advertises LongCat 2.5 Preview Free, MiniMax M3.1 Flash Free and Beam Free as
temporarily free/unlimited. Exact IDs, route-specific retention and evaluation
status are in [the model catalog](model-catalog.md#opencode-go-temporary-free-candidates).
This does not change the current Kimi preference or authorize switching/inference.

### OpenCode Go quota and free-model limits — refreshed 2026-10-23

Official-guide recheck for the next bounded CLI review (2026-10-23):
[Go](https://opencode.ai/v2/docs/console/go/) still lists `kimi-k2.7-code` at
`https://opencode.ai/inference/go/openai/v1/chat/completions`, with no training
and zero-day retention. It requires a stable conversation/session header and a
client-specific User-Agent. Its **Usage beyond limits** section says enabling
Extra Usage permits subscription-limit overflow to Console pay-as-you-go credits.
An allowance-only acceptance must therefore confirm Extra Usage is disabled;
route identity or client-side call limits alone cannot establish that account
setting. This was a public-document recheck, not an account observation or
inference grant. The usage-endpoint findings below retain their original scope.

Live observation from this account, plus public-source cross-check:

- **Go subscription allowance can be read with the inference key.**
  `GET https://opencode.ai/zen/go/v1/usage` with `Authorization: Bearer <OPENCODE_API_KEY>`
  returns rolling (5-hour), weekly and monthly percentages plus reset timestamps.
  This contradicts the 2026-10-22 note that no Go-key allowance endpoint existed.
  The endpoint is not documented in the public Console API pages as of 2026-10-23.

- **Zen free models are not covered by the Go subscription.** Models such as
  `opencode/deepseek-v4.1-flash-free` and `opencode/mimo-v2.6-flash-free` are
  Console/Zen limited-time free routes with their own daily cap. Public docs used
  to cite ~200 requests/day, but the number was removed from the Go page around
  2026-10-22 and is now enforced server-side without exposing remaining quota or
  reset time via the API. They can therefore return “free usage limit reached”
  while the Go subscription still has headroom.

- **There is no reliable API for Zen free-model remaining quota or reset time.**
  OpenCode states the free limit is dynamic and changes with capacity, so they
  do not publish a fixed number. The console web UI shows current usage/reset,
  but no authenticated API endpoint returns the daily free allowance. A 429
  response *sometimes* carries a `Retry-After` header (observed pointing to the
  next 00:00 UTC), but this is not guaranteed and does not expose remaining quota.
  Clients cannot reliably predict when a Zen free route will unblock.

- **Go free models are provider-wide-locked when any Go cap is hit.** Public bug
  reports (#49014, #51682) confirm that exhausting the 5-hour/weekly/monthly cap
  on one Go model blocks the entire `opencode-go` provider, including the
  temporary free models, until that window resets. The Go page says "you can
  continue using the free models," but enforcement appears to treat all Go routes
  as sharing the same lock.

Practical implication for this repository: reliable unattended/attended CLI work
should route through Go paid-included models (e.g., `opencode-go/go-kimi-k2.7-code`)
when Go is the chosen source, not through `opencode/...-free` Zen routes. Zen free
routes are acceptable only for optional, interruptible trials with a fallback plan.

### OpenCode automatic information discovery — checked 2026-10-22

The [Console API overview](https://opencode.ai/v2/docs/console/api/) documents
model listing and scoped Usage Read permissions. Its
[Budgets API](https://opencode.ai/v2/docs/console/api/budgets) lists member monthly
monetary budgets, spend and resets; it can expose personal identities and requires
the applicable key permissions. This is not evidence that the owner's Go key can
read Go subscription-window remaining quota. The Go guide documents model listing;
verify each endpoint/account scope before claiming automatic allowance support.
Do not substitute workspace budgets or advertised limits for Go remaining usage.

Implementation status in `ai_provider`:

- ``OpenCodeGoChatClient`` connects to ``https://opencode.ai/inference/go/openai/v1``
  using OpenAI-compatible Chat Completions, with project User-Agent and optional
  per-request ``x-opencode-session`` from ``request.metadata["opencode_session"]``.
- ``OpenCodeGoResponsesClient`` extends the generic ``OpenAIResponsesChatClient``
  base for Go's Responses endpoint at ``https://opencode.ai/inference/go/v1/responses``.
- ``OpenCodeGoMessagesClient`` extends the generic ``AnthropicMessagesChatClient``
  base for Go's Messages endpoint at ``https://opencode.ai/inference/go/v1/messages``.
- ``create_chat_client`` routes OpenCode Go models by protocol:
  ``responses`` → ``OpenCodeGoResponsesClient``, ``messages`` →
  ``OpenCodeGoMessagesClient``, otherwise ``OpenCodeGoChatClient``.
- ``OpenCodeGoSourceInfo`` lists models from ``GET /inference/go/v1/models`` and
  normalizes capabilities/prices defensively. Each inventory item now records the
  model's ``protocol`` (``chat``/``responses``/``messages``),
  ``trains_on_request_data``, and ``requires_global_regions`` flags.
- Account allowance is read from ``GET /zen/go/v1/usage`` (see the refreshed quota
  section above). ``OpenCodeGoSourceInfo.account_allowance`` calls that endpoint with
  the Go inference key and normalizes the rolling/weekly/monthly percentages plus
  their reset timestamps; ``read_opencode_go_allowance`` additionally reports the
  binding window and the published per-model monthly caps under ``model_limits_usd``.
  The endpoint is reachable but is not listed on the public Console API pages, so it
  is treated as an observed endpoint rather than a documented contract. Two facts
  must stay separate: the endpoint reports **account-wide percentages only** (it does
  not decompose usage by model), while the per-model dollar caps are documented
  sub-limits, not observations. Hitting any account window blocks the entire
  ``opencode-go`` provider, including its free models, until that window resets.
- ``ProviderKind.OPENCODE_GO`` and ``BillingSource.OPENCODE_GO_SUBSCRIPTION_ALLOWANCE``
  wire Go into config, factory and the existing account-usage dispatcher.

Official documented Go endpoints (re-fetched 2026-10-22 from the
[Go guide](https://opencode.ai/v2/docs/console/go/)): Chat Completions
`https://opencode.ai/inference/go/openai/v1/chat/completions`, Responses
`https://opencode.ai/inference/go/openai/v1/responses`, Messages
`https://opencode.ai/inference/go/anthropic/v1/messages`, and Gemini
`https://opencode.ai/inference/go/google/v1beta/models/<model>`, with the live model
list at `GET https://opencode.ai/inference/go/v1/models`. The Chat path matches the
implementation exactly. The implemented Responses/Messages bases
(`/inference/go/v1/responses`, `/inference/go/v1/messages`) are shorter than the
documented `/go/openai/v1/responses` and `/go/anthropic/v1/messages` forms, but both
were live-confirmed working on 2026-10-22 (see the probe below), so this is a recorded
working divergence, not a defect. See the
[conformance plan](../../../docs/documentation-conformance-plan.md) for the full
finding.

### Live probe observations — 2026-10-22

``GET /inference/go/v1/models`` returned **36** model ids. The endpoint does **not**
return capabilities, context-window or prices. The live list differs from the
published docs: `longcat-2.5-preview-free` is absent; `grok-4.6`, `glm-5.1`,
`kimi-k2.6`, `qwen3.6-plus`, `qwen3.7-max`, `minimax-m2.5`, `minimax-m2.7`,
`omen-alpha` are present.

A minimal public/synthetic probe (`max_output_tokens=8`) across all 36 models
produced **23 ok / 13 error**. Raw results are preserved at
`docs/artifacts/go-all-model-probe-20261022.json`.

**Follow-up probe:** the owner toggled Console Privacy settings for Global
regions and "paid endpoints that train on request data", and the new
Responses/Messages adapters were activated. With `max_output_tokens=16` (needed
because GPT Luna rejects values below 16), the rerun produced **33 ok / 3 error**.
Raw results are preserved at
`docs/artifacts/go-all-model-probe-20261022-rerun.json`.

Models unblocked by protocol routing and privacy toggles:
- **Responses:** `deepseek-v4.1-flash`, `deepseek-v4-pro`, `grok-4.6`, `grok-4.7`,
  `gpt-5.6-luna`, `gpt-6-luna`, `muse-spark-1.2-contributor`,
  `muse-spark-1.3-contributor`.
- **Messages:** `claude-haiku-5-5`, `minimax-m2.7`.

Still failing after toggles:
- `mimo-v2.5-pro`: upstream/router still reports unsupported model ID.
- `gemini-4-argon-contributor`: returns "Model does not support this protocol"
  on Chat, Responses and Messages endpoints.
- `longcat-2.0`: `402` endpoint unavailable.

### Error classification for failing models

| Model | Error | Meaning | Fix type |
| --- | --- | --- | --- |
| `deepseek-v4.1-flash`, `deepseek-v4-pro` | `400` "requires Global regions. Select Global in your workspace's Privacy settings" | Model is routed through Global regions; workspace privacy setting blocks it. | Account setting: Settings → Privacy → Global regions. Public reports: anomalyco/opencode #50155, #49184, #58044. |
| `grok-4.6`, `grok-4.7`, `gpt-5.6-luna`, `gpt-6-luna` | `400` "Model does not support this protocol" | These models are served from `/zen/go/v1/responses` (OpenAI Responses protocol), not `/v1/chat/completions`. | Code: add Responses-protocol adapter or route these model IDs to the responses endpoint. |
| `claude-haiku-5-5`, `minimax-m2.7` | `400` "Model does not support this protocol" | These models are served from `/zen/go/v1/messages` (Anthropic Messages protocol), not `/v1/chat/completions`. | Code: add Messages-protocol adapter or route these model IDs to the messages endpoint. |
| `muse-spark-1.2-contributor`, `muse-spark-1.3-contributor`, `gemini-4-argon-contributor` | `400` "trains on request data. Allow paid endpoints that train on request data in your workspace's Privacy settings" | Contributor models trade discounted pricing for training rights; explicit opt-in required. They also appear to map to `/v1/responses`. | Account setting: Settings → Privacy → "Allow paid endpoints that train on request data". Public reports: anomalyco/opencode #50016, #47562. |
| `mimo-v2.5-pro` | `400` "Unsupported model mimo-v2.5-pro" | Upstream/router does not recognize this model ID right now. Likely a transient Console Go routing issue; MiMo models have a history of upstream provider changes. | Wait/retry or use `mimo-v2.5` / `mimo-v2.6-pro`. Public reports: anomalyco/opencode #45990, #45291, #43481. |
| `longcat-2.0` | `402` "Endpoint is unavailable" | Either the model is temporarily down or the subscription cap/balance does not cover it. | Check Console usage/caps; retry later. Public reports: anomalyco/opencode #42750, #42757, #27964. |

- **Models that ignore `max_output_tokens`**: `qwen3.6-plus`, `qwen3.7-max`,
  `qwen3.7-plus`, and `grok-4.6` returned far more output tokens than requested
  even at `max_output_tokens=16`. Treat these as non-compliant for cost budgeting
  until the behavior is confirmed fixed.
- **GPT Luna requires `max_output_tokens >= 16`**; values below 16 return
  `invalid_request_error`.
- Several models inject additional context tokens (`minimax-m3` 182 input tokens,
  `minimax-m3.1-flash-free` 208, `beam-free` 52, `omen-alpha` 64, `kimi-k3` 94),
  so per-request token estimates should not assume only the caller's prompt
  counts toward the cap.
- **Free models observed today:** `beam-free`, `minimax-m3.1-flash-free`.
  `longcat-2.5-preview-free` was not returned by the listing endpoint and
  `longcat-2.0` failed the access probe.

Use the probe only with explicit bounds; the qwen models in particular can
consume far more tokens than requested.

### Investigating a route-specific failure

When a provider issue is identified, investigate whether it is isolated to the
selected model, upstream endpoint, account/quota or gateway before describing the
whole source as unavailable. For a gateway such as OpenRouter, model availability
can differ by upstream provider even with the same gateway key and daily quota.
Check current official metadata/status, safely retained diagnostics and dated
public evidence first. Compare other models on the same upstream and eligible
models on another upstream when that can distinguish the failure boundary.

Any live comparison must remain within an explicitly authorized bounded scope:
one simple public/synthetic request per selected route, fresh quota/price/privacy
checks, no implicit retries, paid fallback, credential reuse, new service or
private-context admission. Preserve attempt caps, actual completions, provider
identity when safely known, usage/cost, observation times and cleanup. A failed
route does not prove all models on its gateway failed; a working alternative does
not establish the original route's cause or coding quality. Keep unknown causes
unknown and do not turn diagnostic findings into automatic routing/default changes.

Before interpreting model-quality failures, compare the exact hosted route's
documented message/tool/reasoning contract and generation settings with the actual
adapter path. Record settings as matched, unmatched or unknown; model-name parity
is not settings parity. Distinguish first-pass authored correctness, iterative
test/repair behavior, permission/freeze safety and ordinary software correctness.
Provider continuation, when required, belongs in origin-bound transient adapter
state under ADR-055 rather than durable reasoning logs. A larger context/call cap
or successful connection does not prove better quality or fix a stalled task.

| Source | Access and published offer | Current integration / limits |
| --- | --- | --- |
| Antigravity | Official Google agent client; Free allowance refreshes weekly, with capacity/work-based limits | Model discovery connected successfully. Remaining quota and selected-model entitlement unknown. Shared MCP permission mapping unresolved. Automatic quota-reader startup isolation is unproved; this does not invalidate the separate connection check. |
| Requesty | Existing API adapter; advertised 200 free-model requests/day without a card | Exact approved Gemma route passed live zero input/output/cache/tier-price validation. Free daily remaining unknown. Prepaid balance does not measure free allowance. Route quality remains provisional standard. Paid routes remain supported under explicit cost policy. |
| OpenRouter | API gateway; advertised 50 free requests/day, rising to 1,000 after adding $10 credits; 20 requests/minute | Owner selected next-source priority on 2026-10-14. Experimental opt-in free-only adapter implemented offline: distinct key/provenance, exact zero prices/tool support/daily remaining checks each call, zero price caps and data_collection=deny. Key/account readiness and live quality unverified; example Qwen free endpoint listing was empty. Credit purchase deferred; no paid fallback. Updated 2026-10-24: `google/gemma-4-31b-it:free` (262,144 context, tools, one free endpoint) is now a declared default-catalog route; the adapter guards are unchanged and live quality is still unmeasured. |
| Gemini CLI | Individual free/Pro/Ultra access retired on 2026-06-18 | Owner sign-in failed with the matching retirement error; official announcement verified 2026-10-14. Offline adapter/MCP evidence is preserved, but the individual free route refuses even with cached auth. Approved pilot never started. Enterprise/API access remains a separate, unapproved route; no Antigravity substitution. |
| Groq | Free API with per-model request and token limits | Full coding-session use recommended for deferral; smaller tasks remain candidates. No adapter or account acceptance established. See quantitative comparison below. |
| Cerebras | $5 trial after verified payment method, expires after 30 days; no recurring free tier | Deferred as an emergency/promotion candidate. Revisit for distinctive capability or cost; no account/integration activation. |
| OpenCode Console | Optional model gateway usable with other coding agents; limited-time free models coexist with paid models | Deferred. Guaranteed no-deposit access and numeric daily capacity not established. Model-specific privacy and automatic reload settings require assessment. OpenCode's agent client is separate from this gateway. |
| Zed / Delta | 14-day trial, $5 shared balance, GPT-6 Luna only, no card required | Deferred emergency/promotion candidate. Trial access through these clients does not establish access through this application's CLI. |
| Copilot / Kiro | Existing official-client adapters with account allowances | Check readiness and allowance locally. Supported integration does not guarantee current account capacity. |

Private account observations and diagnostic receipts stay in local artifacts and
the immediate handoff, not in a public package inventory. Unknown metadata must
remain unknown; authentication, model listing and zero prices do not prove usable
quota or successful inference.

## OpenRouter privacy contract

OpenRouter privacy contract remains unresolved for a Free-plan account: its
[pricing table](https://openrouter.ai/pricing/) excludes data-policy routing,
while routing/provider-logging documentation describes filters without that
qualification. Historically the experimental client refused Free/unknown-tier key
metadata before inference. ADR-063 now permits the explicit public/synthetic-input
exception described above; unattested/private inputs retain that refusal. Earlier
successful mocks represented an already non-free-tier account calling only
zero-priced models; they did not establish free-account entitlement. No deposit
or additional policy weakening follows from this observation.

Re-confirmed 2026-10-22 against the current pricing page; see the dated refresh
above. Upstream treats an endpoint whose policy it cannot establish as
retaining **and** training, and its separate `zdr` filter is stronger than the
`data_collection=deny` this adapter requests.

Current official public free-model metadata (2026-10-14) lists alternatives such
as `google/gemma-4-31b-it:free`, `thinkingmachines/inkling-small:free` and
`cohere/north-mini-code:free` with zero advertised prices and tools. The older
Qwen example is absent and explicitly historical. Current site/API observations
supersede older local catalog/research assertions about availability; they do not
establish coding quality or privacy-filter enforcement. The local Free-tier guard
is an engineering refusal, not evidence of OpenRouter denying all Free access.
[Current public free catalog](https://openrouter.ai/api/v1/models?q=free).

## Groq token limits and coding-workflow fit

The published free table currently lists `openai/gpt-oss-120b`,
`openai/gpt-oss-20b` and `qwen/qwen3.8-27b` at:

| Limit | Published value |
| --- | --- |
| Requests/minute | 30 |
| Requests/day | 1,000 |
| Tokens/minute | 8,000 |
| Tokens/day | 200,000 |

Actual organization limits can differ. Cached tokens are excluded from rate
limits, but a different provider cannot reuse another provider's cache. These are
throughput quotas, **not** an 8,000-token model context window. Model context and
request admission must be assessed separately.

A bounded CLI review recorded 210,777 accumulated input tokens, including 175,232
cached tokens, and 874 output tokens across tool/model rounds. A cold arithmetic
equivalent is 211,651 / 8,000 = 26.46 minutes of throughput and exceeds the stated
daily token budget. Hypothetical identical cache hits reduce the arithmetic to
36,419 / 8,000 = 4.55 minutes. These are illustrative comparisons, not measured
Groq latency, a single request's size, or representative daily workload. Tokenizers
and templates differ; a large individual request may be refused rather than queued.

Do not reduce required instructions, original tests or conversation history to
make a route fit. Prefer evaluating Groq on naturally small subsidiary tasks;
full-session eligibility needs actual account limits and accepted quality evidence.

## Data ownership and orchestration

- `ai_provider` owns provider-specific collection and normalization: units,
  model/account scope, source, observation time, reset information when known,
  native estimates, errors and cleanup evidence.
- `ai_orchestrator` owns eligibility, selection and fallback policy. Applications
  may pass neutral observed facts alongside declared catalog capabilities. The
  orchestrator must not call provider APIs or depend on `ai_provider` to read them.
- Keep published plan limits, observed remaining quota, model context capacity,
  pricing and evaluated quality separate. A daily request limit is not a daily
  count of completed coding tasks; one task can make many model calls.
- Existing automatic observers cover supported Codex/Copilot account metadata
  and pinned Kiro estimates. This document adds no quota-aware routing or shared
  machine-readable rate-limit schema. A later executable contract needs explicit
  freshness/unknown-state semantics and tests before it influences routing.

Sharing facts does not require duplicated provider tables or a mandatory package
dependency. Both package READMEs link here. See ADR-021, ADR-050 and ADR-057.

## Full external agents

An API gateway supplies models; a full agent also owns a model/tool loop, native
instructions and possibly sessions or permissions. Our existing external-client
executors already integrate full agents through a different execution path from
the project's own provider-driven loop.

Compatible agents can use the CLI-owned shared MCP tools, approval scopes,
process supervisor, saved conversation and fallback handoff. They do not need to
bypass all CLI functionality. Their own model/tool loop replaces the internal
loop, so native prompts, tools, history and permissions need explicit mapping.
Unrestricted native tools can bypass shared receipts and permission controls;
that mode is not evidence of equivalent safety or continuity. Unsupported mapping
must refuse or report its limitation, not silently downgrade the contract.

## Primary references

2026-10-15 access-check follow-up: OpenRouter's official limit schema defines free
requests per UTC day. Requesty's free-model documentation confirms a daily
organization-wide limit but does not specify the reset timezone; the inspected
catalog response supplied no numeric reset/quota headers. Do not schedule its
pre-reset allowance use from an inferred midnight. See
[reusable access-check requirements](../../../docs/repo-assistant/provider-access-checks.md).
Allowance-consuming probes belong in a separate explicit live command, outside
pytest and Git hooks; deterministic receipt/selection tests remain mocked.

Current [Requesty terms](https://www.requesty.ai/terms) distinguish free-account
Training Permitted Models from paid-account protections. Historical catalog
no-training observations are not a blanket guarantee for current free routes;
recheck exact model/account treatment before admitting private workloads. This
follow-up admits no new private context or billing source.

Checked 2026-10-13; verify again before choosing or activating a source.

- [Antigravity plans](https://antigravity.google/docs/plans/)
- [Requesty free models](https://www.requesty.ai/free-models)
- [OpenRouter free access and limits](https://openrouter.ai/blog/tutorials/how-to-get-the-lowest-cost-llm-inference-on-openrouter/)
- [Gemini CLI quotas](https://geminicli.com/docs/resources/quota-and-pricing/)
- [Groq rate limits](https://console.groq.com/docs/rate-limits)
- [Cerebras trial limits](https://inference-docs.cerebras.ai/support/rate-limits)
- [OpenCode Console models, privacy and billing](https://opencode.ai/v2/docs/console/models/)
- [Zed trial](https://zed.dev/pricing)

Retirement source: [official Gemini CLI announcement](https://github.com/google-gemini/gemini-cli/discussions/28017). The previous 1,000-request individual offer is historical and must not be used for current routing.

### Kimi tool continuation and output allowance - verified 2026-10-23

The [official Kimi thinking-model guide](https://platform.kimi.ai/docs/guide/use-thinking-models)
specifies preserved `reasoning_content` for K2.7 Code tool loops, recommends
`max_tokens >= 16000`, and says reasoning and visible answer share that budget.
Thinking cannot be disabled for this model; omit `temperature`. The
[Go guide](https://opencode.ai/v2/docs/console/go/) lists the same model on its
OpenAI-compatible endpoint. Gateway-specific enforcement remains unverified.

The Go adapter now carries this field through ADR-055's transient origin-bound
continuation contract for exactly `kimi-k2.7-code`, including streamed fragments.
Raw metadata excludes reasoning fields. That protocol repair implied no reasoning
persistence, model switch, budget increase or inference authorization. Saved-session
restart still restores visible conversation, not private continuation state.
Do not classify an output-limited empty answer as model-quality acceptance or
silently reinterpret reasoning as delivered answer text.


Owner follow-up (2026-10-23): selected the automatic 16000-token default for
native coding on exactly opencode_go / kimi-k2.7-code. It is set before context
admission; explicit request budgets still win and other models retain their
existing defaults. Context insufficiency refuses without silently reducing this
model's default. Deterministic transport/admission tests cover normal/streaming,
explicit overrides, scope isolation and unknown/small capacities. This does not
change account settings or establish live acceptance.

### Meta Model API - published facts refreshed 2026-10-27

2026-10-28 protocol refresh: [tool calling](https://dev.meta.ai/docs/tool-calling)
documents flat Responses function definitions, function-call/result items and
matching call ids. [Responses](https://dev.meta.ai/docs/protocols/responses)
supports encrypted-only reasoning replay with `include` and `store:false`; replay
requires a summary field and preserves assistant commentary phase. Workbench now
implements these in the shared Responses adapter under ADR-073. Offline agent
read/tool-result loops cover Meta, generic Responses and Go Responses. This is
software-path evidence, not live model-quality or C6 acceptance. Published Muse
Spark Standard prices remain USD1.25 input/USD4.25 output per million tokens on
the [pricing page](https://dev.meta.ai/docs/pricing-rate-limits), rechecked today.

[Official pricing](https://dev.meta.ai/docs/pricing-rate-limits) lists Standard
Muse Spark1.3/1.2/1.1 at USD1.25 input and USD4.25 output per million tokens,
USD0.15 cached input. Standard content is not used to train Meta models;
Contributor variants exchange content-training permission for discounted pricing.
[Overview](https://dev.meta.ai/docs/overview) lists api.meta.ai/v1 and Responses
support. These published facts establish neither account access/credit nor an
enforced spending limit. Route entitlement, billing/retention settings and actual
usage still require scoped admission. No account observations or secrets recorded.
Meta billing control correction, checked 2026-10-27: the official
[spend-limit alert help](https://dev.meta.ai/help/billing/spend-limit-alert)
explicitly says Model API has no hard usage spending cap. The setting sends an
email alert; usage above it remains payable. Do not label that alert a hard cap or
set a provider-cap verification flag from it. Local admission bounds are distinct
from provider billing guarantees. This corrects any earlier assumption that the
direct API dashboard can enforce such a cap; no account settings were changed.
Meta reasoning/output accounting, checked2026-10-27: official
[reasoning guide](https://dev.meta.ai/docs/reasoning) and
[Responses guide](https://dev.meta.ai/docs/protocols/responses) state reasoning
and visible output share max_output_tokens and billed output totals. Numeric
output_tokens_details.reasoning_tokens and input_tokens_details.cached_tokens
provide accounting breakdown without private reasoning text. An unset effort is
provider default; do not assume a fixed level. Incomplete/max_output_tokens means
the requested output limit was reached, not that all consumed tokens were reasoning.

Meta Responses protocol details, checked 2026-10-27 from the official
[Responses guide](https://dev.meta.ai/docs/protocols/responses): `input` accepts
message roles `developer`, `system`, `user` and `assistant`, multiple system
messages, and typed content blocks; top-level `instructions` is equivalent to a
developer message and is not persisted across `previous_response_id`. `store`
defaults to true, so a non-persistent client must send `store: false`. Reasoning
continuity needs either `include: ["reasoning.encrypted_content"]` with
`store: false` or server-managed `previous_response_id`; the two cannot be
combined (HTTP 400). `max_output_tokens` has a minimum of 16 and shares the
context window with input (`input_tokens + max_output_tokens` must fit), so the
full window is never a valid output cap. Non-streaming requests are subject to a
server-side time limit and can return HTTP 504; streaming is exempt. The API also
rejects `truncation: "auto"` and `frequency_penalty`/`presence_penalty`, and
`reasoning.effort: "none"` is unsupported for Muse Spark. Prompt caching is
available (`prompt_cache_retention` hint), so repeated long instructions may bill
at the cached input rate.

Measured live on 2026-10-27 with four synthetic probes that contained no repository
content (`artifacts/meta-smoke-20261027/`): authentication, `system`-role input,
`store: false` and provider-reported usage all work against `muse-spark-1.3`. One
operational fact matters for budgeting: at `max_output_tokens: 64` the response
carried **no visible text** and reported `finish_reason: length`, because all 64
output tokens were reasoning; the same prompt at `max_output_tokens: 512` returned
`link ok` after 467 output tokens, **456 of them reasoning**. Muse Spark therefore
spent roughly 95% of its output budget on reasoning even for a trivial prompt, so a
small cap silently produces empty answers. The four probes cost under USD0.01 in
total. This is a small connectivity/accounting observation, not quality acceptance.
