"""Offline scoring for council synthesis verdicts (no model calls)."""

from __future__ import annotations


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def score_question(
    verdict: dict,
    member_names: list[str],
    reference_phrases: list[str],
) -> dict[str, float]:
    """Score one synthesis verdict: contract, attribution, calibration, recall.

    - ``parse_ok``: chair prose followed the verdict contract.
    - ``holders_valid``: every disagreement holder is a council member.
    - ``calibrated``: ``full`` has no disagreements, ``none`` has no agreed
      points (``partial`` is always consistent).
    - ``recall``: fraction of reference phrases found in agreed + next.
    """
    parse_ok = bool(verdict.get("parse_ok"))
    holders = [
        holder
        for item in verdict.get("disagreements", [])
        if isinstance(item, dict)
        for holder in (item.get("holders") or [])
    ]
    known = {name.lower() for name in member_names}
    holders_valid = all(str(holder).lower() in known for holder in holders)
    consensus = verdict.get("consensus")
    agreed = [a for a in verdict.get("agreed", []) if isinstance(a, str)]
    if consensus == "full":
        calibrated = not verdict.get("disagreements")
    elif consensus == "none":
        calibrated = not agreed
    else:
        calibrated = consensus == "partial"
    haystack = _normalize(
        " ".join(agreed + [a for a in verdict.get("next_actions", []) if isinstance(a, str)])
    )
    refs = [_normalize(phrase) for phrase in reference_phrases if phrase.strip()]
    recall = sum(1 for phrase in refs if phrase and phrase in haystack) / len(refs) if refs else 1.0
    overall = (float(parse_ok) + float(holders_valid) + float(calibrated) + recall) / 4
    return {
        "parse_ok": float(parse_ok),
        "holders_valid": float(holders_valid),
        "calibrated": float(calibrated),
        "recall": recall,
        "overall": overall,
    }


def aggregate(per_question: dict[str, dict[str, float]]) -> dict[str, float]:
    """Mean each metric over questions; empty input scores zero."""
    if not per_question:
        return {
            "parse_ok": 0.0,
            "holders_valid": 0.0,
            "calibrated": 0.0,
            "recall": 0.0,
            "overall": 0.0,
        }
    keys = ("parse_ok", "holders_valid", "calibrated", "recall", "overall")
    return {
        key: sum(scores[key] for scores in per_question.values()) / len(per_question)
        for key in keys
    }
