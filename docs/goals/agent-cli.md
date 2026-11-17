# Agent / CLI (Mai)

## Goal

A provider-neutral agent loop plus the repo coding assistant CLI that runs at
or above commercial quality: tools, permissions, delegation, streaming
progress, reviewable runs with receipts.

## Vision (owner, 2026-11-16)

Mai is our intended agent, built upon `ai_provider` and `ai_orchestrator`,
with user interaction through the Dashboard or the CLI. We retain full
transcripts and control over it, and use that record to continuously
improve it and make it learn on our development. Everything vendor
agents can do is the baseline: we may do features better or add more,
but Mai must never stay behind commercial products. Interactive Mai
(dashboard chat as a conversational agentic loop, not single-shot Q&A)
was ordered as part of the larger plans and remains queued after the
Mai-as-service batch resume slice.

## Non-goals

Model contracts (provider), routing policy (orchestrator), dashboard
presentation (dashboard).

## Owner

Jakub.

## Health

on-track — R1–R3 + R5 streaming merged; Mai runs via dashboard with
pre-approval; supervision design pending owner placement decision.

## Connected plans

- `docs/plans/p4-agent-ux-research.md`
- `docs/plans/p4-agent-ux-proposal.md`
- `docs/plans/mai-supervision-design.md`
- `docs/plans/ai-trainer-framing.md`
- `docs/plans/cli-development-readiness-review.md`
- `docs/plans/opencode-go-integration-first-20261022.md`
- `docs/plans/opencode-go-ide-handoff-20261022.md`
- `docs/plans/repo-assistant-cli-parity-plan.md`

## Next action

Owner decision on Mai supervision placement/authority/paging, then implement.
Queued (owner-approved 2026-11-14): Mai-as-service batch resume first
(unattended drain driver + boot reconciliation), then interactive Mai —
dashboard chat was always meant to be agentic, not single-shot Q&A
(needs conversational loop + scope-based approvals + presence routing).

Update 2026-11-17: supervision placement decided (inbox 8962425c, option A:
fleet probe now, in-CLI later); the fleet probe merged. Remaining
supervision work is unscheduled, not owner-blocked.

## Mai-switch acceptance bar (owner 2026-11-17)

Mai becomes the primary interface when it reaches same-or-higher
capabilities as the Muse CLI and is reliably wired into the Dashboard
and the workbench system. No switch before the readiness checklist
(empty-completion guard, instruction budget, stuck detection, redeploy
reliability, mail discipline) is verified green.
