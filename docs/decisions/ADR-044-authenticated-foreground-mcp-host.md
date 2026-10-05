# ADR-044 — Authenticated foreground loopback MCP host

**Status:** Accepted; foreground host and read-only IDE bridge acceptance passed
**Date:** 2026-10-05

## Context and alternatives

ADR-041 already selected foreground process ownership and existing SQLite
receipts with explicit restart reconciliation. Per-client stdio MCP servers
cannot independently own a child while preserving its live handle across agent
route changes. The alternatives were a scoped operating-system IPC proxy,
an authenticated loopback MCP host, or retaining incomplete external process access.

## Owner decision and rationale

The owner selected B: an authenticated loopback MCP host. Their rationale is
that authentication, connection/session lifecycle and shutdown behavior will be
needed eventually, so implementing them now is preferable to deferring them.
This is the owner's reason, although the previous technical recommendation was IPC.

The owner supplied their local PyCharm HTTP Stream configuration and explicitly
required machine-specific settings to stay local. Other users must supply their
own copied configuration or a subsequently approved automatic discovery mechanism.

## Implementation boundaries

- One foreground CLI owns the supervisor and an ephemeral `127.0.0.1` listener.
  Existing per-client stdio adapters forward to that host using MCP Streamable
  HTTP with JSON responses. Optional GET streams, SSE replay and a daemon are absent.
- Fresh bearer credentials are issued per invocation, bound to a tool registry,
  workspace, task/run and permission preset. MCP sessions are bound to that bearer.
  Credentials and sessions expire on invocation completion, interruption, deadline
  or owner shutdown. A session ID alone never authorizes an operation.
- Credentials travel in the launched client's environment; generated MCP settings
  and logged commands contain only a URL and the environment variable name.
  Existing client permission restrictions remain additional boundaries.
- Start/stop use existing shell approvals; status uses read permissions. Shared
  receipts reuse existing optional session storage. No raw commands, outputs,
  credentials or reasoning are added to durable receipts.
- Route switches preserve the same supervisor. Restarted handles remain observations
  and cannot attach by PID. Owner shutdown stops its direct children; descendant
  management retains the existing documented limitation.
- PyCharm supplies separate read-only IDE tools through an imported ignored local
  file. A fixed wrapper allowlist covers interpreter selection, diagnostics and
  symbol information. Arbitrary IDE calls and mutating refactors are excluded.
  The official MCP SDK remains an optional IDE dependency under ADR-041.

## Consequences

The host introduces local HTTP authentication and lifecycle responsibilities.
Host/Origin validation, loopback binding, bounded request bodies, explicit bearer
revocation and session ownership require regression coverage. The current host
reuses existing JSON-RPC handlers without introducing a web framework.

Explicit configuration import is sufficient for the supplied endpoint. Automatic
IDE discovery, OAuth/cloud hosts, persistent credentials, user-wide client grants
and background ownership are separate decisions. Transport tests with synthetic
clients do not establish hosted-client or attended terminal acceptance.

## Implementation checkpoint

Real Copilot 1.0.91 and Kiro 2.24.0 continued a synthetic quota failure, polled the
same owned in-flight child through the shared HTTP host, and completed the partial
edit with fresh run receipts. Host validation passed and both children were stopped.
Four failed Copilot startup fixtures remain preserved. The current Copilot client
first probes `server/discover`; unsupported discovery returns JSON-RPC -32601 so
it can negotiate classic initialization rather than losing the connection.
Explicit per-client environment forwarding contains variable references, not tokens.

The owner approved SDK installation. The official SDK interoperability test and
all three project IDE wrappers passed against PyCharm. Recorded SDK traffic shows
successful HTTP 200 session deletion for each wrapper; the earlier direct probe's
404 is preserved as historical evidence. Unavailable-endpoint and missing-SDK
failures are explicit, with transport task-group errors redacted at the CLI boundary.
Attended terminal approval and production Codex/Antigravity parity remain open.
