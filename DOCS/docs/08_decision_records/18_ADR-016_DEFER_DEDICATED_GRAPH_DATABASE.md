# ADR-016 — Defer Dedicated Graph Database

**Status:** ACCEPTED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

Evidence and relationship graphs are important, but V1 graph volume is modest.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. Dedicated graph database immediately
2. No graph model
3. Relational graph model in PostgreSQL and defer specialized graph store

## Decision

Implement evidence and relationship graph structures in PostgreSQL first.

## Rationale

Maintains strong transactions and lower operational burden while graph requirements are still evolving.

## Positive Consequences

- Simpler V1
- Consistent lineage
- Fewer data stores

## Negative Consequences / Trade-Offs

- Some graph traversals may be less elegant

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

- Graph algorithms/query latency become a measured bottleneck

## Final Decision State

**ACCEPTED**
