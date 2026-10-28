# ADR-073: Shared Responses tools and stateless continuation

**Status:** Accepted and implemented; live C6 acceptance open
**Date:** 2026-10-28

## Context and owner decision

The Meta API supports developer-defined tools, but Workbench's Responses adapter
implemented text only. The catalog correctly advertised tools as unavailable.
The standalone Operator has a separate implementation; it does not provide this
capability to Workbench. A planned cross-route C6 process-continuity trial therefore
needed protocol support before any live coding request.

The owner approved the recommendation to implement Responses tool support in the
existing shared adapter, rather than duplicate it in a Meta-specific adapter.
Reuse and avoiding duplicate protocol maintenance were the stated technical
recommendation; no additional personal rationale is attributed to the owner.

## Decision

Translate existing neutral tool definitions, calls and results into Responses
function tools, `function_call` and `function_call_output` items. Validate call ids
and argument objects before delivering executable calls. Streaming normalizes
completed output through the same parser and preserves terminal failure/usage.

Use ADR-055's transient, origin-bound ProviderContinuation for ordered native
output, assistant phase and opaque encrypted reasoning. Replay only to the same
provider/model/endpoint and only while the neutral message still matches it.
Rewritten messages and cross-origin fallback use neutral text/tool history and
do not replay stale native or reasoning state. Do not persist or log reasoning.

Meta explicitly requests encrypted reasoning and retains `store:false`; no
`previous_response_id` or server-managed conversation state is introduced.
Contributor variants remain refused. Other Responses subclasses share tool
serialization/parsing; this does not establish every model's entitlement or
tool quality. Catalog capabilities remain distinct from live acceptance.

## Alternatives and consequences

- Shared implementation: reusable protocol handling and one normalization path;
  requires regression coverage for Meta, generic Responses and Go Responses.
- Meta-only implementation: smaller initial regression surface; duplicates common
  protocol logic and creates additional maintenance as the protocol evolves.

Existing message contracts, storage formats, approval policy, provider boundaries
and fallback policy remain unchanged. Native continuation counts toward existing
admission. A completed offline tool loop proves software composition, not model
quality, selected-route live C6 continuity or installed-client parity.

## Sources

Official references checked 2026-10-28:
[Meta tools](https://dev.meta.ai/docs/tool-calling) and
[Responses stateless replay](https://dev.meta.ai/docs/protocols/responses).
