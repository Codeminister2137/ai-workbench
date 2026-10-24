# CLI Development Foundation Roadmap

## Planned: reliable model availability across sources

Owner direction, 2026-10-21: plan a reliable way to check model availability for
every configured source. Defer implementation while completing the paid-native
CLI baseline. The stale `gpt-5.5` ChatGPT route demonstrates why executable/auth
readiness and a static catalog entry are insufficient. Use source-appropriate
metadata where available, preserve capability/entitlement distinctions and
freshness, and report unknowns explicitly. Do not use model generation as an
availability probe or silently switch models, providers or billing tiers.
This planned work adds no service, recurring monitor, dependency or paid usage.

## Implemented: advisory scrutiny and bounded repair

ADR-066 now uses tolerant report parsing with labelled format limitations,
records unreadable reviews as review failures, defaults to advisory scrutiny,
and retains `--scrutiny-policy required` for a blocking non-pass verdict.
Coding and external-agent paths feed findings back as untrusted advice, rerun
validation and review, and share the existing repair-cycle cap. Unreadable
re-review stops repair rather than reusing stale findings. A pass with non-empty
`format_issues` shows the review limitation in closeout.

Focused offline regressions cover these behaviors. Live model-quality and
integrated report-fidelity acceptance remain incomplete. The minimal loop is
the owner-approved design; the full research refinement guard set is deferred.
Research and pending matcher choices are preserved in the dated artifact briefs.

## Current paid-route baseline: 2026-10-24

The shell/PID ownership repairs, MCP warning policy and advisory scrutiny repair
are integrated. Offline acceptance-controller and Go two-turn harness checks do
not establish live paid-route completion. October 23 Go review trials stopped on
timeout/output exhaustion; continuation replay is now repaired under ADR-055.
Owner selected an automatic 16000-token native coding default for exactly Go
Kimi K2.7 Code. Fresh read-only Go continuation now demonstrates two invocations,
exact saved visible history, actual inspection tools, matched admission/transport
budgets and verified owned cleanup. Its reporting remains qualified: an unqualified
no-provider-calls claim contradicts host counts, and a nested summary duplicates
the CLI heading. External detection is not automatic CLI correction. Full coding,
orchestrated review/repair and fallback acceptance remain open. Retain original
tests, full instructions/history, frozen review, finite bounds and owned cleanup.
Comparable bounded Go runs have standing owner approval; keep each scope named.
On the same date, one bounded coding/review question completed under local
auxiliary and scrutiny support, and a separate read-only report-fidelity trial
was mechanically accepted but tainted by a local auxiliary tool proposal. Repairs
for that auxiliary contract and for a bold closeout label are offline-validated.
A third bounded trial then aligned the harness with production's auxiliary
contract and exercised explicit bookkeeping attribution: the auxiliary proposal
is recorded without stopping the run, and the primary report named both host
databases as host bookkeeping. Clean paid-agent workflow acceptance, live
fallback and scrutiny-fed repair remain open. See
[the current baseline assessment](baseline-gap.md) for evidence and remaining
limits. Local synthetic parity remains separate from the paid-route baseline.

## Historical paid-native checkpoint: 2026-10-21

Prioritize ordinary development through established paid clients with fallback.
Current-route work delivered reviewed diagnostic process ownership, conservative
MCP failure tracking and test integration in `c3b4ba9`; independent registered
validation passed 2,604 tests with 3 skips, lint/types passed and final frozen
review found no concrete defect. Coding CLI failures and a model test timeout
remain preserved; they are not retroactively promoted by host validation.
The [current baseline assessment](baseline-gap.md) records the remaining command
timeout/ownership gap, pending MCP error-semantics decision and unverified selected
fallback. Broader local-model parity and availability automation remain separate.

## Historical checkpoint: 2026-10-20

