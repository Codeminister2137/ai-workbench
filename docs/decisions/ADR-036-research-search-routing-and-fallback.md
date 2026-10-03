# ADR-036 - Research Search Routing and Fallback

**Status:** Accepted
**Date:** 2026-10-02

## Context and owner decision

The owner approved Tavily, Brave, and SearXNG, requested fallback analogous to
the coding-agent system, and clarified that sensitive searches meant reduced
tracking when requested. Ordinary research need not be completely private.
Full local query retention remains approved because it helps refine workflows.
No paid charges were authorized. This supersedes ADR-034's SearXNG-only default
and prohibition on automatic provider switching; its historical rationale remains.

## Options and trade-offs

- Tavily Basic: structured research discovery and a no-card free tier; requires
  an API key and shares queries with an external processor. Result quality has
  not been benchmarked for this repository. Paid/unknown account plans are rejected.
- Brave Search: independent index and monthly free credits; requires billing
  setup, an explicit free-only provider-side cap, and rights to retain results.
  Standard API retention restrictions conflict with saved research transcripts.
- Public SearXNG: no account key, reduces upstream identity tracking; public
  instances can be throttled or have upstream CAPTCHA failures. The operator
  still sees queries and client IP; this is not confidential search.
- A single provider: simpler, but outages or quota exhaustion stop discovery.
  Bounded fallback adds attempt bookkeeping without a new service or store.

## Implementation policy

`auto` orders Tavily, Brave, SearXNG for standard searches. Missing credentials
and unmet account requirements are recorded as skipped. Explicit primaries can
be selected; fallback can be disabled and respects the existing user fallback
setting. The successful route persists across implementation and repair.
Each eligible provider is tried at most once per query; authentication, quota,
and rejected-plan failures disable that provider for the run. Rate limits,
network failures, malformed responses, and upstream outages permit fallback.
Genuine empty results succeed and do not trigger another provider.

`reduced_tracking` permits only SearXNG, including during fallback. `disabled`
or provider `none` removes discovery. These preferences govern search separately
from `local_only` inference. Private prompts, secrets, and workspace content
must not be submitted as search queries. No semantic confidentiality detector
is claimed. Source fetching remains available when discovery is disabled.

Tavily checks `/usage` before every query, requires a recognized free account
with no pay-as-you-go allowance/usage and available credits, and sends Basic
requests without automatic parameters, generated answers, or raw-content extraction.
Unknown billing metadata fails closed. Provider-side quota enforcement handles
concurrent usage; local counters alone would not guarantee a spending limit.

Brave is eligible only with `BRAVE_SEARCH_API_KEY`,
`BRAVE_SEARCH_FREE_ONLY_CONFIRMED=1`, and `BRAVE_SEARCH_STORAGE_ALLOWED=1`.
The first confirmation means the owner configured a zero paid monthly usage
allowance (the dashboard adds included credits) and disabled auto-reload; the
second means the account permits retaining returned data in transcripts.
These declarations are setup prerequisites, not automatic verification of an
account. The documented search API exposes no billing preflight comparable to
Tavily's usage endpoint. Do not enable them merely to bypass eligibility checks.

Search routes use public DNS validation, pinned connections, verified TLS,
fixed authenticated origins, no redirects, bounded JSON, and sanitized failures.
No new dependency or infrastructure is introduced. Models supply only query
and result count, never keys, endpoints, privacy overrides, or billing settings.
Search receipts retain full queries, UTC time, route, skips/failures, status,
response digest when available, and discovered URLs in existing stage metadata.
Search data/snippets remain discovery and cannot satisfy fetch receipt validation.

## Consequences and validation limits

Fallback improves availability while preserving cost/tracking eligibility; it
does not guarantee useful results or establish provider-quality superiority.
Credentials are environment-only and excluded from records and object repr.
Without keys, automatic routing uses the approved public endpoint
`https://search.mectov.my.id/search`. Authenticated live verification needs
owner-provided credentials; offline contract tests do not prove live account setup.

References: [Tavily usage API](https://docs.tavily.com/documentation/api-reference/endpoint/usage),
[Tavily search API](https://docs.tavily.com/documentation/api-reference/endpoint/search),
[Brave billing and retention FAQ](https://api-dashboard.search.brave.com/documentation/resources/help-feedback),
[SearXNG API](https://docs.searxng.org/dev/search_api.html).
