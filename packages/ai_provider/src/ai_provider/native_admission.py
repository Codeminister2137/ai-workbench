"""Versioned native coding evidence and complete-request input admission.

The built-in receipts describe tool calling, not general model quality. Inventory
digests include the Ollama model manifest (weights, template and parameters).
Only metadata endpoints are consulted; admission never probes with inference.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, replace
from typing import Any

from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import AIRequest, AIResponse, AIStreamEvent, BackendInfo, ChatClient
from ai_provider.errors import ProviderError, ProviderErrorCategory
from ai_provider.ollama_models import list_local_ollama_models
from ai_provider.ollama_runtime import get_ollama_version

# Bump when native request translation/tool-loop semantics invalidate the probes.
NATIVE_CONTRACT_VERSION = 1


@dataclass(frozen=True, slots=True)
class NativeToolEvidence:
    """One bounded tool-call receipt tied to a runtime and model manifest."""

    model: str
    model_digest: str
    runtime_version: str
    supported: bool
    receipt: str
    # Receipt revision stays pinned when the active adapter/loop revision changes.
    contract_version: int = 1


NATIVE_TOOL_EVIDENCE = (
    NativeToolEvidence(
        "gpt-oss:20b",
        "17052f91a42e97930aa6e28a6c6c06a983e6a58dbb00434885a0cf5313e376f7",
        "0.32.5",
        True,
        "2026-10-04 native-prompt-eval-gpt: actual tools on 20 paired tasks; "
        "19/20 strict effect checks per prompt, one newline miss",
    ),
    NativeToolEvidence(
        "qwen2.5-coder:14b",
        "9ec8897f747e246e970bc5cfdda85d22f1123dc2e3d34978a010a75968716849",
        "0.32.5",
        False,
        "2026-10-04 native-prompt-eval: textual requests, no actual tools on 20 paired tasks",
    ),
)


def native_tool_incompatibility(
    model: str,
    *,
    model_digest: str | None,
    runtime_version: str | None,
    contract_version: int = NATIVE_CONTRACT_VERSION,
) -> str | None:
    """Refuse unknown/stale receipts; never substitute the requested model."""
    evidence = next((item for item in NATIVE_TOOL_EVIDENCE if item.model == model), None)
    if evidence is None:
        return f"Native tool compatibility is unknown for {model}; bounded acceptance is required"
    if (
        not model_digest
        or not runtime_version
        or model_digest != evidence.model_digest
        or runtime_version != evidence.runtime_version
        or contract_version != evidence.contract_version
    ):
        return f"Native tool compatibility evidence is stale or unverifiable for {model}"
    if not evidence.supported:
        return f"Native tool execution failed the runtime compatibility probe for {model}"
    return None


def native_coding_catalog(catalog: tuple[Any, ...], profile: Any) -> tuple[Any, ...]:
    """Apply ADR-041 locally without weakening explicit route/model constraints.

    This is static eligibility only; each actual local turn rechecks the receipt.
    Hosted candidates still pass the existing orchestrator privacy/quality gates.
    """
    if profile.user_model_override or profile.user_route_id_override:
        return catalog
    supported = {
        item.model
        for item in NATIVE_TOOL_EVIDENCE
        if item.supported and item.contract_version == NATIVE_CONTRACT_VERSION
    }
    return tuple(
        item
        for item in catalog
        if item.backend.provider != "ollama" or item.backend.model in supported
    )


def installed_native_identity(config: BackendConfig) -> tuple[str | None, str | None]:
    """Read fresh metadata without starting a runtime or loading a model."""
    timeout = min(config.timeout_seconds, 2.0)
    version = get_ollama_version(config.base_url, timeout_seconds=timeout)
    models = list_local_ollama_models(config.base_url, timeout_seconds=timeout)
    digest = next((item.digest for item in models if item.name == config.model), None)
    return digest, version


@dataclass(slots=True)
class NativeCodingClient:
    """Check every turn, including history, before forwarding a coding request.

    The UTF-8/2 estimate and 256-token framing reserve follow the existing
    research admission convention. They may reject a request an exact tokenizer
    would fit, and are not proof of native token capacity. No content is trimmed.
    """

    client: ChatClient
    config: BackendConfig
    context_tokens: int | None
    diagnostic: Callable[[str], None] | None = None

    @property
    def backend(self) -> BackendInfo:
        return self.client.backend

    def _request(self, request: AIRequest) -> AIRequest:
        model = request.model or self.config.model
        if model != self.config.model:
            raise ProviderError(
                "Native admission model differs from the selected model; no request sent",
                category=ProviderErrorCategory.CONFIGURATION,
            )
        if self.config.provider is ProviderKind.OLLAMA:
            if not any(item.model == model for item in NATIVE_TOOL_EVIDENCE):
                raise ProviderError(
                    f"Native tool compatibility is unknown for {model}; no model request sent",
                    category=ProviderErrorCategory.CONFIGURATION,
                )
            digest, version = installed_native_identity(self.config)
            reason = native_tool_incompatibility(
                model, model_digest=digest, runtime_version=version
            )
            if reason:
                raise ProviderError(reason, category=ProviderErrorCategory.CONFIGURATION)
        context = self.context_tokens
        if context is None:
            self._report(
                "native_input_admission: unknown context capacity; no verified token count"
            )
            return request
        if type(context) is not int or context <= 0:
            raise ProviderError(
                "Invalid native context budget", category=ProviderErrorCategory.CONFIGURATION
            )
        output = request.max_output_tokens
        if output is None:
            output = min(8192, context // 4)
        if type(output) is not int or output <= 0:
            raise ProviderError(
                "Invalid native output budget", category=ProviderErrorCategory.CONFIGURATION
            )
        serialized = json.dumps(
            {
                "messages": [asdict(message) for message in request.messages],
                "tools": [tool.to_json_schema() for tool in request.tools],
            },
            ensure_ascii=False,
        ).encode("utf-8")
        estimated = (len(serialized) + 1) // 2
        self._report(
            f"native_input_admission: estimated_utf8 input_tokens={estimated} "
            f"output_tokens={output} framing_tokens=256 context_tokens={context}; "
            "verified_token_count=false"
        )
        if estimated + output + 256 > context:
            raise ProviderError(
                "Native model input does not fit the estimated context budget; "
                "complete instructions, schemas and history were preserved; no model request sent",
                category=ProviderErrorCategory.CONFIGURATION,
                provider=self.config.provider.value,
            )
        metadata = dict(request.metadata)
        if self.config.provider is ProviderKind.OLLAMA:
            metadata["ollama_context_length"] = context
        return replace(request, metadata=metadata, max_output_tokens=output)

    def _report(self, message: str) -> None:
        if self.diagnostic:
            self.diagnostic(message)

    def complete(self, request: AIRequest) -> AIResponse:
        return self.client.complete(self._request(request))

    def stream(self, request: AIRequest) -> Iterator[AIStreamEvent]:
        yield from self.client.stream(self._request(request))


def prepare_native_coding_client(
    client: ChatClient, config: BackendConfig, args: Any, diagnostic: Callable[[str], None] | None
) -> ChatClient:
    """Resolve existing catalog/resource limits for the actual selected model."""
    from pathlib import Path

    from ai_orchestrator import load_model_catalog

    from ai_provider.ollama_runtime import get_ollama_resource_profile

    catalog = load_model_catalog(
        getattr(args, "catalog", Path("packages/ai_orchestrator/examples/model_catalog.toml"))
    )
    limits = [
        item.backend.context_limits
        for item in catalog
        if item.backend.provider == config.provider.value and item.backend.model == config.model
    ]
    windows = [item.context_window_tokens for item in limits if item.context_window_tokens]
    capacity = min(windows) if windows else None
    if config.provider is ProviderKind.OLLAMA:
        resource = getattr(args, "ollama_profile", None)
        defaults = [item.runtime_context_tokens for item in limits if item.runtime_context_tokens]
        runtime = (
            get_ollama_resource_profile(resource).context_length
            if resource
            else (min(defaults) if defaults else None)
        )
        if runtime is None:
            raise ProviderError(
                "Native local runtime context is unknown; select a known catalog/resource profile",
                category=ProviderErrorCategory.CONFIGURATION,
            )
        capacity = min(capacity, runtime) if capacity else runtime
    return NativeCodingClient(client, config, capacity, diagnostic)
