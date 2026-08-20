# ADR-013 — PostgreSQL as Transactional System of Record

**Status:** ACCEPTED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

IIOS requires transactions, referential integrity, point-in-time metadata, auditability, portfolio accounting, and flexible queries.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. Multiple specialized databases from Day 1
2. Document database
3. PostgreSQL as governed transactional core

## Decision

Use PostgreSQL as the authoritative transactional system of record.

## Rationale

Strong integrity plus broad query capabilities reduce operational complexity.

## Positive Consequences

- Transactions
- Constraints
- Flexible indexing
- Strong tooling

## Negative Consequences / Trade-Offs

- High-volume specialized workloads may eventually move elsewhere

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

- Measured workload exceeds PostgreSQL design or institutional isolation requires split

## Final Decision State

**ACCEPTED**
