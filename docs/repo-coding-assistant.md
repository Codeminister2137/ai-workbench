# Repo Coding Assistant CLI

The repo assistant composes provider-neutral routing, repository context and
explicit tool permissions. It supports offline planning, local or hosted answers,
approved coding actions, persistent chat and supervised public research.

## Start here

Run from the repository root. These commands prepare a plan without inference:

```powershell
uv run --no-sync ai-assistant --help
uv run --no-sync ai-assistant --mode plan "Explain this repository's architecture."
```

For normal Windows use, `scripts/repo-assistant.ps1` loads the ignored `.env`,
selects a local transcript directory and invokes the stable `ai-assistant` command.
The wrapper may create log directories even when the underlying request is planned.

Provider execution requires `--execute`. Model availability, client sign-in and
billing entitlement are separate checks. The default task privacy is `local_only`;
the shipped cost ceiling is `prepaid_credits_allowed`. Private preferences and
explicit CLI flags can narrow that ceiling. Do not assume that an available API
key authorizes transmitting repository contents or spending credits.

## Guides by workflow

| Goal | Guide |
| --- | --- |
| Plan, ask, review or implement a bounded task | [Getting started](repo-assistant/getting-started.md) |
| Run staged validation, scrutiny and repairs | [Foreground orchestration](repo-assistant/orchestration.md) |
| Retrieve public sources and produce a report | [Research tools and acceptance](repo-assistant/research.md) |
| Configure reviewers, modes and token admission | [Research review](repo-assistant/research-review.md) |
| Save or resume a local conversation | [Persistent chat](repo-assistant/chat.md) |
| Select native agents, preferences and fallback | [External agents](repo-assistant/external-agents.md) |
| Understand writes, logs and data boundaries | [Permissions and privacy](repo-assistant/permissions.md) |
| Plan and explicitly start budgeted research jobs | [Task scheduling](repo-assistant/scheduling.md) |
| Carry common tools, scoped approvals and skills through fallback | [Common tools and approvals](repo-assistant/common-inspection.md) |
| Retain coding receipts and supervise foreground children | [Coding continuity](repo-assistant/coding-continuity.md) |

## Current limits

The accepted shared-tools and daily-development direction is tracked in the
[development roadmap](repo-assistant/development-roadmap.md) and ADR-040.
Cross-agent skills, permission mappings and coding/process continuity remain
incomplete; roadmap approval does not establish current capability parity.

Research inference is local-only; public fetching and search still transmit public
URLs and queries outside the machine. Receipts prove retrieval and writes, not
factual truth. Quality-first review remains opt-in: the representative evaluation
found false approvals and explanation defects. The integrated sustained acceptance
is incomplete. A structurally accepted report is not a quality certificate.

The scheduler is a foreground, user-started workflow. Planned tasks do not start
automatically, and a task must fit its full allocation plus separate handoff time.
Generic process-wide cancellation and a global job queue are outside its scope.

## Fixed local acceptance jobs

[ADR-043](decisions/ADR-043-fixed-local-native-acceptance-jobs.md) implements a
separate fixed native coding job. Its [v1 definition fields](repo-assistant/acceptance-job-proposal.md)
are strict: no commands, prompts or arbitrary executables. The model can read a
generated fixture and edit only `source.py`; the host runs fixed protected tests.
Execution currently requires Windows retained process-tree ownership and an
existing Ollama executable. No runtime or model is installed automatically.

Use the project environment to inspect help or plan a reviewed definition:

```powershell
python -m uv run --no-sync python -m ai_provider.acceptance_jobs --help
python -m uv run --no-sync python -m ai_provider.acceptance_jobs --database artifacts/orchestrated-runs.sqlite3 plan --definition artifacts/acceptance-definition.json
python -m uv run --no-sync python -m ai_provider.acceptance_jobs --database artifacts/orchestrated-runs.sqlite3 list
```

Create the JSON definition using every field in the contract table. Select an
explicit local catalog route, model, unused numeric-loopback port, pinned positive
compatibility identity and resource limits. For example, a 300-second allocation,
60-second request limit, 8192 context, 512 output and four iterations are planning
examples; they do not choose a compute window for you. Planning/listing perform
no provider requests, fixture creation or runtime startup.

After selecting a live compute window, explicitly run the chosen IDs in order:

```powershell
python -m uv run --no-sync python -m ai_provider.acceptance_jobs --database artifacts/orchestrated-runs.sqlite3 run example-job --start --local-compute-available --available-minutes 10
```

This command starts local inference and a foreground-owned runtime. It refuses an
occupied endpoint, stale compatibility evidence or insufficient full allocation;
failure and unverified cleanup stop the sequence. The final 15 seconds of each
allocation are reserved for cleanup/handoff. Estimated input admission and
provider usage remain distinct; a passing fixture proves only its bounded effects.

Artifacts use hashes of database/task identity under `artifacts/acceptance-jobs/`.
Definitions, receipts and results remain in the selected database. Restart leaves
running jobs for reconciliation; never replay them automatically. After inspecting
ownership receipts and reconciling effects/processes manually, mark an interrupted
job failed using `fail-interrupted ID --reason TEXT --reconciled`. `defer ID --reason
TEXT` applies only to planned jobs. A retry needs a new task ID and definition;
do not delete or overwrite earlier evidence.

`trusted_local` grants broad tool permissions. Logs, saved reports and transcript
databases can contain private text or model-selected quotations. These generated
files are ignored by Git; review them separately before sharing them.

## Related documentation

- [Environment and secrets](environment.md)
- [Architecture and package boundaries](architecture.md)
- [Decision index](decisions.md)
- [Development and Git workflow](git-workflow.md)

The former monolithic guide is organized into the pages above. Its entry path
remains stable; use the workflow pages for detailed commands and configuration.
