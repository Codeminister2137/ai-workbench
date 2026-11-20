"""Tests for the allowance-snapshot glue (first eval loop)."""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "ai_orchestrator" / "src"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "ai_provider" / "src"))

_SPEC = importlib.util.spec_from_file_location(
    "snapshot_allowances", REPO_ROOT / "scripts" / "snapshot-allowances.py"
)
_snapshot = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_snapshot)


def test_dedupe_keeps_first_row_per_bucket() -> None:
    rows = [
        {"provider": "codex", "bucket_id": "codex", "window": "primary", "used_percent": 0.0},
        {"provider": "codex", "bucket_id": "codex", "window": "primary", "used_percent": 5.0},
        {"provider": "codex", "bucket_id": "codex", "window": "secondary", "used_percent": 1.0},
    ]
    unique = _snapshot._dedupe(rows)
    assert [(row["window"], row["used_percent"]) for row in unique] == [
        ("primary", 0.0),
        ("secondary", 1.0),
    ]


def test_dedupe_empty() -> None:
    assert _snapshot._dedupe([]) == []
