# ADR-072: Modal Runtime Provider Route

## Status
Accepted

## Date
2026-10-28

## Context
Modal provides serverless GPU/CPU containers that can host open-weight models
with an OpenAI-compatible Chat Completions endpoint. The owner has $100 of
hackathon credits and expects $30 of recurring monthly credits, making Modal a
useful long-term inference source for the workbench. Unlike token-priced
providers, Modal bills by compute time, so the provider boundary should treat it
as a runtime rather than a generic API.

The existing `ai_provider` layer already supports `LOCAL_RUNTIME` (Ollama) and
`PROVIDER_API` (hosted token APIs). Modal fits neither category cleanly: it is
hosted like a provider API, but its cost model and deployment lifecycle are
runtime-like.

## Decision
1. Add `AccessMethod.MODAL_RUNTIME` to distinguish Modal-hosted endpoints from
generic provider APIs.
2. Add `ProviderKind.MODAL` with API-key resolution from `MODAL_API_KEY`.
3. Add two distinct billing sources:
   - `BillingSource.MODAL_TOKEN_BILLING` for Modal Shared Endpoints / Model API
     routes billed per token.
   - `BillingSource.MODAL_RUNTIME_BILLING` for Modal serverless GPU/CPU container
     routes billed per second of compute time.
   The distinction between hackathon credits and monthly free credits within each
   surface is kept outside the app (e.g., via user-config priority or allowance
   labels), not in the billing source enum.
4. Add `ModalRuntimeChatClient` in `ai_provider/adapters/modal.py`. It inherits
from `OpenAICompatibleChatClient` to reuse the Chat Completions protocol, but
overrides `backend` and `base_url` so that:
   - the route advertises `chat=True`, `streaming=True`, `tools=True`;
   - a missing `base_url` is rejected with a clear configuration error;
   - the `/models` readiness probe is skipped for Modal routes, because a
     user-controlled Modal deployment is not required to implement it.
5. Add `modal/qwen/qwen2.5-coder-7b-instruct` to the model catalog, pointing at
`Qwen/Qwen2.5-Coder-7B-Instruct` served by a Modal vLLM endpoint. The cost
estimate is illustrative (per-second GPU pricing) and the route is marked
provisional pending measured latency and context capacity.

## Consequences
- Modal credits can be consumed through the same orchestrator/fallback path as
other provider routes.
- The adapter stays thin: protocol reuse avoids reimplementing chat/streaming,
while the Modal-specific access method leaves room for future runtime lifecycle
features (deploy, keep-warm, scale-to-zero) without changing callers.
- Cost tracking remains approximate; actual spend is per-second GPU time, not
per-token. Local admission bounds and receipt tracking are still required.
- A deployed Modal app with an OpenAI-compatible `/v1/chat/completions` endpoint
is a prerequisite for live use; the adapter does not deploy or manage it.
