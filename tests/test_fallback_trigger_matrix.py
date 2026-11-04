"""Fallback trigger truth table: trigger x error-category x overload admission.

Pins the admission matrix implemented by ``FallbackSession.run`` together with
the ``explicit_usage_limit`` / ``explicit_model_overload`` marker tables in
``ai_provider.execution_fallback`` (composed with the ``ai_orchestrator``
fallback candidate ranking). Covers Track B W1 gaps G1 (usage/overload marker
tables) and G2 (category gating), including the surprising cases:

* UNKNOWN + overload text switches as ``model_overload`` (plain UNKNOWN raises).
* RATE_LIMIT / USAGE_LIMIT + overload text switches as ``usage_limit``: the
  overload text does not change the failure kind, so the billing bucket is
  exhausted instead of marking the route overloaded.
* A failed external result carrying both markers switches as ``usage_limit``
  (``is_limited`` wins; overload is only evaluated when not limited).
"""

import pytest
from ai_orchestrator import (
    AccessMethod,
    AccessRoute,
    AuthMethod,
    BackendLocation,
    BillingSource,
    CostPolicyTier,
    ModelBackend,
    ModelCapabilities,
    ModelCatalogEntry,
    PrivacyClass,
    QualityThreshold,
    TaskCapability,
    TaskProfile,
    prepare_execution,
)
from ai_provider.agent_readiness import AgentReadiness
from ai_provider.errors import ProviderError, ProviderErrorCategory
from ai_provider.execution_fallback import (
    FallbackSession,
    explicit_model_overload,
    explicit_usage_limit,
    external_model_overload,
    external_usage_limit,
)
from ai_provider.external_agents import ExternalAgentEventSummary, ExternalAgentResult

# Pinned copies of the production marker tables in execution_fallback.py.
# Any production edit must update these lists deliberately, not silently.
USAGE_MARKERS = (
    "usage_limit_reached",
    "insufficient_quota",
    "quota_exceeded",
    "usage limit",
    "quota exhausted",
    "quota exceeded",
    "exceeded your quota",
    "premium request limit",
    "no remaining credits",
    "rate limit exceeded",
    "resource_exhausted",
    "credit balance is exhausted",
)
OVERLOAD_MARKERS = (
    "server_overloaded",
    "selected model is at capacity",
    "model is overloaded",
    "server is overloaded",
)

PLAIN_FAILURE_TEXT = "synthetic provider failure without trigger markers"
OVERLOAD_FAILURE_TEXT = "synthetic failure: server_overloaded, retry shortly"


def test_trigger_fixture_texts_behave_as_labeled():
    """Guard the matrix inputs themselves against marker-table drift."""
    assert not explicit_usage_limit(PLAIN_FAILURE_TEXT)
    assert not explicit_model_overload(PLAIN_FAILURE_TEXT)
    assert not explicit_usage_limit(OVERLOAD_FAILURE_TEXT)
    assert explicit_model_overload(OVERLOAD_FAILURE_TEXT)


@pytest.mark.parametrize("marker", USAGE_MARKERS)
def test_usage_marker_table_triggers_usage_limit_only(marker):
    assert explicit_usage_limit(f"request failed: {marker}")
    assert explicit_usage_limit(f"request failed: {marker.upper()}")
    assert not explicit_model_overload(marker)


@pytest.mark.parametrize("marker", OVERLOAD_MARKERS)
def test_overload_marker_table_triggers_overload_only(marker):
    assert explicit_model_overload(f"request failed: {marker}")
    assert explicit_model_overload(f"request failed: {marker.upper()}")
    assert not explicit_usage_limit(marker)


@pytest.mark.parametrize(
    "text",
    [
        "permission denied",
        "connection reset by peer",
        "model returned malformed tool arguments",
        PLAIN_FAILURE_TEXT,
        "",
    ],
)
def test_negative_text_triggers_neither_predicate(text):
    assert not explicit_usage_limit(text)
    assert not explicit_model_overload(text)


def _events(failure):
    return ExternalAgentEventSummary(
        final_answer=None,
        command_events=(),
        tool_events=(),
        web_search_events=(),
        file_change_events=(),
        usage=None,
        failure_reason=failure,
        parse_errors=(),
    )


def _result(returncode, stdout, stderr, failure=None):
    return ExternalAgentResult(
        ("client",),
        returncode,
        stdout,
        stderr,
        events=None if failure is None else _events(failure),
    )


