# Provider source state

**Checked:** 2026-10-13; Gemini individual-access retirement verified 2026-10-14.
Published limits and account observations can expire.

**Latest scoped update:** 2026-10-21, OpenRouter limits/privacy and Codex data-policy
scope. This does not refresh every historical offer in the table below.

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
- Current implementation: `adapters/openrouter.py` refuses Free-plan accounts
  with unverified privacy-filter entitlement before admitting model inference.
  A free daily counter does not override that guard. Any public/synthetic-only
  exception is a separate owner-controlled privacy-policy decision, not approved
  merely by an end-of-day allowance grant.

### Codex and cross-provider privacy — checked 2026-10-21

[Codex authentication documentation](https://learn.chatgpt.com/docs/auth) distinguishes
ChatGPT workspace policies from API-organization retention/data-sharing settings.
Do not infer an individual's effective controls from a product name or subscription
alone. This repository has not inspected the owner's account data controls.
Using an external model means selected input is sent outside the workstation;
it does not establish public disclosure, training permission or equivalent handling
by every other processor. Evaluate the task data and each additional recipient.

## Sources and readiness

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
| OpenRouter | API gateway; advertised 50 free requests/day, rising to 1,000 after adding $10 credits; 20 requests/minute | Owner selected next-source priority on 2026-10-14. Experimental opt-in free-only adapter implemented offline: distinct key/provenance, exact zero prices/tool support/daily remaining checks each call, zero price caps and data_collection=deny. Key/account readiness and live quality unverified; example Qwen free endpoint listing was empty. Credit purchase deferred; no paid fallback. |
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
qualification. The experimental client refuses Free/unknown-tier key metadata
before inference. Offline successful mocks represent an already non-free-tier
account calling only zero-priced models; they do not establish free-account
entitlement. No deposit or policy weakening follows from this observation.

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
