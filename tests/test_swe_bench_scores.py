"""Published SWE-bench capability priors; no network and no model call."""

import json
from io import BytesIO

import pytest
from ai_provider.source_info import CapabilityPrior, CapabilityScore
from ai_provider.swe_bench_scores import (
    LEADERBOARD_URL,
    read_swe_bench_scores,
)


class Response(BytesIO):
    status = 200

    def __init__(self, raw, headers=None):
        super().__init__(raw if isinstance(raw, bytes) else json.dumps(raw).encode())
        self.headers = headers or {}


def row(**changes):
    result = {
        "agent": "mini-SWE-agent",
        "agent_org": "SWE-agent",
        "checked": True,
        "cost": 12.5,
        "date": "2026-02-13",
        "model_display": "GLM 4.5",
        "model_org": "Zhipu",
        "name": "mini-SWE-agent + GLM 4.5",
        "resolved": 42.5,
        "warning": None,
    }
    result.update(changes)
    return result


def transport(monkeypatch, *, results=None, status=200, splits=("Verified",)):
    calls = []

    def send(http_request, **kwargs):
        calls.append(http_request)
        if status != 200:
            from email.message import Message
            from urllib.error import HTTPError

            raise HTTPError(http_request.full_url, status, "error", Message(), None)
        leaderboards = [
            {"name": name, "results": results if results is not None else [row()]}
            for name in splits
        ]
        return Response({"leaderboards": leaderboards})

    monkeypatch.setattr("ai_provider.swe_bench_scores.urlopen", send)
    return calls


def test_scores_are_read_without_a_model_call(monkeypatch):
    calls = transport(monkeypatch)
    result = read_swe_bench_scores("Verified")
    assert isinstance(result, CapabilityPrior)
    assert result.status == "observed"
    assert result.split == "Verified"
    assert result.source_url == LEADERBOARD_URL
    assert [call.get_method() for call in calls] == ["GET"]
    score = result.scores[0]
    assert isinstance(score, CapabilityScore)
    assert score.benchmark == "SWE-bench"
    assert score.model_display == "GLM 4.5"
    assert score.model == "glm 4.5"
    assert score.agent == "mini-SWE-agent"
    assert score.agent_org == "SWE-agent"
    assert score.score == 42.5
    assert score.scale == "percent_resolved"
    assert score.measured_at == "2026-02-13"
    assert score.verified is True
    assert score.cost_usd == 12.5


def test_published_name_variants_normalize_to_one_key(monkeypatch):
    transport(
        monkeypatch,
        results=[
            row(model_display="GLM 4.5"),
            row(model_display="GLM-4.5"),
            row(model_display="GPT-5"),
            row(model_display="GPT 5"),
        ],
    )
    result = read_swe_bench_scores("Verified")
    assert {score.model for score in result.scores} == {"glm 4.5", "gpt 5"}
    assert {score.model_display for score in result.scores} == {
        "GLM 4.5",
        "GLM-4.5",
        "GPT-5",
        "GPT 5",
    }


def test_the_scaffold_stays_attached_to_every_score(monkeypatch):
    transport(
        monkeypatch,
        results=[
            row(model_display="GLM 4.5", agent="mini-SWE-agent", resolved=42.5),
            row(model_display="GLM 4.5", agent="Other Scaffold", resolved=61.0),
        ],
    )
    result = read_swe_bench_scores("Verified")
    assert len(result.scores) == 2
    assert {score.agent for score in result.scores} == {"mini-SWE-agent", "Other Scaffold"}
    summary = result.summary()
    assert summary["model_count"] == 1
    assert summary["agent_count"] == 2
    assert summary["best_score"] == 61.0
    assert summary["best_score_model"] == "glm 4.5"
    assert summary["best_score_agent"] == "Other Scaffold"


def test_unknown_split_is_unavailable_rather_than_guessed(monkeypatch):
    transport(monkeypatch, splits=("Verified", "Lite"))
    result = read_swe_bench_scores("Nonexistent")
    assert result.status == "unavailable"
    assert result.reason == "unknown_split"
    assert result.scores == ()


def test_rows_without_a_model_name_are_skipped(monkeypatch):
    transport(monkeypatch, results=[row(), {"agent": "orphan"}, "not-a-row"])
    result = read_swe_bench_scores("Verified")
    assert len(result.scores) == 1


def test_unreported_values_stay_unknown(monkeypatch):
    transport(monkeypatch, results=[row(cost=None, checked=None, warning=None, date=None)])
    score = read_swe_bench_scores("Verified").scores[0]
    assert score.cost_usd is None
    assert score.verified is None
    assert score.warning is None
    assert score.measured_at is None


def test_a_published_warning_is_preserved(monkeypatch):
    transport(monkeypatch, results=[row(warning="Unverified submission")])
    score = read_swe_bench_scores("Verified").scores[0]
    assert score.warning == "Unverified submission"


def test_malformed_payloads_refuse_without_raising(monkeypatch):
    monkeypatch.setattr(
        "ai_provider.swe_bench_scores.urlopen",
        lambda *a, **k: Response({"leaderboards": "not-a-list"}),
    )
    result = read_swe_bench_scores("Verified")
    assert result.status == "unavailable"
    assert result.reason == "metadata_request_failed"


@pytest.mark.parametrize("status,reason", [(404, "source_not_found"), (403, "permission_denied")])
def test_http_failures_are_sanitized(monkeypatch, status, reason):
    transport(monkeypatch, status=status)
    result = read_swe_bench_scores("Verified")
    assert result.status == "unavailable"
    assert result.reason == reason


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), True])
def test_invalid_timeouts_refuse_before_io(monkeypatch, timeout):
    monkeypatch.setattr(
        "ai_provider.swe_bench_scores.urlopen",
        lambda *a, **k: pytest.fail("Network attempted"),
    )
    with pytest.raises(ValueError, match="finite and positive"):
        read_swe_bench_scores("Verified", timeout_seconds=timeout)


def test_an_empty_split_name_is_rejected():
    with pytest.raises(ValueError, match="[Ss]plit"):
        read_swe_bench_scores("  ")
