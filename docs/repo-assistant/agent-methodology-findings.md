# Agent methodology findings and research sources

Recorded 2026-10-14. This is a reusable engineering review and research seed,
not a model ranking, availability guarantee, or instruction to run inference.
Source claims must be rechecked against current official documentation and the
exact hosted route before implementation. Historical failures remain evidence.

## Findings to retain

The owner clarified on 2026-10-16 that ordinary Python constructs belong in
CLI parity evaluation. A synthetic fixture rejected `int()` before execution
because its handwritten language allowlist was too narrow; that was not a
production CLI permission restriction. Fresh fixture preparation accepts public
builtins and standard numeric/string/container methods while retaining its
no-I/O task scope, protected tests, approval/privacy rules and frozen review.
AST inspection is a task check, not an OS sandbox; the production command
runner's workspace working-directory check is not OS isolation either.
Preserve consumed failures and distinguish offline validation from live quality.

The native model/tool/observation loop follows conventional agent architecture.
A new agent framework is not needed to address the identified gaps.

| Finding | Evidence and limits | Engineering implication |
| --- | --- | --- |
| Gateway, model and upstream availability are separate | A direct Gemma request returned upstream throttling; other free routes answered small requests. Neither establishes enduring availability or coding quality. | Investigate alternate models/upstreams before making a provider-wide claim. Separate access checks from quality evaluations. |
| Ordinary history and provider continuation are different | Synthetic compatible-adapter inspection preserved tool IDs/arguments but did not capture or replay provider continuation. Ordinary loop history was retained. | Test the exact route contract using ADR-055's transient, origin-bound state and admission/logging protections. Missing continuation is not a proven cause of the observed repetition. |
| Effective model settings are unknown | Requests omitted sampling settings; NVIDIA and Cohere model cards recommend explicit settings. Native template options are not automatically gateway options. | Record matched, unmatched and unknown settings. Verify hosted support before changing payloads. |
| The strict pilot under-observes iterative recovery | Edit phases prohibited tests before independent host inspection; the first failed host check stopped the run. | Retain this safety evidence and add a distinct bounded edit/test/repair evaluation. Do not reinterpret failed strict trials as successes. |
| Structural inspection is not substantive plan acceptance | Initial requirements deliberately conflicted with a protected test; later correction resolved them. Some model planning claims were inaccurate despite passing structural gates. | Report structural and semantic outcomes separately; use a clear-task baseline as well as correction/freeze stress tests. |
| Repeated reads indicate lack of progress, not its cause | A correct source edit was followed by unchanged companion reads until the per-turn cap; required companion tests/review were incomplete. No observed API/tool validation error explains it. | Start with offline trace diagnosis. Warning, stopping and recovery behavior need separate policy decisions. |
| Normal CLI usage is not cumulative | The final response's usage was reported; intermediate metered calls were missing from normal turn totals, especially on failure. Independent pilot receipts retained the totals. | Distinguish per-response metrics, cumulative known sums and incomplete coverage. Missing usage/cost remains unknown. |
| Tool usability and attention need evaluation | Literal reads and edits worked in the observed runs; the required instructions, schemas and history were retained. | Evaluate clear tool feedback and current-task signals rather than removing required context or adding infrastructure. |

One small failed task per model cannot establish relative quality. A successful
connection or arithmetic response is not a coding-agent acceptance result.
Use independent checks of authored effects, protected inputs, substantive review,
numeric usage evidence and verified cleanup.

## Accepted direction and remaining boundaries

The owner accepted the recommendation on 2026-10-14: begin with offline exact-route
adapter/settings conformance and numeric usage reporting; retain the strict
authoring/correction/freeze evaluation and add a separately labelled bounded
iterative-development acceptance. Baseline CLI remains the priority; independent
unattended supervision remains the next established priority after baseline CLI.
Later research should inform these goals, rather than displace them.

The acceptance method is approved in principle. A concrete new live trial still
needs fresh inputs, explicit attempt/per-turn/time/tool bounds, permitted repair
conditions, independent final checks and owner grant/readiness. Consumed grants
cannot be reused. This record does not authorize reasoning logging, relaxed
privacy guards, paid fallback, a dependency, scheduler activation or promotion.

## 2026-10-15 evaluation follow-up