@pytest.mark.parametrize(
    ("returncode", "stdout", "stderr", "failure", "usage", "overload"),
    [
        (1, "", "failed: usage limit reached", None, True, False),
        (1, "", "failed: server_overloaded", None, False, True),
        # Both predicates fire on combined text; FallbackSession.run prefers limited.
        (1, "", "usage limit reached; server_overloaded", None, True, True),
        (1, "", "clean", "usage limit reached", True, False),
        (1, "", "clean", "server_overloaded", False, True),
        # Returncode 0 with a failure reason still consults the marker tables.
        (0, "", "clean", "usage limit reached", True, False),
        (0, "", "clean", "server_overloaded", False, True),
        # Successful output never triggers, even with markers in stderr.
        (0, "done", "usage limit reached", None, False, False),
        (0, "done", "server_overloaded", None, False, False),
        # Prompt/tool/final-answer text (stdout) never triggers.
        (1, "usage limit reached", "clean", None, False, False),
        (1, "server_overloaded", "clean", None, False, False),
        (1, "", "clean", None, False, False),
        (1, "", "clean", "clean", False, False),
    ],
)
def test_external_predicates_gate_on_failed_error_channels(
    returncode, stdout, stderr, failure, usage, overload
):
    result = _result(returncode, stdout, stderr, failure)
    assert external_usage_limit(result) is usage
    assert external_model_overload(result) is overload


def _entry(route, method, billing):
    return ModelCatalogEntry(
        backend=ModelBackend(
            route=AccessRoute(
                route_id=route,
                provider="test",
                product=route,
                model="auto",
                location=BackendLocation.EXTERNAL,
                access_method=method,
                auth_method=AuthMethod.CHATGPT_SIGN_IN,
                billing_source=billing,
                cost_policy_tier=CostPolicyTier.ALLOWANCES_ALLOWED,
            ),
            capabilities=ModelCapabilities(chat=True, tools=True),
        ),
        quality=QualityThreshold.HIGH,
    )


def _catalog():
    return (
        _entry("codex", AccessMethod.CODEX_CLI, BillingSource.CHATGPT_SUBSCRIPTION_ALLOWANCE),
        _entry(
            "copilot", AccessMethod.COPILOT_CLI, BillingSource.GITHUB_COPILOT_SUBSCRIPTION_ALLOWANCE
        ),
        _entry("kiro", AccessMethod.KIRO_CLI, BillingSource.KIRO_SUBSCRIPTION_ALLOWANCE),
    )


def _profile():
    return TaskProfile(
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        cost_policy_tier=CostPolicyTier.ALLOWANCES_ALLOWED,
        required_capabilities=frozenset({TaskCapability.CHAT, TaskCapability.TOOLS}),
        user_route_id_override="codex",
    )


def _initial(catalog):
    plan = prepare_execution("Fix source", _profile(), catalog, review_prompt=False).execution_plan
    assert plan is not None
    return plan.target


def _session(monkeypatch):
    monkeypatch.setattr(
        "ai_provider.execution_fallback.check_agent_readiness",
        lambda method: AgentReadiness(True, "authenticated"),
    )
    catalog = _catalog()
    return FallbackSession(
        _profile(),
        catalog,
        _initial(catalog),
        compatible=lambda target: True,
        progress=lambda text: None,
    )


def _provider_execute(calls, category, message):
    def execute(target, prompt):
        calls.append(target.route_id)
        if len(calls) == 1:
            raise ProviderError(message, category=category)
        return "continued"

    return execute


def _assert_provider_case(run, calls, expected):
    codex_billing = BillingSource.CHATGPT_SUBSCRIPTION_ALLOWANCE.value
    if expected == "raise":
        assert calls == ["codex"]
        assert run.attempts == []
        assert run.exhausted == set()
        assert run.overloaded == set()
        return
    reason = expected  # "usage_limit" or "model_overload"
    assert calls == ["codex", "copilot"]
    assert run.attempts == [
        {"route_id": "codex", "status": reason},
        {"route_id": "copilot", "status": "finished"},
    ]
    assert run.handoff is None
    if expected == "usage_limit":
        assert run.exhausted == {codex_billing}
        assert run.overloaded == set()
    else:
        assert run.overloaded == {"codex"}
        assert run.exhausted == set()


PROVIDER_MATRIX = [
    (ProviderErrorCategory.CONFIGURATION, False, "raise"),
    (ProviderErrorCategory.CONFIGURATION, True, "raise"),
    (ProviderErrorCategory.AUTHENTICATION, False, "raise"),
    (ProviderErrorCategory.AUTHENTICATION, True, "raise"),
    (ProviderErrorCategory.RATE_LIMIT, False, "usage_limit"),
    (ProviderErrorCategory.RATE_LIMIT, True, "usage_limit"),
    (ProviderErrorCategory.USAGE_LIMIT, False, "usage_limit"),
    (ProviderErrorCategory.USAGE_LIMIT, True, "usage_limit"),
    (ProviderErrorCategory.TIMEOUT, False, "raise"),
    (ProviderErrorCategory.TIMEOUT, True, "raise"),
    (ProviderErrorCategory.RETRYABLE, False, "raise"),
    (ProviderErrorCategory.RETRYABLE, True, "model_overload"),
    (ProviderErrorCategory.NON_RETRYABLE, False, "raise"),
    (ProviderErrorCategory.NON_RETRYABLE, True, "raise"),
    (ProviderErrorCategory.PRIVACY_POLICY, False, "raise"),
    (ProviderErrorCategory.PRIVACY_POLICY, True, "raise"),
    (ProviderErrorCategory.UNKNOWN, False, "raise"),
    (ProviderErrorCategory.UNKNOWN, True, "model_overload"),
]


