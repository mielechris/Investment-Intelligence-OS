# ADR-015 — Use pgvector Initially

**Status:** ACCEPTED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

Semantic retrieval is useful, but a separate vector platform would add complexity.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. Dedicated vector database
2. No vector retrieval
3. pgvector inside PostgreSQL

## Decision

Use pgvector initially for governed semantic retrieval.

## Rationale

Colocates embeddings with source permissions, time filters, provenance, and transactional metadata.

## Positive Consequences

- Lower complexity
- Permission-aware filtering
- Easy joins

## Negative Consequences / Trade-Offs

- May not scale to extreme corpus/query volume

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

- Measured semantic-retrieval workload exceeds PostgreSQL capacity

## Final Decision State

**ACCEPTED**
