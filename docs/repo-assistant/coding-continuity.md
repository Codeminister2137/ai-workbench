# Foreground coding continuity

Opt in with `--coding-session new` on an executed ask/review/implement request.
The CLI prints the session ID. Use that ID on a later invocation to include the
original objective, explicitly supplied `--session-decision` values and recent
observed receipts. Repository instructions are freshly loaded. Privacy and cost
boundaries must remain unchanged; permissions are evaluated again on each invocation.

```powershell
.\scripts\repo-assistant.ps1 "Implement the agreed helper" --mode implement --execute --coding-session new
.\scripts\repo-assistant.ps1 "Inspect progress and continue" --mode implement --execute --coding-session SESSION_ID
```

Storage uses the existing application chat SQLite path unless `--coding-session-db`
is supplied. Tables are additive; existing chat data is retained. Session objectives
and explicit decisions are local records, so do not include credentials. Tool
receipts store operation names, status and output hashes, not arguments, output
bodies or model reasoning. External-client receipts store observed completion
metadata; common MCP per-tool persistence across clients is still a later slice.
Records remain until explicitly deleted; no automatic retention job is installed.

A running/interrupted session or uncertain client receipt refuses restart until
the user inspects files and processes, confirms no other CLI owns the session,
and supplies `--coding-session-reconciled`. This acknowledgement never replays an
operation or restores an approval. Process records from an earlier host become
`unknown_after_restart`; old PIDs never grant permission to control a process.
The acknowledgement is explicit human responsibility, not a live-owner lease or
automatic proof that side effects are reconciled.

During provider-native coding in an opted-in session, `process_start`,
`process_status` and `process_stop` share one foreground supervisor. Starts use
an executable/argument array without an implicit shell, require shell permission,
and restrict the working directory to the workspace. Status uses ordinary process
inspection with no AI call, bounded stdout/stderr and an explicit truncation marker.
Stopping also requires shell permission. Only opaque handles for children started
by this supervisor are accepted; callers cannot supply an unrelated PID.

The supervisor survives native agent switches while the foreground invocation
lives and stops its direct children on exit. It does not manage descendant trees,
restore dead pipes, run a daemon or replace the research scheduler. Long local AI
research remains scheduled through the existing supported research task type.
Cross-client common process tools and shared MCP mutation approvals are incomplete.
