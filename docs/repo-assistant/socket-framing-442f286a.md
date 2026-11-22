# Chunked-request socket observation

Run `442f286a4fd14370a575c8dd4cd4ceaf`, 2026-11-22.
Status: **INCOMPLETE: bounded capture complete; originating abort unknown.**

## Bounds and result

Exactly one invocation of
`apps/workbench_dashboard/tests/test_inference_proxy.py::test_run_scope_auth_revocation_and_size`
ran serially with xdist disabled and PYTEST_ADDOPTS cleared, under a 45-second
subprocess timeout. It passed: **1 passed in 0.57s**, exit 0; total subprocess
elapsed 1.043s. Python 3.14.4 Windows AMD64. No retry or production fix.
The test includes seven requests; only one carries Transfer-Encoding.
Existing callback assertions passed, using a synthetic local callback.

The earlier b1eac80c capture was absent from this checkout and was read from
`../b1eac80c9b88/docs/repo-assistant/socket-framing-b1eac80c.py` and its report.
This diagnostic reuses its wrappers, selects the requested test, and adds UTC
wall timestamps alongside monotonic nanoseconds. Original test framing,
authorization behavior, request contents and production code remain unchanged
by these repository edits. No private docs/plans or CURRENT_CONTEXT.md was
present in this checkout.

[Capture script](socket-framing-442f286a.py),
[events](socket-framing-442f286a/events.json),
[receipt](socket-framing-442f286a/receipt.json),
[supervisor bound/result](socket-framing-442f286a/supervisor.json),
[pytest result](socket-framing-442f286a/result.xml).
Console output remains at `.tmp/socket-framing-442f286a/console.txt`.
Output-directory creation refuses reuse. Ruff subsequently reformatted the
script; this was whitespace only, and the consumed test was not rerun.

## Observed chunked-request sequence

164 events, zero instrumented exceptions. Times are microseconds relative to
400 send_response entry at 2026-11-22T12:07:22.486886Z.

| Event | Relative microseconds |
| --- | ---: |
| Client header send starts (183 bytes) | -232.5 |
| Server socket read returns 183 bytes | -50.5 |
| Server begins 400 response: Transfer-Encoding present, no Content-Length | 0.0 |
| Client header send returns | +28.8 |
| Client body send starts / returns (56 bytes) | +35.1 / +48.3 |
| Client socket read returns response headers (172 bytes) | +70.9 |
| Client response begin returns | +111.8 |
| Server end_headers returns | +124.2 |
| Client socket read returns response body (40 bytes) | +138.2 |
| Server finish starts / returns | +147.9 / +152.8 |
| Server shutdown starts | +156.9 |
| Server close starts / returns | +206.0 / +214.1 |

The test supplies a chunked header but http.client sends the JSON string without
chunk framing (encode_chunked defaults false). This was preserved. The server
rejects the header and its drain reads zero because Content-Length is absent.
Its only observed socket read for this request returned the 183 header bytes;
the client sent the 56 body bytes after rejection began. No body read is observed
before close. The full response reached the client before shutdown.

This shows successful rejection despite unread application body bytes. It does
not measure kernel receive-queue contents or identify an abort origin. A passing
instrumented sample cannot rule out unread-body close in the historical failure.
Instrumentation changes scheduling; no packet, ETW or Winsock-origin trace was
collected. Object ids are process-local and reusable; thread ordering plus the
unique Transfer-Encoding status identifies the request, not durable socket ids.

## Source investigation and next action

Web searches: `site.github.com/python/cpython 150499 unread body close reset HTTP`
and `site.learn.microsoft.com WSAECONNABORTED 10053 socket`.
[Microsoft Winsock reference](https://learn.microsoft.com/en-us/windows/win32/winsock/windows-sockets-error-codes-2)
defines 10053 as a host-software abort with possible timeout/protocol causes;
the code does not identify the responsible component.
[CPython issue 150499](https://github.com/python/cpython/issues/150499) concerns
HTTP framing and persistent-connection body handling. Neither source establishes
this incident's cause.

Next action: prepare a separately bounded diagnostic capturing metadata-only
socket/ETW shutdown and abort provenance alongside these application events.
Do not replay this consumed allowance. Any capture requiring elevated/manual
approval must stop for that approval; avoid packet contents and credentials.
Completion requires evidence identifying the originating abort or ruling out
unread-body close for an actual failing request. No production fix is justified
by this passing observation alone.

Validation: one test as above; Ruff lint and formatting checks for the diagnostic.
No broad suite or whole-repository type check is claimed. No test module was added.
