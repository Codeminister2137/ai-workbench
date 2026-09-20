# ai-provider

Provider-agnostic AI contracts and adapters.

This package is the infrastructure layer below orchestration and applications. It owns provider-specific API calls, request/response translation, backend identity, provider errors, and usage metadata. It does not choose the best model, judge prompts, synthesize Council answers, or implement job-search logic.

## Current Scope

- Neutral chat-first request/response contract.
- Prototype privacy classes.
- Backend identity and model capabilities.
- Provider-reported usage metadata where available.
- Ollama chat adapter.
- Ollama chat streaming.
- OpenAI-compatible Chat Completions adapter for OpenAI and Requesty.
- Provider factory for configured chat clients.

The first hosted adapter intentionally targets OpenAI-compatible Chat
Completions because that is the shared protocol documented by Requesty and it
maps directly to the current neutral chat contract. ADR-020 records this protocol
choice and the rule that richer provider APIs, such as OpenAI's Responses API,
should be preferred later when they add needed capability without hurting
compatibility, privacy, cost, quality, or maintainability.

See `docs/interface.md` for the one-page interface spec and capability matrix.

## Minimal Usage

```python
from ai_provider import AIMessage, AIRequest, MessageRole
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.factory import create_chat_client

client = create_chat_client(
    BackendConfig(provider=ProviderKind.OLLAMA, model="llama3.2")
)

response = client.complete(
    AIRequest(messages=(AIMessage(MessageRole.USER, "Say hello in one sentence."),))
)

print(response.message.content)
print(response.backend.provider, response.backend.model)
```

## Streaming

```python
from ai_provider import AIMessage, AIRequest, AIStreamDelta, AIStreamFinal, MessageRole
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.factory import create_chat_client

client = create_chat_client(
    BackendConfig(provider=ProviderKind.OLLAMA, model="llama3.2")
)

for event in client.stream(
    AIRequest(messages=(AIMessage(MessageRole.USER, "Say hello in one sentence."),))
):
    if isinstance(event, AIStreamDelta):
        print(event.content, end="")
    elif isinstance(event, AIStreamFinal):
        print(f"\nbackend={event.response.backend.provider}")
```

## Orchestrator Composition

`ai_orchestrator` returns neutral execution targets instead of depending on this
package. When a caller chooses to execute through `ai_provider`, adapt the target
at the boundary. See `examples/orchestrator_execution_target.py` for the minimal
mapping from `ai_orchestrator.ExecutionTarget` to `BackendConfig`.

That example also includes a caller-side `prepare_backend_config(...)` helper
that runs `ai_orchestrator.prepare_execution(...)`, adapts only ready execution
plans, and returns `None` for provider config when the prompt needs review or no
model satisfies the task profile. It does not execute a provider request.

For the next no-network step, `prepare_provider_request(...)` also builds an
`AIRequest` after orchestration is ready. The caller still decides whether and
when to create a client and execute the request.

For a small coding-oriented flow, see `examples/coding_assist.py`. It loads a
model catalog, builds a coding `TaskProfile`, runs orchestration, prints the
selected provider/model and reasons by default, and only calls a provider when
`--execute` is passed. Hosted execution still requires an explicit external
privacy class such as `--privacy external_allowed`.

Example dry run:

```powershell
python packages\ai_provider\examples\coding_assist.py `
  "Explain this failing test and suggest the smallest fix."
```

The example also accepts an optional provider-neutral system instruction:

```powershell
python packages\ai_provider\examples\coding_assist.py `
  "Explain this failing test and suggest the smallest fix." `
  --system "Be concise and preserve the user's intent."
```

When executing against local Ollama, the example can also start `ollama serve`
first:

```powershell
python packages\ai_provider\examples\coding_assist.py `
  "Explain this failing test and suggest the smallest fix." `
  --execute --start-ollama
```

Example hosted execution:

```powershell
$env:OPENAI_API_KEY = "..."
python packages\ai_provider\examples\coding_assist.py `
  "Explain this failing test and suggest the smallest fix." `
  --privacy external_allowed --provider openai --model gpt-5-mini --execute
