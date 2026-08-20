# Investment Intelligence OS
## Package 05 — Agent Cards — v0.1

**Destination:** `docs/05_agent_cards/`  
**Governing packages:** 01 Project Charter, 02 Architecture, 03 Specifications, 04 Data Catalog  
**Operating mode:** Research, backtesting, scenario analysis, and paper trading only

---

## Purpose

This package defines the specialist AI team inside IIOS.

Each Agent Card establishes:

- mission;
- domain boundary;
- allowed inputs;
- required evidence;
- permitted tools;
- forbidden behavior;
- structured output;
- confidence rubric;
- abstention rules;
- escalation rules;
- model policy;
- cost and time limits;
- evaluation criteria;
- failure tests.

Agents are analysts, not autonomous traders.

No agent may:

- place an order;
- change risk limits;
- change source permissions;
- change the Constitution;
- access arbitrary secrets;
- use unapproved network or shell tools;
- treat model confidence as position size;
- bypass the Investment Committee or deterministic Risk Engine.

---

## Agent Roster

| File | Agent / Control |
|---|---|
| `01_AGENT_RUNTIME_CONTRACT.md` | Shared runtime rules |
| `02_SHARED_AGENT_OUTPUT_SCHEMA.md` | Common structured output |
| `03_RETRIEVAL_AND_TOOL_POLICY.md` | Retrieval and tool permissions |
| `04_ABSTENTION_ESCALATION_AND_FAILURE_POLICY.md` | Fail-safe behavior |
| `05_EVENT_TRIAGE_AGENT.md` | Event classification and materiality |
| `06_POLICY_ANALYST.md` | Presidency, Congress, agencies, courts, trade |
| `07_MACRO_AND_RATES_ANALYST.md` | Fed, rates, inflation, labor, growth, liquidity |
| `08_GEOPOLITICAL_ANALYST.md` | War, sanctions, diplomacy, trade routes |
| `09_COMMODITY_WEATHER_AGRICULTURE_ANALYST.md` | Commodities, weather, crops, livestock |
| `10_CORPORATE_AND_SECTOR_ANALYST.md` | Companies, filings, capex, sectors |
| `11_MARKET_STRUCTURE_ANALYST.md` | Trend, breadth, volatility, options, liquidity |
| `12_STRATEGY_RESEARCH_ANALYST.md` | Public strategies, disclosed trades, bot behavior |
| `13_SUPPLY_CHAIN_ANALYST.md` | Suppliers, facilities, logistics, dependencies |
| `14_INSTITUTIONAL_FLOW_ANALYST.md` | Public holdings, insider filings, positioning |
| `15_HISTORICAL_ANALOG_ANALYST.md` | Comparable historical regimes/events |
| `16_CAUSAL_CHAIN_ANALYST.md` | Economic transmission mechanisms |
| `17_EVIDENCE_AUDITOR.md` | Evidence integrity and claim support |
| `18_DATA_QUALITY_ANALYST.md` | Freshness, provenance, revisions, trust |
| `19_SKEPTIC_RED_TEAM.md` | Attack causality, bias, crowding, leakage |
| `20_THESIS_SCORING_AGENT.md` | Standardized thesis score dimensions |
| `21_PORTFOLIO_CONTEXT_ANALYST.md` | Portfolio overlap and causal-cluster context |
| `22_RISK_EXPLANATION_AGENT.md` | Explain deterministic risk outputs |
| `23_COMMITTEE_CHAIR_AGENT.md` | Run bounded investment committee process |
| `24_POSTMORTEM_ANALYST.md` | Process-vs-outcome review |
| `25_KNOWLEDGE_EVOLUTION_ANALYST.md` | Propose belief/strategy updates |
| `26_AGENT_EVALUATION_MATRIX.md` | Evaluation and calibration framework |
| `27_AGENT_TEST_SCENARIOS.md` | Standard adversarial tests |
| `28_AGENT_CARD_TEMPLATE.md` | Reusable card template |

---

## Mandatory Runtime Rule

Every agent run MUST be linked to:

```text
agent definition/version
+ model/version
+ prompt/version
+ source cutoff
+ retrieval context
+ tool policy
+ evidence IDs
+ structured output
+ cost
+ latency
+ correlation ID
```

Completed outputs are immutable. Corrections require a new run.
