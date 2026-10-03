# ADR-037 - Source Evidence for Research Review

**Status:** Accepted; implemented
**Date:** 2026-10-02

## Context

The game-closed research run completed 29 refinement attempts and 30 formatted
local reviews. Its structure and current-run receipts passed, but manual checks
found unsupported claims that the reviewer missed. The reviewer currently sees
the report and retrieval receipts, without the retrieved source text. A receipt
establishes execution rather than whether a source supports a claim.

The run also retrieved five distinct final URLs despite a four-source prompt
instruction. Current tools do not enforce a distinct-source quota. Changed report
bytes/source digests establish activity, not semantic improvement.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Bounded in-memory fetched excerpts | Enables source/claim comparison using existing retrieval, without new page-body persistence | Adds excerpt-selection and context-allocation requirements; remains imperfect model judgment |
| Reviewer retrieval tools | Independent retrieval and checking | Expands tools/network surface, latency and request counts |
| Existing advisory review plus manual audits | Simple existing boundary | Unsupported claims can pass automated review |

## Decision

The owner accepted the recommendation to provide bounded in-memory fetched
excerpts to the local research reviewer. Implementation was initially deferred
and resumed on 2026-10-03 under the owner's unattended-work instruction.
No reviewer retrieval tools, new external service,
new fetched-page-body persistence, or smaller reviewer context/output allowance
is approved by this decision. Existing report/receipt validation remains intact.

The owner subsequently approved all four presented recommendations (D1-D4):
bounded coverage across fetched sources, advisory grounding findings followed by
evaluation, an optional per-run enforced source limit unset by default, and
accounting by distinct successfully fetched final URLs. These are accepted
policies for the implementation. A blocking grounding gate remains a
future decision after evaluation, not an unresolved prerequisite for this work.

On 2026-10-02 the owner explicitly requested decision recording and preparation
of tomorrow's handoff, with no implementation now. Subsequent replies choosing
policies during this session must be recorded without starting implementation
unless the owner explicitly changes that instruction.

## Reason

The owner agreed with the bounded-excerpt recommendation after evidence showed
that advisory reviews missed unsupported claims. The owner's stated priority is
quality over speed. No further personal rationale was supplied. This records
agreement with the recommendation without inventing additional owner motivations.
The owner then explicitly approved all four policy recommendations. Their trade-offs
are preserved below; no separate rationale for each policy was supplied.

## Consequences

The intended reviewer will receive actual bounded source text with source
identity and explicit coverage/truncation limits, through existing local
inference. Receipts and excerpt text must remain distinguishable from model
claims. No broader factual-reliability improvement is established until evaluated.
Missing source coverage must not be presented as proof that a claim is false.

Inspect existing transcript/log behavior before implementation: in-memory source
retention does not by itself guarantee that downstream prompt logs contain no
excerpts. Do not silently add new persistence or change approved full-query
receipts. Memory-only evidence will be unavailable after process exit; restart
retrieval/persistence behavior is not approved by this ADR.

## Accepted related policies

The owner approved all four recommendations on 2026-10-02. Tables retain the
alternatives and trade-offs; approval does not claim these policies are implemented.

### D1 - Excerpt coverage

| Option | Pros | Cons |
|---|---|---|
| Bounded coverage across fetched sources (accepted first implementation) | Predictable shared budget; every source can receive coverage; simple allocation | Important passages can fall outside retained excerpts |
| Claim-targeted passage selection | More relevant passages per context token | Additional selection logic can miss context or bias evidence |

Use one total evidence budget with explicit omissions/truncation; exact bounds
must be investigated against the current 32k review capacity. Do not approve
smaller report evidence or a larger model context implicitly. Balanced coverage
is a starting policy, not a guarantee of sufficient coverage for every claim.

### D2 - Whether grounding findings block completion

