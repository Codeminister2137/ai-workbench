# Investor slice 2: offline ETF momentum qualification first

Status: Accepted direction, 2026-11-28. Strategy selection COMPLETE;
qualification and first trial design INCOMPLETE.

## Authority and scope

Owner source `426eb4f248614154a8c929743ffd20cd`, answer A:
"Qualify ETF momentum offline first", implemented by closeout run
`db51e645a3e74ae49f9a1921bc74f352`. No additional rationale supplied.
This selects research sequencing, not a successful backtest or trial launch.

The source explicitly asks for exact symbols, cadence and launch window;
the answer supplies none. SPY/QQQ were examples in bounds source
`472cea09ec2048fc89a2f94e6908c3c6`, not owner-selected symbols.
Existing runtime defaults do not supply missing owner approval.

## Alternatives and consequences

A (chosen and technically recommended) qualifies ETF time-series momentum
offline before connected paper execution. It follows the existing research
disproof protocol and can expose a failed hypothesis, but requires validated
historical data and delays broker evidence. B, a mechanics-only paper smoke
trial, would produce broker/journal evidence sooner but changes the purpose
and provides no strategy-quality evidence. C defers connected trials and
avoids acting risk but delays broker evidence. Neither B nor C was selected.

## Qualification contract and remaining freeze

The private plans `investor-paper-design-20261123.md`,
`investor-coverage-note1-20261123.md` and
`investor-strategy-note2-20261123.md` inform this direction. Their older
storage/scaffold proposals are superseded by ADR-097 and the existing loop;
they do not authorize another store or service.

- Candidate family: ETF time-series momentum, daily bars first. The plan's
  12-1 and 6-1 variants are candidates, not a selected parameter set.
- Before running qualification, freeze strategy/version, exact universe,
  historical bar range and source, corporate-action treatment, fill/cost
  assumptions and walk-forward windows. Record the manifest and input hashes.
  Resolve material choices before representing this as a frozen design.
- Audit each symbol for completeness, freshness and corporate actions;
  preserve gaps and missing audit rows. Every result needs an honesty header
  covering universe, range, fills, slippage, queue, impact, fees, dividends
  and unresolved audit limitations. Do not silently interpolate gaps.
- Preserve the plan's disproof: trailing ten-year Sharpe <= 0 after haircuts,
  or edge concentrated in honesty-flagged months, disproves the hypothesis.
  Use walk-forward evidence for parameter claims. Two consecutive disproof
  windows or one missing traded-symbol audit row voids the run. Freeze window
  definitions and haircuts before consuming data; do not tune on results.
- Journal decisions and linked outcomes under ADR-097; compare deterministic
  replay with originals. Fixture tests prove software contracts only, not
  momentum quality, valid historical coverage or profitability.

No historical qualification was run in this closeout. No dataset, winning
variant, exact symbols, cadence or launch date is claimed frozen. Offline
qualification preparation may proceed without launching a connected trial.

## Connected trial admission

Retain caps from `472cea09`: five orders/day, $1,000/order, $5,000 open
exposure, two or three fixed liquid US ETFs, at most five trading days,
paper only and journal proof. Before admission require passing qualification,
owner-confirmed exact symbols/cadence/window and independently evidenced
runtime safety including restart/ambiguous-order recovery. Runtime work is
tracked separately on `8f1ccefb6bc64cf9b94b2514640f2c15`; this decision
does not declare it complete. No broker calls, paid data, paid inference,
new data transmission, scheduler or launch authorization is added here.

Next action: prepare the complete offline qualification manifest and freeze
its material choices through the dashboard before the first historical run.
Completion requires a frozen manifest, audited data and a preserved disproof
report; a failed hypothesis is a valid research outcome, not launch readiness.
