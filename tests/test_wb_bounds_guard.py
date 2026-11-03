"""Regression tests: workbench path guard and bounded provider reads.

Covers the fix/wb-bounds-guard branch: model-proposed workbench paths must
stay inside the worktree, and provider response bodies must fail closed past
the shared transport bound instead of growing without limit.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from ai_provider import (
    AIMessage,
    AIRequest,
    AIStreamDelta,
    AIStreamFinal,
    MessageRole,
    PrivacyClass,
    ProviderError,
    ProviderErrorCategory,
    ProviderKind,
)
from ai_provider.adapters.openai_compatible import OpenAICompatibleChatClient
from ai_provider.config import BackendConfig
from ai_provider.http_transport import read_bounded

ROOT = Path(__file__).resolve().parents[1]


def _load_loop_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "unattended_development_loop", ROOT / "scripts" / "unattended-development-loop.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


loop = _load_loop_module()


def _client() -> OpenAICompatibleChatClient:
    return OpenAICompatibleChatClient(
        BackendConfig(
            provider=ProviderKind.REQUESTY,
            model="openai/gpt-5.1",
            api_key="requesty-key",
            timeout_seconds=9.0,
        )
    )


def _request() -> AIRequest:
    return AIRequest(
        messages=(AIMessage(MessageRole.USER, "Say hello."),),
        privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
    )


def _stub_propose(monkeypatch: pytest.MonkeyPatch, changes: dict[str, str]) -> None:
    def fake_propose(
        task: str,
        files: dict[str, str],
        out: Path,
        deadline_epoch: float,
        mode: str = "rewrite",
    ) -> dict:
        out.mkdir(parents=True, exist_ok=True)
        (out / "proposal.json").write_text(json.dumps({"changes": changes}), encoding="utf-8")
        receipt = {"at": "now", "valid": True, "mode": mode}
        (out / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        return receipt

    monkeypatch.setattr(loop, "propose", fake_propose)
    monkeypatch.setattr(
        loop, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="ok", stderr="")
    )


class _SizedReadResponse:
    """Stub with a real sized read() plus optional Content-Length."""

    def __init__(self, body: bytes, content_length: str | None = None) -> None:
        self._body = body
        self._pos = 0
        self._content_length = content_length
        self.read_calls = 0

    def __enter__(self) -> _SizedReadResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def getheader(self, name: str, default: Any = None) -> Any:
        if name.lower() == "content-length" and self._content_length is not None:
            return self._content_length
        return default

    def read(self, size: int = -1) -> bytes:
        self.read_calls += 1
        if size is None or size < 0:
            chunk = self._body[self._pos :]
            self._pos = len(self._body)
            return chunk
        chunk = self._body[self._pos : self._pos + size]
        self._pos += len(chunk)
        return chunk


class _StreamLinesResponse:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines

    def __enter__(self) -> _StreamLinesResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self._lines)


def _delta_chunk(content: str, finish: str | None = None) -> bytes:
    payload = {"choices": [{"delta": {"content": content}, "finish_reason": finish}]}
    return b"data: " + json.dumps(payload).encode("utf-8") + b"\n\n"


# --- Workbench path guard ---


def test_workbench_rejects_parent_escape_without_partial_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = tmp_path / "wt"
    worktree.mkdir()
    out = tmp_path / "out"
    _stub_propose(monkeypatch, {"ok.txt": "legit", "../escape.txt": "pwned"})

    receipt = loop.workbench_implement("task", {}, out, 9999999999.0, worktree, "branch")

    assert receipt["applied"] is False
    assert "rejected_path" in receipt
    assert not (worktree / "ok.txt").exists()
    assert not (tmp_path / "escape.txt").exists()
    persisted = json.loads((out / "receipt.json").read_text(encoding="utf-8"))
    assert persisted["applied"] is False


def test_workbench_rejects_absolute_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    worktree = tmp_path / "wt"
    worktree.mkdir()
    out = tmp_path / "out"
    absolute = tmp_path / "abs-evil.txt"
    _stub_propose(monkeypatch, {str(absolute): "pwned"})

    receipt = loop.workbench_implement("task", {}, out, 9999999999.0, worktree, "branch")

    assert receipt["applied"] is False
    assert "rejected_path" in receipt
    assert not absolute.exists()


def test_workbench_writes_nested_relative_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = tmp_path / "wt"
    worktree.mkdir()
    out = tmp_path / "out"
    _stub_propose(
        monkeypatch,
        {"pkg/sub/module.txt": "hello", "pkg/sub/../sibling.txt": "sibling"},
    )

    receipt = loop.workbench_implement("task", {}, out, 9999999999.0, worktree, "branch")

    assert receipt["applied"] is True
    assert (worktree / "pkg" / "sub" / "module.txt").read_text(encoding="utf-8") == "hello"
    assert (worktree / "pkg" / "sibling.txt").read_text(encoding="utf-8") == "sibling"


def test_workbench_rejects_symlink_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    worktree = tmp_path / "wt"
    worktree.mkdir()
    outside = tmp_path / "outside.txt"
    link = worktree / "linkdir"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks require privileges on this host")
    out = tmp_path / "out"
    _stub_propose(monkeypatch, {"linkdir/outside.txt": "pwned"})

    receipt = loop.workbench_implement("task", {}, out, 9999999999.0, worktree, "branch")

    assert receipt["applied"] is False
    assert not outside.exists()


# --- Bounded provider reads ---


def test_complete_rejects_oversized_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ai_provider.http_transport.MAX_RESPONSE_BYTES", 1024)
    body = b"x" * 2048

    def fake_urlopen(request: Any, timeout: float) -> _SizedReadResponse:
        return _SizedReadResponse(body, content_length=str(len(body)))

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", fake_urlopen)

    with pytest.raises(ProviderError) as error:
        _client().complete(_request())

    assert error.value.category is ProviderErrorCategory.NON_RETRYABLE
    assert "byte body limit" in str(error.value)


def test_complete_rejects_huge_content_length_before_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _SizedReadResponse(b"{}", content_length=str(100 * 1024 * 1024))

    def fake_urlopen(request: Any, timeout: float) -> _SizedReadResponse:
        return stub

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", fake_urlopen)

    with pytest.raises(ProviderError) as error:
        _client().complete(_request())

    assert "byte body limit" in str(error.value)
    assert stub.read_calls == 0


def test_complete_accepts_body_within_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ai_provider.http_transport.MAX_RESPONSE_BYTES", 1024)
    payload = {
        "choices": [
            {"message": {"role": "assistant", "content": "Hosted answer"}, "finish_reason": "stop"}
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    assert len(body) < 1024

    def fake_urlopen(request: Any, timeout: float) -> _SizedReadResponse:
        return _SizedReadResponse(body, content_length=str(len(body)))

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", fake_urlopen)

    response = _client().complete(_request())

    assert response.message.content == "Hosted answer"


def test_stream_rejects_oversized_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ai_provider.http_transport.MAX_RESPONSE_BYTES", 1024)
    lines = [_delta_chunk("y" * 100) for _ in range(50)]

    def fake_urlopen(request: Any, timeout: float) -> _StreamLinesResponse:
        return _StreamLinesResponse([*lines, b"data: [DONE]\n\n"])

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", fake_urlopen)

    with pytest.raises(ProviderError) as error:
        list(_client().stream(_request()))

    assert error.value.category is ProviderErrorCategory.NON_RETRYABLE
    assert "byte body limit" in str(error.value)


def test_stream_accepts_body_within_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ai_provider.http_transport.MAX_RESPONSE_BYTES", 1024)
    lines = [_delta_chunk("Hello "), _delta_chunk("world", finish="stop"), b"data: [DONE]\n\n"]

    def fake_urlopen(request: Any, timeout: float) -> _StreamLinesResponse:
        return _StreamLinesResponse(lines)

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", fake_urlopen)

    events = list(_client().stream(_request()))

    assert isinstance(events[0], AIStreamDelta)
    assert isinstance(events[-1], AIStreamFinal)
    assert events[-1].response.message.content == "Hello world"


class _NoArgReadResponse:
    """Legacy stub whose read() takes no size argument."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body


def test_read_bounded_supports_legacy_no_arg_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ai_provider.http_transport.MAX_RESPONSE_BYTES", 16)
    assert read_bounded(_NoArgReadResponse(b"small")) == b"small"
    with pytest.raises(ProviderError) as error:
        read_bounded(_NoArgReadResponse(b"x" * 17))
    assert error.value.category is ProviderErrorCategory.NON_RETRYABLE
