# ADR-034 - SearXNG Research Discovery

**Status:** Accepted; routing/default policy superseded by ADR-036
**Date:** 2026-10-02

## Context

Research currently fetches supplied public URLs but does not discover sources.
The owner requires free-default search governed by the overall cost policy and
explicitly approved SearXNG and recording the decision on 2026-10-02.

## Options considered

- Configurable public SearXNG endpoint: documented HTTP search API, no search
  credentials required by the proposed integration; public-instance availability
  and JSON access vary.
- Brave Search API: official API, credentials and explicit allowance/spending
  enforcement required.
- Defer discovery and continue fetching supplied URLs only.

## Decision

Use configurable public SearXNG for the free-default research discovery path.
No specific endpoint has been selected or tested. Propose and verify an endpoint
before live use; do not silently switch to another provider on failure.
Do not introduce a self-hosted service or new dependency under this approval.
Optional paid alternatives must respect the overall cost policy and require
their own integration authorization; no charges are authorized by this decision.

Inference remains local. Search queries and ordinary HTTP request metadata leave
the machine for the configured SearXNG operator; upstream search engines may
also receive queries. This is the external query-sharing boundary presented
with the recommendation the owner approved. Credentials are not required for
the proposed public-endpoint path. Private prompts or workspace contents must
not be transmitted merely because discovery is enabled.

Reuse existing public-HTTP protections, CUSTOM permissions, bounded responses,
and local run evidence. Search results indicate discovery, not proof that the
linked sources were fetched or that their claims are correct. Preserve the
separate source-fetch/report-receipt gate. The exact search configuration and
receipt representation remain implementation work; material contract changes
still require a decision rather than being implied by this approval.

## Reason

The owner accepted the recommendation of SearXNG for its documented API and
free-default fit. The existing cost preference is recorded in ADR-033's dated
amendment. No additional personal rationale was supplied for the provider choice.

## Consequences

- Search availability depends on the selected public instance and its policies;
  discovery failures must be reported honestly.
- Endpoint validation, discovery/cost tests, and live search/fetch/report evidence
  are still required. Approval does not imply implemented or verified search.
- Search evidence should remain in the existing local run-evidence mechanism;
  any new persistent-data contract requires separate review.

Reference: [SearXNG search API](https://docs.searxng.org/dev/search_api.html).

## Endpoint investigation (2026-10-02)

No endpoint was selected. Bounded JSON API probes using the public query
`Ollama tool calling documentation` failed for nine candidates from the public
instance registry: `priv.au`, `opnxng.com`, `etsi.me`, `anonsearch.win`, and
`search.serpensin.com` returned HTTP 429; `baresearch.org`, `libresearch.space`,
and `search.inetol.net` returned non-JSON responses; `search.lumy.live` timed out.
The last three were tested with the existing protected public-HTTP fetcher.
These observations describe this machine's checks at that time, not permanent
instance availability. No inference or private workspace data was sent.

Proposed implementation contract, awaiting owner review: an explicit
`--searxng-endpoint` with no automatic endpoint/provider fallback, and separate
search receipts in existing run metadata containing the endpoint, query hash,
UTC time, response digest, and bounded discovered URLs. Query hashes reduce
raw-query retention but are not anonymization. Full-query receipts are the
debugging-oriented alternative. Neither proposal is an accepted persisted-data
decision yet. Discovery does not satisfy linked-source fetch receipt checks.

## Amendment - Full query retention (2026-10-02)

The owner chose full-query retention for now because the exact queries can help
refine workflows. Future search receipts will retain the submitted query locally
in the existing run-evidence mechanism. This supersedes the proposed query-hash
choice above; endpoint selection and the remaining integration are still pending.
Full queries support replay and debugging but retain more potentially sensitive
data than hashes. Retention does not authorize transmitting private prompts or
workspace contents to search operators or upstream engines.

## Further endpoint verification (2026-10-02)

A further bounded check tested sixteen candidates with the protected fetcher.
`https://search.mectov.my.id/search` returned JSON. Its initial query returned
zero results; a follow-up public `python` query returned actual Python.org links
over HTTP 200 without credentials or charges. Explicit DuckDuckGo and Google
queries returned zero results and CAPTCHA/suspension diagnostics. This verifies
some useful API access, not reliable coverage for every topic.

The proposed endpoint is configurable with no automatic fallback. Automatic
approval review rejected implementing the selected endpoint before explicit
endpoint approval, citing external query transmission. The owner was asked to
approve this endpoint for public-topic queries only. Private prompts, secrets,
and workspace contents remain excluded. No search-tool implementation was
applied; endpoint approval and integration are still pending. Probe evidence
is local under `artifacts/searxng-endpoint-check-20261002-164949/`.

## Amendment - Endpoint approval and default reconsideration (2026-10-02)

The owner explicitly approved `https://search.mectov.my.id/search`, with a caveat:
if a better search option exists when privacy is relaxed, use that for ordinary
research and retain SearXNG as a more private alternative for sensitive searches.
This resolves the specific endpoint approval issue. Search remains unimplemented.

Investigation identified a material distinction: public SearXNG reduces some
tracking and masks the user's IP from upstream engines, but its operator and
upstream engines still receive query contents. It is not a confidential-query
route. The owner has been asked to clarify whether sensitive means reduced
tracking or permission to disclose confidential query content. No broader
sensitive-data transmission permission has been inferred.

Technical recommendation, awaiting approval: evaluate Tavily Basic on its free
plan for ordinary public research; keep SearXNG explicitly selectable for public
topics where reduced tracking is desired; block external search for confidential
content. Tavily offers 1,000 monthly credits without a card, Basic uses one credit,
and its free plan stops at quota exhaustion. It requires an API key, currently
not configured. Brave is another candidate with an independent index, but its
monthly credits coexist with paid pricing and required billing details. These
API candidates have not been benchmarked against this repository's research
tasks; no result-quality superiority is established. Paid charges remain
unauthorized. Local synthesis and separate source-fetch evidence remain required.

## Amendment - Provider and fallback approval (2026-10-02)

The owner approved all proposed providers and requested fallback analogous to
coding agents. Sensitive searches mean reduced tracking when requested.
ADR-036 records the new routing/fallback policy and supersedes the earlier
single-provider default and no-switch proposal. Endpoint and full-query retention
approvals remain in force. Historical pending statements above describe earlier
investigation, not current unresolved approvals.

References checked on 2026-10-02:

- [SearXNG public-instance trust and privacy](https://docs.searxng.org/own-instance.html)
- [Tavily pricing and credit costs](https://docs.tavily.com/documentation/api-credits)
- [Tavily free-plan quota behavior](https://www.tavily.com/pricing)
- [Tavily query-data processing](https://www.tavily.com/privacy)
- [Brave pricing](https://brave.com/search/api/)
- [Brave account requirements and query retention](https://api-dashboard.search.brave.com/app/documentation/general/privacy-policy)
