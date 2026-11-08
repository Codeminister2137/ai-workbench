"""Offline vacancy shortlist: export file + profile + preferences report.

Reads an Openings export JSON array (no server needed), filters by owner
preferences, scores matches against the private profile, and prints a
ranked shortlist. Read-only: nothing is sent, stored, or modified.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from evidence import analyze_vacancy_fit
from openings_import import import_openings_export
from preferences import JobPreferences, check_preferences
from profiles import default_profile_path, load_profile


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for the vacancy shortlist."""
    parser = argparse.ArgumentParser(
        description="Rank exported vacancies by preferences and profile fit."
    )
    parser.add_argument("export", type=Path, help="Openings export JSON array file")
    parser.add_argument(
        "--profile",
        type=Path,
        default=default_profile_path(),
        help="Candidate profile TOML (default: private data path)",
    )
    parser.add_argument(
        "--location", action="append", default=[], help="Acceptable location (repeatable)"
    )
    parser.add_argument("--no-remote", action="store_true", help="Exclude remote vacancies")
    parser.add_argument(
        "--exclude-company",
        action="append",
        default=[],
        help="Excluded company (repeatable)",
    )
    parser.add_argument(
        "--title-contains",
        action="append",
        default=[],
        help="Required title word (repeatable, all must match)",
    )
    parser.add_argument(
        "--employment-type",
        action="append",
        default=[],
        help="Allowed employment type (repeatable)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the shortlist report; return the process exit code."""
    args = build_parser().parse_args(argv)
    try:
        rows = json.loads(args.export.read_text(encoding="utf-8"))
        vacancies = import_openings_export(rows)
        profile = load_profile(args.profile)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    preferences = JobPreferences(
        locations=tuple(args.location),
        remote_ok=not args.no_remote,
        excluded_companies=tuple(args.exclude_company),
        title_must_include=tuple(args.title_contains),
        employment_types=tuple(args.employment_type),
    )
    ranked: list[tuple[float, str]] = []
    excluded = 0
    for vacancy in vacancies:
        passes, reasons = check_preferences(preferences, vacancy)
        if not passes:
            excluded += 1
            continue
        analysis = analyze_vacancy_fit(vacancy, profile)
        summary = (
            f"{analysis.match_score:.2f} {vacancy.title} at {vacancy.company} "
            f"[{vacancy.location}] "
            f"+{len(analysis.matched_skills)}/~{len(analysis.adjacent_skills)}/"
            f"?{len(analysis.learning_skills)}/-{len(analysis.missing_requirements)}"
        )
        if analysis.uncertainty_flags:
            summary += f" flags:{','.join(analysis.uncertainty_flags)}"
        ranked.append((analysis.match_score, summary))
    ranked.sort(key=lambda item: item[0], reverse=True)
    for _, summary in ranked:
        print(summary)
    print(f"{len(ranked)} shown, {excluded} excluded by preferences")
    return 0


if __name__ == "__main__":
    sys.exit(main())