The scoped OpenRouter continuation/accounting changes are implemented offline.
A fresh bounded iterative run repaired source and passed its original tests, but
exhausted eight edit calls before companion tests, a final report or frozen review.
Its later host oracle pass is diagnostic only; acceptance remains failed.

The owner approved preparing a fresh 16-edit/4-review trial and requested an
alternative to repeated hard iteration cutoffs without allowing indefinite loops.
The owner subsequently approved attended stall checkpoints and flexible phase
allocation. An isolated acceptance harness now pauses before another provider
call on repeated unchanged reads or repeated failed tests at the same file state.
It reuses the existing deadline-bound terminal approval channel; no answer closes
the run, and a late approval cannot renew the grant. No-op edits and A/B/A state
oscillation do not erase the observations. That experiment did not select
automatic recovery; the subsequent accepted default is recorded below.

One total resource envelope and a serial-review reserve replace independent phase
call caps for this experiment. Deterministic checks cover serial inspection/repair/
review, checkpoint refusal, history/continuation preservation, expiry and cleanup.
Separate acceptance outcomes distinguish resource exhaustion from correctness,
provider and safety failures while preserving raw CLI status and strict historical
outcomes. Privacy/authorization guards, independent acceptance and fresh live
grants remain required. This test harness does not change normal CLI defaults or
establish live quality, unattended checkpointing or general anti-loop coverage.

The subsequent approved live trial stopped on an exact-text edit mismatch before
any checkpoint: the anchor contained an extra blank line and no edit was applied.
Owned cleanup was verified, and the grant is consumed. The owner subsequently
approved ordinary error recovery by default; the failed run must not be
relabelled or resumed. Its uncaught host exception exposed a separate usage-footer
gap, now repaired without changing execution failure or acceptance semantics.

### Accepted recovery default and slice-level stalls (2026-10-15)

The owner approved ordinary tool-use and test correction as normal iterative
coding behavior, rather than a one-anchor exception, to evaluate Codex quality
parity. Return actionable errors, preserve history and inspect actual effects
before repeating an operation that might have partially succeeded. Corrections
consume the existing total allowance; they do not gain a separate retry budget.
Retain strict safety/correction/freeze evaluation separately. Safety, privacy,
authorization, protected-file and frozen-review boundaries remain binding.

Detect repeated equivalent failures without relevant state changes or new
evidence, including no-op edits and state cycling. At an attended checkpoint,
request bounded continuation. During an unattended window, record the stalled
slice's evidence, effects, blocker and unlock condition, safely close its owned
operations and continue another useful approved slice from the wider plan.
Only a fresh review establishing all remaining useful authorized work complete
or blocked permits early closeout and the owner's applicable sleep policy.
Switching slices never renews a grant, deadline or permission.

Default recovery gives realistic development evidence and avoids truncating
recoverable mistakes; it can consume more allowance and requires progress
monitoring that may falsely flag a useful investigation. Report first-attempt
tool errors, recovery effectiveness, final correctness and total consumption
separately. First-error stopping remains useful strict diagnostic evidence,
but is not the default iterative coding acceptance criterion.

This is an accepted policy, not evidence that a new acceptance harness or
independent unattended supervisor is implemented. Existing production-loop
tests cover model continuation after a tool error; the consumed acceptance
harness stopped on non-test tool errors. Preserve that harness and its receipts.
Prepare fresh inputs/paths and explicit attempt/per-turn/time/tool bounds,
deterministically test recovery/stall/cleanup behavior, then seek a fresh live
grant. Ask readiness only for known required owner input. Baseline remains
INCOMPLETE; this decision authorizes no inference or general quality promotion.

## Interrupted-run closeout (2026-10-16)

Subsequent observations must remain distinct: one run captured a provider error
finish, another reached its coding-call ceiling without a report, and a fresh
unattended run stopped at the fixture-language guard before running newly edited
source. None establishes the cause of an earlier unobserved blank response.
Allowance and language restrictions must be explicit in the task, while complete
history and ordinary tool access remain available. Local disclosure tests do not
establish that the model will finish its report or review. Do not relax safety
checks or resume a consumed attempt to turn correct-looking effects into acceptance.

The integrated successor repaired its implementation and an incorrect new test
expectation, preserved original tests, and passed seven tests and the independent
bounded oracle. It produced no final edit report or frozen review, so integrated
acceptance failed. The provider finish reason and raw terminal response shape were
not retained; the cause of the empty normalized response remains unknown. A
separate history diagnostic stopped at the quota guard before any completion
request, providing no model response or usage observations. Consumed attempts
remain immutable; a daily allowance reset does not renew their grants.

