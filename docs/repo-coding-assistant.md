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
| Carry common inspection tools and skills through fallback | [Common inspection](repo-assistant/common-inspection.md) |
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
