# Mai-switch readiness checklist (switch accepted, 2026-11-20)

Bar (owner-set): Mai reaches same-or-higher capability than Muse CLI
plus reliable Dashboard/system wiring.

## Already evidenced

- [x] Interactive chat surface live (scoped), subprocess backend, master switch.
- [x] Drain executes queued runs on schedule (300s ticks, live-verified 2026-11-18).
- [x] Answer close-out autonomy: 2 verified autonomous close-outs 2026-11-18
      (boundary + supervision, incl. reconciling my parallel manual work).
- [x] Empty-completion guards: zero-work fails, hollow-with-iterations fails,
      hollow completions escalate to needs-attention.
- [x] Instruction budget: 96k override + growth-guard test.
- [x] Supervision doctrine: ADR-090 (dashboard-native, pause/kill/page).

## Fresh today, needs soak (no action, just time)

- [ ] Loop health diagnostics (toolless/repeat warnings): shipped, watch
      for false positives over the next runs.
- [ ] Mail dedupe: shipped, confirm noise actually drops.
- [ ] Supervisor lock retry: shipped, confirm busy outcomes vanish.

## Still open (real work)

- [x] Eval parity vs Muse CLI: round 2 complete 2026-11-19 (paid-vs-paid,
      Codex vs muse-spark-1.3, same base) — Mai 19 vs Muse 18, no
      zero-correctness task, wiring reliable all 5 turns; ~4x fewer tokens
      (1.87M/12.9K vs 8.12M/47.4K). Caveats: 5 pilot tasks; local-model
      grades unevaluated. Evidence: docs/plans/mai-parity-battery/scores.json.
      Migration decision: inbox `ee58d176` (2026-11-20), switch now with rollback window.
- [x] Stuck-run fallback: reconcile interruption cap shipped 2026-11-18
      (cancel + terminal note after repeated output-less interruptions).
- [x] Completion-to-inbox mail routing: unattended-only policy shipped
      2026-11-18 (terminal mails wired, doc-pointer rule recorded).

## Sign-off

Owner selected **Switch now with rollback window** on 2026-11-20 in inbox
`ee58d176076d4aa083e669955c0904d2`. Mai is the daily coding surface;
Muse CLI remains provisioned for overflow and rollback. See the
[daily coding and rollback protocol](mai-daily-coding.md).

Migration setup is COMPLETE; the two-week operational review is pending.
The soak items above remain observations to collect, not proven successes.
