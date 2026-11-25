# Fallback repair: verdict pipeline now (B), single executor later (C)

Status: B accepted and implemented 2026-11-23 (proven live: 45 verdict
switches 23-24.11). C accepted 23.11, GO recorded 25.11, implemented
25.11 (single `FallbackExecutor`; drain/relay/Mai migrated;
`FallbackSession` deleted). Remaining acceptance: capped-primary live
proofs per path (needs inference allowance) + C5 dynamic ordering
(needs persistence decision). Owner decision, attended session
2026-11-23. No additional owner rationale was supplied beyond:
fallback is a core feature and top priority; major restructuring is
acceptable if needed.

## Problem

Run 3cf57c68 (2026-11-23) walked codex:usage_limit -> gemma:usage_limit
-> kiro/auto:finished and died, with 10+ ready routes unused (copilot,
antigravity-flash, opencode-go, ...). The drain then failed every run
for hours on the same chain. Three stacked defects:

1. Recognition: Kiro on monthly cap exits 1 with empty channels and no
   cap text. `external_usage_limit()` matches stderr markers only, so
   the failed result recorded "finished" and stopped the tree.
2. Interpretation: allowance observations are recorded but never acted
   on. Kiro at 100% plan consumption reported status "available" and
   was fully admitted; the readers deliberately "never infer a
   remaining balance" and nothing downstream interprets either.
3. Fragmentation: fallback logic spans FallbackSession, marker lists,
   Mai predicates, the drain retry wrapper, pause states, plus the
   unwired relay composition (`relay_inference`, zero callers).

## Options considered

| Option | Benefits | Costs and risks |
| --- | --- | --- |
| A: repair kiro only | Smallest blast radius; unblocks drain now | Next silent-cap client reopens the hole; fragmentation untouched |
| B: one verdict pipeline in ai_provider | Single decision point; fixes the whole silent-cap class; bounded blast radius; reusable inside C | Touches the execution hot path; needs one verified assumption per client |
| C: full restructure, one fallback executor | Principled end-state; eliminates seams | Large; touches Mai + drain + relay at once; highest regression risk |

## Decision

B now, C as the declared direction. A is a bandage on a principle
violation. C without B's verdict taxonomy risks rebuilding the same
seams in a new shape.

## Scope B implementation (6d95caa)

- `classify_external_result()`: success / usage_limit / model_overload
  / capability / route_failure / genuine_failure. Signal markers win
  over work evidence; stdout still never inspected.
- Zero-work failure (nonzero exit, 0 events, no answer) falls through
  as `route_failure`, retiring the route but never its billing bucket
  (new `failed_routes` set; new candidate exclusion).
- `allowance_exhausted()`: verified per-source interpreters (kiro:
  covered>=plan means consumed, empirically settled 2026-11-23).
  Verified-exhausted routes are skipped without executing
  (`allowance_exhausted` attempt status). Unknown sources never block.
- Genuine mid-work failures stay terminal (no spend multiplication).
- Relay composition kept: it belongs to the accepted Mai-container
  placement (`mai-container-full-fallback.md`); scope C absorbs it.
- Trigger-matrix expectations for no-marker/stdout-only cases updated
  to `route_failure` as the approved contract change.

## Consequences

- The 3cf57c68 shape now completes on a healthy route (covered by
  `test_silent_cap_falls_through_instead_of_recording_finished`).
- New attempt statuses `route_failure` / `allowance_exhausted` appear
  in run reports; closeout renders them opaquely.
- Scope C backlog: inbox `b58f8502` (blocked by B, inbox `0da81197`).
