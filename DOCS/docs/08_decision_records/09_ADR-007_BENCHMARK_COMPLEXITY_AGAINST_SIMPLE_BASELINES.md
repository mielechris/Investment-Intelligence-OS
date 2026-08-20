# ADR-007 — Benchmark Complexity Against Simple Baselines

**Status:** ACCEPTED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

Complex AI or quantitative systems can appear impressive while adding no real edge.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. Trust complex model if profitable
2. Require only benchmark-relative return
3. Require every complex component to beat or improve on simple relevant baselines

## Decision

Complexity must improve correctness, calibration, risk, reliability, cost, or performance relative to simpler baselines.

## Rationale

Prevents unnecessary technical and statistical overfitting.

## Positive Consequences

- Simpler systems win when sufficient
- Clear evidence of incremental value

## Negative Consequences / Trade-Offs

- Some ambitious ideas will be rejected
- Requires baseline engineering

## Risks and Controls

| Risk | Control |
|---|---|
| Decision becomes stale | Review trigger and superseding ADR |
| Implementation drifts from decision | Ticket/spec traceability and architecture tests |
| Hidden exception weakens control | Audit exception and explicit approval |
| Operational shortcut bypasses intent | Definition of Done and release review |

## Implementation Impact

This decision must be reflected in the relevant:

- charter/governance documents;
- architecture;
- specifications;
- data catalog;
- agent/tool permissions where relevant;
- operations/runbooks;
- tests;
- implementation tickets.

## Validation

Validation requires automated or review evidence demonstrating that implementation behavior matches this decision.

Where the decision is architectural, at least one negative test SHOULD prove that the prohibited alternative path is blocked.

## Reversal / Migration

If this decision changes:

1. create a new ADR;
2. mark this record superseded;
3. define migration;
4. update affected packages;
5. update tests;
6. preserve historical decisions made under this ADR.

## Review Triggers

- A domain has no meaningful simple baseline and an alternative evaluation is approved

## Final Decision State

**ACCEPTED**
