# ADR-094: Supervisor follow-up guarantee and inbox chain reports

Status: Accepted direction, 2026-11-19 (loop plan v3, owner `go`);
implementation on feature/supervisor-evolution.

Extends [ADR-090](ADR-090-dashboard-supervision-authority.md): no new
service, daemon, watcher, or tab. The supervisor grows follow-up
issuance and report finalization as native duties.

## Problem

Work items reached terminal states with no tracked follow-up: owner
answers without close-outs (cap refusals were flagged, never retried),
failed runs with only a note, adopted ideas with no elaboration task,
E2E follow-up refusals stamped but never retried, and closed answer
chains with no durable summary. Each gap was found live on 2026-11-19.

## Decision

1. Event-time issuance: every trigger files its follow-up synchronously
   (owner answer → close-out; agent close → source report-back; E2E
   verdicts → fix tasks; run failure → triage task; adopted idea →
   elaboration task; report supersede → link entry). Cap refusals set a
   pending flag instead of raising, and dedupe keys prevent doubles.
2. Tick-time self-audit (`supervisor_tick_audit` on the scheduled
   drain tick): retries refused filings and detects orphans
   (answered-no-closeout, failed-no-triage, adopted-no-elaboration).
3. Probe verdict: fresh failed runs without a triage task read
   `dead-end` in Fleet (with triage: `broken`, unchanged).
4. Chain reports: a supervisor-issued `report` inbox type filed at
   chain end (initial + evolution + achieved + links). Acknowledge
   archives out of the badge; acknowledged reports are immutable
   except append-only supersede links; reopening stays the explicit
   owner override.

## Consequences

- New follow-up duties go in dashboard supervisor flows, never in
  agents, Mai-side code, or new processes.
- The weekly forgotten sweep keeps its backstop role; healed loops
  stop filing by the resolved-first rule, so no sweep rule is removed.
- Historical closed chains are not auto-reported (no badge flood);
  the deepseek saga is migrated by hand as the proof chain.
- Run-failure triage and adopted-idea elaboration were carved out as
  battery tasks T1/T5 under frozen link keys (`triage_for`,
  `elaboration_for`); the verdict and audit read those keys, and the
  winning diffs are adopted into this branch.
- The idea trigger fires on adoption, not capture: raw captures stay
  triage-filtered by design. One-line change if the owner prefers filed.
- Auto-handoff detection/rendering ships unwired; emit thresholds and
  loop wiring need a separate owner confirmation.
