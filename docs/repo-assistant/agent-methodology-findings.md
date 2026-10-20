# Agent methodology findings and research sources

Recorded 2026-10-14. This is a reusable engineering review and research seed,
not a model ranking, availability guarantee, or instruction to run inference.
Source claims must be rechecked against current official documentation and the
exact hosted route before implementation. Historical failures remain evidence.

## Findings to retain

### Orchestrated local trial — 2026-10-20

`cj` enabled actual continuous coding-chat orchestration with all support calls
inside finite bounds. It is consumed and failed: eleven HTTP200 responses
(ten coding, one auxiliary, zero scrutiny), ten tool calls, one successful source
write, three unchanged original tests and no companions. No tests, coding report,
frozen review or phase gate completed. Correctness is unestablished. Independent
postflight verified 152 sealed dependencies at `57a1358`, model-only effects and
cleanup of eleven owned children plus controller/runtime/listeners. It declined
source execution because the static companion-test requirement was unmet.

The private notice checker required one formatted notice and also counted every
occurrence of its label. A model grep for `Host trial allowance` echoed that label
in the search result, causing a false duplicate detection. Nine earlier notices
verified. The saved inner grep result plus an explicitly synthetic valid notice
reproduces this failure offline; the actual failing outer result was not saved.
The prospective correction removes only the broad label count, retaining exactly
one complete notice and the counter/time/conflict checks. The launcher then hit
a secondary filename collision with an earlier preparation-failure receipt.
Future receipts use exclusive unique filenames; the consumed receipts remain.

Separately, the tool-free auxiliary response falsely claimed source edits and
test execution, including companion tests that did not exist. It was displayed
raw, despite its role instruction prohibiting those claims. This is a material
accuracy defect, distinct from the private checker failure. Auxiliary text was
not passed into primary prompts; the saved phase candidate is not a primary final
report. Both auxiliary display paths now label the advice unverified and state
that this pass performs no edits/tests and supplies no completion evidence.
Raw advice is preserved; there is no semantic verification or automatic repair.
Scripted implement/continuous delivery checks cover qualification and separation
from primary/reviewer prompts, alongside actual validation subprocesses. These
checks establish presentation behavior, not live model detection or correction.

Observed usage: 174,640 input and 4,512 output tokens across all eleven responses.
Their sum is 179,152; reported total and cost were absent. No economics claim
follows. Evidence: ignored `artifacts/cli-orchestrated-integrated-20261019cj/`,
`artifacts/cli-orchestrated-postflight-20261020cl/` and prospective offline fixes
in `artifacts/cli-report-fidelity-repair-20261020cm/`. No replay, host code/report
rescue or promotion of an incomplete workflow occurred.

### Offline workflow calibration — 2026-10-19

Seven scripted cases exercised the actual orchestrated CLI validation,
repair/revalidation, scrutiny and final rendering paths. Fifteen boundary requests
were scripted; eight actual validation processes each ran three unittest cases.
No real model calls occurred. Auxiliary support was stubbed and prompt review
skipped. A separate read-only audit matched terminal reports, SQLite stages,
validation histories, source effects, protected tests/instructions and reference
hashes; all eight recorded validation processes were absent at postflight.

Actual failing validation triggered the existing repair loop, which accepted a
scripted correction and reran passing validation. Correct drafts, honest uncertainty
and harmless recovered friction produced appropriate final reports. Failed required
validation with an explicit incomplete report demonstrated containment, not task
completion; CLI return code zero alone is not quality acceptance.

The material gap is final delivery after scrutiny: a scripted reviewer explicitly
flagged an unsupported hash-verification claim and proposed a truthful revision,
but the final Changed preview and Agent report repeated the false claim. The earlier
warning and recorded findings establish detection; effective final qualification
or correction remains unestablished. A deliberately scripted reviewer miss left
the same false claim unqualified. This negative control does not estimate any
real model's detection rate; external reference checks are not CLI protections.

