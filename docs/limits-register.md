# Limits register: hardcoded inference and budget caps

Owner-authorized 2026-11-02 after the L3 ladder showed both Meta-family models
truncating T3 at exactly 4096 output tokens (graded FAIL, full price paid).

## Principle

Caps exist to bound cost, latency, and runaway loops — but a cap set below
what the task needs does not save money: it buys a failed run plus a rerun at
a higher cap. Set inference caps from **observed usage plus headroom**, prefer
**overridable parameters over literals**, and record every change here with
its evidence.

Review trigger: any live run whose output tokens exactly equal the cap is a
truncation suspect — raise the cap (or add an override) and update this file.

## Inference output caps

| Location | Value | Purpose | Verdict |
|---|---|---|---|
| `route_eval` T0 | 1024 | 3-line completion | Keep — observed ≤487 |
| `route_eval` T1 | 4096 | 2-function module | Raised 2026-11-02 (was 2048; dots T1 hit the cap exactly). Re-probe PASS at 1173 tokens. |
| `route_eval` T3 | 16384 | 3-function spec build | Raised 2026-11-02 (was 4096; live truncation evidence). Meta passes at 3566. Baseten fills 4096/16384/32768 alike (unbounded verbosity, capability FAIL) — default stays, no further raise. CLI override: `--max-output-tokens T3:N` |
| `route_eval` T2 | 2048 | 1-function repair | Keep — observed ≤1275 |

| `native_admission` kimi-k2.7-code default | 16000 | Reasoning + answer share one allowance | Keep — owner-approved default; revisit if the model changes |
| `native_admission` unset-cap fallback | min(8192, context//4) | Adaptive default when no cap given | Keep — adaptive, not fixed |
| `AIRequest.max_output_tokens` default | None | Provider default applies; admission sizes it | Keep — neutral contract |
| `repo_coding_assistant` emergency preservation | 2000 | Bounded failure handoff | Keep — short by design; truncation loses handoff text, acceptable for an emergency path |
| `scrutiny_workflow` research reviewer | 1200 | Local-only review turn | Keep — latency-motivated; local inference is free, so raise freely if reviews truncate |
| `mail_digest` summary | 2048 | Email-sized digest | Keep — sized to the medium |
| `baseten-supervised-develop`, `plan-with-supervisor`, `unattended-development-loop` | 16384 | Coding-sized outputs | Keep — repo convention for coding work |
| `baseten-synthetic-acceptance` | 128 | Synthetic acceptance probe | Keep — intentionally tiny probe |

## Loop and grading bounds

| Location | Value | Purpose | Verdict |
|---|---|---|---|
| `mcp_server` delegation | 8 iterations / 180 s | Bound delegated MCP loops | Keep — overridable parameters |
| `route_eval` candidate grading | 2.0 s wall-clock | A grade must always resolve | Keep — timeout grades FAIL, worker stays daemon |

## Deliberately out of scope

- Socket, process, and HTTP timeouts: liveness bounds, not inference economics.
- `tests/integration` small caps (8/256/512): intentionally tiny live probes.
- Context-window declarations in catalogs: provider facts, not our caps.
