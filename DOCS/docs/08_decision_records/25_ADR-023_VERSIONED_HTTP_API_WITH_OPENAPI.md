# ADR-023 — Versioned HTTP API with OpenAPI

**Status:** ACCEPTED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

The frontend and future clients need a stable governed transport boundary.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. Direct database UI
2. GraphQL immediately
3. Versioned REST-style HTTP JSON API with generated OpenAPI contract

## Decision

Expose `/api/v1/` typed APIs and asynchronous job IDs for long-running work.

## Rationale

Provides simple contracts, generated documentation, and provider/client decoupling.

## Positive Consequences

- Clear contracts
- Typed frontend integration
- Easy testing

## Negative Consequences / Trade-Offs

- May need additional API styles later

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

- Client patterns or institutional integrations require another transport

## Final Decision State

**ACCEPTED**
