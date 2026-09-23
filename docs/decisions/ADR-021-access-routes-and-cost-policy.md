# ADR-021 - Access Routes And Cost Policy Boundaries

**Status:** Accepted

**Date:** 2026-09-21

## Context

The repository originally described execution mostly as provider/model selection.
That is too broad for the product goal: a user may have local models, API keys,
gateway credits, included subscription allowances, or official CLI entitlements
from the same underlying provider.

Provider identity alone does not determine how execution is reached, which
credentials are used, which product owns authentication, or which billing bucket
is consumed. OpenAI through Codex with ChatGPT sign-in and OpenAI through direct
API billing are different access routes, even if both ultimately use OpenAI
models.

The product must never silently cross a billing boundary. If a user allows only
local, free, or included subscription usage, the system must not silently fall
back to metered API billing or paid gateway credits.

Subscription-backed access should only use officially supported mechanisms. The
system must not rely on browser cookies, private endpoints, scraped tokens, or
unsupported reuse of consumer-session credentials.

## Options Considered

### Keep Provider/Model As The Selectable Unit

This is simple and matches early provider-adapter code.

The drawback is that it collapses distinct routes such as OpenAI API and Codex
CLI. That makes billing, entitlement, and authentication boundaries ambiguous.

### Add Flat Access/Auth/Billing Metadata To Backend Entries

This is a small extension to the existing catalog shape.

The drawback is that route identity remains implicit. Overrides and explanations
can still collide when two routes share the same provider and model.

### Make Access Route The Selectable Unit

This makes each official execution path explicit. A route has its own identifier,
provider, product/service, access method, authentication method, billing source,
minimum cost-policy tier, location, model, capabilities, and estimates.

The drawback is a modest refactor of catalog and execution-target contracts.

### Build A Full Account, Quota, And Entitlement Registry

This would model live account state, reset windows, prepaid credits, subscription
plans, and provider-specific quota APIs.

The drawback is unnecessary infrastructure before the current routes prove value.
Many providers do not expose subscription allowances programmatically.

## Decision

Use access routes as the selectable execution unit in `ai_orchestrator`.

An access route represents one official way to execute a model, such as:

- Ollama local runtime using local compute;
- Requesty provider API using configured Requesty access;
- OpenAI direct API using API-key billing;
- Codex CLI using ChatGPT sign-in and subscription allowance.

`ai_provider` remains the provider API adapter layer. It should not own
subscription-backed CLI integrations. Official clients such as Codex CLI should
own their own subscription authentication when possible, and repository code
should adapt orchestration targets to those executors at the boundary.

Add an ordered cost-policy tier to route selection:

- `LOCAL_ONLY`
- `FREE_ONLY`
- `ALLOWANCES_ALLOWED`
- `PREPAID_CREDITS_ALLOWED`
- `BILLING_ALLOWED`

Higher tiers permit the routes in lower tiers. The default task policy is
`ALLOWANCES_ALLOWED`.

OpenAI direct API routes require `BILLING_ALLOWED` by default. Codex
subscription-backed routes can be eligible by default for external-allowed tasks
because they consume included subscription allowance. Requesty routes may be
classified according to the user's configured account policy and current
available credits.

## Rationale

The owner wants one application to unify the AI access the user already has. If a
user connects a subscription-backed or included-allowance route, the system
should assume they intend to use that included allowance, while still preventing
silent use of prepaid credits or metered billing.

Prepaid credits are intentionally separate from included allowances. Even though
they have already been purchased, they retain value if unused and should not be
treated as free fallback capacity.

## Consequences

Route selection must filter by privacy, route overrides, cost policy,
capabilities, and quality before ranking by quality/latency.

Fallback cannot cross from allowance-backed routes to prepaid or metered routes
unless the task policy explicitly allows it.

Provider/API adapters remain focused on official APIs and API credentials.
Subscription-backed tools such as Codex CLI, future Claude Code, Gemini CLI, or
GitHub Copilot CLI should be separate executor routes that use official client
authentication.

Live quota and entitlement discovery remain future work. Missing live quota data
must not be treated as unlimited quota.

## Related Decisions

- `docs/decisions.md` ADR-002 - Provider-Agnostic AI Boundary
- `docs/decisions.md` ADR-004 - Local And Cloud Backends Must Be Switchable
- `docs/decisions.md` ADR-010 - Usage Tracking Is A Separate Concern
- `docs/decisions.md` ADR-014 - Provider Contract And Dependencies
- `docs/decisions.md` ADR-016 - Optional Package Composition And Neutral Orchestrator Contracts
- `docs/decisions.md` ADR-020 - Coding MVP Supports Local Requesty And OpenAI Backends
