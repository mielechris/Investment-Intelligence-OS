# ADR-028 — Defer Vendor-Specific Market Data, Broker, and Cloud Decisions

**Status:** DEFERRED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

Provider selection depends on asset coverage, licensing, cost, reliability, latency, and future live requirements that are not yet fully known.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. Select vendors immediately
2. Avoid provider planning
3. Define internal adapters now and defer vendor lock-in

## Decision

Keep provider interfaces stable and delay vendor-specific commitments until requirements are testable.

## Rationale

Reduces premature lock-in and preserves negotiating/technical flexibility.

## Positive Consequences

- Portability
- Lower early cost
- Better evidence-based selection

## Negative Consequences / Trade-Offs

- Some implementation choices remain open
- Initial fixtures/adapters may need temporary providers

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

- A vertical-slice requirement cannot proceed without selecting a provider
- Always-on deployment becomes necessary

## Final Decision State

**DEFERRED**