The owner selected explicit final qualification first because it is a smaller
delivery fix without additional inference. The CLI now shows concrete unresolved
findings or review failure beside the preserved draft, withholds an accepted
Changed preview, and labels proposed reviewer revisions as not applied or
independently verified. Scoped host validation remains separate. This contains
unresolved review without automatically adopting a correction or deciding every
finding is valid/material. Passing-review and no-review output remain unchanged.
Focused offline tests cover direct and orchestrated delivery, actual local
validation, malformed/unavailable review and a deliberate reviewer miss. Automatic
correction, a semantic grader, new review defaults and live detection guarantees
were not added. Preparation/receipts: artifacts/cli-workflow-calibration-20261019cg/
and artifacts/cli-scrutiny-delivery-20261019ch/; consumed results remain unchanged.

### Outcome-based acceptance reassessment — 2026-10-19

Owner clarified that a model mistake may be caught by scrutiny, the main model
or another declared workflow component. Evaluate the trustworthy final outcome
and meaningful validation; record the primary mistake separately. Harmless
recovered command friction need not be disclosed in prose, while an unsupported
claim of hash/test/diff verification is material. A clear stop is containment,
not successful completion. External evaluator detection does not by itself prove
the normal CLI would catch the issue. The canonical [acceptance criteria](acceptance-criteria.md)
include positive and negative calibration cases and retain all safety boundaries.

This supersedes using every recovered-error omission as a future usability gate.
It withdraws the immediate recommendation to introduce structured report
submission before assessing existing workflow safeguards. Historical `by`/`cc`/`ce`
results remain unchanged under their original rules. No production contract,
review default, live allowance or automatic report rewrite has been introduced.

### Owner-directed behavioral baseline — 2026-10-19

Later attended `cc`/`ce` evidence repeats the report-fidelity failure under coherent
instructions. The isolated diagnostic disclosed supplied synthetic facts but omitted
its actual refused search; the fresh integrated fallback produced independently
correct effects/tests/oracle yet omitted its recovered command refusal. The exact
coding report was rejected before frozen review. A predeclared independent report
gate contains false completion; it does not improve report authorship or replace a
missing second report. Full context/tool access and correct host metadata did not
establish faithful prose. Preserve the failures and avoid another blind prompt-only
trial or speculative generic grader. Public completion/report contract changes
remain owner decisions. See `artifacts/cli-report-fidelity-integrated-20261019ce/live-review.md`.

The fresh integrated `by` run completed both structural phases with independently
correct model-authored effects, but did not establish strict acceptance. Its
coding report omitted the required recovered-command disclosure. Postflight
also found two inherited blanket import clauses in the actual composed task,
despite the correct full root snapshot and approved typing inspector. The
preflight's check for one obsolete spelling did not detect these other clauses.
No imports were used, so this supplies no live typing exposure or causal gain.
Preserve the consumed evidence; clarify only the known stale clauses before a
future seal and check the complete composed task. Seventeen new offline regressions
include the actual counterexample. Do not turn structural report acceptance into
independent report approval or replace the model's report on the host.
Evidence: `artifacts/cli-typing-integrated-acceptance-20261019by/live-review.md` and
`artifacts/cli-instruction-coherence-20261019bz/README.md`.

The owner clarified that [AGENTS.md](../../AGENTS.md) and other applicable
repository instruction files are the behavioral baseline for our CLI agents.
Ordinary inspection, coding, testing and correction should have the same
owner-approved scope as Codex. This reinforces ADR-024's project-owned,
provider-neutral policy rather than transferring platform tools or credentials.
The existing context loader retains required root/nested instructions completely;
an additional check verifies the actual updated root file loads without truncation.

Pilot restrictions may simplify a question or contain effects, but must be
declared and justified before inference. Do not turn a convenient fixture rule
into a product restriction. The latest `typing` failure exposed such an overly
narrow rule: it is a scope-compliance failure under the original task, not proof
that the library is unsafe or the algorithm incorrect. The owner approved reviewed
standard-library imports for future fixtures. The consumed result is unchanged.