| Option | Pros | Cons |
|---|---|---|
| Start advisory, evaluate, then decide on a blocking gate (accepted) | Measures false positives/coverage before changing completion semantics; findings still guide refinement | Unsupported claims may remain in a technically completed run |
| Add a blocking grounding verdict immediately | Stronger automatic response to unsupported verified claims | Imperfect review can reject correct claims, especially when excerpts omit supporting text |

Accepted policy: evaluate source/claim findings separately from existing structural
checks, including supported claims, unsupported claims, inferred/unknown labels,
and missing source coverage. A future blocking gate requires an explicit decision
after evaluation; it is not silently pre-approved here.

### D3 - Enforceable source limit

| Option | Pros | Cons |
|---|---|---|
| Optional per-run tool-enforced limit (accepted) | Enforces an explicit owner limit across refinement cycles; can be unset for broad research | Adds configuration and tool policy; a low cap can restrict useful follow-up |
| Keep a prompt-only limit | No new configuration or implementation | Models can exceed it, as observed |

Accepted policy: an optional per-run maximum, unset unless supplied. Four was the
acceptance request's limit, not an approved global default for all research.
This new configuration/behavior contract is approved for deferred implementation.

### D4 - What consumes an enforced source limit

| Option | Pros | Cons |
|---|---|---|
| Distinct successfully fetched final URLs (accepted) | Redirect aliases and repeated reads need not consume extra slots; failed links do not prevent recovery | Enforcement must handle redirects/deduplication; does not itself cap HTTP attempts |
| Distinct requested URLs, including failures | Simple accounting before retrieval; bounds attempted destinations | Broken links and aliases consume slots and can prevent useful retrieval |

Accepted policy: successful distinct final URLs count; repeated sources do not
consume additional slots and failed fetches remain governed by existing action/
time/request bounds. Inspect how to enforce the cap before obtaining an additional
source body and report exhaustion honestly. Do not use a source quota as a claim
that all network requests are bounded to that number.

## Implementation and validation status

Implemented on 2026-10-03 after the owner explicitly resumed unattended work:

- `ai_agent.research_evidence` retains the latest thirty source excerpts, each
  bounded to 12,000 UTF-8 bytes. Local review shares up to 16,000 text bytes,
  balanced across covered sources and redistributed when a source is short.
  JSON framing/escaping can lower the text allocation to fit the existing
  64,000-byte request bound with 8,000 bytes reserved for review/task framing.
  Existing 24,000-character report and thirty-receipt windows are preserved.
  Exceptionally large existing report/receipt/task framing may still exceed the
  request bound even without source text; no larger context is implicitly adopted.
- Source identity includes final URL, digest, and fetch time. Missing text,
  source omissions, extraction truncation, and fetched-body truncation are explicit.
  Reviews and repairs share the process-local cache; recomposition cannot recover
  text from persisted receipts. Grounding findings remain advisory and use the
  existing review/refinement flow, without a new semantic gate.
- `--research-max-sources N` / wrapper `-MaxSources N` is optional and unset by
  default. Successful distinct final URLs count across turns/refinements. The
  protected HTTP fetcher checks the resolved successful final URL before reading
  a new body. Failures do not consume slots; repeated URLs remain eligible.
  Redirect resolution may still issue requests. Existing stage metadata retains
  the supplied maximum and receipts, permitting accounting to be reconstructed
  without reconstructing excerpt text.
- Logging inspection found no existing saving of reviewer prompts or page bodies.
  Existing tool previews, model replies, reports, and persisted review findings
  can contain quotations. This implementation adds no raw-source persistence and
  does not promise quotation-free existing outputs.

The paired local source-grounding evaluation used twenty labeled fictional
claim/source cases across supported facts, unsupported verified claims, honest
inferences/unknowns, and missing coverage. Artifacts are ignored under
`artifacts/research-grounding-20261003/`. Both variants parsed 19/20 responses;
the receipt-only baseline matched the source-truth category in 4/20 cases and
the excerpt variant in 6/20. The excerpt variant detected 2/4 unsupported verified
claims, rejected honest unknowns, and missed all four missing-coverage categories.
These synthetic, evaluation-prompt results establish neither broad factual
reliability nor an approved blocking gate. Baseline reviewers cannot know hidden
source truth; these counts are descriptive rather than a fair proof of quality
improvement. No production reviewer/model/context/output change was adopted.

