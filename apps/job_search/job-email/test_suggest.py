"""Suggestion prompt/routing/record contracts; no live model calls."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from evidence import analyze_vacancy_fit
from models import CandidateProfile, EvidenceStatus, JobVacancy, SkillEvidence
from suggest import (
    build_suggestion_prompt,
    execute_suggestion_plan,
    parse_suggestions,
    record_suggestions,
    route_suggestion_task,
)

CATALOG_TOML = """
[[models]]
route_id = "ollama/qwen2.5-coder:14b"
provider = "ollama"
product = "ollama"
model = "qwen2.5-coder:14b"
location = "local"
access_method = "local_runtime"
auth_method = "none"
billing_source = "local_free"
cost_policy_tier = "local_only"
quality = "standard"
latency = "interactive"

[models.capabilities]
chat = true
streaming = true
tools = false
structured_output = false
multimodal_input = false
embeddings = false

[models.context_limits]
context_window_tokens = 32768
runtime_context_tokens = 4096

[models.estimate]
typical_latency_seconds = 13.0
input_cost_per_million_tokens = 0
output_cost_per_million_tokens = 0
source = "synthetic test fixture"

[[models]]
route_id = "meta/muse-spark-1.3"
provider = "meta"
product = "meta_api"
model = "muse-spark-1.3"
location = "external"
access_method = "provider_api"
auth_method = "api_key"
billing_source = "meta_api_billing"
cost_policy_tier = "prepaid_credits_allowed"
quality = "high"
latency = "interactive"

[models.capabilities]
chat = true
streaming = true
tools = false
structured_output = false
multimodal_input = false
embeddings = false

[models.context_limits]
context_window_tokens = 128000
runtime_context_tokens = 4096

[models.estimate]
typical_latency_seconds = 8.0
input_cost_per_million_tokens = 0
output_cost_per_million_tokens = 0
source = "synthetic test fixture"
"""


def profile():
    return CandidateProfile(
        applicant_name="Synthetic Applicant",
        applicant_location="Nowhere",
        applicant_summary="Synthetic.",
        portfolio_url="https://example.invalid",
        linkedin_url="https://example.invalid",
        skills={
            "Python": SkillEvidence(
                "Python",
                EvidenceStatus.DEMONSTRATED,
                notes="Five years of backend work.",
                source_kinds=("cv", "github"),
            ),
        },
    )


def vacancy():
    return JobVacancy(
        id="vac-suggest",
        company="Example Corp",
        title="Python Developer",
        location="Remote",
        description="Build backend services in Python.",
        required_skills=("Python", "Rust"),
    )


def test_prompt_is_deterministic_and_evidence_bound():
    verdicts = analyze_vacancy_fit(vacancy(), profile()).verdicts
    first = build_suggestion_prompt(vacancy(), verdicts, profile())
    second = build_suggestion_prompt(vacancy(), verdicts, profile())
    assert first == second
    assert "Python Developer" in first and "Example Corp" in first
    assert "Python: strong" in first
    assert "Rust: missing" in first
    assert "Never invent" in first
    assert "cv, github" in first


def test_parse_suggestions_splits_and_strips():
    assert parse_suggestions("1. Emphasize asyncio.\n\n  \nPROHIBITED:\n- Rust") == (
        "1. Emphasize asyncio.",
        "PROHIBITED:",
        "- Rust",
    )
    assert parse_suggestions("  \n ") == ()


def test_local_only_profile_routes_to_ollama(tmp_path):
    catalog_file = tmp_path / "catalog.toml"
    catalog_file.write_text(CATALOG_TOML, encoding="utf-8")
    from ai_orchestrator import load_model_catalog

    catalog = load_model_catalog(catalog_file)
    plan = route_suggestion_task(catalog, "synthetic prompt")
    assert plan.target.route_id == "ollama/qwen2.5-coder:14b"
    assert plan.target.provider == "ollama"


def test_routing_failure_raises_before_any_call(tmp_path):
    meta_only = CATALOG_TOML.split("[[models]]")
    catalog_file = tmp_path / "catalog.toml"
    catalog_file.write_text("[[models]]" + meta_only[2], encoding="utf-8")
    from ai_orchestrator import load_model_catalog

    catalog = load_model_catalog(catalog_file)
    with pytest.raises(ValueError, match="suggestion routing failed"):
        route_suggestion_task(catalog, "synthetic prompt")


def test_unsupported_executor_rejected():
    plan = SimpleNamespace(target=SimpleNamespace(provider="requesty", model="x", base_url=None))
    with pytest.raises(ValueError, match="unsupported suggestion executor"):
        execute_suggestion_plan(plan, "synthetic prompt")


def test_record_carries_routing_and_parsed_lines():
    target = SimpleNamespace(
        route_id="ollama/qwen2.5-coder:14b",
        provider="ollama",
        model="qwen2.5-coder:14b",
        cost_policy_tier=SimpleNamespace(value="local_only"),
    )
    plan = SimpleNamespace(target=target)
    record = record_suggestions(plan, "prompt-text", "1. Do the thing.\n\n- Never lie.")
    assert record.route_id == "ollama/qwen2.5-coder:14b"
    assert record.suggestions == ("1. Do the thing.", "- Never lie.")
    assert len(record.prompt_sha256) == 64
