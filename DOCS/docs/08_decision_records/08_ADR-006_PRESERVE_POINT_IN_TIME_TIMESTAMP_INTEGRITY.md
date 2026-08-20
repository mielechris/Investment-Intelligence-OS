# ADR-006 — Preserve Point-in-Time Timestamp Integrity

**Status:** ACCEPTED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

Financial research is invalid when future or revised information leaks into historical decisions.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. Use source date only
2. Use retrieval date only
3. Preserve occurrence, publication, effective, observed, and market-available time as needed

## Decision

Treat time semantics as first-class data and use market availability for historical eligibility.

## Rationale

Prevents look-ahead bias and separates policy effectiveness from market knowledge.

## Positive Consequences

- Valid backtests
- Accurate event studies
- Reconstructable decisions

## Negative Consequences / Trade-Offs

- More complex ingestion
- Some timestamps remain uncertain

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

- A source cannot support required time semantics
- Data architecture is materially redesigned

## Final Decision State

**ACCEPTED**