Focused contract tests, full software checks, and context-capacity probes are
recorded in the run artifacts and local handoff. Future performance tests still
require advance notice as described in `docs/workflow.md`.

Capacity probes retained the full report window and existing reviewer settings:
four sources returned a valid review with 8,826 provider-reported input tokens;
thirty sources fit the request-byte bound but timed out at 300 seconds. Successful
review at that larger scale remains unverified. This is a recorded limitation,
not evidence of a GPU defect or authorization to reduce report coverage, change
the reviewer, increase timeouts, or introduce a blocking gate.

### Follow-up prompt/evidence evaluation (2026-10-03)

The owner approved another grounding-quality slice retaining the existing local
DeepSeek reviewer, 32,768-token context, 1,200 output tokens, request bounds,
timeouts and advisory policy. Implementation separates source evidence, report
claims and completion-summary claims in a research-specific prompt. Quoted source
passages precede report claims; source identity, truncation and missing coverage
remain explicit. Five fictional calibration examples explain confidence labels.
Non-research scrutiny retains its existing prompt. No source-cache budgets,
provider routing, persistence or semantic completion gate changed.

The evaluation made 120 local calls across forty distinct fictional cases: twenty
development cases compared a frozen excerpt-aware baseline with three prompt
variants, followed by twenty fresh cases comparing that baseline with the selected
calibrated variant. Alternatives were rejected for excessive false rejections or
invalid response format. Prepared requests and raw responses were retained in
ignored `artifacts/research-grounding-quality-20261003/`, with snapshots and an
audit README. No actual fetched page bodies were persisted by this evaluation.

In both the development comparison and fresh holdout, the selected variant and
baseline parsed 20/20 reviews and accepted 4/4 supported assertions. Acceptance of
honestly labeled unknowns changed from 2/4 to 4/4 in development and 0/4 to 4/4 in
holdout. Both variants falsely approved 2/4 unsupported verified claims in each
set; development errors affected different cases, including a regression. The
selected holdout response approved retaining request bodies while quoting
"Request bodies are never retained." Another response fabricated a source quote
from a candidate inference. Missing-coverage judgments remained inconsistent.

These are verdict outcomes and manually audited examples, not overall semantic
accuracy. Most responses omitted an evaluation-only classification marker, so
the scripts' `correct` totals measure marker compliance and must not be presented
as accuracy. Cases are small, correlated synthetic fixtures rather than full
research reports or a prompt-injection benchmark. The selected prompt provides a
limited, reproduced uncertainty-handling benefit; broad factual improvement and
safe automated semantic gating remain unestablished. Software validation passed:
584 tests, seven skips, Ruff lint/format and configured Pyright checks.

A further comparison of alternative reviewers would require a new scope decision;
no default-model switch is authorized by this evaluation. Provider activation is
not required for the completed local slice. The prior thirty-source timeout log
shows 16,509 input tokens within the configured context and approximately 169
decoded tokens before cancellation; it does not establish context overflow or a
hardware cause.

### Owner-authorized local reviewer comparison (2026-10-03)

The owner approved comparing alternative existing local reviewers while keeping
production defaults unchanged. Their stated purpose is supporting a variety of
local models and finding a model that performs well for the research task. This
evaluation addresses grounding review, not autonomous search or report synthesis.
It uses the same provider-neutral request/configuration interface for all models.
No model download, hosted call, dependency, application-code change, catalog
ranking change or semantic gate was introduced.

