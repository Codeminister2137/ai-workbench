# Mai agent

The personal AI execution surface: dashboard chat turns that run tools
in isolated worktrees, Mai-routed model sessions behind the orchestrator,
and the drain that executes queued runs unattended.

Key areas: `packages/ai_agent` (loop, tools, Mai sessions),
`apps/workbench_dashboard/dashboard_chat.py`, `mai_run.py`.

Current state: interactive surface live; supervision placement undecided;
switch-readiness tracked in the Mai Roadmap (Plans tab).
