"""Explicit local Openings intake/export; no discovery, profile or delivery API."""

from __future__ import annotations

import http.client
import ipaddress
import json
import math
import socket
import threading
import time
from dataclasses import asdict, dataclass
from urllib.parse import urlencode

from models import JobVacancy
from openings_import import import_openings_export

MAX_BODY_BYTES = 2 * 1024 * 1024


class OpeningsAPIError(RuntimeError):
    """A bounded request failed; details omit tokens, posting data and response bodies."""


@dataclass(frozen=True, slots=True)
class OpeningsPosting:
    """Source posting only; stable source/external ID preserve requisition identity."""

    title: str
    company: str
    source: str
    external_id: str
    job_url: str
    location: str = ""
    description: str | None = None
    is_remote: bool | None = None
    job_level: str | None = None

    def payload(self) -> dict[str, object]:
        for name in ("title", "company", "source", "external_id", "job_url"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be nonempty text")
        if not isinstance(self.location, str):
            raise ValueError("location must be text")
        for name in ("description", "job_level"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{name} must be text or null")
        if self.is_remote is not None and type(self.is_remote) is not bool:
            raise ValueError("is_remote must be a boolean or null")
        return {**asdict(self), "status": "new"}


class OpeningsAPI:
    """One-request methods for an explicitly supplied numeric loopback endpoint.

    No server is started and no credentials are discovered. Writes require the
    operator to verify the pinned mirror fix before constructing a write-enabled
    client; that assertion is not remote attestation. A failed write may already
    have reached the server: reconcile its state before retrying manually.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        token: str,
        timeout_seconds: float = 15,
        mirror_fix_verified: bool = False,
    ) -> None:
        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError("Openings endpoint must be a numeric loopback address")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Invalid Openings port")
        if not isinstance(token, str) or not token.strip() or any(c in token for c in "\r\n"):
            raise ValueError("An explicit valid Openings token is required")
        if (
            type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 120
        ):
            raise ValueError("Timeout must be finite and between zero and 120 seconds")
        if type(mirror_fix_verified) is not bool:
            raise ValueError("Mirror-fix verification must be explicit boolean")
        self._host, self._port, self._token = host, port, token
        self._timeout = timeout_seconds
        self._mirror_fix_verified = mirror_fix_verified

    def export_jobs(self, *, limit: int = 50, offset: int = 0) -> tuple[JobVacancy, ...]:
        """Read one bounded JSON export page; do not auto-page or infer approval."""
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("Export limit must be between one and 1000")
        if type(offset) is not int or offset < 0:
            raise ValueError("Export offset must be nonnegative")
        query = urlencode({"format": "json", "limit": limit, "offset": offset})
        rows = self._request("GET", f"/api/export/jobs?{query}", None)
        if not isinstance(rows, list) or len(rows) > limit:
            raise OpeningsAPIError("Invalid Openings export response")
        try:
            return import_openings_export(rows)
        except (TypeError, ValueError):
            raise OpeningsAPIError("Invalid Openings export response") from None

    def add_posting(self, posting: OpeningsPosting) -> str:
        """Intake one posting as new; return canonical ID, never application consent."""
        if not self._mirror_fix_verified:
            raise OpeningsAPIError("Verify the reviewed Openings mirror fix before writes")
        result = self._request("POST", "/api/jobs", posting.payload())
        if (
            not isinstance(result, dict)
            or result.get("success") is not True
            or type(result.get("affected_count")) is not int
            or result["affected_count"] != 1
            or result.get("message") not in ("created", "updated")
            or not isinstance(result.get("job_ids"), list)
            or len(result["job_ids"]) != 1
            or not isinstance(result["job_ids"][0], str)
            or not result["job_ids"][0].strip()
        ):
            raise OpeningsAPIError("Invalid Openings intake response; reconcile before retry")
        return result["job_ids"][0]

    def _request(self, method: str, path: str, payload: dict[str, object] | None) -> object:
        body = None if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8")
        if body is not None and len(body) > MAX_BODY_BYTES:
            raise ValueError("Openings request exceeds body bound")
        deadline = time.monotonic() + self._timeout
        connection = http.client.HTTPConnection(self._host, self._port, timeout=self._timeout)
        watchdog: threading.Timer | None = None
        response: http.client.HTTPResponse | None = None
        try:
            connection.connect()
            sock = connection.sock
            if sock is None:
                raise OpeningsAPIError("Openings connection unavailable")

            def set_remaining_timeout() -> None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                if sock.fileno() >= 0:
                    sock.settimeout(remaining)

            set_remaining_timeout()

            def expire() -> None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            # Socket timeouts alone restart on each header read. The watchdog
            # interrupts a peer trickling headers/body across the total deadline.
            watchdog = threading.Timer(max(0, deadline - time.monotonic()), expire)
            watchdog.daemon = True
            watchdog.start()
            connection.request(
                method,
                path,
                body=body,
                headers={"X-Openings-Token": self._token, "Content-Type": "application/json"},
            )
            set_remaining_timeout()
            response = connection.getresponse()
            if response.status not in ((200,) if method == "GET" else (200, 201)):
                raise OpeningsAPIError(
                    f"Openings HTTP status {response.status}; no retry performed"
                )
            content_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                raise OpeningsAPIError("Openings response must be JSON")
            data = bytearray()
            while True:
                set_remaining_timeout()
                chunk = response.read1(min(65536, MAX_BODY_BYTES + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > MAX_BODY_BYTES:
                    raise OpeningsAPIError("Openings response exceeds body bound")
            set_remaining_timeout()
            return json.loads(data)
        except (OSError, http.client.HTTPException, UnicodeError, ValueError):
            raise OpeningsAPIError(
                "Openings request failed; reconcile writes before retry"
            ) from None
        finally:
            if watchdog is not None:
                watchdog.cancel()
                watchdog.join(timeout=1)
            if response is not None:
                response.close()
            connection.close()
