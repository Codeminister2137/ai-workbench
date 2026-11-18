"""L1 claim extractor: structure source-state prose into cited claims.

Reads provider finding docs (source-state.md) and emits machine-usable
claims with file+line provenance. Pure text structure: provider bullets,
dated findings, endpoint mentions. No inference, no network, no models.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_BULLET_RE = re.compile(r"^-\s+\*\*(?P<provider>[^*]+)\*\*\s*(?P<rest>.*)$")
_DATE_RE = re.compile(r"\b(?P<date>20\d\d-\d\d-\d\d)\b")
_OWNER_RE = re.compile(r"^Owner\s+(\d\d-\d\d|\d\d\d\d-\d\d-\d\d)\s*:")
_ENDPOINT_RE = re.compile(
    r"(?:GET|POST)\s+(?P<endpoint>[A-Za-z0-9._~:/?#@!$&'()*+,;=%-]*[A-Za-z0-9_/])"
)


@dataclass(frozen=True, slots=True)
class SourceClaim:
    """One extracted claim with provenance."""

    kind: str  # provider_finding | dated_finding | endpoint | owner_note
    provider: str
    text: str
    file: str
    line: int


def extract_claims(path: str | Path) -> tuple[SourceClaim, ...]:
    """Extract claims from one finding doc; unknown lines are skipped, never guessed."""
    file_path = Path(path)
    claims: list[SourceClaim] = []
    current_provider = ""
    for number, raw_line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.rstrip()
        if not line.strip():
            continue
        bullet = _BULLET_RE.match(line)
        if bullet is not None:
            current_provider = bullet.group("provider").strip()
            claims.append(
                SourceClaim(
                    kind="provider_finding",
                    provider=current_provider,
                    text=bullet.group("rest").strip()[:500],
                    file=str(file_path),
                    line=number,
                )
            )
        for date_match in _DATE_RE.finditer(line):
            claims.append(
                SourceClaim(
                    kind="dated_finding",
                    provider=current_provider,
                    text=f"{date_match.group('date')}: {line.strip()[:400]}",
                    file=str(file_path),
                    line=number,
                )
            )
        if _OWNER_RE.match(line.strip()):
            claims.append(
                SourceClaim(
                    kind="owner_note",
                    provider=current_provider,
                    text=line.strip()[:500],
                    file=str(file_path),
                    line=number,
                )
            )
        for endpoint_match in _ENDPOINT_RE.finditer(line):
            claims.append(
                SourceClaim(
                    kind="endpoint",
                    provider=current_provider,
                    text=endpoint_match.group("endpoint")[:300],
                    file=str(file_path),
                    line=number,
                )
            )
    return tuple(claims)
