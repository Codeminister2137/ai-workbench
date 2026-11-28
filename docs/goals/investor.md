# AI Investor

## Goal

Paper-trading research track: honest backtests and bounded paper-live
trials on Alpaca paper (ADR-092), journaled for offline replay on the
Council SQLite slice. No live trading until a later explicit decision.

## Non-goals

Live trading, real-money credentials anywhere, autonomous order
placement before the autonomy policy decision.

## Owner

Jakub.

## Health

on-track — owner 2026-11-24: design + coverage research drafted;
Alpaca signup pending with owner.

## Connected plans

- `docs/plans/investor-paper-design-20261123.md`
- `docs/plans/investor-coverage-note1-20261123.md`
- `docs/plans/investor-strategy-note2-20261123.md`

## Next action

Qualify ETF time-series momentum offline first (owner A on `426eb4f2`).
Prepare and freeze the qualification manifest, audit historical data and run
the disproof protocol before a connected trial. Exact symbols, cadence and
launch window remain pending; scaffold defaults are not owner approval.
See [accepted direction and qualification gates](../decisions/investor-momentum-qualification.md).
The Council SQLite journal and bounded loop already exist; runtime safety
and connected-trial readiness remain separate acceptance work.
