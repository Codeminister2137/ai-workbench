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
