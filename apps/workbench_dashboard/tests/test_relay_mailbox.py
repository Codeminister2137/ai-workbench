"""Host-initiated mailbox relay: protocol, validation, timeouts, cleanup."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from relay_mailbox import (
    HostMediator,
    RelayError,
    RelayGrant,
    WorkerClient,
    validate_request,
)

GRANT = RelayGrant(run_id="run", model="fixed")


def _run_turn(tmp_path: Path, complete, messages, timeout_s=10.0):
    mediator = HostMediator(tmp_path, GRANT, complete)
    outcome: dict = {}

    def serve():
        try:
            outcome["served"] = mediator.serve_once(timeout_s=timeout_s)
        except Exception as exc:  # noqa: BLE001 - test capture
            outcome["error"] = exc

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        outcome["result"] = WorkerClient(tmp_path, GRANT).complete(messages, timeout_s=timeout_s)
    except Exception as exc:  # noqa: BLE001 - test capture
        outcome["error"] = exc
    thread.join(timeout=timeout_s + 5)
    return outcome


def test_happy_path_returns_callback_result(tmp_path: Path):
    outcome = _run_turn(
        tmp_path,
        lambda model, messages: {"text": "synthetic", "model": model},
        [{"role": "user", "content": "hi"}],
    )
    assert outcome["result"] == {"text": "synthetic", "model": "fixed"}
    assert outcome["served"] is True
    assert list(tmp_path.iterdir()) == []


def test_wrong_model_refused(tmp_path: Path):
    mediator = HostMediator(tmp_path, GRANT, lambda m, msgs: {})
    (tmp_path / "request.json").write_text(
        json.dumps({"id": "t", "model": "other", "messages": [{"role": "user", "content": "x"}]}),
        encoding="utf-8",
    )
    assert mediator.serve_once(timeout_s=5) is True
    response = json.loads((tmp_path / "response.json").read_text(encoding="utf-8"))
    assert response["id"] == "t"
    assert "grant" in response["error"]


def test_malformed_request_answered_without_callback(tmp_path: Path):
    calls = []
    mediator = HostMediator(tmp_path, GRANT, lambda m, msgs: calls.append(1) or {})
    (tmp_path / "request.json").write_text("not json", encoding="utf-8")
    assert mediator.serve_once(timeout_s=5) is True
    assert calls == []
    response = json.loads((tmp_path / "response.json").read_text(encoding="utf-8"))
    assert response["id"] == "unknown"


def test_callback_exception_reports_class_only(tmp_path: Path):
    def boom(model, messages):
        raise RuntimeError("sk-secret-should-never-leak")

    outcome = _run_turn(tmp_path, boom, [{"role": "user", "content": "hi"}])
    assert isinstance(outcome["error"], RelayError)
    assert "sk-secret" not in str(outcome["error"])
    assert "RuntimeError" in str(outcome["error"])


def test_worker_timeout_when_host_silent(tmp_path: Path):
    client = WorkerClient(tmp_path, GRANT)
    with pytest.raises(RelayError, match="timed out"):
        client.complete([{"role": "user", "content": "hi"}], timeout_s=0.3)


def test_host_timeout_without_request(tmp_path: Path):
    mediator = HostMediator(tmp_path, GRANT, lambda m, msgs: {})
    assert mediator.serve_once(timeout_s=0.2) is False


def test_response_id_mismatch_rejected(tmp_path: Path):
    (tmp_path / "response.json").write_text(
        json.dumps({"id": "foreign", "result": {"text": "x"}}), encoding="utf-8"
    )
    client = WorkerClient(tmp_path, GRANT)
    with pytest.raises(RelayError, match="mismatch"):
        client.complete([{"role": "user", "content": "hi"}], timeout_s=5)


def test_oversize_request_refused(tmp_path: Path):
    big = "x" * (64 * 1024 + 1)
    (tmp_path / "request.json").write_text(
        json.dumps({"id": "t", "model": "fixed", "messages": [{"role": "user", "content": big}]}),
        encoding="utf-8",
    )
    mediator = HostMediator(tmp_path, GRANT, lambda m, msgs: {})
    assert mediator.serve_once(timeout_s=5) is True
    response = json.loads((tmp_path / "response.json").read_text(encoding="utf-8"))
    assert "cap" in response["error"]


def test_validate_request_shapes() -> None:
    good = {"id": "t", "model": "fixed", "messages": [{"role": "user", "content": "x"}]}
    assert validate_request(good, GRANT)[0] == "t"
    for bad in (
        [],
        {**good, "id": ""},
        {**good, "model": "other"},
        {**good, "messages": []},
        {**good, "messages": [{"role": "tool", "content": "x"}]},
        {**good, "messages": [{"role": "user", "content": 42}]},
        {**good, "messages": [{"role": "user", "content": "x", "extra": 1}]},
    ):
        with pytest.raises(RelayError):
            validate_request(bad, GRANT)
