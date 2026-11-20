# Mai agent

The personal AI execution surface: dashboard chat turns that run tools
in isolated worktrees, Mai-routed model sessions behind the orchestrator,
and the drain that executes queued runs unattended.

Key areas: `packages/ai_agent` (loop, tools, Mai sessions),
`apps/workbench_dashboard/dashboard_chat.py`, `mai_run.py`.

Current state: daily coding uses dashboard Mai (owner decision 2026-11-20).
Dashboard-native supervision is accepted in ADR-090. Muse CLI stays available
for overflow and rollback. Weekly checks and the 2026-12-04 review follow the
[daily coding protocol](../mai-daily-coding.md).
