# ADR-024: Codex CLI Parity, Authorization, and Development Tool Policy

## Status
Accepted

## Date
2026-09-27

## Context
The repo assistant is being stabilized as a CLI-first coding workflow. Codex is
the base capability target, but the architecture must remain usable with
alternate models, providers, and execution surfaces. The remaining parity gaps
are not only implementation details: approval policy, connected app/tool access,
and external-service authorization affect privacy, credentials, write actions,
and future compatibility.

The owner selected these directions:

1. Use clear model-neutral approval policy presets rather than attempting exact
   ChatGPT/Codex UI approval parity.
2. Build explicit tool bridges for development-relevant app/document/control
   capabilities when needed, with read and write capability designed together
   even when writes are disabled by default.
3. Expand external-service connectors one at a time only when a concrete
   workflow justifies the access.
4. Keep user authorization for GitHub, Codex, and similar services in one
   reusable place rather than scattering per-tool authentication logic.

## Options Considered

### Approval policy

1. Keep only the current Codex CLI sandbox flags.
2. Add repo-assistant approval policy presets that are independent of the
   underlying model/provider.
3. Try to emulate this ChatGPT session's managed approval UI exactly.

### App/document/control parity

1. Leave app/document/control tools out of CLI parity.
2. Add read-only diagnostics first.
3. Build explicit MCP/plugin/tool bridges for selected development-relevant
   capabilities.

### External-service connectors

1. Keep only the current local installed plugin set.
2. Approve and implement connectors one at a time.
3. Bulk-install or bulk-connect a broad plugin set.

## Decision

1. **Approval policy presets are the durable abstraction.**
   The repo assistant will define clear approval modes that can work across
   Codex, Ollama, hosted providers, and future executors. Codex remains the
   baseline user experience, but policy semantics belong to this project rather
   than to one model or UI.

2. **Development tools may be added as explicit bridges.**
   App/document/control parity should focus first on tools needed for coding
   and development workflows. Other app categories remain deferred until there
   is a concrete need.

3. **Read and write capability are designed together.**
   For a tool surface that may eventually mutate files, repositories, documents,
   tickets, deployments, or external services, the contract should model both
   read and write operations from the start. Write operations may be disabled by
   default or require a stricter approval mode, but the design should not create
   a read-only dead end that must be replaced later.

4. **External connectors are approved one at a time.**
   GitHub is the likely first candidate when a concrete repository workflow
   requires it, but its read/write boundary must be explicit before
   authorization or implementation.

5. **Authorization is centralized and reusable.**
   Service sign-in, token/session discovery, authorization state, permission
   summaries, and revocation/diagnostic behavior should live behind one
   reusable authorization boundary. Individual tools should consume that
   boundary rather than handling user authorization independently.

## Consequences

- The CLI can converge toward Codex capability parity without becoming
  Codex-only.
- Future approval behavior can be tested against project-owned policy modes
  instead of one provider's UI.
- Development app/tool bridges can evolve from read to write safely because the
  write boundary is part of the initial contract.
- External-service access remains auditable and incremental.
- A reusable authorization layer is now a prerequisite for serious GitHub,
  Codex plugin/app, cloud deployment, issue tracker, document, and similar
  integrations.
- Implementing broad document/app-control parity remains out of scope until a
  specific development workflow selects the first tool surface.
