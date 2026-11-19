# ADR-092: Investor live-data source (Alpaca paper selected)

Status: Alpaca paper selected by owner, 2026-11-19 (inbox
`d50c644d9f8c44b992f1d6c83d13fe87`, answer A; closed dashboard resolution
verified). First broker, not exclusive. No integration is implemented here.
Coverage research and autonomous paper policy: [ADR-093](ADR-093-investor-coverage-and-paper-autonomy.md).

## Problem

The investor extension needs live market data + fill simulation for
strategy research. The owner accepted the broker-paper-API direction;
which broker was undecided. Candidates differ in eligibility, cost to
start, universe, and paper fidelity.

## Research

Historical comparison below predates the selection. Corrections checked
2026-11-19: XTB discontinued API access on 2025-03-14; OANDA's official v20
exclusions name TMS BROKERS S.A. and Global Markets, rather than all EU access.
See [current official sources and coverage findings](../research/investor-coverage-20261119.md).
The old XTB candidate and blanket OANDA exclusion below are superseded.

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

## Original recommendation (historical)

The original recommendation favored Alpaca paper-only and considered IBKR
and XTB for broader coverage. Owner selected Alpaca as the first broker.
XTB is no longer a viable API candidate; IBKR funding is not authorized.
ADR-093 records the subsequent broader-research and autonomy decision.

## Consequences

- Alpaca is selected; additional brokers and the first execution universe remain
  unselected pending the broader research direction in ADR-093.
- The selected broker's paper limits become the documented caveats on
  every strategy result.
- A funded-account prerequisite (IBKR) or live-eligibility question
  (Alpaca) is an owner action, never an agent signup.
