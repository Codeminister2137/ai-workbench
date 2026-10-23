"""Conservative route mapping proposals and saved-reader reproduction."""

import json
import re
import tomllib
from datetime import date
from pathlib import Path

import pytest
from ai_provider.route_family_matcher import propose_route_family
from ai_provider.source_info import CapabilityScore

CHECKED = date(2026, 10, 23)


def row(model, **kwargs):
    return CapabilityScore(
        source="aider_polyglot",
        benchmark="polyglot",
        split="polyglot",
        model=model,
        model_display=model,
        score=50,
        scale="percent_correct",
        **kwargs,
    )


def propose(model, rows):
    return propose_route_family("test/route", model, rows, checked=CHECKED)


@pytest.mark.parametrize(
    ("model", "published", "confidence", "gap"),
    [
        ("GLM-4.5", "GLM 4.5", "exact", None),
        ("gemini-3.1-pro", "gemini 3 pro", "family", "version gap"),
        ("qwen3:14b", "openrouter/qwen/qwen3-32b", "family", "size gap"),
        ("gemini-3-pro-high", "gemini 3 pro", "family", "high"),
        ("gpt-5-mini", "openai/gpt-5", "family", "mini"),
        ("gpt-6.1-sol", "openai/gpt-5", "unmatched", None),
        ("deepseek-coder-v2:16b", "deepseek/deepseek-chat", "unmatched", None),
        ("unknown-4", "unknown-3", "unmatched", None),
        ("gpt-5:free", "openai/gpt-5", "unmatched", None),
        ("qwen3:14b-q4", "qwen3-14b", "unmatched", None),
        ("auto", "auto", "unmatched", None),
    ],
)
def test_layers(model, published, confidence, gap):
    result = propose(model, [row(published)])
    assert result.confidence == confidence
    assert result.reason
    assert result.checked == CHECKED
    if gap:
        assert gap in result.gap
    if confidence == "unmatched":
        assert result.matched_row is None


def test_alias_warning_and_configuration():
    result = propose("deepseek-chat", [row("deepseek/deepseek-chat", configuration="edit=whole")])
    assert result.confidence == "alias"
    assert "Rolling/unpinned alias" in result.reason
    assert "weak evidence" in result.reason
    assert result.configuration == "edit=whole"


def test_empty():
    assert propose("gpt-5", []).matched_row is None


def test_configuration_and_order_are_explicit():
    rows = [
        row("openai/gpt-5", configuration=f"edit=diff; reasoning={effort}")
        for effort in ("low", "high", "medium")
    ]
    first = propose("gpt-5.1", rows)
    assert first == propose("gpt-5.1", reversed(rows))
    assert first.configuration == "edit=diff; reasoning=high"
    assert first.configuration in first.reason


def test_unscored_row_carries_no_prior():
    candidate = row("gpt-5")
    from dataclasses import replace

    assert propose("gpt-5", [replace(candidate, score=None)]).matched_row is None


def test_saved_reader_snapshot_reproduction():
    root = Path(__file__).resolve().parents[1]
    directory = root / "artifacts/model-capability-priors-20261022"
    paths = [directory / name for name in ("aider-polyglot.json", "swe-bench-verified.json")]
    if not all(path.exists() for path in paths):
        pytest.skip("Private saved reader snapshots are unavailable")
    # These are serialized CapabilityPrior outputs, not raw HTML/API payloads.
    rows = [
        CapabilityScore(**item)
        for path in paths
        for item in json.loads(path.read_text(encoding="utf-8"))["scores"]
    ]
    catalog = tomllib.loads(
        (root / "packages/ai_orchestrator/examples/model_catalog.toml").read_text(encoding="utf-8")
    )
    table = (root / "packages/ai_provider/docs/route-upstream-family-mapping.md").read_text(
        encoding="utf-8"
    )
    agreements = 0
    disagreements = []
    for entry in catalog["models"]:
        route = entry["route_id"]
        line = next(line for line in table.splitlines() if line.startswith(f"| `{route}` |"))
        expected = re.search(r"`(exact|family|alias|unmatched)`", line)[1]
        result = propose_route_family(route, entry["model"], rows, checked=CHECKED)
        cells = line.split("|")
        # Agreement requires confidence AND a row actually cited in the table.
        agreed = result.confidence == expected and (
            result.matched_row is None or f"`{result.matched_row.model}`" in cells[4]
        )
        agreements += agreed
        if not agreed:
            disagreements.append(
                {
                    "route": route,
                    "proposal": result.matched_row.model if result.matched_row else None,
                    "reason": result.reason,
                    "gap": result.gap,
                    "table": cells[4:7],
                }
            )
    print(
        json.dumps(
            {
                "agreements": agreements,
                "disagreements": disagreements,
                "total": len(catalog["models"]),
            },
            indent=2,
        )
    )
    assert len(catalog["models"]) == 18
    assert agreements == 13
    assert {item["route"] for item in disagreements} == {
        "openai/codex-gpt-5.5",
        "openai/api-gpt-5.1",
        "openai/api-gpt-5-mini",
        "requesty/openai/gpt-5.1",
        "requesty/openai/gpt-5-mini",
    }


def test_decimal_version_is_not_folded_into_integer():
    assert propose("glm-45", [row("glm-4.5")]).confidence != "exact"


def test_unknown_vendor_is_not_assumed():
    assert propose("unverified/gpt-5.1", [row("openai/gpt-5")]).confidence == "unmatched"


def test_effort_suffix_never_claims_exact():
    result = propose("gemini-3-pro-high", [row("gemini-3-pro-high")])
    assert result.confidence == "family"
    assert "high" in result.gap
