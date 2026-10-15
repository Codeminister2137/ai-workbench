"""Cumulative numeric receipts use fake HTTP and never consume allowance."""

import json
from argparse import Namespace

import pytest
from ai_provider import AIMessage, AIRequest, BackendConfig, MessageRole, PrivacyClass, ProviderKind
from ai_provider.adapters.openai_compatible import OpenAICompatibleChatClient
from ai_provider.errors import ProviderError
from ai_provider.transcripts import print_run_metrics, start_run_metrics
from ai_provider.turn_usage import ACTIVE_USAGE, usage_scope


def adapter():
    return OpenAICompatibleChatClient(BackendConfig(ProviderKind.REQUESTY, "test", api_key="fake"))


REQUEST = AIRequest(
    (AIMessage(MessageRole.USER, "synthetic"),), privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK
)


def usage_summary():
    ledger = ACTIVE_USAGE.get()
    assert ledger is not None
    return ledger.summary()


def raw(usage):
    return {
        "choices": [
            {
                "message": {"content": "answer", "reasoning": "private-sentinel"},
                "finish_reason": "stop",
            }
        ],
        "usage": usage,
    }


def report(response=None):
    print_run_metrics(
        start_run_metrics(),
        primary_elapsed_seconds=None,
        primary_response=response,
        scrutiny_elapsed_seconds=None,
        scrutiny_response=None,
    )


