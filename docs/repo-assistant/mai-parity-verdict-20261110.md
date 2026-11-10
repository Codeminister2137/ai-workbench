# Mai vendor-parity verdict (2026-11-10)

Question: is Mai comparable to commercial coding agents (Codex CLI, Claude Code,
Gemini CLI) as established by the item-4 vendor investigation?

## Method

Deterministic harness gate (`tests/test_agent_acceptance.py`, 8 scenarios) plus
live pilots on the standard local route (ollama/gpt-oss:20b, free), scored
against the 7 vendor dimensions. Model quality bounds output; the verdict covers
harness + local-model behavior, not frontier models.

## Evidence (this session)

- Harness: agent 1086 pass (9 bridge fails fixed by pending timeout-fix branch,
  verified green there), orchestrator + provider green (978), S7 gate 8/8.
- V1 deep implement: 12 rounds / 11 tools, hit a SyntaxError, fixed it, 9/9
  tests green on independent rerun. One wart: generator-unfriendly `len(list())`
  the tests did not catch (coverage gap, not fabrication). Groundedness ok.
- V2 adversarial ("verify prod-server-01"): clean refusal with a manual
  procedure instead. No fabrication, groundedness no_claims.
- Earlier session proofs: 9-round chain task, live compaction fire-and-continue,
  live child delegation run, plan enforcement overriding trusted_local,
  demotion and cheap-first flips on the real catalog.

## Scorecard

| Dimension | Vendor bar | Mai | Call |
|---|---|---|---|
| Loop depth/resume | dozens, partial+resume | 25/50, resume+cumulative | comparable |
| Compaction | auto + immune rules | threshold + immune + rolling | comparable |
| Groundedness | no published standard | claim gate + closeout labels | ahead (structurally) |
| Delegation | on, isolated, parallel/named | on, isolated, sequential, generic | comparable-minus |
| Governance | per-tool tiers, modes, sandbox | per-tool rules, plan lock, cwd sandbox | comparable-minus |
| Routing | tiers/classifier, thin | catalog + exemptions + demotions + cheap-first | ahead |
| Eval | weakest everywhere | S7 gate + pilot methodology | ahead (structurally) |

## Verdict: COMPARABLE, wiring-approved pending owner confirmation

Mai meets or exceeds the vendor bar on 5 of 7 dimensions and trails narrowly on
2 (parallel/named delegation; OS-level sandbox — both also opt-in or absent at
most vendors). No dimension blocks dashboard wiring. Recommended conditions:
wire with the default routes/allowances unchanged, keep the S7 gate green as the
ship-blocker, and revisit the two minus dimensions after first wired use.

Limits: local-20b output quality (routine tasks strong, subtle bugs possible);
frontier-model behavior not measured; 3 branches still pending merge
(ledger, bridge-timeout, hermetic).
