"""Eval ladder grading and gating; clients mocked, no network and no inference."""

import time
from types import SimpleNamespace

import pytest
from ai_provider import route_eval
from ai_provider.errors import ProviderError, ProviderErrorCategory
from ai_provider.route_eval import (
    EvalResult,
    capability_cards,
    check_completion,
    check_t1,
    check_t2,
    check_t3,
    estimate_cost_usd,
    run_eval,
    run_ladder,
    select_model,
)

T1_GOOD = (
    "```python\n"
    "def clamp(value, lo, hi):\n"
    "    if value < lo:\n"
    "        return lo\n"
    "    if value > hi:\n"
    "        return hi\n"
    "    return value\n"
    "\n"
    "def retry_delay_ms(base_ms, factor, attempt):\n"
    "    return base_ms * factor ** attempt\n"
    "```"
)

T2_GOOD = (
    "```python\n"
    "def is_retryable(status):\n"
    "    if status == 429:\n"
    "        return True\n"
    "    if status >= 500 and status <= 599:\n"
    "        return True\n"
    "    return False\n"
    "```"
)

T3_GOOD = (
    "```python\n"
    "import math\n"
    "\n"
    "def mean(values):\n"
    "    total = 0\n"
    "    count = 0\n"
    "    for value in values:\n"
    "        total = total + value\n"
    "        count = count + 1\n"
    "    return total / count\n"
    "\n"
    "def stragglers(values, band):\n"
    "    average = mean(values)\n"
    "    lo = average - band\n"
    "    hi = average + band\n"
    "    out = []\n"
    "    for value in values:\n"
    "        if value < lo or value > hi:\n"
    "            out.append(value)\n"
    "    return out\n"
    "\n"
    "def rmse(values, target):\n"
    "    total = 0\n"
    "    count = 0\n"
    "    for value in values:\n"
    "        diff = value - target\n"
    "        total = total + diff * diff\n"
    "        count = count + 1\n"
    "    return math.sqrt(total / count)\n"
    "```"
)


def test_checker_passes_correct_completion():
    assert check_completion("```python\ndef add2(x):\n    return x + 2\n```") is True


def test_checker_passes_bare_function_without_fence():
    assert check_completion("def add2(x):\n    return 4 if x == 2 else x") is True


def test_checker_rejects_wrong_broken_and_empty_answers():
    assert check_completion("```python\ndef add2(x):\n    return x + 1\n```") is False
    assert check_completion("```python\ndef add2(x):\n    return \n```") is False
    assert check_completion("I cannot do that.") is False
    assert check_completion("") is False


def test_checker_rejects_import_escape():
    assert check_completion("```python\nimport os\ndef add2(x):\n    return 4\n```") is False


def test_t1_checker_passes_correct_module():
    assert check_t1(T1_GOOD) is True


def test_t1_checker_passes_bare_module_without_fence():
    bare = (
        "def clamp(value, lo, hi):\n"
        "    if value < lo:\n"
        "        return lo\n"
        "    if value > hi:\n"
        "        return hi\n"
        "    return value\n"
        "def retry_delay_ms(base_ms, factor, attempt):\n"
        "    return base_ms * factor ** attempt\n"
    )
    assert check_t1(bare) is True


def test_t1_checker_rejects_wrong_partial_and_empty_answers():
    wrong = (
        "```python\n"
        "def clamp(value, lo, hi):\n"
        "    return value\n"
        "def retry_delay_ms(base_ms, factor, attempt):\n"
        "    return base_ms * factor ** attempt\n"
        "```"
    )
    assert check_t1(wrong) is False
    assert check_t1("```python\ndef clamp(v, lo, hi):\n    return v\n```") is False
    assert check_t1("I cannot do that.") is False
    assert check_t1("") is False


def test_t1_checker_holds_back_edge_cases():
    # Passes the prompt's visible examples but ignores the upper bound.
    plausible = (
        "```python\n"
        "def clamp(value, lo, hi):\n"
        "    if value < lo:\n"
        "        return lo\n"
        "    return value\n"
        "def retry_delay_ms(base_ms, factor, attempt):\n"
        "    return base_ms * factor ** attempt\n"
        "```"
    )
    assert check_t1(plausible) is False


def test_t1_checker_rejects_import_and_builtin_escape():
    with_import = T1_GOOD.replace("def clamp", "import os\ndef clamp", 1)
    assert check_t1(with_import) is False
    with_builtin = (
        "```python\n"
        "def clamp(value, lo, hi):\n"
        "    if value < lo:\n"
        "        return lo\n"
        "    if value > hi:\n"
        "        return hi\n"
        "    return value\n"
        "def retry_delay_ms(base_ms, factor, attempt):\n"
        "    return sum([base_ms * factor ** attempt])\n"
        "```"
    )
    assert check_t1(with_builtin) is False


