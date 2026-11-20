"""Read-only catalog query regressions."""

import json
from pathlib import Path
from urllib.request import urlopen

import pytest
from dashboard_test_http import serve_dashboard
from orchestrator_view import query_routes

CATALOG = (
    Path(__file__).resolve().parents[3] / "packages/ai_orchestrator/examples/model_catalog.toml"
)


def test_search_preserves_recommendation_and_exposes_recorded_grades():
    original = CATALOG.read_bytes()
    result = query_routes(CATALOG)
    searched = query_routes(CATALOG, search="OLLAMA quality")
    assert searched["catalog"]
    assert all(row["provider"] == "ollama" for row in searched["catalog"])
    assert all("quality" in row["notes"].lower() for row in searched["catalog"])
    assert searched["routes"] == result["routes"]
    assert all(row["quality"] in {"low", "standard", "high"} for row in result["catalog"])
    assert CATALOG.read_bytes() == original
    assert query_routes(CATALOG, search="no-such-catalog-model-xyz")["catalog"] == []


def test_zero_admission_retains_reasons_and_catalog():
    result = query_routes(CATALOG, capabilities=["embeddings"], privacy="local_only")
    assert result["admitted"] is False
    assert result["ok"] is True
    assert result["rejected"]
    assert result["catalog"]
    assert all(row["reason"] for row in result["rejected"])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"capabilities": ["made-up"]},
        {"privacy": "made-up"},
        {"cost_tier": "made-up"},
    ],
)
def test_invalid_filters(kwargs):
    with pytest.raises(ValueError):
        query_routes(CATALOG, **kwargs)


def test_http_query(tmp_path):
    with serve_dashboard(tmp_path, config={"catalog_path": str(CATALOG)}) as (base, _):
        with urlopen(
            base + "/api/orchestrator/routes?search=ollama&privacy=local_only"
        ) as response:
            result = json.load(response)
    assert result["ok"]
    assert result["catalog"]
    assert all(row["provider"] == "ollama" for row in result["catalog"])
    assert "capabilities" in result["options"]
