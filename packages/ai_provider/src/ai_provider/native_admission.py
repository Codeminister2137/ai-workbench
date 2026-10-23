"""Versioned native coding evidence and complete-request input admission.

The built-in receipts describe tool calling, not general model quality. Inventory
digests include the Ollama model manifest (weights, template and parameters).
Only metadata endpoints are consulted; admission never probes with inference.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import (
    AIRequest,
    AIResponse,
    AIStreamEvent,
    BackendInfo,
    ChatClient,
    FinishReason,
    UsageSource,
)
from ai_provider.errors import ProviderError, ProviderErrorCategory
from ai_provider.ollama_models import list_local_ollama_models
from ai_provider.ollama_runtime import get_ollama_version

# Bump when native request translation/tool-loop semantics invalidate the probes.
NATIVE_CONTRACT_VERSION = 2


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
        "2026-10-11 continuation-probe-20261011-231014: actual read/read/edit, "
        "correct fixture effect and untouched second file, no tool errors, "
        "thinking received/replayed; final marker-report check failed; quality unverified",
        contract_version=2,
    ),
    NativeToolEvidence(
        "qwen2.5-coder:14b",
        "9ec8897f747e246e970bc5cfdda85d22f1123dc2e3d34978a010a75968716849",
        "0.32.5",
        False,
        "2026-10-04 native-prompt-eval: textual requests, no actual tools on 20 paired tasks",
    ),
    NativeToolEvidence(
        "qwen3:14b",
        "bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8",
        "0.32.5",
        True,
        "2026-10-12 qwen-qualification-20261012-111559 (non-thinking) and "
        "qwen-qualification-20261012-113216 (thinking): actual read/edit, exact "
        "fixture effect, untouched second file, correct final marker, no tool errors; "
        "thinking received/replayed when enabled. Coding quality unverified; earlier "
        "thinking fixture duplicated a marker and another probe failed under a 120-second bound",
        contract_version=2,
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


@dataclass(frozen=True, slots=True)
class _MeasuredPrefix:
    scope: str
    messages: str
    length: int
    input_tokens: int


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _scope_fingerprint(value: Any) -> str | None:
    """Unverifiable options must retain absolute admission, not create an anchor."""
    try:
        return _fingerprint(value)
    except (TypeError, ValueError):
        return None


def estimate_coding_input_tokens(request: AIRequest) -> int:
    """Estimate complete coding input, including message metadata and tool schemas."""
    serialized = json.dumps(
        {
            "messages": [asdict(message) for message in request.messages],
            "tools": [tool.to_json_schema() for tool in request.tools],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    return (len(serialized) + 1) // 2


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
    deadline: float | None = None
    client_factory: Callable[[BackendConfig], ChatClient] | None = None
    measured_prefix_prototype: bool = False
    _prefix: _MeasuredPrefix | None = field(default=None, init=False, repr=False)
    _pending: tuple[str, str, int] | None = field(default=None, init=False, repr=False)

    @property
    def backend(self) -> BackendInfo:
        return self.client.backend

    def _request(self, request: AIRequest, config: BackendConfig | None = None) -> AIRequest:
        self._pending = None
        identity = None
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
            digest, version = installed_native_identity(config or self.config)
            identity = (digest, version)
            reason = native_tool_incompatibility(
                model, model_digest=digest, runtime_version=version
            )
            if reason:
                raise ProviderError(reason, category=ProviderErrorCategory.CONFIGURATION)
        # Kimi's reasoning and visible answer share its output allowance. Apply
        # the owner-approved default before sizing, never after admission.
        if (
            request.max_output_tokens is None
            and self.config.provider is ProviderKind.OPENCODE_GO
            and model == "kimi-k2.7-code"
        ):
            request = replace(request, max_output_tokens=16000)
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
        estimated = estimate_coding_input_tokens(request)
        estimate_kind = "estimated_utf8"
        if self.measured_prefix_prototype and self.config.provider is ProviderKind.OLLAMA:
            scope = _scope_fingerprint(
                {
                    "provider": self.config.provider.value,
                    "model": model,
                    "endpoint": self.config.base_url,
                    "identity": identity,
                    "contract": NATIVE_CONTRACT_VERSION,
                    "context": context,
                    "temperature": request.temperature,
                    "top_p": request.top_p,
                    "privacy": request.privacy_class,
                    "metadata": request.metadata,
                    "tools": [tool.to_json_schema() for tool in request.tools],
                }
            )
            messages = [asdict(message) for message in request.messages]
            prefix = self._prefix
            if (
                prefix is not None
                and scope is not None
                and prefix.scope == scope
                and len(messages) >= prefix.length
                and _fingerprint(messages[: prefix.length]) == prefix.messages
            ):
                appended = messages[prefix.length :]
                added_bytes = len(json.dumps(appended, ensure_ascii=False).encode("utf-8"))
                estimated = prefix.input_tokens + (added_bytes + 1) // 2 + 256 * len(appended)
                estimate_kind = "measured_prefix_estimated_append"
            else:
                self._prefix = None
            if scope is not None:
                self._pending = (scope, _fingerprint(messages), len(messages))
        self._report(
            f"native_input_admission: {estimate_kind} input_tokens={estimated} "
            f"output_tokens={output} framing_tokens=256 context_tokens={context}; "
            "verified_token_count=false"
        )
        if estimated + output + 256 > context:
            self._pending = None
            raise ProviderError(
                "Native model input does not fit the estimated context budget; "
                "complete instructions, schemas and history were preserved; no model request sent",
                category=ProviderErrorCategory.CONFIGURATION,
                provider=self.config.provider.value,
            )
        metadata = dict(request.metadata)
        if self.config.provider is ProviderKind.OLLAMA:
            metadata["ollama_context_length"] = context
            if self.measured_prefix_prototype:
                metadata["ollama_preserve_context"] = True
        return replace(request, metadata=metadata, max_output_tokens=output)

    def _report(self, message: str) -> None:
        if self.diagnostic:
            self.diagnostic(message)

    def complete(self, request: AIRequest) -> AIResponse:
        try:
            admitted = self._request(request, self._bounded_config())
            client = self._bounded_client()
            response = client.complete(admitted)
            self._bounded_config()
        except BaseException:
            self._prefix = self._pending = None
            raise
        pending, self._pending = self._pending, None
        self._prefix = None
        count = response.usage.input_tokens
        if (
            pending is not None
            and self.context_tokens is not None
            and response.usage.source is UsageSource.PROVIDER_REPORTED
            and type(count) is int
            and 0 < count <= self.context_tokens - (admitted.max_output_tokens or 0) - 256
            and response.finish_reason in (FinishReason.STOP, FinishReason.LENGTH)
            and response.backend.provider == self.config.provider.value
            and response.backend.model == self.config.model
            and response.backend.base_url == self.client.backend.base_url
        ):
            self._prefix = _MeasuredPrefix(*pending, count)
        return response

    def stream(self, request: AIRequest) -> Iterator[AIStreamEvent]:
        # Streaming remains on the absolute gate during this bounded prototype.
        self._prefix = None
        admitted = self._request(request, self._bounded_config())
        self._pending = None
        client = self._bounded_client()
        for event in client.stream(admitted):
            self._bounded_config()
            yield event
        self._bounded_config()

    def _bounded_config(self) -> BackendConfig:
        """Refuse expired turns and cap both admission probes and inference timeouts."""
        if self.deadline is None:
            return self.config
        remaining = self.deadline - time.perf_counter()
        if remaining <= 0:
            raise ProviderError(
                "Native coding deadline expired; no further model or tool actions admitted",
                category=ProviderErrorCategory.TIMEOUT,
            )
        return replace(self.config, timeout_seconds=min(self.config.timeout_seconds, remaining))

    def _bounded_client(self) -> ChatClient:
        config = self._bounded_config()
        if self.deadline is None:
            return self.client
        if self.client_factory is None:
            from ai_provider.factory import create_chat_client

            factory = create_chat_client
        else:
            factory = self.client_factory
        client = factory(config)
        self._bounded_config()
        return client


def prepare_native_coding_client(
    client: ChatClient,
    config: BackendConfig,
    args: Any,
    diagnostic: Callable[[str], None] | None,
    *,
    client_factory: Callable[[BackendConfig], ChatClient] | None = None,
) -> ChatClient:
    """Resolve existing catalog/resource limits for the actual selected model."""
    from pathlib import Path

    from ai_orchestrator import load_model_catalog

    from ai_provider.ollama_runtime import get_ollama_resource_profile

    measured_prefix = bool(getattr(args, "experimental_measured_prefix", False))
    if measured_prefix and config.provider is not ProviderKind.OLLAMA:
        raise ProviderError(
            "Experimental measured-prefix admission requires native Ollama coding tools",
            category=ProviderErrorCategory.CONFIGURATION,
        )
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
    return NativeCodingClient(
        client,
        config,
        capacity,
        diagnostic,
        deadline=getattr(getattr(args, "fallback_session", None), "deadline", None),
        client_factory=client_factory,
        measured_prefix_prototype=measured_prefix,
    )
