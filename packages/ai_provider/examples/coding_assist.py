"""Compatibility exports for the package-owned coding assistant helpers."""

from typing import Any

from ai_provider import coding_assist as _coding_assist
from ai_provider.coding_assist import (
    CodingAssistResult,
    backend_config_from_execution_target,
    coding_request_from_prompt,
    coding_task_profile,
)
from ai_provider.ollama_runtime import ensure_ollama_server


def run_coding_prompt(*args: Any, **kwargs: Any) -> CodingAssistResult:
    """Forward to the package implementation while preserving old patch points."""

    original = _coding_assist.ensure_ollama_server
    _coding_assist.ensure_ollama_server = ensure_ollama_server
    try:
        return _coding_assist.run_coding_prompt(*args, **kwargs)
    finally:
        _coding_assist.ensure_ollama_server = original


__all__ = [
    "CodingAssistResult",
    "backend_config_from_execution_target",
    "coding_request_from_prompt",
    "coding_task_profile",
    "run_coding_prompt",
]
