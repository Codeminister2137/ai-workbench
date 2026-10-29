# Bounded Meta development now

## Interactive terminal chat

From the Workbench project terminal:

```powershell
.\scripts\meta-develop.ps1 -Chat `
  -RepoRoot artifacts/meta-acp-coding-20261029/worktree `
  -RunDirectory artifacts/meta-chat-first
```

Add `-Check` for an offline setup check. Without it, the existing coding-chat
mode displays `You>`: type an authorized public Operator task, then follow up in
the same conversation. Edits/commands use real interactive approvals. `/exit`
closes the chat; Ctrl+C interrupts it and requires checking partial effects.
Operator-generated code must still run in the approved isolated runner; do not
approve running it on the credential host.

The existing Workbench database `data/repo-assistant-chats.sqlite3` stores the
conversation, using the existing session schema. No new database/backend is
provisioned; missing storage refuses startup. Select another existing database
with `-SessionDatabase`. This is owner-driven foreground conversation, not an
autonomous multi-task scheduler or a new continuity contract.

**The entire conversation shares eight provider calls, USD2 and a 15-minute
admission window.** Tool follow-ups count as calls. New turns do not reset any
limit. Exhaustion stops before the next send, returns exit2, and retains effects
and receipts. These local limits do not replace the aggregate funding check.
Use an unused run directory; never automatically restart to replenish allowance.
Optional `-TaskFile` executes a supplied initial task immediately; omit it to
start at the prompt. Private Workbench transmission remains separately gated.

Offline acceptance exercises the actual coding-chat controller over eight
synthetic turns, checks prior owner/assistant history in the second request, and
proves a ninth request never reaches transport. No physical approval or live
chat quality is claimed by that test. The earlier real single-task Meta coding
and independent Modal validation remain the live development evidence.

Subsequent live two-turn continuity pilot also passed: real Spark responses
recalled a random synthetic tag from the earlier turn through the coding-chat
controller. Those inputs were automated pilot continuations, with no simulated
human approval or generated-code execution. The PowerShell `-Chat -Check` entry
also passed without inference. Local evidence: `artifacts/meta-chat-live-20261029/`.

## One focused task

Use the existing Workbench CLI through `scripts/meta-develop.py` for one focused
public-repository coding task. No new installation, service, scheduler or database.
Run from the configured project environment using either entry point below.

In a Windows project terminal, the companion launcher supplies the existing
package paths without changing directories or importing the whole `.env`:

```powershell
.\scripts\meta-develop.ps1 `
  -RepoRoot artifacts/meta-acp-coding-20261029/worktree `
  -TaskFile artifacts/meta-cli-coding-20261029/task.txt `
  -RunDirectory artifacts/my-next-meta-task -Check
```

It uses the existing project `.venv` by default; pass `-PythonExecutable` to use
the IDE's configured interpreter instead. It installs nothing. Remove `-Check`
only for a fresh authorized task, not the already-completed example below.

The equivalent Python entry point is:

```powershell
uv run --locked --no-sync python scripts/meta-develop.py `
  --repo-root artifacts/meta-acp-coding-20261029/worktree `
  --task-file artifacts/meta-cli-coding-20261029/task.txt `
  --run-dir artifacts/my-next-meta-task --check
```

`--check` performs local setup checks without inference. Remove it to execute a
**new authorized task**, with a new task file and unused run directory. The example
task has already been completed: do not replay it. Check the current handoff for
remaining aggregate funding and approved data scope before each new allocation.

The launcher loads only `META_API_KEY` from the local environment file, selects
Spark1.3 Standard, and invokes the existing native-tool implementation runner.
It snapshots only the Meta route into its catalog, avoiding other fallback routes.
Per invocation: eight actual HTTP requests, complete input128KiB/request, output
8192 tokens, request90seconds, admission window15minutes. Full conservative
reservation before each send totals at most USD1.630208, inside the named USD2
envelope. Failures retain reservations; no automatic reset/resume or budget renewal.
These are local controls, not a provider billing cap or an aggregate account ledger.
Budget allocation across separate invocations still belongs to the supervising
workflow. Context/instructions are refused if too large, never silently trimmed.

Declared first-task exceptions: low reasoning, source editing only, workspace-write
policy, no orchestrated stages or local Ollama reviewer. Native shell/custom tools
still require real approval. Generated Operator code must execute only in its
approved isolated runner, not the credential host. Host review and independent
Modal checks complete this workflow; the launcher does not certify its own output.
No automatic multi-task unattended loop or private Workbench transmission is granted.
Use existing coding-chat when a separately approved interactive conversation is
needed; this helper intentionally runs a single bounded task.

Acceptance on2026-10-29: three real Meta calls/18136tokens, approximately15seconds,
actual public checker edit; host-authored regression tests; protected export checks
8/8 and full public suite184passed8skipped69subtests in Modal with cleanup verified.
Two original full-suite fixture failures were preserved and diagnosed (omitted
sample, then64KiB file limit blocking a deliberate65537byte test fixture). A fresh
bounded full-suite diagnostic used128KiB child files; product policy was unchanged.
Evidence: local `artifacts/meta-cli-coding-20261029/`. This establishes the concrete
workflow, not general model quality, unattended continuity or Baseten acceptance.
