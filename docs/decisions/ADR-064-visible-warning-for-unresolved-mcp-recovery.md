# ADR-064 — Visible warning for unresolved MCP recovery

**Status:** Accepted 2026-10-22; implemented offline, live behaviour unverified.

## Decision and owner intent

The owner approved the "warning-with-evidence" option. An MCP tool-call failure
that call identity cannot resolve must no longer be reported as a failed run
when the run independently proves completion. It becomes a **visible warning**
beside the completed result, and the unresolved reason is retained.

The rationale is report fidelity, not leniency. The previous strict rule
reported "the run failed" for runs that demonstrably completed, which is a false
claim in the opposite direction from the one the acceptance criteria fear, and
it made baseline CLI acceptance unable to distinguish a genuinely failed trial
from a recovered success. It also caused completed runs to trigger fallback and
preservation retries, spending allowance on work that had already succeeded.

The owner's scope was explicit: the exception applies to **both** unresolved
call identity and a same-tool retry under a new call id.

## Contract

`parse_external_agent_jsonl` classifies an MCP failure as unresolved when its
identity — the `(server, tool, call_id)` tuple — cannot be matched to a later
successful MCP completion of the same call. That covers:

- **unresolved call identity** — the failure event carries no usable `id`
  (or `server`, or `tool`), so no later event can prove recovery;
- **cross-id retry** — the agent retried the same tool and succeeded under a
  *different* call id, so the failure's identity is never matched;
- **no retry** — the failed tool was never called again successfully.

An unresolved failure is demoted from a run-level failure to a warning **only
when the run independently proves completion**. All of these must hold:

1. no fatal, non-MCP failure marker appears anywhere in the stream;
2. a `turn.completed` event with no failure marker is present;
3. a final answer is produced **after** the MCP failure;
4. no identified MCP call is left pending and no unidentified MCP call is left
   open at the end of the stream.

Then `failure_reason` stays `None`, the unresolved reasons are returned in the
new `ExternalAgentEventSummary.mcp_warnings` field, and the CLI prints one
`external_agent_mcp_warning: <reason>` line per unresolved failure. A run that
completes with warnings exits successfully; a run that is genuinely incomplete
or fatal still fails and still exits non-zero.

The reasons are retained verbatim, so an unresolved failure can never be
masked by resolving a different call. Every unresolved failure produces its own
warning.

## What did not change

- A fatal error is never demoted. The existing rule that a fatal marker
  survives an apparent recovery is unchanged.
- An identified failure with its own matching recovery keeps the current
  behaviour exactly.
- A run with no completed turn, no fresh answer, an unfinished call, or a
  fatal error is still a failure with a non-zero exit.
- The `provider` privacy, cost and approval boundaries are untouched. This
  ADR changes how a completed run is *described*, not what may be executed.
- The shared-tool receipts remain the source of truth for what actually
  happened. The warning says that recovery could not be proven; it does not
  certify that the intended effect occurred.

## Validation

Offline tests cover the warning cases (unresolved identity, cross-id retry, no
retry), the four demotion conditions, the retention of multiple independent
unresolved failures, the reporting line, and the downstream outcome (a
completed run with a warning is not a failed fallback). The two existing tests
whose outcome class changed were re-specified deliberately and their original
invariant — that an independently unresolved failure is never erased by
resolving a different call — is preserved as warning retention.

Live external-agent behaviour, coding quality and baseline CLI acceptance are
separate questions and remain unverified by this change.
