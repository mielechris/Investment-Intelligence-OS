# ADR-003 — Public or Properly Licensed Information Only

**Status:** ACCEPTED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

The platform needs strong information provenance and a clean institutional-readiness boundary.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. Use any information found online
2. Use only official government data
3. Use lawful public or properly licensed information with quarantine

## Decision

Use lawful public or properly licensed information only; quarantine uncertain provenance and prohibit MNPI, hacked, stolen, confidential, or unlicensed information.

## Rationale

This maximizes legality, auditability, reproducibility, and future institutional defensibility.

## Positive Consequences

- Clean provenance
- Lower legal/data risk
- Auditable research

## Negative Consequences / Trade-Offs

- May exclude attractive but uncertain data
- Requires source-rights metadata

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

- A new data class or license is proposed
- Future counsel requires stricter policy

## Final Decision State

**ACCEPTED**
