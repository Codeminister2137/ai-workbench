"""Agent-check HTTP probe: GET one dashboard path, expect a status code.

Usage: e2e-http-get.py <path> <expect-status> [--base URL]

Hits the served dashboard (default 127.0.0.1:8766) and exits 0 only when
the status matches AND the body parses as JSON with ok=true (for 200).
Asserts transport + shape, never body content (serve state varies).
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve()

DEFAULT_BASE = "http://127.0.0.1:8766"


def check(base: str, path: str, expect: int, timeout: float = 20.0) -> tuple[bool, str]:
    """GET path; True when status matches (+ok-shape on 200)."""
    if not path.startswith("/"):
        return False, "path must start with /"
    url = base.rstrip("/") + path
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            body = response.read().decode("utf-8", "replace")[:4000]
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            body = exc.read().decode("utf-8", "replace")[:4000]
        except Exception:  # noqa: BLE001 - error bodies are best-effort
            body = ""
    except Exception as exc:  # noqa: BLE001 - probe reports, never raises
        return False, f"request failed: {type(exc).__name__}: {exc}"
    if status != expect:
        return False, f"status {status}, expected {expect}"
    if expect == 200:
        try:
            payload = json.loads(body)
        except ValueError:
            return False, "200 body is not JSON"
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            return False, "200 body lacks ok:true"
    return True, f"status {status}, shape ok ({len(body)} bytes)"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    base = DEFAULT_BASE
    if args[:1] == ["--base"]:
        base = args[1]
        args = args[2:]
    if len(args) != 2:
        print("usage: e2e-http-get.py [--base URL] <path> <expect-status>")
        return 2
    path, expect_raw = args
    try:
        expect = int(expect_raw)
    except ValueError:
        print(f"bad status: {expect_raw!r}")
        return 2
    ok, detail = check(base, path, expect)
    print(detail)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
