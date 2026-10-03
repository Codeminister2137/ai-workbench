# Research review policy and token admission

[CLI guide](../repo-coding-assistant.md) · [Privacy and permissions](permissions.md)

Research uses a dedicated review prompt that separates source evidence from report
claims and the completion summary. Quoted source passages precede the candidate
report, with explicit coverage flags and unavailable-source URLs. Calibration
examples distinguish verified assertions from tentative inferences and honest
unknowns. A forty-case fictional DeepSeek prompt evaluation found more consistent
acceptance of honest unknowns, but no reduction in false factual approvals. Reviews still
invented supporting quotations and approved contradictions. Treat their grounding
judgments as fallible advisory findings requiring human verification; this is not
a demonstrated factual-accuracy improvement. These historical comparisons predate
the opt-in contracts below. Evaluation details are recorded in ADR-037.

A subsequent local reviewer comparison used the same forty cases across four
installed models plus a Qwen 3 thinking-disabled variant, then twenty fresh cases
for the finalists. Qwen 3 14B with thinking disabled had the best observed
verdict/format consistency and short-review latency within the existing budget;
GPT-OSS 20B was the stronger alternative for source explanations and corrected
claim wording. Both handled the four/thirty-source full-report capacity fixtures.
These are task-specific recommendations from synthetic evidence, not accepted
defaults or a universal model ranking. Production selection and advisory policy
remain unchanged. Autonomous search/report-writing quality was not compared;
native research execution separately requires a tool-capable model. See ADR-037
for results, remaining explanation errors and the bounds of the comparison.

ADR-038 review contracts are available as an explicit research-only opt-in:
`--research-review-policy quality_first`. The legacy reviewer/settings remain the
default because the completed representative audit did not satisfy the quality
activation gates. Auto selects a supported deliberative preset for final grounding;
direct mode requires workload-specific evaluation evidence in the neutral policy,
or an explicit mode override. Short report length does not establish simplicity.
When eligible peers have equal catalog quality, selection prefers a reviewer
different from the primary model; same-model review is identified in the reasons.
This is a conservative capability rule, not a new measured model-quality ranking.

Use `--research-review-model MODEL` and `--research-review-mode
auto|default|direct|deliberative` to override the reviewer. Overrides require the
opt-in policy and never bypass local/free route checks. `default` explicitly
retains the model's native mode, including models without declared reasoning
controls. Catalog `metadata.review_deliberative` / `review_direct` booleans
declare preset eligibility, and the provider verifies installed capabilities
before inference. Missing metadata never invents support. The current mappings
support Qwen3 thinking true/false and GPT-OSS deliberative high effort; GPT-OSS
direct mode is unsupported and produces a clear error. There is no cloud fallback.
When `/api/show` advertises `thinking.values`, the requested explicit value must
appear with the same type; an unsupported value cannot silently use the runtime
default. Installed runtimes without that field retain the capability and
architecture checks.

`--research-review-output-tokens` defaults to 4096 and accepts 2048–8192;
`--research-review-timeout-seconds` defaults to 300 and accepts positive finite
values up to 300. Each call also respects `--timeout-seconds` and the actual run
deadline. The whole review, including capability inspection and at most one
stronger length retry, shares a deadline no later than 300 seconds. A retry can
double the generation allowance up to 8192 with the same mode and unchanged
evidence if time/context remain. Truncation, an empty visible answer, a late
response or failed format parsing never becomes a pass or a weaker-mode fallback.
Sampling remains matched at temperature 0.2 pending controlled tuning.

The opt-in final reserve is ten percent of the run capped at 300 seconds;
legacy/non-research retains the 120-second cap. Context remains 32768 unless
an explicit Ollama resource profile supplies it. The adapter reserves framing
and bounds input tokens conservatively by UTF-8 bytes by default. Optional
`--research-review-tokenizer-file` supplies one explicit local tokenizer JSON for
the selected quality-first reviewer. Compatible Qwen on/off profiles use the
complete rendered input count; unsupported combinations retain the byte bound.
The conservative bound can reject large evidence that an exact tokenizer could fit;
it never shrinks source/report evidence or enlarges an explicit context to force
admission. Mode, route, decision reasons, effective allowances and retry outcomes
reuse existing scrutiny-stage metadata; source bodies and prepared prompts gain
no new production persistence. A small pilot cannot satisfy the rollout gates.

The pure `ai_orchestrator.scheduling.admit_task` contract checks explicit start,
positive required allocation, remaining monotonic time, planned status and
caller-validated execution constraints. It neither runs nor changes a task's
status. Non-fitting tasks remain planned. The application-owned SQLite scheduler
and strict selected ordering are implemented under ADR-039; generic cancellation
remains outside its scope. Long tasks require an explicit start.

