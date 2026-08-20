# ADR-005 — Separate Reasoning Layers

**Status:** ACCEPTED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

AI systems can blur fact, inference, hypothesis, and recommendation unless objects are explicitly separated.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. Store one narrative recommendation
2. Store facts and trades only
3. Persist fact, inference, hypothesis, thesis, and decision separately

## Decision

Persist fact, inference, hypothesis, thesis, and decision as separate governed layers.

## Rationale

Improves auditability, falsifiability, explainability, and model discipline.

## Positive Consequences

- Clear lineage
- Better postmortems
- Less hallucinated certainty

## Negative Consequences / Trade-Offs

- More schema complexity
- More workflow stages

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

- Canonical reasoning model is redesigned

## Final Decision State

**ACCEPTED**
