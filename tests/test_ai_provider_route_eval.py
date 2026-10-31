"""Micro-evaluation grading; clients mocked, no network and no inference."""

from types import SimpleNamespace

from ai_provider import route_eval
from ai_provider.route_eval import EvalResult, check_completion, run_eval, select_model


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
