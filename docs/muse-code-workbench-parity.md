# Muse Code vs workbench agent — parity and switch-over reference

Date: 2026-11-05. Reason: `api.meta.ai` transport errors interrupted Muse Code
sessions, so execution moves to the workbench agent while Muse stays the main
development model. This doc records what changes, what is lost, and what to
implement. It is a living reference: update it when either side gains features.

## Model layer: parity (same backend, same failures)

- Muse Code runs on Meta Muse Spark; the workbench `meta` adapter
  (`packages/ai_provider/src/ai_provider/adapters/meta.py`) calls the same
  `https://api.meta.ai/v1` Responses endpoint with `muse-` models
  (admission-gated; Contributor variants refused on privacy grounds).
- Consequence: **switching vehicles does not dodge backend or network
  outages.** The 2026-11-05 transport errors coincide with this PC's router
  DNS failing (both `api.meta.ai` and `github.com` unresolvable); any local
  Meta call fails either way. Diagnose network before blaming the vehicle.
- Resilience advantage (workbench): provider switching. The workbench runs
  the same agent on Ollama locally when Meta is unreachable; Muse Code has
  no model fallback. Tonight: Ollama (`gpt-oss:20b`, `qwen2.5-coder:14b`
  available offline); Muse via Meta when DNS recovers.

## Capability matrix

| Capability | Muse Code (this CLI) | Workbench agent | Verdict |
| --- | --- | --- | --- |
| Read/write/edit files | read/write/edit tools | read/list/create/edit/stage tools | Parity (workbench adds staged review) |
| Shell + processes | powershell, PTY input, monitors, cron | run_command, python_runtime | Gap: no background monitors or scheduler; `day_cycle.py`/sleep helpers are manual |
| Code search | ripgrep wrapper | find_files, grep_search | Parity |
| Web search/fetch | web_search, web_fetch | research tool files exist (depth not audited here) | Likely gap; verify before web-heavy work |
| Image generation | image_generation | none | Gap (irrelevant to current roadmap) |
| Subagents | native pool (up to 64) + workflow fan-out | one-level `delegate_task` | Gap: depth and scale |
| Skills | ~25 (git, python-env, taste, plan, doctor, …) | framework + 3 (`review-repo-change`, `git-safety`, `durable-test-collateral`, 2026-11-09) | Narrowed: breadth still differs, top-leverage two ported |
| Memory | memory files | transcripts, sessions, CURRENT_CONTEXT | Partial: workbench has more durable run records, less cross-day recall |
| Asking the owner | request_user_input (live only) | inbox decisions/approvals (async, persists) | Advantage workbench for unattended |
| Approvals/safety | approval modes + shell sandbox | TRUSTED_LOCAL/permissions/fan-out/allowlist + AGENTS.md | Parity with different trade-offs |
| Git discipline | git skill + AGENTS.md | AGENTS.md + review skill | Parity (same repo conventions) |
| Dashboard/inbox/owner tasks | none | full loop | Advantage workbench |
| Receipts/evidence | session logs | run receipts, approvals, usage ledger | Advantage workbench |

## Automation level (how much runs itself)

Automatic today (pure code): validators (P7, staged edits, backup denylist),
state machines (drain claims, approvals, receipts), HTTP endpoints, backup
snapshots, sleep timers, tests/lint/type gates.

Needs a driver (the gap): nothing invokes the drain or agent loops on its
own — the drain driver was explicitly deferred by the owner. Tonight the
gap is supplemented manually: tasks are driven by invoking the drain /
`ai-assistant` CLI per step, approvals flow through the inbox as designed.

Not automatic by design: owner decisions, secret provisioning, push
transport, anything needing the network while DNS is down.

## Missing features to implement (priority order)

1. Port the relevant Muse Code skills — PARTLY DONE 2026-11-09: `git-safety` + `durable-test-collateral` landed with contracts + tests. Remaining: python-env placement, taste (dashboard).
2. Drain driver — DONE (`DrainScheduler` + wiring + tests; periodic ticks, off unless the host starts it).
3. Monitor/cron equivalent for long-running watches — only if a real
   unattended need appears; manual driving covers tonight.
4. Deeper subagents — only if one level proves insufficient in practice.
5. Research depth — VERIFIED 2026-11-09: searxng discovery + pinned-HTTPS fetch + evidence-tracked reports (`research.py`, `research_search.py`, `research_http.py`). Web-heavy work cleared.

## Re-audit verdict (2026-11-09)

Switch-ready for supervised and unattended repo work: inbox approvals, receipts, staged review, and provider fallback all exceed Muse Code. Remaining gaps before interactive-CLI parity: one-level `delegate_task` only (no deep fan-out), no live owner-prompt equivalent (inbox is async by design), skill breadth (~25 vs 3), and weaker cross-day recall. None blocks the switch for loop-driven work; interactive daily-driver use should wait for deeper delegation + live prompts.

## Operating rule during the switch

Muse via Meta remains the main development provider whenever reachable;
Ollama is the automatic fallback for local runs. Judge work by the repo's
own tests and receipts, not by which vehicle drove. Keep this doc current.
