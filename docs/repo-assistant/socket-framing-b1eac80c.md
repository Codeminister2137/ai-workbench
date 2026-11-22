# Windows 10053 framing observation

Run `b1eac80c9b88494cbb44b8cfb7626bd1`, 2026-11-22.
Status: **INCOMPLETE — bounded observation completed; historical cause unknown.**

The original failures and their uncertainty remain preserved in
[health evidence](health-48679817-evidence.md#preserved-baseline-failure-and-bounded-diagnosis).
No production transport, authorization policy or test expectation was changed.
No private `docs/plans/` or local `CURRENT_CONTEXT.md` was present in this checkout.

## Fresh diagnostic

Exactly one invocation of
`tests/test_foreground_http.py::test_permissions_session_binding_deadline_and_shutdown`
ran serially, with xdist disabled, inside a subprocess with a 45-second timeout.
Result: **1 passed in 2.05 seconds**, process exit 0, Python 3.14.4 Windows AMD64.
There were no retries and the chunked-request test was not run.

[Diagnostic script](socket-framing-b1eac80c.py) temporarily wraps standard-library
send, response-begin, server status/header output, SocketIO reads and server
finish/shutdown/close operations. It records monotonic nanoseconds, thread ids,
object ids, byte counts, framing metadata, status codes and exception type/code.
It never records header values, credentials, paths, request/response contents or
exception messages. Instrumentation is confined to this diagnostic process and
perturbs timing; this is not a packet trace or an uninstrumented reproduction.
The status capture observes `send_response`, not a snapshot of the host deque.

Retained evidence: [events](socket-framing-b1eac80c/events.json),
[receipt](socket-framing-b1eac80c/receipt.json),
[pytest result](socket-framing-b1eac80c/result.xml).
Raw console output remains in `.tmp/socket-framing-b1eac80c/console.txt`.
The script refuses to reuse an existing output directory to preserve consumed runs.

## Observed sequence

Times below are microseconds relative to the server's 401 `send_response` entry.

| Event | Relative time |
| --- | ---: |
| Client header send starts / ends (288 bytes) | -655.7 / -304.8 |
| Client body send starts / ends (167 bytes) | -298.3 / -200.5 |
| Server SocketIO read returns 455 bytes | -89.2 |
| Server emits status 401; Content-Length 167, no Transfer-Encoding | 0.0 |
| Client read returns 178 response bytes | +56.3 |
| Client response `begin` returns | +107.8 |
| Server header output returns | +159.4 |
| Server finish starts / ends | +169.4 / +174.1 |
| Server shutdown starts | +179.6 |
| Server close starts / ends | +251.2 / +256.7 |

All 350 recorded events contained zero instrumented exceptions. The captured
server statuses were 200, 202, 200, 200, 200, 204, 400, **401**, 200, 202, 200,
202, 404, 403, 200, 202, 200. The test's existing assertions passed.

For this request the server's socket read received the combined header/body byte
count before rejection. The application rejects before consuming the buffered
body, but this does not imply that body bytes remained in the kernel receive
queue at close. Client response parsing completed before server shutdown began.
This successful observation shows that early application rejection alone does
not inevitably produce 10053. It cannot establish or rule out the originating
abort in either historical failure. No evidence-based transport fix follows.

## Source investigation and next action

Web searches performed: `site.github.com/python/cpython 150499 unread body close
reset HTTP` and `site.learn.microsoft.com WSAECONNABORTED 10053 socket`.
[Microsoft's Winsock reference](https://learn.microsoft.com/en-us/windows/win32/winsock/windows-sockets-error-codes-2)
defines 10053 as a host-software abort, with possible timeout/protocol causes;
the code does not identify the responsible component.
[CPython 150499](https://github.com/python/cpython/issues/150499) concerns HTTP
framing/persistent-connection handling and does not establish this incident's cause.

Next action: prepare a separately named, finite diagnostic for the chunked-request
test, preserving its original framing and capturing the same event sequence.
If an abort is observed, preserve it and correlate socket/ETW or packet evidence
before attributing it to unread-body close, a timeout or other host software.
Completion requires evidence identifying the abort origin (with a justified fix
and regression checks if applicable), or evidence ruling out the proposed
mechanism for an actual failing request. A passing isolated test is insufficient.

Validation: Ruff check and format check passed; Pyright reported zero errors
with a missing worktree-local `.venv` notice (the repository venv interpreter
was used). No broad suite was run; the bound was one test, once.
