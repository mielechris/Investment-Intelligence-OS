# ADR-027 — Require Golden End-to-End Trace in Release Testing

**Status:** ACCEPTED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

Individual passing tests do not prove the system works as a complete decision loop.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. Unit/integration tests only
2. Manual demonstration
3. Maintain deterministic golden source-to-postmortem trace

## Decision

Every release must execute a golden end-to-end reference scenario.

## Rationale

Protects cross-module contracts and proves lineage, risk, execution, and recovery together.

## Positive Consequences

- System-level confidence
- Regression detection
- Release discipline

## Negative Consequences / Trade-Offs

- Golden fixture requires maintenance

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

- Release architecture changes to an equivalent system-level verification method

## Final Decision State

**ACCEPTED**
