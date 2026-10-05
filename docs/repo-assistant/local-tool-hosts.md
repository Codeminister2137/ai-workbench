# Local foreground MCP and PyCharm bridge

The authenticated foreground MCP host is selected in [ADR-044](../decisions/ADR-044-authenticated-foreground-mcp-host.md).

## Shared processes

Execute a request with `--shared-tools coding` to share repository tools and
`process_start`, `process_status`, `process_stop` through one foreground CLI.
The host starts lazily on the first external invocation, binds an ephemeral port
on `127.0.0.1`, and issues fresh access for each client run. Native execution uses
the same supervisor. The optional `--coding-session` keeps existing receipts and
observed process metadata; process sharing also works without persistence.

Process handles remain valid across agent route changes while this CLI lives.
Each replacement client receives new permissions and authentication; the old
client's access expires. On CLI shutdown, the listener closes and owned direct
children stop. Restarted handles cannot reattach to old processes by PID.

Start/stop require the selected preset's shell authority; status is read-only.
Interactive operations need an attended terminal. Missing terminal input causes
denial. Workspace containment is not an operating-system sandbox. The existing
supervisor manages direct children, not independently detached descendants.

Per-run stdio adapters preserve compatibility with Codex, Copilot and Kiro's
existing client mappings. They forward to the common HTTP host. Authentication
values travel in inherited environment variables; command logs and generated
configuration only identify those variables. Antigravity remains excluded until
its scoped shared-tool access is verified.

The HTTP host supports MCP initialization, JSON tool responses and session deletion.
GET streaming returns 405. It rejects unexpected Host/Origin, bearer/session
mismatches, expired access, unsupported protocol versions and oversized requests.
Calls are not retried automatically after a lost response: inspect uncertain effects.
Newer clients probing `server/discover` receive JSON-RPC -32601 and can negotiate
the supported classic initialization. Per-client environment references explicitly
forward the invocation credential without including its value in configuration.

## Machine-local PyCharm setup

Every user supplies their own endpoint. There is no published port or project path.
In PyCharm settings, open **Tools → MCP Server**, enable the server, apply, and
use **Manual Client Configuration → Copy HTTP Stream Config**. Keep command
execution without confirmation disabled. See [JetBrains' setup instructions](https://www.jetbrains.com/help/pycharm/mcp-server.html).

Save the copied JSON in a temporary local file, then import it:

```powershell
python -m uv run --no-sync python -m ai_agent.ide_bridge --workspace-root . --import-config PATH_TO_COPIED_JSON
```

The importer validates the loopback HTTP address and project-selection header,
then writes `data/pycharm-mcp.json`, which is ignored by Git. Existing configuration
is preserved unless `--replace` is explicitly supplied. Remove the temporary
copy when no longer needed. Reimport if PyCharm's endpoint changes.

This initial contract accepts the non-secret `IJ_MCP_SERVER_PROJECT_PATH` header
for this workspace. Credentials, additional headers, remote addresses and URLs
with credentials/query/fragment are refused. Preserve authentication if an IDE
requires it; authenticated IDE configuration needs a separate approved contract.

Install the approved optional SDK through the workspace's uv workflow:

```powershell
python -m uv sync --extra ide
python -m uv run --no-sync python -m ai_agent.ide_bridge --check
```

The check reports whether the IDE exposes the three required underlying tools.
With valid local configuration, shared inspection/coding tools include:

| Project tool | PyCharm operation | Arguments |
| --- | --- | --- |
| `python_environment` | `get_python_environment` | `path` |
| `file_diagnostics` | `get_file_problems` | `path` |
| `symbol_info` | `get_symbol_info` | `path`, one-based `line`, `column` |

Paths must identify an existing workspace file. Missing SDK/IDE/tools produce an
explicit failure. The SDK handles the IDE's handshake and HTTP/SSE lifecycle.
Ambient HTTP proxies are disabled. Only these read-only tools are forwarded;
mutating refactors and arbitrary IDE operations are not part of this bridge.

PyCharm is a separate tool host from the project's process supervisor. Closing
the IDE affects IDE tools; the foreground CLI remains the process owner.

## Validation checkpoint

Full offline suite: 1124 passed, eight skipped in 154.50 seconds; Ruff lint/format
and Pyright passed. Seven skips are the existing optional live checks; the eighth
is official SDK interoperability until the optional dependency is installed.

`scripts/fallback-acceptance.py --shared-process --fallback-client copilot` and the
equivalent Kiro fixture each passed: synthetic initial quota failure, real shared
edit continuation, an actual poll of the same in-flight child, protected-file
validation and verified child cleanup. Four failed Copilot handshake fixtures
remain retained separately from the passing runs. Offline tests cover denial,
scope/session mismatch, expiry during approval, owner shutdown and restart refusal.

Direct read-only PyCharm HTTP calls also passed. Installation and acceptance using
the project's optional SDK bridge remain pending; direct probes are separate evidence.
PyCharm returned 404 to direct session-deletion requests. The SDK must be checked
against that lifecycle behavior rather than assuming IDE session deletion succeeded.
