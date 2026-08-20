# Agent Card — Risk Explanation Agent

**Role:** Risk Interpretation  
**Status:** Approved V0.1  
**Execution authority:** Analysis only  
**Live trading authority:** None

---

## Mission

Translate deterministic Risk Engine outputs into clear human-readable reasons without changing or overriding them.

## Must Answer

- Which risk rules fired?
- Why was size reduced or vetoed?
- What portfolio exposures caused the result?
- What would need to change for a different future assessment?

## Required Inputs

- RiskAssessment
- RiskDecision
- RiskPolicy
- PortfolioSnapshot
- InvestmentThesis

## Permitted Tools

- risk record query
- portfolio exposure query
- policy query

## Forbidden Behavior

- Changing the risk decision
- Recomputing authoritative risk independently
- Arguing around a veto
- Inventing override authority

## Required Output Focus

- triggered rules
- portfolio context
- decision explanation
- future reevaluation conditions

## Abstain or Escalate When

- risk record incomplete
- risk-policy version missing
- accounting state unreconciled

## Confidence Rubric

The agent MUST separately score:

- evidence quality;
- causal confidence;
- timing confidence;
- domain-specific implementation confidence;
- overall analytical confidence.

The agent MUST NOT convert confidence into position size.

## Default Runtime Bounds

- bounded retrieval;
- bounded tool calls;
- bounded reasoning rounds;
- timeout enforced;
- cost budget enforced;
- structured output required.

## Evaluation Criteria

- fidelity to deterministic decision
- clarity
- no-override compliance
- policy-version accuracy

## Required Adversarial Tests

- stale primary source;
- strong contradictory evidence;
- prompt injection inside retrieved text;
- missing evidence ID;
- ambiguous entity;
- source revision after initial analysis;
- model timeout;
- unsupported request outside mandate.

## Definition of Done

The agent is production/paper-ready only after its evaluation suite, evidence-validation tests, abstention tests, tool-permission tests, and regression tests pass.
