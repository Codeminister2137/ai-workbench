#!/usr/bin/env python3
"""File a structured inbox brief (options up front, no prose parsing).

Decision briefs filed with free-text "Options: A) ... B) ..." force the
owner (or AI) to reconstruct the choices. This helper requires explicit
--option values for decision items so the dashboard renders multi-choice
directly from the record.
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
) -> dict:
    """Assemble the /api/inbox payload; decisions need >= 2 options.

    Follow-ups (who + what) go both into ``metadata["followup"]`` for
    structured consumers and on top of the body so every surface (UI,
    mail, API) shows them without extra rendering.
    """
    if not title.strip():
        raise ValueError("title is required")
    if item_type == "decision" and len(options) < 2:
        raise ValueError("decision briefs need at least two --option values")
    if assignee not in ASSIGNEES:
        raise ValueError(f"assignee must be one of {ASSIGNEES}")
    followup: dict[str, str] = {}
    if needs_owner and needs_owner.strip():
        followup["owner"] = needs_owner.strip()
    if needs_ai and needs_ai.strip():
        followup["ai"] = needs_ai.strip()
    if followup:
        lead = []
        if "owner" in followup:
            lead.append(f"Needs from you (owner): {followup['owner']}")
        if "ai" in followup:
            lead.append(f"Needs from AI: {followup['ai']}")
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