Post-loop validation exposed a separate deterministic continuity gap: successful
loop return followed by CLI report rejection lost the transient conversation,
although earlier tool effects remained. The local fix carries complete loop
messages into these errors without changing their non-retryable classification,
replaying tools, logging raw history or adding another loop. Tests check retained
history, actual effects and representation privacy. This does not repair empty
model reports or establish live fallback quality.

## Source index for later research

Live-launch follow-up (2026-10-15): the approved attempt failed in a host metadata
worker before any completion/tool effects, with unchanged inputs and verified
cleanup. The original stderr/metadata observation is unavailable; this is not a
model-quality or service-availability result. A real Windows venv process test
exposed an intermediate Python launcher that violates the immediate-parent guard.
Fake provider replies alone had not exercised this live-only admission branch.
The separate repair retains job ownership, verifies controller birth and permits
only direct parentage or one verified Python-launcher hop. A no-network smoke
test must exercise the actual child process chain, guard and real seal checks,
with a local sink replacing the network operation. Preserve the consumed attempt;
do not infer that a zero-completion failure authorizes an automatic retry.

The subsequent approved attempt made 14 completions, repaired the source and
passed five visible tests, then stopped on a proposed tool outside fixture scope.
The receipt retained no tool name; its identity remains unknown. Preserve the
refusal and missing final report/frozen review as failed acceptance even when
poststop host tests and the bounded oracle pass. Record minimal rejected-tool
identity in future receipts without saving arguments or private continuation.

Poststop checks exposed another false-positive preflight gap: the oracle read
its original-test baseline from the now-edited live file. Scripted workflows in
separate workspaces left that baseline untouched and missed the defect. Verify
the prepared original snapshot against its manifest, then compare the final AST
against that immutable baseline. A regression must exercise added companions in
the same mutable fixture and reject changed originals/index content. Keep host
verifier failures separate from model correctness and missing model phases.

The next bounded run demonstrated ordinary recovery: a failed literal edit was
followed by reads of actual effects, a corrected edit and passing tests. It then
exhausted its 14-call coding allowance while six of 20 total calls remained
reserved for review. No final report or frozen review completed. Report a total
budget and its phase reserves together; a scripted batch of tool calls does not
predict a real model's call count. Preserve the failed run and seek a fresh owner
decision before increasing the allowance. Do not borrow the review reserve,
truncate instructions/history or weaken acceptance to make a small budget pass.

With the subsequently approved 24-call allowance, the edit/report phase passed
and frozen review reached all required tool observations before repeating reads.
Local replay reproduced the checkpoint after the third unchanged test-file read;
no tool/schema error explains this review stall. The original review deadline
expired before the owner's continuation could be applied. A later chat approval
does not renew an expired checkpoint or a consumed trial. Preserve that timing
separately from the model's repeated reads. Passing source/oracle checks and
completed review tools still cannot replace a missing substantive model report.

A separately authorized standalone frozen review subsequently completed with a
substantive report, required tool observations, six passing tests, no writes or
stall and verified cleanup. Independent inspection accepted this narrow result.
It used an explicit completion instruction and a fresh task without a coding
conversation, so it does not isolate the cause of the earlier stall. Carry that
instruction into a fresh integrated preparation while retaining all required
coding history; do not infer that history may be dropped or prior failures passed.

2026-10-15 offline implementation follow-up: fresh acceptance preparation now
returns ordinary tool/schema failures for correction, requires observing actual
effects before another write, detects equivalent failures at unchanged state,
and preserves attended continuation within the original envelope. Syntax feedback
does not execute uninspected code. The scripted full workflow passed independent
test inventory/oracle, substantive host review and owned cleanup; 80 combined
guard/progress checks and 207 existing fallback contract checks passed. This is
software evidence only. Strict historical evaluations remain separate and unchanged.

The owner subsequently selected context-aware observable-history transfer in
ADR-059, partially superseding ADR-032's counts-only handoff. Native coding routes
use full ordinary mid-turn messages/tool calls/results only with 20% destination
headroom after the complete input, tools, output and framing; otherwise use the
bounded handoff. Unknown effective capacity also selects bounded mode. This is
implemented offline, without provider-private reasoning transfer, raw checkpoint
persistence or changes to privacy/quality/billing/approval gates. External native
clients retain bounded mode while their full request remains unmeasured.
Independent unattended supervision remains after baseline parity.

