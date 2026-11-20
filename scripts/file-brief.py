#!/usr/bin/env python3
"""File a structured inbox brief (options up front, no prose parsing).

Decision briefs filed with free-text "Options: A) ... B) ..." force the
owner (or AI) to reconstruct the choices. This helper requires explicit
--option values for decision items so the dashboard renders multi-choice
directly from the record. Decisions additionally require one --tradeoff
per option plus --recommend/--recommendation, so briefs always carry
the pros/cons and recommendation the writing rules demand.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

DEFAULT_URL = "http://127.0.0.1:8766"


MERGE_TIERS = ("tier1", "tier2", "tier3")
ASSIGNEES = ("owner", "agent")


def _match_option(label: str, options: list[str]) -> str:
    """Match a trade-off/recommendation label to exactly one option.

    Case-insensitive prefix match: "R" matches "R: relay ..." but an
    empty or ambiguous label fails loudly instead of misfiling.
    """
    key = label.strip().casefold()
    if not key:
        raise ValueError("trade-off and recommendation labels must not be empty")
    hits = [option for option in options if option.casefold().startswith(key)]
    if len(hits) != 1:
        raise ValueError(f"label {label!r} must match exactly one option")
    return hits[0]


def _parse_tradeoffs(raw: list[str], options: list[str]) -> list[dict[str, str]]:
    """Parse "LABEL | PRO | CON" entries; one per option, structural only.

    No prose judgment: presence and option coverage are enforced, quality
    of the reasoning is still the filer's responsibility.
    """
    parsed = []
    for entry in raw:
        parts = [part.strip() for part in entry.split("|")]
        if len(parts) != 3 or not all(parts):
            raise ValueError(f"trade-off needs 'LABEL | PRO | CON': {entry!r}")
        label, pro, con = parts
        parsed.append({"option": _match_option(label, options), "pro": pro, "con": con})
    covered = sorted(item["option"] for item in parsed)
    if covered != sorted(options):
        raise ValueError("trade-offs must cover every option exactly once")
    return parsed


def build_payload(
    *,
    title: str,
    body: str,
    options: list[str],
    item_type: str = "decision",
    created_by: str = "supervisor",
    assignee: str = "owner",
    tier: str | None = None,
    metadata: dict | None = None,
    needs_owner: str | None = None,
    needs_ai: str | None = None,
    tradeoffs: list[str] | None = None,
    recommend: str | None = None,
    recommendation: str | None = None,
) -> dict:
    """Assemble the /api/inbox payload; decisions need >= 2 options.

    Follow-ups (who + what) go both into ``metadata["followup"]`` for
    structured consumers and on top of the body so every surface (UI,
    mail, API) shows them without extra rendering. Trade-offs and the
    recommendation render the same way when provided; the CLI requires
    them for decisions while programmatic callers (sweep re-filings)
    may carry prose in the body instead.
    """
    if not title.strip():
        raise ValueError("title is required")
    if item_type == "decision" and len(options) < 2:
        raise ValueError("decision briefs need at least two --option values")
    if assignee not in ASSIGNEES:
        raise ValueError(f"assignee must be one of {ASSIGNEES}")
    tradeoff_rows = _parse_tradeoffs(tradeoffs or [], options or []) if tradeoffs else []
    recommended_option: str | None = None
    if recommend is not None or recommendation is not None:
        if recommend is None or not (recommendation or "").strip():
            raise ValueError("recommendation needs both --recommend and --recommendation")
        recommended_option = _match_option(recommend, options or [])
    followup: dict[str, str] = {}
    if needs_owner and needs_owner.strip():
        followup["owner"] = needs_owner.strip()
    if needs_ai and needs_ai.strip():
        followup["ai"] = needs_ai.strip()
    lead = []
    if "owner" in followup:
        lead.append(f"Needs from you (owner): {followup['owner']}")
    if "ai" in followup:
        lead.append(f"Needs from AI: {followup['ai']}")
    if tradeoff_rows:
        lead.append("Trade-offs:")
        lead.extend(
            f"- {row['option']}: Pro: {row['pro']} | Con: {row['con']}" for row in tradeoff_rows
        )
    if recommended_option is not None:
        lead.append(f"Recommendation: {recommended_option} — {(recommendation or '').strip()}")
    if lead:
        body = "\n".join(lead) + "\n\n" + body
    payload = {
        "title": title,
        "body": body,
        "type": item_type,
        "created_by": created_by,
        "assignee": assignee,
        "options": options,
    }
    merged = dict(metadata or {})
    if tier is not None:
        if tier not in MERGE_TIERS:
            raise ValueError(f"tier must be one of {MERGE_TIERS}")
        merged["tier"] = tier
    if followup:
        merged["followup"] = followup
    if tradeoff_rows:
        merged["tradeoffs"] = tradeoff_rows
    if recommended_option is not None:
        merged["recommendation"] = {
            "option": recommended_option,
            "why": (recommendation or "").strip(),
        }
    if merged:
        payload["metadata"] = merged
    return payload


def send(url: str, payload: dict, token: str | None = None) -> dict:
    """POST the payload; returns the decoded response record."""
    request = urllib.request.Request(
        f"{url.rstrip('/')}/api/inbox",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if token:
        request.add_header("X-Supervisor-Token", token)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="File a structured inbox brief.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--body", default="")
    parser.add_argument("--body-file", type=Path, default=None)
    parser.add_argument("--option", action="append", default=[], dest="options")
    parser.add_argument(
        "--tradeoff",
        action="append",
        default=[],
        dest="tradeoffs",
        help="Per-option trade-off 'LABEL | PRO | CON' (decisions: one per option).",
    )
    parser.add_argument(
        "--recommend",
        default=None,
        help="Recommended option label (decisions: required, must match one option).",
    )
    parser.add_argument(
        "--recommendation",
        default=None,
        help="Why the recommended option fits (decisions: required).",
    )
    parser.add_argument(
        "--metadata",
        action="append",
        default=[],
        dest="metadata_items",
        help="Extra metadata 'KEY=VALUE' (repeatable; e.g. owner_gate=<id>).",
    )
    parser.add_argument("--type", default="decision", dest="item_type")
    parser.add_argument("--tier", default=None, help="Merge tier (tier1/2/3, ADR-087).")
    parser.add_argument(
        "--needs-owner", default=None, help="Follow-up action needed from the owner."
    )
    parser.add_argument("--needs-ai", default=None, help="Follow-up action needed from AI.")
    parser.add_argument(
        "--assignee",
        default="owner",
        help="Who must act: owner (decisions, approvals) or agent (AI work).",
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--token", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    body = args.body
    if args.body_file is not None:
        body = args.body_file.read_text(encoding="utf-8")
    metadata: dict[str, str] = {}
    for item in args.metadata_items:
        key, sep, value = item.partition("=")
        if not sep or not key.strip():
            print(f"error: --metadata needs 'KEY=VALUE': {item!r}", file=sys.stderr)
            return 2
        metadata[key.strip()] = value.strip()
    if args.item_type == "decision" and (
        not args.tradeoffs or args.recommend is None or not (args.recommendation or "").strip()
    ):
        print(
            "error: decision briefs need --tradeoff per option plus --recommend and --recommendation",
            file=sys.stderr,
        )
        return 2
    try:
        payload = build_payload(
            title=args.title,
            body=body,
            options=args.options,
            item_type=args.item_type,
            tier=args.tier,
            assignee=args.assignee,
            needs_owner=args.needs_owner,
            needs_ai=args.needs_ai,
            tradeoffs=args.tradeoffs or None,
            recommend=args.recommend,
            recommendation=args.recommendation,
            metadata=metadata or None,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if (
        args.assignee == "owner"
        and args.needs_ai
        and args.needs_ai.strip()
        and not (args.needs_owner and args.needs_owner.strip())
    ):
        print(
            "warning: AI-only follow-up filed to the owner; pass --assignee agent for AI work",
            file=sys.stderr,
        )
    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return 0
    try:
        result = send(args.url, payload, args.token)
    except OSError as exc:
        print(f"error: dashboard unreachable: {exc}", file=sys.stderr)
        return 1
    if not result.get("ok"):
        print(f"error: {result.get('error', 'unknown')}", file=sys.stderr)
        return 1
    print(result["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
