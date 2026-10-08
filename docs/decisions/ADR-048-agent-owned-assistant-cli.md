# ADR-048 - Agent-owned repository assistant CLI

**Status:** Accepted

**Date:** 2026-10-08

## Owner decision and intent

During the repository design audit, the owner proposed that the CLI belongs in
`ai_agent` and asked whether the architecture contradicted this. Inspection found
that the dependency direction supports the move: `ai_agent` already depends on
`ai_provider` and `ai_orchestrator`. Existing documentation nonetheless assigned
CLI/run composition to the provider package. The owner explicitly approved the
recommended focused migration after this discrepancy and its scope were explained.

This supersedes the earlier placement of the assistant entry point, command
implementation, argument registration and CLI external-execution settings in
`ai_provider`. It does not supersede research, persistence, routing, approval or
provider-adapter decisions recorded in earlier ADRs.

## Decision

- `ai_agent.cli:main` owns the unchanged `ai-assistant` command.
- `ai_agent.repo_coding_assistant` owns its command/workflow implementation.
- `ai_agent.repo_assistant_args` owns argument registration.
- `ai_agent.external_execution` owns common CLI primary/repair/fallback settings.
- Provider contracts, authentication, HTTP translation and official-client
  adapters retain their `ai_provider` ownership. Orchestration policy stays in
  `ai_orchestrator`.
- Research, run-store, transcript and fallback composition helpers remain in
  their existing modules for this slice. Their existing optional integration
  references use the canonical agent module. This is not a migration of the
  entire composition layer.
- Old provider import paths remain explicit compatibility aliases to the same
  module objects, preserving attribute assignments as well as named imports.
  The old `python -m ai_provider.repo_coding_assistant` and example entry point
  still delegate to the agent implementation.
- The provider package does not gain a dependency on the agent package. Legacy
  CLI imports require `ai-agent`; importing provider core remains independent.
- Remove source-layout `sys.path` injection from the CLI implementation. Install
  the workspace packages and use their package/command entry points.

## Alternatives and consequences

Keeping the CLI in `ai-provider[cli]` would preserve ownership and need less
migration, but leaves agent workflow composition assigned to the lower provider
layer. A new separate composition package would isolate the workflow but add
packaging and import migration overhead. Moving the entire composition layer to
`ai_agent` now would give broader separation, but expands work across research,
storage and fallback APIs before their ownership has been reviewed individually.

The selected focused move follows the owner's proposed package ownership and
existing dependency direction, preserves compatibility and limits rework. It
leaves historical composition debt explicit rather than pretending that all
provider modules are now pure adapters. Compatibility aliases are narrowly
scoped; new repository code/tests use canonical agent imports.

## Validation

Offline CLI and workspace tests cover native/external execution, repair,
fallback, approvals and storage behavior. Additional regressions exercise both
module entry points, alias identity/attribute updates, command ownership and
provider-core imports without loading `ai_agent`. Both packages are built as
offline wheels, and entry-point metadata is inspected. No new dependency,
persistent format or live external execution is introduced.
