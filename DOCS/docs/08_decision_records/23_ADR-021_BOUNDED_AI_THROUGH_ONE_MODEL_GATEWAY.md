# ADR-021 — Bounded AI Through One Model Gateway

**Status:** ACCEPTED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

Scattered provider calls make permissions, versioning, cost, and safety difficult to govern.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. Agents call provider SDK directly
2. One fixed model everywhere
3. All model calls pass through governed Model Gateway

## Decision

Use a single Model Gateway abstraction with approved models, prompts, tools, budgets, and logging.

## Rationale

Centralizes model authority and enables provider portability.

## Positive Consequences

- Governance
- Cost control
- Reproducibility
- Fallback management

## Negative Consequences / Trade-Offs

- Gateway becomes critical dependency

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

- Model architecture changes to fully local or another governed abstraction

## Final Decision State

**ACCEPTED**
