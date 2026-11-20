"""Tests for scripts/file-brief.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "file-brief.py"


def _load():
    spec = importlib.util.spec_from_file_location("file_brief", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_payload_carries_options() -> None:
    mod = _load()
    payload = mod.build_payload(title="Merge brief: x", body="b", options=["Merge now", "Hold"])
    assert payload["options"] == ["Merge now", "Hold"]
    assert payload["type"] == "decision"
    assert payload["created_by"] == "supervisor"
    assert payload["assignee"] == "owner"


def test_decision_requires_two_options() -> None:
    mod = _load()
    with pytest.raises(ValueError, match="at least two"):
        mod.build_payload(title="t", body="b", options=["Only one"])
    with pytest.raises(ValueError, match="title is required"):
        mod.build_payload(title="  ", body="b", options=["A", "B"])
    # Non-decision items may carry zero options.
    payload = mod.build_payload(title="t", body="b", options=[], item_type="note")
    assert payload["options"] == []


def _decision_args(extra=None):
    base = [
        "--title",
        "t",
        "--body",
        "b",
        "--option",
        "A: first",
        "--option",
        "B: second",
        "--tradeoff",
        "A | fast | narrow",
        "--tradeoff",
        "B | broad | slow",
        "--recommend",
        "A",
        "--recommendation",
        "Speed matters most.",
    ]
    return base + (extra or [])


def test_dry_run_prints_payload(capsys) -> None:
    mod = _load()
    code = mod.main(_decision_args(["--dry-run"]))
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["options"] == ["A: first", "B: second"]
    assert payload["metadata"]["tradeoffs"] == [
        {"option": "A: first", "pro": "fast", "con": "narrow"},
        {"option": "B: second", "pro": "broad", "con": "slow"},
    ]
    assert payload["metadata"]["recommendation"] == {
        "option": "A: first",
        "why": "Speed matters most.",
    }
    assert "Trade-offs:" in payload["body"]
    assert "Recommendation: A: first" in payload["body"]


def test_main_rejects_optionless_decision(capsys) -> None:
    mod = _load()
    assert mod.main(["--title", "t", "--body", "b"]) == 2
    assert "--tradeoff per option" in capsys.readouterr().err
    assert (
        mod.main(
            [
                "--title",
                "t",
                "--body",
                "b",
                "--option",
                "Only",
                "--tradeoff",
                "Only | pro | con",
                "--recommend",
                "Only",
                "--recommendation",
                "Why.",
            ]
        )
        == 2
    )
    assert "at least two" in capsys.readouterr().err


def test_decision_requires_tradeoffs_and_recommendation(capsys) -> None:
    mod = _load()
    assert mod.main(["--title", "t", "--body", "b", "--option", "A", "--option", "B"]) == 2
    assert "--tradeoff per option" in capsys.readouterr().err
    assert (
        mod.main(
            [
                "--title",
                "t",
                "--body",
                "b",
                "--option",
                "A",
                "--option",
                "B",
                "--tradeoff",
                "A | pro | con",
            ]
        )
        == 2
    )


def test_tradeoff_coverage_validated() -> None:
    mod = _load()
    good = dict(title="t", body="b", options=["A: x", "B: y"])
    with pytest.raises(ValueError, match="exactly once"):
        mod.build_payload(**good, tradeoffs=["A | pro | con"])
    with pytest.raises(ValueError, match="exactly one option"):
        mod.build_payload(
            **good,
            tradeoffs=["A | pro | con", "Z | pro | con"],
        )
    with pytest.raises(ValueError, match="LABEL \\| PRO \\| CON"):
        mod.build_payload(**good, tradeoffs=["A | onlypro", "B | pro | con"])
    with pytest.raises(ValueError, match="both --recommend"):
        mod.build_payload(
            **good,
            tradeoffs=["A | pro | con", "B | pro | con"],
            recommend="A",
        )
    with pytest.raises(ValueError, match="exactly one option"):
        mod.build_payload(
            **good,
            tradeoffs=["A | pro | con", "B | pro | con"],
            recommend="Z",
            recommendation="Why.",
        )
    payload = mod.build_payload(
        **good,
        tradeoffs=["B | broad | slow", "A | fast | narrow"],
        recommend="b",
        recommendation="Coverage wins.",
    )
    assert payload["metadata"]["recommendation"]["option"] == "B: y"


def test_metadata_items_validated_and_merged(capsys) -> None:
    mod = _load()
    code = mod.main(_decision_args(["--metadata", "owner_gate=g1", "--dry-run"]))
    assert code == 0
    assert json.loads(capsys.readouterr().out)["metadata"]["owner_gate"] == "g1"
    assert mod.main(_decision_args(["--metadata", "no-equals"])) == 2
    assert "KEY=VALUE" in capsys.readouterr().err


def test_followup_prepends_body_and_metadata() -> None:
    mod = _load()
    payload = mod.build_payload(
        title="t",
        body="details",
        options=["A", "B"],
        needs_owner="Pick A or B.",
        needs_ai="Implement the pick.",
    )
    assert payload["body"].startswith(
        "Needs from you (owner): Pick A or B.\nNeeds from AI: Implement the pick.\n\n"
    )
    assert payload["body"].endswith("details")
    assert payload["metadata"] == {
        "followup": {"owner": "Pick A or B.", "ai": "Implement the pick."}
    }


def test_followup_blank_means_absent() -> None:
    mod = _load()
    payload = mod.build_payload(title="t", body="b", options=["A", "B"], needs_owner="  ")
    assert payload["body"] == "b"
    assert "metadata" not in payload


def test_assignee_flag_validated() -> None:
    mod = _load()
    payload = mod.build_payload(title="t", body="b", options=[], item_type="task", assignee="agent")
    assert payload["assignee"] == "agent"
    with pytest.raises(ValueError, match="assignee"):
        mod.build_payload(title="t", body="b", options=["A", "B"], assignee="someone")


def test_ai_only_followup_to_owner_warns(capsys) -> None:
    mod = _load()
    code = mod.main(
        ["--title", "t", "--body", "b", "--type", "task", "--needs-ai", "Do it.", "--dry-run"]
    )
    assert code == 0
    assert "--assignee agent" in capsys.readouterr().err
    code = mod.main(
        [
            "--title",
            "t",
            "--body",
            "b",
            "--type",
            "task",
            "--needs-ai",
            "Do it.",
            "--assignee",
            "agent",
            "--dry-run",
        ]
    )
    assert code == 0
    assert capsys.readouterr().err == ""


def test_tier_metadata_optional_and_validated() -> None:
    mod = _load()
    payload = mod.build_payload(title="t", body="b", options=["A", "B"], tier="tier2")
    assert payload["metadata"] == {"tier": "tier2"}
    plain = mod.build_payload(title="t", body="b", options=["A", "B"])
    assert "metadata" not in plain
    with pytest.raises(ValueError, match="tier"):
        mod.build_payload(title="t", body="b", options=["A", "B"], tier="tier9")
