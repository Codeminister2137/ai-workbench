"""Granular per-source capability bands for the recommendation-only grade.

Owner decision (2026-10-23): grade each public source with its own categorical
band, deliberately more granular than a high/medium/low split, and publish the
result as a recommendation only. Runtime routing keeps reading the declared
catalog entry, so a band never admits, rejects or downgrades a request.

Three rules keep a band honest:

- **Per source.** Aider's ``percent_correct`` and SWE-bench's
  ``percent_resolved`` are different scales measured under different harnesses,
  so each source owns its own cutoffs. The two bands are reported side by side
  and are never averaged, merged or ranked against each other.
- **Fixed cutoffs on a dated calibration.** Each source's cutoffs were anchored
  on the p10/p25/median/p75/p90 of that source's published rows in the dated
  2026-10-22 snapshot, then fixed. A later refresh therefore moves a row
  between bands only when the published score itself changes, never because the
  band edges silently moved with the field. The bands are population bands, not
  equal-width bands: SWE-bench clusters near the top, so its upper edges are
  closer together than Aider's.
- **Absent stays absent.** A route with no published score returns ``None``. It
  is never imputed from a neighbouring family, and a missing prior is never
  reported as a weak band.

A band is a selection prior, never acceptance evidence
(``docs/repo-assistant/acceptance-criteria.md``): a public benchmark scores an
upstream model under its own agent scaffold, not this repository's CLI, and a
local L3 CLI measurement overrides a band for a specific task.

The vocabulary is deliberately distinct from
``ai_orchestrator.QualityThreshold`` (``low``/``standard``/``high``), which is
the *minimum requirement a task declares* for a catalog entry. A band is
*published evidence about an upstream family* — a different layer, which is why
this module never writes to a catalog entry and its labels are never readable
as requirement tiers. Reusing ``low``/``high`` here would make it easy for a
reader — or a future change feeding bands into selection — to confuse "what
this model is" with "what this task needs", so the two vocabularies must not
overlap.

Owner decision (2026-10-23): the labels are ``Frontier``, ``Very strong``,
``Strong``, ``Mediocre``, ``Weak``, ``Very weak``, strongest first. An earlier
``Frontier``/``Strong``/``Solid``/``Competent`` scale was rejected because
*Strong*, *Solid* and *Competent* read as synonyms, which made adjacent bands
indistinguishable at a glance. A five-tier ``Very high``/``High``/``Medium``/
``Low``/``Very low`` alternative was also rejected, both for the vocabulary
collision above and because it would discard the frontier distinction, which
the data supports and which is decision-relevant: frontier routes are the ones
worth preferring. **Only the labels changed; the calibrated cutoffs did not.**
A rename must never move a band edge.

Every source needs its own calibrated :class:`CapabilityBandScale`. Asking for
an uncalibrated source raises instead of reusing another source's cutoffs,
because the next source added (a different benchmark, a different population)
cannot share these edges honestly.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_BAND_FLOOR = 0.0
_PERCENT_MAX = 100.0
_PERCENT_SCALES = frozenset({"percent_correct", "percent_resolved"})


@dataclass(frozen=True, slots=True)
class CapabilityBandScale:
    """One source's fixed band cutoffs, anchored on a dated calibration.

    ``bands`` is ordered strongest first as ``(minimum_score, label)`` pairs and
    must reach the 0 floor, so every in-range score maps to exactly one label.
    ``calibration`` records which dated snapshot fixed the edges so a reader can
    re-derive them.
    """

    source: str
    scale: str
    calibration: str
    bands: tuple[tuple[float, str], ...]

    def __post_init__(self) -> None:
        if not self.bands:
            raise ValueError("A band scale needs at least one band")
        if self.scale not in _PERCENT_SCALES:
            raise ValueError(
                f"Band cutoffs are calibrated for a 0-100 percent scale, not {self.scale!r}"
            )
        labels = [label for _, label in self.bands]
        if any(not label.strip() for label in labels) or len(set(labels)) != len(labels):
            raise ValueError("Band labels must be non-empty and unique")
        minima = [minimum for minimum, _ in self.bands]
        if any(not math.isfinite(minimum) for minimum in minima):
            raise ValueError("Band cutoffs must be finite")
        if any(minimum < _BAND_FLOOR for minimum in minima):
            raise ValueError("Band cutoffs must not be negative")
        if minima != sorted(minima, reverse=True):
            raise ValueError("Band cutoffs must descend from the strongest band")
        if minima[-1] != _BAND_FLOOR:
            raise ValueError("The weakest band must start at the 0 floor")

    @property
    def labels(self) -> tuple[str, ...]:
        """Return this source's band labels from strongest to weakest."""

        return tuple(label for _, label in self.bands)

    def band_for_score(self, score: float) -> str:
        """Return the band for one score already validated on this scale."""

        for minimum, label in self.bands:
            if score >= minimum:
                return label
        raise ValueError(f"No band on {self.source!r} covers a score of {score}")


