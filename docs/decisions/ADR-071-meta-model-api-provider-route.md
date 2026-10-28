# ADR-071: Dedicated Meta Model API Provider Route

## Status
Accepted

## Date
2026-10-27

## Context
Meta Model API credits are currently the owner's most reliable paid inference
route, and the credits should be spent mainly on the Remote AI Operator hackathon
project. The Workbench had no Meta provider, so the owner could not select a
Muse Spark route from the CLI or the orchestrator, and Muse Spark was reachable
only through OpenCode Go's Contributor variants, which exchange content-training
permission for discounted pricing.

The Meta endpoint speaks the OpenAI Responses protocol at
`https://api.meta.ai/v1`, so the existing generic `OpenAIResponsesChatClient`
already implements the request and response shape. The choice was between a
generic OpenAI-compatible entry (reusing the existing adapter with a base-URL
override) and a dedicated adapter that inherits the Responses client.

## Decision
1. Add `ProviderKind.META` with API-key resolution from `META_API_KEY`.
2. Add `MetaResponsesChatClient`, inheriting `OpenAIResponsesChatClient`, with:
   - the `https://api.meta.ai/v1` endpoint default and catalogue-visible override;
   - `muse-` model admission on both the configured model and per-request
     overrides;
   - refusal of Contributor variants, because Meta trains on their request
     content;
   - a forced `store: false` so repository content is not persisted provider-side.
3. Add `BillingSource.META_API_BILLING` and the `meta/muse-spark-1.3` catalog
   route at `prepaid_credits_allowed`, with published Standard pricing as its
   estimate. Lowering the tier to `billing_allowed` is an explicit later edit,
   not a silent default.
4. Keep the route available after the hackathon because it uses the owner's own
   Meta account rather than event-scoped credit access.

## Consequences
- The owner can select a Meta Standard route whose content is not used to train
  Meta models, instead of the Contributor variants that require training consent.
- The provider boundary stays explicit: Meta-specific admission, endpoint and
  persistence policy live in one adapter instead of leaking into callers.
- Quality and context capacity for Muse Spark remain unevaluated here, so the
  route is a candidate, not an accepted replacement for the current models.
- Meta has no hard provider spending cap. Local admission bounds remain the only
  spending guard, and the catalog tier must be lowered deliberately when the
  prepaid credits are exhausted.
