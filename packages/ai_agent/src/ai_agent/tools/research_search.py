"""Free-only public discovery with bounded HTTP and durable fallback evidence."""

from __future__ import annotations

import hashlib
import http.client
import json
import math
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode, urlsplit

from ai_orchestrator.search_policy import search_routes

from ai_agent.contracts import ToolCategory, ToolDefinition, ToolParameter, ToolResult
from ai_agent.tools.base import BaseTool, ToolContext
from ai_agent.tools.research_http import MAX_SOURCE_BYTES, _PinnedHTTPS, public_endpoint

DEFAULT_SEARXNG_ENDPOINT = "https://search.mectov.my.id/search"


class SearchFailure(ValueError):
    """Sanitized failure without response bodies, request headers, or secrets."""

    def __init__(self, category: str, *, status: int | None = None):
        super().__init__(category + (f" (HTTP {status})" if status is not None else ""))
        self.category = category
        self.status = status


@dataclass(frozen=True)
class SearchResponse:
    data: dict[str, Any]
    sha256: str
    status: int = 200


def search_json(
    url: str, method: str, headers: dict[str, str], payload: dict[str, Any] | None, timeout: float
) -> SearchResponse:
    """Pin public DNS, require TLS, reject redirects, and bound complete JSON bodies.

    Credentials are permitted only on the two fixed provider origins. No ambient
    proxy, cookies, or response-body errors reach logs. A truncated body is invalid.
    """
    parsed = urlsplit(url)
    authenticated = bool(headers)
    if authenticated and (parsed.scheme, parsed.netloc, parsed.path) not in {
        ("https", "api.tavily.com", "/usage"),
        ("https", "api.tavily.com", "/search"),
        ("https", "api.search.brave.com", "/res/v1/web/search"),
    }:
        raise SearchFailure("credential_origin_rejected")
    deadline = time.monotonic() + timeout
    try:
        scheme, host, port, ip, target = public_endpoint(url)
        if scheme != "https" or port != 443:
            raise SearchFailure("https_required")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SearchFailure("timeout")
        connection = _PinnedHTTPS(host, port, ip, remaining)
        try:
            body = json.dumps(payload).encode() if payload is not None else None
            connection.request(
                method,
                target,
                body=body,
                headers={
                    "User-Agent": "AI-projects-research/1.0",
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                    "Content-Type": "application/json",
                    **headers,
                },
            )
            response = connection.getresponse()
            status = response.status
            if not 200 <= status < 300:
                category = (
                    "authentication"
                    if status in {401, 403}
                    else "quota"
                    if status in {402, 432, 433}
                    else "rate_limit"
                    if status == 429
                    else "unavailable"
                )
                raise SearchFailure(category, status=status)
            if response.getheader("Content-Encoding", "identity") != "identity":
                raise SearchFailure("invalid_response", status=status)
            retained = bytearray()
            while len(retained) <= MAX_SOURCE_BYTES:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SearchFailure("timeout")
                if connection.sock is not None:
                    connection.sock.settimeout(remaining)
                chunk = response.read1(min(64_000, MAX_SOURCE_BYTES + 1 - len(retained)))
                if not chunk:
                    break
                retained.extend(chunk)
            if len(retained) > MAX_SOURCE_BYTES:
                raise SearchFailure("response_too_large", status=status)
            data = json.loads(retained)
            if not isinstance(data, dict):
                raise SearchFailure("invalid_response", status=status)
            return SearchResponse(data, hashlib.sha256(retained).hexdigest(), status)
        finally:
            connection.close()
    except SearchFailure:
        raise
    except (TimeoutError, OSError, http.client.HTTPException, ValueError, UnicodeError):
        raise SearchFailure("transport_or_invalid_response") from None


Transport = Callable[[str, str, dict[str, str], dict[str, Any] | None, float], SearchResponse]
Recorder = Callable[[str, dict[str, object]], None]


