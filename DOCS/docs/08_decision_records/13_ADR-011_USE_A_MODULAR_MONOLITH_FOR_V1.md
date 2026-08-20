# ADR-011 — Use a Modular Monolith for V1

**Status:** ACCEPTED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

V1 has one operator, evolving domain contracts, and a rapid vertical-slice target.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. Microservices
2. Single unstructured application
3. Modular monolith with strict internal module boundaries

## Decision

Use a modular monolith for backend V1.

## Rationale

Provides strong transactions, simpler local operation, easier debugging, and future extraction boundaries without distributed-systems overhead.

## Positive Consequences

- Fast development
- Low operational burden
- Strong consistency

## Negative Consequences / Trade-Offs

- Requires discipline to avoid internal coupling
- Some modules may later require extraction

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

- Independent scaling/security/deployment need is measured

## Final Decision State

**ACCEPTED**
