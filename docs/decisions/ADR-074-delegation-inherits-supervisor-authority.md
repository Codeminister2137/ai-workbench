# ADR-074: Delegation inherits supervisor authority

Status: Accepted owner direction (2026-10-27), implemented 2026-10-28.

## Decision and rationale

The owner requires implementation workers: delegation must inherit the actual
supervisor grant or receive a narrower explicit grant. A universally read-only
child prevents ordinary delegated implementation and validation. Read-only is
therefore an optional profile. The owner retains product and architecture authority.

The host binds existing tools, the live permission manager, workspace, original
instructions/objective and allowed inference backends. Model arguments can narrow
tools, paths, exact commands and permission profiles; they cannot grant broader
authority. Ancestor restrictions remain effective through nesting. Children share
original reply/tool allowances and deadline, with a parent report reservation and
maximum depth two. Revocation prevents subsequent effects; completed effects remain.

Funded execution reuses the exact approved parent client, retaining billing,
privacy and admission guards. A catalog entry alone cannot authorize another paid
executor. Native fallback retains the initial backend snapshot and shared budget.
The external-client MCP host budgets descendants; it cannot count provider requests
performed independently inside an official CLI.

Delegated OS processes receive an allowlisted environment plus explicitly bound
values rather than ambient credential variables. File/command scope is enforced
at tool calls, not an OS sandbox: an approved command retains its actual filesystem
and network capabilities. No credential discovery, new processor, private-data
transmission or simulated physical approval is authorized by inheritance.

## Alternatives and consequences

- Inherited authority with narrowing enables real edits and validation, while
  requiring shared accounting and enforcement across native and MCP routes.
- Universal read-only delegation is simpler to contain but contradicts the owner's
  implementation-worker requirement and forces all effects onto the supervisor.

Legacy unbound local runners remain read-only; bare registries without a runner
refuse delegation. Missing funded capabilities fail explicitly. No new service,
dependency, persistent format or public Operator code is introduced.

## Evidence and limits

Deterministic tests cover actual child edits and Python validation, inherited and
narrower permissions, nested limits, cancellation, backend refusal and credential
variable exclusion in real shell/process execution. Hosted nested delegation
acceptance and general model-quality parity remain unestablished.
