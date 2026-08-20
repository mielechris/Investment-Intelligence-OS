# ADR-018 — Use Transactional Outbox and Consumer Inbox

**Status:** ACCEPTED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

State changes and downstream events must not diverge during crashes.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. Publish events directly after commit
2. Distributed transaction
3. Transactional outbox plus idempotent consumer inbox

## Decision

Commit domain state and outbox event atomically; consumers record inbox receipts.

## Rationale

Prevents lost events and duplicate effects without pretending to have network-level exactly-once delivery.

## Positive Consequences

- Reliable event propagation
- Replayable
- Idempotent

## Negative Consequences / Trade-Offs

- Additional tables and dispatcher logic

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

- External event infrastructure replaces internal dispatch while preserving envelope semantics

## Final Decision State

**ACCEPTED**
