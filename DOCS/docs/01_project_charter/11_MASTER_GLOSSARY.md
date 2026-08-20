# Investment Intelligence OS
## Master Glossary — v0.1

**Purpose:** Establish one shared language for product, data, research, AI, risk, execution, and governance.

---

## Core System Terms

**IIOS**  
Investment Intelligence OS.

**Personal-first, institution-ready**  
Designed for one owner in V1 while preserving interfaces, provenance, security, and governance that support future institutional scale.

**World model**  
A structured representation of the current economic, political, corporate, commodity, geopolitical, weather, and market state.

**Evidence graph**  
A network linking sources, events, entities, claims, support, contradiction, assets, theses, decisions, and outcomes.

**Decision journal**  
The durable record of what IIOS believed, why, what action it took or rejected, what happened, and what it learned.

**Command center**  
The owner-facing interface that presents world state, events, opportunities, committee views, risk, paper portfolio, learning, and data health.

---

## Data and Evidence Terms

**Source**  
The publisher, provider, document, feed, API, filing, or dataset from which information originates.

**Raw record**  
The immutable original response or document captured by IIOS before normalization.

**Canonical event**  
A vendor-neutral structured representation of an observed event.

**Entity**  
A uniquely identified company, person, country, agency, sector, commodity, currency, instrument, indicator, or other relevant object.

**Provenance**  
The documented origin, ownership, rights, retrieval path, and transformation history of information.

**Trust score**  
A structured assessment of source reliability, directness, consistency, and provenance.

**Data-quality score**  
A structured assessment of freshness, completeness, validity, consistency, and revision risk.

**Deduplication**  
Identifying multiple records that refer to the same underlying event or document.

**Revision**  
A later correction, restatement, or update to previously released information.

**Quarantine**  
A state in which data is retained only for review and excluded from reasoning, testing, and decisions.

---

## Timestamp Terms

**`published_at`**  
When the source published the information.

**`effective_at`**  
When the underlying policy, rule, transaction, or condition becomes effective.

**`observed_at`**  
When IIOS retrieved or observed the information.

**`market_available_at`**  
When the information could reasonably have been available to market participants.

**Point-in-time data**  
Data represented exactly as it was available at a historical decision time.

**Look-ahead leakage**  
Use of future, revised, or unavailable information in an earlier historical test.

---

## Reasoning Terms

**Fact**  
A statement directly supported by evidence.

**Inference**  
A reasoned interpretation derived from facts.

**Hypothesis**  
A falsifiable proposition that may be tested.

**Investment thesis**  
A hypothesis expressed as an instrument, direction, horizon, mechanism, catalysts, assumptions, and invalidation conditions.

**Claim**  
A stored statement classified as fact, inference, or hypothesis and linked to evidence.

**Causal chain**  
A proposed sequence from cause through mechanism and intermediate effects to expected asset impact.

**Counter-chain**  
A credible alternative mechanism or explanation that contradicts or weakens the leading causal chain.

**Assumption**  
A condition treated as true for the purpose of a hypothesis but not fully established.

**Falsifier**  
Evidence or an outcome that would weaken or reject a hypothesis.

**Catalyst**  
An event or condition expected to move the thesis toward realization.

**Invalidation condition**  
A predefined condition that makes the thesis no longer valid.

**Expected lag**  
The estimated time between cause and observable market effect.

**Historical analog**  
A prior event or regime with relevant similarities and documented differences.

**No-trade**  
An explicit decision that evidence, timing, edge, or risk does not justify a position.

**Abstention**  
An agent or system response indicating that it cannot responsibly reach a conclusion.

---

## Agent and Governance Terms

**Specialist agent**  
A bounded AI analyst assigned to a defined domain, evidence standard, tool set, and output schema.

**Investment Committee**  
The aggregation and debate layer that preserves dissent and issues candidate or no-trade decisions.

**Skeptic / Red Team**  
The function that actively attacks causality, assumptions, crowding, leakage, confirmation bias, and missing evidence.

**Risk veto**  
The authority to reject or reduce a candidate regardless of committee enthusiasm.

