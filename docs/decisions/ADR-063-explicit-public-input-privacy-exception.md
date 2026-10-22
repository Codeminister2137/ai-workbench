# ADR-063 — Explicit public-input privacy exception

**Status:** Accepted, 2026-10-21; implemented offline, live access unverified.

## Decision and owner intent

The owner approved permitting explicitly public or synthetic input despite
uncertain no-training entitlement, retaining protections for private material.
This enables useful allowance work without treating all externally permitted
or low-risk repository data as public. Possible retention/training of that
public input and the need for careful classification were explicit trade-offs.

The alternative blanket entitlement gate is simpler and more conservative,
but prevents free-route work even with intentionally public material. The
selected exception depends on correct caller classification and does not
establish equivalent privacy terms between processors.

## Contract

For OpenRouter, `AIRequest.privacy_class` must be `PUBLIC_OR_LOW_RISK` and
`AIRequest.metadata["public_or_synthetic"]` must be the literal boolean `True`.
Caller code thereby attests that the **complete** input, including system text,
history, tool schemas/results, attachments and continuation data, contains only
public or synthetic material approved for possible retention/training. Model
output is not authorization. Reassess every composed request before setting it
again; no agent loop, CLI or saved session obtains the attestation automatically.
This declaration is not a content scanner or proof that data is public.

The adapter permits uncertain Free-plan privacy-filter entitlement for that
request. Exact named-model zero prices, tool-capability metadata, valid remaining
quota and ordinary privacy enforcement still apply to completions and streams.
Keep `data_collection=deny`, zero price caps and required-parameter enforcement;
these requested constraints do not prove Free-plan filter enforcement.
There is no paid retry, source/model change, automatic billing fallback or new
inference grant. Unattested low-risk and externally allowed private requests keep
their entitlement gate; local-only/sensitive requests retain their existing denial.

The attestation is local request metadata, not a wire field or persistent client
setting. A request-aware compatible-adapter hook supplies policy context without
mutable client state or duplicate metadata checks. Requesty behavior is unchanged.
No new privacy enum, configuration/CLI option, database, service or dependency.

## Validation

Offline tests cover complete/streaming calls, both `require_free_model` settings,
exact boolean classification, unchanged wire guards, private/local/sensitive
denials, invalid/exhausted quota, nonzero prices and a public request followed by
an unattested request on the same client. Original tests remain unchanged.
Live access, model quality and baseline CLI acceptance are separate questions.