| Source | Why retain it / question to revisit |
| --- | --- |
| [OpenRouter reasoning documentation](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens) | Returned reasoning exclusion differs from disabling generation; investigate documented continuation through tool turns and exact route requirements. |
| [NVIDIA Nemotron Super model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16) | Recommended sampling and coding-agent template settings; distinguish native capabilities from hosted free-route support. |
| [Cohere North Mini Code model card](https://huggingface.co/CohereLabs/North-Mini-Code-1.0) | Recommended sampling and benchmark harness/repetition methodology; benchmark claims are not local acceptance evidence. |
| [Cohere North Mini Code documentation](https://docs.cohere.com/docs/north-mini-code-1.0) | Current supported model behavior and integration guidance. |
| [Cohere tool-use patterns](https://docs.cohere.com/docs/tool-use-usage-patterns) | Normal multi-step tool/observation interaction and repair feedback. |
| [NVIDIA agent integration cookbook](https://github.com/NVIDIA-NeMo/Nemotron/blob/main/usage-cookbook/Nemotron-3-Super/OpenScaffoldingResources/README.md) | First-party agent configurations and pitfalls; recheck example aliases and allowances against the current endpoint. |
| [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) | Simple loops, environmental feedback and usable agent/computer interfaces. |
| [Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | Tool clarity and relevant current context; preserve required instructions while testing presentation. |
| [SWE-agent paper](https://arxiv.org/abs/2405.15793) | Study how interface design changes coding-agent performance; examine task sets, controls and transfer limits. |
| [LangChain/NVIDIA Nemotron Ultra harness study](https://www.langchain.com/blog/tuning-the-harness-not-the-model-a-nemotron-3-ultra-playbook) | First-hand study of trace-specific harness signals. Different model/harness; assess reproducibility and avoid fixture-specific prompt overfitting. No framework adoption implied. |
| [OpenClaw issue 86669](https://github.com/openclaw/openclaw/issues/86669) | Reported dropped template options and reasoning-only retry loops. A diagnostic clue, not a match to our successful tool calls or proof of our cause. |
| [OpenClaw issue 90982](https://github.com/openclaw/openclaw/issues/90982) | Reported hidden schema errors and retry loops. Our observed receipts had no such validation errors; inspect applicability before attribution. |
| [OpenRouter NVIDIA free endpoint metadata](https://openrouter.ai/api/v1/models/nvidia/nemotron-3-super-120b-a12b:free/endpoints) | Recheck current upstream, limits and supported parameters. Metadata is not a completion/access test. |
| [OpenRouter Cohere free endpoint metadata](https://openrouter.ai/api/v1/models/cohere/north-mini-code:free/endpoints) | Same route-specific checks; current official API outranks old catalog snapshots. |
| [OpenRouter status](https://status.openrouter.ai/) | Service-wide incident signals cannot prove an individual free route is usable. |
| [OpenRouter Downdetector](https://downdetector.co.uk/status/openrouter/) | User-report aggregation; useful corroboration, not a model-specific health oracle. |
| [Gemma model-status page](https://modelstatus.dev/models/google/gemma-4-31b-it:free) | Third-party route metrics; establish whether observations are independent or republished gateway data. |
| [Third-party OpenRouter free-tier probe](https://klymentiev.com/blog/openrouter-free-tier) | Historical cross-model access observations and linked data. Revisit methodology, timestamps and upstream isolation; arithmetic success does not establish agent quality. |

## Future research brief

Revisit these sources through the existing research workflow when it has an
authorized execution window and verified source/search grants. Produce a claim
matrix separating official contracts, study results, issue reports, local facts
and hypotheses. Record date/version, model, upstream, harness, settings, task set,
repetitions, controls, failure taxonomy and applicability to our implementation.
Keep contradictory evidence and identify what an offline check can resolve before
requesting inference. Select the smallest relevant experiment; do not install
software from examples or turn research into an automatic live model sweep.

The complete local review and immutable trial evidence remain separately preserved
in the private handoff/artifacts. This public-safe index contains no credentials,
raw prompts, private reasoning, account balances or machine-specific sessions.
