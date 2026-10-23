"""Propose offline route-to-row mappings for human review, never acceptance.

First compare conservatively normalized identities (case and punctuation, with
known gateway/vendor prefixes removed). Then use explicit, bounded family
grammars: GPT major generations stay separate; Qwen coder, Gemini pro/flash,
and DeepSeek product lines stay separate. Unknown families receive no heuristic
match. Version, parameter count, tier and effort differences are reported.
Free/quantized variants are left unmatched unless their full identity matches.

Candidates rank by identity, version distance, size distance, then diff format,
reasoning high/medium/low, newest measurement and lexical provenance. Scores
never determine rank and scales are never compared. Configuration selection is
an explicit proposal policy, not evidence that this route used that configuration.
Known rolling DeepSeek aliases always retain alias confidence and a warning.
Callers supply the checked date; no clock, filesystem, network or inference runs.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Literal

from ai_provider.source_info import CapabilityScore

Confidence = Literal["exact", "family", "alias", "unmatched"]
_PREFIXES = {"openrouter", "openai", "google", "qwen", "moonshotai", "deepseek"}
_ALIASES = {"deepseek|chat", "deepseek|reasoner"}


def _identity(model: str) -> str:
    parts = model.casefold().split("/")
    while len(parts) > 1 and parts[0] in _PREFIXES:
        parts.pop(0)
    return "|".join(re.findall(r"[a-z]+|\d+(?:\.\d+)?", "/".join(parts)))


@dataclass(frozen=True, slots=True)
class RouteFamilyMatch:
    """One dated proposal, including the complete measured run's provenance."""

    route_id: str
    model: str
    matched_row: CapabilityScore | None
    confidence: Confidence
    reason: str
    gap: str | None
    checked: date

    @property
    def configuration(self) -> str | None:
        """Return the selected run configuration without discarding its identity."""

        return self.matched_row.configuration if self.matched_row else None


@dataclass(frozen=True)
class _Family:
    key: str
    version: tuple[int, int]
    size: int | None
    modifiers: tuple[str, ...]


def _family(model: str) -> _Family | None:
    parts = model.casefold().split("/")
    if any(part not in _PREFIXES for part in parts[:-1]):
        return None
    value = parts[-1]
    value = re.sub(r"[\s_:]+", "-", value)
    patterns = (
        (r"gpt-(?P<v>\d+(?:\.\d+)?)(?P<tail>.*)", "gpt"),
        (r"gpt-oss(?P<tail>.*)", "gpt-oss"),
        (r"qwen(?P<v>\d+(?:\.\d+)?)(?P<tail>.*)", "qwen"),
        (r"gemini-?(?P<v>\d+(?:\.\d+)?)(?P<tail>.*)", "gemini"),
        (r"gemma-?(?P<v>\d+(?:\.\d+)?)(?P<tail>.*)", "gemma"),
        (r"kimi-k(?P<v>\d+(?:\.\d+)?)(?P<tail>.*)", "kimi"),
        (r"glm-?(?P<v>\d+(?:\.\d+)?)(?P<tail>.*)", "glm"),
    )
    for pattern, key in patterns:
        match = re.fullmatch(pattern, value)
        if match is None:
            continue
        version = (match.groupdict().get("v") or "0").split(".")
        major, minor = int(version[0]), int(version[1]) if len(version) > 1 else 0
        tail = match["tail"].strip("-")
        tokens = tail.split("-") if tail else []
        size = None
        modifiers = []
        for token in tokens:
            if re.fullmatch(r"\d+b", token):
                size = int(token[:-1])
            elif token in {"pro", "flash", "coder"}:
                key += "-" + token
            elif token in {"mini", "high", "medium", "low", "code", "preview"}:
                modifiers.append(token)
            elif token not in {"it", "instruct"}:
                return None
        if key == "gemini" or (key == "gpt" and major == 0):
            return None
        # A GPT-6 row cannot be inferred from a GPT-5 result.
        if key == "gpt":
            key += f"-{major}"
        return _Family(key, (major, minor), size, tuple(modifiers))
    return None


def propose_route_family(
    route_id: str,
    model: str,
    candidates: Iterable[CapabilityScore],
    *,
    checked: date,
) -> RouteFamilyMatch:
    """Return a conservative proposal using only supplied rows and checked date.

    An unmatched result has no row and therefore no score or implicit band.
    Reviewers must accept a proposal before treating it as a route mapping.
    """

    def unmatched(reason: str) -> RouteFamilyMatch:
        return RouteFamilyMatch(route_id, model, None, "unmatched", reason, None, checked)

    if model.strip().casefold() == "auto":
        return unmatched("Provider-selected auto has no fixed model identity.")
    identity = _identity(model)
    family = _family(model)
    restricted = bool(re.search(r":free\b|(?:[:_-])q\d|quant", model, re.I))
    ranked = []
    for row in candidates:
        if row.score is None or not row.scale:
            continue
        other_id = _identity(row.model)
        other = _family(row.model)
        gaps = []
        same = identity == other_id
        effort_suffix = bool(family and set(family.modifiers) & {"high", "medium", "low"})
        if effort_suffix and family is not None:
            same = False
            gaps.append(f"unmeasured effort suffix: {family.modifiers}")
        if not same:
            if restricted or re.search(r":free\b|(?:[:_-])q\d|quant", row.model, re.I):
                continue
            if family is None or other is None or family.key != other.key:
                continue
            if family.version != other.version:
                gaps.append(f"version gap: {family.version} vs {other.version}")
            if family.size != other.size:
                gaps.append(
                    f"size gap: {family.size or 'unspecified'}b vs {other.size or 'unspecified'}b"
                )
            if family.modifiers != other.modifiers:
                gaps.append(f"unmeasured suffix/tier gap: {family.modifiers} vs {other.modifiers}")
            if not gaps:
                gaps.append("naming gap: published instruction/identity suffix differs")
        alias = other_id in _ALIASES
        confidence: Confidence = "alias" if alias else "exact" if same else "family"
        warning = (
            " Rolling/unpinned alias may resolve differently today; historical scores "
            "are not a current-quality claim."
            if alias
            else ""
        )
        config = row.configuration or "unreported"
        reason = (
            (
                "Normalized identity layer."
                if same
                else f"Recognized family layer ({family.key if family else ''})."
            )
            + f" Selected configuration: {config}; harness: {row.agent or 'unreported'}."
            + warning
        )
        if "edit=whole" in config:
            reason += " Whole-edit run is weak evidence compared with diff."
        if row.warning:
            reason += f" Source warning: {row.warning}"
        proposal = RouteFamilyMatch(
            route_id, model, row, confidence, reason, "; ".join(gaps) or None, checked
        )
        distance = (
            abs(family.version[0] - other.version[0]) * 100
            + abs(family.version[1] - other.version[1])
            if family and other
            else 0
        )
        size_distance = abs((family.size or 0) - (other.size or 0)) if family and other else 0
        effort = 0 if "reasoning=high" in config else 1 if "reasoning=medium" in config else 2
        rank = (not same, distance, size_distance, "edit=diff" not in config, effort)
        ranked.append((rank, row, proposal))
    if not ranked:
        return unmatched("No justified identity or recognized family row; no prior attached.")
    # Stable ties include every record field; input order never chooses a run.
    ranked.sort(key=lambda item: repr(item[1].to_dict()))
    ranked.sort(key=lambda item: item[1].measured_at or "", reverse=True)
    ranked.sort(key=lambda item: item[0])
    return ranked[0][2]
