# Investment Intelligence OS
## Risk Register — v0.1

**Purpose:** Track the conditions most likely to create false confidence, financial harm, invalid research, legal or data problems, and operational failure.

---

## 1. Rating Scale

### Likelihood

- **1 — Rare**
- **2 — Unlikely**
- **3 — Possible**
- **4 — Likely**
- **5 — Almost certain**

### Impact

- **1 — Minor**
- **2 — Moderate**
- **3 — Serious**
- **4 — Major**
- **5 — Critical**

### Score

`Risk Score = Likelihood × Impact`

- **1–4:** Low
- **5–9:** Moderate
- **10–15:** High
- **16–25:** Critical

---

## 2. Initial Risk Register

| ID | Risk | Likelihood | Impact | Score | Primary Controls | Trigger / Indicator | Owner | Status |
|---|---|---:|---:|---:|---|---|---|---|
| R-001 | False causality | 4 | 5 | 20 | Counter-chains, event studies, benchmarks, skeptic agent, no-trade | Strong narrative with weak controlled evidence | Reasoning Lead / Skeptic | Open |
| R-002 | Look-ahead leakage | 4 | 5 | 20 | Four timestamps, point-in-time datasets, leakage tests, immutable raw records | Backtest performance collapses after timestamp correction | Data / Research | Open |
| R-003 | Overfitting and data mining | 4 | 5 | 20 | Holdout, walk-forward, baselines, parameter sensitivity, complexity discipline | Many variants tested but only best result shown | Research | Open |
| R-004 | Stale, missing, or bad feeds | 4 | 4 | 16 | Source health, freshness checks, quarantine, redundancy, stand-down | Critical source exceeds freshness threshold | Data / Operations | Open |
| R-005 | Political confirmation bias | 4 | 5 | 20 | Multi-domain contradiction, skeptic review, policy-lifecycle classification, no source oracle | System repeatedly confirms one preferred political narrative | Committee / Skeptic | Open |
| R-006 | Disclosure-lag misuse | 3 | 4 | 12 | Explicit filing/report lag, market-available timestamp, UI warnings | 13F, COT, or insider record treated as real-time position | Data / Research | Open |
| R-007 | Unrealistic execution | 4 | 4 | 16 | Spread, slippage, fees, liquidity, turnover, fill model | Paper results materially exceed realistic executable results | Execution / Research | Open |
| R-008 | Hidden concentration | 4 | 5 | 20 | Theme clusters, factor exposure, correlation, position caps | Multiple positions depend on one macro or policy event | Risk | Open |
| R-009 | AI hallucination or unsupported claim | 4 | 5 | 20 | Structured retrieval, evidence IDs, source verification, abstention | Claim has no valid evidence link | AI Governance | Open |
| R-010 | Model or prompt drift | 3 | 4 | 12 | Model registry, prompt versions, evaluation suite, release gates | Behavior changes after provider or prompt update | AI Governance | Open |
| R-011 | Security or credential failure | 3 | 5 | 15 | Secret manager, least privilege, rotation, audit, safe failure | Secret appears in logs or repository | Security / Operations | Open |
| R-012 | Improper or unlicensed information | 2 | 5 | 10 | Public/MNPI boundary, provenance, rights metadata, quarantine | Source rights or origin cannot be verified | Founder / Future Legal | Open |
| R-013 | Scope explosion | 5 | 4 | 20 | Vertical-slice rule, V1 scope gate, backlog, change control | New domains delay end-to-end proof | Founder / Product | Open |
| R-014 | Cost sprawl | 4 | 3 | 12 | Usage budgets, caching, model routing, cost metrics, batch processing | Model or data spend exceeds budget without measured value | Founder / AI Architect | Open |
| R-015 | Operational complexity | 4 | 4 | 16 | Modular monolith first, service boundaries, observability, simple baselines | Too many services or agents fail independently | Architecture / Operations | Open |
| R-016 | Paper-to-live performance gap | 4 | 5 | 20 | Conservative fills, capacity model, forward paper period, limited live gate | Live-like simulation underperforms paper assumptions | Risk / Execution | Open |
| R-017 | Confidence miscalibration | 4 | 4 | 16 | Calibration curves, confidence buckets, Brier/log scoring where applicable | High-confidence theses fail at similar rate as low confidence | Learning / AI Governance | Open |
| R-018 | Regime dependence | 4 | 4 | 16 | Regime engine, segmented tests, transition monitoring | Strategy works only in one historical environment | Research / Portfolio | Open |
| R-019 | Data revision confusion | 3 | 4 | 12 | Vintage data, revision metadata, raw versions | Revised macro value appears in original decision context | Data | Open |
| R-020 | Human override without audit | 3 | 5 | 15 | Override record, mandatory rationale, approval, immutable log | Manual change appears without linked decision | Founder / Operations | Open |
| R-021 | Tax, legal, or compliance assumptions | 2 | 5 | 10 | Explicit out-of-scope boundary, professional review before live/institutional use | System presents unreviewed legal conclusion as authoritative | Founder / Future Counsel | Open |
| R-022 | Catastrophic portfolio event | 2 | 5 | 10 | Position caps, theme caps, drawdown controls, kill switch, scenario tests | Gap move, correlation spike, liquidity collapse | Risk | Open |
| R-023 | Incorrect entity resolution | 3 | 4 | 12 | Stable IDs, aliases, confidence, manual review, conflict handling | Evidence attaches to wrong company, person, or instrument | Data / Knowledge | Open |
| R-024 | News duplication and narrative amplification | 4 | 3 | 12 | Source clustering, primary-source preference, duplicate detection | Many articles create false impression of independent confirmation | Data / Evidence | Open |
| R-025 | Strategy copying without understanding | 3 | 4 | 12 | Reverse-engineering as hypothesis, competing models, validation | Public trade is copied despite unknown sizing, hedge, or delay | Strategy Research | Open |

---

## 3. Mandatory Stand-Down Conditions

New paper risk must be disabled when:

- critical source health is failed or stale;
- canonical-event generation is corrupted;
- decision lineage is incomplete;
- risk service is unavailable;
- paper accounting does not reconcile;
- model outputs cannot be tied to registered versions;
- unauthorized data enters the system;
- a kill-switch threshold is reached;
- timestamps are unreliable;
- a critical security incident is unresolved.

---

## 4. Risk Review Cadence

### Daily

- critical feed health;
- current drawdown;
- limit breaches;
- abnormal model behavior;
- unexplained lineage;
- concentration and theme overlap.

### Weekly

- new risks;
- failed hypotheses;
- agent calibration;
- source reliability;
- costs;
- false positives;
- missed opportunities;
- operational incidents.

### Monthly

- drawdown and recovery;
- regime performance;
- risk-adjusted results;
- strategy retirement;
- model drift;
- vendor risk;
- security posture;
- whether system complexity adds value.

---

## 5. Risk Entry Template

### R-XXX — Risk Title

**Description:**  
**Cause:**  
**Potential consequence:**  
**Likelihood:**  
**Impact:**  
**Score:**  
**Owner:**  
**Current controls:**  
**Control gaps:**  
**Leading indicators:**  
**Stand-down trigger:**  
**Response plan:**  
**Residual risk:**  
**Status:**  
**Review date:**  
**Related decisions, tickets, and specifications:**  

---

## 6. Risk Acceptance Rule

A high or critical residual risk may not be quietly accepted through implementation.

It requires:

- explicit owner;
- documented rationale;
- compensating controls;
- review date;
- founder approval;
- Decision Register entry.
