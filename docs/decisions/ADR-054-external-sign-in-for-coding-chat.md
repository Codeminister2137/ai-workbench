# ADR-054 - External sign-in for coding-chat

**Status:** Accepted; implementation validated offline, live acceptance pending
**Date:** 2026-10-11

## Decision

The owner selected external sign-in for continuous coding-chat. The host checks
existing account readiness but never reads an inline login answer or launches
the sign-in command during the conversation. This applies to primary readiness
even when fallback is disabled. Sign-in commands are displayed as instructions;
the owner signs in outside coding-chat, then retries a turn or restarts/resumes.
Readiness is rebuilt on each turn; retry does not reset the launch deadline.
Missing primary authentication refuses execution. Unauthenticated optional
fallback routes remain unavailable; authenticated primary execution can proceed.

Standalone requests retain their existing interactive preflight. No new user
configuration flag, credential storage, account service or dependency is added.
Explicit resume allowances still follow ADR-053; sign-in does not renew a deadline.

## Evidence, alternatives and rationale

A mocked trace confirmed that fallback preflight called blocking input while
coding-chat's joined polling reader was alive. Both readers could consume the
same terminal input, violating ADR-049's single-reader contract. An inline login
child could also compete for the terminal. Expiry checks alone do not resolve it.

The alternatives presented were pausing chat input while inline sign-in owns the
terminal (retains convenience, interrupts steering, requires lifecycle wiring)
and requiring sign-in outside coding-chat (simpler, requires a manual step;
restart/resume was initially described as necessary). Source inspection confirms
that existing per-turn readiness refresh also permits retry without restart.
External sign-in was the technical recommendation because it
separates terminal ownership and authentication handling. The owner's response
was "External"; no additional personal rationale was supplied or inferred.

## Validation limits

Mocked checks cover primary readiness failure, exclusion of unauthenticated
fallbacks, execution with an authenticated primary, disabled fallback, and no
input/login subprocess admission. An end-to-end coding-chat regression exercises
the active reader, failed SUMMARY, preserved failed outcome and cleanup.
Existing standalone inline sign-in regression remains passing. No real account,
login process, inference, GPU workload or service was started. Installed-client
and actual model edit/test/review acceptance remains incomplete and deferred.
