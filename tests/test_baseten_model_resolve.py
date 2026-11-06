import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "baseten-supervised-develop.py"
spec = importlib.util.spec_from_file_location("baseten_supervised_develop", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

MODEL = mod.MODEL
_resolve_model = mod._resolve_model


def test_cli_model_wins_over_all_env(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_MODEL", "env-supervisor")
    monkeypatch.setenv("IMPLEMENTER_MODEL", "env-implementer")
    assert _resolve_model(" cli-model ", role="supervisor") == "cli-model"
    assert _resolve_model(" cli-model ", role="implementer") == "cli-model"
    assert _resolve_model(" cli-model ", role=None) == "cli-model"
    assert _resolve_model("cli-model") == "cli-model"


def test_role_supervisor_prefers_supervisor_fallbacks(monkeypatch):
    # prefers SUPERVISOR_MODEL
    monkeypatch.setenv("SUPERVISOR_MODEL", "sup-model")
    monkeypatch.setenv("IMPLEMENTER_MODEL", "imp-model")
    assert _resolve_model(None, role="supervisor") == "sup-model"
    # falls back to IMPLEMENTER_MODEL when SUPERVISOR_MODEL missing
    monkeypatch.delenv("SUPERVISOR_MODEL", raising=False)
    assert _resolve_model(None, role="supervisor") == "imp-model"
    # then MODEL when both missing
    monkeypatch.delenv("IMPLEMENTER_MODEL", raising=False)
    assert _resolve_model(None, role="supervisor") == MODEL


def test_role_implementer_prefers_implementer_fallbacks(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_MODEL", "sup-model")
    monkeypatch.setenv("IMPLEMENTER_MODEL", "imp-model")
    assert _resolve_model(None, role="implementer") == "imp-model"
    monkeypatch.delenv("IMPLEMENTER_MODEL", raising=False)
    assert _resolve_model(None, role="implementer") == "sup-model"
    monkeypatch.delenv("SUPERVISOR_MODEL", raising=False)
    assert _resolve_model(None, role="implementer") == MODEL


def test_unroled_prefers_supervisor_then_implementer_then_default(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_MODEL", "sup-model")
    monkeypatch.setenv("IMPLEMENTER_MODEL", "imp-model")
    assert _resolve_model(None) == "sup-model"
    assert _resolve_model(None, role=None) == "sup-model"
    monkeypatch.delenv("SUPERVISOR_MODEL", raising=False)
    assert _resolve_model(None) == "imp-model"
    monkeypatch.delenv("IMPLEMENTER_MODEL", raising=False)
    assert _resolve_model(None) == MODEL


def test_empty_whitespace_env_ignored(monkeypatch):
    # empty/whitespace SUPERVISOR_MODEL should fall through to IMPLEMENTER_MODEL
    monkeypatch.setenv("SUPERVISOR_MODEL", "   ")
    monkeypatch.setenv("IMPLEMENTER_MODEL", "imp-model")
    assert _resolve_model(None, role="supervisor") == "imp-model"
    assert _resolve_model(None) == "imp-model"
    # both empty -> MODEL
    monkeypatch.setenv("SUPERVISOR_MODEL", "")
    monkeypatch.setenv("IMPLEMENTER_MODEL", "  \t ")
    assert _resolve_model(None) == MODEL
    assert _resolve_model(None, role="supervisor") == MODEL
    assert _resolve_model(None, role="implementer") == MODEL
    # whitespace cli_model falls through to env/default
    monkeypatch.setenv("SUPERVISOR_MODEL", "sup-model")
    assert _resolve_model("   ", role="supervisor") == "sup-model"
    monkeypatch.delenv("SUPERVISOR_MODEL", raising=False)
    monkeypatch.delenv("IMPLEMENTER_MODEL", raising=False)
    assert _resolve_model("   ") == MODEL
