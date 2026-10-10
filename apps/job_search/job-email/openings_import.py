"""Read Openings JSON export rows without a server, account or delivery side effect.

The source's canonical job ID is retained so similarly named requisitions remain
distinct. Full source rows remain available for review, including metadata this
prototype does not yet represent. No skills or recipient addresses are inferred.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from models import JobVacancy, WorkMode


def _text(row: Mapping[str, object], key: str, *, required: bool = False) -> str:
    value = row.get(key)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f"Openings {key} must be {'nonempty ' if required else ''}text")
    return value.strip()


def import_openings_export(rows: Sequence[Mapping[str, object]]) -> tuple[JobVacancy, ...]:
    """Normalize already-loaded JSON export rows, rejecting conflicting repeats.

    Repeated identical rows are collapsed by canonical ID. Different IDs remain
    separate even with identical company/title/location. Conflicting records for
    one ID require the caller to choose a snapshot instead of silently taking one.
    This does not read files, retrieve full posting details, filter by suitability,
    or interpret a tracker status as permission to apply.
    """
    result: list[JobVacancy] = []
    seen: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("Each Openings export row must be an object")
        identifier = _text(row, "job_id", required=True)
        company = _text(row, "company", required=True)
        title = _text(row, "title", required=True)
        remote = row.get("is_remote")
        if remote is not None and type(remote) is not bool:
            raise ValueError("Openings is_remote must be a boolean or null")
        raw = json.dumps(dict(row), ensure_ascii=False, sort_keys=True, allow_nan=False)
        if identifier in seen:
            if seen[identifier] != raw:
                raise ValueError(f"Conflicting Openings export rows for job {identifier!r}")
            continue
        seen[identifier] = raw
        result.append(
            JobVacancy(
                id=f"openings:{identifier}",
                company=company,
                title=title,
                location=_text(row, "location"),
                work_mode=WorkMode.REMOTE if remote is True else WorkMode.UNSPECIFIED,
                description=_text(row, "description"),
                experience_requirement=_text(row, "job_level") or None,
                source=_text(row, "source") or "openings",
                source_url=_text(row, "job_url") or None,
                raw_content=raw,
                duplicate_key=f"openings:{identifier}",
            )
        )
    return tuple(result)
