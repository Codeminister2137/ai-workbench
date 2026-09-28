# ai-provider

Provider-agnostic AI request contracts, adapters, runtime helpers, and coding
assistant support.

This package is the infrastructure layer below orchestration and applications.
It owns provider-specific API calls, request/response translation, backend
identity, provider errors, streaming, tool-call normalization, and usage
metadata. It does not choose the best model, judge prompts, synthesize Council
answers, or implement job-search logic.

## Current Scope

- Neutral chat-first request/response contract.
- Provider identity, usage metadata, and prototype privacy classes.
- Ollama chat and streaming adapter.
- OpenAI-compatible Chat Completions adapter for OpenAI, Requesty, and Google
  Gemini-compatible routes.
- Provider factory for configured chat clients.
- Local Ollama inventory, pull, runtime, and capability helpers.
- Repo-aware coding assistant CLI support.
- Codex CLI executor integration for approved external-agent routes.

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

## Configuration

`BackendConfig.from_env()` reads:

```text
AI_PROVIDER_KIND=ollama
AI_PROVIDER_MODEL=llama3.2
AI_PROVIDER_BASE_URL=http://localhost:11434
AI_PROVIDER_API_KEY=
AI_PROVIDER_TIMEOUT_SECONDS=60
```

For hosted providers, `AI_PROVIDER_API_KEY` is used first. Provider-specific
fallbacks include `OPENAI_API_KEY`, `REQUESTY_API_KEY`, `GEMINI_API_KEY`, and
`GOOGLE_API_KEY`. Do not commit real API keys.

## Repo-Aware Coding Assistant

The stable workspace command is:

```powershell
python -m uv run ai-assistant "Explain this repository structure."
```

The Windows convenience wrapper is:

```powershell
.\scripts\repo-assistant.ps1 "Explain this repository structure."
```

See `docs/repo-coding-assistant.md` for modes, provider selection, local Ollama
startup, Codex CLI routes, transcript logging, approval policies, and native
tool execution.

## Orchestrator Composition

`ai_orchestrator` returns neutral execution targets instead of depending on this
package. When a caller chooses to execute through `ai_provider`, adapt the target
at the boundary.

Examples:

- `examples/orchestrator_execution_target.py`
- `examples/coding_assist.py`
- `examples/live_delegation_runner.py`

## Local Ollama Helpers

Examples:

- `examples/ollama_models.py` - list, inspect, and explicitly pull local models
- `examples/local_ollama_latency.py` - run a local benchmark and print catalog
  estimate snippets

Model pulls remain explicit. Future orchestrator-driven provisioning should call
these primitives only after a separate routing or provisioning-policy decision.

## Tests

Normal tests use mocks and do not require Ollama or hosted credentials:

```powershell
python -m uv run pytest tests\test_ollama_adapter.py tests\test_openai_compatible_adapter.py
```

Optional live Ollama tests:

```powershell
$env:AI_PROVIDER_RUN_OLLAMA_INTEGRATION = "1"
$env:AI_PROVIDER_MODEL = "llama3.2"
python -m uv run pytest tests\integration\test_ollama_live.py
```

Optional hosted integration tests:

```powershell
$env:AI_PROVIDER_RUN_HOSTED_INTEGRATION = "1"
$env:AI_PROVIDER_KIND = "openai"
$env:AI_PROVIDER_MODEL = "gpt-5-mini"
$env:OPENAI_API_KEY = "..."
python -m uv run pytest tests\integration\test_hosted_live.py
```