The prepared profile admits `import typing`, module aliases and explicit imports
of fourteen reviewed type names, including the failing `Iterable`, `Tuple` and
`List`, plus ordinary annotations/type aliases. It does not admit all standard
library modules, runtime typing helpers or calls on imported typing objects.
Existing no-I/O/reflection/original-test protections remain; AST checks are a
fixture check, not an OS sandbox. Local implementation and exact name list:
`artifacts/cli-typing-fixture-policy-20261019bw/README.md`.

| Behavioral baseline | Current arithmetic pilot deviation and purpose |
| --- | --- |
| Complete applicable instructions and observable history | Retain them; do not shorten them to save inference usage |
| Ordinary Python and useful standard-library code | Review typing expressions explicitly; other source imports/runtime helpers remain outside this small no-I/O fixture |
| Inspect, edit, test and correct within authorized bounds | Two editable files and exact test command contain effects; bounded ordinary correction remains available |
| Meaningful tests and honest validation | Protect original assertions and test-framework semantics; require companion tests and an independent oracle |
| Review based on observed changes and tests | Freeze writes during the review phase; require real reads, Git observations, test execution and a substantive report |
| Owner authority and actual approval policy | Label synthetic callbacks explicitly; they never supply physical approval, paid/privacy permission or new provider authority |

Before the next fresh live slice, compose the profile into a new controller and
verify its actual task text, worker/command guard, instruction snapshot, seals,
successful-observation gates and owned cleanup. Do not edit consumed harnesses or
infer a model-quality improvement from deterministic checks. The next unattended
session requires the owner's separate session prompt; it has not started here.

An extra pre-seal check caught a preparation-order error: the existing builder
intentionally snapshots committed `HEAD:AGENTS.md`, so a fixture prepared before
committing the instruction clarification contained the preceding rules. No
inference ran. Preserve that preparation, commit the approved instructions first,
and create fresh inputs with explicit committed/working/snapshot equality checks.

### Pilot methodology audit and next sequence — 2026-10-19

The fresh integrated continuation established a specific earlier-stage failure:
model-authored source imported `typing` despite the task's explicit no-import
scope. The fixture guard refused its phase-one test proposal before execution.
All nine responses were HTTP200; no live tests, oracle or reports completed.
Protected inputs, originals, sealed code, model-only edit attribution and owned
cleanup pass. An ordinary failed text replacement was successfully corrected
after an unnumbered reread. The shared review completion mechanism was never
reached; do not credit or blame it for this outcome. Correctness remains unknown.
Evidence: `artifacts/cli-integrated-completion-acceptance-20261019bu/live-review.md`.

The subsequent owner decision above supersedes retaining the blanket import ban
for future fixtures. The following investigation proposal records the earlier scope.
Before another integrated trial, reproduce this exact pre-execution refusal
offline. Investigate safe actionable code-conformance feedback while preserving
the no-import execution guard, original limits and hard protected-input/path/
reflection/approval boundaries. This is proposed follow-up, not an adopted change
to safety recovery. Retain a fixed originating rule in private closeout rather
than logging raw rejected content. Do not relax scope after observing a failure
or execute rejected source merely to obtain an oracle score.

A separate fresh frozen review passed with a true accepted report, accurate
notices and independently verified tests/oracle/cleanup. It used prior
model-authored input, so it does not establish new authorship or a full workflow
pass. No completion feedback was needed in that run; a causal improvement is
unproven. Evidence: `artifacts/cli-budget-notice-acceptance-20261019bt/live-review.md`.

Earlier diagnostic findings follow; their outcomes remain unchanged.

