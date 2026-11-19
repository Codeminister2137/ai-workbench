# Investor coverage, comparable projects and geopolitical events

Checked 2026-11-19. Research for owner answer B, inbox
`2592e3e4e34d4a7db970482ef7f9f48d`; policy in
[ADR-093](../decisions/ADR-093-investor-coverage-and-paper-autonomy.md).
Public documentation research only; no broker account or entitlement was tested.

## Coverage findings

| Asset scope | Candidate and evidence | Constraints / disposition |
| --- | --- | --- |
| US stocks and ETFs | Alpaca selected first; [official tutorial](https://alpaca.markets/learn/start-paper-trading) describes stock/ETF paper support | [Paper docs](https://docs.alpaca.markets/us/docs/paper-trading): global email-only paper signup, free simulation, paper-only equity feed restricted to IEX. Does not reproduce latency slippage, queue priority, market impact, fees or dividends. |
| Crypto and US options | Same tutorial includes both; [options docs](https://docs.alpaca.markets/us/docs/options-trading) say paper capability is enabled by default | Broadens research without necessarily adding a broker. Contract availability and data entitlements need checking per experiment. Options require expiry/multiplier/assignment modeling; crypto needs continuous-market conventions. Neither is an owner-approved first universe yet. |
| International securities, FX, futures and bonds | [IBKR product directory](https://www.interactivebrokers.com/en/trading/products-exchanges.php) is the broader candidate to investigate instrument by instrument | [FAQ](https://www.interactivebrokers.com/support/faq/content/paper-account-60341604) says paper access requires funded live access; [data rules](https://www.interactivebrokers.com/en/trading/papertrader-delayed-data.php) distinguish delayed quotes and paid subscriptions. Funding is outside current authority. A [Campus lesson](https://www.interactivebrokers.com/campus/trading-lessons/how-to-open-an-ibkr-paper-trading-account/) has inconsistent approved-versus-funded wording: do not assume a free unfunded API path. |
| FX / CFDs | OANDA offers a demo and v20 API, but [official introduction](https://developer.oanda.com/rest-live-v20/introduction/) excludes OANDA TMS BROKERS S.A. and Global Markets | Local entity/account eligibility must be established. This is more precise than the older blanket claim that all EU API access was dropped. No eligible Polish route verified. |
| FX / CFDs via XTB | [Official help](https://www.xtb.com/en/help-center/our-platforms/does-xtb-offer-investment-automation-tools) says API access ended 2025-03-14 | Remove XTB xAPI from viable integration recommendations. Old SDK/community examples do not establish service availability. |

Engineering recommendation after this broader comparison: first prove the workflow
with Alpaca stocks/ETFs, then separate crypto/options experiments when required
modeling and free-data access are verified. This reduces initial simulation
complexity but narrows direct international/FX/futures coverage. IBKR would broaden
that coverage at a funding, data and operational cost; it is not selected here.
ETF exposure to bonds, commodities or foreign markets is a proxy, not equivalent
to directly trading those instruments. Multiple brokers are feasible later;
keep separate cash ledgers, instrument identities, currencies and fill assumptions
so overlapping positions and buying power are not double-counted.

## Comparable research

- [TradingAgents project and paper](https://tradingagents-ai.github.io/) separate
  fundamental, technical, sentiment and news analysis, debate and risk roles.
  Useful pattern: preserve opposing evidence and risk evaluation alongside a
  verdict. It is a research reference, not a dependency recommendation or proof
  of profitable autonomous trading in this repository.
- [FinMem paper](https://arxiv.org/abs/2311.13743) studies profile, layered memory
  and decision modules. Useful pattern: connect prior observations and outcomes
  to later decisions. Its reported stock experiments do not establish transfer
  to other assets or this system. Begin with inspectable records and replay;
  a vector database or training pipeline is not required for this closeout.

These references support experiments with memory and deliberation; they do not
establish that logging alone changes model weights or improves performance.

## Political and geopolitical event handling

[Caldara and Iacoviello's GPR research/data](https://www.matteoiacoviello.com/gpr.htm)
distinguish geopolitical threats from realized acts. Their
[paper](https://pubs.aeaweb.org/doi/10.1257/aer.20191823) studies adverse economic
effects; an aggregate association is not a direction or timing rule for one asset.
The following is a proposed evaluation design, not an implemented news signal:

1. Record publication, first-observed and event times separately, with timezone,
   URL, publisher, quoted claim, revisions and independent corroboration. An
   official speech verifies what was said, not that the threatened act occurred.
   Treat an example of a leader announcing war as hypothetical unless verified.
2. Classify threat, confirmed action, escalation, reversal, tariff/sanction or
   policy change. Separate facts from the profile's hypotheses and confidence.
   Consider energy supply, shipping, FX, rates, regional exposure and sectors;
   do not map every alarming headline to a universal sell instruction.
3. Model alternative outcomes: escalation, de-escalation, already-priced news,
   market closure/gaps and contradictory reports. Record why the profile acts,
   reduces exposure or holds. News content is evidence, never tool instructions.
4. Replay only information available by decision time. Prevent later revisions,
   future prices and outcome-derived memories leaking into earlier decisions.
   Include delayed/stale news, duplicate rumors, corrections and no-news controls.
5. Compare identical profiles with and without event context and with/without
   retrieved lessons over chronologically held-out episodes. Use identical price
   data, capital and cost assumptions; include cash/passive baselines. Report
   return, drawdown, turnover, uncertainty, latency and operational cost alongside
   failed/abstained decisions. Stratify by event and regime; do not tune and score
   on the same crises or infer quality from one favorable run.

No news-feed vendor, subscription, credential or automated ingestion is selected.
Public web research here is distinct from future transmission of private records
to inference providers. Before runtime integration, verify source licenses,
historical availability, latency and entity-specific free access. Preserve the
normal privacy and paid-inference boundaries.
