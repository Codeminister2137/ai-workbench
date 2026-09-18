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

### `BackendConfig`

Configured backend selection:

- `provider`: currently only `ollama` is implemented;
- `model`: backend model ID;
- `base_url`: optional backend URL override;
- `timeout_seconds`: bounded request timeout.

`BackendConfig.from_env()` reads `AI_PROVIDER_*` variables.

## Capability Matrix

| Capability | Ollama | Requesty placeholder | Direct-provider placeholder |
| --- | --- | --- | --- |
| Chat completion | Implemented | Planned | Planned |
| Streaming | Not yet | Planned when needed | Planned when needed |
| Provider-reported usage | Partial, when Ollama reports counts | Planned | Planned |
| External execution | No | Planned | Planned |
| Tool calling | Not yet | Future trigger | Future trigger |
| Structured output | Not yet | Future trigger | Future trigger |
| Embeddings | Not yet | Future trigger | Future trigger |

The interface should not pretend every backend supports every feature. New capabilities should be added only when a real consumer needs them.

## Provider Factory

Use `create_chat_client(config)` to construct a `ChatClient` from `BackendConfig`. Unimplemented providers fail with a configuration error instead of silently falling back.

## HTTP Client Decision

The current Ollama adapter uses the Python standard library. Keep this until streaming, richer retries, or async behavior create a concrete need for a dependency such as `httpx`.
