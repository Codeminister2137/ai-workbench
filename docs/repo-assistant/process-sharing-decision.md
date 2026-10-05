# Shared foreground process access: decision brief

**BLOCKED on transport/authentication choice; existing foreground supervisor stays approved.**

ADR-041 selected a foreground supervisor, existing SQLite receipts and explicit
restart reconciliation. Native session tools now expose its process handles;
handoffs retain observed handle/status metadata. Synthetic fallback polls the
same owned child without launching it again. Restarted handles remain observations
only and cannot attach to a process by PID.

The common external coding MCP profile currently provides blocking `run_command`,
not `process_start/status/stop`. Each official client starts its own stdio MCP
server. Adding a supervisor independently to each server would lose shared live
handles on route changes and would not satisfy C6. SQLite cannot restore its
live pipes or safely transfer child ownership.

## Decision needed

Choose how per-client MCP adapters reach the existing CLI-owned supervisor.
This introduces a private local communication channel and authentication scope;
it is not a choice to reopen foreground ownership or add a daemon.

| Option | Benefit | Trade-off |
| --- | --- | --- |
| A: Scoped local IPC proxy, Windows named pipes / Unix sockets | No listening network port; standard-library implementation can retain one foreground owner | Platform-specific transport/testing and explicit per-run authentication/expiry |
| B: Authenticated loopback MCP host scoped to the foreground CLI | Standard MCP transport and potential reuse for more shared tools | Local listener, HTTP/session lifecycle, authentication and dependency scope need approval |
| C: Keep native foreground process tools and external blocking shell | No new transport or authentication surface | Cross-client live process control stays incomplete |

Recommendation: A for the current single-user local CLI. Keep handles owned by
the CLI; authorize each start/stop under the selected preset, let status remain
read-only, expire adapter access after run/owner exit, and retain existing receipt
and reconciliation semantics. No command/output/credential persistence or daemon
is proposed. Implementation must test a real in-flight child through route changes,
denied start/stop, adapter expiry, interruption, cleanup and restart refusal.

Owner question: choose A, B or C, and state the main reason if it differs from the
recommendation. Record a detailed ADR only after the owner selects the channel.
