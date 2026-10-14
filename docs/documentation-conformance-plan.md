# Official-documentation conformance review

**Priority: High. Scope: whole repository. Status: planned; first Ollama fix implemented.**

The owner prioritized this on 2026-10-11: differences between official documentation
and implementation confuse humans and AI and create later problems. Dropped Ollama
thinking state between tool calls is the first confirmed discrepancy; its repair
does not establish repo-wide conformance or successful coding-quality acceptance.

## Bounded review order

1. Provider adapters/shared contracts: fields, multi-turn tools, continuation,
   streaming, errors, timeout semantics and supported versions.
2. Orchestration/agents: provider limits, fallback, context/token accounting,
   approval/session ownership and lifecycle.
3. Council, job search and automation integrations: API/data contracts,
   authentication, paging/retries and documented SDK usage.
4. Repository tooling: Python/package configuration, CLI usage, dependencies,
   examples and guides.

Prioritize used, failing and high-risk surfaces in reviewable slices alongside
current product work. This does not authorize blanket rewrites, dependency
upgrades, new services or external data transmission.

## Evidence and completion

- Identify installed/supported versions; use primary official documentation or
  versioned upstream source, distinguishing current docs from the version in use.
- Compare actual code paths with focused contract tests, including multi-turn and
  failure behavior. Record reproducible discrepancies and their concrete effects.
- Classify each finding as a bug, stale local guidance, intentional departure or
  unresolved decision. Official examples alone do not mandate an implementation.
- Fix demonstrated bugs and affected guides together. Document valid departures;
  ask at material architecture/privacy/API/dependency boundaries.
- Verify tests/diffs and record remaining limits in the existing handoff/report,
  without adding a tracking system. Use scoped live checks where necessary.

Each slice finishes when its selected contracts conform or have justified,
explicit departures. Whole-repository completion requires coverage of all groups.

## First finding

Ollama's multi-turn examples retain the complete assistant message; streamed
follow-ups include thinking, content and tool calls. Our normalized follow-up
omitted thinking. ADR-055 records explicit transient message metadata as the fix.
Verify roundtrip/privacy/sizing offline and native tool effects live. No quality
gain is inferred solely from documentation alignment.

Sources: [Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling),
[Ollama thinking](https://docs.ollama.com/capabilities/thinking).

## Subsequent bounded findings

The shared process tool advertised argv as an unconstrained array even though its
handler accepts only strings. Optional neutral array-element metadata now survives
agent/provider translation and advertises `items: {type: string}` for that tool.
Existing callers omitting metadata keep their schema. This corrects the published
tool contract; it does not establish the cause of a gateway400 or coding quality.

Requesty's current model catalog exposes cache-write `caching_price`,
`caching_5m_price` and `caching_1h_price` alongside cache-read prices. The existing
free-only checker ignored those write prices. It now checks every advertised
cache price at both model and threshold tiers before completion or streaming;
offline regressions refuse a nonzero price before POST and retain zero-price
behavior. No new account, source, billing fallback or transmission is activated.
Malformed catalog UTF-8 now produces the existing configuration refusal before
inference instead of escaping as an unhandled decoder exception.
Source: [Requesty List Models](https://docs.requesty.ai/api-reference/endpoint/models-list).

Council declared a message-to-conversation foreign key but never enabled SQLite
enforcement. It now enables the existing constraint on every store connection.
Offline checks reject new orphan messages, preserve normal/resumed history, and
retain historical orphan rows without migration or deletion. This changes no
schema or application workflow; [SQLite requires per-connection enablement](https://www.sqlite.org/foreignkeys.html#fk_enable).
