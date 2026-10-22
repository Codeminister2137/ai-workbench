"""Published Aider polyglot capability priors; no network and no model call."""

import json
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError

import pytest
from ai_provider.aider_polyglot_scores import (
    AGENT,
    AGENT_ORG,
    LEADERBOARD_URL,
    read_aider_polyglot_scores,
)
from ai_provider.source_info import CapabilityPrior, CapabilityScore

DETAILS = """<tr id="main-row-0"></tr>
<tr class="details-row" id="details-0">
<td colspan="7"><ul>
<li><strong>
  Dirname
:</strong>
  2025-08-23-15-47-21--gpt-5-high
</li>
<li><strong>Model :</strong> gpt-5 (high)</li>
<li><strong>Edit format :</strong> diff</li>
<li><strong>Reasoning effort :</strong> high</li>
<li><strong>Test cases :</strong> 225</li>
<li><strong>Percent cases well formed :</strong> 91.6</li>
<li><strong>Syntax errors :</strong> 0</li>
<li><strong>Exhausted context windows :</strong> 0</li>
<li><strong>Prompt tokens :</strong> 2675561</li>
<li><strong>Completion tokens :</strong> 2623429</li>
<li><strong>Command :</strong> <code>aider --model openai/gpt-5</code></li>
<li><strong>Date :</strong> 2025-08-23</li>
<li><strong>Total cost :</strong> 29.0829</li>
<li><strong>Pass rate 2 :</strong> 88.0</li>
</ul></td>
</tr>"""


class Response(BytesIO):
    status = 200

    def __init__(self, raw, headers=None):
        super().__init__(raw if isinstance(raw, bytes) else json.dumps(raw).encode())
        self.headers = headers or {}


def transport(monkeypatch, *, page=DETAILS, status=200):
    calls = []

    def send(http_request, **kwargs):
        calls.append(http_request)
        if status != 200:
            raise HTTPError(http_request.full_url, status, "error", Message(), None)
        return Response(page.encode())

    monkeypatch.setattr("ai_provider.aider_polyglot_scores.urlopen", send)
    return calls


def test_a_run_is_read_with_its_specific_model_id(monkeypatch):
    calls = transport(monkeypatch)
    result = read_aider_polyglot_scores()
    assert isinstance(result, CapabilityPrior)
    assert result.status == "observed"
    assert result.split == "polyglot"
    assert result.source_url == LEADERBOARD_URL
    assert [call.get_method() for call in calls] == ["GET"]
    score = result.scores[0]
    assert isinstance(score, CapabilityScore)
    assert score.benchmark == "Aider polyglot"
    assert score.model == "openai/gpt-5"
    assert score.model_display == "gpt-5 (high)"
    assert score.score == 88.0
    assert score.scale == "percent_correct"
    assert score.cost_usd == 29.0829
    assert score.measured_at == "2025-08-23"


def test_the_single_harness_is_recorded_on_every_score(monkeypatch):
    transport(monkeypatch)
    score = read_aider_polyglot_scores().scores[0]
    assert score.agent == AGENT
    assert score.agent_org == AGENT_ORG


def test_run_configuration_and_diagnostics_are_recorded(monkeypatch):
    transport(monkeypatch)
    score = read_aider_polyglot_scores().scores[0]
    assert score.configuration == "edit=diff; reasoning=high"
    assert score.test_cases == 225
    assert score.well_formed_percent == 91.6
    assert score.syntax_errors == 0
    assert score.context_exhausted == 0
    assert score.prompt_tokens == 2675561
    assert score.completion_tokens == 2623429


def test_repeated_runs_differing_only_by_edit_format_stay_distinguishable(monkeypatch):
    architect = DETAILS.replace(
        "<strong>Edit format :</strong> diff", "<strong>Edit format :</strong> architect"
    ).replace("<strong>Pass rate 2 :</strong> 88.0", "<strong>Pass rate 2 :</strong> 78.2")
    transport(monkeypatch, page=DETAILS + "\n" + architect)
    scores = read_aider_polyglot_scores().scores
    assert len(scores) == 2
    assert sorted(score.score or 0.0 for score in scores) == [78.2, 88.0]
    assert {score.configuration for score in scores} == {
        "edit=diff; reasoning=high",
        "edit=architect; reasoning=high",
    }


