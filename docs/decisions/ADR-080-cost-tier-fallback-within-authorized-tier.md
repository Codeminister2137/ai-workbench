# ADR-080: Cost-tier fallback walks within the authorized tier, never above it

Status: Accepted by the owner, 2026-11-02.

## Decision and intent

When reaching a model fails (transport error, account refusal, provider-edge
refusal), the ladder and future routed work try the next candidate **within
the already-authorized cost tier**: free routes walk every resolved candidate, paid routes walk 3 unless the run raises the cap, and two consecutive parked (account-level) refusals stop a route — instead of
stopping at the first failure. Stopping and reporting stays an option only
where continuing risks ballooning cost.

Cost tiers are never escalated without explicit owner approval: a run
authorized for allowances must not silently spend paid credits, and a free
run must not silently become a paid run. The run declares its allowance
upfront (ladder: `--allow-tier`, default `prepaid_credits_allowed`); every
route has a ceiling tier; routes above the allowance are recorded as
`tier-blocked` and never attempted. Free routes additionally never resolve
paid candidates, matching the provider guards that refuse rather than fall
back to a paid model.

Owner rationale (2026-11-02): on failure the useful question is "what
benefits the user — stopping and reporting, or reaching a different model
and continuing the requested task?" Continuing within the authorized tier
is the common answer; the stop condition is ballooning-cost risk, and tier
escalation always needs approval.

## Mechanism and policy split

- Mechanism (`ai_provider.route_eval`, no policy): `run_candidate_ladder`
  attempts an ordered candidate list until one model returns a gradeable
  answer, recording every attempt — error rows for skipped candidates, a
  `no-model` skip for empty lists. A graded FAIL counts as reached (the
  model was measured); only transport/refusal errors advance the walk. The
  walk never substitutes its own picks. Two consecutive parked errors end the walk
early (`PARKED_STREAK_LIMIT`); CLI `--max-candidates 0` walks everything resolved.
- Policy (`scripts/l3_ladder.py`, caller side): resolves candidates through
  `recommend_model` over the orchestrator catalog (selected + alternatives),
  applies the tier gates above, refreshes free routes from live $0-verified
  listings minus recently-failed models, and pins paid/grant routes to
  catalog entries (unknown paid models are never auto-tried).
- First-row live-list auto-pick (`select_model`) is retired: it produced the
  Nov 1–2 failures (OpenRouter 503, Requesty-Novita 403) and cannot express
  tier policy. The provider layer keeps only the $0-discovery helper
  (`list_free_candidates`).

## Cost scheduling (roadmap input)

Model checking/evaluation follows cost: free routes are tested immediately
and before catalog refreshes; paid routes stay deferred until an emergency
or an explicit grant (extends the P2 source-onboarding runs and P5
emergency-spend: expiring-soon credits count as free). Evidence-to-quality
feedback (L3 verdicts updating catalog quality priors, so proven models
outrank unproven high priors) is accepted future P2 work, not this slice:
today catalog order still leads and measurement only records.

## Consequences

- Ladder runs need `--allow-tier` thought once (default prepaid covers the
  current five routes: free, allowance, and grant/prepaid entries); lowering
  it visibly skips routes instead of silently spending.
- The example catalog must keep ≥1 entry per eval route with honest tiers;
  this ADR ships with Baseten-hackathon, OpenCode-deepseek, Requesty-nemotron,
  and OpenRouter-dots entries, all provisional and evidence-noted.
- `route_eval.main` requires `--candidates`; ad-hoc runs go through
  `scripts/l3_ladder.py`, which writes a `ladder-resolved-*` audit record
  beside each snapshot.

## Scheduling (owner, 2026-11-02)

Full sweeps (notably free walk-all runs) do not run on a daily schedule:
quota burn without a question behind it. Allowed triggers: explicit owner
request, new-model onboarding events, or P5 emergency mode (near refresh
with remaining balance to burn, never promoting to prepaid). The default ladder
stays capped; `--max-candidates 0` is an explicit per-run choice,
never a standing schedule.
