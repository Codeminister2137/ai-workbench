# Provider model recommendations

This is a human-readable recommendation catalog, not executable routing policy.
The runtime route catalog belongs to
[ai_orchestrator](../../ai_orchestrator/examples/model_catalog.toml).
Provider/gateway, exact model and access route remain separate identities.
Listing a model here does not implement its adapter or authorize inference.

## OpenCode Go

Checked 2026-10-22. See [dated source findings](source-state.md#opencode-go-model-starting-points--checked-2026-10-22)
and [official Go documentation](https://opencode.ai/v2/docs/console/go/).

| Model | Model ID | Recommended role | Evidence / limitation |
| --- | --- | --- | --- |
| Kimi K2.7 Code | `kimi-k2.7-code` | Current single-model starting point for implementation, tests and frozen review | Provisional engineering recommendation; repository quality acceptance unestablished |
| GLM-5.2 | `glm-5.2` | Alternative implementation model for later selection | Retained option; no manual switch required by the current workflow |
| GLM-5.3 | `glm-5.3` | Optional different-model reviewer for later automated selection | Not a current review requirement; repository quality acceptance unestablished |

Current workflow preference: use Kimi throughout while model switching remains
manual. Keep frozen review as a separate read-only phase, preferably a fresh
session using the same model. This avoids manual model coordination; the cost is
that implementation and review may share model-specific blind spots. A fresh
session provides separation of task/context, not model diversity or guaranteed
independent judgment. Actual tests, factual reporting, frozen inputs and owned
cleanup remain required.

Model alternatives are recommendations for future selection, not an automatic
fallback chain, measured quality ranking, model-switch instruction, or permission
to change billing/privacy. Record new task evidence before promoting a model's
quality grade. Account quota and exact hosted model availability still need fresh
admission; credentials never belong in this catalog.

## OpenCode Go temporary free candidates

Checked 2026-10-22 against the [official offer and privacy table](https://opencode.ai/v2/docs/console/go/). Live model listing and access probes were also run; see [source-state.md](source-state.md).

| Model | Exact ID | Advertised usage | Training / retention | Live listing status |
| --- | --- | --- | --- | --- |
| LongCat 2.5 Preview Free | `longcat-2.5-preview-free` | Temporarily free, unlimited | No training / zero days | **Not returned** by `GET /inference/go/v1/models` today; access unverified |
| MiniMax M3.1 Flash Free | `minimax-m3.1-flash-free` | Temporarily free, unlimited | No training / zero days | Listed; probe **ok** |
| Beam Free | `beam-free` | Temporarily free, unlimited; regional exclusions | No training / 30 days | Listed; probe **ok** |

These are future evaluation candidates, not accepted coding replacements. The
promotion has no specified end date on the checked page; traffic abuse controls
remain. Advertised allowance is not guaranteed throughput or model quality.
Retain Kimi as the current single-model preference; no manual switch or inference
is requested by listing these options.

Live access probes found **13 of 36 models failing** with the initial
Chat-Completions-only adapter. After implementing Responses/Messages protocol
routing and toggling Console Privacy settings for Global regions and
training-on-request-data, the rerun with `max_output_tokens=16` found **3 of 36
models still failing** (`mimo-v2.5-pro`, `gemini-4-argon-contributor`,
`longcat-2.0`). Several models (`qwen3.6-plus`, `qwen3.7-max`, `qwen3.7-plus`,
`grok-4.6`) still ignore the requested `max_output_tokens` limit. Update any
fallback plan with these observations rather than assuming all listed models are
interchangeable.

OpenCode Go exposes **three protocol endpoints**, all now implemented in
`ai_provider`:

- **Chat Completions** (`/inference/go/openai/v1/chat/completions`): GLM, Kimi,
  LongCat, MiMo, Hy3, Omen Alpha, Space Bunny, Qwen. Served by
  `OpenCodeGoChatClient`.
- **Responses** (`/inference/go/v1/responses`): Grok, GPT Luna, Muse Spark
  Contributor, DeepSeek (some variants). Served by `OpenCodeGoResponsesClient`,
  which extends the generic `OpenAIResponsesChatClient` base adapter.
- **Messages** (`/inference/go/v1/messages`): MiniMax M2.7, Claude Haiku 5.5.
  Served by `OpenCodeGoMessagesClient`, which extends the generic
  `AnthropicMessagesChatClient` base adapter.

`create_chat_client` selects the adapter based on the model's declared protocol.
`OpenCodeGoSourceInfo` populates each model's `protocol`,
`trains_on_request_data`, and `requires_global_regions` metadata so callers can
enforce privacy choices before inference.

DeepSeek and Muse Spark Contributor models additionally require specific Privacy
settings in the OpenCode Console (Global regions and "allow paid endpoints that
train on request data"). With those toggles enabled, the latest all-model probe
achieved **33 ok / 3 error**; `gemini-4-argon-contributor` remains unsupported on
all three endpoints, `mimo-v2.5-pro` remains upstream-unsupported, and
`longcat-2.0` remains unavailable.

## Adding other providers

Add recommendations as they are investigated, recording exact model/access route,
task role, checked date, source and evaluated versus provisional status. Do not
invent a recommended model for every provider simply to fill a table. Existing
source readiness and unresolved limitations remain in [source-state.md](source-state.md).
Keep public recommendations separate from private account-specific preferences.
