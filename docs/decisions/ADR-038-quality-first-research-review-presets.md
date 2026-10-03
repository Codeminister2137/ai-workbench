# ADR-038 - Quality-First Research Review Presets

**Status:** Accepted; opt-in integration and representative audit complete; sustained acceptance incomplete
**Date:** 2026-10-03

## Context

The local reviewer comparison favored Qwen3 thinking-disabled for short reviews
under a shared 1200-token generation cap. Both Qwen modes rejected the tested
unsupported facts and matched fresh verdicts. One thinking-on review exhausted
the generation allowance before producing final content. Short fictional cases
and padded capacity probes do not establish a general research-quality ranking.

The owner questioned whether disabling thinking could overfit these measurements.
The owner then approved preserving both modes, quality-first per-review selection,
and the D1-D5 planning recommendations, subject to zero financial charges. The
owner clarified that 1200 tokens is not a hard product requirement, research
usually has more time, and comparable performance testing is still valuable.

## Options considered

| Choice | Benefits | Trade-offs |
|---|---|---|
| General thinking-off default | Lower measured short-review latency; avoids scratchpad exhausting a small allowance | Broader quality effect is unmeasured; may remove useful multi-step reasoning |
| Manual presets only | Small implementation; explicit user control | Does not provide automatic per-review selection |
| Explainable deterministic selection, accepted | Testable and cheap; conservative defaults; retains overrides | Rules may miss savings and need workload evidence |
| Model-selected mode | Flexible classification | Adds latency and another unproven judgment |

## Decision

1. Implement neutral capability-aware review/preset selection in ai_orchestrator.
   Map selected presets to supported controls at the provider boundary. Preserve
   model/mode overrides, existing configuration compatibility and bypass paths.
   Unknown complexity selects a deliberative supported preset. Fast presets need
   task-specific evaluation support. Do not hard-code a global model ranking or
   assume all models expose Qwen-style boolean thinking controls.
2. Authorize controlled tuning of generation allowances from 2048 to 8192 tokens,
   request timeout at most 300 seconds, and final-review reserve of ten percent
   capped at 300 seconds. Clamp calls to remaining wall time and context headroom.
   Preserve source/report evidence bounds and explicit context settings. Permit
   one bounded same-or-stronger retry for output truncation when resources permit.
   These bounds are not claims of optimal settings or mandatory token consumption.
3. Evaluate 24 diverse public-source review tasks, with eight cases held out by
   topic family, against Qwen3 thinking-on/off and fixed GPT-OSS20B. Assess source
   attribution, explanations and corrected claims as well as format/verdicts.
   Preserve a controlled comparison before assessing tuned supported presets.
4. Permit selected public-source excerpts, benchmark requests and raw local-model
   responses in ignored local evaluation artifacts for reproducibility. This
   evaluation-only exception does not change production process-local source
   retention under ADR-037. Private documents are not research fixtures. Inference
   stays local; public queries/URLs use existing approved search/fetch routes.
5. Permit provisional research-only activation after software checks pass, all
   planned held-out calls complete, no critical false approvals or material quality
   regressions against the fixed baseline are found, and latency fits the limits.
   Incomplete/ambiguous evidence keeps the policy opt-in and conservative. This
   does not approve a blocking factual-certification gate or unrelated routing changes.
6. No charged calls, prepaid spending or billable escalation are authorized for
   this work. Enforce route eligibility and existing free-search safeguards even
   if credentials are present. If a free route cannot be established, use an
   already-approved free alternative or defer that operation. Key absence is not
   a cost-control guarantee. No new models, dependencies, services or credentials
   are approved by this decision.

## Time windows and execution authorization

The owner approved a four-hour general work/testing window, with bounded evaluation
and an up-to-110-minute live research acceptance when time permits. For the next
session the owner instead allotted approximately two hours. This planning session
starts no execution window or live test. The next session requires an explicit
resume instruction; plan that work for at most 120 minutes, respecting any shorter
remaining owner deadline. Do not infer a permanently renewed two-hour window.

