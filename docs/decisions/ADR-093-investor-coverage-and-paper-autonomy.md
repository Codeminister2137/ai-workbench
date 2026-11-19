# ADR-093: Investor coverage research and autonomous paper policy

Status: Accepted direction, 2026-11-19; research closeout complete;
runtime integration remains future work.

## Owner decision and rationale

Source: inbox `2592e3e4e34d4a7db970482ef7f9f48d`, answer **B: Broader
coverage research first**. The owner wants autonomous, cost-free experiments
while money is simulated, with full transcripts or at least decision records
to support learning from experience. They explicitly requested research into
similar systems and political/geopolitical effects on markets.

Prior decision `d50c644d9f8c44b992f1d6c83d13fe87` selected Alpaca paper as
the first broker, not an exclusive broker. Its dashboard resolution is closed;
this checkout's older ADR-092 had not yet recorded that selection.

## Accepted policy

- Research broader asset classes and broker coverage before fixing the first
  execution universe. Research coverage is not an executable instrument list.
- Autonomous research and paper decisions do not require per-order human
  review while funds remain simulated. Real-money trading, paid data/services,
  funded accounts and paid inference are not authorized by this decision.
  Existing resource, privacy and provider-admission rules still apply.
- Retain at least an inspectable decision record for every decision, including
  hold, rejected and failed decisions. Full observable transcripts may supplement
  records when privacy permits; hidden model reasoning is not required.
- Records must identify the run, profile/model/prompt version, observation and
  decision times, source references and information available then, proposed
  allocation, rationale, uncertainty, alternatives, risk checks, action or hold
  reason, and simulated outcome/fill assumptions. Link later outcome assessment
  and lessons to the original immutable decision; do not rewrite losing history.
- Learning means evaluating recorded hypotheses and outcomes. It does not prove
  model improvement or authorize unreviewed changes to execution permissions,
  budgets or privacy. Keep secrets and sensitive transcripts out of records.

The old Council v1 plan's general exclusion of autonomous decision-making
remains historical scope for that prototype. This owner decision specifically
extends the Investor paper research direction; it does not change the whole
Council's authority. No storage format, new service or dependency is selected.

## Alternatives and consequences

A small Alpaca universe with human review would be simpler and start sooner,
but would delay testing the owner's intended autonomous workflow and leave
coverage gaps unexplored. Broader research first (chosen) informs instrument
and broker design, but delays experiments and requires checking entitlements,
eligibility and simulation differences. The prior technical recommendation was
the small-universe option; the owner's broader choice is authoritative.

Autonomous paper operation enables uninterrupted experiments and more comparable
decision histories; it also permits simulated losses and compounds bad signals.
Decision records and out-of-sample evaluation make those failures inspectable;
they do not make paper returns evidence of live profitability.

## Research and implementation boundary

See [dated coverage and event research](../research/investor-coverage-20261119.md).
It corrects the old XTB API candidate and the overbroad OANDA exclusion.
Recommended sequencing there is engineering advice, not an owner-selected
universe or an additional broker selection.

Current `apps/ai_council/investor` supplies deterministic fixture evaluation,
profiles and a stub judge. It has no broker execution loop or durable Investor
decision journal. This decision closeout adds no autonomous runtime and makes
no claim that recording or self-learning is already implemented.

Next implementation slice: define a replayable decision-record contract using
the existing Council/run recording facilities where suitable, prove records for
hold/reject/failure as well as success, and prove paper-only endpoint/credential
and cost guards before any connected trial. Resolve concrete persistence or
external-data decisions at their normal boundary. Do not add several broker
adapters merely because the research considers several brokers.