Ignored artifacts under `artifacts/research-model-comparison-20261003/` preserve
production snapshots, model digests/quantization, fixtures, every prepared request
and raw response, timings, parser outcomes and a visible-response semantic audit.
There were 282 local calls: sixteen screening calls, 160 matched forty-case calls
across four models, forty additional matched calls for Qwen 3 with thinking
disabled, sixty fresh-case calls across the three finalists, and six full-report
capacity probes. The corpus contains sixty distinct short fictional cases and
two capacity fixtures. No real search/retrieval or new production logging occurred.

All requests retained 32,768 context, 1,200 output tokens, temperature 0.2 and a
300-second timeout. Default thinking was used initially. One Qwen 3 call exhausted
its output budget in thinking and produced no visible review. The existing adapter
option `ollama_thinking=False` was then tested as a separate experimental variant;
it was not adopted for production. The prompt was not tuned separately per model.

Matched forty-case verdict outcomes (eight cases per category):

| Installed model / setting | Valid format | Unsupported facts falsely passed | Honest unknowns passed | Tentative inferences passed | Median seconds |
|---|---:|---:|---:|---:|---:|
| DeepSeek Coder V2 16B, Q4_0 | 40/40 | 4/8 | 7/8 | 8/8 | 12.79 |
| Qwen 2.5 Coder 14B, Q4_K_M | 40/40 | 0/8 | 5/8 | 7/8 | 7.46 |
| Qwen 3 14B, Q4_K_M, default thinking | 39/40 | 0/8 | 7/8 | 8/8 | 13.39 |
| GPT-OSS 20B, MXFP4, default thinking | 40/40 | 0/8 | 7/8 | 8/8 | 8.85 |
| Qwen 3 14B, Q4_K_M, thinking disabled | 40/40 | 0/8 | 8/8 | 8/8 | 6.38 |

Every variant accepted all eight supported facts. Qwen 3's missing unknown verdict
was a thinking-only truncation, rather than a delivered false rejection. These
are verdict outcomes, not overall semantic accuracy or self-assigned model scores.
The prior evaluation-only category marker is not used to compute these results.

The three finalists each returned valid reviews with expected verdict dispositions
on all twenty fresh two-source cases, without the classification-marker instruction.
They accepted supported facts, honest unknowns and reasonable tentative inferences;
flagged unsupported verified claims and unavailable-text claims; and rejected an
inference that contradicted explicit weekday restrictions. All ignored the embedded
source instruction in the tested Nacre examples; this is not an injection benchmark.
Fresh medians were GPT-OSS 9.25s, Qwen 3 default 15.41s and Qwen 3 thinking-disabled
6.56s. All three returned valid reviews identifying the contradiction in both
24,000-character report probes with four/thirty sources, unchanged evidence bounds
and approximately 10,800–17,200 input tokens. Single padded capacity probes, with
loading/cache differences, establish completion rather than a speed ranking or
realistic large-report reliability. The prior DeepSeek timeout remains a separate
observation; this comparison does not establish its hardware cause.

Technical recommendation, not an accepted default: Qwen 3 thinking-disabled for
best observed verdict/format/speed under the current bounded review budget;
GPT-OSS as the stronger explanation/correction alternative. Qwen variants still
confuse source silence with contradiction and sometimes suggest confidence labels
outside the report contract. GPT-OSS falsely rejected one honest unknown and
sometimes misattributed a detail between sources or confused unavailable review
text with failed retrieval. Good verdict totals do not establish fully correct
explanations or safe automated factual gating. The cases are small, correlated
synthetic families and single stochastic draws, not a universal model ranking.

Validation checked all 282 records for complete counts, identical case messages,
unchanged request bounds, local-only privacy, model identity and re-parsed format.
Focused adapter/evidence/research tests passed (110 passed, one skipped); benchmark
scripts passed Ruff lint/format. Production prompt/cache/execution hashes match
the pre-comparison snapshots. Adopting a new research-review model/preset remains
an owner decision; default selection and advisory completion policy are unchanged.