**Model registry**  
The record of models, versions, configurations, evaluations, costs, authority, and deployment status.

**Prompt registry**  
The versioned record of prompts and structured instructions used by AI components.

**ADR**  
Architecture Decision Record.

**Decision Register**  
The index of material decisions, rationale, consequences, status, and review triggers.

**Engineering Log**  
The chronological record of work completed, tests, defects, assumptions, blockers, and next actions.

**Definition of Done**  
The evidence required before an item can be called complete.

---

## Research Terms

**Backtest**  
A historical simulation of a strategy using defined data and execution assumptions.

**Event study**  
An analysis of asset behavior around a class of events relative to a benchmark and context.

**Benchmark**  
A simple or market-standard comparison used to judge whether complexity adds value.

**Train set**  
Data used to fit or develop a model or strategy.

**Validation set**  
Data used to select among candidate models or parameters.

**Holdout set**  
Data reserved for final evaluation and not repeatedly used for tuning.

**Walk-forward test**  
A sequence of historical train-and-test windows that approximates repeated real-time deployment.

**Overfitting**  
Learning noise or quirks of the development sample that do not generalize.

**Data mining**  
Searching many hypotheses or configurations until one appears successful by chance.

**Parameter sensitivity**  
The degree to which results change when settings change slightly.

**Regime**  
A probabilistic market or macro environment such as inflationary growth, disinflation, recession, high volatility, or liquidity expansion.

**Calibration**  
The match between stated probability or confidence and actual outcomes.

**Promotion**  
Moving a hypothesis or strategy to a higher trust or deployment state after satisfying gates.

**Retirement**  
Removing a hypothesis, model, or strategy from active use because evidence no longer supports it.

---

## Portfolio and Execution Terms

**Paper trade**  
A simulated trade using realistic order, fill, fee, spread, and portfolio assumptions without live capital.

**Net asset value (NAV)**  
The current value of the paper or live portfolio after liabilities.

**Gross exposure**  
The sum of absolute long and short exposures.

**Net exposure**  
Long exposure minus short exposure.

**Theme exposure**  
Combined exposure to positions driven by the same economic, policy, sector, commodity, or causal thesis.

**Concentration**  
Excessive dependence on one instrument, sector, factor, theme, or event.

**Correlation**  
The degree to which positions move together.

**Liquidity**  
The ability to trade an instrument without unacceptable price impact or delay.

**Spread**  
The difference between bid and ask prices.

**Slippage**  
The difference between expected execution price and simulated or actual execution price.

**Turnover**  
The amount of portfolio trading over a period.

**Capacity**  
The amount of capital a strategy can deploy before costs and market impact degrade the edge.

**Drawdown**  
The decline from a prior portfolio peak.

**Kill switch**  
A control that stops new activity or closes/reduces exposure under defined critical conditions.

**Stand-down**  
A safe operating state in which new risk is disabled because data, model, risk, security, or operational conditions are unreliable.

---

## Information-Boundary Terms

**Public information**  
Information lawfully available to the public.

**Properly licensed information**  
Information used under a valid agreement or right that permits the intended use.

**MNPI**  
Material nonpublic information.

**Disclosure lag**  
The delay between the underlying event or position and public reporting.

**13F**  
A delayed public holdings disclosure filed by certain institutional investment managers.

**COT**  
Commitments of Traders, a public futures-positioning report with defined measurement and publication timing.

---

## Decision Classifications

**Long**  
A thesis that benefits from an increase in the value of the chosen instrument or exposure.

**Short**  
A thesis that benefits from a decrease in the value of the chosen instrument or exposure.

**Watch**  
Evidence is potentially meaningful, but timing, confirmation, or risk is insufficient.

**Avoid**  
The system identifies unfavorable asymmetry, unreliable conditions, or unacceptable risk.

**No-trade**  
The correct current action is to take no position.

**Enter**  
Open a paper or approved position.

**Reduce**  
Decrease exposure.

**Exit**  
Close exposure.

**Stand down**  
Disable new risk due to system or market conditions.
