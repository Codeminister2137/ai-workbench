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

`--mode coding-chat --execute` runs successive tool-capable turns. The existing
provider-only `--mode chat` remains available. Questions and planning turns do
not authorize edits merely because coding tools are available.

Selected files, repository instructions and skills are reloaded on each turn.
History contains user turns, final model reports and host-observed outcomes,
not cached repository snapshots. The conversation budget currently refuses
overflow rather than dropping decisions. Automatic compaction for long coding
conversations remains incomplete; unlimited history is not a capacity guarantee.

Offline tests and synthetic-client host acceptance do not establish comparable
model results, installed-client parity or lower cost. Validate representative
multi-turn development tasks and measure API cost/allowance use separately.
The wider migration requirement remains incomplete until that evidence exists.

See [implementation proposal and acceptance plan](../repo-assistant/continuous-coding-chat-plan.md).
