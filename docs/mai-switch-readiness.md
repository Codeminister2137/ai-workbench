# Mai-switch readiness checklist (draft for owner sign-off, 2026-11-18)

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
      Migration decision brief: inbox `ee58d176` (2026-11-20, open).
- [x] Stuck-run fallback: reconcile interruption cap shipped 2026-11-18
      (cancel + terminal note after repeated output-less interruptions).
- [x] Completion-to-inbox mail routing: unattended-only policy shipped
      2026-11-18 (terminal mails wired, doc-pointer rule recorded).

## Sign-off

Owner signs by answering the linked inbox item: switch approved,
switch approved with conditions (state them), or not yet (state the blocker).