Prioritize review contracts/integration, focused checks and a short comparable
pilot. The full representative evaluation and sustained live acceptance remain
incomplete until actually performed. Four-hour work and long live runs remain
planned under the user-started scheduling direction in ADR-039. Preparing a plan
or starting a session must not automatically launch those scheduled jobs.

## Owner rationale

Quality takes priority; the system should support varied local models and choose
appropriate modes. Time consumed by one task reduces time available for others.
The owner wants understandable comparable tests, with occasional long live runs,
and enough advance decisions to permit unattended implementation.

## Consequences

The legacy research reviewer retains its 1200-token allowance and two-minute
reserve. The opt-in quality-first policy supplies bounded generation and a
five-minute reserve cap; representative activation evidence remains incomplete.
Provider-neutral request planning and supported model presets need focused contract
tests. Existing receipt validation, advisory findings and sustained-refinement
policies remain. Performance findings remain provisional; passing a small set is
not proof of general factual reliability. Record contention before performance
testing. Defer only a newly disputed item and continue independent authorized work.

This ADR supersedes the earlier requirement to preserve the experimental output
cap and the comparison-only restriction for this approved research-review slice.
It does not change the accepted production source-retention boundary or create
a general permission for charged execution.

## Implementation checkpoint (2026-10-03)

Neutral review plans, catalog preset declarations, resource admission and local
native-mode mapping are implemented behind `--research-review-policy quality_first`.
Hard reviewer/mode overrides and an explicit native-default bypass are retained.
Auto final grounding uses supported deliberation; no production direct-mode
evaluation reference is currently supplied. Qwen3 maps to boolean thinking and
GPT-OSS deliberation to high effort, after checking installed capability/architecture.
One stronger length retry shares the review deadline and preserves evidence.
Conservative byte-based input bounds can refuse large payloads that a tokenizer
could fit; no evidence reduction or context enlargement is implied. Existing
sampling is preserved for controlled comparison. Default promotion remains pending
the full representative held-out evaluation; software tests or a pilot cannot
replace it. This checkpoint implements the accepted direction without changing
the historical rationale or introducing a persistent source store.

## Evaluation preparation checkpoint (2026-10-03 continuation)

The owner explicitly allotted a new 90-minute unattended continuation window,
deferring unresolved decisions until return. This is a specific allocation, not
an automatic renewal. The full 90-minute evaluation cannot fit after preparation
and handoff reserve; it and the 110-minute sustained acceptance remain planned.

Twenty-four public-source draft cases across six families are prepared in ignored
local artifacts, with SQLite and PostgreSQL reserved as the eight-case whole-family
holdout before inference. Twelve references retain only selected passages and
retrieval receipts. The runner checks digests, keeps expected findings out of
requests, rotates the three comparison variants, and records prepared requests/raw
responses before interpretation. Its planning path invokes no models. A completed
call matrix is distinct from the required explanation/correction quality audit.

Nine short local development calls across a contradiction, missing source text and
a source-embedded instruction all flagged their focal assertions. Visible URL,
confidence-label and precision defects remain, including an unsupported exact
10ms guarantee retained as an inference in a suggested correction and a missing-
source assertion called verified. Verdict rejection is not quality acceptance.
No heldout inference or default promotion occurred. The reports are shorter than
production guidelines and within-family variants are correlated; these limitations constrain
future interpretation. A separate 22,649-character report with 16,800 excerpt
characters was refused before inference at 32k context because its conservative
byte bound was 51,722. Full-size capacity is unresolved; evidence/context were
preserved. Accurate local counting or explicit resource-policy changes require
further investigation and the owner's decision.

When an installed runtime supplies `thinking.values`, explicit controls are now
checked for exact type/value membership to prevent silently using a default for
unsupported named efforts. Installed runtimes without that field retain
the existing capability/architecture path. This strengthens the accepted supported-
controls requirement; it does not change the quality ranking or sampling policy.

## Offline token-count investigation authorization (2026-10-03)