def test_t1_prompt_shows_visible_examples():
    assert "clamp(5, 0, 10) == 5" in route_eval.TASK_T1
    assert "retry_delay_ms(100, 2, 3) == 800" in route_eval.TASK_T1


def test_t2_checker_passes_fixed_function():
    assert check_t2(T2_GOOD) is True


def test_t2_checker_rejects_original_bug_and_regressions():
    original = "```python\ndef is_retryable(status):\n    return status == 429\n```"
    assert check_t2(original) is False
    always_true = "```python\ndef is_retryable(status):\n    return True\n```"
    assert check_t2(always_true) is False
    misses_429 = "```python\ndef is_retryable(status):\n    return status >= 500\n```"
    assert check_t2(misses_429) is False
    assert check_t2("") is False


def test_t2_checker_rejects_import_escape():
    smuggled = "```python\nimport os\ndef is_retryable(s):\n    return True\n```"
    assert check_t2(smuggled) is False


def test_t3_checker_passes_correct_module():
    assert check_t3(T3_GOOD) is True


def test_t3_checker_passes_math_without_import_styles():
    # math is pre-bound, so using it without importing also grades.
    no_import = T3_GOOD.replace("import math\n\n", "")
    assert check_t3(no_import) is True
    power = no_import.replace("math.sqrt(total / count)", "(total / count) ** 0.5")
    assert check_t3(power) is True


def test_t3_checker_rejects_wrong_partial_and_empty_answers():
    wrong_mean = (
        "```python\n"
        "import math\n"
        "def mean(values):\n"
        "    for value in values:\n"
        "        return value\n"
        "def stragglers(values, band):\n"
        "    return []\n"
        "def rmse(values, target):\n"
        "    return 0.0\n"
        "```"
    )
    assert check_t3(wrong_mean) is False
    missing_rmse = (
        "```python\n"
        "def mean(values):\n"
        "    total = 0\n"
        "    count = 0\n"
        "    for value in values:\n"
        "        total = total + value\n"
        "        count = count + 1\n"
        "    return total / count\n"
        "def stragglers(values, band):\n"
        "    return []\n"
        "```"
    )
    assert check_t3(missing_rmse) is False
    assert check_t3("") is False


def test_t3_checker_rejects_disallowed_import():
    smuggled = T3_GOOD.replace("import math", "import math\nimport os", 1)
    assert check_t3(smuggled) is False


def test_t3_hidden_tests_stay_out_of_prompt():
    for literal in (
        "[1, 2, 3, 4, 100]",
        "[2, 4, 4, 4, 5, 9]",
        "[10, 20, 30, 40]",
        "[50, 1, 2, 3]",
        "[5, 5, 5, 9]",
    ):
        assert literal not in route_eval.TASK_T3
    # The prompt's example is illustrative only, with disjoint values.
    assert "mean([2, 4])" in route_eval.TASK_T3


def test_candidate_timeout_matches_design():
    assert route_eval.CANDIDATE_TIMEOUT_SECONDS == 2.0


def test_guarded_grading_resolves_at_timeout():
    started = time.monotonic()
    graded = route_eval._run_guarded("value = 1", lambda namespace: time.sleep(2) or True, (), 0.05)
    assert graded is False
    assert time.monotonic() - started < 1.0


def test_safe_modules_allow_only_named_imports():
    namespace = route_eval._exec_candidate("import math\nvalue = math.sqrt(9)", ("math",))
    assert namespace is not None and namespace["value"] == 3.0
    assert route_eval._exec_candidate("import os", ("math",)) is None
    assert route_eval._exec_candidate("import math", ()) is None
    assert route_eval._exec_candidate("value = len([1])", ("math",)) is None


def test_run_eval_grades_and_records_usage(monkeypatch):
    calls = []

    class Client:
        def complete(self, request):
            calls.append(request)
            return SimpleNamespace(
                message=SimpleNamespace(content="```python\ndef add2(x):\n    return x*2\n```"),
                usage=SimpleNamespace(input_tokens=10, output_tokens=20),
            )

    result = run_eval(Client(), "r", "m")
    assert isinstance(result, EvalResult)
    assert (result.passed, result.input_tokens, result.output_tokens) == (True, 10, 20)
    assert result.latency_ms is not None
    assert calls[0].max_output_tokens == 1024
    assert calls[0].temperature == 0.0
    assert calls[0].metadata == {"public_or_synthetic": True}


def test_run_eval_captures_transport_failure():
    class Broken:
        def complete(self, request):
            raise ConnectionError("down")

    result = run_eval(Broken(), "r", "m")
    assert (result.passed, result.latency_ms) == (False, None)
    assert result.error == "ConnectionError: down"


