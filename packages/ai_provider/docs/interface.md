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

### `AIResponse`

One normalized provider response:

- `message`: assistant message;
- `backend`: provider/model/location identity;
- `usage`: provider-reported, estimated, or unavailable token usage;
- `finish_reason`: normalized stop/length/error/unknown value;
- `latency_ms`: measured adapter latency when available;
- `raw_metadata`: original provider metadata retained for diagnostics.

### Streaming

`ChatClient.stream(request)` yields `AIStreamEvent` values:

- `AIStreamDelta`: one text delta with raw provider metadata;
- `AIStreamFinal`: one final normalized `AIResponse` containing accumulated
  assistant text, backend identity, usage metadata when available, finish reason,
  latency, and raw final provider metadata.

Streaming adapters must enforce the same privacy policy as non-streaming
completion before sending the request.

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

### `BackendConfig`

Configured backend selection:

- `provider`: `ollama`, `requesty`, or `openai`;
- `model`: backend model ID;
- `base_url`: optional backend URL override;
- `api_key`: optional hosted-provider credential loaded from environment or
  supplied by the caller;
- `timeout_seconds`: bounded request timeout.

`BackendConfig.from_env()` reads `AI_PROVIDER_*` variables.

## Capability Matrix

| Capability | Ollama | Requesty | OpenAI |
| --- | --- | --- | --- |
| Chat completion | Implemented | Implemented | Implemented |
| Streaming | Implemented | Implemented | Implemented |
| Provider-reported usage | Partial, when Ollama reports counts | Implemented when reported | Implemented when reported |
| External execution | No | Implemented | Implemented |
| Tool calling | Not yet | Future trigger | Future trigger |
| Structured output | Not yet | Future trigger | Future trigger |
| Embeddings | Not yet | Future trigger | Future trigger |

The interface should not pretend every backend supports every feature. New capabilities should be added only when a real consumer needs them.

## Hosted API Shape

The initial hosted adapter uses OpenAI-compatible Chat Completions for both
Requesty and OpenAI. This is a deliberate compatibility choice, not a permanent
statement that Chat Completions is always the best protocol. ADR-020 records that
each hosted adapter should document whether it uses Chat Completions, Responses,
Anthropic Messages, or another API shape, and why.

Prefer the richer provider API when it does not compromise compatibility,
privacy, cost, quality, or maintainability. OpenAI's Responses API is a likely
future OpenAI-specific adapter when built-in tools, computer use, or richer
agentic streaming become necessary.

## Provider Factory

Use `create_chat_client(config)` to construct a `ChatClient` from `BackendConfig`. Unimplemented providers fail with a configuration error instead of silently falling back.

## HTTP Client Decision

The current Ollama adapter uses the Python standard library. Keep this until streaming, richer retries, or async behavior create a concrete need for a dependency such as `httpx`.
