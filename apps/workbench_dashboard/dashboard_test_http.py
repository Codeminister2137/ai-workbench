"""Shared HTTP test helpers for the dashboard suite (tests import these)."""

from __future__ import annotations

import json
from urllib.request import Request, urlopen


def post_json(base: str, path: str, payload: dict) -> dict:
    """POST a JSON payload to the dashboard test server."""
    request = Request(
        f"{base}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(base: str, path: str) -> dict:
    """GET a JSON payload from the dashboard test server."""
    with urlopen(f"{base}{path}", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))
