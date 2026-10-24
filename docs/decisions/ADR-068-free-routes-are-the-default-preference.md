# ADR-068 — Free routes are the default preference

**Status:** Accepted

**Date:** 2026-10-24

**Owner decision:** stated directly while choosing how to add the OpenRouter
route: *"A, Always A, by default. More free stuff is good."* The same turn
approved the concrete Option A (declare an OpenRouter free catalog route).

## Context

ADR-021 defines cost-policy tiers (`local_only`, `free_only`,
`allowances_allowed`, `prepaid_credits_allowed`, `billing_allowed`) and makes the
task's ceiling the admission boundary. The ladder already allows a cheaper tier
from a more expensive ceiling, so a free route can serve an `allowances_allowed`
task.

Before this decision the default catalog declared one free hosted route
(`requesty/free-google/gemma-4-31b-it`) and one free local tier (Ollama). The
fallback order in local `user-config.toml` was derived from observed allowance
and reliability, and the free route was already first because it spends nothing.
The remaining question was whether free routes are an occasional fallback or the
preferred default.

The owner answered that directly: free is the default, and adding more free
sources is desirable. This ADR records that preference so later sessions do not
re-litigate it or treat a paid route as the obvious first choice.

## Decision

When a free route satisfies the task's declared requirements, it is preferred
over a paid or allowance-consuming route.

Concretely:

1. **Free first in ordering.** Free routes are listed before
   allowance/credit/billing routes in the default fallback priority, and a new
   free route is inserted ahead of paid ones when its capability is comparable.
2. **Free is a preference, not a waiver.** The task's quality threshold, privacy
   class, required capabilities (tools, streaming, context) and provider
   boundaries still decide admission. A free route that cannot meet them is not
   selected merely because it is free.
3. **Free stays honestly ungraded.** A route with no measured row keeps its
   `unmatched` confidence and provisional quality. Free does not become a claim
   about coding quality, and a passing live call is admission evidence, not
   quality acceptance.
4. **Adding a free source is preferred to buying capacity.** When the owner asks
   for more capacity, first look for an existing free or already-paid-for
   allowance route. This is a preference for research direction, not permission
   to add a provider, credential, data flow or dependency: those remain material
   decisions requiring owner approval.
5. **Free routes keep their guards.** Free-only adapters continue to verify
   exact zero prices, tool support and remaining quota before every call, and
   refuse rather than escalate to a paid model. The preference never authorizes
   paid overage.

## Consequences

- `packages/ai_orchestrator/examples/model_catalog.toml` now declares
  `openrouter/free-google/gemma-4-31b-it:free` alongside the Requesty free route.
  Its route id follows ADR-065 with a new `openrouter_free` → `free` product slug,
  so the derivation still reproduces every declared id.
- **Declaring a free route and ordering it are separate steps.** A free route is
  inserted ahead of paid routes only once it can actually serve the task. On
  2026-10-24 the OpenRouter route passed every adapter guard for an attested
  synthetic request, but a no-credits account reports `is_free_tier: true`, so
  an ordinary unattested CLI request is refused by ADR-063's entitlement guard.
  It is therefore declared and testable but deliberately absent from the local
  fallback order until that entitlement question is decided. Preferring free
  routes never means pretending an unusable free route is usable.
- The default fallback order keeps the proven Requesty free route first, then
  `opencode-go`, `kiro` and `copilot`, and the order stays configuration,
  re-derivable when allowance or reliability changes.
- Free routes concentrate risk: each has one or few endpoints and a daily
  request ceiling, so a free-first order must still fall through the whole
  ordered set rather than stop at the first free candidate. The observed 429 from
  the route's single upstream shared pool is an example of why.
- Cost reporting must keep showing $0.00 for free calls and separate hosted
  allowance consumption, so a free-first policy is auditable rather than assumed.
- This ADR does not change any provider's privacy terms, the unresolved
  OpenRouter Free-plan data-policy conflict, or the attested-public-input
  exception in ADR-063. It also does not change which provider error categories
  continue a fallback walk; that remains a separate routing decision.