def test_multiple_calls_failure_and_isolated_turns(monkeypatch, capsys):
    payloads = iter(
        [
            raw({"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12, "cost": 0}),
            raw({"prompt_tokens": 20, "completion_tokens": 3, "total_tokens": 23}),
            None,
        ]
    )

    def post(self, payload):
        result = next(payloads)
        if result is None:
            raise ProviderError("synthetic failure")
        return result

    monkeypatch.setattr(OpenAICompatibleChatClient, "_post_chat", post)

    @usage_scope
    def turn():
        client = adapter()
        client.complete(REQUEST)
        final = client.complete(REQUEST)
        summary = usage_summary()
        assert summary["total_tokens"] == {
            "known_sum": 35,
            "observed_calls": 2,
            "coverage": "complete",
        }
        assert summary["reported_cost_usd"] == {
            "known_sum": 0,
            "observed_calls": 1,
            "coverage": "partial",
        }
        report(final)
        with pytest.raises(ProviderError):
            client.complete(REQUEST)
        report()
        return usage_summary()

    summary = turn()
    assert summary["attempts"] == 3 and summary["responses"] == 2
    assert summary["total_tokens"]["coverage"] == "partial"
    assert summary["calls"][-1] == {}
    output = capsys.readouterr().out
    assert "primary_total_tokens: 23" in output
    assert "primary_usage_scope: final_response" in output
    assert "private-sentinel" not in output
    assert ACTIVE_USAGE.get() is None

    @usage_scope
    def fresh():
        assert usage_summary()["total_tokens"]["known_sum"] is None

    fresh()


@pytest.mark.parametrize("value", [None, True, -1, "0", float("nan"), float("inf"), 10**1000])
def test_invalid_cost_remains_unknown(monkeypatch, value):
    monkeypatch.setattr(
        OpenAICompatibleChatClient, "_post_chat", lambda *args: raw({"cost": value})
    )

    @usage_scope
    def turn():
        assert adapter().complete(REQUEST).usage.reported_cost_usd is None
        assert usage_summary()["reported_cost_usd"] == {
            "known_sum": None,
            "observed_calls": 0,
            "coverage": "unknown",
        }

    turn()


def test_usage_survives_malformed_response_and_stream_failure(monkeypatch):
    malformed = raw({"total_tokens": 7, "cost": 0.25})
    malformed["choices"] = []
    monkeypatch.setattr(OpenAICompatibleChatClient, "_post_chat", lambda *args: malformed)

    def stream(*args):
        yield {"choices": [], "usage": {"total_tokens": 9}}
        raise ProviderError("synthetic disconnect")

    monkeypatch.setattr(OpenAICompatibleChatClient, "_stream_chat", stream)

    @usage_scope
    def turn():
        with pytest.raises(ProviderError):
            adapter().complete(REQUEST)
        with pytest.raises(ProviderError):
            list(adapter().stream(REQUEST))
        summary = usage_summary()
        assert summary["responses"] == 0
        assert summary["total_tokens"] == {
            "known_sum": 16,
            "observed_calls": 2,
            "coverage": "partial",
        }
        assert summary["reported_cost_usd"]["coverage"] == "partial"

    turn()


def test_stream_usage_is_not_double_counted(monkeypatch):
    def stream(*args):
        yield {"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]}
        yield {"choices": [], "usage": {"total_tokens": 11, "cost": 0}}

    monkeypatch.setattr(OpenAICompatibleChatClient, "_stream_chat", stream)

    @usage_scope
    def turn():
        list(adapter().stream(REQUEST))
        summary = usage_summary()
        assert summary["total_tokens"]["known_sum"] == 11
        assert summary["responses"] == summary["attempts"] == 1
        json.dumps(summary, allow_nan=False)

    turn()


def test_estimates_are_not_reported_as_provider_totals():
    from ai_provider import UsageMetadata, UsageSource
    from ai_provider.turn_usage import TurnUsage

    ledger = TurnUsage(attempts=1, responses=1, calls=[{}])
    ledger.record(UsageMetadata(source=UsageSource.ESTIMATED, total_tokens=100), 0)
    assert ledger.summary()["total_tokens"] == {
        "known_sum": None,
        "observed_calls": 0,
        "coverage": "unknown",
    }


def test_cost_sum_overflow_remains_unknown(monkeypatch):
    monkeypatch.setattr(
        OpenAICompatibleChatClient, "_post_chat", lambda *args: raw({"cost": 1e308})
    )

    @usage_scope
    def turn():
        adapter().complete(REQUEST)
        adapter().complete(REQUEST)
        summary = usage_summary()
        assert summary["reported_cost_usd"] == {
            "known_sum": None,
            "observed_calls": 2,
            "coverage": "partial",
        }
        json.dumps(summary, allow_nan=False)

    turn()


@pytest.mark.parametrize("failure", [ValueError, KeyboardInterrupt])
def test_cli_host_failure_keeps_numeric_receipts_before_cleanup(monkeypatch, capsys, failure):
    from ai_agent import repo_coding_assistant as cli

    monkeypatch.setattr(
        OpenAICompatibleChatClient, "_post_chat", lambda *a: raw({"total_tokens": 7})
    )
    cleaned = []

    def cleanup():
        ledger = ACTIVE_USAGE.get()
        assert ledger is not None and ledger.report_printed
        cleaned.append(True)

    def execute(*a, **k):
        adapter().complete(REQUEST)
        raise failure("private-host-error-sentinel")

    monkeypatch.setattr(cli, "_execute_request", execute)
    with pytest.raises(failure):
        cli._main([], parsed_args=Namespace(_transcript_cleanup=cleanup))
    output = capsys.readouterr().out
    summary = json.loads(output.split("cumulative_usage_json: ", 1)[1])
    assert summary["attempts"] == summary["responses"] == 1
    assert summary["total_tokens"] == {"known_sum": 7, "observed_calls": 1, "coverage": "complete"}
    assert summary["reported_cost_usd"]["known_sum"] is None
    assert summary["reported_cost_usd"]["coverage"] == "unknown"
    assert "private-sentinel" not in output and "private-host-error-sentinel" not in output
    assert "final_response" not in output
    assert cleaned == [True] and ACTIVE_USAGE.get() is None


def test_cli_exit_does_not_repeat_normal_metrics(monkeypatch, capsys):
    from ai_agent import repo_coding_assistant as cli

    monkeypatch.setattr(
        OpenAICompatibleChatClient, "_post_chat", lambda *a: raw({"total_tokens": 7})
    )

    def execute(*a, **k):
        report(adapter().complete(REQUEST))
        return 0

    monkeypatch.setattr(cli, "_execute_request", execute)
    assert cli._main([], parsed_args=Namespace()) == 0
    output = capsys.readouterr().out
    assert output.count("cumulative_usage_json: ") == 1
    assert "primary_usage_scope: final_response" in output


@pytest.mark.parametrize("output_failure", [OSError, ValueError])
def test_broken_fallback_output_cannot_mask_host_failure_or_cleanup(monkeypatch, output_failure):
    from ai_agent import repo_coding_assistant as cli

    cleaned = []

    def execute(*a, **k):
        raise RuntimeError("original host failure")

    def broken_output(**kwargs):
        raise output_failure("output unavailable")

    monkeypatch.setattr(cli, "_execute_request", execute)
    monkeypatch.setattr(cli, "_print_cumulative_usage", broken_output)
    with pytest.raises(RuntimeError, match="original host failure"):
        cli._main([], parsed_args=Namespace(_transcript_cleanup=lambda: cleaned.append(True)))
    assert cleaned == [True] and ACTIVE_USAGE.get() is None
