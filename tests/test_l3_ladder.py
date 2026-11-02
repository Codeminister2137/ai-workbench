"""Ladder resolution policy; live inference is never executed here."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/l3_ladder.py"
_spec = importlib.util.spec_from_file_location("l3_ladder", SCRIPT)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

CostPolicyTier = _module.CostPolicyTier
EvalResult = _module.EvalResult
apply_tier_blocks = _module.apply_tier_blocks
recent_failed_models = _module.recent_failed_models
resolve_route = _module.resolve_route

FREE = CostPolicyTier.FREE_ONLY
PREPAID = CostPolicyTier.PREPAID_CREDITS_ALLOWED
BILLING = CostPolicyTier.BILLING_ALLOWED


def test_recent_failed_models_collects_error_ids(tmp_path) -> None:
    good = [{"route": "r", "model": "fine", "error": None, "task_id": "T0"}]
    bad = [
        {"route": "r", "model": "flaky", "error": "ProviderError: HTTP 503", "task_id": "T0"},
        {"route": "r", "model": "?", "error": "no-model", "task_id": "T0"},
    ]
    (tmp_path / "route-eval-T0-a.json").write_text(json.dumps(good), encoding="utf-8")
    (tmp_path / "route-eval-T0-b.json").write_text(json.dumps(bad), encoding="utf-8")
    (tmp_path / "route-eval-T0-c.json").write_text("{broken", encoding="utf-8")
    assert recent_failed_models(tmp_path) == {("r", "flaky")}
    assert recent_failed_models(tmp_path / "missing") == set()


def test_resolve_route_tier_blocks_above_allowance() -> None:
    candidates, note = resolve_route(
        "meta",
        catalog=(),
        credentials={},
        allow_tier=FREE,
        max_candidates=3,
        skip=frozenset(),
        live_refresh=True,
    )
    assert candidates == []
    assert note.startswith("tier-blocked")


def test_resolve_route_orders_catalog_before_live(monkeypatch) -> None:
    from ai_orchestrator.catalog import load_model_catalog

    catalog = load_model_catalog(
        Path(__file__).resolve().parents[1] / "packages/ai_orchestrator/examples/model_catalog.toml"
    )
    monkeypatch.setattr(
        _module.route_eval,
        "list_free_candidates",
        lambda route, creds: ["zzz-new:free", "google/gemma-4-31b-it:free"],
    )
    candidates, _note = resolve_route(
        "openrouter",
        catalog=catalog,
        credentials={},
        allow_tier=PREPAID,
        max_candidates=3,
        skip=frozenset(),
        live_refresh=True,
    )
    assert candidates[0] == "google/gemma-4-31b-it:free"
    assert "zzz-new:free" in candidates


def test_resolve_route_skips_failed_live_models(monkeypatch) -> None:
    from ai_orchestrator.catalog import load_model_catalog

    catalog = load_model_catalog(
        Path(__file__).resolve().parents[1] / "packages/ai_orchestrator/examples/model_catalog.toml"
    )
    monkeypatch.setattr(
        _module.route_eval,
        "list_free_candidates",
        lambda route, creds: ["bad:free", "good:free"],
    )
    candidates, _note = resolve_route(
        "openrouter",
        catalog=catalog,
        credentials={},
        allow_tier=PREPAID,
        max_candidates=3,
        skip=frozenset({("openrouter", "bad:free")}),
        live_refresh=True,
    )
    assert "bad:free" not in candidates
    assert "good:free" in candidates


def test_resolve_route_pins_without_live_refresh() -> None:
    from ai_orchestrator.catalog import load_model_catalog

    catalog = load_model_catalog(
        Path(__file__).resolve().parents[1] / "packages/ai_orchestrator/examples/model_catalog.toml"
    )
    candidates, _note = resolve_route(
        "meta",
        catalog=catalog,
        credentials={},
        allow_tier=PREPAID,
        max_candidates=3,
        skip=frozenset(),
        live_refresh=False,
    )
    assert candidates == ["muse-spark-1.3"]


def test_apply_tier_blocks_rewrites_skips_only() -> None:
    rows = [
        EvalResult("meta", "?", "t", False, None, None, None, "no-model", "T0"),
        EvalResult("meta", "m", "t", True, 1, 2, 3, None, "T0"),
    ]
    rewritten = apply_tier_blocks(rows, {"meta": "tier-blocked: needs billing"}, "T0")
    assert rewritten[0].error == "tier-blocked: needs billing"
    assert rewritten[1].error is None


def test_main_rejects_bad_allow_tier(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        _module.main(["--allow-tier", "everything"])
    assert exc.value.code == 2


def test_main_rejects_missing_catalog(capsys, tmp_path) -> None:
    with pytest.raises(SystemExit) as exc:
        _module.main(["--catalog", str(tmp_path / "nope.toml")])
    assert exc.value.code == 2


def test_main_runs_offline_with_tmp_catalog(monkeypatch, tmp_path, capsys) -> None:
    catalog = tmp_path / "cat.toml"
    catalog.write_text(
        "[[models]]\n"
        'route_id = "openrouter/free-test/m-free"\n'
        'provider = "openrouter"\n'
        'product = "openrouter_free"\n'
        'model = "m:free"\n'
        'location = "external"\n'
        'billing_source = "openrouter_free"\n'
        'cost_policy_tier = "free_only"\n'
        "[models.capabilities]\n"
        "chat = true\n",
        encoding="utf-8",
    )

    class Client:
        def complete(self, request):
            return SimpleNamespace(
                message=SimpleNamespace(content="def add2(x):\n    return x + 2"),
                usage=SimpleNamespace(input_tokens=1, output_tokens=2),
            )

    monkeypatch.setattr(_module.route_eval, "list_free_candidates", lambda r, c: ["m:free"])
    monkeypatch.setattr(
        _module.route_eval, "_clients", lambda creds: {"openrouter": lambda m: Client()}
    )
    code = _module.main(
        [
            "--catalog",
            str(catalog),
            "--snapshot-dir",
            str(tmp_path / "snap"),
            "--routes",
            "openrouter",
            "--tasks",
            "T0",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "openrouter/T0 (m:free): PASS" in out
    assert "snapshot:" in out and "resolved:" in out
    assert list((tmp_path / "snap").glob("route-eval-T0-*.json")) != []
    assert list((tmp_path / "snap").glob("ladder-resolved-*.json")) != []


def test_resolve_route_zero_returns_full_live_list(monkeypatch) -> None:
    from ai_orchestrator.catalog import load_model_catalog

    catalog = load_model_catalog(
        Path(__file__).resolve().parents[1] / "packages/ai_orchestrator/examples/model_catalog.toml"
    )
    live = ["m1:free", "m2:free", "m3:free", "m4:free", "m5:free"]
    monkeypatch.setattr(_module.route_eval, "list_free_candidates", lambda route, creds: list(live))
    candidates, _note = resolve_route(
        "openrouter",
        catalog=catalog,
        credentials={},
        allow_tier=PREPAID,
        max_candidates=0,
        skip=frozenset(),
        live_refresh=True,
    )
    for model in live:
        assert model in candidates


def test_main_rejects_negative_max_candidates(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        _module.main(["--max-candidates", "-1"])
    assert exc.value.code == 2
    assert "--max-candidates" in capsys.readouterr().err
