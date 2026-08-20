# Investment Intelligence OS
## V1 Scope and Success Gates — v0.1

**Document purpose:** Define exactly what Version 1 must build, what it must not build, and the evidence required to declare V1 successful.

---

## 1. V1 Definition

Version 1 is a personal investment-intelligence and paper-trading system for one owner/operator.

It must ingest lawful public information, create a structured world state, connect evidence to causal hypotheses, convene bounded AI analysts, preserve dissent, apply risk controls, simulate paper execution, and learn from outcomes.

V1 is not a production brokerage system and is not authorized to trade live capital autonomously.

---

## 2. V1 Primary User Journey

The owner opens the command center and can answer, in approximately ten minutes:

1. What changed in the world and markets?
2. Which events matter most?
3. What evidence supports that ranking?
4. Which sectors, companies, commodities, currencies, rates, or crypto assets may be affected?
5. What is the leading causal chain?
6. What is the strongest counter-chain?
7. What information is missing?
8. What do the specialist agents believe?
9. Where do they disagree?
10. What does the investment committee recommend?
11. What does risk allow?
12. What paper positions exist and why?
13. What has the system recently learned?
14. Are any data, model, or operational failures forcing a stand-down?

---

## 3. V1 Required Outputs

### Daily Briefing

The daily briefing must contain:

- generated time and data cutoff;
- source-health status;
- market and macro regime;
- policy and legislative state;
- geopolitical risk state;
- weather, agriculture, livestock, and commodity state;
- corporate and sector developments;
- public-flow context;
- market-structure confirmation or contradiction;
- ranked event radar;
- ranked opportunity board;
- committee candidates;
- no-trade decisions;
- risk-state summary;
- paper-portfolio summary;
- unresolved hypotheses;
- recent postmortems and belief updates.

### Thesis Record

Every thesis must include:

- unique thesis ID;
- instrument or asset expression;
- direction: long, short, watch, avoid, or no-trade;
- time horizon;
- event or condition that created the thesis;
- evidence IDs;
- causal chain;
- counter-chain;
- assumptions;
- catalysts;
- expected lag;
- invalidation conditions;
- missing information;
- evidence confidence;
- committee confidence;
- risk disposition;
- status;
- creation and review timestamps.

### Decision Record

Every decision must include:

- decision ID;
- linked thesis ID;
- agent views;
- dissent;
- committee rationale;
- risk rationale;
- approved action;
- paper order or no-order reason;
- model and prompt versions;
- source cutoff;
- subsequent outcome;
- postmortem.

---

## 4. V1 In-Scope Capabilities

### A. Data and Source Layer

- Official-source connectors
- Licensed market-data connector interface
- Immutable raw payload storage
- Canonical normalized event model
- Canonical market-data model
- Deduplication
- Revision handling
- Four-timestamp preservation
- Data freshness checks
- Source trust and data-quality scoring
- Quarantine for uncertain records

### B. World Model and Evidence Layer

- Entity registry
- Company, sector, country, agency, commodity, currency, instrument, and indicator entities
- Relationship mapping
- Current world-state snapshots
- Evidence graph
- Support and contradiction links
- Historical analog retrieval
- Policy-lifecycle state
- Regime state

### C. Reasoning Layer

- Causal-chain construction
- Counter-chain construction
- Expected lag
- Assumption tracking
- Falsifier tracking
- Missing-information detection
- Alternative explanation generation
- Thesis scoring

### D. Agent Layer

At minimum:

- Policy Analyst
- Macro and Rates Analyst
- Skeptic / Red Team

Expanded V1:

- Geopolitical Analyst
- Commodity and Weather Analyst
- Corporate and Sector Analyst
- Market Structure Analyst
- Strategy Research Agent
- Risk Manager
- Investment Committee

### E. Research Layer

- Hypothesis registry
- Point-in-time research datasets
- Event-study framework
- Baseline strategies
- Strategy reverse-engineering research
- Train, validation, and holdout separation
- Walk-forward testing
- Regime analysis
- Cost, spread, slippage, and turnover assumptions
- Robustness checks
- Research result registry

### F. Portfolio and Paper Layer

- Paper account
- Orders
- Simulated fills
- Positions
- Cash
- Realized and unrealized P&L
- Gross and net exposure
- Theme and causal-cluster exposure
- Correlation checks
- Position limits
- Drawdown monitoring
- Kill-switch and stand-down states
- Thesis-to-position linkage

### G. Learning and Audit Layer

- Decision journal
- Postmortems
- Outcome attribution
- Agent calibration
- Strategy calibration
- Belief promotion, revision, and retirement
- Model registry
- Prompt registry
- Full source-to-outcome lineage
- Engineering log
- Decision register

### H. User Experience

- One-screen command center
- Searchable decision journal
- Source and data-health warnings
- Committee and dissent view
- Risk dashboard
- Paper portfolio
- Learning panel
- Clear no-trade and stand-down state

---

## 5. Required Initial Data Domains

The first working loop must include three different types of source:

1. **Presidency or federal policy**
   - Presidential actions, executive orders, memoranda, proclamations, or official remarks.

2. **Federal Reserve or macro**
   - FOMC actions, minutes, speeches, testimony, inflation, labor, growth, rates, liquidity, or yield-curve data.

3. **At least one non-policy domain**
   - SEC;
   - NOAA;
   - USDA;
   - EIA;
   - CFTC;
   - Treasury / OFAC;
   - USTR;
   - Commerce;
   - Federal Register;
   - another approved primary source.

This prevents the first model from becoming a single-narrative political system.

---

## 6. V1 Out of Scope

