# Investment Intelligence OS
## Decision Register — v0.1

**Purpose:** Preserve why material product, architecture, data, model, risk, and operating decisions were made.

A decision is material when reversing it would affect system behavior, data lineage, security, risk, scope, cost, schedule, or future scalability.

---

## Status Vocabulary

- **Proposed** — under review
- **Accepted** — approved and active
- **Superseded** — replaced by a newer decision
- **Deprecated** — still present but scheduled for removal
- **Rejected** — considered and not selected
- **Retired** — no longer applicable

---

## Initial Decisions

| ID | Date | Status | Decision | Direction | Rationale | Review Trigger |
|---|---|---|---|---|---|---|
| ADR-001 | 2026-08-20 | Accepted | Personal-first, institution-ready | Build for one operator now while preserving modular interfaces, provenance, security, and auditability | Maximizes speed without forcing a future rewrite | Multi-user or institutional pilot begins |
| ADR-002 | 2026-08-20 | Accepted | Paper before live | V1 supports research, backtesting, scenario analysis, and paper trading only | Historical performance alone is insufficient; risk and operations must be proven forward | Formal live-pilot evidence package exists |
| ADR-003 | 2026-08-20 | Accepted | Public or properly licensed information only | Exclude MNPI, hacked, leaked, confidential, stolen, and unlicensed data | Protects legal, ethical, provenance, and institutional-readiness boundaries | Legal or licensing requirements change |
| ADR-004 | 2026-08-20 | Accepted | Policy is a component, not an oracle | Presidential actions and behavior are high-value inputs but must be checked against Fed, Congress, courts, global events, weather, fundamentals, flows, valuation, and market behavior | Prevents political confirmation bias and single-narrative trading | Evidence shows domain weighting should change |
| ADR-005 | 2026-08-20 | Accepted | Separate evidence layers | Store fact, inference, hypothesis, thesis, and decision separately | Prevents models from presenting interpretation as fact and improves auditability | Canonical reasoning schema is redesigned |
| ADR-006 | 2026-08-20 | Accepted | Timestamp integrity | Preserve published, effective, observed, and market-available times where relevant | Prevents look-ahead leakage and false backtest performance | Data architecture changes |
| ADR-007 | 2026-08-20 | Accepted | Benchmark everything | Complex strategies must outperform, reduce risk, improve calibration, or diversify useful simple baselines after costs | Prevents unnecessary complexity and overfitting | Research promotion standard changes |
| ADR-008 | 2026-08-20 | Accepted | Risk veto | Risk may reduce or reject any committee candidate | Protects capital and separates idea quality from portfolio suitability | Risk governance is formally revised |
| ADR-009 | 2026-08-20 | Accepted | Preserve dissent | Agent disagreement and assumptions remain visible | Avoids false consensus and improves learning | Committee architecture changes |
| ADR-010 | 2026-08-20 | Accepted | Reasoning is auditable | Every decision preserves source, evidence, model, thesis, risk, execution, and outcome lineage | Enables reconstruction, testing, accountability, and institutional readiness | Audit model changes |

---

## New Decision Entry Template

### ADR-XXX — Decision Title

**Date:** YYYY-MM-DD  
**Status:** Proposed / Accepted / Superseded / Deprecated / Rejected / Retired  
**Owner:**  
**Related tickets:**  
**Related specifications:**  
**Supersedes:**  
**Superseded by:**  

#### Context

Describe the problem, constraint, opportunity, or disagreement that requires a decision.

#### Options Considered

1. Option A
2. Option B
3. Option C

#### Decision

State the selected direction clearly.

#### Why

Explain the evidence, trade-offs, and assumptions.

#### Positive Consequences

- Consequence

#### Negative Consequences and Risks

- Consequence

#### Required Controls

- Control

#### Implementation Impact

List affected:

- documents;
- schemas;
- services;
- agents;
- tests;
- data;
- security;
- operations;
- cost;
- schedule.

#### Validation

Explain how the decision will be tested.

#### Review Trigger

State the date or condition that requires reconsideration.

---

## Register Rules

1. Do not delete old decisions.
2. Supersede them.
3. Link code and tickets to the decision ID.
4. Record rejected options when the trade-off matters.
5. Update this register before merging a material architecture change.
6. Add a review trigger to any decision based on uncertain assumptions.
