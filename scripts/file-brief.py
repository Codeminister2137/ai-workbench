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


def build_payload(
    *,
    title: str,
    body: str,
    options: list[str],
    item_type: str = "decision",
    created_by: str = "supervisor",
    assignee: str = "owner",
) -> dict:
    """Assemble the /api/inbox payload; decisions need >= 2 options."""
    if not title.strip():
        raise ValueError("title is required")
    if item_type == "decision" and len(options) < 2:
        raise ValueError("decision briefs need at least two --option values")
    return {
        "title": title,
        "body": body,
        "type": item_type,
        "created_by": created_by,
        "assignee": assignee,
        "options": options,
    }


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
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--token", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    body = args.body
    if args.body_file is not None:
        body = args.body_file.read_text(encoding="utf-8")
    try:
        payload = build_payload(
            title=args.title, body=body, options=args.options, item_type=args.item_type
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
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