def test_run_eval_tolerates_missing_usage():
    class NoUsage:
        def complete(self, request):
            return SimpleNamespace(
                message=SimpleNamespace(content="def add2(x):\n    return 4"), usage=None
            )

    result = run_eval(NoUsage(), "r", "m")
    assert (result.passed, result.input_tokens) == (True, None)


@pytest.mark.parametrize(
    ("task_id", "answer", "cap"),
    [
        ("T0", "```python\ndef add2(x):\n    return x + 2\n```", 1024),
        ("T1", T1_GOOD, 2048),
        ("T2", T2_GOOD, 2048),
        ("T3", T3_GOOD, 4096),
    ],
)
def test_run_eval_grades_each_task_with_its_cap(task_id, answer, cap):
    calls = []

    class Client:
        def complete(self, request):
            calls.append(request)
            return SimpleNamespace(
                message=SimpleNamespace(content=answer),
                usage=SimpleNamespace(input_tokens=10, output_tokens=20),
            )

    result = run_eval(Client(), "meta", "m", task_id=task_id)
    assert (result.task_id, result.passed) == (task_id, True)
    assert calls[0].max_output_tokens == cap
    assert calls[0].temperature == 0.0
    assert calls[0].metadata == {"public_or_synthetic": True}
    assert calls[0].messages[0].content == route_eval.TASK_SPECS[task_id].prompt


def test_run_eval_rejects_unknown_task():
    class Client:
        def complete(self, request):
            raise AssertionError("must not send")

    with pytest.raises(ValueError, match="unknown route-eval task"):
        run_eval(Client(), "r", "m", task_id="T9")


def test_run_eval_grades_wrong_answer_as_fail_without_error():
    class Client:
        def complete(self, request):
            return SimpleNamespace(
                message=SimpleNamespace(content="I cannot do that."),
                usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            )

    result = run_eval(Client(), "meta", "m", task_id="T1")
    assert (result.passed, result.error) == (False, None)


@pytest.mark.parametrize(
    "category",
    [
        ProviderErrorCategory.RATE_LIMIT,
        ProviderErrorCategory.AUTHENTICATION,
        ProviderErrorCategory.USAGE_LIMIT,
    ],
)
def test_run_eval_marks_parked_refusals(category):
    class Limited:
        def complete(self, request):
            raise ProviderError("provider refused", category=category, provider="x")

    result = run_eval(Limited(), "r", "m")
    assert result.passed is False
    assert result.error is not None and result.error.startswith("parked:ProviderError")


def test_run_eval_marks_raw_http_refusal_status():
    class Raw403:
        def complete(self, request):
            raise ConnectionError("HTTP Error 403: Forbidden")

    result = run_eval(Raw403(), "r", "m")
    assert result.error == "parked:ConnectionError: HTTP Error 403: Forbidden"


def test_estimate_cost_usd_uses_price_table():
    assert estimate_cost_usd("meta", 800, 1500) == (800 * 1.25 + 1500 * 4.25) / 1_000_000
    assert estimate_cost_usd("openrouter", 800, 1500) == 0.0
    assert estimate_cost_usd("requesty", 800, 1500) == 0.0
    assert estimate_cost_usd("baseten", 800, 1500) is None
    assert estimate_cost_usd("opencode_go", 800, 1500) is None
    assert estimate_cost_usd("meta", None, 1500) is None
    assert estimate_cost_usd("meta", 800, None) is None


