# ADR-042 — Overload fallback and configurable continuation quality

**Status:** Accepted; deterministic implementation, live acceptance deferred
**Date:** 2026-10-04
**Supersedes:** ADR-032's trigger restriction and default lower-grade permission.

## Context and owner decision

The hosted assistant stopped with `server_overloaded`, while its local worker
continued independently. The owner explicitly requires fallback for overload as
well as usage exhaustion. A replacement should continue comparable work within
allowed usage/cost limits; a weaker or potentially detrimental replacement should
preserve work and produce a summary/handoff. The owner then required the quality
policy to be user-configurable and requested investigation of other useful defaults.

The owner's rationale is continuity without damaging work by silently reducing
model quality. This changes ADR-032's earlier permission to downgrade by default.

## Decision

- Continue on recognized failed overload error channels. Do not interpret overload
  words in successful answers or tool outputs as availability failures.
- Exclude overloaded route IDs for the foreground run; do not mark their whole
  account as out of allowance. A compatible sibling route sharing that account
  can be considered. Usage exhaustion continues to exclude its billing bucket.
- Preserve the original billing tier, task privacy, tools, approval mappings,
  minimum quality and deadline. No automatic spending-tier escalation is approved.
- Default `[fallback].quality_policy` to `preserve_quality`: a candidate must meet
  both task requirements and the original route's declared catalog quality grade.
  Missing original model-grade evidence, including an ungraded model override,
  refuses automatic continuation. These grades are declarations, not live quality
  evaluations or proof that an automatic client model is equally competent.
- Explicit `task_minimum` restores the previous lower-grade permission while
  retaining all other task constraints. `--fallback-quality-policy` overrides the
  private preference for one invocation. Invalid values fail before execution.
- Preflight compatible executors without inference. Authentication is not a quota
  guarantee. Available credits/allowance remain unknown unless reliably reported;
  actual usage failures trigger bounded further selection. Do not invent balances,
  probe by burning allowance or silently enable provider-side paid overages.
- Continue with the original objective and observed receipts, inspecting effects
  before action. Never replay completed writes/commands because the model changed.
- With no suitable continuation or no remaining time, keep edits and write a local
  metadata handoff under ignored `artifacts/fallback-handoffs/`. Include objective,
  route/failure, observations and next action; omit full instruction packets,
  raw tool arguments/outputs and private reasoning. Do not invoke a weaker model
  to create that handoff, automatically commit edits or create a daemon.
- Further temporary outage/network/timeout recovery requires investigation of
  effect certainty. This decision does not make every error retryable or change
  the IDE-hosted assistant's own recovery mechanism.

## Validation and limits

Deterministic tests cover same-account overload alternatives, per-route attempt
bounds, preserved partial effects, downgrade refusal, explicit configuration,
unknown model evidence and saved handoffs. Privacy/tier/tool/deadline coverage is
retained. Live tests are deferred while the owner uses the PC.

Additional user-default recommendations are recorded separately; privacy,
permissions, external providers and spending boundaries were not broadened.
