from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from ai_provider import (
    AIMessage,
    AIRequest,
    AIResponse,
    BackendInfo,
    BackendLocation,
    MessageRole,
    PrivacyClass,
)

_EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "packages"
    / "ai_provider"
    / "examples"
    / "local_ollama_latency.py"
)
_SPEC = importlib.util.spec_from_file_location("local_ollama_latency_example", _EXAMPLE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_EXAMPLE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _EXAMPLE
_SPEC.loader.exec_module(_EXAMPLE)

BenchmarkResult = _EXAMPLE.BenchmarkResult
build_benchmark_request = _EXAMPLE.build_benchmark_request
format_catalog_estimate = _EXAMPLE.format_catalog_estimate
run_latency_benchmark = _EXAMPLE.run_latency_benchmark


class FakeClient:
    def __init__(self, latencies_ms: tuple[float, ...]) -> None:
        self._latencies_ms = iter(latencies_ms)
        self.requests: list[AIRequest] = []

    @property
    def backend(self) -> BackendInfo:
        return BackendInfo(
            provider="ollama",
            model="llama3.2",
            location=BackendLocation.LOCAL,
        )

    def complete(self, request: AIRequest) -> AIResponse:
        self.requests.append(request)
        return AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, "benchmarked"),
            backend=self.backend,
            latency_ms=next(self._latencies_ms),
        )

    def stream(self, request: AIRequest):
        raise NotImplementedError


def test_build_benchmark_request_is_local_only() -> None:
    request = build_benchmark_request("Explain a failing test.", max_output_tokens=64)

    assert request.messages == (AIMessage(MessageRole.USER, "Explain a failing test."),)
    assert request.privacy_class is PrivacyClass.LOCAL_ONLY
    assert request.temperature == 0
    assert request.max_output_tokens == 64
    assert request.metadata["benchmark"] == "local_ollama_latency"


def test_run_latency_benchmark_skips_warmup_and_summarizes_completed_runs() -> None:
    client = FakeClient((1000, 2000, 4000, 6000))

    result = run_latency_benchmark(
        client,
        prompt="Explain a failing test.",
        runs=3,
        warmup_runs=1,
        max_output_tokens=64,
    )

    assert len(client.requests) == 4
    assert [sample.latency_seconds for sample in result.samples] == [2.0, 4.0, 6.0]
    assert result.mean_latency_seconds == 4.0
    assert result.median_latency_seconds == 4.0
    assert result.min_latency_seconds == 2.0
    assert result.max_latency_seconds == 6.0
    assert result.typical_latency_seconds == 4.0


def test_format_catalog_estimate_produces_toml_snippet() -> None:
    result = BenchmarkResult(
        provider="ollama",
        model="llama3.2",
        prompt="Explain a failing test.",
        warmup_runs=1,
        samples=(
            _EXAMPLE.BenchmarkSample(run_number=1, latency_seconds=2.0),
            _EXAMPLE.BenchmarkSample(run_number=2, latency_seconds=4.0),
        ),
    )

    snippet = format_catalog_estimate(result)

    assert "typical_latency_seconds = 3" in snippet
    assert 'source = "local benchmark: 2 runs, 1 warmup' in snippet
    assert "input_cost_per_million_tokens = 0" in snippet
    assert "output_cost_per_million_tokens = 0" in snippet