AIDER_POLYGLOT_SCALE = CapabilityBandScale(
    source="aider_polyglot",
    scale="percent_correct",
    calibration=(
        "artifacts/model-capability-priors-20261022/aider-polyglot.json "
        "(69 published rows, observed 2026-10-22): p10 12.0, p25 26.2, "
        "median 52.4, p75 70.2, p90 79.6, max 88.0; cutoffs 12 / 25 / 50 / 70 / 80"
    ),
    bands=(
        (80.0, "Frontier"),
        (70.0, "Very strong"),
        (50.0, "Strong"),
        (25.0, "Mediocre"),
        (12.0, "Weak"),
        (0.0, "Very weak"),
    ),
)

SWE_BENCH_VERIFIED_SCALE = CapabilityBandScale(
    source="swe_bench",
    scale="percent_resolved",
    calibration=(
        "artifacts/model-capability-priors-20261022/swe-bench-verified.json "
        "(180 published (model, scaffold) rows, observed 2026-10-22): "
        "p10 24.0, p25 40.6, median 55.4, p75 70.0, p90 74.4, max 79.2; "
        "cutoffs 24 / 40 / 55 / 70 / 75"
    ),
    bands=(
        (75.0, "Frontier"),
        (70.0, "Very strong"),
        (55.0, "Strong"),
        (40.0, "Mediocre"),
        (24.0, "Weak"),
        (0.0, "Very weak"),
    ),
)

BAND_SCALES: Mapping[str, CapabilityBandScale] = {
    AIDER_POLYGLOT_SCALE.source: AIDER_POLYGLOT_SCALE,
    SWE_BENCH_VERIFIED_SCALE.source: SWE_BENCH_VERIFIED_SCALE,
}


def _scale_for(source: str) -> CapabilityBandScale:
    scale = BAND_SCALES.get(source)
    if scale is None:
        raise ValueError(
            f"No band scale calibrated for source {source!r}; calibrate one for that "
            "source instead of reusing another source's cutoffs"
        )
    return scale


def band_for(source: str, score: float | None) -> str | None:
    """Return the recommendation-only band for one published score.

    ``score is None`` means the source published no score for that row, which
    returns ``None``: an absent prior is reported as absent, never as a low
    band. An uncalibrated ``source`` raises, so a new source must be calibrated
    rather than silently inheriting another source's edges.
    """

    scale = _scale_for(source)
    if score is None:
        return None
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ValueError("Capability score must be a number")
    value = float(score)
    if not math.isfinite(value) or not _BAND_FLOOR <= value <= _PERCENT_MAX:
        raise ValueError("Capability score must be a finite 0-100 percent value")
    return scale.band_for_score(value)


def band_counts(source: str, scores: Iterable[float | None]) -> dict[str, int]:
    """Count scored rows per band for one source, strongest band first.

    Rows without a score are excluded rather than counted as weak, so the
    counts only describe rows the source actually published.
    """

    scale = _scale_for(source)
    counts = dict.fromkeys(scale.labels, 0)
    for score in scores:
        label = band_for(source, score)
        if label is not None:
            counts[label] += 1
    return counts


def main() -> int:
    """Print a saved prior snapshot's band distribution; no network, no model."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prior", required=True, type=Path, help="saved CapabilityPrior JSON snapshot"
    )
    args = parser.parse_args()

    snapshot: Any = json.loads(args.prior.read_text(encoding="utf-8"))
    if not isinstance(snapshot, dict):
        raise SystemExit("snapshot must be a JSON object")
    source = snapshot.get("source")
    if not isinstance(source, str) or source not in BAND_SCALES:
        raise SystemExit(f"snapshot source is not calibrated for banding: {source!r}")
    rows = snapshot.get("scores")
    if not isinstance(rows, list):
        raise SystemExit("snapshot has no scores list")

    scale = BAND_SCALES[source]
    scored: list[float] = []
    unscored = 0
    for row in rows:
        if not isinstance(row, dict):
            raise SystemExit("snapshot row must be a JSON object")
        score = row.get("score")
        if score is None:
            unscored += 1
        elif isinstance(score, bool) or not isinstance(score, (int, float)):
            raise SystemExit(f"snapshot has a non-numeric score: {score!r}")
        else:
            scored.append(float(score))

    print(
        json.dumps(
            {
                "source": source,
                "scale": scale.scale,
                "calibration": scale.calibration,
                "row_count": len(rows),
                "scored_rows": len(scored),
                "unscored_rows": unscored,
                "band_counts": band_counts(source, scored),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
