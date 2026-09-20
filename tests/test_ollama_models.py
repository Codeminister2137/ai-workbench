from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ai_provider import (
    OllamaPullConstraints,
    ProviderError,
    ProviderErrorCategory,
    list_local_ollama_models,
    pull_ollama_model,
    stream_ollama_model_pull,
)


class FakeHttpResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self) -> FakeHttpResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class FakeStreamingHttpResponse:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = payloads

    def __enter__(self) -> FakeStreamingHttpResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def __iter__(self):
        for payload in self.payloads:
            yield json.dumps(payload).encode("utf-8") + b"\n"


def test_list_local_ollama_models_parses_tags_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> FakeHttpResponse:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return FakeHttpResponse(
            {
                "models": [
                    {
                        "name": "llama3.2:latest",
                        "model": "llama3.2:latest",
                        "size": 2_019_393_189,
                        "digest": "digest",
                        "modified_at": "2026-01-01T00:00:00Z",
                        "details": {"parameter_size": "3.2B"},
                    }
                ]
            }
        )

    monkeypatch.setattr("ai_provider.ollama_models.urlopen", fake_urlopen)

    models = list_local_ollama_models("http://ollama.test", timeout_seconds=3.0)

    assert captured == {"url": "http://ollama.test/api/tags", "timeout": 3.0}
    assert len(models) == 1
    assert models[0].model == "llama3.2:latest"
    assert models[0].size_bytes == 2_019_393_189
    assert models[0].details["parameter_size"] == "3.2B"


def test_stream_ollama_model_pull_parses_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> FakeStreamingHttpResponse:
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeStreamingHttpResponse(
            [
                {"status": "pulling manifest"},
                {
                    "status": "pulling layer",
                    "digest": "sha256:abc",
                    "total": 100,
                    "completed": 40,
                },
                {"status": "success"},
            ]
        )

    monkeypatch.setattr("ai_provider.ollama_models.urlopen", fake_urlopen)

    events = list(stream_ollama_model_pull("llama3.2", "http://ollama.test"))

    assert captured["url"] == "http://ollama.test/api/pull"
    assert captured["body"] == {"model": "llama3.2", "stream": True}
    assert [event.status for event in events] == ["pulling manifest", "pulling layer", "success"]
    assert events[1].total_bytes == 100
    assert events[1].completed_bytes == 40


def test_pull_ollama_model_rejects_download_larger_than_constraint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("ai_provider.ollama_models.ensure_ollama_server", lambda base_url: None)
    monkeypatch.setattr(
        "ai_provider.ollama_models.stream_ollama_model_pull",
        lambda model, base_url, *, timeout_seconds: iter(
            [
                _progress("pulling manifest"),
                _progress("pulling layer", total_bytes=200),
            ]
        ),
    )

    constraints = OllamaPullConstraints(
        min_free_bytes=1,
        max_download_bytes=100,
        models_path=tmp_path,
    )

    with pytest.raises(ProviderError) as error:
        pull_ollama_model("too-large", constraints=constraints)

    assert error.value.category is ProviderErrorCategory.CONFIGURATION
    assert "maximum download size" in str(error.value)


def test_pull_ollama_model_returns_result_when_constraints_pass(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("ai_provider.ollama_models.ensure_ollama_server", lambda base_url: None)
    monkeypatch.setattr(
        "ai_provider.ollama_models.stream_ollama_model_pull",
        lambda model, base_url, *, timeout_seconds: iter(
            [
                _progress("pulling layer", total_bytes=100, completed_bytes=100),
                _progress("success"),
            ]
        ),
    )

    result = pull_ollama_model(
        "llama3.2",
        constraints=OllamaPullConstraints(
            min_free_bytes=1,
            max_download_bytes=200,
            models_path=tmp_path,
        ),
    )

    assert result.model == "llama3.2"
    assert result.max_reported_total_bytes == 100
    assert [event.status for event in result.events] == ["pulling layer", "success"]


def test_pull_ollama_model_calls_progress_callback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("ai_provider.ollama_models.ensure_ollama_server", lambda base_url: None)
    monkeypatch.setattr(
        "ai_provider.ollama_models.stream_ollama_model_pull",
        lambda model, base_url, *, timeout_seconds: iter(
            [
                _progress("pulling layer", total_bytes=100, completed_bytes=50),
                _progress("success"),
            ]
        ),
    )
    events = []

    pull_ollama_model(
        "llama3.2",
        constraints=OllamaPullConstraints(min_free_bytes=1, models_path=tmp_path),
        progress_callback=events.append,
    )

    assert [event.status for event in events] == ["pulling layer", "success"]


def _progress(
    status: str,
    *,
    total_bytes: int | None = None,
    completed_bytes: int | None = None,
):
    from ai_provider import OllamaPullProgress

    return OllamaPullProgress(
        status=status,
        total_bytes=total_bytes,
        completed_bytes=completed_bytes,
    )