The approved standalone frozen-review diagnostic has now exercised the stronger
gate live. On independently validated prior model-authored input, the local model
used six of eight calls: both file reads, passing tests and Git status, but no
Git diff. It ended with a substantive report that incorrectly attributed the
copied implementation to current work and described an unobserved diff. The gate
correctly failed; independent tests/oracle, frozen inputs and cleanup passed.
This isolates a premature completion/report-accuracy problem with spare budget,
not review-cap exhaustion or an engine error. Model internal cause remains unknown.
Local evidence: `artifacts/cli-frozen-review-diagnostic-20261019bo/live-review.md`.
Before another live pilot, reproduce missing-check completion and unsupported
authorship/diff claims deterministically and inspect existing completion-feedback
points. Any correction must remain model-authored inside original bounds; a host
report, larger allowance or blind full-workflow repeat would not answer this case.
Material changes to loop/API/approval policy still require the owner's decision.
This review-only failure does not alter integrated acceptance or earlier results.

The owner questioned whether repeated pilots were producing actionable evidence.
An offline audit of six recent, heterogeneous runs found three independently
correct implementations, two verified coding reports and no complete acceptance.
Four runs did not exercise the mechanism their proposed change targeted. These
counts describe investigations, not a controlled model pass rate or a measured
quality improvement. See the local entry point
`artifacts/cli-pilot-methodology-audit-20261019bn/pilot-audit.md`.

The pilots have found real defects and limits: discarded diagnostic detail,
syntax admission mistaken for executed tests, repeated synthetic approvals,
fixture rules that prematurely stop ordinary correction, and inadequate review
headroom. However, changing fixtures and several controls between full workflows
does not isolate which change helped. A guard-test count is software evidence,
not model-quality evidence. Successful transport is not successful task execution.

