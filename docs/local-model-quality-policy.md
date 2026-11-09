# Local-model quality policy v1 (2026-11-09)

Owner ask (loop8 Q1): know which tasks can run local vs routed,
and which fixes local models need. Evidence: loop10 Q1–Q4 queue
(4/5 deepseek fail, thinker truncation fix + live verify, Meta
effort behavior, 24-task dual-arm eval: local 13/24, grant 12/24).

## What local models can own today

- Deterministic transforms with mechanical graders (format,
  extract, classify, dedupe) — both arms ~50% suggestion leakage
  WITHOUT gating, so outputs must be mechanically gated
  regardless of arm. Gating is the policy, not the model.
- Short structured generations (intake parsing, titles, labels).
- Draft-then-verify loops where a checker (not a human) accepts.

## What must route to stronger models

- Long structured outputs from thinker models (Q1: qwen3:14b
  truncates past budget; 4× budget + `TruncatedOutputError` on
  LENGTH only contains it — route, don't stretch).
- Anything needing instruction-following past ~2 constraints
  (grant arm leaked at the same rate; complexity is the enemy).
- Customer-visible prose without a human pass.

## Blocked models (evidence-backed)

- `deepseek-coder-v2:16b`: BLOCKED (Q4: 4/5 fail). Re-test only
  on new weights with the same 5-task probe.

## Required tooling (shipped)

- `thinker_output_budget` + `ensure_complete` + LENGTH →
  `TruncatedOutputError` (ollama adapter).
- Mechanical output gates on every pipeline stage (Q3 lesson:
  "both arms ~50% leak" means the gate IS the quality).

## Routing rules for the orchestrator

1. Default local for gated deterministic work; route on: output
   length > thinker budget, constraint count > 2, or prior
   truncation on the same task shape.
2. Never silently retry a truncated thinker output on the same
   model — escalate arm or shrink the task.
3. Tiny budgets on grant models return length+empty (Q2) — floor
   budgets per model, never squeeze.

## gpt-oss:20b thinker finding (loop11 probe, 6 local calls)

- 30-item list task: 400 AND 1600 budgets → LENGTH with ZERO
  visible chars (1600 tokens all thinking, 6.1k trace chars).
  4096 → completes (3530 eval, ~3× thinking overhead, DONE).
- The 4× thinker multiplier is INSUFFICIENT for gpt-oss:20b on
  list-structured tasks (~9× needed here). `think: false` is
  NOT honored (Ollama 0.32.5, generate and chat APIs).
- Consequences: route long structured outputs AWAY from
  gpt-oss:20b; prefer qwen2.5-coder:14b (non-thinker) for
  deterministic local work. The LENGTH→TruncatedOutputError
  guard fires correctly on empty-on-length — that is its job,
  not an adapter bug. No per-model multiplier change on one
  sample; re-probe before tuning.

## Review triggers

Re-run the 24-task harness when: new local weights land, a new
model joins the fleet, or leak rate on gated tasks exceeds 5%.
This doc changes only on fresh harness evidence.
