"""Bounded public HTTP retrieval with pinned DNS and no ambient credentials."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import socket
import ssl
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

MAX_SOURCE_BYTES = 512_000


@dataclass(frozen=True)
class FetchedSource:
    """Bytes actually retrieved and compact provenance for this fetch."""

    body: bytes
    content_type: str
    charset: str
    receipt: dict[str, object]


def public_endpoint(url: str) -> tuple[str, str, int, str, str]:
    """Resolve a credential-free HTTP URL and reject non-public addresses."""
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or any(ord(char) < 33 for char in url)
        or "\\" in url
    ):
        raise ValueError("Use a public HTTP(S) URL without credentials or control characters")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in {80, 443}:
        raise ValueError("Research fetching supports public ports 80 and 443 only")
    addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    ips = [str(item[4][0]) for item in addresses]
    if not ips:
        raise ValueError("No source address resolved")
    for value in ips:
        address = ipaddress.ip_address(value)
        mapped = getattr(address, "ipv4_mapped", None)
        if (
            not address.is_global
            or address.is_multicast
            or (mapped is not None and not mapped.is_global)
        ):
            raise ValueError("Research fetching cannot access private or non-public networks")
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    return parsed.scheme, parsed.hostname, port, ips[0], target


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, ip: str, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout)
        self.ip = ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self.ip, self.port), self.timeout)


class _PinnedHTTPS(_PinnedHTTP):
    def connect(self) -> None:
        super().connect()
        assert self.sock is not None
        self.sock = ssl.create_default_context().wrap_socket(self.sock, server_hostname=self.host)


def fetch_public_url(
    url: str,
    *,
    timeout_seconds: float = 20.0,
    before_body: Callable[[str], None] | None = None,
) -> FetchedSource:
    """GET public text, validating and pinning every redirect destination.

    No environment proxy, cookie jar, authentication, or user headers are used.
    The body is bounded and its digest explicitly describes the retained bytes.
    """
    original = url
    deadline = time.monotonic() + timeout_seconds
    for _ in range(6):
        scheme, host, port, ip, target = public_endpoint(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Source-fetch budget exhausted")
        connection = (_PinnedHTTPS if scheme == "https" else _PinnedHTTP)(host, port, ip, remaining)
        response = None
        watchdog = None
        expired = threading.Event()
        try:
            connection.request(
                "GET",
                target,
                headers={
                    "User-Agent": "AI-projects-research/1.0",
                    "Accept": "text/*, application/json, application/xhtml+xml",
                    "Accept-Encoding": "identity",
                },
            )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Source-fetch budget exhausted")
            deadline_socket = connection.sock
            if deadline_socket is not None:
                deadline_socket.settimeout(remaining)

                def abort_read(sock=deadline_socket, event=expired):
                    event.set()
                    try:
                        # HTTPResponse may retain the socket after connection.sock
                        # becomes None for a Connection: close response.
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

                watchdog = threading.Timer(remaining, abort_read)
                watchdog.daemon = True
                watchdog.start()
            response = connection.getresponse()
            if expired.is_set() or time.monotonic() >= deadline:
                raise TimeoutError("Source-fetch budget exhausted")
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise ValueError("Redirect has no destination")
                url = urljoin(url, location)
                continue
            if not 200 <= response.status < 300:
                raise ValueError(f"Source returned HTTP {response.status}")
            content_type = response.headers.get_content_type()
            if not (
                content_type.startswith("text/")
                or content_type in {"application/json", "application/xhtml+xml"}
            ):
                raise ValueError(
                    f"Unsupported source format: {content_type}; use a public text page"
                )
            if response.getheader("Content-Encoding", "identity") != "identity":
                raise ValueError(
                    "Compressed sources are not supported by this bounded text fetcher"
                )
            if before_body is not None:
                before_body(url)
            body = bytearray()
            while len(body) <= MAX_SOURCE_BYTES:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Source-fetch budget exhausted")
                if deadline_socket is not None:
                    deadline_socket.settimeout(remaining)
                chunk = response.read1(min(64_000, MAX_SOURCE_BYTES + 1 - len(body)))
                if not chunk:
                    break
                body.extend(chunk)
            if expired.is_set() or time.monotonic() >= deadline:
                raise TimeoutError("Source-fetch budget exhausted")
            truncated = len(body) > MAX_SOURCE_BYTES
            retained = bytes(body[:MAX_SOURCE_BYTES])
            return FetchedSource(
                retained,
                content_type,
                response.headers.get_content_charset() or "utf-8",
                {
                    "requested_url": original,
                    "final_url": url,
                    "http_status": response.status,
                    "fetched_at_utc": datetime.now(UTC).isoformat(),
                    "sha256": hashlib.sha256(retained).hexdigest(),
                    "bytes_retained": len(retained),
                    "truncated": truncated,
                },
            )
        except (OSError, http.client.HTTPException) as error:
            if expired.is_set():
                raise TimeoutError("Source-fetch budget exhausted") from error
            raise
        finally:
            if watchdog is not None:
                watchdog.cancel()
                watchdog.join(timeout=1)
            if response is not None:
                response.close()
            connection.close()
    raise ValueError("Too many source redirects")