`scripts/research-review-evaluation.py` plans the approved local comparison from
an evaluation-only public-source corpus. It requires 24 cases across at least
six topic families, eight held out by whole family, and matching context/sampling
settings. Source excerpt digests are checked before execution. Expected findings
are kept out of reviewer requests. Corpus excerpts and results stay in ignored
local artifacts under ADR-038; private documents cannot be benchmark fixtures.
Preflight validates every case/source field consumed by execution, including audit
findings and complexity, so a malformed late case cannot waste earlier model calls.
Case IDs use 1–64 letters/digits/underscores/hyphens and are unique ignoring case
to protect Windows output files. Source IDs are unique within a case. Explicit
missing coverage remains valid through an empty segment list and coverage description;
its retrieval receipt cannot supply missing source text.

Plan without starting inference:

```powershell
python -m uv run --no-sync python scripts/research-review-evaluation.py `
  artifacts\research-review\corpus.json
```

To explicitly start that selected task in a sufficiently long window, add
`--execute --available-minutes 110`. The runner reserves ten minutes for handoff
by default, counts preparation against the window, and requires the full
90-minute task allocation. A 90-minute overall window with that reserve is
refused without starting models. Each serial review rechecks its full configured
call allocation; a non-fitting next call stops this experiment with an incomplete
summary. This fixed experiment runner does not implement a general scheduler queue,
storage contract, skip policy or hard cancellation for arbitrary jobs.

The three variants are Qwen3 deliberative/direct and GPT-OSS native-default.
Variant order rotates by case, and development calls precede holdout. A fresh
output directory protects previous evidence. The runner records prepared requests
and raw local responses before parsing, including malformed responses and bounded
retries. `CALLS_COMPLETE` means all planned calls were attempted; format failures
still give a nonzero exit, and visible-answer quality audit remains pending.
Source attribution, claim scope, corrected confidence labels, critical false
approvals, baseline regressions and latency must be audited before considering
D4 activation. Software checks or shorter development pilots cannot satisfy it.

The prepared October 3 corpus uses correlated variants of six public-source
families and reports shorter than the production length guideline. A separate
22.6k-character report with 16.8k excerpt characters was refused at 32k context
under conservative byte admission. The approved tokenizer diagnostic subsequently
counted the same full-evidence requests at 11,304-11,889 input tokens and matched
all 72 matrix runtime input counts for the inspected templates. The opt-in production
counter is now implemented and replayed offline against recorded Qwen capacity
requests. Live acceptance of the integration remains deferred.

The October 3 matrix attempted all 72 cells; 71 parsed and one GPT baseline format
failed. Deliberative/direct/GPT focal agreement was 24/24, 23/24 and 21/24 including
that failure. Direct made a critical false approval on a heldout transaction-scope
claim. Citation/confidence/correction defects remain, so D4 keeps the policy opt-in.
These correlated short reports do not establish general factual reliability.

An isolated offline counter is available with the approved optional dependency:

```powershell
uv sync --group research-token-count
uv run --no-sync --group research-token-count python scripts/research-token-count-prototype.py `
  --tokenizer-file C:\path\to\qwen-tokenizer.json `
  --request-file artifacts\research-review\request.json `
  --template-file artifacts\research-review\qwen-template.txt
```

Diagnostic assets are local ignored artifacts, not bundled model data. The script
downloads nothing and performs no inference. Request counting accepts only the
inspected two-message model/template/tokenizer fingerprints and supported thinking
controls; Qwen requires an explicit boolean (native-default probes mismatched),
and GPT additionally requires `--runtime-date YYYY-MM-DD`. Arbitrary rendered
UTF-8 input can instead use `--rendered-prompt-file`. Padding/truncation are disabled,
complete input digests are recorded, and the output remains `PROTOTYPE_ONLY` with
runtime compatibility unverified by the script itself. Separate recorded runtime
comparisons supply the evidence; a diagnostic count alone cannot admit production input.

Production exact counting additionally requires Ollama 0.32.5, tokenizers 0.23.2,
the inspected GGUF blob and template digest, the pinned tokenizer digest, two plain
system/user messages and explicit Qwen on/off. Unknown versions/assets/templates,
extra model history/system instructions/adapters, missing dependency/file and
Qwen native default use the conservative bound. GPT remains conservative because
its runtime date/timezone agreement is unverified outside the recorded session.
The diagnostic can still count GPT with a supplied date. No private runner endpoint
or automatic download is a production dependency.

The tokenizer path is relative to the invoking working directory unless absolute.
The option requires `--tool-profile research --research-review-policy quality_first`.
For a future explicitly started Qwen-deliberative run, append
`--research-review-tokenizer-file C:\path\to\qwen-tokenizer.json`.
The wrapper forwards this through its existing extra CLI arguments. Stage metadata
records `input_bound_method` and any `tokenizer_fallback_reason` without saving
prompt/source bodies. Version inspection, counting and retries share the review
deadline; fallback never trims evidence or increases context. Software replay is
not live acceptance, and runs remain planned while local compute is unavailable.
