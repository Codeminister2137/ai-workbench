"""Unit tests for the proxy scoped model callback (no network)."""

import pytest

from apps.workbench_dashboard.proxy_model_callback import (
    CallbackExhausted,
    ScopedGrant,
    make_scoped_callback,
)


def _raw(text="ok", usage=None):
    def complete(model, messages, timeout_s):
        return {"text": text, "usage": usage or {"total_tokens": 10}}

    return complete


def test_happy_path_returns_result_dict():
    cb = make_scoped_callback(
        grant=ScopedGrant(model="m", max_calls=2, token_budget=100),
        complete=_raw(),
    )
    assert cb("m", [{"role": "user", "content": "hi"}])["text"] == "ok"


def test_wrong_model_refused():
    cb = make_scoped_callback(
        grant=ScopedGrant(model="m", max_calls=2, token_budget=100),
        complete=_raw(),
    )
    with pytest.raises(ValueError, match="scoped to"):
        cb("other", [])


def test_call_budget_exhausted():
    cb = make_scoped_callback(
        grant=ScopedGrant(model="m", max_calls=1, token_budget=100),
        complete=_raw(),
    )
    cb("m", [])
    with pytest.raises(CallbackExhausted, match="call budget"):
        cb("m", [])


def test_token_budget_exhausted():
    cb = make_scoped_callback(
        grant=ScopedGrant(model="m", max_calls=5, token_budget=15),
        complete=_raw(usage={"prompt_tokens": 10, "completion_tokens": 10}),
    )
    with pytest.raises(CallbackExhausted, match="token budget"):
        cb("m", [])


def test_timeout_detected_via_clock():
    ticks = iter([0.0, 999.0])
    cb = make_scoped_callback(
        grant=ScopedGrant(model="m", max_calls=1, token_budget=100, call_timeout_s=5),
        complete=_raw(),
        clock=lambda: next(ticks),
    )
    with pytest.raises(TimeoutError):
        cb("m", [])
