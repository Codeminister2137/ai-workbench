# ADR-078: Delegation reports execution completeness separately from tool errors

Status: Accepted by the owner and implemented, 2026-10-29.

## Decision and intent

Delegating work reported `delegate_task` as failed whenever any earlier tool
error had occurred, even when the child recovered, finished its final answer and
validated the result. A real funded child run produced exactly that: nineteen
Modal checks passed after an earlier rejected attempt, yet the prepared gate saw
`delegate_task.is_error=true` and the phase stayed INCOMPLETE. The owner approved
recording execution completeness as its own fact instead of redefining the
existing boolean.

`is_error` keeps its historical meaning: at least one tool result was an error,
or the child stopped without a usable final response. Callers that already test
this field keep their current behaviour and existing run records are not
regraded. `execution_complete` and `execution_reason` in result metadata, plus the
`Execution complete: ...` output line, say whether the child actually stopped on
a final answer. The reason names the first applicable cause — unresolved tool
calls, empty final response, provider output length limit, or provider error
finish reason — and otherwise reports the returned finish reason.

A complete execution is not an accepted outcome. The rendered line states that
the task outcome still requires independent validation, because a model-authored
claim about its own recovery is not evidence. Supervisors must read both fields
and only accept recovery from current, independently observed effects.

The same fact is produced by both delegation paths: the native `delegate_task`
tool and the MCP bridge. The CLI delegation status line uses it too, so a
recovered child is reported as `completed with earlier tool errors` rather than
`failed`, and an incomplete child as `incomplete`.

## Alternatives and trade-offs

- Preserve `is_error` and add `execution_complete` (chosen) keeps every existing
  caller working, keeps error evidence visible, and separates two genuinely
  different questions. It requires supervisors to consider both fields; a caller
  that reads only `is_error` still sees a conservative "failed".
- Redefining `is_error` as final execution failure would simplify recovery
  handling but changes the meaning existing callers and records rely on, and it
  risks hiding an unresolved refusal that a model merely described as recovered.

Neither option relaxes approval, path, command, privacy or budget guards, and
neither lets model text establish completion.

## Consequences

Delegation can distinguish "an earlier attempt errored" from "the child never
finished". Historical tool error evidence, truncation labels and the legacy
boolean remain in place, so the previously reported INCOMPLETE phases keep their
original receipts and can be assessed with the new fact without being rewritten.
