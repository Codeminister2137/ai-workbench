# Current task - ATTENDED; hybrid runner implemented, live result qualified

Branch: develop. Latest production code: c6c2f34; handoff commit follows.
No active inference job, local server, timer, sleep or unattended window.
Owner-authorized logical commits and push to develop remain in scope.

## Owner authority and current policy

Keep auxiliary review and scrutiny local for now (ADR-025). A wholly paid-tier
workflow is permissible only after evidence establishes local-model inadequacy.
Local token economy is secondary to sufficient context, output and time; retain
finite run/cleanup bounds, count every role and report hosted usage separately.
The two local controls below support retaining local models, not escalation.

Standing comparable bounded Go acceptance authorization remains; owner confirmed
Extra Usage disabled. No paid overage, unbounded retries, model/billing switches,
new private payloads, raw-prompt/private-reasoning logging or credential exposure.
Native Go Kimi default is 16000 output tokens before admission; explicit caps win.
Existing endpoint: https://opencode.ai/inference/go/openai/v1/chat/completions.
Fresh synthetic fixture tasks/source/tests, committed AGENTS and their execution
history were used; no private plans or .env values were transmitted/logged.
Actual account remaining quota/dollar cost were not observed. Closeouts begin
with exact ## **SUMMARY** and Changed/Validated/Notes bullets.

## Completed implementation and validation

7ba21ef records owner local-first and conditional escalation policy.
e2936f6 closes run-store SQLite connections after commit/rollback; two regression
cases failed before repair. 89 focused checks passed.
107c17d supplies bounded native read/diff/test receipts to scrutiny, including
read-only phases with no changed-file excerpts. 85 focused checks passed.
c96cc92 renders a leading duplicate model SUMMARY as Agent summary, retaining
raw saved response. c6c2f34 fixes bold/empty Changed-label preview and clarifies
host database/log bookkeeping in existing final-response instructions.
Latest 56 focused checks passed. Full suite after final code commit:
2801 passed / 9 skipped in 238.94 seconds; receipt
artifacts/hybrid-preview-bookkeeping-full-suite-20261024.log.
Earlier code/handoff push gates passed through 6885708; final push follows.

## Consumed live evidence - do not replay or rewrite verdicts

artifacts/cli-baseline-hybrid-successor-20261024c/: FAILED private acceptance.
16 calls (12 Go, 4 local), 22 tools, 272.46 seconds. Source/tests and oracle
passed; frozen-review scrutiny lacked actual read/diff/test receipts, requested
revision, and private acceptance stopped. Both runtime and worker cleanup passed.
Original reports/logs preserved. This wrapper stop was not a Go service failure.

artifacts/local-scrutiny-evidence-20261024d/: fresh local-only diagnostic,
2 real GPT-OSS calls, 65536 context / 16384 output, 66.08 seconds. Supported
candidate passed (9/10); synthetic 99-tests/hash-verification claim required
revision. Original fixture remained unchanged; cleanup verified; no paid calls.
This does not regrade c or establish a general truth guarantee.

artifacts/cli-baseline-hybrid-successor-20261024e/: fresh frozen HEAD 6885708.
313 guard tests, scripted production workflow, independent audit and owned launch
smoke passed before live. Existing coding-chat --orchestrated completed coding
and frozen review: 15 calls (11 Go primary, 2 local auxiliary, 2 local scrutiny),
19 tools, 328.19 seconds. Both phases ran 10 tests: 5 originals preserved, 5
meaningful companions added. Independent 3616-case oracle, raw saved-report
continuity, model-only writes, frozen review and owned cleanup all verified.
Usage: Go 215382 input + 5447 output; local 40492 input + 5771 output tokens.
Independent mechanical/substantive evidence:
artifacts/hybrid-live-assessment-20261024/assessment-e.json and substantive-e.json.

## Remaining limits / next independent acceptance scope

Runner implementation and this bounded coding/review question are handled.
Clean report fidelity remains qualified: model reports call run/session DBs
unrelated and unchanged, although the host created/updated them. Do not interpret
local pass verdicts as automatic semantic correction. New c6c2f34 instructions
clarify this, but their model adherence has not had another paid acceptance run.
Post-trial current-render files are labelled host re-renderings, not original
model delivery. Original e completion and c failure remain unchanged.

Broader baseline/general quality parity is not established. For a future fresh
baseline slice, verify bookkeeping attribution and/or fallback under a concrete
new bounded question; do not repeat paid coding merely to reproduce this result.
Live fallback and scrutiny-fed repair were not exercised by e (offline checks
cover repair composition). Keep all original-test/frozen-review/history/cleanup
protections and local support. No current owner decision blocks the implemented
runner. Five matcher disagreements remain unapplied: ask before changing mapping.
Relevant private plans remain repo-assistant-cli-parity-plan.md and
opencode-go-integration-first-20261022.md; old unattended plan is CLOSED.
Historical continuity trials and earlier failures remain in docs/session-history.md.
