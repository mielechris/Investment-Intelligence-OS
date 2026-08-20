# ADR-025 — Opaque Canonical IDs and External Identity Mappings

**Status:** ACCEPTED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

Tickers, names, provider IDs, and contracts change over time.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. Use ticker as primary key
2. Use provider ID as canonical key
3. Use opaque canonical IDs with time-aware external mappings

## Decision

Every canonical entity/instrument gets stable internal identity; provider identifiers are mappings.

## Rationale

Prevents symbol reuse, provider lock-in, and historical identity corruption.

## Positive Consequences

- Stable history
- Vendor neutrality
- Correct point-in-time mapping

## Negative Consequences / Trade-Offs

- More mapping tables and entity-resolution logic

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

- Identity architecture is replaced with equivalent or stronger guarantees

## Final Decision State

**ACCEPTED**