class ScriptedClient:
    """Mocked transport keyed by task marker; records every request."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def complete(self, request):
        self.calls.append(request)
        prompt = request.messages[0].content
        for marker, answer in self.answers:
            if marker in prompt:
                if isinstance(answer, Exception):
                    raise answer
                return SimpleNamespace(message=SimpleNamespace(content=answer), usage=None)
        raise AssertionError(f"unexpected prompt: {prompt[:60]!r}")


_LADDER_MARKS = (
    ("def add2", "```python\ndef add2(x):\n    return x + 2\n```"),
    ("def clamp", T1_GOOD),
    ("def is_retryable", T2_GOOD),
    ("mean(values)", T3_GOOD),
)
_WRONG_T1 = "```python\ndef clamp(v, lo, hi):\n    return v\n```"


def test_run_ladder_passes_full_ladder_in_order():
    client = ScriptedClient(_LADDER_MARKS)
    results = run_ladder(client, "r", "m")
    assert [item.task_id for item in results] == ["T0", "T1", "T2", "T3"]
    assert all(item.passed for item in results)
    assert len(client.calls) == 4


def test_run_ladder_stops_at_first_fail():
    answers = (("def add2", _LADDER_MARKS[0][1]), ("def clamp", _WRONG_T1), *_LADDER_MARKS[2:])
    client = ScriptedClient(answers)
    results = run_ladder(client, "r", "m")
    assert [(item.task_id, item.passed) for item in results] == [("T0", True), ("T1", False)]
    assert len(client.calls) == 2


def test_run_ladder_stops_on_parked_refusal():
    refused = ProviderError("HTTP 429", category=ProviderErrorCategory.RATE_LIMIT, provider="x")
    answers = (("def add2", _LADDER_MARKS[0][1]), ("def clamp", refused), *_LADDER_MARKS[2:])
    client = ScriptedClient(answers)
    results = run_ladder(client, "r", "m")
    assert [item.task_id for item in results] == ["T0", "T1"]
    assert results[1].error is not None and results[1].error.startswith("parked:")


def test_run_ladder_collects_full_card_when_gating_disabled():
    answers = (("def add2", _LADDER_MARKS[0][1]), ("def clamp", _WRONG_T1), *_LADDER_MARKS[2:])
    client = ScriptedClient(answers)
    results = run_ladder(client, "r", "m", stop_on_fail=False)
    assert [item.task_id for item in results] == ["T0", "T1", "T2", "T3"]
    assert [item.passed for item in results] == [True, False, True, True]


def test_capability_cards_group_tasks_and_flag_parked():
    results = [
        EvalResult("r", "m", "2026-11-01T00:00:01+00:00", True, 10, 5, 5, None, "T0", 0.0),
        EvalResult(
            "r",
            "m",
            "2026-11-01T00:00:02+00:00",
            False,
            None,
            None,
            None,
            "parked:ProviderError: HTTP 429",
            "T1",
            None,
        ),
        EvalResult("other", "m2", "2026-11-01T00:00:03+00:00", True, 7, 1, 2, None, "T0", 0.0),
    ]
    cards = capability_cards(results)
    assert len(cards) == 2
    card = next(item for item in cards if item["route"] == "r")
    assert card["parked"] is True
    assert card["checked_utc"] == "2026-11-01T00:00:02+00:00"
    assert card["tasks"]["T0"]["passed"] is True
    assert card["tasks"]["T1"]["error"] == "parked:ProviderError: HTTP 429"
    other = next(item for item in cards if item["route"] == "other")
    assert other["parked"] is False


def test_snapshot_name_carries_task_ids():
    full = ("T0", "T1", "T2", "T3")
    assert route_eval._snapshot_name(full, "stamp") == "route-eval-T0-T3-stamp.json"
    assert route_eval._snapshot_name(("T1",), "stamp") == "route-eval-T1-stamp.json"
    assert route_eval._snapshot_name(("T1", "T2"), "stamp") == "route-eval-T1-T2-stamp.json"


def test_main_rejects_unknown_task_id(capsys):
    with pytest.raises(SystemExit) as exc:
        route_eval.main(["--tasks", "T9"])
    assert exc.value.code == 2
    assert "unknown task id" in capsys.readouterr().err


def test_select_model_pins_funded_routes(monkeypatch):
    monkeypatch.setattr(
        route_eval,
        "_list_model_ids",
        lambda route, creds: (_ for _ in ()).throw(AssertionError("no fetch")),
    )
    assert select_model("meta", {}) == "muse-spark-1.3"
    assert select_model("baseten", {}) == route_eval.BASETEN_HACKATHON_MODEL


def test_select_model_prefers_free_and_cheap_ids(monkeypatch):
    monkeypatch.setattr(
        route_eval, "_list_model_ids", lambda route, creds: ["a/big", "b/small:free", "c/flash"]
    )
    assert select_model("openrouter", {}) == "b/small:free"
    assert select_model("opencode_go", {}) == "c/flash"
    monkeypatch.setattr(route_eval, "_list_model_ids", lambda route, creds: ["a/big"])
    assert select_model("opencode_go", {}) == "a/big"
    monkeypatch.setattr(route_eval, "_list_model_ids", lambda route, creds: [])
    assert select_model("openrouter", {}) is None


def test_select_model_uses_zero_price_rows_for_requesty(monkeypatch):
    rows = [
        {"id": "paid", "api": "chat", "pricing": [], "input_price": "1", "output_price": "2"},
        {"id": "freebie", "api": "chat", "pricing": [], "input_price": "0", "output_price": "0"},
    ]
    monkeypatch.setattr(route_eval, "_list_rows", lambda route, creds: rows)
    assert select_model("requesty", {}) == "freebie"
    monkeypatch.setattr(route_eval, "_list_rows", lambda route, creds: rows[:1])
    assert select_model("requesty", {}) is None
