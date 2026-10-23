"""Per-source capability bands: calibration and contract, no network or model call."""

import json
import sys

import pytest
from ai_orchestrator.models import QualityThreshold
from ai_provider.capability_bands import (
    AIDER_POLYGLOT_SCALE,
    BAND_SCALES,
    SWE_BENCH_VERIFIED_SCALE,
    CapabilityBandScale,
    band_counts,
    band_for,
    main,
)

BOUNDARIES = [
    # (score, aider band, swe band) — each pair of cutoffs is calibrated per source
    (80.0, "Frontier", "Frontier"),
    (79.9, "Very strong", "Frontier"),
    (76.0, "Very strong", "Frontier"),
    (70.0, "Very strong", "Very strong"),
    (60.0, "Strong", "Strong"),
    (51.0, "Strong", "Mediocre"),
    (30.0, "Mediocre", "Weak"),
    (12.0, "Weak", "Very weak"),
    (0.0, "Very weak", "Very weak"),
]

OWNER_APPROVED_LABELS = (
    "Frontier",
    "Very strong",
    "Strong",
    "Mediocre",
    "Weak",
    "Very weak",
)


def test_scale_is_six_bands_not_three():
    """The owner asked for more granularity than high/medium/low."""

    assert len(AIDER_POLYGLOT_SCALE.labels) == 6
    assert len(SWE_BENCH_VERIFIED_SCALE.labels) == 6
    assert AIDER_POLYGLOT_SCALE.labels == SWE_BENCH_VERIFIED_SCALE.labels


def test_labels_match_the_owner_approved_vocabulary():
    """2026-10-23: Strong/Solid/Competent read as synonyms, so they were renamed.

    Only the labels changed; a rename must never move a calibrated band edge.
    """

    assert AIDER_POLYGLOT_SCALE.labels == OWNER_APPROVED_LABELS
    assert SWE_BENCH_VERIFIED_SCALE.labels == OWNER_APPROVED_LABELS


def test_renaming_the_labels_left_every_cutoff_where_it_was():
    """Guards the calibration, which is the data rather than the vocabulary."""

    assert [minimum for minimum, _ in AIDER_POLYGLOT_SCALE.bands] == [
        80.0,
        70.0,
        50.0,
        25.0,
        12.0,
        0.0,
    ]
    assert [minimum for minimum, _ in SWE_BENCH_VERIFIED_SCALE.bands] == [
        75.0,
        70.0,
        55.0,
        40.0,
        24.0,
        0.0,
    ]


def test_band_labels_never_read_as_declared_quality_tiers():
    """A band is published evidence; QualityThreshold is a declared requirement.

    The two vocabularies must not overlap, so a band can never be misread as a
    declared minimum and a future change feeding bands into selection cannot
    silently satisfy a requirement.
    """

    declared = {tier.value for tier in QualityThreshold}
    assert declared == {"low", "standard", "high"}
    assert declared.isdisjoint(AIDER_POLYGLOT_SCALE.labels)


@pytest.mark.parametrize(("score", "aider", "swe"), BOUNDARIES)
def test_boundary_scores_map_to_exactly_one_band_per_source(score, aider, swe):
    assert band_for("aider_polyglot", score) == aider
    assert band_for("swe_bench", score) == swe


def test_cutoffs_are_calibrated_per_source_not_shared():
    """The same number means different things on two different scales."""

    assert band_for("aider_polyglot", 76.0) == "Very strong"
    assert band_for("swe_bench", 76.0) == "Frontier"
    assert band_for("aider_polyglot", 30.0) == "Mediocre"
    assert band_for("swe_bench", 30.0) == "Weak"


def test_absent_score_is_reported_as_absent_not_as_a_low_band():
    assert band_for("aider_polyglot", None) is None
    assert band_for("swe_bench", None) is None


def test_uncalibrated_source_is_rejected_rather_than_reusing_cutoffs():
    with pytest.raises(ValueError, match="No band scale calibrated"):
        band_for("lmarena_elo", 76.0)


@pytest.mark.parametrize("score", [-0.1, 100.1, float("nan"), float("inf"), True, "88.0"])
def test_invalid_scores_are_rejected(score):
    with pytest.raises(ValueError):
        band_for("aider_polyglot", score)


@pytest.mark.parametrize(
    "bands",
    [
        ((80.0, "Frontier"), (70.0, "Strong"), (90.0, "Solid")),  # not descending
        ((80.0, "Frontier"), (5.0, "Strong")),  # no 0 floor
        ((80.0, "Frontier"), (0.0, "Strong"), (-1.0, "Weak")),  # negative cutoff
        ((80.0, "Frontier"), (0.0, "Frontier")),  # duplicate label
        (),  # no bands
    ],
)
def test_scale_rejects_cutoffs_that_cannot_cover_the_range(bands):
    with pytest.raises(ValueError):
        CapabilityBandScale(
            source="aider_polyglot", scale="percent_correct", calibration="", bands=bands
        )


def test_scale_rejects_a_non_percent_scale():
    """A new benchmark on another scale must be calibrated, never assumed 0-100."""

    with pytest.raises(ValueError, match="percent scale"):
        CapabilityBandScale(
            source="lmarena_elo", scale="elo", calibration="", bands=((0.0, "Frontier"),)
        )


def test_counts_are_ordered_by_strength_and_cover_scored_rows_only():
    counts = band_counts("aider_polyglot", [88.0, 41.8, None, 4.9])
    assert list(counts) == list(AIDER_POLYGLOT_SCALE.labels)
    assert sum(counts.values()) == 3
    assert counts == {
        "Frontier": 1,
        "Very strong": 0,
        "Strong": 0,
        "Mediocre": 1,
        "Weak": 0,
        "Very weak": 1,
    }


def test_every_declared_source_has_its_own_calibrated_scale():
    assert set(BAND_SCALES) == {"aider_polyglot", "swe_bench"}
    assert BAND_SCALES["aider_polyglot"] is AIDER_POLYGLOT_SCALE
    assert BAND_SCALES["swe_bench"] is SWE_BENCH_VERIFIED_SCALE


def test_command_line_reports_the_band_distribution_of_a_saved_snapshot(
    tmp_path, monkeypatch, capsys
):
    snapshot = tmp_path / "prior.json"
    snapshot.write_text(
        json.dumps(
            {
                "source": "aider_polyglot",
                "scores": [
                    {"model": "a", "score": 88.0},
                    {"model": "b", "score": 41.8},
                    {"model": "c", "score": None},
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["capability_bands", "--prior", str(snapshot)])

    assert main() == 0

    reported = json.loads(capsys.readouterr().out)
    assert reported["source"] == "aider_polyglot"
    assert reported["scale"] == "percent_correct"
    assert reported["row_count"] == 3
    assert reported["scored_rows"] == 2
    assert reported["unscored_rows"] == 1
    assert reported["band_counts"]["Frontier"] == 1
    assert reported["band_counts"]["Mediocre"] == 1


def test_command_line_refuses_a_source_that_was_never_calibrated(tmp_path, monkeypatch):
    snapshot = tmp_path / "prior.json"
    snapshot.write_text(json.dumps({"source": "other", "scores": []}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["capability_bands", "--prior", str(snapshot)])

    with pytest.raises(SystemExit, match="not calibrated"):
        main()