The owner accepted the recommendation to prototype accurate local counting,
with any concrete dependency proposed before installation. The conservative
production fallback remains until compatibility is verified. Local inference,
weight loading and runtime probes are currently prohibited by the owner.

`scripts/research-token-count-prototype.py` is an isolated diagnostic for a supplied
local tokenizer JSON and already rendered prompt. It downloads nothing, disables
padding/truncation, records file digests and explicitly labels runtime compatibility
unverified. No optional dependency has been installed and no actual tokenizer
count is claimed. A raw tokenizer count is insufficient to prove Ollama chat
admission: the installed tokenizer, template, generation prefix and mode-specific
serialization must match. Production policy and the frozen corpus are unchanged.

## Approved tokenizer and live evaluation checkpoint (2026-10-03)

The owner subsequently approved tokenizer installation and local models/long runs
for a three-hour session, superseding the earlier resource prohibition. Installed
`tokenizers==0.23.2` in the optional `research-token-count` dependency group using
a Windows wheel; no model weights, transformers or torch were installed. Public
upstream tokenizer assets are revision/digest pinned in ignored diagnostic artifacts.

All 72 planned review calls were attempted with frozen settings, including all
eight whole-family holdouts. Seventy-one parsed; one GPT baseline format failed.
Deliberative Qwen agreed with 24/24 focal dispositions, direct 23/24 and GPT 21/24
including the format failure. Direct returned pass on a false PostgreSQL scope
claim despite describing the contradiction in its issues. Citation, confidence
and correction defects remain across variants. D4 therefore keeps the policy
opt-in; Qwen deliberative is a defensible explicit acceptance preset, not a
general factual reliability claim. Mean review latencies were 37.82s, 19.67s and
38.29s respectively; this small correlated corpus does not establish general ranks.

The isolated two-message renderer matched all 72 recorded runtime input counts.
Installed vocabulary IDs/merges and diagnostic runner token IDs matched the
approved upstream assets for the tested inputs. These results apply only to the
inspected model/template fingerprints and modes. Production admission still uses
the conservative byte bound; asset resolution and production integration remain
an owner decision. No evidence is discarded to obtain admission.

The fully allocated 110-minute supervised acceptance was explicitly started with
GPT as primary and Qwen deliberative as reviewer. It saved a structurally valid
report, but stopped before refinement because conservative input admission refused
the review. It is INCOMPLETE, not a successful sustained run. Private artifacts
retain the actual failure and full report; the allocation was not shortened.

Supplementary plain/Unicode-whitespace probes matched GPT high-effort input counts,
but their 2048-token responses truncated and are not quality successes. Qwen native
default differed by two tokens from the candidate framing on both probes. The
prototype now refuses Qwen counting without an explicit boolean; it does not
guess an effective default. Original mismatches remain recorded. Explicit Qwen
on/off results and the frozen matrix are unchanged.

## Owner-approved production local-file configuration

The owner answered "Yes" to the proposed explicit optional local-file configuration
with compatibility guards and conservative fallback, then confirmed implementation
while prohibiting local models/live tests because PC capacity is needed. The choice
keeps acquisition and asset ownership explicit; no automatic cache/download or
bundled assets are adopted. The owner did not provide additional rationale beyond
approving the presented trade-offs. Auxiliary-panel changes remain deferred.

`--research-review-tokenizer-file` now optionally selects the local JSON for the
quality-first reviewer. Verified explicit Qwen on/off can use complete rendered
counts; library/runtime/model/template/tokenizer fingerprints and plain-message
shape are checked. Missing or unsupported inputs retain conservative admission
and record the fallback reason. GPT date-dependent framing remains conservative
because future runtime timezone/date agreement is not established by the measured
session. Shared rendering also serves the isolated diagnostic, avoiding duplication.
Preparation/counting consume the existing deadline; evidence/context/retry limits
and opt-in routing are unchanged. Offline replay matches the two recorded full-size
Qwen counts. Live integrated acceptance is deferred under the current resource
restriction; software correctness is not a successful sustained research run.
