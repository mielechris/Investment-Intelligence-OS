# Investment Intelligence OS
## Reasoning, Hypothesis, and Explainability Architecture — v0.1

---

## 1. Reasoning Doctrine

IIOS does not move directly from headline to trade.

The reasoning architecture separates:

```text
fact
→ inference
→ hypothesis
→ investment thesis
→ committee decision
→ risk decision
```

Each transition has requirements.

---

## 2. Claim Model

A claim includes:

- statement;
- classification: fact, inference, or hypothesis;
- subject and object entities;
- time scope;
- geography;
- supporting evidence;
- contradictory evidence;
- confidence;
- author or process;
- model and prompt version if AI-assisted;
- status;
- falsifiers.

Unsupported claims remain `PROPOSED` or are rejected.

---

## 3. Causal Chain

A causal chain is an ordered set of steps.

Example structure:

```text
formal policy action
→ implementation by agency
→ change in domestic capacity or trade cost
→ change in company revenue, cost, or capital spending
→ earnings or cash-flow revision
→ valuation and positioning interaction
→ instrument price effect
```

Each step records:

- cause;
- effect;
- mechanism;
- expected sign;
- expected lag;
- evidence;
- assumptions;
- confidence;
- alternative explanation;
- falsifier.

---

## 4. Counter-Chain

Every promoted thesis requires at least one credible counter-chain.

Examples:

- policy is delayed or challenged;
- benefit is already priced;
- input costs offset revenue benefit;
- competitors benefit more;
- interest rates dominate the sector;
- war de-escalates;
- weather impact is geographically limited;
- substitution prevents scarcity;
- public filing is too delayed to represent current exposure;
- market move was caused by another event.

---

## 5. Missing Information

The Reasoning Engine creates explicit missing-information requests.

A request includes:

- question;
- why it matters;
- evidence that could answer it;
- urgency;
- source domain;
- effect on confidence;
- owner or workflow;
- expiration.

The system may stop thesis promotion until critical information is resolved.

---

## 6. Hypothesis Registry

A hypothesis includes:

- falsifiable statement;
- predicted direction;
- affected assets;
- horizon;
- expected lag;
- conditions;
- causal chain;
- counter-chain;
- required data;
- success metric;
- failure metric;
- benchmark;
- status;
- review date.

Ideas do not become code before registration.

---

## 7. Investment Thesis

A thesis adds investability to a hypothesis.

Required fields:

- instrument expression;
- long, short, watch, avoid, or no-trade;
- entry conditions;
- horizon;
- catalysts;
- expected path;
- invalidation;
- exit conditions;
- liquidity considerations;
- risk factors;
- portfolio overlap;
- evidence confidence;
- timing confidence;
- implementation confidence;
- market-pricing assessment.

---

## 8. Thesis Scoring

Recommended dimensions:

- source quality;
- evidence directness;
- causal coherence;
- implementation probability;
- independent corroboration;
- counter-case strength;
- historical support;
- market confirmation;
- valuation or pricing;
- timing clarity;
- liquidity;
- crowding;
- portfolio fit;
- data freshness;
- model agreement;
- calibration history.

Scores remain decomposed.

A single composite score may rank candidates but must not hide weak dimensions.

---

## 9. Explainability Packet

Every committee candidate receives an explainability packet containing:

1. decision summary;
2. source cutoff;
3. key facts;
4. inferences;
5. hypothesis;
6. causal chain;
7. counter-chain;
8. supporting evidence;
9. contradictory evidence;
10. historical analogs;
11. missing information;
12. agent views;
13. dissent;
14. confidence dimensions;
15. risk considerations;
16. invalidation;
17. expected lag;
18. model, prompt, and code versions.

---

## 10. Historical Analog Use

Analog retrieval may inform:

- likely lag;
- distribution of outcomes;
- common failure modes;
- regime dependence;
- second-order effects.

It may not:

- replace a causal mechanism;
- imply the current event is identical;
- use future labels in historical retrieval;
- hide sample size.

---

## 11. Market Reaction Attribution

A market move around an event is analyzed against:

- broad benchmark;
- sector benchmark;
- related commodities or rates;
- pre-event trend;
- volatility;
- concurrent events;
- surprise relative to expectation;
- positioning;
- liquidity;
- persistence.

Post-event association is not automatically causal.

---

## 12. LLM Role

LLMs may:

- summarize evidence;
- extract candidate claims;
- generate causal alternatives;
- propose missing questions;
- compare analogs;
- draft structured agent views;
- challenge assumptions.

LLMs may not:

- create evidence that does not exist;
- decide source rights;
- bypass typed schemas;
- authorize risk;
- place orders;
- silently rewrite hypotheses.

---

## 13. Deterministic Validation

Before promotion, the system verifies:

- all evidence IDs exist;
- evidence is permitted;
- required timestamps exist;
- hypothesis is falsifiable;
- counter-chain exists;
- invalidation exists;
- instrument is valid;
- source cutoff is recorded;
- critical data is fresh;
- agent output follows schema.

---

## 14. Confidence Model

Confidence is multidimensional.

Store at least:

- evidence confidence;
- causal confidence;
- policy implementation confidence;
- timing confidence;
- market-pricing confidence;
- data-quality confidence;
- model confidence;
- overall committee confidence.

Calibration compares confidence buckets with later outcomes.

---

## 15. Reasoning Acceptance Tests

- unsupported fact claim is rejected;
- inference is not displayed as fact;
- high-confidence thesis without counter-chain is blocked;
- ambiguous policy stage lowers implementation confidence;
- missing invalidation blocks promotion;
- historical analog cannot use future data;
- evidence retraction triggers thesis review;
- model disagreement remains visible;
- explainability packet reconstructs the full decision.
