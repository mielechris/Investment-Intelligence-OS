# ADR-012 — Separate API, Worker, Scheduler, and Frontend Processes

**Status:** ACCEPTED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

One codebase can still benefit from separating runtime workloads.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. One process for everything
2. Full microservices
3. Same backend package with separate API, worker, scheduler, plus separate frontend

## Decision

Run distinct API, worker, scheduler, and frontend processes.

## Rationale

Separates long-running workloads and scheduling from request handling while preserving simple deployment.

## Positive Consequences

- Better reliability
- Independent scaling
- Clear runtime responsibilities

## Negative Consequences / Trade-Offs

- More local processes
- Requires process health checks

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

- Runtime topology no longer meets measured workload

## Final Decision State

**ACCEPTED**
