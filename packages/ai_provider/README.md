# ai-provider

Provider-agnostic AI request contracts, adapters, runtime and execution helpers.

This package is the infrastructure layer below orchestration and applications.
It owns provider-specific API calls, request/response translation, backend
identity, provider errors, streaming, tool-call normalization, and usage
metadata. It does not choose the best model, judge prompts, synthesize Council
answers, or implement job-search logic.

## Current Scope

- Neutral chat-first request/response contract.
- Provider identity, usage metadata, and prototype privacy classes.
- Ollama chat and streaming adapter.
- OpenAI-compatible Chat Completions adapter for OpenAI, Requesty, Google
  Gemini-compatible routes, and OpenCode Go.
- Shared Responses tools and streaming for Meta/OpenAI-compatible routes, with
  transient origin-bound native continuation. Meta enforces stateless encrypted
  reasoning replay and refuses Contributor variants; live coding quality remains
  separate from protocol support.
- Provider factory for configured chat clients.
- Baseten Chat Completions, streaming usage and tools, with an explicit event-key
  configuration helper and reasoning removed from successful response metadata.
- Experimental, opt-in OpenRouter free-only API client with per-call exact-price,
  tool-support and daily-quota checks; no deposit or paid fallback.
- OpenCode Go adapter with model discovery, per-request session headers and
  explicit unavailable allowance state; no paid overage or automatic switching.
- Local Ollama inventory, pull, runtime, and capability helpers.
- Compatibility imports for the agent-owned CLI and shared execution/storage helpers.
- Native Codex, Copilot, Antigravity and Kiro executors for approved routes.
- Same-tier usage fallback and explicit private configuration at the CLI boundary.
- Local chat transcripts, supervised research workers and foreground scheduling.

The adapters implement provider behavior. `ai_agent` owns the repository assistant
CLI and composes routing policy and tools. Existing research, transcript and
fallback helpers remain here; provider contracts do not own model selection or
report quality.

See the [interface specification](docs/interface.md) for the capability matrix.

OpenRouter root and choice-level errors use the same sanitized provider error
categories. An `error` finish without usable details is non-retryable; partial
answers and tool calls from that failed response are rejected. Existing eligible
quota/rate-limit fallback remains subject to routing, privacy and quality guards;
an unclassified error does not trigger fallback.

See [provider source state](docs/source-state.md) for dated source limits,
integration readiness and evaluation gaps, including Groq's token quotas. These
findings are shared with orchestration by reference; they are not live quota or
executable routing policy. [Installation guidance](../../docs/installation.md)
separates the Python workspace from optional external runtimes and clients.

For subscription/gateway choices and official agent SDK alternatives, start with
[access and agent integration options](docs/access-options.md). It links the dated
comparisons, model recommendations and remaining decision boundaries; external
IDE configuration or a stored key does not establish a working package adapter.

The [provider model recommendation catalog](docs/model-catalog.md) records suggested
models by access source, intended roles and evidence limits. It is a reference for
manual use and future automation, separate from the Orchestrator's runtime catalog.

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

## Baseten protocol integration

`ProviderKind.BASETEN` uses `https://inference.baseten.co/v1` and the existing
Chat Completions transport. Ordinary configurations resolve `BASETEN_API_KEY`;
an explicit `BackendConfig.api_key` takes precedence. Event access is separate:

```python
from ai_provider.adapters.baseten import baseten_hackathon_config
from ai_provider.factory import create_chat_client

# Configuration only: requires an already-loaded BASETEN_HACKATHON_API_KEY.
# Does not read .env, send a request or print the credential.
client = create_chat_client(baseten_hackathon_config())
```

The helper requires the event credential without personal/generic-key fallback,
selects `meta-models/muse-spark-open-1026`, and refuses request model overrides
that would leave that alias. Use this helper for event access rather than the
ordinary `BackendConfig.from_env` personal-key convention. Backend configuration
representations omit API keys.

Streaming requests ask for final usage. Separate reasoning fields are removed from
successful response/delta metadata; final text uses only the provider's `content`
field. Reported completion totals already include reasoning tokens. No raw
reasoning continuation is retained for this adapter. Error diagnostics remain
subject to the existing provider error policy.

This is offline protocol support, not live model acceptance or a billing cap.
No Baseten route is added to automatic selection/fallback. Verify actual credit
eligibility, balance, expiry and prevention of owner-funded charges before live
admission. Existing privacy checks still apply; published ZDR does not authorize
private payloads. See [source state](docs/source-state.md) for official links.

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

See the [CLI guide](../../docs/repo-coding-assistant.md) for modes, provider
selection, local runtime startup, external agents, chat, research and permissions.
The command is owned by `ai-agent`: argument registration lives in
`ai_agent.repo_assistant_args`; execution composition lives in
`ai_agent.repo_coding_assistant`. Old provider CLI imports remain compatibility
aliases and require `ai-agent`. Provider-core imports remain independent of it.
Neither a planned request nor an acceptance
`--plan` requires inference.

Research review supports an optional local tokenizer file with verified profile
checks and conservative fallback. The optional `research-token-count` dependency
group is needed for exact counting; tokenizer assets are not bundled or downloaded
automatically. See [review settings](../../docs/repo-assistant/research-review.md).

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

Authenticated OpenAI-compatible requests refuse HTTP redirects for inference,
streaming and model-catalog reads. Configure the final API endpoint directly;
credentials and prompts are never forwarded to a redirect destination.

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
