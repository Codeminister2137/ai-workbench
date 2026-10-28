# AI Provider Interface

This package exposes the smallest provider-facing contract needed by current consumers. It is intentionally a Python package, not a service.

## Boundary

`ai_provider` owns:

- provider request/response translation;
- backend identity;
- model capability metadata;
- provider error normalization;
- provider-reported or estimated usage metadata;
- privacy enforcement at the provider boundary.

`ai_provider` does not own:

- prompt judging or refinement;
- model recommendation;
- routing policy;
- budget/quota policy;
- application workflows.

Those responsibilities belong above this package, primarily in `ai_orchestrator`.

## Core Types

Requesty's `require_free_model` checks the exact effective model before every
completion or stream. Input/output prices and every advertised cache-read or
cache-write price must be zero, including threshold pricing tiers. Nonzero or
invalid advertised prices refuse inference; missing optional cache prices do not
invent a charge or grant. This is a price check, not proof of remaining allowance,
privacy entitlement or model quality. Cache fields follow the official
[Requesty model catalog](https://docs.requesty.ai/api-reference/endpoint/models-list).
Malformed catalog JSON or UTF-8 also refuses before inference with a configuration
error; response contents are not included in the user-facing error message.

Function tools use `AIToolDefinition`/`AIToolParameter`. Array parameters may set
optional `item_type_name` (for example, `"string"` for process argument lists),
which emits the standard JSON Schema `items` property. Omitting it preserves the
previous unconstrained-array schema. The agent's corresponding tool contract
carries this metadata through its provider translation; tool handlers still own
argument validation and effects.

### `AIMessage`

One chat message with:

- `role`: `system`, `user`, or `assistant`;
- `content`: text content;
- `name`: optional speaker/tool label for future use.

### `AIRequest`

One chat-style completion request:

- `messages`: ordered `AIMessage` values;
- `model`: optional per-request model override;
- `temperature`: optional model sampling setting;
- `max_output_tokens`: optional output cap;
- `privacy_class`: prototype privacy label;
- `metadata`: caller metadata that adapters may preserve but should not require.

OpenRouter's optional public-input exception uses
`metadata={"public_or_synthetic": True}` together with
`privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK`. This attests that the **entire**
request is public/synthetic and approved for possible retention/training; the
broader privacy class alone does not qualify. Caller code must reassess history,
instructions and tool results on every request. No automatic classification or
saved-session inheritance is provided. The exception permits uncertain Free-plan
privacy-filter entitlement while preserving zero-price, quota and requested
`data_collection=deny` guards. See [ADR-063](../../../docs/decisions/ADR-063-explicit-public-input-privacy-exception.md).

The separate `ai_provider.reviewed_input.reviewed_input_request` helper binds
review of exact non-sensitive UTF-8 text to `reviewed_non_sensitive_sha256` request
metadata. OpenRouter accepts this narrow entitlement exception only for one
bounded USER message without tools, history, names, tool-call data or private
continuation. It does not declare the input public and does not inherit across
requests; modifying or adding input invalidates review. The caller must exclude
secrets/genuinely private data and approve possible retention/training. This is
an explicit declaration, not secret detection. Existing privacy/price/quota/wire
guards remain. See [ADR-069](../../../docs/decisions/ADR-069-restricted-reviewed-non-sensitive-input.md).

### `AIResponse`

One normalized provider response:

- `message`: assistant message;
- `backend`: provider/model/location identity;
- `usage`: provider-reported, estimated, or unavailable token usage;
- `finish_reason`: normalized stop/length/error/unknown value;
- `latency_ms`: measured adapter latency when available;
- `raw_metadata`: original provider metadata retained for diagnostics.

Raw metadata is omitted from the default representations of `AIResponse` and
`AIStreamDelta`: provider diagnostics can contain private thinking or continuation
state. Explicit field access and serialization retain their existing contents;
they are diagnostic operations, not a sanitized logging format. This does not
change answer text, usage, tool calls or exact-origin continuation replay.

### Streaming

The shared Responses adapter translates flat function definitions and typed
`function_call`/`function_call_output` history, matching ids before sending results.
Both complete and streamed responses deliver normalized calls only after argument
validation; failed responses cannot deliver executable calls. Native order, message
phase and encrypted reasoning travel transiently through ADR-055 continuation,
separate from ordinary metadata. Rewritten messages or a different origin do not
replay that state. Meta explicitly requests encrypted content with `store:false`.
This protocol support does not establish a model's live coding quality.

`ChatClient.stream(request)` yields `AIStreamEvent` values:

- `AIStreamDelta`: one text delta with raw provider metadata;
- `AIStreamFinal`: one final normalized `AIResponse` containing accumulated
  assistant text, backend identity, usage metadata when available, finish reason,
  latency, and raw final provider metadata.

Streaming adapters must enforce the same privacy policy as non-streaming
completion before sending the request.

Hosted single-line SSE data events accept the optional space after `data:`,
including the `[DONE]` terminator. This follows the
[SSE field syntax](https://html.spec.whatwg.org/multipage/server-sent-events.html#parsing-an-event-stream);
this bounded check does not establish complete EventSource parsing conformance.

Final streaming responses preserve tool calls in both `message.tool_calls` and
`tool_calls`. Hosted calls are assembled by stream index, including interleaved
argument fragments; Ollama calls arriving before its final usage chunk remain
available. Hosted trailing usage is normalized and its original chunk retained
under `raw_metadata.stream_usage_chunk`. The adapter does not add an
`include_usage` request option, so absent provider counts remain unavailable.
These layouts follow [OpenAI's streaming contract](https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events)
and [Ollama's streamed tool responses](https://ollama.com/blog/streaming-tool).

Malformed JSON/UTF-8, non-object response envelopes and invalid tool argument
JSON are normalized to nonretryable `ProviderError` instances. Invalid arguments
never silently become an empty executable call. Software fixtures verify these
contracts without hosted calls or model-quality claims.
Malformed tool arrays, call/function objects and empty function names also fail
explicitly rather than being dropped or converted into a successful tool-free answer.
Optional token counters accept only nonnegative integers, excluding booleans;
invalid counters remain unknown without discarding a valid answer. Unexpected
finish metadata normalizes to `unknown`.

### `BackendConfig`

Configured backend selection:

- `provider`: `ollama`, `requesty`, `openrouter`, `openai`, `google`, `opencode_go`, or `meta`;
- `model`: backend model ID;
- `base_url`: optional backend URL override;
- `api_key`: optional hosted-provider credential loaded from environment or
  supplied by the caller;
- `timeout_seconds`: bounded request timeout.

`BackendConfig.from_env()` reads `AI_PROVIDER_*` variables.

### `EndpointAvailability` and `EndpointInventory`

Source-neutral route-availability records. Every source normalizes into this
shape so consumers never branch per source, and a value the source did not
report stays `None` rather than being inferred.

`EndpointAvailability` describes one provider endpoint for one model:
`source`, `model`, `provider`, `endpoint` (the provider's endpoint tag),
`status`, `uptime_1d_percent`, `uptime_30m_percent`, `latency_seconds`,
`throughput_tokens_per_second`, `quantization`, `service_tier`,
`context_length`, `max_completion_tokens`, `prices`, `supported_parameters`
and `observed_at_utc`. The unit is carried in the name: uptime is a ratio in
the range 0-100 as reported by the source.

`EndpointInventory` is the per-model envelope: `status` (`observed`,
`unavailable` or `unknown`), `source`, `model`, `endpoints`,
`observed_at_utc` and `reason`. An observation with no advertised endpoint is
still `observed` — the empty list is the finding, and `reason` says so. Its
`summary()` reports `provider_count`, `endpoint_count`, the best and worst
1-day uptime, the largest context length and the quantizations present.

These are source-reported availability observations, not quality judgments: a
healthy endpoint says nothing about the model behind it, and a quantized
endpoint is not the same capability as a full-precision one. They are not
acceptance evidence for this repository.

`ai_provider.openrouter_endpoints.read_openrouter_endpoint_availability` reads
the public OpenRouter endpoints API for one model id. It sends no prompt, calls
no model, needs no credential, and never discovers credential files.

### `CapabilityScore` and `CapabilityPrior`

Published, dated capability results used as a **selection prior**. They are not
acceptance evidence for this repository, and a published score is almost never
a property of the model alone: the same model appears under several agent
scaffolds with different scores. The scaffold is therefore part of every
record, and a score must never be read as a model-only claim.

`CapabilityScore` holds one published result: `source`, `benchmark`, `split`,
`model` (a comparable key derived from the published name), `model_display`
(the source's own spelling, kept so the normalization stays auditable),
`agent`, `agent_org`, `score`, `scale` (the unit of `score`), `measured_at`,
`verified`, `cost_usd`, `warning`, `source_url` and `observed_at_utc`.

`CapabilityPrior` is the per-split envelope: `status` (`observed`,
`unavailable`, `unknown`), `source`, `benchmark`, `split`, `scores`,
`observed_at_utc`, `reason` and `source_url`. Its `summary()` reports the row,
model and agent counts and the strongest published row, with that row's agent
still attached. The record is JSON-safe and safe to persist, so a stored prior
stays dated; the caller owns any cache.

`ai_provider.swe_bench_scores.read_swe_bench_scores` reads the public
SWE-bench leaderboard data for one split. It needs no credential, sends no
prompt and calls no model. A missing split is reported as unavailable rather
than guessed.

`ai_provider.aider_polyglot_scores.read_aider_polyglot_scores` reads the public
Aider polyglot leaderboard page, which is HTML rather than JSON, using only the
Python standard library. Two properties make it the better prior for comparing
models against each other:

- **One harness.** Every row was produced by the same tool, so scores are
  comparable model-to-model. The harness is still recorded on every record, and
  a score must never be read as a model-only claim.
- **A specific model id.** Each run publishes the exact `--model` argument it
  used, such as `openrouter/openai/gpt-oss-120b`, so the record grades one
  model rather than a family. The published display name is kept separately so
  the extraction stays auditable.

Each run also publishes the failure modes that decide whether a model is usable
in practice rather than merely accurate: the share of cases that produced a
well-formed answer, syntax errors, and exhausted context windows.

`ai_provider.capability_bands` turns those two priors into the recommendation
grade published in the [model catalog](model-catalog.md). Each source keeps its
own fixed band cutoffs, calibrated on a dated snapshot and then frozen, because
`percent_correct` and `percent_resolved` are different scales under different
harnesses; the two bands are reported side by side and never averaged.
`band_for()` returns `None` when a source published no score, so an absent prior
is never reported as a low band, and an uncalibrated source raises rather than
inheriting another source's cutoffs. A band is published evidence about an
upstream family — deliberately a different vocabulary from the Orchestrator's
`QualityThreshold` (`low`/`standard`/`high`), which is the minimum tier a task
declares for a catalog entry. This module never writes to a catalog entry, and a
local L3 CLI measurement overrides a band for a specific task.

## Capability Matrix

| Capability | Ollama | Requesty | OpenRouter | OpenAI | Google | OpenCode Go |
| --- | --- | --- | --- | --- | --- | --- |
| Chat completion | Implemented | Implemented | Implemented | Implemented | Implemented | Implemented |
| Streaming | Implemented | Implemented | Implemented | Implemented | Implemented | Implemented |
| Provider-reported usage | Partial, when Ollama reports counts | Implemented when reported | Implemented when reported | Implemented when reported | Implemented when reported | Implemented when reported |
| Model listing | Local only | Via API | Via API | Via API | Via API | Via API |
| Account allowance observation | No | No | Via API | No | No | Unavailable: no official endpoint |
| Route availability observation | No | No | Via API | No | No | No |
| External execution | No | Implemented | Implemented | Implemented | Implemented | Implemented |
| Tool calling | Not yet | Future trigger | Implemented | Future trigger | Future trigger | Implemented |
| Structured output | Not yet | Future trigger | Future trigger | Future trigger | Future trigger | Future trigger |
| Embeddings | Not yet | Future trigger | Future trigger | Future trigger | Future trigger | Future trigger |

The interface should not pretend every backend supports every feature. New capabilities should be added only when a real consumer needs them.

## Hosted API Shape

The initial hosted adapter uses OpenAI-compatible Chat Completions for both
Requesty and OpenAI. This is a deliberate compatibility choice, not a permanent
statement that Chat Completions is always the best protocol. ADR-020 records that
each hosted adapter should document whether it uses Chat Completions, Responses,
Anthropic Messages, or another API shape, and why.

OpenCode Go now supports all three documented endpoints:

- **Chat Completions** at `https://opencode.ai/inference/go/openai/v1` via
  `OpenCodeGoChatClient`.
- **Responses** at `https://opencode.ai/inference/go/v1/responses` via
  `OpenCodeGoResponsesClient`, a subclass of the reusable
  `OpenAIResponsesChatClient`.
- **Messages** at `https://opencode.ai/inference/go/v1/messages` via
  `OpenCodeGoMessagesClient`, a subclass of the reusable
  `AnthropicMessagesChatClient`.

The Responses and Messages endpoints require the `x-opencode-session` header;
the adapters read it from `request.metadata["opencode_session"]`. A live
all-model probe with the correct protocol routing and Console Privacy toggles
achieved 33 ok / 3 error; remaining failures are `mimo-v2.5-pro` (upstream
unsupported), `gemini-4-argon-contributor` (no supported protocol) and
`longcat-2.0` (unavailable).

`create_chat_client` routes OpenCode Go models by the protocol declared in
source info. Callers should pass a stable conversation session id in
``request.metadata["opencode_session"]`` so the adapter can send the
``x-opencode-session`` header Go expects for routing and prompt caching. A
project-specific User-Agent is sent automatically.

Model inventory is collected from ``GET /inference/go/v1/models`` and now
includes each model's ``protocol`` (``chat``/``responses``/``messages``),
``trains_on_request_data``, and ``requires_global_regions`` metadata. Go
subscription remaining allowance is **not** exposed by an official endpoint for
the inference key; the collector reports ``unavailable`` rather than inferring
it from published limits.

Prefer the richer provider API when it does not compromise compatibility,
privacy, cost, quality, or maintainability. The generic
`OpenAIResponsesChatClient` and `AnthropicMessagesChatClient` bases make the
same protocol available to future non-Go providers without duplicating payload
and stream parsing logic.

## Provider Factory

Use `create_chat_client(config)` to construct a `ChatClient` from `BackendConfig`. Unimplemented providers fail with a configuration error instead of silently falling back.

## HTTP Client Decision

The current Ollama adapter uses the Python standard library. Keep this until streaming, richer retries, or async behavior create a concrete need for a dependency such as `httpx`.
