# ADR-024 — Typed React Command Center; Backend Remains Authoritative

**Status:** ACCEPTED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

The user needs a responsive personal command center, but browser state must not own portfolio or risk calculations.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. Server-rendered static dashboard only
2. Frontend performs portfolio logic
3. Typed React UI backed by authoritative API

## Decision

Use a typed React command center and keep financial/risk authority on the backend.

## Rationale

Supports rich interaction without compromising system integrity.

## Positive Consequences

- Strong UX
- Typed contracts
- Safe authority boundary

## Negative Consequences / Trade-Offs

- Two-language stack
- Frontend build/dependency management

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

- Frontend technology no longer meets needs or a platform migration is approved

## Final Decision State

**ACCEPTED**
