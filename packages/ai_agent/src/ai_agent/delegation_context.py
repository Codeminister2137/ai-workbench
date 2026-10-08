"""Bounded source rendering and reference checks for local context delegation."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from ai_provider.repo_context import RepoContextFile


@dataclass(frozen=True, slots=True)
class DelegationContext:
    """Rendered context and the contiguous source lines actually supplied."""

    text: str
    source_line_counts: tuple[tuple[str, int], ...]

    @property
    def sources(self) -> tuple[str, ...]:
        return tuple(source for source, _ in self.source_line_counts)


def assemble_delegation_context(
    context_files: Sequence[RepoContextFile], *, max_chars: int
) -> DelegationContext:
    """Count headers, separators and truncation notices within the same budget."""
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero.")
    sections: list[str] = []
    source_line_counts: list[tuple[str, int]] = []
    used = 0
    for context_file in context_files:
        separator = "\n\n" if sections else ""
        remaining = max_chars - used - len(separator)
        if remaining <= 0:
            break
        header = f"=== SOURCE: {context_file.display_path} ===\n"
        if len(header) >= remaining:
            sections.append(separator + header[:remaining])
            break
        rendered = header
        lines = context_file.content.splitlines()
        visible_lines = 0
        complete = (
            header + "".join(f"{number}: {line}\n" for number, line in enumerate(lines, start=1))
        ).rstrip()
        if len(complete) <= remaining:
            sections.append(separator + complete)
            used += len(separator) + len(complete)
            if lines:
                source_line_counts.append((context_file.display_path, len(lines)))
            continue
        for line_number, line in enumerate(lines, start=1):
            line_text = f"{line_number}: {line}\n"
            marker = f"[source truncated after line {line_number}]"
            reserve = len(marker) if line_number < len(lines) else 0
            if len(rendered) + len(line_text) + reserve > remaining:
                marker = f"[source truncated after line {visible_lines}]"
                rendered += marker[: remaining - len(rendered)]
                break
            rendered += line_text
            visible_lines = line_number
        rendered = rendered.rstrip()
        sections.append(separator + rendered)
        used += len(separator) + len(rendered)
        if visible_lines:
            source_line_counts.append((context_file.display_path, visible_lines))
    return DelegationContext("".join(sections), tuple(source_line_counts))


def has_source_citation(summary: str, context: DelegationContext) -> bool:
    """Require at least one complete reference to a line actually supplied.

    This checks reference existence, not whether the cited line supports a claim.
    """
    counts: dict[str, int] = {}
    for source, count in context.source_line_counts:
        normalized = source.replace("\\", "/").casefold()
        counts[normalized] = max(counts.get(normalized, 0), count)
    for match in re.finditer(r"\[source:([^\]\r\n]+):([1-9][0-9]*)\]", summary, re.IGNORECASE):
        source, line = match.groups()
        count = counts.get(source.replace("\\", "/").casefold(), 0)
        # Compare digit strings before int conversion to bound malformed model output.
        if len(line) <= len(str(count)) and int(line) <= count:
            return True
    return False