```

## Environment Configuration

`BackendConfig.from_env()` reads these variables by default:

```text
AI_PROVIDER_KIND=ollama
AI_PROVIDER_MODEL=llama3.2
AI_PROVIDER_BASE_URL=http://localhost:11434
AI_PROVIDER_API_KEY=
AI_PROVIDER_TIMEOUT_SECONDS=60
```

For hosted providers, `AI_PROVIDER_API_KEY` is used first. If it is unset,
`BackendConfig.from_env()` falls back to `OPENAI_API_KEY` for `openai` and
`REQUESTY_API_KEY` for `requesty`. Do not commit API keys.

## Privacy Classes

Privacy classes are prototypes:

- `LOCAL_ONLY`
- `EXTERNAL_ALLOWED`
- `SENSITIVE_REVIEW_REQUIRED`
- `PUBLIC_OR_LOW_RISK`

The provider layer enforces that `LOCAL_ONLY` requests cannot be sent to external backends. The labels may change when cloud adapters and routing policy are implemented.

## Live Ollama Integration Test

Normal tests use mocks and do not require Ollama. To run the optional live test:

```powershell
$env:AI_PROVIDER_RUN_OLLAMA_INTEGRATION = "1"
$env:AI_PROVIDER_MODEL = "llama3.2"
python -m uv run pytest tests\integration\test_ollama_live.py
```

The live tests include non-streaming and streaming chat. They assume Ollama is
running and the configured model is available.

## Local Ollama Latency Benchmark

The orchestrator catalog can use local benchmark latency as a manual estimate.
Run this only when Ollama is already running and the configured model is pulled:

```powershell
python packages\ai_provider\examples\local_ollama_latency.py `
  --model llama3.2 --runs 3 --warmup-runs 1
```

If Ollama is installed but not running, the benchmark can start it first:

```powershell
python packages\ai_provider\examples\local_ollama_latency.py `
  --model llama3.2 --runs 3 --warmup-runs 1 --start-ollama
```

The benchmark sends a local-only coding-style prompt, prints measured response
latencies, and includes a TOML `[models.estimate]` snippet that can be copied
into `packages/ai_orchestrator/examples/model_catalog.toml` after review. It
does not persist observations or update routing policy automatically.

## Local Ollama Model Library

This package includes provider-side helpers for local Ollama model inventory and
explicit pulls. The helpers can list installed models, show local model details,
and pull a requested model while enforcing caller-provided disk constraints.

Example list:

```powershell
python packages\ai_provider\examples\ollama_models.py --list --start-ollama
```

Example constrained pull:

```powershell
python packages\ai_provider\examples\ollama_models.py `
  --pull llama3.2 `
  --start-ollama `
  --models-path D:\AI\Ollama\models `
  --min-free-gb 40 `
  --max-download-gb 80
```

Model pulls remain explicit for now. Future orchestrator-driven auto-provisioning
should call these provider primitives after a separate routing/policy decision,
so disk usage and model-library changes stay bounded by user-defined constraints.

## Live Hosted Integration Tests

Hosted integration tests are also skipped by default. They send prompts to an
external provider and require explicit credentials.

OpenAI:

```powershell
$env:AI_PROVIDER_RUN_HOSTED_INTEGRATION = "1"
$env:AI_PROVIDER_KIND = "openai"
$env:AI_PROVIDER_MODEL = "gpt-5-mini"
$env:OPENAI_API_KEY = "..."
python -m uv run pytest tests\integration\test_hosted_live.py
```

Requesty:

```powershell
$env:AI_PROVIDER_RUN_HOSTED_INTEGRATION = "1"
$env:AI_PROVIDER_KIND = "requesty"
$env:AI_PROVIDER_MODEL = "openai/gpt-5-mini"
$env:REQUESTY_API_KEY = "..."
python -m uv run pytest tests\integration\test_hosted_live.py
```
