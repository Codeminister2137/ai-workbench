# Provider route access checks

Owner-approved requirements, 2026-10-15. Reusable catalog selection and scheduler
integration are planned; the current bounded probes save private per-run receipts.
This document does not claim that a general live command or schedule exists.

## Purpose and evidence

Access checks answer whether a particular configured provider/model route can
currently return a small response or a synthetic tool call. They do not certify
coding quality, privacy entitlement, fallback readiness or general availability.
Keep successful, failed, skipped and unobserved outcomes distinct.

The 2026-10-15 pre-reset OpenRouter sweep made 3 of 20 permitted attempts:
Liquid LFM and Nemotron Lightning answered correctly; Inkling Small returned 403,
triggering the prepared conservative stop policy. No tool phase ran. The precise
403 cause was not retained and remains unknown; this is not proof of a global
account refusal. Known usage for the two responses was 457 tokens and reported
$0; failed-request usage/cost is unknown. Gateway counters did not advance in the
before/after observations. Host attempts must never be replaced by that counter.

Requesty official documentation states a daily free-model limit but does not
identify the reset timezone. An authenticated catalog GET returned no numeric
reset/quota headers. UTC usage-report aggregation elsewhere would not prove the
free allowance resets at UTC midnight. Do not invent a pre-09:00 deadline.

## Required reusable workflow

- Take explicitly selected routes from the existing catalog/inventory. Provider
  inventory belongs behind provider adapters; the configured neutral routing
  catalog currently belongs to `ai_orchestrator`. Reuse that ownership rather
  than duplicating catalogs or forcing a new package dependency.
- Plan checks for missing or stale matching evidence; show the plan before
  inference. Match provider, exact model, endpoint, access/auth/billing scope,
  local account scope, probe kind and adapter/probe contract revision. Changing
  those inputs invalidates reuse. Never persist credentials or derive public
  account identifiers from secrets.
- Make freshness and failure cooldown explicit. A recent failed check is evidence
  of that attempt, not permission for an immediate retry loop. A skipped admission
  is not a failed model completion. Select an investigated alternative or request
  a fresh bounded diagnostic grant when appropriate.
- Reuse recorded observations without rerunning their consumed grant or launch
  sentinel. Every live invocation needs a new run/grant identity and explicit
  attempt, output, time, tool, account and privacy scope.
- Refresh price, quota and privacy admission before every completion even when
  an access receipt is fresh. Fresh access evidence never bypasses these guards.
- Keep only safe receipt fields: timestamps, route identity, check kind/version,
  attempt/response/check counts, closed failure classification, HTTP status,
  numeric usage/cost with coverage, quota/reset observations and evidence links.
  Missing values remain unknown. No raw prompts, reasoning, credentials or remote
  error text in ordinary records.
- Treat failures conservatively, but distinguish model/upstream refusal from
  proved account-wide limits. Save safe numeric/closed diagnostic fields before
  concluding scope. Never automatically retry, switch to paid billing or promote
  a route/default based on access checks.

## Keep allowance-consuming execution out of pytest

Use a separate explicit live command for ad-hoc investigation and future selected
scheduled runs. Normal pytest, full-suite helpers, import, discovery and Git hooks
must never launch these checks or consume allowance. Deterministic unit tests for
selection, freshness, receipt parsing and guards use fake HTTP only. Do not add
the live sweep as a pytest test, even one enabled by a normal environment flag.

## Ad-hoc and scheduled use

Ad-hoc runs respond to a concrete access question and a bounded owner grant.
Future end-of-allowance runs require verified provider/account reset evidence,
remaining allowance, a reserve for higher-priority authorized work and an active
execution window. Skip unknown reset/quota/privacy or unavailable approval.
Scheduling may choose stale access checks or another approved useful task when
an incoming reset would otherwise leave allowance unused. It must not generate
work merely to burn quota, revive a consumed grant, cross a reset into a new
allowance or install an unapproved recurring job.

Baseline CLI remains first; independent unattended supervision follows immediately.
This capability should compose with that supervisor and existing supported job
runners after their contract is selected. The current research queue is not an
arbitrary-command executor; do not insert access jobs into it under a false kind.

## Implementation decision to resolve before building storage/scheduling

Existing per-run JSON receipts are enough to preserve today's facts. For a reusable
selector, compare a small versioned private receipt index with reuse of existing
SQLite run storage. JSON is simple and keeps this slice independent, but needs
atomic writes and an indexing/concurrency policy. SQLite offers indexed history
and transactions, but extending current tables adds a migration and ownership
contract. Technical recommendation: first reuse immutable per-run receipts with
an offline read-only selector; decide whether a persistent index is needed from
actual selection cost. Do not introduce a second database or new daemon now.

Owner choices remain for the concrete persisted format, account-scope mechanism,
freshness/cooldown defaults and supported scheduled-job contract. The workflow
requirements above are accepted; these architectural details are not silently
selected by retaining evidence.

Sources checked 2026-10-15:

- [OpenRouter limits](https://openrouter.ai/docs/api_reference/limits): free usage
  is defined per UTC day; distinguish rate limits from credit/budget limits.
- [Requesty free-model limits](https://docs.requesty.ai/features/free-models):
  daily organization-wide allowance; reset time unspecified.
- [Requesty limits](https://docs.requesty.ai/features/api-limits): general spend
  and concurrency policies do not define the free daily reset instant.

Detailed run receipts and catalog/account observations stay in ignored private
artifacts. Preserve original failures and independently review numeric receipts
and cleanup; a reproducible probe procedure is separate from its one-time grant.
