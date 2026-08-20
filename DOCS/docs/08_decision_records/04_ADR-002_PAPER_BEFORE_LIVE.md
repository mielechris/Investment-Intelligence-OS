# ADR-002 — Paper Before Live

**Status:** ACCEPTED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

Historical success is insufficient evidence for autonomous use of real capital.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. Build directly against live broker
2. Research only with no execution layer
3. Research plus paper execution with future live adapter boundary

## Decision

V1 supports research, backtesting, scenarios, and paper trading only.

## Rationale

Forward paper operation is required to evaluate execution, calibration, operations, and risk before considering live deployment.

## Positive Consequences

- Protects capital
- Exposes operational defects
- Creates realistic learning loop

## Negative Consequences / Trade-Offs

- Delays live deployment
- Paper execution may still differ from live

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

- Formal live-pilot evidence package exists
- Independent legal/risk/security review is complete

## Final Decision State

**ACCEPTED**
