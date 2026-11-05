# ADR-081: Absorb remote-operator's supervised loop into the workbench dashboard

Status: Accepted by the owner, 2026-11-05 (merge plan approved; remote-operator
frozen hackathon-only 2026-11-04).

## Decision and intent

Merge remote-operator's proven interaction parts into ai-workbench,
dashboard-first: one local place shows projects, AI tasks, plans, runs, and
approvals, with AI-driven development through a supervised loop
(chat → plan → approve → run → review diff → approve → applied, receipts at
every step). The remote-operator repo stays frozen in its submission state;
all product work happens here.

Absorb, don't port: workbench already owns the provider layer, an approval
bridge, run tracking, and shared approvals, so operator's interaction
patterns move over — not its plumbing. The provider boundary stays intact:
nothing bypasses `ai_provider` adapters or the orchestrator, and metering
lives above the adapters.

Owner rationale (2026-11-04/05): post-contest reuse by the same owner; the
hackathon inspiration-only rule no longer binds. Dashboard visual style stays
as-is while absorbing parts.

## What moved

| Operator source | Workbench target | Form |
|---|---|---|
| `control.py` tool loop (pending, events, never-replay, recovery-as-result) | `ai_agent/loop.py` | Adapted onto ChatClient/ToolRegistry/PermissionManager |
| Staged approvals (expiry, evidence re-verify, revalidate) | `ai_agent/shared_approvals.py` | Adapted onto TerminalApproval/digest binding |
| Park/resume + write reconcile | `ai_agent/recovery.py` (new) | Absorbed mechanics, P4 turn-boundary shapes |
| Project roots + staged project approvals | `ai_agent/staged_edits.py` (new) | Adapted, checks:none by design |
| Threads/plans/runs/drain/inbox-cursor | `ai_agent/supervisor_threads.py`, `supervisor_drain.py` (new) | Mechanics absorbed, P6 file-backed shapes |
| Receipts/events + cancel guard | `ai_agent/run_tracking.py` | Helpers only, no tracker rewrite |
| STT transcribe + ffmpeg handling | `ai_provider/stt.py` + `adapters/meta_asr.py` (new) | Neutral flow + adapter engine, injected metering |
| Translate-at-ingestion + manifest | `ai_provider/translation.py` (new) | ChatClient-backed engine, fail-closed 409 |
| Grant metering (admission gates, fingerprint, legacy refusal) | `ai_orchestrator/spend_ledger.py` (new) | P5 shapes, prototype |
| Dictation/progress/checklist/bell UI patterns | `apps/workbench_dashboard/web/*` | Adapted to dashboard style |
| Installer offers (uv/ffmpeg, Tailscale opt-out, task, probe) | `scripts/install-workbench.ps1` (new) | Local-first: no passwords, Docker, or phone flow |
| Chat → run queue (the post-submit gap) | Dashboard run-request + inbox approval + drain | New, most-restrictive default |

## What stayed frozen

Modal hosted app, judge accounts, sample CSV task + scripted reference,
Docker sample validation, Build/Review view structure, access-code phone
flow, PC sleep controls, hosted multi-tenancy. Workbench stays local-first;
remote access remains token + Tailscale, revisited only on owner call.

## Conflict resolutions (proposal vs proven behavior)

- P6's "no writes to plans/runs from dashboard" and "no persistent task
  queue" non-goals are superseded for exactly two flows: chat run-requests
  (queued runs + approval decisions) and staged-file approvals. Both were
  already foreshadowed by the shipped report-request flow. Data shapes still
  follow P6 (file-backed, inbox decision/clariant shapes).
- Operator behavior wins for loop mechanics (claim-file drain, never-replay,
  digest-bound approvals); proposals win for data shapes (P5 spend records,
  P6 run/inbox files, P4 turn groups and Did/Found/Next rendering).
- Chat fan-out defaults to `restricted` (no child spawns) via
  `chat_fanout_policy`, surfaced in receipts, run records, and UI; the owner
  picks otherwise per config. Explicit owner prohibition stays `denied`.
- Drain approval rule is answer-based, not status-based: a recorded `Approve`
  survives close-before-drain (close is archival; answers immutable after
  close). Refusal is explicit `Reject`, never a bare close.
- G6's per-client data isolation stays an open owner question: runs/inbox
  stay global with per-run project refs; no per-project data-dir split was
  designed.

## Consequences

- The supervised loop runs end-to-end on the dashboard with fixture-level
  executors; the real AgentLoop-as-executor wiring is the next integration
  (seams are injected callables, never imports).
- STT/Meta-ASR and translation carry coarse cent-ceiling prototype pricing;
  sub-cent precision and per-model pricing tables are P5 follow-ups. The ASR
  wire contract was proven via operator; this port still needs its own
  synthetic-clip probe before claiming end-to-end success.
- `POST /api/stt/transcribe` and non-English ingestion fail closed (409)
  until the owner wires a keyed engine, metering, and translator.
- Follow-ups: AgentLoop staging/executor wiring, `data/projects.json`
  registry file, run-cancel endpoint, per-project isolation (owner call),
  production STT metering/ledger binding, synthetic-clip ASR probe.
