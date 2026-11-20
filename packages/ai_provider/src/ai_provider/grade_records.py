"""Measured capability grade records: eval verdicts become catalog evidence.

Smoke probes (``capability_eval``) emit one JSON verdict per line. This
module folds those verdicts into one dated record per route and writes
them under a grades directory that the catalog loader can overlay on
declarations (measured wins; see ``ai_orchestrator.catalog``).

Only ``pass``/``fail`` verdicts become booleans. Anything else
(``error``, ``unknown``) is excluded: an inconclusive probe must never
record support as false. Records never overwrite: one file per route
per UTC date, ``<route-slug>-<YYYY-MM-DD>.json``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CAPABILITY_FLAGS = (
    "chat",
    "streaming",
    "tools",
    "structured_output",
    "multimodal_input",
    "embeddings",
)


@dataclass(frozen=True, slots=True)
class GradeRecord:
    """One route's measured capability flags with provenance."""

    route_id: str
    checked_utc: str
    capabilities: dict[str, bool]
    evidence: str

    def to_json(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "checked_utc": self.checked_utc,
            "capabilities": dict(self.capabilities),
            "evidence": self.evidence,
        }


def _slug(route_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", route_id.strip().lower()).strip("-")
    if not slug:
        raise ValueError("Route id must contain slug-safe characters")
    return slug


def _record_date(checked_utc: str) -> str:
    try:
        moment = datetime.fromisoformat(checked_utc.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Verdict checked_utc is not an ISO instant") from None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).date().isoformat()


def fold_verdicts(verdicts: list[dict[str, Any]], *, evidence: str) -> list[GradeRecord]:
    """Fold raw verdict dicts into one record per route.

    Later verdicts for the same route+capability win (re-probes within
    one run supersede). Inconclusive statuses are dropped; a route with
    no conclusive verdict yields no record.
    """
    if not evidence.strip():
        raise ValueError("Grade records require an evidence reference")
    folded: dict[str, dict[str, tuple[str, bool]]] = {}
    for verdict in verdicts:
        if not isinstance(verdict, dict):
            raise ValueError("Each verdict must be a JSON object")
        route_id = verdict.get("route_id")
        capability = verdict.get("capability")
        status = verdict.get("status")
        checked = verdict.get("checked_utc")
        if not isinstance(route_id, str) or not route_id.strip():
            raise ValueError("Verdict needs a route_id")
        if capability not in CAPABILITY_FLAGS:
            raise ValueError(f"Unknown capability: {capability!r}")
        if not isinstance(checked, str) or not checked.strip():
            raise ValueError("Verdict needs checked_utc")
        if status == "pass":
            value: bool | None = True
        elif status == "fail":
            value = False
        else:
            continue  # error/unknown: inconclusive, never recorded
        folded.setdefault(route_id, {})[capability] = (checked, value)
    records = []
    for route_id, flags in folded.items():
        latest = max(checked for checked, _ in flags.values())
        records.append(
            GradeRecord(
                route_id=route_id,
                checked_utc=latest,
                capabilities={name: value for name, (_, value) in sorted(flags.items())},
                evidence=evidence,
            )
        )
    records.sort(key=lambda record: record.route_id)
    return records


def record_grades(eval_output: Path, grades_dir: Path, *, evidence: str) -> list[Path]:
    """Write grade records from one eval JSONL output. Never overwrites."""
    verdicts = []
    for lineno, line in enumerate(eval_output.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            verdicts.append(json.loads(line))
        except ValueError:
            raise ValueError(f"Invalid verdict JSON on line {lineno}") from None
    written = []
    for record in fold_verdicts(verdicts, evidence=evidence):
        target = grades_dir / f"{_slug(record.route_id)}-{_record_date(record.checked_utc)}.json"
        if target.exists():
            raise FileExistsError(f"Grade record already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(record.to_json(), indent=1) + "\n", encoding="utf-8")
        written.append(target)
    return written


def load_grade_records(grades_dir: Path) -> dict[str, GradeRecord]:
    """Load records newest-first per route (later dates win)."""
    if not grades_dir.is_dir():
        return {}
    best: dict[str, GradeRecord] = {}
    for path in sorted(grades_dir.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid grade record: {path}")
        record = GradeRecord(
            route_id=str(raw["route_id"]),
            checked_utc=str(raw["checked_utc"]),
            capabilities={
                str(name): bool(value) for name, value in dict(raw["capabilities"]).items()
            },
            evidence=str(raw["evidence"]),
        )
        for name in record.capabilities:
            if name not in CAPABILITY_FLAGS:
                raise ValueError(f"Unknown capability in {path}: {name!r}")
        current = best.get(record.route_id)
        if current is None or record.checked_utc > current.checked_utc:
            best[record.route_id] = record
    return best
