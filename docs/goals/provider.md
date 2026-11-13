# Provider-Agnostic AI Infrastructure

## Goal

One neutral contract for all model access (chat, streaming, tools, usage
metadata), with provider quirks isolated in adapters. Local/cloud switching
through configuration; no app code touches provider APIs directly.

## Non-goals

Task routing, model picking for a job, prompt judging (orchestrator). Agent
loop behavior (agent-cli).

## Owner

Jakub.

## Health

on-track — adapters green, streaming shared via `consume_stream`, local-model
quality policy v1 in force.

## Connected plans

- `docs/plans/local-model-quality-policy.md` (dropped; superseded by
  `docs/local-model-quality-policy.md`)
- `docs/plans/local-model-pilot-20261112.md`
- `docs/plans/model-capability-data-plan.md`
- `docs/plans/research-token-count-prototype.md`
- `docs/plans/search-tooling-landscape-note-20261022.md`

## Next action

Feed open question 2/3 outcomes into `model_catalog.toml` when decided.