- Autonomous live trading
- Brokerage custody
- Customer funds
- Public users
- Subscription billing
- High-frequency execution
- Market making
- Co-location
- Unbounded agents
- Self-modifying production prompts
- Hidden use of unapproved data
- Material nonpublic information
- Exact replication claims for undisclosed trading bots
- Guaranteed returns
- Tax optimization
- Personalized legal conclusions
- Full institutional compliance certification
- Full multi-broker production routing
- Unlimited asset-class coverage on Day 1

---

## 7. Initial Paper-Risk Defaults

These are starting configuration values for testing, not permanent investment advice.

| Control | Initial Default |
|---|---:|
| Maximum single position | 2% of paper net asset value |
| Maximum theme or causal cluster | 10% of paper net asset value |
| Maximum gross exposure | 100% until leverage is separately researched and approved |
| Minimum thesis confidence for risk review | 0.60 |
| Daily stand-down trigger | 2% paper NAV drawdown |
| Portfolio kill-switch trigger | 8% paper NAV drawdown |
| New risk during stale or failed critical feeds | Disabled |
| Trade with unexplained decision lineage | Rejected |
| High-correlation or duplicate-theme exposure | Reduce or reject |
| Autonomous live execution | Disabled |

Confidence may inform review priority, but it may not translate directly into leverage.

---

## 8. Success Gates

### Gate 1 — Timestamp Integrity

**Required behavior**

- The system knows when information was published, effective, observed, and market-available.
- Historical tests use only what could have been known at the time.
- Revised data is versioned.
- Automated leakage tests exist.

**Failure condition**

A future or revised value influences an earlier decision without explicit simulation labeling.

---

### Gate 2 — Evidence Provenance

**Required behavior**

- Every material recommendation is traceable to an immutable source record.
- Source retrieval and parsing are logged.
- Unsupported claims are rejected or labeled.
- Contradictory evidence can be attached.

**Failure condition**

A recommendation contains a material claim that cannot be traced to evidence.

---

### Gate 3 — Reasoning Discipline

**Required behavior**

- Facts, inferences, hypotheses, theses, and decisions are stored separately.
- Every promoted thesis has a causal chain, counter-chain, assumptions, lag, and falsifiers.
- Missing information is visible.
- The system can abstain.

**Failure condition**

A narrative moves directly from headline to trade.

---

### Gate 4 — Risk Discipline

**Required behavior**

- Risk can veto any candidate.
- Limits are enforced in deterministic tests.
- Concentration and correlation are evaluated.
- Stale critical data disables new risk.
- No-trade and stand-down are operational states.

**Failure condition**

An order bypasses risk or violates an active limit.

---

### Gate 5 — Research Validity

**Required behavior**

- Strategies are compared with simple benchmarks.
- Tests include realistic costs and slippage.
- Out-of-sample or walk-forward evaluation is used.
- Regime and parameter sensitivity are reported.
- Sample size and drawdown are visible.
- Leakage and overfitting tests exist.

**Failure condition**

A strategy is promoted from an in-sample performance chart alone.

---

### Gate 6 — Forward Validity

**Required behavior**

- The system generates real-time paper decisions outside the development sample.
- Calibration, drawdown, operational behavior, and decision quality are reviewed.
- Performance is evaluated by strategy, regime, asset class, horizon, and confidence bucket.

**Failure condition**

Historical performance is treated as sufficient proof.

---

### Gate 7 — Operational Reliability

**Required behavior**

- Feed failures are detected.
- Stale data is flagged.
- Jobs retry safely.
- Failed jobs do not create partial hidden state.
- Secrets are protected.
- Logs, backups, and recovery procedures exist.
- Abnormal model or portfolio behavior triggers stand-down.

**Failure condition**

The system continues taking new risk while critical state is unreliable.

---

## 9. Seven-Day Vertical-Slice Acceptance Test

The vertical slice is complete only when one real public event can be traced through all stages:

1. source retrieved;
2. raw payload preserved;
3. canonical event created;
4. entities resolved;
5. source quality scored;
6. claim generated;
7. causal chain generated;
8. counter-chain generated;
9. missing information listed;
10. policy view produced;
11. macro view produced;
12. skeptic view produced;
13. committee candidate or no-trade produced;
14. risk decision produced;
15. paper order simulated or explicitly rejected;
16. portfolio state updated;
17. command center displays the state;
18. journal reconstructs the entire chain;
19. tests verify the happy path;
20. tests verify at least one failure path.

---

## 10. V1 Completion Criteria

V1 may be declared complete when:

- the daily process runs repeatedly without manual repair;
- multiple domains are ingested;
- source and model failures are visible;
- decisions are evidence-linked;
- the system regularly produces no-trade when appropriate;
- paper accounting reconciles;
- risk limits are enforced;
- baseline and candidate strategies are compared;
- forward paper results exist;
- postmortems alter future confidence;
- backup and restore have been tested;
- the founder can reconstruct any material decision;
- all critical P0 issues are closed;
- the Constitution and project charter remain satisfied.

---

## 11. Promotion Beyond V1

V1 completion does not automatically authorize live capital.

A future limited live pilot requires a separate decision and evidence package covering:

- stable critical-source operation;
- reliable point-in-time datasets;
- adequate forward paper sample;
- realistic execution;
- acceptable drawdown;
- risk-control testing;
- security review;
- operational recovery;
- legal and compliance review where appropriate;
- deliberate human approval;
- materially smaller risk than the paper environment.

---

## 12. Scope-Change Rule

A proposed V1 feature must answer:

1. Does it improve the source-to-decision-to-learning loop?
2. Is it required to satisfy a success gate?
3. Does it reduce a principal risk?
4. Does it block the vertical slice?
5. Can it be deferred without causing a rewrite?

Features that do not satisfy one of the first four questions should normally move to the backlog rather than interrupt V1.
