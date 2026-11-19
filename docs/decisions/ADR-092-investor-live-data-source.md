# ADR-092: Investor live-data source (research recorded, selection open)

Status: Research recorded 2026-11-19; broker selection awaits owner
decision (inbox brief filed alongside). Paper trading only; no broker
selected, no accounts, no keys, no orders.

## Problem

The investor extension needs live market data + fill simulation for
strategy research. The owner accepted the broker-paper-API direction;
which broker was undecided. Candidates differ in eligibility, cost to
start, universe, and paper fidelity.

## Research

Full comparison: `docs/plans/investor-broker-selection-20261119.md`
(dated sources, unknowns preserved).

- Alpaca paper-only: global email signup, free, $100k sim, separate
  keys/endpoint, IEX data; no dividends/slippage modeling. PL *live*
  eligibility unconfirmed (irrelevant for paper).
- IBKR paper: fullest universe, EU eligible — but needs a funded Pro
  account first; TWS API needs a local Gateway process.
- XTB xAPI demo: Polish, quick demo accounts, CFD/forex scope; demo
  data rules largely undocumented.
- OANDA v20: out — EU API support dropped in practice.

Data/credentials/logging: paper keys via env, never logged; fills and
curves persisted locally without secrets; fixtures remain the offline
gate. Investor tuning/eval artifacts stay private.

## Recommendation (not a decision)

Start with Alpaca paper-only (zero friction, documented limits); keep
IBKR for EU assets once funded; keep XTB for CFD/forex focus. The owner
selection brief carries options with pros/cons; this ADR records the
outcome once the owner chooses.

## Consequences

- No integration code is written until the owner selects a broker.
- The selected broker's paper limits become the documented caveats on
  every strategy result.
- A funded-account prerequisite (IBKR) or live-eligibility question
  (Alpaca) is an owner action, never an agent signup.
