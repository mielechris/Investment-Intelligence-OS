# ADR-019 — Assume At-Least-Once Delivery and Enforce Idempotent Effects

**Status:** ACCEPTED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

Retries and crashes can redeliver events and jobs.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. Assume exactly-once delivery
2. Avoid retries
3. Accept at-least-once and make handlers idempotent

## Decision

Design all retriable workflows for at-least-once delivery with exactly-once durable effects.

## Rationale

This is an honest reliability model and prevents duplicate decisions, orders, and fills.

## Positive Consequences

- Crash tolerance
- Safe retries
- Clear invariants

## Negative Consequences / Trade-Offs

- Requires idempotency keys and uniqueness constraints

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

- A future platform provides stronger delivery semantics and migration proves equivalence

## Final Decision State

**ACCEPTED**
