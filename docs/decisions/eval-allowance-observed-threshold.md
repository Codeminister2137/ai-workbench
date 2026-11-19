# Eval allowance budgets: observed stop threshold

Status: Accepted, owner answer B in inbox `5a326594ab884271b7a431b9998adb47`,
2026-11-19. Supersedes the strict-ceiling interpretation of the proposed
10% budget in scope item `bd5fa3a29bb143669ea084f5ef49f218`.

## Decision

Treat 10% of each allowance bucket per cycle as an **observed stop threshold**,
not a guaranteed consumption ceiling. Run sequential bounded calls with fresh
native observations before and after each call. Stop on missing/stale readings,
threshold attainment/crossing, changed windows/reset cycle, or uncertain accounting.
Count shared product usage conservatively; it cannot reliably be attributed away.
No metered spend, autonomous launches, floor changes or new provider access is
approved. Product headroom remains a requirement.

The owner explicitly accepted overshoot risk. No further rationale was supplied.
A single call, delayed provider reporting, or concurrent product usage can exceed
10% before detection. A fresh native request does not prove instant provider data.

## Alternatives

Strict pre-call upper bounds (prior recommendation) preserve a hard ceiling but
exclude percentage-only routes without defensible request bounds. Observed
thresholds (chosen) permit those routes to be sampled but cannot guarantee the
ceiling or precise attribution. The owner's selection is authoritative.

## Implementation and boundaries

`ai_provider.eval_threshold.ObservedEvalThreshold` wraps one bounded operation
with pre/post reads, counts percentage-point increases from the cycle baseline
across every supplied window, and latches failures. Acquisition exceeding the
caller's explicit freshness duration is rejected. The reader must issue fresh
requests and supply every applicable account window; cached readings are invalid.
The caller owns operation bounds, account exclusivity, provider admission, cycle
baseline retention and product priority. Do not recreate a guard for each call.
A reset/decrease requires review and a new cycle baseline, never an implicit refill.

This is a deterministic guard for the future eval runner, not a scheduler or a
persistent cycle ledger. The broader approved P1-P3 work in the private
`docs/plans/eval-scheduling-20261119.md` remains INCOMPLETE and its source stays
open. That runner must retain/recover accounting across jobs and restart or fail
closed before enabling allowance calls. No live evaluation is performed here.

Proving checks cover below-threshold admission, shared usage reaching exactly
10%, accepted post-call overshoot, failure latching, all-window enforcement,
missing/invalid/expired/slow reads, cycle changes, decreasing usage, reentrant
call rejection, and post-call observation after operation failure.