Current official OpenAI guidance supports defining an objective, dataset and
metrics before comparison, evaluating workflow stages, and grading observable
traces against explicit criteria:
[evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices),
[trace grading](https://developers.openai.com/api/docs/guides/trace-grading), and
[lightweight agent evals](https://developers.openai.com/blog/eval-skills).
We apply these principles locally; no OpenAI evaluation service, SDK dependency,
data upload, private-reasoning logging or internal-Codex-equivalence claim follows.

Small improvements implemented offline now:

- A stage audit distinguishes correct code, report accuracy, review progress,
  intervention exposure and unchanged unknowns. Consumed receipts stay untouched.
- A stronger private review gate requires successful reads of both final files,
  successful Git status/diff and a successful executed test observation. Tool
  names alone do not suffice. Counterexamples demonstrate the old gate's gap;
  the existing scripted happy path already contained all required actions.
- Test-command refusal, syntax admission and reported execution are separate.
  Execution counts are cross-checked against owned test-child receipts.
- Provider-usage observation coverage is independent of workflow completion;
  missing totals remain unknown rather than becoming invented provider totals.
- The prepared failed-write feedback reports a fixed originating component and
  rule, without retaining rejected content or permitting a write before reread.

The strengthened controller and helpers are prepared and checked offline in the
same artifact root. They must be composed into a fresh live harness before they
can be claimed as live behavior. All existing acceptance requirements remain.

Next bounded sequence:

1. Before inference, write a short case card: one question, fixed case version,
   changed factor, trigger proving it was exercised, expected observations,
   independent checks, stop/falsifier, bounds and the action each outcome enables.
2. Use deterministic reproductions first. For remaining model questions, target
   the affected stage. The next live diagnostic should review a fresh, frozen,
   independently validated public fixture with meaningful diffs. This isolates
   tool-argument use, review headroom and report completion from coding failures.
   Mark it review-only; it cannot pass the integrated coding/review baseline.
3. Keep task content and settings stable across comparisons. Fresh paths,
   immutable snapshots and finite named allowances do not require changing task
   semantics. Record unavoidable differences and do not infer causal gains.
4. Every failed phase needs the failing operation/component/rule, actual effects,
   evidence, remaining unknowns, a smallest reproducer and a proposed correction.
   Distinguish the primary failure from a secondary controller closeout error.
   Exact historical rejected-command spelling remains unknown when discarded.
5. Return to a fresh integrated coding/test/report/frozen-review slice after the
   targeted diagnostic answers its question. Both substantive true reports,
   model authorship, unchanged protections/oracle and verified cleanup remain
   mandatory. Never resume a consumed allowance or rescue model code on the host.

Larger follow-ups belong to the existing CLI and logging plans: consolidate the
historical harness-import chain, add reviewed privacy-safe rejection-rule facts,
and maintain a small fixed regression case set with predeclared comparisons.
Do not build a new evaluation framework, migrate artifacts, change public data
contracts or collect raw rejected commands/prompts merely to improve diagnostics.

On 2026-10-18 the owner reaffirmed that ordinary correction belongs in the
agent's coding turn and requested comparison with established agent practices
before choosing further loop controls. A proposed single correction per turn
was not established as policy. OpenAI documents
[bounded recovery with effect checks](https://developers.openai.com/api/docs/guides/agents-api/errors)
and [model feedback after recoverable tool failures](https://developers.openai.com/api/docs/guides/tools-computer-use-sdk-drivers).
These sources support feedback, finite resources and explicit failure handling;
they do not establish a universal correction count or reveal internal Codex
retry policy. Production's provider-error boundary and the private pilot's
repeated-blocker callbacks are different surfaces; do not claim their parity.

The owner subsequently approved implementing selective recovery in the shared
agent, with the instruction to execute a small change or plan a larger one. The
investigation found coordinated adapter, error-contract, loop, checkpoint and
reporting work. The implementation is now checked offline and documented in
[the CLI roadmap](development-roadmap.md#approved-next-baseline-slice-shared-model-output-recovery).
Follow the documented expert approach: safe actionable feedback, observed-effect
checks, original resource limits, preserved history and escalation for repeated
lack of progress. These are design requirements to validate locally, not a claim
that our implementation already matches OpenAI or that every service failure is
recoverable. Keep ordinary tool correction, malformed model output, transport
retries and safety/approval failures distinct. Do not replace those distinctions
with a universal retry count, blindly replay tools or weaken acceptance to match
an external example. Recheck relevant official guidance during implementation;
reuse this repository's components rather than adding an agent SDK/framework.

The initial shared implementation chooses an actionable stop for repeated output
failures at the same observed file state, as permitted by the plan, rather than
adding a production approval prompt. Known pre-tool argument failures receive
safe host feedback within existing iteration/deadline limits. The neutral error
signal remains non-retryable for transport/fallback purposes. File observations
are bounded and conservative; this is not a general supervisor or proof of model
quality. [ADR-061](../decisions/ADR-061-shared-model-output-recovery.md) records the
contract, consequences and offline validation. Fresh live acceptance remains open.

The owner also approved a narrow future-fixture exception for read-only
`type(value).__name__`, because ordinary error formatting should not fail a coding
evaluation. Inspect the builtin one-argument expression precisely; keep other
dunder access, calling/mutating that attribute, shadowed type functions, dynamic
class construction, reflection, I/O, protected originals and frozen-review
restrictions. This changes a synthetic fixture check, not production permissions.
Consumed fixtures and their failed outcomes remain unchanged.

On 2026-10-17 the owner accepted the visible-console interaction evidence from
the local aw pilot and authorized Codex to take the user role in subsequent
similar synthetic pilots, avoiding repeated physical `yes` input. Reuse the
existing harness checkpoint callback and label its answers as automated pilot
continuations, never physical human approvals. This is scoped pilot automation:
it does not change production approval policy, create an unattended work window,
renew consumed inference grants or authorize new data/providers. Prepare fresh
finite bounds and deterministic checks before each live pilot. Safety,
scope, expiry, protected tests, frozen review and independent acceptance remain.

The owner then granted standing authorization for local-only tests, including
local-model pilots in the approved scope. Fresh named finite allowances are
prepared and checked locally without asking for per-run approval. Hosted/paid
inference retains its separate grant requirements. Announced gaming mode means
the owner needs PC resources: do not start heavy local tests and safely wind down
owned tests. No automatic gaming-mode detection or new supervisor is implied.

Automated pilot callbacks must carry already-checked launch authority across the
existing environment sanitizer without restoring grants to model/tool variables.
The first delegated pilot incorrectly rechecked a deliberately removed variable
and refused an ordinary continuation. A regression reproduced this with the live
flag and real sanitizer; a fresh successor captures authority transiently before
sanitation and preserves scope, guard, deadline and phase limits. Its subsequent
local engine HTTP500 occurred before a checkpoint, so live delegated continuation
remains unobserved. Preserve that distinction and do not repeat trials blindly
when the engine error's exact cause was not retained by the private transport.

The local HTTP500 investigation found that the private pilot worker closed the
HTTP error without reading its JSON error message. A fresh preparation now reads
bounded error bodies and persists redacted status/cause categories, parser error
kinds, timing and worker/controller correlation before returning. Arbitrary error
text, echoed prompts/tool arguments and private thinking remain excluded; unknown
categories remain unknown. Real loopback500 and privacy tests verify the path.
The fresh model probe completed eleven requests without500, passed an automated
checkpoint, then failed a separate source-correctness oracle. This does not prove
the earlier500cause or a runtime fix. Reuse the improved diagnostics for justified
future local work rather than repeating unchanged trials to force reproduction.

The aw receipts verified initial physical confirmation and three current
continuation answers; they do not establish every interactive denial/expiry path
on real hardware. Coding passed host tests/oracle, but review command failures,
missing diff inspection and unsupported report claims still failed acceptance.
Its harness reserved six review calls/tools without enforcing the published
phase ceilings; overall totals stayed bounded, but future preparation must align
the written phase limits with actual admission checks. Preserve the consumed
failure rather than relabel it after changing the harness.

The owner clarified on 2026-10-16 that ordinary Python constructs belong in
CLI parity evaluation. A synthetic fixture rejected `int()` before execution
because its handwritten language allowlist was too narrow; that was not a
production CLI permission restriction. Fresh fixture preparation accepts public
builtins and standard numeric/string/container methods while retaining its
no-I/O task scope, protected tests, approval/privacy rules and frozen review.
AST inspection is a task check, not an OS sandbox; the production command
runner's workspace working-directory check is not OS isolation either.
Preserve consumed failures and distinguish offline validation from live quality.

The owner also clarified that local models should not inherit hosted speed
limits. The local gpt-oss trial was cancelled at its 60-second request cap while
numeric runtime telemetry still showed generation. Record this as an incomplete
trial under an unsuitable resource envelope, not an empty terminal response or
proof of model-quality failure. Prepare subsequent local allowances from measured
hardware throughput, output budget, prompt processing and complete workflow needs;
merely extending a request inside the same short total may still starve review.
Report latency separately from correctness and completion. Keep finite compute
grants, cancellation, cleanup, privacy and substantive review. Local execution
avoids hosted request quotas and remote-service dependencies; this does not yet
establish comparative model quality or end-to-end reliability.

Check the actual attended input/output path before a live launch. A Windows
console handle can exist without a visible approval prompt in a piped launcher.
Chat approval does not constitute a physical console answer. The longer local
trial exposed that mismatch; it also left malformed tests with missing originals.
Keep both findings, verify cleanup independently after an external stop, and
leave unflushed usage unknown. A visible-terminal manual launcher can support
supervised small tasks while end-to-end acceptance remains incomplete.

The native model/tool/observation loop follows conventional agent architecture.
A new agent framework is not needed to address the identified gaps.

The owner clarified that Codex should operate the CLI as a delegation coordinator,
rather than merely hand the owner a manual command. Existing read-only approval
policy permits headless review tasks without a physical prompt while retaining
the full tool definitions; shell/write/custom operations remain denied. A local
review completed on a supplied real patch, but its inaccurate line references
and missed exit-code bug required host verification. Earlier attempts failed on
oversized listing output and an incomplete file snapshot. Supply complete task
dependencies, preserve failures and separate model review from host authorship,
testing and repair. This does not establish quality parity or measured Codex savings.

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
