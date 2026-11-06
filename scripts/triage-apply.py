"""Apply audit-triage verdicts to a markdown ledger, failing loud on misses.

Verdicts file (JSON): {"<title substring>": "<VERDICT text>", ...}.
Each title must match exactly one ledger line still carrying the
marker (default **UNREVIEWED**); zero or multiple matches abort with
no write. Replaces 12+ one-off apply scripts from the 2026-11-03 audit.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_MARKER = "**UNREVIEWED**"


def load_verdicts(path: Path) -> dict[str, str]:
    """Read and validate the verdict map (non-empty titles and texts)."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f"Verdicts file is not valid JSON: {path}") from exc
    if not isinstance(payload, dict) or not payload:
        raise ValueError("Verdicts file must hold a non-empty JSON object")
    verdicts: dict[str, str] = {}
    for title, verdict in payload.items():
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Verdict titles must be non-empty strings")
        if not isinstance(verdict, str) or not verdict.strip():
            raise ValueError(f"Verdict for {title!r} must be a non-empty string")
        verdicts[title] = verdict
    return verdicts


def apply_verdicts(
    lines: list[str], verdicts: dict[str, str], *, marker: str = DEFAULT_MARKER
) -> list[str]:
    """Return ledger lines with verdicts applied; raise on any miss/ambiguity."""
    if not marker:
        raise ValueError("Marker must be a non-empty string")
    updated = list(lines)
    errors: list[str] = []
    for title, verdict in verdicts.items():
        hits = [index for index, line in enumerate(updated) if marker in line and title in line]
        if len(hits) != 1:
            errors.append(f"{title!r}: {len(hits)} matching lines (need exactly 1)")
            continue
        updated[hits[0]] = updated[hits[0]].replace(marker, f"**{verdict}**", 1)
    if errors:
        raise ValueError("; ".join(errors))
    return updated


def main(argv: list[str] | None = None) -> int:
    """Apply a verdicts file to a ledger; --dry-run checks without writing."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--verdicts", type=Path, required=True)
    parser.add_argument("--marker", default=DEFAULT_MARKER)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        verdicts = load_verdicts(args.verdicts)
        lines = args.ledger.read_text(encoding="utf-8").split("\n")
        updated = apply_verdicts(lines, verdicts, marker=args.marker)
    except (OSError, ValueError) as exc:
        print(f"triage-apply: {exc}", file=sys.stderr)
        return 1
    if args.dry_run:
        print(f"would apply {len(verdicts)} verdicts to {args.ledger}")
        return 0
    args.ledger.write_text("\n".join(updated), encoding="utf-8")
    print(f"applied {len(verdicts)} verdicts to {args.ledger}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
