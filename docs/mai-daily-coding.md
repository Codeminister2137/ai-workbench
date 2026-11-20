# Daily coding with Mai

Owner decision: inbox `ee58d176076d4aa083e669955c0904d2`, answered
2026-11-20: **Switch now with rollback window**. No additional rationale
was supplied. This adopts the switch described in the source brief.

## Daily workflow and defaults

Use dashboard Mai for daily coding: choose Agent in a coding chat, or
file an agent task for the existing queued-run drain. Ask remains available
for read-only questions. Existing sessions retain their selected mode.
Muse CLI stays installed and provisioned for overflow, complex work and rollback.

Local dashboard settings: chat_agent_enabled=true, mai_backend=subprocess,
drain_interval_seconds=300. The existing owner-selected chat approval policy
is retained. Mai uses user-config.toml (allowances_allowed, standard quality,
trusted_local) and the orchestrator catalog; production run arguments do not
pin a provider or model. The dashboard's Ollama Ask settings do not select
Mai's coding route. Existing privacy, quality floors, spend grants, deadlines
and approval boundaries continue to apply.

## Weekly usage and quality tracking

Dashboard owner tasks dated 2026-11-27 and 2026-12-04 link to this protocol.
At each review, inspect the preceding week's Mai run receipts and coding chat
reports and append one row below. Record completed/failed/needs-attention runs,
correctness defects and owner rework, interruption/recovery problems, wiring
failures, Muse overflow count/reasons, observed tokens/cost and latency when
available. Cite run/session IDs and receipts. Unknown usage remains unknown;
missing token attribution is not zero spend. Avoid private prompts in this log.
Owner feedback is needed for usability and correctness observations not visible
in receipts. Reviews are dashboard tasks, not a new scheduler or model allowance.

| Period / review | Evidence | Quality, recovery and wiring | Usage / latency | Overflow | Outcome |
| --- | --- | --- | --- | --- | --- |
| Baseline, 2026-11-19 | Source brief; docs/plans/mai-parity-battery/scores.json (private local evidence) | Reported five-task pilot: Mai 19, Muse 18; wiring 5/5 | Reported Mai 1.87M input / 12.9K output vs Muse 8.12M / 47.4K | Not measured | Pilot supports switch; not general parity proof |
| 2026-11-20 to 2026-11-27 | Pending | Pending | Unknown | Unknown | Review due 2026-11-27 |
| 2026-11-27 to 2026-12-04 | Pending | Pending | Unknown | Unknown | Rollback review due 2026-12-04 |

## Rollback window and criteria

The two-week window runs 2026-11-20 through 2026-12-04. At either review,
roll back daily coding to Muse if quality or usage regresses: substantive
incorrect results/rework, persistent hollow/stuck completions or dashboard
wiring failures, or higher observed usage for comparable work without a quality
benefit. A privacy/approval breach warrants immediate stop and escalation.
Compare like tasks and effective routes; retain failures and label missing
measurements. A five-task aggregate is not a numeric production threshold.
Insufficient evidence must be reported to the owner rather than called a pass.

Rollback: use Muse CLI for daily coding, select Ask for chats that should stop
editing, and cancel or pause affected Mai runs through dashboard supervision.
Do not delete sessions, worktrees, receipts or the Muse setup. The owner may
choose to keep Mai for bounded work; closing a review records that choice and
its evidence. No automatic provider switch, grant renewal or destructive reset.
