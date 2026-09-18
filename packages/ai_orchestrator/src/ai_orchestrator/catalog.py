from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from ai_orchestrator.models import (
    BackendLocation,
    LatencyTarget,
    ModelBackend,
    ModelCapabilities,
    ModelCatalogEntry,
    QualityThreshold,
)


def load_model_catalog(path: Path) -> tuple[ModelCatalogEntry, ...]:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    raw_models = raw.get("models", [])
    if not isinstance(raw_models, list):
        raise ValueError("Model catalog must define a [[models]] list.")

    return tuple(_catalog_entry(item) for item in raw_models)


def _catalog_entry(item: dict[str, Any]) -> ModelCatalogEntry:
    provider = _required_string(item, "provider")
    model = _required_string(item, "model")
    location = BackendLocation(_required_string(item, "location"))
    quality = QualityThreshold(str(item.get("quality", QualityThreshold.STANDARD.value)))
    latency = LatencyTarget(str(item.get("latency", LatencyTarget.INTERACTIVE.value)))
    base_url = item.get("base_url")
    notes = item.get("notes")
    capabilities = _capabilities(item.get("capabilities", {}))

    return ModelCatalogEntry(
        backend=ModelBackend(
            provider=provider,
            model=model,
            location=location,
            base_url=base_url if isinstance(base_url, str) else None,
            capabilities=capabilities,
        ),
        quality=quality,
        latency=latency,
        notes=notes if isinstance(notes, str) else None,
    )


def _required_string(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Model catalog entry must define a non-empty {key!r}.")
    return value.strip()


def _capabilities(raw: object) -> ModelCapabilities:
    if not isinstance(raw, dict):
        raise ValueError("Model capabilities must be a table.")

    return ModelCapabilities(
        chat=_bool(raw, "chat", default=True),
        streaming=_bool(raw, "streaming", default=False),
        tools=_bool(raw, "tools", default=False),
        structured_output=_bool(raw, "structured_output", default=False),
        multimodal_input=_bool(raw, "multimodal_input", default=False),
        embeddings=_bool(raw, "embeddings", default=False),
    )


def _bool(raw: dict[str, Any], key: str, *, default: bool) -> bool:
    value = raw.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"Capability {key!r} must be a boolean.")
    return value