def test_a_run_without_a_published_configuration_reports_none(monkeypatch):
    page = "\n".join(
        line
        for line in DETAILS.splitlines()
        if "Edit format" not in line and "Reasoning effort" not in line
    )
    transport(monkeypatch, page=page)
    assert read_aider_polyglot_scores().scores[0].configuration is None


def test_extra_command_flags_do_not_corrupt_the_model_id(monkeypatch):
    transport(
        monkeypatch,
        page=DETAILS.replace(
            "<code>aider --model openai/gpt-5</code>",
            "<code>aider --model openrouter/openai/gpt-oss-120b --reasoning-effort high</code>",
        ),
    )
    score = read_aider_polyglot_scores().scores[0]
    assert score.model == "openrouter/openai/gpt-oss-120b"


def test_a_row_without_an_identifiable_model_is_skipped(monkeypatch):
    broken = DETAILS.replace("aider --model openai/gpt-5", "aider --model")
    transport(monkeypatch, page=broken + "\n" + DETAILS)
    result = read_aider_polyglot_scores()
    assert len(result.scores) == 1
    assert result.scores[0].model == "openai/gpt-5"


def test_unreported_values_stay_unknown(monkeypatch):
    page = "\n".join(
        line
        for line in DETAILS.splitlines()
        if not any(
            label in line
            for label in (
                "Edit format",
                "Reasoning effort",
                "Syntax errors",
                "Exhausted context windows",
                "Prompt tokens",
                "Completion tokens",
            )
        )
    )
    transport(monkeypatch, page=page)
    score = read_aider_polyglot_scores().scores[0]
    assert score.configuration is None
    assert score.syntax_errors is None
    assert score.context_exhausted is None
    assert score.prompt_tokens is None
    assert score.completion_tokens is None


def test_non_numeric_published_values_are_ignored(monkeypatch):
    transport(monkeypatch, page=DETAILS.replace("91.6", "n/a").replace("29.0829", "free"))
    score = read_aider_polyglot_scores().scores[0]
    assert score.well_formed_percent is None
    assert score.cost_usd is None


def test_lists_outside_the_details_rows_are_not_parsed(monkeypatch):
    page = "<ul><li><strong>Model :</strong> not-a-run</li></ul>" + DETAILS
    transport(monkeypatch, page=page)
    result = read_aider_polyglot_scores()
    assert len(result.scores) == 1
    assert result.scores[0].model_display == "gpt-5 (high)"


def test_a_page_with_no_published_run_is_unavailable(monkeypatch):
    transport(monkeypatch, page="<html><body><p>Moved</p></body></html>")
    result = read_aider_polyglot_scores()
    assert result.status == "unavailable"
    assert result.reason == "metadata_request_failed"
    assert result.scores == ()


@pytest.mark.parametrize("status,reason", [(404, "source_not_found"), (403, "permission_denied")])
def test_http_failures_are_sanitized(monkeypatch, status, reason):
    transport(monkeypatch, status=status)
    result = read_aider_polyglot_scores()
    assert result.status == "unavailable"
    assert result.reason == reason


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), True])
def test_invalid_timeouts_refuse_before_io(monkeypatch, timeout):
    monkeypatch.setattr(
        "ai_provider.aider_polyglot_scores.urlopen",
        lambda *a, **k: pytest.fail("Network attempted"),
    )
    with pytest.raises(ValueError, match="finite and positive"):
        read_aider_polyglot_scores(timeout_seconds=timeout)


def test_the_request_is_read_only_and_carries_no_credential(monkeypatch):
    calls = transport(monkeypatch)
    read_aider_polyglot_scores()
    assert calls[0].get_header("Authorization") is None
    assert calls[0].get_header("User-agent")
