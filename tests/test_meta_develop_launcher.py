"""Offline checks for the bounded Meta CLI launcher, never inference."""

import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "meta_develop", Path(__file__).parents[1] / "scripts/meta-develop.py"
)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
URL = "https://api.meta.ai/v1/responses"


@pytest.mark.parametrize(
    "extra",
    [
        {"model": "other"},
        {"stream": True},
        {"previous_response_id": "old"},
        {"input": "x" * 131073},
        {"max_output_tokens": -1},
        {"tools": [{"type": "web_search"}]},
        {"input": [{"type": "input_image"}]},
    ],
)
def test_unsafe_or_unbounded_payload_refused(extra):
    with pytest.raises(ValueError):
        launcher.admit({"model": "muse-spark-1.3", **extra}, URL, "POST")


def test_output_cap_and_nonpersistent_mode_preserve_context():
    context = [{"role": "user", "content": "Keep complete instructions"}]
    body = json.loads(
        launcher.admit(
            {
                "model": "muse-spark-1.3",
                "input": context,
                "store": True,
                "max_output_tokens": 99999,
            },
            URL,
            "POST",
        )
    )
    assert body["input"] == context
    assert body["store"] is False
    assert body["max_output_tokens"] == 8192
    assert launcher.RESERVE * launcher.MAX_CALLS <= 2


def test_other_destination_refused():
    with pytest.raises(ValueError):
        launcher.admit({"model": "muse-spark-1.3"}, "https://example.com", "POST")


def test_shared_allowance_stops_before_ninth_send_and_after_expiry():
    receipt = {"requests": []}
    for _ in range(8):
        launcher.reserve(receipt, 1, 100)
    with pytest.raises(ValueError):
        launcher.reserve(receipt, 2, 100)
    assert len(receipt["requests"]) == 8
    with pytest.raises(ValueError):
        launcher.reserve({"requests": []}, 900, 100)


def test_catalog_contains_only_selected_meta_route():
    import tomllib

    catalog = launcher.meta_catalog(
        Path(__file__).parents[1] / "packages/ai_orchestrator/examples/model_catalog.toml"
    )
    assert [model["route_id"] for model in tomllib.loads(catalog)["models"]] == [
        "meta/muse-spark-1.3"
    ]
