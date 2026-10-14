# ADR-056 - Measured-prefix native admission prototype

**Status:** Accepted prototype and experimental CLI opt-in; broader readiness incomplete
**Date:** 2026-10-12

The owner approved the recommendation to prototype provider-reported prefix
counts offline first, followed by local counting comparisons and compatibility
checks. The existing absolute UTF-8/2 gate remains the default. This does not
approve dropping required instructions/history or weakening acceptance checks.

Observed Qwen requests estimated 38,641 input tokens but reported 15,461; the
next request was refused on its estimate. Its actual count is unknown. The
purpose is to investigate false refusals that obstruct continuous CLI work.

Retain only an in-memory prefix fingerprint, prefix length and reported count,
bound to model, endpoint, installed digest/runtime, schemas and request options.
Estimate appended messages conservatively, reserve output and framing, and
fall back to the absolute gate on invalid/missing usage or identity changes.
Do not persist prompt content, reasoning or effects in this state. No automatic
replay, dependency, external processor or service is introduced.

Keeping the absolute gate avoids count-state complexity but may reject useful
work despite available context. Measured prefixes may reduce refusals but remain
estimates: provider cache/count semantics and template boundary changes require
actual checks. Successful transport alone does not establish model quality.

The prototype must disable provider-side truncation/context shifting for its
local verification, so a sizing mistake fails rather than silently removing
instructions. Default behavior changes require validated evidence and a separate
readiness assessment. Streaming may retain the absolute gate during the prototype.

## Bounded validation

Offline invalidation/privacy/overflow checks pass. Full workspace validation:
1,992 passed, 28 skipped; modified Python files pass Ruff/formatting; full
Pyright reports zero errors and warnings. Local repeat counts were stable and
appended estimates exceeded observed input counts on both pinned models.
Provider-side overflow refusal was verified with preservation enabled. Strict
read/edit/preservation/final-marker fixtures passed for Qwen in both thinking
modes and GPT-OSS with continuation replay.

Qwen's CLI pilot failed: timeouts, indentation damage and lost assertions. Its
generated file was saved and the exact pre-pilot tests restored. GPT-OSS then
completed the diagnostic-test edit/check/review case with the complete prior
chat retained, 16 GPU layers, 45 new calls and 1,795.47 seconds in a fresh
30-minute launch. It recovered from numerous missing/ambiguous edit anchors;
this is not a general coding-quality improvement or controlled benchmark.
The owner subsequently reported gaming during these runs. Historical speed
observations are confounded and cannot justify routing or hardware changes.

All original assertions and tests survived; marker usage/absence coverage was
model-authored. Host task/frozen checks passed 38 tests; model review inspected
the scoped diff and actual results, with one factual wording correction. Review
did not alter the checked file. Runtime cleanup and source/.env/frozen hashes
were verified. No cloud inference, install, commit, merge or push occurred.

At the prototype checkpoint the release-scope choice remained pending: expose an
experimental CLI opt-in, retain harness-only evaluation, or change the default.
The recommendation was explicit opt-in before broader validation.

## Experimental CLI exposure approved (2026-10-12)

The owner accepted that recommendation after reviewing its trade-offs: an
explicit opt-in makes the prototype usable in real CLI sessions while retaining
the current default; harness-only support would preserve the public interface
but restrict use to controlled tests. This approval changes the release scope,
not the default policy or acceptance requirements.

Expose `--experimental-measured-prefix` for executed native Ollama coding tools.
Reject incompatible uses rather than silently ignoring the flag. Do not persist
the option or prefix state; callers must select it for each launch/resume. Each
native loop owns its in-memory anchor, so a new loop still admits its first full
request using the absolute gate. Streaming and invalid anchors retain that gate.
No research routing, external processing or tool permission change is approved.

Software checks and live model-quality acceptance must remain distinct. The
failed coding/review attempts do not establish broader readiness.

## Public opt-in validation (2026-10-12)

The CLI option is implemented. Offline checks cover the default, parser/help,
native argument propagation, incompatible modes/providers, selected hosted-route
refusal and unchanged context limits. The fresh local CLI pilot activated the
experiment through the public flag without a private field override. It completed
37 observable model calls in 1,793.41 seconds with a clean exit and owned cleanup.

Two model-authored tests survived host-guided correction and actual host checks:
wire metadata with the option disabled/enabled, complete request-metadata
immutability, and absolute refusal when provider usage is unavailable. Behavioral
counterfactuals distinguish ignored opt-in and available versus unavailable usage.
All original test bodies and the scoped production source were preserved. The
model reviewed supplied source/tests and actual results without further edits;
its claim that context length is experimental-only was corrected in the host
assessment. Both modes set context length; the experiment controls preservation
and prefix admission. The broader CLI quality goal remains incomplete.

Final software gate: 2,134 passed, 22 skipped across workspace, Council and
job-search suites; Ruff, formatting and Pyright passed. This establishes bounded
integration and recovery evidence, not autonomous coding parity or a speed gain.
