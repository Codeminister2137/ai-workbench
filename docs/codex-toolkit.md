# Local development toolkit

Portable repository tooling notes. Machine-specific IDE settings, runtime paths,
account state and immediate agent handoffs belong in ignored local files.

## Workspace commands

Run these from the repository root after configuring the project interpreter:

```powershell
uv run --no-sync ai-assistant --mode plan "Explain the repository structure."
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pyright
```

Planning does not contact an inference provider. Live integration tests are
separately enabled through explicit environment switches; keep them disabled
when only validating software or when local compute is unavailable.

## IDE and agent context

Use the SDK configured for the project. Follow [AGENTS.md](../AGENTS.md) for
implementation boundaries and [the workflow](workflow.md) for validation.
The [prompt library](prompt-library.md) is the canonical repository source for
named Codex prompts. Local copies and IDE configuration can differ by machine.

`CURRENT_CONTEXT.md` is an ignored immediate handoff. Keep it short: active task,
current permissions, verified results, unresolved decisions and an imperative
next action. Archive historical detail locally and link to durable ADRs rather
than accumulating superseded instructions in the current handoff.

Use the existing session-boundary helper when context pressure becomes material:

```powershell
.\scripts\session-boundary.ps1
```

A tooling permission setting does not authorize architectural changes, credential
transmission, paid inference or publication. Those remain explicit task boundaries.
This public guide does not prescribe changing IDE approval policies or editing
private tool databases.

## Sharing and publication

Do not publish private machine paths, account status, runtime configuration,
transcripts or handoffs merely to demonstrate that a local tool works. Use neutral
placeholders in examples and inspect reachable Git history before publishing.
See [publication and privacy](publication.md), [environment](environment.md) and
[Git workflow](git-workflow.md).
