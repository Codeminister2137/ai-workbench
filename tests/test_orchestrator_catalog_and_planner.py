from __future__ import annotations

from pathlib import Path

from ai_orchestrator import (
    BackendLocation,
    ModelBackend,
    ModelCapabilities,
    TaskProfile,
    load_model_catalog,
    plan_execution,
    recommend_model,
)
from ai_orchestrator.models import LatencyTarget, ModelCatalogEntry, QualityThreshold


def test_load_model_catalog_reads_toml_entries(tmp_path: Path) -> None:
    catalog_path = tmp_path / "models.toml"
    catalog_path.write_text(
        """
[[models]]
provider = "ollama"
model = "llama3.2"
location = "local"
quality = "standard"
latency = "interactive"
base_url = "http://localhost:11434"

[models.capabilities]
chat = true
structured_output = false
""",
        encoding="utf-8",
    )

    catalog = load_model_catalog(catalog_path)

    assert len(catalog) == 1
    assert catalog[0].backend.provider == "ollama"
    assert catalog[0].backend.model == "llama3.2"
    assert catalog[0].backend.location is BackendLocation.LOCAL
    assert catalog[0].backend.capabilities.chat is True
    assert catalog[0].backend.base_url == "http://localhost:11434"


def test_plan_execution_converts_recommendation_to_neutral_target() -> None:
    candidate = ModelCatalogEntry(
        backend=ModelBackend(
            provider="ollama",
            model="llama3.2",
            location=BackendLocation.LOCAL,
            base_url="http://localhost:11434",
            capabilities=ModelCapabilities(),
        ),
        quality=QualityThreshold.STANDARD,
        latency=LatencyTarget.INTERACTIVE,
    )
    recommendation = recommend_model(TaskProfile(), (candidate,))

    plan = plan_execution(TaskProfile(), recommendation, timeout_seconds=10)

    assert plan.target.provider == "ollama"
    assert plan.target.model == "llama3.2"
    assert plan.target.base_url == "http://localhost:11434"
    assert plan.target.timeout_seconds == 10
    assert plan.reasons == recommendation.reasons


def test_plan_execution_allows_targets_outside_ai_provider() -> None:
    candidate = ModelCatalogEntry(
        backend=ModelBackend(
            provider="custom",
            model="model",
            location=BackendLocation.LOCAL,
            capabilities=ModelCapabilities(),
        ),
    )
    recommendation = recommend_model(TaskProfile(), (candidate,))

    plan = plan_execution(TaskProfile(), recommendation)

    assert plan.target.provider == "custom"
    assert plan.target.model == "model"
