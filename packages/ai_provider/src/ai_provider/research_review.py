"""Local research review adapter for neutral plans and bounded full-evidence calls."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from ai_orchestrator.review import ReviewMode, ReviewSettings, allocate_review

from ai_provider.config import BackendConfig
from ai_provider.contracts import (
    AIRequest,
    AIResponse,
    AIStreamEvent,
    BackendInfo,
    BackendLocation,
    ChatClient,
    FinishReason,
    PrivacyClass,
)
from ai_provider.factory import create_chat_client
from ai_provider.ollama_models import show_ollama_model
from ai_provider.ollama_runtime import get_ollama_version
from ai_provider.research_execution import _validate_local_runtime


def review_runtime_options(mode: ReviewMode, model_details: dict[str, Any]) -> dict[str, object]:
    """Map only verified native controls; boolean thinking and effort are distinct."""
    if mode is ReviewMode.DEFAULT:
        return {}
    if "thinking" not in model_details.get("capabilities", []):
        raise ValueError("Selected model does not advertise native thinking support")
    architecture = model_details.get("model_info", {}).get("general.architecture")
    if architecture == "qwen3":
        control: bool | str = mode is ReviewMode.DELIBERATIVE
    elif architecture == "gptoss" and mode is ReviewMode.DELIBERATIVE:
        control = "high"
    else:
        raise ValueError(f"Unsupported native review mode {mode.value} for {architecture!r}")
    # Newer runtimes advertise exact supported values. Unsupported names can
    # silently use the runtime default, so never send an unverified explicit value.
    # Older installed runtimes here expose capability + architecture only.
    if "thinking" in model_details:
        thinking = model_details["thinking"]
        values = thinking.get("values") if isinstance(thinking, dict) else None
        if not isinstance(values, list) or not any(
            type(value) is type(control) and value == control for value in values
        ):
            raise ValueError(
                f"Installed model does not support explicit thinking value {control!r}"
            )
    return {"ollama_thinking": control}


def review_input_token_upper_bound(request: AIRequest) -> int:
    """Use UTF-8 bytes plus per-message framing when no tokenizer is available.

    This intentionally conservative bound can refuse large evidence payloads that
    a model tokenizer could fit. It never silently reduces report/source evidence.
    Review requests have two plain messages and no tool schemas or tool calls.
    """
    if request.tools or any(message.tool_calls for message in request.messages):
        raise ValueError("Research reviewers cannot receive tools or tool calls")
    return sum(len(message.content.encode("utf-8")) + 256 for message in request.messages)


@dataclass
class ResearchReviewClient:
    """One non-streaming review with at most one stronger output-truncation retry."""

    config: BackendConfig
    mode: ReviewMode
    context_tokens: int
    settings: ReviewSettings
    deadline: float | None
    details: dict[str, object] = field(default_factory=dict)
    client_factory: Callable[[BackendConfig], ChatClient] = create_chat_client
    model_inspector: Callable[..., dict[str, Any]] = show_ollama_model
    clock: Callable[[], float] = time.perf_counter
    tokenizer_file: Path | None = None
    version_inspector: Callable[..., str | None] = get_ollama_version

    @property
    def backend(self) -> BackendInfo:
        return BackendInfo("ollama", self.config.model, BackendLocation.LOCAL, self.config.base_url)

    def complete(self, request: AIRequest) -> AIResponse:
        _validate_local_runtime(self.config)
        if self.deadline is not None and not math.isfinite(self.deadline):
            raise ValueError("Review deadline must be finite")
        if not math.isfinite(self.config.timeout_seconds):
            raise ValueError("Review configuration timeout must be finite")
        if request.privacy_class is not PrivacyClass.LOCAL_ONLY:
            raise ValueError("Research reviewer requires local-only privacy")
        if request.model is not None and request.model != self.config.model:
            raise ValueError("Review request model differs from selected configuration")
        # One absolute deadline covers capability inspection and both attempts,
        # including callers without an outer run deadline.
        deadline = min(
            self.deadline if self.deadline is not None else float("inf"),
            self.clock() + self.settings.timeout_seconds,
        )
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise ValueError("Review deadline exhausted before capability inspection")
        model_details = self.model_inspector(
            self.config.model, self.config.base_url, timeout_seconds=min(10.0, remaining)
        )
        options = review_runtime_options(self.mode, model_details)
        for key, value in model_details.get("model_info", {}).items():
            if key.endswith(".context_length") and isinstance(value, int):
                if self.context_tokens > value:
                    raise ValueError("Configured review context exceeds installed model capacity")
        input_bound = review_input_token_upper_bound(request)
        input_method = "utf8_bytes_plus_framing"
        self.details.pop("tokenizer_fallback_reason", None)
        if self.tokenizer_file is not None:
            from ai_provider.research_token_count import count_review_input_tokens

            remaining = deadline - self.clock()
            if remaining <= 0:
                raise ValueError("Review deadline exhausted before tokenizer inspection")
            version = self.version_inspector(
                self.config.base_url, timeout_seconds=min(2.0, remaining)
            )
            try:
                counted_request = replace(
                    request, model=self.config.model, metadata={**request.metadata, **options}
                )
                input_bound = count_review_input_tokens(
                    counted_request, model_details, self.tokenizer_file, runtime_version=version
                )
                input_method = "verified_local_tokenizer"
            except ValueError as error:
                self.details["tokenizer_fallback_reason"] = str(error)
        attempts: list[dict[str, object]] = []
        self.details.update(
            mode=self.mode.value,
            context_tokens=self.context_tokens,
            input_token_upper_bound=input_bound,
            input_bound_method=input_method,
            attempts=attempts,
        )
        prior_output = None
        for attempt in range(2):
            allocation = allocate_review(
                self.settings,
                context_tokens=self.context_tokens,
                input_token_upper_bound=input_bound,
                remaining_seconds=deadline - self.clock(),
                prior_output_tokens=prior_output,
            )
            timeout = min(self.config.timeout_seconds, allocation.timeout_seconds)
            client = self.client_factory(replace(self.config, timeout_seconds=timeout))
            prepared = replace(
                request,
                max_output_tokens=allocation.max_output_tokens,
                metadata={
                    **request.metadata,
                    **options,
                    "ollama_context_length": self.context_tokens,
                },
                temperature=request.temperature if request.temperature is not None else 0.2,
            )
            record: dict[str, object] = {
                "attempt": attempt + 1,
                "max_output_tokens": allocation.max_output_tokens,
                "timeout_seconds": timeout,
                "status": "running",
            }
            attempts.append(record)
            try:
                response = client.complete(prepared)
            except Exception:
                record["status"] = "failed"
                raise
            record.update(status="completed", finish_reason=response.finish_reason.value)
            if self.clock() >= deadline:
                record["status"] = "deadline_exceeded"
                raise ValueError("Review returned after its deadline")
            if response.finish_reason is FinishReason.LENGTH:
                record["status"] = "truncated"
                if attempt == 0:
                    prior_output = allocation.max_output_tokens
                    continue
                raise ValueError("Review remained output-truncated after one bounded retry")
            if response.finish_reason is FinishReason.ERROR or not response.message.content.strip():
                record["status"] = "invalid_final_answer"
                raise ValueError("Review produced an error or no visible final answer")
            return response
        raise AssertionError("unreachable")

    def stream(self, request: AIRequest) -> Iterator[AIStreamEvent]:
        raise ValueError("Research review requires complete final-answer and truncation checks")
        yield  # Keep the ChatClient iterator contract without starting a stream.