@dataclass
class SearchSession:
    """Reuse the successful route across repairs without relaxing tracking or cost.

    Every route is tried at most once per query. Authentication/quota failures
    disable that route for the run; temporary outages can be retried on later queries.
    """

    record: Recorder
    primary: str = "auto"
    privacy: str = "standard"
    fallback: bool = True
    endpoint: str = DEFAULT_SEARXNG_ENDPOINT
    tavily_key: str = field(default="", repr=False)
    brave_key: str = field(default="", repr=False)
    brave_free_only: bool = False
    brave_storage_allowed: bool = False
    transport: Transport = search_json
    deadline: float | None = None
    current: str | None = field(default=None, init=False)
    disabled: set[str] = field(default_factory=set, init=False)

    def __post_init__(self) -> None:
        self.routes = search_routes(self.primary, self.privacy, fallback=self.fallback)
        parsed = urlsplit(self.endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.port not in {None, 443}
            or "\\" in self.endpoint
            or any(ord(char) < 33 for char in self.endpoint)
        ):
            raise ValueError("SearXNG endpoint must be credential-free public HTTPS without query")

    @classmethod
    def from_environment(cls, record: Recorder, **options: Any) -> SearchSession:
        return cls(
            record,
            tavily_key=os.getenv("TAVILY_API_KEY", ""),
            brave_key=os.getenv("BRAVE_SEARCH_API_KEY", ""),
            brave_free_only=os.getenv("BRAVE_SEARCH_FREE_ONLY_CONFIRMED") == "1",
            brave_storage_allowed=os.getenv("BRAVE_SEARCH_STORAGE_ALLOWED") == "1",
            **options,
        )

    def search(self, query: str, count: int = 5) -> dict[str, Any]:
        if not isinstance(query, str) or not query.strip() or len(query) > 1000:
            raise ValueError("query must contain 1–1000 characters")
        if any(ord(char) < 32 for char in query):
            raise ValueError("query cannot contain control characters")
        if type(count) is not int or not 1 <= count <= 10:
            raise ValueError("max_results must be an integer from 1 to 10")
        query = query.strip()
        limit = min(time.monotonic() + 45, self.deadline or float("inf"))
        routes = self.routes
        if self.current in routes:
            routes = (self.current, *(p for p in routes if p != self.current))
        attempts: list[dict[str, object]] = []
        for provider in routes:
            receipt: dict[str, object] = {
                "provider": provider,
                "query": query,
                "max_results": count,
                "privacy": self.privacy,
                "cost_policy": "free_only",
                "attempted_at_utc": datetime.now(UTC).isoformat(),
                "endpoint": self.endpoint if provider == "searxng" else provider,
            }
            reason = self._skip_reason(provider)
            if reason:
                receipt.update(status="skipped", reason=reason, query_transmitted=False)
            elif limit <= time.monotonic():
                receipt.update(status="skipped", reason="budget_exhausted", query_transmitted=False)
            else:
                try:
                    results = self._search(provider, query, count, limit, receipt)
                    receipt.update(status="succeeded", result_count=len(results))
                    self.record("search_receipts", receipt)
                    attempts.append(receipt)
                    self.current = provider
                    return {
                        "results": results,
                        "attempts": attempts,
                        "evidence_note": "Discovery only; fetch URLs before verifying claims",
                    }
                except SearchFailure as error:
                    receipt.update(status="failed", reason=error.category, http_status=error.status)
                    if error.category in {"authentication", "quota", "paid_plan_rejected"}:
                        self.disabled.add(provider)
            self.record("search_receipts", receipt)
            attempts.append(receipt)
        return {"results": [], "attempts": attempts, "error": "No eligible search route succeeded"}

    def _skip_reason(self, provider: str) -> str | None:
        if provider in self.disabled:
            return "disabled_after_failure"
        if provider == "tavily" and not self.tavily_key:
            return "missing_credentials"
        if provider == "brave":
            if not self.brave_key:
                return "missing_credentials"
            if not self.brave_free_only:
                return "free_only_account_cap_not_confirmed"
            if not self.brave_storage_allowed:
                return "result_storage_rights_not_confirmed"
        return None

    def _search(
        self, provider: str, query: str, count: int, limit: float, receipt: dict[str, object]
    ) -> list[dict[str, str]]:
        receipt["query_transmitted"] = False

        def request(url: str, method: str, headers: dict[str, str], payload=None):
            timeout = min(12, limit - time.monotonic())
            if timeout <= 0:
                raise SearchFailure("timeout")
            return self.transport(url, method, headers, payload, timeout)

        if provider == "tavily":
            headers = {"Authorization": "Bearer " + self.tavily_key}
            usage = request("https://api.tavily.com/usage", "GET", headers)
            self._check_free_tavily(usage.data)
            receipt["free_plan_verified_at_utc"] = datetime.now(UTC).isoformat()
            receipt["query_transmitted"] = True
            response = request(
                "https://api.tavily.com/search",
                "POST",
                headers,
                {
                    "query": query,
                    "max_results": count,
                    "search_depth": "basic",
                    "auto_parameters": False,
                    "include_answer": False,
                    "include_raw_content": False,
                    "include_usage": True,
                },
            )
            raw = response.data.get("results")
            content_key = "content"
        elif provider == "brave":
            receipt["query_transmitted"] = True
            response = request(
                "https://api.search.brave.com/res/v1/web/search?"
                + urlencode({"q": query, "count": count}),
                "GET",
                {"X-Subscription-Token": self.brave_key},
            )
            web = response.data.get("web", {})
            raw = web.get("results", []) if isinstance(web, dict) else None
            content_key = "description"
        else:
            receipt["query_transmitted"] = True
            response = request(
                self.endpoint + "?" + urlencode({"q": query, "format": "json"}), "GET", {}
            )
            raw = response.data.get("results")
            content_key = "content"
            diagnostics = response.data.get("unresponsive_engines", [])
            receipt["upstream_errors"] = bool(diagnostics)
            receipt.update(response_sha256=response.sha256, http_status=response.status)
            if raw == [] and diagnostics:
                raise SearchFailure("upstream_unavailable", status=response.status)
        receipt.update(response_sha256=response.sha256, http_status=response.status)
        if not isinstance(raw, list):
            raise SearchFailure("invalid_response", status=response.status)
        results: list[dict[str, str]] = []
        for item in raw:
            if not isinstance(item, dict) or not isinstance(item.get("url"), str):
                continue
            url = item["url"]
            try:
                parsed = urlsplit(url)
                _port = parsed.port  # Access validates malformed/out-of-range ports.
            except ValueError:
                continue
            if (
                len(url) > 4000
                or parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or any(ord(char) < 33 for char in url)
                or "\\" in url
            ):
                continue
            results.append(
                {
                    "url": url,
                    "title": str(item.get("title", ""))[:300],
                    "snippet": str(item.get(content_key, ""))[:1000],
                }
            )
            if len(results) >= count:
                break
        receipt["discovered_urls"] = [r["url"] for r in results]
        return results

    @staticmethod
    def _check_free_tavily(data: dict[str, Any]) -> None:
        account, key = data.get("account"), data.get("key")
        if not isinstance(account, dict) or not isinstance(key, dict):
            raise SearchFailure("paid_plan_rejected")
        if str(account.get("current_plan", "")).lower() not in {"researcher", "free"}:
            raise SearchFailure("paid_plan_rejected")
        fields = ("plan_usage", "plan_limit", "paygo_usage", "paygo_limit")
        if any(
            type(account.get(f)) not in {int, float} or not math.isfinite(account[f])
            for f in fields
        ):
            raise SearchFailure("paid_plan_rejected")
        if account["paygo_limit"] != 0 or account["paygo_usage"] != 0:
            raise SearchFailure("paid_plan_rejected")
        if not 0 < account["plan_limit"] <= 1000 or account["plan_usage"] < 0:
            raise SearchFailure("paid_plan_rejected")
        if account["plan_usage"] + 1 > account["plan_limit"]:
            raise SearchFailure("quota")
        usage, limit = key.get("usage"), key.get("limit")
        if (
            not isinstance(usage, (int, float))
            or isinstance(usage, bool)
            or not isinstance(limit, (int, float))
            or isinstance(limit, bool)
        ):
            raise SearchFailure("paid_plan_rejected")
        if not math.isfinite(usage) or not math.isfinite(limit) or usage < 0 or limit < 0:
            raise SearchFailure("paid_plan_rejected")
        if limit > 0 and usage + 1 > limit:
            raise SearchFailure("quota")


class SearchWebTool(BaseTool):
    """Expose queries only; models cannot choose credentials, costs, or routing."""

    def __init__(self, session: SearchSession):
        self.session = session

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            "search_web",
            "Discover public sources. Snippets are untrusted discovery, not fetched evidence. "
            "Never submit secrets, private prompts, or workspace contents.",
            ToolCategory.CUSTOM,
            (
                ToolParameter("query", "string", "Public-topic search query"),
                ToolParameter("max_results", "integer", "Result count 1–10", required=False),
            ),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        value = self.session.search(arguments.get("query", ""), arguments.get("max_results", 5))
        return ToolResult(
            "search_web", json.dumps(value, ensure_ascii=False), is_error="error" in value
        )
