# ADR-049 - Continuous Coding Chat

**Status:** Accepted direction (2026-10-09); migration acceptance incomplete

## Context and alternatives

The owner requires ongoing development conversations in the project CLI with
results comparable to or better than the current assistant. Per-request coding
invocations and provider-only saved chat do not meet that requirement. Tools,
instructions, skills and development continuity must support coding quality.
Delegation is intended to lower cost while preserving quality.

Two interface options were presented: extend the existing `--mode chat` contract
to permit coding and official clients, or add a distinct continuous coding mode.
Extending chat offers one interface but changes its established action-free,
provider-only behavior. A distinct mode preserves that contract and makes coding
authority explicit, at the cost of a new interface and session integration.

## Decision and rationale

The owner accepted the recommendation for a distinct continuous coding-chat mode,
using a plain terminal interface, reusable foreground controller and existing
local SQLite storage. No daemon, additional database or framework is introduced.
The stated product rationale is to conduct the same development conversations
in the CLI with comparable results and lower cost through bounded delegation.

Retain official-client and provider-native execution under the accepted shared
tool architecture. Keep routing/fallback in the existing Orchestrator and
provider/client adapters; conversation control belongs in `ai_agent`.

Persist user turns and final responses in existing chat records. Link them to
the coding session by ID without a schema migration. Existing coding records
retain explicit decisions and hashed effect receipts. Do not broaden receipt
persistence to secrets, private reasoning or raw tool arguments/output.

Preserve workspace/privacy/cost boundaries on resume. Delegated tasks inherit
primary privacy by default under ADR-022. Each turn uses fresh execution and
approval scopes. A live foreground supervisor can span turns; restart restores
observations, not live pipes, grants or arbitrary process ownership. Interrupted
effects require explicit reconciliation rather than automatic replay.

## Initial implementation and acceptance limits

On 2026-10-09 the owner accepted strict per-required-case baseline quality
assessment: retain owner requirements, achieve outcomes at least as good as the
baseline, and accept no privacy, authorization, data-loss or required-tool
regression. Partial or unavailable required cases remain acceptance gaps. This
fits the existing comparable-or-better migration goal; it is an assessment rule,
not evidence that parity has been achieved. The owner also agreed to withhold
savings claims when the relevant metric cannot be measured. A specific economic
metric, improvement threshold and latency trade-off were initially unresolved.
On 2026-10-10 the owner selected external allowance/API spend, local total tokens
and elapsed time, with time considered but no hard median-completion-time gate.
The owner subsequently adopted a 20% external savings target, with below-target
results subject to case-by-case review rather than automatic rejection. See
[ADR-050](ADR-050-usage-measurement-and-automatic-integration.md).

`--mode coding-chat --execute` runs successive tool-capable turns. The existing
provider-only `--mode chat` remains available. Questions and planning turns do
not authorize edits merely because coding tools are available.

The foreground terminal now accepts in-flight input through one joined polling
reader. Corrections queue the next turn and persist immediately in existing user
message records; host replies link to attempted messages through existing
metadata. Restart exposes unexecuted input as evidence and never replays it.
Chat text cannot answer an in-flight approval: the owner must name the fresh
prompt ID, and the invocation must remain active. Exit/EOF suppress queued work.
This is queued steering, not preemption of already running model calls/effects.

Selected files, repository instructions and skills are reloaded on each turn.
History contains user turns, final model reports and host-observed outcomes,
not cached repository snapshots. On 2026-10-09 the owner accepted deterministic
local history reduction: preserve every owner message and host outcome verbatim,
visibly shorten older assistant reports, and refuse if mandatory context cannot
fit. This avoids extra inference and risks from model-written summaries, at the
cost of retrieving older assistant plans when needed. The owner accepted the
presented recommendation; no further independent rationale was supplied.

Reduction is computed from the full transcript on every turn and after restart;
it never overwrites originals or adds summary storage. Reports shorten oldest
first, preserving newer reports when space permits. Excerpts identify their
original messages; `/history` and `/history MESSAGE_ID` permit local retrieval.
Host-authored interruption notices are retained. The budget includes the current
request and rendered JSON/notice overhead. Unlimited history is not a provider
capacity guarantee. Required tool profiles and fallback scopes are unaffected.

Offline tests and synthetic-client host acceptance do not establish comparable
model results, installed-client parity or lower cost. Validate representative
multi-turn development tasks and measure API cost/allowance use separately.
The wider migration requirement remains incomplete until that evidence exists.

See [implementation proposal and acceptance plan](../repo-assistant/continuous-coding-chat-plan.md).
