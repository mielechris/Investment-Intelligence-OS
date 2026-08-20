# ADR-020 — Separate Retrieval, Parsing, Normalization, and Interpretation

**Status:** ACCEPTED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

Combining source retrieval and market interpretation makes replay and debugging unreliable.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. One connector produces investment signals
2. Parse and normalize together
3. Use separate retrieval, parse, normalize, interpretation stages

## Decision

Keep acquisition, parsing, normalization, and interpretation separate.

## Rationale

Allows raw replay, parser upgrades, canonical contracts, and independent reasoning changes.

## Positive Consequences

- Replayability
- Cleaner testing
- Provider neutrality

## Negative Consequences / Trade-Offs

- More pipeline stages

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

- A specific data class proves a simpler path without harming auditability

## Final Decision State

**ACCEPTED**
