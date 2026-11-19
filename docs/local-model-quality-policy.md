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

- `deepseek-coder-v2:16b`: BLOCKED. Two independent grounds: (1) no
  tool-call support — registry capabilities are completion+insert only
  and a live `/api/chat` tools call returns clean 400 "does not support
  tools" (confirmed 2026-11-18 and 2026-11-19); unusable for agent work
  regardless of other quality. (2) Q4 instruction-following claim 4/5
  fail, raw evidence missing (see re-probe note below). Re-test the
  instruction dimension only on new weights with a recorded probe; the
  tools verdict needs no re-test short of a new model release.

### Re-probe admission check — 2026-11-18

Run `40ba79a98efc4112986c24fbc178c5eb`: **BLOCKED before inference**;
the existing model block remains. This is not a new quality-test failure.

- Live `GET http://127.0.0.1:11434/api/tags` reported
  `deepseek-coder-v2:16b` manifest digest
  `63fb193b3a9b4322a18e8c6b250ca2e70a5ff531e962dbf95ba089b2566f2fa5`,
  size `8905126121`, quantization `Q4_0`, and modified time
  `2026-09-21T00:36:27.0710143+02:00`. The timestamp predates the
  2026-11-09 blocked run; it does not establish new weights. The digest
  identifies the current manifest, not an independently hashed weight blob.
- The private `docs/plans/local-model-queue.md` Q4 entry records five
  fixed instruction prompts, mechanical grading, and four failures, but
  references `C:\Users\Jakub\AppData\Local\Temp\q4-deepseek.json` for
  evidence. That file was absent at inspection. Neither this policy nor
  that plan supplies the exact five prompts, graders, inference settings,
  or blocked-run digest. Targeted repository/history searches did not
  recover the original probe or digest.
- Consequently, changed weights cannot be verified and the same probe
  cannot yet be reproduced. No model-inference calls were initiated by
  this re-probe's tools. No replacement probe was substituted.

Next: recover the original Q4 probe/settings and blocked-run weight identity,
then verify a different installed weight identity before admitting a fresh
bounded five-task run. Routing is unchanged by this documentation update.

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
  deterministic local work — confirmed same task in 547 tokens
  (6.4× cheaper than gpt-oss's 3530). The LENGTH→TruncatedOutputError
  guard fires correctly on empty-on-length — that is its job,
  not an adapter bug. No per-model multiplier change on one
  sample; re-probe before tuning.

## Fleet tool-call support (verified 2026-11-19, `ollama show`)

- `qwen2.5-coder:14b` (9GB): completion + tools + insert. The in-fleet
  coder replacement for deepseek; already the policy pick for
  deterministic local work.
- `qwen3:14b`, `gpt-oss:20b`: completion + tools.
- `deepseek-coder-v2:16b`: completion + insert only, no tools
  (registry + live 400, twice). Out for agent work.

Upgrade candidate: owner approved **Devstral Small 2** (`devstral-small-2:24b`)
pull and bounded local probe on 2026-11-19 (inbox `6750ebd4`, option B), to
compare it with Qwen on the workstation GPU. This does not approve promotion.
The older `devstral:24b` alias is a different release. Artifact size alone
does not establish 16GB VRAM fit or context headroom.

Run `09dcad608b854c25a0c92ce2ec5d4d43`: **INCOMPLETE before inference**.
The one-shot allowance was one pull (20 minutes), then at most six local
calls per model within 15 minutes, with 4,096 context and 512 output tokens.
The pull reported approximately 4.7 MB/s and 53 minutes remaining, so the
owned pull process was stopped early rather than extending the active bound.
This was an operator feasibility stop, not a registry or model-quality failure.
No inference phase was reached by the probe script. Installed inventory after
the stop and local receipt are required evidence; partial download data may
remain in Ollama's cache. Do not remove shared blobs to clean this trial.

Next: use a fresh, explicitly declared download allowance sized for the observed
transfer rate, then pin the installed manifest digest and run structured tool
round-trip, sandboxed edit checks, latency and actual GPU/context residency
checks against Qwen. The prepared synthetic micro-probe is not representative
quality acceptance; broad routing requires the existing evaluation policy.
Qwen remains the policy baseline while Devstral's local quality is unknown.

## Upgrade research closeout - 2026-11-19

Owner answer to inbox `a8739354c7694e4a9190778d0d7c2a47`: C, research
more; also remove the unused DeepSeek model. Research is complete; no pull
or routing change is approved. See the dated [source-state comparison](../packages/ai_provider/docs/source-state.md#local-agent-model-research---2026-11-19).

Correction: `devstral:24b` is the May 2025 release, not the newest Devstral.
Its 14GB artifact size does not establish usable context headroom on a 16GB
GPU. The advertised 128K context is a model limit, not measured local capacity.
Retain installed `qwen2.5-coder:14b` for the existing gated work. Recommend
considering a bounded Devstral Small 2 probe only after a separate owner pull
decision; published benchmarks do not establish local quantized agent quality.

Cleanup: `ollama rm deepseek-coder-v2:16b` succeeded on 2026-11-19;
subsequent `ollama list` showed only gpt-oss:20b, qwen3:14b and
qwen2.5-coder:14b. Removed model's prior listed size was 8.9GB; actual freed
filesystem bytes were not measured. Historical blocked-model evidence above
is retained and does not describe current installation.

Same-day update: the owner then approved option B (Devstral Small 2 pull +
bounded probe) in inbox `6750ebd4`; current probe status is recorded under
Upgrade candidate above, not in this research section.

## Review triggers

Re-run the 24-task harness when: new local weights land, a new
model joins the fleet, or leak rate on gated tasks exceeds 5%.
This doc changes only on fresh harness evidence.
