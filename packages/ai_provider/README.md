# ai-provider

Provider-agnostic AI contracts and adapters.

This package is the infrastructure layer below orchestration and applications. It owns provider-specific API calls, request/response translation, backend identity, provider errors, and usage metadata. It does not choose the best model, judge prompts, synthesize Council answers, or implement job-search logic.

## Current Scope

- Neutral chat-first request/response contract.
- Prototype privacy classes.
- Backend identity and model capabilities.
- Provider-reported usage metadata where available.
- Ollama chat adapter.
- Provider factory for configured chat clients.

Requesty and direct hosted providers are intentionally not implemented yet. The contract is shaped so those adapters can be added later without changing application-facing code.

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

## Environment Configuration

`BackendConfig.from_env()` reads these variables by default:

```text
AI_PROVIDER_KIND=ollama
AI_PROVIDER_MODEL=llama3.2
AI_PROVIDER_BASE_URL=http://localhost:11434
AI_PROVIDER_TIMEOUT_SECONDS=60
```

Only `ollama` is implemented in the first milestone.

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

The test assumes Ollama is running and the configured model is available.