@pytest.mark.parametrize(
    ("category", "overload_text", "expected"),
    PROVIDER_MATRIX,
    ids=[
        f"{category.value}-{'overload' if overload_text else 'plain'}-{expected}"
        for category, overload_text, expected in PROVIDER_MATRIX
    ],
)
def test_provider_error_admission_matrix(monkeypatch, category, overload_text, expected):
    """Category x overload-text admission through FallbackSession.run."""
    run = _session(monkeypatch)
    calls = []
    message = OVERLOAD_FAILURE_TEXT if overload_text else PLAIN_FAILURE_TEXT
    execute = _provider_execute(calls, category, message)
    if expected == "raise":
        with pytest.raises(ProviderError):
            run.run("task", execute, lambda result: False, observe=str)
    else:
        assert run.run("task", execute, lambda result: False, observe=str) == "continued"
    _assert_provider_case(run, calls, expected)


def test_unknown_with_overload_text_switches_as_overload(monkeypatch):
    """UNKNOWN alone raises, but UNKNOWN + overload text is admitted as overload."""
    run = _session(monkeypatch)
    calls = []
    execute = _provider_execute(calls, ProviderErrorCategory.UNKNOWN, OVERLOAD_FAILURE_TEXT)
    assert run.run("task", execute, lambda result: False, observe=str) == "continued"
    _assert_provider_case(run, calls, "model_overload")


def test_rate_limit_with_overload_text_switches_as_usage_limit(monkeypatch):
    """Overload text does not change the failure kind for RATE_LIMIT/USAGE_LIMIT."""
    for category in (ProviderErrorCategory.RATE_LIMIT, ProviderErrorCategory.USAGE_LIMIT):
        run = _session(monkeypatch)
        calls = []
        execute = _provider_execute(calls, category, OVERLOAD_FAILURE_TEXT)
        assert run.run("task", execute, lambda result: False, observe=str) == "continued"
        _assert_provider_case(run, calls, "usage_limit")


def _external_execute(calls, first):
    def execute(target, prompt):
        calls.append(target.route_id)
        if len(calls) == 1:
            return first
        return "continued"

    return execute


def _is_limited(value):
    return isinstance(value, ExternalAgentResult) and external_usage_limit(value)


EXTERNAL_MATRIX = [
    ("usage-stderr", (1, "", "failed: usage limit reached", None), "usage_limit"),
    ("overload-stderr", (1, "", "failed: server_overloaded", None), "model_overload"),
    # Limited wins when both marker kinds are present.
    ("both-markers", (1, "", "usage limit reached; server_overloaded", None), "usage_limit"),
    ("usage-failure-reason", (1, "", "clean", "usage limit reached"), "usage_limit"),
    ("overload-failure-reason", (1, "", "clean", "server_overloaded"), "model_overload"),
    ("no-marker", (1, "", "permission denied", None), "finished"),
    ("usage-stdout-only", (1, "usage limit reached", "clean", None), "finished"),
    ("overload-stdout-only", (1, "server_overloaded", "clean", None), "finished"),
    ("success-usage-stderr", (0, "done", "usage limit reached", None), "finished"),
    ("success-overload-stderr", (0, "done", "server_overloaded", None), "finished"),
]


@pytest.mark.parametrize(
    ("failure", "expected"),
    [(case[1], case[2]) for case in EXTERNAL_MATRIX],
    ids=[case[0] for case in EXTERNAL_MATRIX],
)
def test_external_result_admission_matrix(monkeypatch, failure, expected):
    """External trigger x marker admission through FallbackSession.run."""
    run = _session(monkeypatch)
    calls = []
    first = _result(*failure)
    result = run.run("task", _external_execute(calls, first), _is_limited, observe=str)
    if expected == "finished":
        assert result is first
        assert calls == ["codex"]
        assert run.attempts == [{"route_id": "codex", "status": "finished"}]
        assert run.exhausted == set()
        assert run.overloaded == set()
        return
    assert result == "continued"
    _assert_provider_case(run, calls, expected)
