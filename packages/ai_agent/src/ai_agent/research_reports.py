"""Validate local research-report structure without fetching sources or using AI."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlsplit

REQUIRED_SECTIONS = (
    "Executive summary",
    "Source map",
    "Candidate models, practices, or facts to add/revisit",
    "Recommended fields, metrics, or decision criteria",
    "Provider/source-specific notes",
    "Risks, stale-data warnings, and unknowns",
    "Suggested next implementation slice",
    "Repair checks performed",
)
_URL = re.compile(r"https?://[^\s<>|)\]]*", re.IGNORECASE)
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_STATUS = re.compile(r"\b(verified|inferred|unknown|stale[- ]risk)\b", re.IGNORECASE)
_SOURCE_ID = re.compile(r"\bS[1-9]\d*\b")
_CITATION = re.compile(r"\[(S[1-9]\d*)\]")
_DASHES = str.maketrans({char: "-" for char in "\u2010\u2011\u2012\u2013\u2014\u2212"})


@dataclass(frozen=True)
class Source:
    """Declared source provenance; a report declaration is not fetch evidence."""

    urls: tuple[str, ...]
    ids: tuple[str, ...]
    fetched: bool
    access_dates: tuple[str, ...]


def _urls(text: str) -> tuple[str, ...]:
    return tuple(match.group().rstrip(".,;:") for match in _URL.finditer(text))


def _content(text: str) -> str:
    """Ignore examples and comments when locating report evidence."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"(?ms)^\s*(`{3,}|~{3,})[^\n]*\n.*?^\s*\1\s*$", "", text)
    return re.sub(r"(?m)^[ \t]*(?:(?:-[ \t]*){3,}|(?:\*[ \t]*){3,}|(?:_[ \t]*){3,})$", "", text)


def _sections(text: str) -> tuple[dict[str, str], list[str]]:
    sections: dict[str, str] = {}
    errors: list[str] = []
    positions: list[tuple[str, int, int]] = []
    for match in re.finditer(r"(?m)^\s*(?:#{1,6}\s+|\d+[.)]\s+)([^\n]+)$", text):
        title = re.sub(r"^\d+[.)]\s*", "", match.group(1).strip()).strip(" *:#")
        canonical = next(
            (
                name
                for name in REQUIRED_SECTIONS
                if name.casefold() == title.translate(_DASHES).casefold()
            ),
            None,
        )
        if canonical:
            positions.append((canonical, match.start(), match.end()))
    for index, (name, _, start) in enumerate(positions):
        end = positions[index + 1][1] if index + 1 < len(positions) else len(text)
        if name in sections:
            errors.append(f"duplicate section: {name}")
        sections[name] = text[start:end].strip()
    for name in REQUIRED_SECTIONS:
        if name not in sections:
            errors.append(f"missing required section: {name}")
        elif not re.sub(r"(?m)^\s*#{1,6}[^\n]*$", "", sections[name]).strip():
            errors.append(f"empty required section: {name}")
    return sections, errors


def _table_rows(text: str) -> list[str]:
    """Read data rows after a Markdown table separator, excluding headers."""
    rows: list[str] = []
    in_table = False
    for line in text.splitlines():
        if re.fullmatch(r"\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*", line):
            in_table = True
        elif in_table and "|" in line:
            rows.append(line)
        else:
            in_table = False
    return rows


def _entries(text: str) -> list[str]:
    """Accept tables, top-level lists, source subsections, or prose paragraphs."""
    rows = _table_rows(text)
    if rows:
        text = "\n".join(line for line in text.splitlines() if "|" not in line)
    list_marker = r"(?:[-*+]|\d+[.)])\s+"
    if re.search(r"(?m)^" + list_marker, text):
        # Do not let the presence of a table hide additional list entries.
        bullets = [
            part.strip()
            for part in re.split(r"(?m)^(?=" + list_marker + ")", text)
            if re.match(list_marker, part)
        ]
        return rows + bullets
    if re.search(r"(?m)^#{1,6}\s+", text):
        return rows + [
            part.strip()
            for part in re.split(r"(?m)^(?=#{1,6}\s+)", text)
            if re.match(r"#{1,6}\s+", part)
        ]
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if rows:
        # Plain introductions to a table are not separate candidate/source entries.
        paragraphs = [part for part in paragraphs if _URL.search(part) or _STATUS.search(part)]
    return rows + paragraphs


def _sources(text: str, today: date) -> tuple[list[Source], list[str]]:
    errors: list[str] = []
    sources: list[Source] = []
    for number, entry in enumerate(_entries(text), 1):
        urls = _urls(entry)
        if not urls:
            # A preamble is allowed; a declared source ID still needs an actual URL.
            if _SOURCE_ID.search(entry):
                errors.append(f"source map entry {number}: missing HTTP(S) URL")
            continue
        label = f"source map entry {number}"
        for url in urls:
            try:
                parsed = urlsplit(url)
                valid = bool(parsed.hostname) and not parsed.username and not parsed.password
                _ = parsed.port
            except ValueError:
                valid = False
            if not valid:
                errors.append(f"{label}: malformed URL")
        not_fetched = bool(re.search(r"\bnot[ _-]fetched\b", entry, re.IGNORECASE))
        fetched = bool(re.search(r"\bfetched\b", entry, re.IGNORECASE)) and not not_fetched
        if not (fetched or not_fetched):
            errors.append(f"{label}: declare retrieval as fetched or not fetched")
        dates = _DATE.findall(entry)
        if fetched and not dates:
            errors.append(f"{label}: missing access date (YYYY-MM-DD)")
        for value in dates:
            try:
                accessed = date.fromisoformat(value)
            except ValueError:
                errors.append(f"{label}: invalid date {value}")
            else:
                if accessed > today:
                    errors.append(f"{label}: access date is in the future ({value})")
        sources.append(Source(urls, tuple(_SOURCE_ID.findall(entry)), fetched, tuple(dates)))
    if not sources:
        errors.append("source map: declare at least one HTTP(S) source with retrieval status")
    ids = [source_id for source in sources for source_id in source.ids]
    if len(ids) != len(set(ids)):
        errors.append("source map: source IDs must be unique")
    return sources, errors


def validate_report(
    text: str,
    *,
    min_chars: int = 7000,
    today: date | None = None,
    fetch_receipts: Sequence[Mapping[str, object]] | None = None,
    advisories: list[str] | None = None,
) -> list[str]:
    """Return mandatory errors; optionally collect nonblocking length advice."""
    errors = []
    visible = _content(text)
    if advisories is not None:
        advisories.extend(report_advisories(text, min_chars=min_chars))
    sections, section_errors = _sections(visible)
    errors.extend(section_errors)
    sources, source_errors = _sources(sections.get("Source map", ""), today or date.today())
    errors.extend(source_errors)
    if fetch_receipts is not None:
        for source in sources:
            if not source.fetched:
                continue
            for url in source.urls:
                matching = [
                    receipt
                    for receipt in fetch_receipts
                    if url in (receipt.get("requested_url"), receipt.get("final_url"))
                    and isinstance(receipt.get("http_status"), int)
                    and 200 <= int(str(receipt["http_status"])) < 300
                    and re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("sha256", "")))
                ]
                if not matching:
                    errors.append(
                        f"claimed fetched source has no successful current-run receipt: {url}"
                    )
                elif not any(
                    str(receipt.get("fetched_at_utc", ""))[:10] in source.access_dates
                    for receipt in matching
                ):
                    errors.append(f"source access date disagrees with current-run receipt: {url}")
    url_sources = {url: source for source in sources for url in source.urls}
    id_sources = {source_id: source for source in sources for source_id in source.ids}
    body = "\n".join(value for name, value in sections.items() if name != "Source map")
    for source_id in sorted(set(_CITATION.findall(body)) - id_sources.keys()):
        errors.append(f"citation [{source_id}]: not declared in Source map")
    for url in sorted(set(_urls(body)) - url_sources.keys()):
        errors.append(f"citation URL not declared in Source map: {url}")
    candidates = sections.get(REQUIRED_SECTIONS[2], "")
    claims = _entries(candidates)
    for number, claim in enumerate(claims, 1):
        statuses = {match.casefold().replace(" ", "-") for match in _STATUS.findall(claim)}
        label = f"candidate entry {number}"
        if not statuses:
            errors.append(
                f"{label}: label confidence as verified, inferred, unknown, or stale-risk"
            )
        cited = [id_sources[key] for key in _CITATION.findall(claim) if key in id_sources]
        cited += [url_sources[url] for url in _urls(claim) if url in url_sources]
        if not cited and "unknown" not in statuses:
            errors.append(f"{label}: cite a declared URL or [S1] source ID, or label as unknown")
        if "verified" in statuses and not any(source.fetched for source in cited):
            errors.append(
                f"{label}: verified claims need a source declared fetched with an access date"
            )
    risks = sections.get(REQUIRED_SECTIONS[5], "")
    if not re.search(
        r"\b(unknowns?|uncertain(?:ty|ties)?|unverified|not verified)\b", risks, re.IGNORECASE
    ):
        errors.append(
            "risks section: explicitly state unknowns or uncertainties, including when none remain"
        )
    return errors


def report_advisories(text: str, *, min_chars: int = 7000) -> list[str]:
    """Suggest coverage review without treating length as a completion requirement."""
    visible_chars = len(_content(text).strip())
    if visible_chars >= min_chars:
        return []
    return [
        f"research report length advisory: {visible_chars} visible chars, "
        f"below the {min_chars}-character guideline; review substantive coverage if useful. "
        "Length alone does not fail completion or require repair; do not add filler."
    ]


def has_report_write_receipt(
    path: str,
    sha256: str,
    receipts: Sequence[Mapping[str, object]],
    relocations: Sequence[Mapping[str, object]] = (),
) -> bool:
    """Match original write evidence, allowing explicitly recorded artifact moves.

    Relocations preserve the original receipt instead of inventing a new write.
    Both the relocation and the original receipt must match the surviving bytes.
    """
    original_paths = {path}
    original_paths.update(
        str(move["original_path"])
        for move in relocations
        if move.get("path") == path and move.get("sha256") == sha256 and move.get("original_path")
    )
    return any(
        receipt.get("path") in original_paths and receipt.get("sha256") == sha256
        for receipt in receipts
    )
