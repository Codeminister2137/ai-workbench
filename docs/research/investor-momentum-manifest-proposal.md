# Offline ETF momentum qualification manifest proposal

Status: INCOMPLETE / NOT FROZEN. Prepared 2026-11-28 for run
`d4bf881f2ec74df69448e795ca6284b0`. No historical qualification consumed.
Owner acceptance of research sequencing is not acceptance of these parameters.

Authority: [qualification contract](../decisions/investor-momentum-qualification.md).
Read the three private plans: `investor-paper-design-20261123.md`,
`investor-coverage-note1-20261123.md`, `investor-strategy-note2-20261123.md`
from the main checkout's `docs/plans/`. Their honesty and disproof requirements
apply; their proposed separate store/scaffold is superseded by ADR-097.

## Local input investigation

The isolated worktree has no discovered CSV/Parquet history. Filename searches
of the main checkout's `data/` and `artifacts/` found no CSV, Parquet, Feather,
Arrow, historical-bars or momentum input candidates. This is a bounded search,
not proof that no history exists anywhere on the owner's PC. Council's data
directory contains `council.sqlite3`; read-only schema inspection found only
conversations, messages and sqlite_sequence, not historical-bar tables.
Additional filename searches under main-checkout `apps/` and `.tmp/` found no
CSV/Parquet/Feather/Arrow or historical/bars JSON candidates. Unsearched caches
and embedded data remain unknown. No provider download is authorized here.
Existing `investor/replay.py` records injected observations and fixture fills;
its zero-cost fixture assumptions are not historical qualification evidence.

Source: UNRESOLVED. Input paths, provider/feed, acquisition timestamp, licensing,
timezone, exchange calendar, raw/adjusted columns, action records and SHA-256:
UNAVAILABLE. No dataset is represented as audited. Do not substitute synthetic
fixtures or fetch Alpaca/IEX data to fill this gap.

## Proposed freeze package A (requires owner decision)

- Universe: SPY and QQQ, fixed throughout; no substitutions, leverage or shorts.
  This tests two correlated broad-market ETFs, not sector-wide generality.
- Strategy: `etf-tsm-12-1-v1`; daily regular-session bars, monthly signals.
  At the final session close of month t, signal is adjusted total-return close
  at month t-1 end divided by that at month t-12 end, minus one. Positive
  signals allocate 50% per ETF; otherwise that sleeve holds USD cash at 0%.
  No volatility targeting, borrowing or parameter selection.
- Inputs: 2004-01-01 through 2025-12-31 inclusive; first-year warmup,
  performance 2005-01-01 through 2025-12-31. Missing warmup voids admission.
- Signal adjustment: explicit split and reinvested-dividend total return.
  Executable prices: raw next-session regular-session open; splits alter shares,
  cash dividends accrue on ex-date and pay on pay-date, without double counting.
  Missing action provenance blocks qualification; no silent price-only proxy.
- Rebalance at the next session open following each signal. Fractional shares,
  no queue simulation; adverse haircut 10 basis points per buy/sell notional
  (5 spread + 3 slippage + 2 impact), plus 1 basis point fees per side.
  These are proposed stress assumptions, not observed market estimates.
  Charge costs on actual turnover, including liquidation; USD, no FX or taxes.
- Liquidity admission: each symbol's preceding 63 sessions must have median raw
  close times raw volume >= USD 100 million at every rebalance. No replacement
  on failure: mark audit failure and stop. Extended hours excluded.
- Walk-forward: initial context 2004-2008; fixed non-overlapping annual test
  windows 2009 through 2025, each January 1 through December 31, using only
  prior observations for signals. No training, optimization or variant selection.
  Full ten-year disproof windows end each December 31, 2014 through 2025
  (2005-2014 first, 2016-2025 last), shifting one calendar year each time.
  Overlap is disclosed; these are not independent statistical samples.

## Audit and disproof specification to freeze with the package

Before execution preserve an audit row for EACH symbol: observed/expected
sessions, duplicates, missing/nonfinite/nonpositive prices, volume defects,
timezone/calendar provenance, first/last dates, splits, dividends, adjustment
reconciliation, liquidity evidence and source/feed limitations. Missing sessions
remain gaps; never forward-fill. Missing execution/valuation/signal inputs void
the run, rather than dropping those observations from the denominator.
Unknown IEX-versus-consolidated-tape differences remain explicit limitations.

Every output begins with universe, dates, source hashes, adjustment policy,
fills, spread/slippage/impact/fees, queue omission, dividends, and missing audits.
Compute daily net equity returns and annualized Sharpe sqrt(252)*mean/std
with risk-free rate zero and sample standard deviation (ddof=1). Zero variance
is undefined and cannot pass. Ten-year Sharpe <= 0 disproves that window.

Proposed concentration test: pre-label months containing any audit flag before
strategy results; edge is concentrated if summed net log returns outside flagged
months <= 0 while summed returns in flagged months > 0. No positive total edge
also fails. Report flagged/unflagged contributions separately. This operational
definition needs owner acceptance; do not invent a threshold after results.
Two consecutive annual-ending disproof windows void the run; one missing audit
row for a traded symbol voids it immediately. Distinguish hypothesis failure,
invalid data, and execution/replay defects. None grants connected launch.

## Freeze, preservation and replay admission

After owner acceptance AND local input audit, record exact input/action/calendar
paths and byte hashes, code commit, manifest byte hash and accepted inbox ID.
Leave this proposal intact; preserve the accepted manifest as a separate version.
No mutable latest-data references, post-result parameter edits or silent reruns.
Use the existing Council journal under ADR-097 for decisions and linked outcomes;
do not introduce a store. Qualification runner implementation must first reconcile
historical share/action/cost semantics with the current fixture replay contract.

Preserve original failure reports as well as successful reports. A deterministic
replay must read frozen local inputs and original decisions without providers or
fresh deliberation, compare allocations, fills, costs, equity, audit flags and
window verdicts, and byte-compare canonical report content (exclude run IDs and
wall-clock metadata explicitly). Record both hashes and any divergence. No
historical run or replay has been executed; no disproof result exists yet.

Dashboard decision: `f9c058c62a2848858bad0493440dd273`, stamped owner gate
`investor-momentum-offline-freeze`. Created and re-read in the existing main
checkout dashboard store. The separately owned trial item `86ee6792` was read:
owner answered A for SPY/QQQ daily first trial; this does not select monthly
offline research parameters or supply historical data. No trial item changed.

Next action: resolve the dashboard freeze
decision, audit chosen inputs, then implement and test the offline runner within
the accepted contract. Completion requires accepted frozen bytes, audited data,
preserved disproof report and independently checked deterministic replay.
