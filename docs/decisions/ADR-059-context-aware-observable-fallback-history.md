# ADR-059 - Context-aware observable fallback history

**Status:** Accepted (2026-10-15); implemented offline, live acceptance incomplete

## Owner decision and rationale

The owner chose conditional full observable history (A) or the existing bounded
handoff (B), because fallback models have their own context limits. They approved
the recommended threshold: use A only when at least 20% of the destination's
effective context remains after input, reserved output and framing. Near or over
that threshold, or with unknown effective capacity, default to B. This partially
supersedes ADR-032's blanket counts-only cross-route handoff; its historical intent
and all other boundaries remain. ADR-055's provider-private state exclusion remains.

## Alternatives and trade-offs

- Conditional full observable history preserves prior instructions, messages,
  tool calls/results and evidence of partial effects. It transmits more task data,
  consumes context and requires destination-specific admission. The 20% reserve
  leaves room for ongoing tool work but can require B sooner than a hard-fit gate.
- Counts-only handoffs everywhere minimize transmission and context usage, but
  omit mid-turn evidence and require more reinspection. They remain the safe
  fallback when the complete request or destination capacity cannot be assessed.

The recommendation was conditional A/B with explicit headroom. The owner agreed;
no additional personal rationale is invented.

## Implementation and boundaries

FallbackSession holds transient observable native error checkpoints. Remove
ProviderContinuation before retaining these for transfer; never serialize provider
reasoning/raw metadata. Keep ordinary message contents and tool arguments/results
complete when A is selected. Do not silently shorten that history to qualify for A.
Multiple failed routes retain all available checkpoints within the invocation.
Clear them at the next invocation, and never put them in saved metadata handoffs,
progress messages or weaker preservation prompts.

The composing CLI adds history to an eligible implementation route's host-controlled
native tool loop. Serialize it as labelled data, without replaying tool calls or
granting approval. Current required instructions, tools, scope and approval policy
still govern. The same destination request estimate used by native admission counts
the complete input and tool schemas; reserve explicit output or the existing default
min(8192, context/4), plus 256 framing tokens. Select A when
`5 * (estimated_input + reserved_output + 256) <= 4 * effective_context`.
Equality qualifies. Recheck as the destination's ongoing tool history grows.

B leaves the original request/objective/instructions and existing observed handoff
intact. It must still pass ordinary hard admission when capacity is known. Required
instructions are never trimmed to make either mode fit. Hosted unknown capacity
remains reported as unknown, not a verified fit. UTF-8 sizing is an estimate, not an
exact tokenizer guarantee. Ollama uses the existing model/runtime minimum capacity.
External native clients add unmeasured context/tools internally, so retain B until
their full effective request can be assessed. External checkpoints unavailable
through existing contracts are not invented. Research/plain completion paths retain
their existing bounded behavior; this slice covers native coding tool loops.

Candidate selection still enforces privacy, billing tier, declared quality floor,
required tools and compatible approvals before any transfer. Preserved edits and
host-owned processes remain in place; the model must inspect uncertain effects.
No automatic replay, broader permissions, provider activation, paid fallback,
reasoning persistence, database migration, dependency, default model or quality
promotion is introduced. This decision is not a live inference grant.

## Validation

Deterministic tests cover the exact 20% boundary, unknown/invalid/overfull capacities,
tool-schema and output reserves, growth during the loop, unchanged B requests,
hard refusal when required input does not fit, provider-state exclusion, transient
multi-route checkpoints and metadata-only saved handoffs. A synthetic CLI transport
verifies a real partial edit followed by full observable history at the next route,
while retaining zero-price, privacy, approval and protected-file assertions.
Live coding quality and current account eligibility remain separately unproved.