The latest integrated orchestrated local trial stopped on a private budget-notice
false positive before tests or either final report. An auxiliary pass also
displayed unsupported edit/test claims. Presentation now explicitly qualifies
tool-free advice; focused offline controls cover that delivery and prospective
notice/receipt corrections. The consumed trial remains failed and unchanged.
No milestone is promoted. See [current acceptance gaps](baseline-gap.md) and
[trial evidence and limits](agent-methodology-findings.md#orchestrated-local-trial--2026-10-20).

Current direction: [reassess acceptance around the full workflow](acceptance-criteria.md).
Owner accepts mistakes caught by scrutiny, the main model or another declared
component before trustworthy final delivery. Separate primary accuracy, successful
bounded recovery, safe incomplete outcomes and material false claims escaping to
the user. Do not reject harmless recovered friction or require flawless drafts.
Preserve meaningful validation, provenance and hard safety/resource boundaries.
Existing historical trial verdicts remain unchanged. Seven-case offline calibration
now demonstrates that validation-driven repair can correct a scripted defect, but
a scrutiny warning/proposed revision does not replace or explicitly qualify the
original claim in final delivery. Owner selected explicit final qualification;
the implementation now preserves a labelled draft beside concrete findings or
review limitations and withholds an accepted outcome preview. Automatic correction
was not added. Focused offline regressions cover final delivery and real validation.
See [the measured limits](agent-methodology-findings.md#offline-workflow-calibration--2026-10-19).
Structured-report API changes remain deferred. General baseline readiness remains
unestablished.

Latest attended evidence: isolated report diagnostic `cc` and fresh integrated
fallback `ce` are consumed and failed report fidelity. `ce` used a coherent final
task and full committed instructions; model-only source/two meaningful companions,
three preserved originals, five passing model/independent tests and 3,616 oracle
cases were verified. Its coding report again omitted its recovered command refusal.
An independent report gate stopped before frozen review; no second report exists.
Eight calls/seven accurate tool notices, 139 dependencies, five original index
entries, protected inputs and eleven owned-child cleanup receipts pass. This is
failed disclosure, not an inferred algorithmic or transport failure. `cc` likewise
omitted an actual refusal despite describing the synthetic one. Baseline remains
**INCOMPLETE**; preserve both reports and all acceptance requirements. Further
report-contract changes need owner selection, not speculative prose grading or
another blind prompt-only retry. See `artifacts/cli-report-fidelity-integrated-20261019ce/live-review.md`.

Fresh `by` completed both structural phases in thirteen local model calls:
model-authored source and four companion tests, three preserved originals,
seven passing tests per phase, independent tests and 3,616 oracle cases, both
returned reports and eleven accurate tool notices. All 135 sealed dependencies,
protected inputs, original index and owned cleanup pass. Strict integrated
acceptance remains **INCOMPLETE**: the coding report omits a required recovered
command refusal, and postflight found stale blanket import clauses beside the
approved typing scope. Full root instructions were correct; composed task
coherence was insufficiently checked. No imports were used, so typing was not
exercised live. Source-only review diff and ambiguous test-preservation wording
are explicit scope notes, not grounds to invent an algorithmic failure.
The consumed run remains unchanged; a separate offline clarification and seventeen
regressions address the task contradiction without new inference or production
changes. Evidence: `artifacts/cli-typing-integrated-acceptance-20261019by/live-review.md`
and `artifacts/cli-instruction-coherence-20261019bz/README.md`.

The owner approved reviewed standard-library imports such as `typing` in future
pilots and clarified that repository agent instructions are the CLI behavioral
baseline. The blanket source-import ban was too narrow for representative Python
usability. A prepared private profile permits fourteen reviewed typing names,
aliases and type expressions while retaining existing effect/protected-test
guards. Required instruction loading and actual guarded test execution are checked
offline; consumed outcomes are unchanged and strict fresh acceptance remains pending.
See [the behavioral baseline and declared test deviations](agent-methodology-findings.md#owner-directed-behavioral-baseline--2026-10-19).

The preceding `bu` integrated slice stopped at the fixture's source-import rule before
tests: model-authored code imported `typing` despite the explicit no-import scope.
The model preserved three originals, added two companion tests, and recovered one
failed text edit. Nine requests returned HTTP200; no test execution, coding report
or frozen review completed. Independent source attribution, protected inputs,
original indexed content, 131 sealed dependencies and owned cleanup pass. Live
correctness is unvalidated and baseline acceptance remains INCOMPLETE. That failure
led to the approved future-profile correction above; it supplies no algorithmic
failure or new execution authority. No blind replay or historical regrade.
Local evidence: `artifacts/cli-integrated-completion-acceptance-20261019bu/live-review.md`.

A preceding fresh bounded frozen review passed on existing model-authored input:
both reads, Git status/diff, six passing tests, accurate notices and an accepted
substantive final report. Independent 3,616-case oracle and cleanup pass; source-only
diff and paraphrased output are recorded scope notes. This supplies no fresh coding
authorship. `artifacts/cli-budget-notice-acceptance-20261019bt/live-review.md`.

Earlier diagnostic evidence follows; its consumed allowance remains closed.

The fresh native review diagnostic exercised ADR-062 live: missing Git diff
triggered shared feedback; the model then corrected an invalid empty-path call
and successfully inspected the diff. The original eight-call ceiling stopped
before a corrected final report, so acceptance still failed. All independent
tests/oracle, frozen inputs and owned cleanup passed. A retained private wrapper
also displayed obsolete24/32ceilings despite correct8/8enforcement. Its effect
on model choice is unknown; the correction subsequently passed offline composition
and the bounded live review above. All displayed counters must match active limits.
The retained candidate is not an accepted report. Local evidence:
`artifacts/cli-completion-acceptance-20261019br/live-review.md`.

Offline continuation reproduced premature completion in the unchanged shared
loop, with original history preserved and spare request budget. Fourteen new
diagnostic regressions pass; prepared fixed origin/rule/missing-check projection
retains the cause safely. The owner selected shared optional completion feedback
in ADR-062. Implementation passes88focused tests and the full offline gate of
2,474passed/3skipped, with full Pyright and Ruff passing. Default completion is
unchanged without caller-declared requirements; live acceptance remains incomplete.
See [daily readiness](daily-cli-readiness.md#current-assessment--2026-10-19)
for implemented capabilities and the separate remaining workflow/migration gates.

The approved isolated frozen-review diagnostic reached review and failed for a
specific omission: no Git diff before the final report, despite unused call/tool
capacity. Its report also misattributed copied input as current implementation
and described an unobserved diff. The stronger gate caught this; independent
tests/oracle, frozen inputs and owned cleanup passed. Baseline remains INCOMPLETE.
Next: deterministic completion/report-accuracy regressions and inspection of
existing bounded feedback points before another fresh live question. Preserve
model authorship and original limits; do not increase caps or repeat integrated
coding merely to reach review. See [methodology findings](agent-methodology-findings.md).

The owner requested a pilot-methodology audit. Recent runs have provided useful
stage evidence but no complete acceptance; several proposed changes were never
exercised before an earlier phase failed. The revised sequence uses deterministic
reproductions and targeted stage diagnostics before another integrated trial.
Stronger successful-observation gates and usage/execution distinctions are
implemented and checked offline. See
[the methodology findings](agent-methodology-findings.md#pilot-methodology-audit-and-next-sequence--2026-10-19).
No historical outcome is regraded and baseline acceptance remains INCOMPLETE.

A bounded local slice produced model-authored changes that passed six tests and
3,616 independent oracle cases, with an accurate coding report. Frozen review
exhausted its allowance after an invalid empty-path Git diff and separate file
diffs; its test run and report remain missing. Cleanup was verified. Baseline
acceptance remains INCOMPLETE. The Git diff tool now explains that callers should
omit `path` for all changes and supply a nonempty path when narrowing the diff;
execution semantics and workspace protections are unchanged.

## Current checkpoint: 2026-10-18

A subsequent local slice made source/test edits but removed an original test;
preservation checks stopped execution before tests or either report. Owned
cleanup was independently verified. Offline private-launcher fixes now preserve
safe error locations, native output/exit codes and populated stop reasons, with
116 guards and an independently checked scripted workflow. The edit tool's
description now explains insertion by retaining the original anchor in the
replacement. This general interface clarification leaves edit semantics and
strict acceptance unchanged; its effect on model adherence is unverified.

A fresh local acceptance slice stopped on its ninth request when the owned
Ollama runtime rejected generated tool-call JSON. Eight responses and one source
edit were observed; no tests, final coding report or frozen review completed.
Protected inputs and originals stayed unchanged, and owned cleanup was verified.
The exact malformed bytes and generation-versus-parser cause remain unknown.
Immediate offline work separates parser error suffixes from echoed arguments and
restores known provider attribution in a fresh private shim. The owner approved
the narrow read-only `type(value).__name__` fixture exception and reaffirmed
ordinary correction within existing resource/approval boundaries. A universal
one-correction-per-turn cap is not an accepted decision. Shared selective recovery
is now implemented offline under ADR-061; baseline live acceptance is INCOMPLETE.

The owner approved shared-agent selective recovery and asked that a larger change
be planned rather than implemented as a small retry patch. The subsequent bounded
implementation below passes software checks; approval and software checks do not
complete live acceptance. The documented OpenAI approach and its limits remain in
[methodology findings](agent-methodology-findings.md#findings-to-retain).

Owner approved structured CLI error attribution with a bounded safe fallback
control receipt ([ADR-060](../decisions/ADR-060-structured-cli-error-attribution.md)).
Provider/category/cause type now survive the covered ProviderError closeout and
coding-chat boundaries and appear in terminal summaries. Deterministic checks
exercise actual native/fallback/CLI execution and reopened transcript storage;
no live inference was needed. Original trace coverage claims were corrected in
[the inventory](../logging-artifact-inventory.md#verified-cli-error-attribution--2026-10-18).
The wider review remains open for provider bodies, tool/worker/scrutiny paths
and complete primary/recovery cause chains. Baseline parity is still incomplete.

Owner direction: add a repository-wide error-propagation review, prioritizing the
CLI/agent and its provider/tool/worker boundaries. Preserve known causes through
translation and make the failing service/stage easy to identify. Every encountered
unexplained error starts immediate investigation; generic statuses and wrappers
must not masquerade as root causes. The bounded review and acceptance requirements
are in [the logging/error review plan](../logging-and-artifact-structure-plan.md#wider-error-propagation-review--owner-direction-2026-10-17).
This adds a review requirement, not a new service, error schema or automatic retry.

Latest local investigation repaired the private pilot's discarded HTTP-error
diagnostics; deterministic loopback/privacy checks pass. A fresh eleven-request
probe did not reproduce the old500, passed a delegated user-role checkpoint, then
failed a separate invalid-input oracle in model-authored code. Exact old500cause
remains unknown because its body was discarded. Preserve all consumed failures,
full instructions/history/tools and independent acceptance protections. Local tests
are authorized without per-run chat grants except announced gaming/resource mode;
hosted/paid and new scope/privacy decisions retain their existing boundaries.

Baseline CLI and reliable fallback remain **INCOMPLETE**. Ordinary tool/test
correction is accepted; older pending one-anchor choices below are historical.
Recent iterative trials produced correct effects in some runs but did not finish
both the substantive edit report and frozen review. Passing code checks alone
does not complete those acceptance phases or establish parity.

Fallback ordering is now an explicit, allowance-derived chain (`[fallback]`
`priority`/`exclude`/`allow_cost_escalation`, `--fallback-priority`,
`--fallback-exclude`). A live switch was recorded on a different billing source,
but no candidate had usable capacity at the time, so fallback is attempted and
recorded rather than completed. See
`docs/repo-assistant/baseline-gap.md` and
`artifacts/fallback-acceptance-20261024-123206/`.

An observed provider `error` finish was normalized as a blank response. The owner
approved recognizing OpenRouter choice-level errors with the existing root-error
categories; an error finish without usable details is non-retryable. Existing
quota/rate-limit fallback eligibility remains guarded. This does not identify
the cause of earlier empty responses whose raw shape was not captured.

Bounded successor preparation now discloses the coding allowance separately from
the total and retains remaining-allowance notices in ordinary tool history. The
unattended path records a stalled slice instead of prompting an absent owner.
A later trial stopped before executing source containing a call outside the
synthetic fixture's inspected language. A subsequent local trial hit the same
artificial restriction on `int()`. The owner clarified that ordinary Python
capabilities should be supported. Fresh fixture preparation broadens builtin
and standard data-type method support while retaining task scope, protected
tests, approval/privacy rules and frozen review. These are fixture changes and
failure observations, not evidence of improved real-model completion.

The owner subsequently clarified that local execution needs allowances suited
to the PC's throughput rather than hosted speed limits. The fresh local trial
timed out on its fourth request before edits or reports; the previous three
responses contained valid tool calls. Prepare both request and overall local
compute allowances accordingly, leaving realistic room for repair and frozen
review. Record latency separately from quality; retain finite grants, cancellation
and all acceptance protections. The consumed timeout remains historical evidence.

The longer local attempt reached seven model requests and source/test edits,
then stalled after two command errors. The owner reported no visible approval
console; the owned tree was stopped with independent cleanup verification.
Read-only review also found invalid test indentation and removal of the original
test inventory, so the incomplete result is not solely a launcher failure.
An opt-in local manual-launch packet now checks for redirected terminal I/O
before inference. It supports supervised experimentation, not accepted migration
or quality promotion. The owner reports roughly 20% of the weekly Codex allowance
remaining; prioritize a usable local handoff and reserve Codex for diagnosis and
review rather than repeated broad inference sweeps.

Continue transparent, fresh, bounded edit/test/report/frozen-review acceptance
when its inference allocation is justified. Retain complete instructions/history,
tools, approval/privacy/quality boundaries and separate strict evaluation.
Independent unattended coordination remains the next priority after baseline;
deadline-only sleep scheduling does not implement that supervisor.

The first useful delegated implementation slice corrects `list_dir` traversal:
the local model supplied the iterative method, and host review corrected output
indentation, typing and junction handling before validation. Depth/hidden pruning
now occurs before descent. Six new regressions and extended boundary checks are
included; the full root suite passed 2,297 tests with nine skipped. This is a
verified software fix with mixed model/host authorship, not full coding parity
or proof of Codex savings. Large shallow listings can still exceed context.

## Approved next baseline slice: shared model-output recovery

**Status: implemented offline; live acceptance INCOMPLETE (2026-10-18).** The owner
prefers recovery in the actual shared agent over a private-pilot-only experiment
and requested alignment with established expert methodology. Investigation found
a coordinated change, so it was planned first under the owner's small-change/large-change
instruction, then implemented after the owner requested continuation. The shared path now uses
the actionable-stop option specified below; it adds no live approval prompt and
no global one-correction-per-turn cap. Detailed local context remains in the
private CLI parity plan. See [ADR-061](../decisions/ADR-061-shared-model-output-recovery.md).

Offline verification: full gate 2,450 passed / 3 skipped (workspace 2,328, Council 38,
job-search 84), full Pyright and Ruff lint/format pass. The production adapter,
shared loop and native CLI activity paths are exercised; failed request usage
stays partial/unknown. First validation failures exposed a Windows oversized test
ID, older result stubs missing the additive count and an unregistered test module;
all were investigated, fixed and verified. No new inference or quality promotion.

OpenAI's [recovery guidance](https://developers.openai.com/api/docs/guides/agents-api/errors)
checks completed effects and bounds attempts/deadlines. Its
[tool-runner example](https://developers.openai.com/api/docs/guides/tools-computer-use-sdk-drivers)
provides safe feedback for recoverable failures while stopping on invalid state.
Apply those principles to our observed failure modes; neither source specifies a
universal correction count or proves equivalence to internal Codex behavior.

At approval, ordinary tool/schema errors already returned actionable feedback, but
`AgentLoop` propagates every `ProviderError`. Ollama's generated-tool JSON parser
can fail before a usable call reaches the host. The private pilot has repeated-
blocker observations and a scoped callback; production lacked that composed path.
Merely marking all HTTP500 errors retryable or catching them in an unobserved
transport retry would conceal failures and risk wasted work.

Implemented in bounded steps on existing boundaries:

1. **Classify known pre-tool output failures.** Inspect existing provider errors,
   Ollama parsing/HTTP handling and admission/accounting. Define the smallest
   neutral signal proving that no executable call was delivered; adapters own
   provider-specific recognition. ADR-061 selects the additive `ToolCallFormatError`
   subtype. Unknown, truncated or spoofed error details must
   not enable correction. Keep raw payloads/reasoning out of messages and logs.
2. **Compose correction and stall handling.** Feed safe host feedback through the
   existing shared loop, preserving full history, instructions, settings, tools
   and privacy. Every failed or corrective request consumes the original turn,
   phase, time and review reserve. Reuse the pilot's useful progress/checkpoint
   principles in production-owned code; do not import private artifact modules.
   Repeated equivalent failures without new evidence trigger a bounded checkpoint
   or actionable stop. Do not create a separate retry allowance or new supervisor.
3. **Preserve approval and evidence boundaries.** Never replay completed tools or
   invent assistant/tool output for a call that could not be decoded. Preserve
   earlier effects and first-error attribution. Production approvals remain human
   or existing authorized policy decisions; automated synthetic callbacks remain
   confined to their named pilot. Unknown effects require reconciliation. During
   an authorized unattended window, stalled-slice evidence/cleanup and wider-plan
   continuation follow existing policy; no unattended window is granted here.
4. **Report and verify the composed behavior.** Distinguish failed requests,
   corrected output, substantive model work and host recovery. Reuse usage/error
   receipts; failed-call usage and cost stay partial/unknown when unobserved.
   Test actual provider/loop/CLI boundaries before preparing any fresh inference.

Required deterministic acceptance:

- Known malformed arguments produce safe feedback, then a corrected call can run
  exactly once and return a substantive report with full earlier context intact.
- Several ordinary corrections can occur within one turn; no global one-correction
  cap is silently introduced. Repeated unchanged failures/no-op or cycling states
  reach a checkpoint/stop instead of an invisible retry loop.
- Unknown errors, denied approval, privacy/safety violations, expired bounds and
  frozen/protected-input violations cannot be converted into automatic recovery.
- Failed or interrupted operations preserve known effects and error attribution;
  no replay occurs when execution is uncertain. Generic HTTP500 is insufficient.
- Original request/tool/time limits and review reserve remain enforced, including
  at checkpoints; truthful numeric usage and unknown coverage survive closeout.
- Parser payload spoofing cannot supply cause labels or leak arbitrary text into
  host feedback, terminal reports, transcripts or safe diagnostic fields.

Only after these checks pass, prepare one fresh bounded local coding/test/report/
frozen-review slice with new inputs, seals, independent oracle and cleanup checks.
Preserve all consumed failures. Baseline completion still requires model-authored
correct effects and both substantive reports, not merely a successful retry.
New dependencies/services, provider/model/runtime changes, privacy/logging changes
or materially different public-contract choices retain the normal decision gate.

Next: align a fresh private pilot's transport shim with the neutral signal, retain
its durable diagnostics, refresh all guards/workflow/oracle/cleanup evidence and
seal against a clean reviewed source checkpoint. Existing consumed ba and prior
seals remain evidence. Do not claim live acceptance from this software change.

## Historical 2026-10-15 live follow-up and interrupted-usage repair

Baseline CLI remains **INCOMPLETE**. Two fresh owner-approved OpenRouter iterative
trials failed different conditions. The first repaired source and passed original
tests but exhausted its eight edit calls before companion tests or frozen review.
The later trial used the accepted flexible total envelope and attended checkpoint
policy; it stopped after five requests because an exact-text edit anchor contained
an extra blank line. No edit was applied and no checkpoint or frozen review was
reached. Owned cleanup was verified. Preserve both failures and consumed grants;
neither an unapplied proposed fix nor a later host diagnostic rescues acceptance.

The host exception also exposed a reporting gap: an unexpected exit could bypass
the normal metrics footer. The CLI now prints unreported cumulative numeric usage
before transcript cleanup, preserves the exception and unknown cost, and avoids
duplicating a normal report. The affected gate passed 528 tests; final focused
checks passed 17, with targeted Pyright and Ruff/formatting clean. These are
overlapping correctness checks, not model-quality or complete-baseline evidence.

Next decision: whether the separate iterative evaluation permits one bounded
literal-anchor correction, or retains its immediate stop on non-test tool errors.
No policy change or successor grant is inferred. Independent supervision remains
immediately after baseline. No production privacy guard, normal approval default,
quality declaration, billing source or source activation changed.

## 2026-10-15 offline conformance and usage slice

OpenRouter now carries transient, exact-origin continuation on ordinary and
streamed tool turns under ADR-055. Synthetic checks cover replay, route/role
isolation, complete-input admission, hidden metadata and answer-only persistence.
Other hosted continuation contracts remain unverified. Temperature/output
forwarding is verified; the owner subsequently accepted opt-in temperature/top_p
controls with existing defaults preserved (ADR-058). Explicit settings now survive
task tool turns, repairs and provider fallback; incompatible external native
clients refuse them. Native template parity and effective hosted settings remain
unverified. No privacy guard changed.

The CLI reports numeric per-call/cumulative observations independently of final
response metrics, with field-level complete/partial/unknown coverage on success
and failure. Missing cost stays unknown; this adds no account quota monitor,
reasoning logging, persistence or allowance-consuming test. See
[usage and conformance semantics](resource-and-usage.md).

Fresh iterative acceptance preparation retains strict safety/correction/freeze
evidence and separately permits bounded model-run test/repair feedback. Baseline
CLI remains **INCOMPLETE**: no new live grant or model-quality acceptance follows
from these offline changes. Independent unattended coordination remains the next
priority after baseline, with supported job runners reused and new coordination,
storage/recovery and task-kind choices reviewed before implementation.

Validation: the affected CLI/provider gate passed 653 tests; subsequent focused
checks passed 92 after final accounting guards and integration tests. Full Pyright
and final targeted Pyright passed; commit hooks passed Ruff and formatting. These
are overlapping software checks, not a combined count or model-quality result.

## Previous checkpoint: 2026-10-14 closeout

Baseline CLI remains **INCOMPLETE**. OpenRouter free-only integration and exact
price/quota/tool guards are implemented and checked offline; production Free-plan
privacy refusal remains unchanged. Gemini individual access is retired and refused.
Earlier setup/discovery checkpoints below are historical, not current readiness.

Direct synthetic access succeeded on several OpenRouter routes, while Cohere and
NVIDIA full CLI trials failed different acceptance conditions. Connection success
does not establish coding quality. Preserve the failed runs and consumed grants.
Next: implement offline exact-route adapter/settings conformance and cumulative
numeric usage reporting, then prepare distinct bounded iterative coding acceptance.
See [preserved methodology findings](agent-methodology-findings.md). Independent
supervision remains immediately after baseline CLI; later research stays backlog.

Closeout validation: 2300 passed / 3 skipped across workspace, Council and job-search;
Ruff, formatting and Pyright passed. These checks do not complete live acceptance.

## 2026-10-13 approved Gemini CLI and OpenRouter direction

Owner approved Gemini CLI integration and requested OpenRouter connection with
the $10 purchase deferred. Node/npm/Gemini were not found on PATH or in checked
common locations. Owner subsequently selected project-scoped environment changes:
Python uses the existing uv `.venv`; external runtimes use supported local prefixes
with reproducible installation guidance. OpenRouter provider/free-price
contracts and a configured key are absent from inspected current configuration.
Neither integration is complete. Antigravity Free tier is owner-confirmed;
connection discovery passed independently of the stricter automatic quota-reader
isolation requirement. Requesty free allowance should be unused today according
to owner evidence; remaining live quota is still unknown. Existing free route
prices passed validation, with no inference or personal prepaid deposit.

Groq's published 8K TPM/200K TPD limits appear unsuitable for full coding sessions:
the focused CLI review accumulated 210,777 input tokens across rounds, including
175,232 cached tokens. Provider cache and tokenizer differences prevent a measured
Groq latency claim. Recommend deferring full-session use; small tasks remain a
candidate. Cerebras and Zed/Delta are owner-deferred emergency promotions;
OpenCode remains exploratory. See ADR-057 and private evidence at
artifacts/provider-source-decisions-20261013/README.md.

## 2026-10-13 Antigravity / Requesty and alternative-source investigation

Owner confirmed both Copilot and Kiro allowances exhausted. Antigravity's
authenticated native model discovery succeeded with verified cleanup; current
quota remains unknown because isolated quota startup is unproved, and scoped
shared MCP grants remain unresolved. Requesty's configured key fetched the live
catalog: thirteen chat models passed the existing zero-price validator, including
the approved Gemma route. Native balance was zero; free daily remaining is unknown.
Metadata establishes neither usable inference capacity nor coding quality.

Host research compared current primary-source offers for OpenRouter, Gemini CLI,
Groq, Cerebras, OpenCode and Zed, separating recurring quotas from temporary
promotions and integration/privacy requirements. No source was adopted, inference
sent, permission changed or purchase/login/install performed. Requesty's existing
standard quality declaration and the high continuation floor remain unchanged.
Evidence and next-step trade-offs: artifacts/fallback-source-survey-20261013/README.md.

## 2026-10-13 Kiro preparation after Copilot allowance exhaustion

Owner confirmed Copilot Free allowance exhausted and selected Kiro. Configured
Kiro 2.24.0 passed isolated no-inference version/usage/model discovery with owned
cleanup verified. Native usage estimate: 50 of 50 plan credits, 100%, reset
2026-11-01; usable capacity remains unverified and appears exhausted. Discovery
lists nine models including explicit Claude Sonnet 4.5 and Sonnet 4; this is not
inference access or quality acceptance. No login, inference, installation,
purchase, defaults or quality-policy change. Capacity confirmation and explicit
model eligibility remain boundaries before a fresh bounded acceptance.
Evidence: artifacts/kiro-baseline-preparation-20261013/README.md.

## 2026-10-13 earlier Copilot preparation

Owner selected Copilot. Existing repository command override resolves Copilot1.0.90;
bounded no-inference auth/model/quota metadata read returned authenticated status,
only auto model, zero remaining chat and zero premium entitlement, with verified
owned cleanup. This does not establish subscription identity/plan or model quality.
No login/update/install/inference/default or quality-policy changes performed.

Opt-in two-route catalog parsed and preserved high Codex/standard Copilot; static
inspection confirms preservation compatibility, not implementation eligibility.
Loading repository command overrides corrects earlier bare-module discovery:
Copilot/Kiro preservation are available; Antigravity continuation is blocked by
explicit MCP grants rather than executable absence. Owner subsequently confirmed
Copilot Free allowance exhausted and moved preparation to Kiro; no login needed.
Evidence: artifacts/copilot-baseline-preparation-20261013/README.md.

## 2026-10-13 local fallback logging and operational configuration

Coding-chat now persists host-observed effective route/ordered fallback attempts
in existing message metadata and resumed history, preserving failure/expiry outcomes
and excluding private handoff contents. Three HOST regression cases, full2188passed
3skipped, Ruff/format/Pyright/diff passed; no live model inference or routing change.
Local evidence: artifacts/cli-fallback-history-20261013/README.md.

Offline inspection of the normal catalog identified a baseline operability gap:
high-quality Codex has only unavailable high Antigravity as an implementation
continuation candidate. Copilot/Kiro auto routes are standard and eligible only for
emergency read-only preservation under current policy. This does not contradict
earlier eligible synthetic-catalog fallback pilots. Explicit comparable-quality
alternate-route selection/validation is needed; do not relabel auto, lower the
quality floor, install a client or change defaults silently. Accounts/quota were
not probed. Daily baseline automatic implementation fallback remains INCOMPLETE.

## 2026-10-13 bounded Codex quality comparison

An owner-authorized exceptional paired synthetic task supplied a direct-chat
baseline and three actual CLI Codex turns: inspection, corrected implementation,
and frozen validation/review after saved-session restart. Both source fixes agree;
CLI authored two meaningful tests, preserved five original tests, and actually ran
all seven through shell and owned process tools. Its factual review distinguished
staged/unstaged state, original/added tests and host/model execution evidence.

Overall live acceptance remains INCOMPLETE: the pilot's host-authored guard denied
legitimate scoped review operations. Historical failure retained; guard repaired
and four regression checks passed locally, with no paid rerun. All three paid
turns consumed; the allowance is closed. Exact direct-chat model/settings and
histories were not matched, so this is positive narrow evidence, not general parity.
Six messages/outcomes persisted; owned host/thread/process cleanup verified.
Local evidence: artifacts/cli-paid-quality-pilot-proposal-20261013/RESULTS.md.
Approved AGENTS rules avoid paired paid trials by default, require bounded
question-driven live usage, and keep other tests local-only. Next quality
acceptance should be a focused CLI-only task under a fresh selected allowance.

The owner then authorized continuation. One fresh Codex CLI-only frozen review
selected `review-repo-change`, retained all six messages including failure, and
completed13shared-tool observations without denial or truncated narrow diffs.
Root inspected the substantive review and accepted accurate correction/test/Git
and host-versus-model evidence. All eight saved messages, unchanged old failures,
frozen files and owned cleanup were verified. The focused review is COMPLETE;
the original guard-blocked trial remains failed and broader equivalence incomplete.
Evidence: the same artifact root's review-20261013-2136/README.md. Both allowances
are used/closed; no repeated pair or general parity/economics claim.

[CLI guide](../repo-coding-assistant.md) ·
[Accepted scope: ADR-040](../decisions/ADR-040-shared-agent-tools-and-cli-development-foundation.md)

## Status and outcome

High-priority repository-wide prerequisite:
[official-documentation conformance](../documentation-conformance-plan.md).
ADR-055 starts with Ollama continuation-state preservation; adapter conformance
and tool compatibility do not establish coding-quality parity.

High-priority usability work also includes the
[logging and artifact structure review](../logging-and-artifact-structure-plan.md):
make sessions understandable to the owner, with one clear result entry point and
organized supporting evidence. The review does not authorize deleting old artifacts.


The [2026-10-10 daily-use readiness report](daily-cli-readiness.md) recommends an
attended real-work pilot as the shortest next step, while retaining the accepted
quality/security migration gates. Full replacement remains incomplete. Usage
fallback is implemented and has bounded installed-client continuation evidence;
it does not make timed candidate selection host-enforced or establish recovery
from today's actual IDE usage-limit interruption. Tomorrow's pilot selection and
fresh live scope remain owner decisions.

**INCOMPLETE — independent foundation slices implemented; design and acceptance gaps remain.**

The 2026-10-13 attended public coding-chat slice completed literal-reader
regression authoring, host validation and frozen model review with verified owned
runtime cleanup. Two model-authored tests cover Unicode/CRLF/no-final-newline
exact editing and literal-mode file/workspace/range/schema refusals. Production
source and all ten original tests were preserved. Full offline gate: 2,158 passed,
three skipped; Ruff, formatting, Pyright and diff checks passed.

This was host-guided recovery: two failed drafts, missed requested corrections,
unnecessary reads, refused tools and a false high-severity review finding required
host feedback. The corrected review read the validation source and retracted that
finding. Shell/process tools were omitted for this narrow authoring case; testing
was host-run. Resume, skills, process control, fallback and representative daily
coding quality remain separate acceptance gaps. This slice establishes neither
autonomous parity nor speed improvement.

The subsequent attended real-task slice corrected `CreateFileTool` byte-count
reporting for UTF-8 text and platform newline translation. Four model-authored
regressions passed after host-guided newline-expectation repair; all twelve
launch-baseline tests and source outside `CreateFileTool.execute` were preserved.
The model ran the scoped tests through shell and owned process start/status tools,
both with exit 0 and 16 passing tests. Independent full validation passed 2,162
tests with three skips; static and old-behavior counterfactual checks passed.

The owner excluded physical-interaction testing, authorizing the exact inspected
commands without manual prompts for this invocation. Default policies stayed
unchanged. A host receipt BOM-loading failure interrupted review startup; recovery
retained the saved conversation and immutable original deadline. The resumed CLI
selected `review-repo-change` and inspected the actual scoped diffs/source/tests.
Code review found no defect, but repeated inaccurate test attribution and handoff
claims required host correction and remained unreliable. Owned cleanup was verified.
Real-task code/test acceptance is complete; continuity-reporting quality and the
broader representative migration assessment remain incomplete.

A subsequent offline reconstruction retained every earlier owner message,
the active correction, review skill and explicit correction-precedence guidance
through the native request-assembly path. No history-delivery defect was
reproduced. A bounded read-only low/medium reasoning comparison used matching
conversation/file/task fixtures; both reports still omitted or misattributed
required validation/recovery facts. No default setting change or broader quality
claim follows from this single case. An independent external-route comparison
requires explicit owner approval for its outbound context.

The owner subsequently authorized one subscription-only installed-Codex read-only
comparison with the scoped files, complete saved conversation and host facts.
Current-client offline containment passed. The native client returned a
substantive, factually reconciled review and exited successfully, but the public
CLI classified its startup feature warning as failure. The same error-labelled
warning was reproduced with synthetic loopback responses; no cloud retry followed.
The review also identified missing success-message/full-file-byte assertions in
the byte-count tests. Existing passing checks remain valid, but those requested
assertion gaps reopen complete test acceptance. Files/history were preserved and
owned cleanup verified. This case changes no defaults and establishes no parity.

An offline follow-up now recognizes the complete known Codex startup notice in
its completed error-item shape, preserving raw evidence, genuine errors and failed
process exits. Host-authored regressions include successful/failed session receipts;
the old-classifier counterfactual rejects the new acceptance checks. Installed-client
synthetic responses confirm that the notice is benign while an intentional denied
read still fails. Full host gate: 2,175 passed, three skipped; Ruff/format/Pyright
and preservation checks passed. No cloud retry or model-authored review of this
fix occurred. Earlier live failure evidence and missing byte-count assertions remain.

Three additional model-authored companion tests now close the ASCII overwrite
success-message and complete platform-newline raw-byte assertion gaps. All sixteen
launch-original test functions/imports and production source were preserved.
Host-guided recovery was needed for an incorrect ASCII count and missing byte
assertion; the host formatted but did not semantically repair the tests. Model
shell and owned process tools actually ran nineteen passing scoped tests. The old
source counterfactual fails five regressions. A usage-limit interruption left no
observed historical cleanup transition; stopped state was reconciled separately.
A fresh full-history local review inspected the diff but failed factual acceptance.
Its owned cleanup was verified. This live slice remains incomplete.

Two bounded host fixes now distinguish an absent separate deterministic validation
stage from actual model tool execution, and report native delegation availability
from the foreground tool registry. Integration checks cover the reported behavior
without invoking a child. The combined host gate is 2,182 passed, three skipped;
Ruff, formatting and Pyright passed. These fixes have no new model review and
establish neither broader CLI quality nor cross-agent parity.

Decision and milestone recording is complete as of 2026-10-04. Verified tools and
fallback are foundations; they do not constitute completed cross-agent parity.

The current [next-session plan and approved directions](next-session-decisions.md)
records D1-D3 approval: conservative configurable privacy/approval defaults,
replacement SearXNG investigation, and the accepted local typed acceptance-job
contract. D3's bounded live fixture passed. The owner now retains direct URL
fetching; search replacement is deferred and does not block independent work.
Historical checkpoints below retain their original validation counts. The earlier
full offline checkpoint was 1,685 passed: root 1,615, Council 33 and job-search 37,
with 3 Windows file-symlink permission skips.
The 2026-10-09 unattended follow-up passed 1,785 offline checks: workspace 1,715,
Council 33 and job-search 37, with the same three file-symlink skips. It adds
strict acceptance effect auditing, redirect/path fixture preparation, runtime
configuration containment and actual CLI skill/semantic continuity checks. See
[the acceptance follow-up](coding-chat-acceptance-results.md#fresh-unattended-window-offline-follow-up-2026-10-09).
The final M1 readiness suite has 84 passing tests. Ruff/formatting, Pyright and
`git diff --check` pass. Live-provider cases remain excluded. See
[test workflow](../test-workflow.md).

The goal is to perform inspect/plan/edit/test/review workflows from the project
CLI, invoke the required skills, resume work and recover from allowance exhaustion
with the common tools still available. PyCharm may host tools initially; eventually
it should only be the human editor/viewer. Different model performance is allowed.

### Migration requirement clarified (2026-10-09)

The owner requires continuous coding chat and results comparable to or better
than their current assistant conversations before moving daily development to
the CLI. Separate coding invocations and bounded tool acceptance are insufficient.
Coding-quality tools, instructions, skills and continuity must support that
outcome. Model differences remain possible, but do not excuse a material quality
regression in the migration workflow. Delegation should reduce cost without
lowering quality; savings and quality preservation both need measured evidence.
See the [continuous coding chat proposal](continuous-coding-chat-plan.md).

## 2026-10-09 continuous coding chat — initial offline integration complete

ADR-049 records the owner's selection of a distinct continuous foreground mode
with existing local SQLite storage. `coding_chat` owns reusable conversation
control; `coding_chat_cli` binds current native/official-client execution and
shared scoped tools. Turns retain decisions and host-observed outcomes while
refreshing files/instructions. Restart checks workspace/privacy/cost boundaries
and requires reconciliation after interruption. Processes live across turns
and are terminated on exit; MCP credentials are fresh and expire after each run.
The provider-only `chat` mode retains its earlier contract.

The slice adds 25 regression cases, including real file effects, approval denial,
process continuity/cleanup, synthetic official-client execution through the real
foreground host, transcript cleanup and deterministic SQLite connection release.
Full gate: root 1,615 passed / 3 Windows symlink skips, Council 33, job-search 37;
Ruff/formatting/Pyright pass. All three infrastructure wheels built offline and
isolated wheel-loaded conversation/parser/persistence smoke passed.

Migration remains INCOMPLETE. Subsequent follow-up work implements deterministic
history reduction and queued in-flight steering, with original transcripts,
mandatory owner text, host outcomes and fresh approval tickets retained. Required
tool installed-client acceptance and representative quality/cost comparisons
remain. The [20-case comparison set](coding-chat-quality-cases.md) maps local
preparation to the remaining conversational evidence. Earlier bounded live
allowances recorded in the acceptance results are exhausted; further execution
needs a newly selected scope. The initial offline integration above made no
live calls, private-source transmission, new database/daemon, merge or push.

## 2026-10-08 design/test audit — approved offline slice complete

ADR-047 records the accepted execution-boundary fixes and requirements-based
regressions. ADR-048 moves the assistant command and workflow into `ai_agent`,
preserving legacy import/launch compatibility and provider-core independence.
Validation, chat context, diagnostics, run tracking, source rendering, local
support passes, repair and final scrutiny now have reusable modules and direct behavior tests.

The follow-up fixes malformed validation commands, preserves timeout output,
rejects impossible mandatory chat budgets, retains structured external failures,
checks references against actually supplied source lines, counts full rendered
context within its budget, and validates time limits before side effects.
Local support derives configuration through the existing execution-target adapter.
Repair success requires actual passed revalidation; skipped checks cannot erase
an existing failure, and missing handoff receipts remain explicit risks.
Repair and scrutiny derive their deadline from the run tracker; an omitted or
later caller deadline cannot bypass its budget. The CLI retains a thin scrutiny
wrapper around explicit execution/client hooks for compatibility.
Storage formats, routing/privacy/approval policies and dependencies are unchanged.

The final offline gate passed 1,660 cases with 3 file-symlink permission skips;
Ruff, formatting and Pyright pass. The CLI remains partly monolithic; broader
composition-helper ownership and attended/live acceptance remain separate work.
All three infrastructure packages built offline wheels. Isolated wheel imports
verify the eight extracted modules, command metadata and both module launchers.
Packaged repair and scrutiny also refuse execution after their tracker deadline.
No live model/account access, email transmission, installation, merge or push ran
in this slice.
A final planning-only review raised explicit local-only privacy versus inherited
parent privacy for context delegation. On 2026-10-09 the owner confirmed
inheritance as the intended default; routing behavior remains unchanged. A
future delegated-task privacy option is deferred. See
[the decision record](post-audit-decisions.md#context-delegation-privacy--inheritance-confirmed-2026-10-09).

## 2026-10-06 closeout consistency — COMPLETE

The repo-assistant CLI now renders one fixed `## **SUMMARY**` envelope across
chat, provider, native-tool, external-agent, and fallback routes. It preserves
agent output separately and bases validation/execution fields on CLI-recorded
evidence rather than model claims. This closes the immediate reporting-contract
priority; it does not change the remaining roadmap scope. Final gate: 1,295
workspace tests passed, 2 skipped; 21 Council tests passed; Ruff, formatting,
Pyright, and `git diff --check` passed.

## 2026-10-05 checkpoint and remaining boundaries

**Earlier slices COMPLETE; CLI foundation INCOMPLETE, with fresh audit below.**

Earlier checkpoint validation: 1106 passed, seven live tests skipped in 142.00 seconds; repository
Ruff lint/format, Pyright and focused commit hooks passed. Separate live results
below are preserved independently of the skipped optional integration tests.

- Shared partial-effect fallback retains complete instructions, objectives,
  task identity, fresh run scopes/approvals, updated receipts and external deadlines.
- Saved foreground process observations survive route changes; an actual synthetic
  in-flight child is polled through the same handle without relaunch. Restarted
  handles remain metadata, not attachment authority.
- Fixed D3 native acceptance passed with real GPT-OSS read/edit effects, host
  validation and verified runtime/worker/validator cleanup. Two earlier startup
  failures remain preserved. Existing model-library configuration is retained;
  owned acceptance runtimes disable cloud discovery/pruning and bound metadata
  readiness retries. No download or global setting changes were made.
- Real Copilot 1.0.91 and Kiro 2.24.0 continued a synthetic Codex quota failure
  using shared workspace writes. Each fixture recorded exactly two successful
  edits under distinct run IDs, retained the partial comment and passed host
  assignment validation. This is bounded continuation evidence, not complete
  tool/skill/interactive-approval parity.
- The [D2 public operator investigation](search-operator-investigation.md) found
  no usable JSON replacement. No configured search operator was changed.

The owner subsequently selected authenticated loopback MCP in
[ADR-044](../decisions/ADR-044-authenticated-foreground-mcp-host.md) and supplied
their machine-local PyCharm endpoint. The shared foreground host is implemented:
fresh bearer/session scopes, start/status/stop across routes, denial/expiry,
interruption cleanup and restart refusal. Real Copilot and Kiro each polled the
same live child after synthetic quota fallback and completed the partial edit;
both children were cleaned up. Four failed Copilot handshake runs are preserved;
the newer `server/discover` probe now receives the supported protocol fallback.

The read-only IDE wrappers/configuration importer are implemented, with the
supplied endpoint saved only in ignored local storage. After the owner's SDK
installation approval, SDK interoperability and all three project IDE wrappers
passed, including successful IDE session deletion. Missing-SDK/unavailable-endpoint
diagnostics were verified. See [local setup](local-tool-hosts.md).
One exact owner-approved shared file write passed through the live terminal
approval handler; the owner's chat confirmation was relayed into the controlling
terminal. This does not prove the owner physically typed there. Live shell approval
and broader client parity remain unverified.
The owner selected the Jedi-based, preview-first Python rename direction on
2026-10-06. The offline implementation is complete: `rename_preview` and
`rename_apply` share the guarded workspace tool contract; `python_navigate`
provides bounded definitions/references through the same optional Jedi extra.
Jedi 0.20.0 is opt-in
under `uv sync --extra rename-preview`. Full offline workspace and Council tests,
Ruff, formatting, Pyright and lock checks pass. Coverage includes preview
immutability, concurrent edits during analysis, cross-file imports/calls,
duplicate local names, Unicode/CRLF, stale and expired plans, complete-diff
approval, one-use handles and partial-write reporting. An actual attended/native/
shared-client apply fixture remains. An isolated temporary-package preview has
passed through both the native registry and foreground HTTP MCP transport using
a synthetic MCP client; the two-file fixture remained unchanged. This is not
installed third-party client or apply-approval acceptance. The owner selected
this direction to advance IDE independence while permitting PyCharm as a
temporary tool host; see [ADR-045](../decisions/ADR-045-ide-independent-semantic-rename.md).
Interactive denial also passed through the foreground HTTP MCP transport: the
approval callback received the complete diff, denied the write, and the fixture
remained unchanged. After the owner approved the exact displayed two-file
`Widget` -> `Gadget` diff, apply passed through the foreground HTTP MCP transport
under the interactive permission policy; the exact diff/digest was checked,
both file effects were verified, and the disposable fixture was cleaned up.
This is bounded synthetic-client shared-transport acceptance, not evidence of
physical terminal input, installed third-party-client parity, or full C5/M5
completion.
Antigravity remains excluded. This is bounded acceptance, not full tool parity.
Component selection and suite timing are documented in [test workflow](../test-workflow.md).
The workspace check also runs the previously omitted Council suite separately.

The fresh wider-plan audit found eligible unfinished work beyond those earlier
slices: common public fetching, deadline/session/shutdown races, streamed provider
tools and trailing usage, malformed-response normalization, saved usage diagnostics,
complete report paging and hard-latency validation. These are implemented and
verified; the earlier blanket blocker conclusion was insufficient.

A bounded actual Copilot fixture called the common public fetch tool once and
returned its HTTP 200 receipt and matching body digest. It used only a public
Python documentation URL in a synthetic workspace, took 13.7 seconds and reported
one premium request. The foreground listener closed. This verifies one client,
not all-client research parity or authenticated-source access.

All six private DOCX plans and five Markdown plans were reviewed again against
code and accepted decisions. Remaining concrete boundaries and recommended next
work are recorded in [the fresh audit](post-audit-decisions.md). This does not mark
the wider project complete or turn old unchecked plan items into new approval.

### Standalone Python runtime diagnostics (C3)

The native and shared coding profiles now expose a read-only `python_runtime`
tool. It reports the interpreter executing the project agent plus declared
`requires-python`, lockfile presence and a conventional workspace `.venv`
candidate. It does not switch interpreters, execute workspace code, or claim
that separately launched commands use the reported environment. This is an
initial IDE-independent diagnostic. The default orchestrated pytest validation
invokes the same Python executable running the repo-assistant process instead of
resolving `python` through PATH; its result records that executable. The
accepted ADR-046 adds `--validation-python` to explicitly select a different
interpreter for that default command. Explicit custom validation commands remain
caller-selected and unchanged. On Windows, quoted command arguments are
unwrapped without losing backslashes. The default remains pytest only;
Ruff/Pyright are available through explicit commands or pre-commit, without
expanding default validation policy.

Standalone validation also retains command-tree ownership through completion,
timeout and interruption. A finite local reproduction showed a 0.5-second timeout
waiting 4.13 seconds for a descendant's inherited output pipes. The runner now
uses the existing Windows job support or a POSIX process group, closes owned
descendants even after successful parent exit, and stops further validation when
cleanup is unverified. Interpreter choice and validation receipt fields remain
unchanged. This advances the C3/C6 offline contract; it does not establish full
M5 or real-model report fidelity.
The credential-filtered worker environment also retains Windows `PATHEXT`, which
PowerShell needs to classify and resolve native executables. A real Python
invocation verifies this without forwarding provider credentials or changing
the caller's interpreter choice.

A narrow standalone offline acceptance now combines `python_runtime`, real pytest
and default/explicit interpreter selection in a workspace with spaces, a
conflicting PATH and a misleading `.venv` hint. Separate subprocesses run without
loading the IDE bridge or MCP server; actual interpreter markers and owned cleanup
are checked. Explicit Ruff/Pyright commands accept valid code and reject seeded
lint/type errors. Both interpreter selections use the same installed executable;
this does not establish a second interpreter's compatibility or complete M5.
Evidence: `artifacts/cli-python-vertical-20261020do/`.

### Consolidated C1-C6 IDE-independence contract (M5 offline)

`tests/test_ide_independent_capabilities.py` exercises the approved capability
set through the shared coding registry in a workspace with no
`data/pycharm-mcp.json`. It covers C1 repository/Git and file mutation, C2 the
portable review skill plus working instructions, C3 `python_runtime` and a real
unittest run, C4 `fetch_url` provenance plus the private-network refusal, C5
Jedi navigation and preview-then-apply rename, and C6 handle-based process
continuity including refusal after host close. A fresh process also proves the
common surface never imports the `mcp` SDK, and a valid IDE configuration only
adds the three read-only IDE tools; removing it restores the identical common
surface.

This is deterministic offline composition evidence, not installed-client or
live-model acceptance. The C4 success path uses an injected test fetcher rather
than a real public request; the C5 checks require the optional Jedi extra; C6
covers host-owned child continuity, not a cross-provider route switch. M5 still
needs installed-client/live evidence and any capability work those checks expose.

## Approved capability set

| ID | Capability | Required outcome |
| --- | --- | --- |
| C1 | Repository tools and local Git | Inspect, search, edit and review changes under the selected permissions |
| C2 | Portable skills/instructions | Discover and invoke development skills with checked dependencies and applicable repository instructions |
| C3 | Python environment/validation | Select the correct interpreter and run tests, lint and type checks with useful diagnostics |
| C4 | Documentation/public research | Retrieve permitted sources and preserve provenance |
| C5 | Semantic code tools | Navigate symbols/references and perform supported safe refactoring |
| C6 | Process/session continuity | Poll/interrupt operations and continue coding through turns and route switches |

## Milestones

| ID | Milestone | Status | Completion condition |
| --- | --- | --- | --- |
| M1 | Readiness and adapter contracts | **Complete offline**; fallback diagnostics distinguish adapter compatibility/executable presence and report effective skill, tool-profile, approval, and option requirements. Live client/account parity is deferred. | Deterministic route/tool/skill/approval checks explain eligibility and exclusions; forced-limit coverage preserves tier and task constraints |
| M2 | Common tools and portable skills | Offline discovery/prerequisite reporting is implemented; Copilot and Kiro passed live selected-skill inspection; Antigravity's default headless MCP permission was verified denied; Codex check is deferred until its reported reset | C1-C4 work through common contracts on selected routes; explicit skills resolve dependencies; required instructions are available or omissions cause a clear refusal |
| M3 | Semantic tooling with temporary IDE host | Read-only IDE bridge, optional Jedi preview/apply, and read-only Python definitions/references implemented; bounded native/shared MCP rename acceptance passed with a synthetic client | Selected C5 operations pass native/shared live acceptance with defined semantics and permissions; installed-client coverage is still required where applicable |
| M4 | Coding and process continuity | In progress; live Copilot and Kiro fallback each continued shared edits and polled the same in-flight process handle | Agreed session/process model preserves objective, decisions, scoped approvals, receipts and handles across turns and fallback; uncertain effects are reconciled |
| M5 | Independence from the IDE tool host | Offline C1-C6 common-surface contract implemented and passing; installed-client/live parity pending | Approved C1-C6 workflows remain usable with PyCharm tool hosting unavailable; PyCharm can serve only as editor/viewer |

Each milestone has deterministic correctness checks and separately recorded live
acceptance where necessary. A milestone cannot be reported fully accepted on
synthetic evidence alone when it requires an installed client or IDE bridge.
Deferred live checks must not prevent independent offline implementation.

### M1: offline acceptance — COMPLETE

First slice implemented on 2026-10-04: `--fallback-readiness` reports static
policy and executor exclusions without authentication/tool/provider probes;
execution preflight retains precise incompatibility reasons. Same-tier and
different-bucket policy tests now cover every cost ceiling. Full offline suite:
828 passed, seven live tests skipped; Pyright clean. Fresh synthetic-exhaustion
acceptance continued a partial edit through real Copilot and passed its fixture.
These results do not prove canonical tool/skill parity or alternate approval modes.

2026-10-06 diagnostic follow-up: the offline report now exposes
`executable_status` (`available`, `unavailable`, or `not_applicable`) separately
from adapter compatibility. This checks local command presence only; it never
starts a client or probes credentials, tool connection, or allowance. Tests
cover a compatible adapter with a missing executable and a present local
executable. Full offline suite: 1,296 passed, 2 skipped; Council: 21 passed;
Ruff and Pyright clean.

The static compatibility matrix now covers both shared-tool profiles across
Codex, Copilot, Kiro, and Antigravity, with all four approval presets for the
coding profile. It verifies that the effective profile/policy reaches the
existing adapter configuration and that unsupported Antigravity shared-tool
mapping is reported rather than treated as eligible. It uses mocked executable
discovery and does not start clients or probe accounts. Installed-client
permission parity remains separate acceptance. Full offline gate after the
matrix: 1,320 passed, 2 skipped; Council: 21 passed; Ruff, formatting, Pyright,
and `git diff --check` passed.

Offline readiness now applies normal shared-tool normalization before reporting:
an explicit skill implies shared inspection and `read_only`, selected skill
sources and existing tool prerequisites are checked, and missing skills produce
a blocked result. The report includes effective shared profile, approval
policy, and validated selected skill names. Regression coverage also verifies
that an unsupported Codex-specific search option is reported as incompatible
for alternate shared-tool routes rather than hidden behind general adapter
support. The option compatibility tests now cover every declared Codex-specific
CLI option for Codex and alternate Copilot/Kiro routes, both with and without
shared coding tools. Existing constraints are preserved, and mutually exclusive
native-tool/session flags are rejected consistently by offline readiness.

The M1 deterministic completion criteria are now met. Existing fallback tests
cover same-tier and cost-ceiling constraints, privacy and tool-capability
filtering, quality-preserving defaults and explicit task-minimum downgrades,
forced quota continuation, exhaustion bounds, incompatible-route refusal, and
preservation of task instructions. Readiness tests cover effective skill,
shared-tool, approval and CLI-option compatibility, including unsupported
routes. Final validation: readiness suite 84 passed; full workspace 1,372
passed and 2 skipped; Council 21 passed; Ruff/formatting, Pyright and
`git diff --check` passed. This completes M1 offline only. Authentication,
remaining allowance, installed-client permissions and live route parity remain
unverified and require a separately selected acceptance window.

Implemented context slices include nested repository instructions for selected
paths and visible context truncation/omission diagnostics. Under ADR-041, complete
applicable instructions use a separate configurable budget and overflow refuses
before execution rather than truncating instructions. A model-free
`--read-search-only` MCP profile exposes repository inspection tools. A
bounded real Copilot acceptance discovered and called `find_files`, `list_dir`
and `read_file` with explicit read/search grants, returned the fixture marker and
left the fixture unchanged. Further isolated fixtures connected Codex and Kiro to
the same inspection profile. Codex found an injected regression through shared
Git/read/search tools; Kiro returned a marker using shared file discovery/read.
These checks confirm three client connections, not write/shell, all-client parity
or fallback with common MCP configuration. Codex's review is not evidence of a
dedicated native skill activation receipt.

All four configured official clients are discovered when the repository's normal
environment file is loaded, and their existing authentication checks report ready.
This does not establish remaining allowance or equivalent authorization. An
Antigravity inspection fixture returned exit zero with no answer or tool receipts:
headless MCP permission was auto-denied. The adapter now reports that explicit
diagnostic as failure while preserving the process status. Narrow native grants
and common approval mapping remain unresolved; no global permission settings
were changed for this fixture. A separate short tool-free Antigravity request
returned the expected answer; basic execution works despite the MCP refusal.

Native coding and the opt-in inspection MCP profile now share bounded local Git
status/diff tools under READ permissions; the default Codex delegation profile
is unchanged. Focused fixtures verify index preservation, staged/unstaged diffs,
literal paths, outside-root refusal and disabled external diff helpers.
Final review also verified that ordinary Git diff can execute configured content
filters. Inspection now disables clean/process helpers and nested submodule content
scans, preserves pointer changes, and reports raw-content comparison explicitly.
Regression fixtures verify helpers do not run and configuration/index stay intact.

A portable `review-repo-change` skill source lives under `packages/ai_agent/skills/`.
Its syntax validator passed. Copilot CLI 1.0.91 discovered an isolated fixture copy,
produced an explicit skill invocation receipt, used shared Git/read tools and
reported an injected regression without changing files. This is one bounded
read-only skill acceptance; automatic installation and provider-native skill
activation remain incomplete. `--list-skills` now discovers known supported
project-local sources and reports their common-tool/Git prerequisites without
starting a client, provider, installer or granting new permissions. Unknown
skills are not advertised without a prerequisite contract.
Offline regression coverage also confirms that selected skills refuse a missing
Git executable and that the complete selected skill instructions survive
usage-limit fallback continuation.

Native coding now uses an actual-tool prompt and retains receipts on bounded
loop failure or an unexecuted final textual request. A live local GPT-OSS coding
fixture performed inspect/edit/PowerShell validation/diff successfully. A paired
20-task synthetic probe returned real tools on GPT-OSS (19/20 strict checks under
each prompt; both missed checks only removed a final newline). Qwen2.5-Coder
returned textual requests with no actual calls on all 20 tasks under each prompt.
No broad model-quality or pass-rate improvement is established; model-native
tool compatibility remains a readiness gap. Catalog routing was not changed.

Direct current-session PyCharm host checks verified interpreter selection, symbol
information, diagnostics and a rename that updated an import and call in a small
temporary package; the imported result passed afterward. The owned fixture was
archived and removed. These checks validate host operations, not the project CLI
bridge, mutating refactor approval semantics or independence from the IDE.

The per-tool/skill readiness audit is complete using existing contracts; no new
capability manifest or public client contract was needed. Authentication, tool
connection, authorization and live availability remain distinct from static
readiness and are not inferred by the offline report.

### Cross-agent acceptance

Synthetic shared-coding continuation is verified for usage exhaustion and overload
through Codex/Copilot command mappings and actual MCP read/edit effects. Full
instructions, objective, preset, quality/tier policy and task identity survive;
run IDs are fresh even without durable sessions. Saved sessions supply updated
hashed receipts on route switches. Interactive continuation requires fresh exact
approval; a denied call leaves the partial edit unchanged. Deadlines refuse later
stages and bound external clients even when they continuously emit output.
This is deterministic evidence, not live client mutation/terminal acceptance.

Synthetic clients must perform a representative inspect/edit/test/review fixture,
exhaust a route after a partial effect, continue using the common tools without
replaying that effect, and produce a resumable handoff. Incompatible routes refuse
before execution with the missing capability or policy named.

After the process/session design is agreed, add equivalent synthetic coverage for
an in-flight operation and handle recovery. Start with bounded operations rather
than introducing a general service or queue.

### 2026-10-06 bounded live acceptance

All requests used disposable synthetic fixtures; no private repository source was
sent to the clients. No web/search calls or natural account exhaustion were used.

| Client | Live check | Result |
| --- | --- | --- |
| GitHub Copilot CLI 1.0.90 | Simulated initial Codex quota failure; shared coding continuation and foreground process continuity | Passed. Two completed edits used distinct run IDs, the existing child was polled by handle and cleaned up, the source passed the host validator, and protected fixture files stayed unchanged. Artifact: `artifacts/fallback-acceptance-20261006-124322`. |
| Kiro CLI 2.24.0 | Same forced-fallback/shared-process fixture | Passed with the same checks. Artifact: `artifacts/fallback-acceptance-20261006-124344`. |
| GitHub Copilot CLI 1.0.90 | Explicit `review-repo-change` skill with shared inspection/read-only permissions | Passed on a synthetic defect: the client used shared inspection tools and reported the changed operator and failing test contract; no edits or web calls. Artifact log: `artifacts/skill-live-copilot-20261006-124538.log`. |
| Kiro CLI 2.24.0 | Same explicit skill and inspection fixture | Passed with the same finding; no edits or web calls. Artifact log: `artifacts/skill-live-kiro-20261006-124617.log`. |
| Google Antigravity CLI 1.2.16 | Workspace-local `repo_shared` MCP config; one `read_file` request under default headless permissions with `--sandbox` and no bypass flag | Server/tool was discovered, but `mcp(repo_shared/read_file)` was denied before execution; no marker was returned and the fixture was unchanged. CLI stderr says headless mode auto-denies MCP permissions and requires an allow rule in `settings.json`. Fixture: `artifacts/antigravity-permission-probe-20261006-125851`. |
| Google Antigravity CLI 1.2.16 | Candidate workspace permission files: root `settings.json` and `.agents/settings.json`, each with only `mcp(repo_shared/read_file)` allowed | Neither location affected the CLI permission decision; both read calls were denied. These files existed only in disposable fixtures. Fixtures: `artifacts/antigravity-project-settings-settings.json-20261006-130912` and `artifacts/antigravity-project-settings-.agents-settings.json-20261006-130912`. |
| Google Antigravity CLI 1.2.16 | Native `write_to_file` request in a disposable fixture, with `--sandbox` and no bypass flag | Denied in headless mode because `write_file` had no allow rule; sentinel remained unchanged. Fixture: `artifacts/antigravity-native-write-probe-20261006-130539`. |
| Google Antigravity CLI 1.2.16 | Harmless native `run_command` (`Write-Output sandbox_probe_only`) with `--sandbox` and no bypass flag | Denied in headless mode because `command` had no allow rule; no marker was produced. This verifies that the tested sandbox invocation did not authorize shell execution. Fixture: `artifacts/antigravity-sandbox-command-probe-20261006-130539`. |
| GitHub Copilot CLI 1.0.90 | Shared coding profile under `read_only`; attempted one `edit_file` call | Denied by the MCP permission manager with “no scoped approval”; the sentinel stayed unchanged and the session recorded the failed edit receipt. Fixture/receipt: `artifacts/permission-live-20261006-124835`. |
| GitHub Copilot CLI 1.0.90 | Shared coding profile under `read_only`; attempted harmless `run_command` output | Denied before command execution with “no scoped approval”; no command output was produced. Fixture/log: `artifacts/shell-permission-live-20261006-124910` and `artifacts/shell-permission-live-copilot-20261006-124919.log`. |
| PyCharm-bundled Codex CLI, route `openai/codex-gpt-5.5` / model `gpt-5.5` | Explicit skill/read-only inspection on the same synthetic review fixture | Deferred until the provider-reported reset on 2026-10-10 at 08:35 (timezone unspecified). The earlier attempt was blocked before any tool call by a usage-limit response; zero tool and file-change events. It was not retried. |

Each completed Copilot invocation reported one premium request. Kiro emitted
per-run credit metering, but no account balance or allowance was queried. The
Codex service’s limit response is not treated as a live capability result. Its
next check is deferred until the provider-reported reset above; do not retry
early or switch routes to evade the limit. Antigravity server discovery is
verified, but its headless request-review mode denies MCP calls without a
matching grant. Official CLI documentation supports workspace-local MCP server
definitions in `.agents/mcp_config.json`; the live denial directs operators to
a `permissions.allow` rule in `settings.json`, while official settings docs
describe permissions as global or project-level settings. The project-only
grant scope was approved, but Antigravity CLI 1.2.16 exposes no project-permission
command or documented project-local permission file. Tests of root
`settings.json` and `.agents/settings.json` in disposable workspaces did not
grant access; the documented CLI settings file is user-level. No narrow per-run
grant override is documented or was tested. `agy mcp list` reported no global
server registrations, and no user/global or project permission/config files were
changed. Do not use
`--dangerously-skip-permissions`: it auto-approves all tool requests and is not
an acceptable substitute for scoped MCP grants. Two further sandboxed native
tool probes were denied as well: a `write_to_file` attempt did not alter its
sentinel, and a harmless `run_command` did not produce its marker. The tested
`--sandbox` invocation therefore did not authorize these native actions; a
project-scoped MCP read grant can be assessed separately while leaving native
file writes and commands without allow rules.
The earlier exact file-creation acceptance used a chat-relayed confirmation;
this run did not claim physical terminal approval, interactive shell approval,
or complete all-client parity. These execution checks do not evaluate model
quality.

Artifacts remain under ignored `artifacts/` for local inspection. The
read-only review fixture retains its intentionally planted diff and the
Codex-generated fallback handoff; no project source was changed by live runs.
The owner approved project-scoped allow rules for only the read-only inspection
tools; no native `write_file` or `command` grants are needed. Applying the
approved scope is blocked in this environment: only the headless CLI is
installed/available, and it provides no documented project-permission setup
path. Configure the exact MCP tool grants from Antigravity's project settings UI
when available, then rerun the live probe. Do not replace this with a user-wide
grant. Antigravity remains excluded until the exact project grants are active
and verified.

## Open design decisions

The investigated options and recommendations are in
[foundation decisions](foundation-decisions.md). All six recommendations are now
accepted in ADR-041; historical pending labels above are superseded. They must not
be presented to the owner for approval again. Current status follows below.

### 2026-10-04 implementation checkpoint

Overload and usage fallback now share the configurable ADR-042 continuation gate.
Default `preserve_quality` requires the original declared grade; explicit
`task_minimum` permits task-qualified weaker routes. Failed continuation saves a
local handoff without a weaker model call. Remaining balances and actual model
quality are not guaranteed by these deterministic checks. Full current validation:
933 passed, seven live tests skipped; live overload/quality-gate acceptance deferred.

Owner-approved task quality, context/instruction limits, request/validation
timeouts and repair caps are now typed private user defaults. Explicit CLI flags
win; shipped values, instruction overflow refusal and scheduler deadline admission
are preserved. Configurable privacy/approval defaults are implemented with shipped
`local_only`/`interactive`; explicit flags and client restrictions take precedence.

- Common inspection, checked project-local skill selection and complete required
  instructions are implemented. Forced Codex-limit fallback through real Copilot
  preserved those contracts; the production Kiro mapping passed its read fixture.
- Opt-in coding sessions retain objectives, explicit decisions and hashed receipts
  in existing application SQLite storage. Native process tools inspect direct
  children without AI calls; cleanup stops owned children. Restart requires human
  reconciliation of uncertain effects and never restores old approvals or pipes.
- Shared mutation approval across external clients remains incomplete. Versioned
  native coding compatibility and estimated model-input admission are implemented
  offline; exact tool-bearing counts and fresh live acceptance remain deferred.
  Native approval requests now show task, workspace and complete operation;
  no-human requests deny.
- Superseded on 2026-10-05: the endpoint was supplied, the SDK was installed with
  owner approval, and project-wrapper/session-lifecycle acceptance passed.
- The scheduled full-instruction acceptance ended failed at 14:05:08 UTC. The repair
  exceeded its local context budget; the saved report and final handoff survived.
  The scheduler recorded failure and stopped the sequence. No quality improvement
  or successful refinement acceptance is established by the reviewer pass.
- Offline follow-up bounds tool-capable repair/refinement previews instead of
  copying the tool-free review packet, retaining complete original requirements.
  This addresses avoidable input duplication; successful live repair is unverified.
- Historical 2026-10-04 compute/sleep limits applied to that run. Current resource
  authorization belongs to the active owner's instruction, not this roadmap.

The owner subsequently raised allowance overhead and requested sleep after saved
work. [Resource and usage guidance](resource-and-usage.md) records the immediate
avoid-idle-model-polling workflow, observed client usage and prioritized measurement
follow-up. An explicit Windows sleep helper is implemented; it adds no automatic
queue behavior or global power configuration.

- Explicit local IDE endpoint/activation and its access scope.
- Search source configuration: missing Tavily/Brave credentials and the failed
  SearXNG endpoint prevent search acceptance; direct URL fetching already works.
- Optional capabilities and generalizing the research-only scheduler, if needed.

Shared terminal approvals and native foreground recovery are accepted directions,
with implementation/acceptance still outstanding. Additional architecture choices
must be investigated separately; they are not automatically new approval gates.

### Native compatibility/input slice: COMPLETE offline

[Native admission contracts and bounded live checks](native-admission.md) document
the implementation. Automatic native coding retains positive GPT-OSS evidence;
explicit models/routes remain hard constraints. Model manifest, Ollama runtime and
native contract changes invalidate receipts. Every coding turn reserves generation
and framing capacity and includes complete instructions, skills, schemas and history.
Ollama requests pin the admitted runtime context. Overflow refuses before inference
and preserves earlier receipts. Byte-derived counts are explicitly estimated;
verified tool-bearing token counting is still incomplete.

Deterministic invalidation/refusal tests and native loop/fallback regressions passed.
No model inference, live client acceptance, new service or workstation sleep ran.
Final full offline suite: 965 passed, seven live tests skipped; Ruff lint/format and
Pyright clean. Foundation M1/M2
remain in progress; synthetic checks do not complete live acceptance or tool parity.
D1-D3 owner answers remain approved. D1 now includes enum validation, explicit CLI
precedence, effective persisted session privacy and retained read-only inspection.
D2 public operator probes remain deferred while work is offline. D3's
[typed-job contract](acceptance-job-proposal.md) was subsequently accepted and
implemented offline under ADR-043.
Shared external mutation approvals were subsequently implemented offline; bounded
live permission acceptance remains deferred.

### D1 user defaults: COMPLETE offline

Commit `f86aca5` adds typed `privacy`/`approval_policy` defaults retaining shipped
`local_only`/`interactive`. Explicit CLI options win, including abbreviations,
equals syntax and selections equal to shipped defaults. Session storage uses the
effective privacy before execution; incompatible resumes still refuse. Shared
inspection remains read-only and native client restrictions remain effective.
Owner private configuration was not rewritten. Full offline validation: 996 passed,
seven live skipped; Ruff lint/format, Pyright and commit hooks passed. At that
checkpoint D3 design awaited review; subsequent acceptance is recorded below.
No inference, service startup or sleep ran.

### D3 fixed local acceptance jobs: COMPLETE offline

Owner accepted the concrete contract in this session. `ai_provider.acceptance_jobs`
adds strict immutable v1 definitions and separate receipts to existing SQLite,
with conditional claims and explicit sequential time admission. The fixed native
harness allows source-only edits, preserves instructions/protected tests, requires
actual ordered read/edit effects, and uses bounded host arithmetic validation.
Retained Windows Job Objects own runtime/worker/validator trees, including after
root exit; other platforms refuse before runtime launch. Cleanup, interruption
and stale runtime/model/native-contract refusal have deterministic coverage.
Receipts flush during work and survive worker interruption. Planning starts no
processes and creates no fixture. Existing research contracts remain unchanged.

Focused offline tests: 55 passed; Pyright clean. Full suite and repository checks
are recorded in the latest checkpoint above. No model inference, actual acceptance
queue entry, runtime startup, new service, download or sleep was performed.
Dummy owned-process tests and fixed validators do not establish live model quality.
Shared external mutation approvals and scoped receipts are implemented below;
D3 live execution remains deferred until a selected compute window.

### Shared coding approvals: COMPLETE offline

`--shared-tools coding` exposes existing inspection/file/shell tools with the
selected preset. Official-client MCP calls pass the project permission manager;
interactive requests use a controlling terminal independently of MCP transport,
approve one exact operation and deny when unavailable. Fresh run IDs and
foreground PID/birth checks prevent inherited authority after owner exit.
Existing optional coding sessions persist task/run/tool and argument/output digest
receipts, including denied/failed calls. No new store, service or saved grant exists.
Shared inspection remains read-only; per-run Codex/Copilot/Kiro mappings avoid
global bypass flags, and Antigravity stays excluded.

Offline tests verify policies, denial, one-use approvals, owner/restart expiry,
workspace refusal, terminal escaping/isolation, scoped mappings and existing
SQLite receipt reuse.
Focused shared-tool/session/MCP tests: 54 passed; full suite: 1079 passed, seven
live tests skipped. Ruff lint/format and Pyright are clean. Live terminal
propagation and actual client mutations remain unverified under the offline limit.

2026-10-06 follow-up: the planned synthetic fallback-after-partial-effect check
is complete. `tests/test_shared_coding_fallback.py` covers quota/overload failure,
`workspace_write`/`interactive`, and persisted/non-persisted sessions. It verifies
the original edit is retained, continuation uses the same task and deadline with
a fresh run ID, tool access is preserved, interactive approvals renew, protected
files/instructions survive, and effects are not replayed. Combined focused
fallback/refinement tests: 70 passed.

The same follow-up investigated the 2026-10-04 research no-progress acceptance.
The saved trace shows both refinement turns returned zero tool calls and no final
text despite actionable review findings. A successful-empty refinement with no
report/evidence fingerprint change is now classified as an execution failure
immediately; it no longer consumes another no-progress cycle. Explicit
non-empty explanations for leaving a report unchanged retain the existing
two-consecutive-no-progress policy. Regression coverage is in
`tests/test_research_refinement.py`. Further model-quality evaluation still
requires a newly selected compute window.

The CLI foundation remains INCOMPLETE. Remaining live checks require the
owner's attended terminal approval, an available Antigravity project-settings
UI to apply already-approved read-only MCP grants, and the Codex route's
provider-reported reset before retry. The latest focused independent-tools,
fallback and refinement regression batch passed: 93 passed, 1 skipped; Ruff,
formatting, Pyright and `git diff --check` passed.

## Coding-agent methodology follow-up

Owner additionally requested reusable catalog-based access checks (2026-10-15):
select only missing/stale matching receipts, with explicit freshness/cooldown and
route/account/contract identity. Allowance-consuming checks run through a separate
live command, never the normal pytest suite or hooks. Support ad-hoc investigation
and future authorized pre-reset useful-work selection without automatic retries
or quota burning. [Access-check workflow](provider-access-checks.md) preserves
the requirements and remaining storage/scheduler decisions. Baseline CLI and the
immediate supervision priority are unchanged.

The owner accepted the 2026-10-14 review's direction: offline adapter/settings
conformance and cumulative numeric usage reporting first, retaining strict
authoring/correction/freeze evidence alongside a separate bounded iterative
test/repair acceptance. Concrete live bounds and fresh grant/readiness remain
required. [Preserved findings and research sources](agent-methodology-findings.md)
record the observations, limits and studies for later research. That follow-up
does not displace baseline CLI or the independent-supervision priority below.

Owner update (2026-10-15): ordinary tool/test error correction is the default
for iterative coding acceptance, within scope and a total resource envelope;
the one-anchor exception proposal is superseded. Retain strict safety/correction/
freeze evaluation separately and report errors, recovery, correctness and usage
independently. Repeated lack of progress triggers an attended bounded-continuation
checkpoint. Unattended, record the slice blocker/evidence and continue another
useful approved slice from the wider plan; only verified exhaustion justifies
early closeout. This does not renew live grants or implement general unattended
supervision. Concrete successor bounds and deterministic recovery/stall checks
remain preparation work; consumed trials remain unchanged.

## Optional capabilities: unselected

Browser/UI testing, notebooks, debugger control, GitHub issues/PR/CI, visual
document analysis, image generation and broader delegation/scheduling remain
outside the selected foundation. Present a concrete need and bounded integration
before adding one. Their research options are preserved in private local plans,
when available; this public roadmap is sufficient to resume the approved work.

## Next priority after baseline CLI: independent unattended supervision

Reuse the Prompt Library's [workflow and automation assessment](../prompt-library.md#reusable-workflows-and-automation-candidates):
closeout/context capture, cheap session-boundary checks, scope/stall review and
pending-decision tracking are inputs to this work, not separate prompt-engine
projects. Most routine checks already belong in authorized implementation;
independent execution after interruption remains future supervisor work. Weekly
prioritization is optional. [End of Day](../prompt-library.md#codex-end-of-day)
adds bounded useful allowance work and preserves existing Git/power authority.

Owner direction (2026-10-14): finish the established baseline CLI goals first;
independent unattended supervision is the next priority immediately afterward.
This does not change existing baseline acceptance conditions or authorize a new
service, general scheduler or persistence contract during baseline work.

Compose the existing supported job runners with an independently running work-window
supervisor. It should survive chat usage-limit interruptions, retain the selected
deadline and authorized task scopes, record completed/failed/interrupted/blocked
outcomes, stop admitting work in time for cleanup, and leave a readable handoff.
Sleep must record the actual work outcome; a deadline timer alone is not completion
evidence. Review/validation and any permitted commit policy must be explicit, with
inherited dirty work preserved and no automatic approval bypass or grant renewal.

Start by reviewing the existing research/fixed-acceptance runners and the one-off
deadline helper. Define the smallest supported coordination slice and acceptance
checks before implementation; ask at new task-kind, storage, service, recovery or
approval boundaries. Do not put arbitrary coding commands into existing queue rows.
Test chat interruption, first failure, uncertain cleanup and deadline closeout with
local deterministic fixtures before an explicitly granted live window. Planning is
approved; broader rollout and material implementation choices remain to be reviewed.

### Owner-requested direction: allowance-aware sleep, wake and continuation

Owner clarification (2026-10-21, attended): the eventual goal is a local work
supervisor that schedules useful authorized work across suitable paid-agent
allowances, can sleep between work windows, and wakes to continue when resources
are available again. Record this direction now; prioritize the established CLI
baseline and reuse its conversation/fallback infrastructure rather than building
a separate PyCharm-chat recovery system. This is a planning requirement, not
approval to register wake tasks, start a daemon, change power settings, select a
local supervisor model, or spend newly refreshed allowances automatically.

The smallest useful progression is:

1. Finish the baseline's demonstrated command/prompt blockers and verify ordinary
   conversation, saved continuation and selected fallback. Preserve meaningful
   validation/review; do not expand baseline acceptance into a general scheduler.
2. Reuse the existing provider-neutral transcript store (ADR-030), conditional
   observable fallback history (ADR-059), ownership receipts and bounded runners.
   Establish what each external client actually retains before promising complete
   history. Saved conversation still needs current repository state, approvals,
   partial effects and test evidence; never invent missing context or persist
   provider-private reasoning. Summarization must disclose omitted context.
3. Add the smallest independently running, finite closeout coordinator after
   baseline: deterministic owned cleanup and evidence capture, readable handoff,
   explicit incomplete/unknown outcomes. An optional model may summarize or
   propose next work; process ownership, spending and power decisions retain
   deterministic enforcement. A local generative model is not a prerequisite.
4. Extend coordination to explicitly authorized future work windows. Distinguish
   using expiring allowance BEFORE reset from resuming on replenished allowance
   AFTER reset. A provider reset is neither proof of restored model capacity nor
   authority to start work. Refresh provider-owned observations, check freshness,
   entitlement, quality, privacy and budget, then admit only useful planned tasks
   whose complete bounds plus cleanup fit the approved window. Defer unknowns;
   no generation-only availability polling or unbounded retry loops.
5. Add an opt-in Windows wake/sleep adapter around that policy. Windows Task
   Scheduler supports `WakeToRun` from sleep/hibernation; verify this machine's
   sleep state, wake-timer/power policy and task execution identity before claiming
   support. Do not assume shutdown wake, unlocked desktop, network readiness or
   native-client authentication. Waking Windows does not resume a cut-off PyCharm
   agent; a separate authorized CLI worker must load the saved task/context.

Keep neutral admission/resource policy in `ai_orchestrator`, source-specific
authentication/quota access in `ai_provider`, and Windows power/process execution
in the application/OS adapter. Reuse ADR-039's supported scheduling contracts and
existing application-owned persistence where applicable; its current foreground,
research-first scope does not authorize arbitrary background coding jobs. New
task types, recovery behavior, persisted contracts and autonomous power/spending
authority require explicit design and owner approval before implementation.

Acceptance should cover chat/controller interruption, retained running tasks,
stale/reused process identities, concurrent writers, missed wakes, stale or wrong
reset metadata, capacity still unavailable after reset, expired grants, owner
return/cancellation and bounded cleanup failure. Never resume a consumed trial
or convert missing tests/reports into success. Before rollout, decide one simple
owner command that cancels both pending work and power actions; today's
`cancel-sleep.cmd` cancels repository sleep timers only.

Windows references: [WakeToRun](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-waketorun)
and [system wake-up events](https://learn.microsoft.com/en-us/windows/win32/power/system-wake-up-events).
These establish OS mechanisms, not verified workstation readiness.

## Resource and scheduling constraints

Owner authorization (2026-10-16, attended): for the current near-end-of-day
workflow, use the remaining allowance of already approved sources whose verified
reset occurs before 10:00 local time, including repetitive access checks. This
supersedes the one-attempt limit and preference to stop after a useful matrix
for this authorization. Prefer useful authorized work, then bounded, paced
public/synthetic checks; stop at exhaustion, reset, account refusal, uncertain
price/privacy, or the run's explicit attempt/time bound. Do not consume the new
post-reset allowance under an expiring-allowance grant. Existing source admission,
zero-price, privacy, approval and Production Free guards remain. This does not
renew consumed acceptance trials, authorize paid fallback, or install a recurring
scheduler, unattended window or sleep action.

Owner-requested backlog (2026-10-14): add a low-priority provider-route access
sweep to the independent supervisor workflow after baseline CLI goals. When no
higher-priority authorized work needs the expiring daily allowance, consider one
simple public/synthetic request per explicitly allowed route about one hour before
its verified provider reset. Store the provider's UTC reset and convert local time
using the time-zone database; OpenRouter's current UTC-day allowance resets at
00:00 UTC (02:00 Warsaw on October 15, 2026), so its one-hour-before slot is
23:00 UTC (01:00 Warsaw on that date). Other providers' resets must be verified
separately; do not assume a shared reset or independent per-model allowances.

Owner clarification (2026-10-20): automatic awareness of available allowances and
approaching resets belongs in `ai_orchestrator`, after the CLI baseline. Reuse
provider-owned quota observations; keep provider authentication and HTTP access
in `ai_provider`. Future orchestration should surface useful authorized work
before an allowance expires, preserve planned reserves, and distinguish metadata
checks from requests that generate model output. This is a backlog priority, not
authorization to implement a scheduler, recurring checks or automatic spending
during the baseline work. Existing source, privacy and billing gates still apply.

Before admission, refresh remaining quota, preserve a reserve for planned
acceptance, and check price, entitlement, capability and data-policy readiness.
Allow at most one completion attempt per selected route per authorized run, with
bounded output/time, pacing, no automatic retries or paid/model fallback. Save
attempt/cap, actual answer/correctness, HTTP/provider error evidence, usage/cost,
quota observations and cleanup independently. Connection/access is not model
quality or CLI acceptance. Unknown quota/reset/privacy or missing unattended grant
defers that route. Do not reuse consumed trials, wake/sleep the workstation or
create recurring tasks just because this workflow is in the backlog. Scheduler
implementation and future live windows still need their normal approved scope.

Source-checking rule: investigate the failure boundary before treating a provider
issue as source-wide. Gateway model availability can differ by upstream provider;
check alternative models/endpoints/options using current official metadata and
safe diagnostics, then bounded live comparisons only within the owner-authorized
scope. Preserve separate gateway/model/upstream/account findings and do not infer
quality or automatically alter routing. The shared source-state reference records
the diagnostic workflow and admission constraints.

Live acceptance requires an explicitly selected compute window. Do not start
inference, clients for model work, runtimes or sustained local workloads merely
because this roadmap was approved. Prefer offline validation and synthetic clients.

The configured supervised research acceptance passed through the scheduler in
an owner-selected window on 2026-10-04, including verified tokenizer admission,
report receipts and durable final handoff. Its refinement attempts made no report
progress, and search failure remained recorded. This establishes plumbing, not
model-quality improvement or continuous use of the full allocated budget.
Selecting that completed task again was refused before worker execution with
"Only planned tasks are eligible to start"; terminal tasks are not replayed.
Long local model work must wait for an explicitly selected
compute window and a supported queued task. ADR-039 does not authorize inserting
arbitrary coding or acceptance commands into that queue. Record unsupported live
cases as pending work, rather than presenting them as executable queue entries.

## Session handoff and milestone updates

2026-10-15 attended follow-up: a fresh successor acceptance preparation implements
ordinary tool/schema correction, syntax feedback without executing uninspected
code, effect inspection before another write, and equivalent-error stall detection
using the existing CLI/owned-process components. Its complete scripted offline
edit/test/repair/report/frozen-review workflow passed independent tests, the host
oracle and cleanup. The unattended branch records a slice blocker requiring
wider-plan selection; this is not an independent work supervisor. Live entry
requires fresh route/privacy authorization and launch sealing.

A separate launch successor now pins a clean production HEAD, fresh original
inputs and unchanged recovery/owned-process code. Default execution is offline;
the launcher creates no grant. Date expiry, an exclusive attempt sentinel,
birth-matched controller checks and the original total deadline prevent automatic
replay or renewal. A complete scripted offline workflow and launch refusal checks
passed with owned cleanup. The proposed existing-source public/synthetic trial
still needs a fresh data-collection exception and exact live grant. No provider
request, account scan or production runtime change follows from this preparation.

The subsequently approved live attempt stopped in its first metadata worker:
zero completion posts, responses or tool effects, unchanged original inputs and
verified owned cleanup. It supplies no coding-quality or availability result;
the original metadata HTTP observation/stderr is unavailable. Local process tests
found the launch guard's direct-parent assumption incompatible with this Windows
virtual-environment launcher. Its fake offline workflow had missed the positive
live-only process branch. A separate successor now verifies controller birth and
allows one verified Python-launcher hop, retaining WindowsJob ownership. Actual
no-network process tests exercise both that gate and real seal validation before
a local sink. Consumed evidence remains unchanged; any successor needs a fresh
input/path/attempt grant. Baseline remains INCOMPLETE.

The next approved public/synthetic attempt reached 14 completions and one repair
cycle, with five visible tests passing. It stopped before executing a proposed
tool outside the fixture scope. No final model report or frozen review completed;
the exact refused tool name was not retained. All owned children exited with
verified cleanup. Separate poststop host checks passed the five tests and bounded
oracle, preserving three original methods, but do not complete the missing model
phases. This is partial coding evidence and a failed acceptance, not parity.

Poststop investigation also reproduced a verifier defect: the oracle reloaded
original methods from the edited live test file, losing the companion-test
baseline. Separate local repair verifies the prepared Git-index snapshot against
the sealed input hash before reusing AST inspection and the existing oracle.
A fresh offline successor also retains refused tool name/phase without arguments
or raw continuation. Safety boundaries remain unchanged; consumed evidence is
immutable. Another live attempt requires fresh inputs, sealing and a one-use grant.

The next approved attempt recovered from a real edit-anchor error after reading
actual effects, repaired the source and passed five visible tests. It stopped at
14 coding completions because six of the 20 total calls were reserved for review.
No final report or frozen review completed; this is failed acceptance despite
passing poststop tests/oracle and verified owned cleanup. No tool was refused.
The observed sequence needed another coding completion before entering review;
do not confuse the configured total with the smaller coding allowance. A modest
increase to the total call allowance is proposed for owner decision, retaining
the review reserve, tool/time bounds and quality floor. No grant is extended.

The owner approved a fresh 24-call attempt with unchanged tool/time bounds and
review reserve. Its edit phase completed with a report, preserved original tests,
three companion tests, independent six-test/oracle passes and one repair cycle.
Frozen review performed the required reads, status/diff inspection and passing
test run, then repeated unchanged reads without producing its substantive report.
The attended continuation checkpoint expired at the original review deadline;
later chat approval was not applied and did not renew the attempt. All owned
children exited with verified cleanup. Acceptance remains failed/incomplete.
Local trace replay confirms required review observations preceded the repeated
reads; it does not establish why the model repeated them or prove quality parity.

A fresh standalone frozen-review fixture is now prepared locally to isolate the
missing report, with an explicit completion instruction, six passing tests,
bounded oracle and write refusal checks. Source and tests are host-prepared;
there is no fabricated coding history or model authorship. This is a proposed
narrow acceptance question, with no live entry point or inference grant. A
review-only success would not pass the consumed workflow or establish parity.

The owner subsequently approved one focused review attempt. It completed in seven
replies with six tool calls, a substantive final report, six passing tests, no
writes or stall checkpoint, unchanged frozen inputs and verified owned cleanup.
Independent host assessment accepted the report against the actual source, diff
and observations. This answers the narrow review question only; the earlier
workflow remains failed, and neither prompt causality nor general parity is
established. A fresh integrated preparation retains complete coding history and
adds the explicit review completion instruction. The subsequently approved
integrated attempt repaired the source and a mistaken new test expectation,
preserved the original tests, and passed seven tests plus the independent bounded
oracle. It returned no final edit report, so frozen review never completed and
acceptance failed. Passing code checks do not supply those missing model phases.

A fresh history diagnostic then refused at the exhausted-quota guard before any
completion request. It provides no live history-interpretation or model-quality
evidence. Both attempts and their grants are consumed. On 2026-10-16, closeout
preserved their receipts and verified owned cleanup without further inference.
The local CLI fix retains transient full loop messages on empty or textual final
report errors, preserving instructions, tool receipts and earlier effects for
inspection. These errors remain non-retryable; no recovery, routing, privacy or
quality policy changed. Baseline remains INCOMPLETE, with no model grade,
production default or fallback quality promotion.

The fallback audit identified ADR-032's counts-only contract. The owner then chose
context-aware transfer in ADR-059: eligible native coding routes receive complete
observable mid-turn history only with at least 20% destination headroom after input,
tools, output and framing; otherwise retain the bounded handoff. Unknown effective
capacity, including unmeasured external-client context, uses the bounded handoff.
Provider-private reasoning and saved/emergency handoffs remain excluded. Existing
quality/privacy/billing/approval gates still apply. Implementation is validated
offline; baseline remains INCOMPLETE. No live quality, availability, default
promotion or new inference grant follows from these checks.

At the 2026-10-04 implementation checkpoint, the full offline suite passed:
857 tests, seven live checks skipped. Ruff and Pyright passed. Separate live checks
described above ran only during the owner-selected compute window. No new runtime
dependencies or user-wide permission settings were introduced. The owned Ollama
runtime was stopped and its listener was verified absent after live work finished.

This file is the tracked milestone source; ADR-040 preserves the decision.
Update milestone status only with implementation and acceptance evidence, naming
any deferred live checks. Keep the ignored `CURRENT_CONTEXT.md` current with the
latest checkpoint, active milestone, imperative next action and completion test.
Private research plans supplement these documents but must not be required to
recover the approved scope in a new session.
