# AI Orchestrator

## Goal

Decide what to run and where: task classification, prompt judging, model and
route selection, fallback, privacy constraints, quota/economics awareness.
Neutral execution targets adaptable to any executor; core decides without
requiring `ai_provider`.

## Non-goals

Provider API handling (provider). Running tools or turns (agent-cli).

## Owner

Jakub.

## Health

on-track — routing, fallback and spend ledger shipped; R5-class UX work lands
in agent-cli.

## Connected plans

- `docs/plans/l3-eval-ladder-design.md`
- `docs/plans/l2-spend-program-status.md`
- `docs/plans/p3-workbench-routed-loop-scouting.md`
- `docs/plans/p5-spend-policy-proposal.md`
- `docs/plans/research-review-orchestration-plan.md`

## Next action

Owner call on open model-capability mapping scope (Go catalogue vs OpenRouter
free routes).
