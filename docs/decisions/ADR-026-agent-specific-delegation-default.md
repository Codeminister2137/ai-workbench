# ADR-026: Agent-Specific Delegation As Default CLI Capability

## Status
Accepted

## Date
2026-09-28

## Context
The repo assistant CLI is becoming the primary coding workflow for this
repository. Earlier local delegation focused on bounded context extraction, and
provider-native tool execution existed behind `--native-tools`.

The owner clarified that delegation is a core CLI capability: the primary model
should be able to delegate whatever bounded support work it considers suitable
to less capable but cheaper models. This includes reading files, summarizing,
checking details, and writing smaller pieces of code when the active approval
policy permits writes.

## Options Considered

### Keep Delegation Opt-In And Context-Only
This preserves the narrowest behavior and minimizes surprise.

The drawback is that the CLI would not exercise the intended multi-model coding
workflow by default, and delegation would remain a side feature instead of part
of the agent model.

### Make Agent-Specific Delegation The Default CLI Path
This keeps delegation in the `ai_agent` layer, above provider routing, and lets
the CLI expose a `delegate_task` tool to the primary model. The delegated child
agent derives a local/cheaper task profile and receives the same workspace tool
surface and approval policy, with nested delegation disabled.

The drawback is that provider-native tool support must be available on the
selected primary route, and the agent layer now owns a second task protocol that
may later be migrated into lower-level provider contracts if the abstraction
proves stable.

## Decision
Use agent-specific delegation as the default implementation-mode CLI capability
for provider-native routes.

Executed `implement` mode uses the `ai_agent.AgentLoop` by default unless
explicitly disabled. The primary agent receives the standard coding tools plus a
`delegate_task` tool. Delegated child tasks derive local-only, cost-minimizing
profiles and may use the standard coding tools, including small file writes,
subject to the same approval policy selected for the run.

Planning, ask, and review modes remain non-mutating. Codex CLI and other
external-agent routes continue to use their dedicated executor path.

## Rationale
Delegation is part of the CLI's intended product identity, not just an optional
context summarization optimization. The top model should spend its capacity on
work that needs it, while cheaper models handle bounded subtasks such as local
inspection, small edits, and verification. Keeping the protocol in `ai_agent`
lets the behavior evolve quickly without forcing another immediate
`ai_provider` contract migration.

## Consequences
- `--native-tools` remains accepted for compatibility, but provider-native
  implementation runs use the agent loop by default.
- `--no-native-tools` exists for the older text-only provider response path.
- Delegated writes are controlled by approval policy, not by a separate
  delegation-specific permission system.
- Nested delegation is disabled to keep runs bounded and easier to inspect.
- The current implementation is intentionally CLI-first and may be revisited if
  multiple applications need the same delegation protocol.

## Related Decisions
- ADR-022 - Subtask Profile Derivation And Local Delegation
- ADR-024 - Codex CLI Parity, Authorization, And Development Tool Policy
- ADR-025 - Local-First Auxiliary AI Work
