"""Wire constants and endpoint validation shared by MCP transports."""

from urllib.parse import urlsplit

PROTOCOL_VERSION = "2025-06-18"


def validate_loopback_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.port
    ):
        raise ValueError("MCP endpoint must be an explicit credential-free loopback HTTP URL")
