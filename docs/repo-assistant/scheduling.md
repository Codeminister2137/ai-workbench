# User-started research task scheduling

[CLI guide](../repo-coding-assistant.md) · [Privacy and permissions](permissions.md)

## User-started research task scheduling

The foreground scheduler reuses the orchestrated run SQLite database. Planning
and listing contact no provider and load no model. Definitions store their full
prompt locally; list output shows only IDs, state and allocations.

```powershell
uv run --no-sync python -m ai_provider.task_scheduler plan public-python --prompt "Research public Python cancellation contracts" --model qwen3:8b --required-minutes 90
uv run --no-sync python -m ai_provider.task_scheduler list
```

When local compute is explicitly available, a selected sequence can be started:

```powershell
uv run --no-sync python -m ai_provider.task_scheduler run public-python --start --local-compute-available --available-minutes 110 --handoff-minutes 10
```

The example is an execution command, not authorization to start it during a
model-free implementation session. Put `--database PATH` before the subcommand
to select another application database. Tasks run sequentially in supplied order;
the first non-fitting task or failed worker stops the sequence. No waiting task
is shortened, reordered or started automatically. Each allocation includes
preparation; the supervisor receives its remaining task deadline. The ten-minute
default handoff reserve is outside the execution window.

Only existing supervised research workers are supported, with local-only Ollama,
the research CLI's `local_only` cost policy and trusted-local research tool controls.
Each worker receives a Markdown report target under
`artifacts/scheduled-research/<queue-and-task-digest>/report.md`. The digest includes
the resolved database path and task ID; task labels are never used as path segments.
Planning creates no report directories. The scheduler does
not start an Ollama service. Existing public retrieval/search permissions and
receipt controls still apply. Stopping the owned worker tree does not guarantee
an independent Ollama server stops computing. Distinct concurrent scheduler
invocations are not a global queue; claims protect each definition from duplicate
execution. Task completion is execution status, not a factual-quality certificate.

Use `defer TASK --reason TEXT` for a planned task. After verifying a stale running
worker has stopped, use `fail-interrupted TASK --reason TEXT` to record failure;
that command does not kill processes. Terminal definitions are not automatically
retried or resumed; plan a new ID for another attempt. Historical run/stage records
are preserved when the additive task table is initialized.

The initial task definition stores only the prompt, primary model, repository and
allocation. It cannot preserve explicit reviewer/tokenizer settings or launch the
acceptance/evaluation scripts. Keep a task requiring those settings deferred until
the definition contract is extended through an approved decision. Putting settings
in its prompt does not configure the worker. The PowerShell research launcher runs
immediately; it does not enqueue its arguments.

Research supervisor failure finalization also survives a broken progress-output
consumer: queued run IDs are still parsed, durable handoff state is recorded, and
the original exception is preserved. An optional final status log is written
before attempting to display it. This does not turn an interrupted worker into a
successful research result.
