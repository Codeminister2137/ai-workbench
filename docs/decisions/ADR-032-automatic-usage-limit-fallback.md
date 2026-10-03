# ADR-032 - Automatic Usage-Limit Fallback

**Status:** Accepted
**Date:** 2026-10-01

## Context And Owner Direction

The owner wants the coding CLI to continue automatically when Codex or another
selected route exhausts its allowance. Fallback is integral default behavior,
not an occasional execution flag. If no comparable route remains, inform the
user. The owner also requires needed account sign-in before execution, rather
than stopping an unattended run to authenticate.

The owner clarified that quality grades influence selection, but a lower-grade
route is permitted when it meets the task requirements. The rationale is to use
available capacity without unnecessary interruption or paid escalation.

## Decision

- `ai_orchestrator.fallback` owns deterministic candidate policy. Executors
  normalize usage failures; the composing CLI handles readiness and continuation.
- Enable fallback by default. Private `[fallback].enabled = false` is an escape
  hatch. Preserve the existing cost preference and explicit primary selection.
- After quota exhaustion, primary route/provider/model overrides may change.
  Keep the task's privacy, capabilities, minimum quality, and latency constraints.
  Rank by existing quality/latency preferences; do not require the replacement
  to match the original route's higher quality grade or change catalog grades.
- Use the original route's **same billing tier**, even when the task ceiling
  permits higher tiers. Neither paid escalation nor a lower-tier switch happens
  silently. Exclude an exhausted billing source, including sibling models sharing
  its bucket. No cross-run quota registry or guessed reset window is introduced.
- Before primary execution, check the primary native client and eligible fallback
  credentials without inference. An unverified primary login stops startup.
  Native checks use Codex login status, Kiro whoami, Antigravity's authenticated
  model list, and Copilot's documented SDK auth-status RPC. Provider routes use
  authenticated model listing. Local routes require a reachable runtime.
- Offer sign-in in an interactive terminal and recheck it. In unattended runs,
  print sign-in instructions and exclude unverified routes. Authentication can
  expire later; preflight is not a quota or entitlement guarantee.
- Preserve requested approval policy and executor-specific capabilities. Routes
  lacking the mapping are ineligible; do not broaden permissions or silently drop
  required search, schema, image, MCP, or session options.
- Switch only for a failed native-client usage/quota error or normalized provider
  rate/usage-limit error. Other failures retain existing failure handling. Never
  classify quota words in successful answers or tool output as exhaustion.
- Continue in the existing working tree, without resetting or replaying edits.
  Pass the original objective and a bounded, observed-state handoff. Native-loop
  error checkpoints retain messages locally; forwarded handoffs use counts and
  direct the replacement to inspect files. Raw tool arguments/outputs are omitted.
- Keep the replacement across repair attempts. Record effective route and attempt
  history in orchestrated implementation-stage details. Honor the existing away
  budget before starting another fallback; do not create a new budget per switch.
- If ready comparable routes are exhausted or absent, print the reason, preserve
  partial work, and return failure without mid-run login or user input.

## Alternatives And Consequences

A hard requirement to match the original model's quality grade unnecessarily
excludes capable routes such as Copilot for standard coding tasks. Task gates
plus quality ranking reflect the owner's clarification without claiming equal
model quality. An explicitly high task-quality requirement remains a hard gate.

Retrying the same allowance bucket through a different model can repeatedly hit
the same limit. Per-run bucket exclusion is conservative and bounded; finer
account/model quota scope can be added when reliable metadata justifies it.

Cross-client native sessions and private reasoning are not portable. This is a
continuation from observed project state, not an identical native-session resume.
An arbitrary side effect cannot be guaranteed exactly once by a model handoff;
the prompt instructs inspection and avoiding repetition of completed writes.
External-client chat mode and restart-after-process-crash recovery remain outside
this coding-run slice. Existing local persistence remains in place; no new
database, service, Python dependency, or authorization store is added.

## Validation

Deterministic tests cover task/grade filtering, financial/privacy/tool constraints,
authentication preflight, partial edits, bounded exhaustion, error classification,
native tool checkpoints, and actual CLI integration. Manual acceptance simulates
the initial Codex quota failure and uses a real authenticated Copilot client on
synthetic files. It verifies preserved partial work and deterministic validation;
it does not claim naturally exhausting a real allowance or model-quality gains.

## Authentication References

- [Copilot SDK authentication status](https://docs.github.com/en/copilot/how-tos/copilot-sdk/troubleshooting/compatibility)
- [Official SDK RPC implementation](https://github.com/github/copilot-sdk/blob/main/python/copilot/client.py)
- [Kiro authentication](https://kiro.dev/docs/cli/authentication/)
- [Antigravity native client](https://www.antigravity.google/docs/cli/reference/)
