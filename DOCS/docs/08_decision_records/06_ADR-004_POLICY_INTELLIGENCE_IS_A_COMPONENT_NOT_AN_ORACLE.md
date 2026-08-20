# ADR-004 — Policy Intelligence Is a Component, Not an Oracle

**Status:** ACCEPTED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

Presidential behavior, policy announcements, executive actions, and government meetings can matter, but can also be delayed, reversed, constrained, or already priced.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. Build a presidency-following trading bot
2. Exclude political information
3. Treat policy as one high-value domain inside a multi-domain system

## Decision

Policy intelligence is a core component, but no political actor or source receives automatic predictive authority.

## Rationale

Prevents confirmation bias while preserving the original policy-intelligence thesis.

## Positive Consequences

- Uses valuable public policy signals
- Reduces partisan/narrative bias
- Forces cross-domain confirmation

## Negative Consequences / Trade-Offs

- More complex than single-signal bot
- May produce more no-trade outcomes

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

- Validated research shows domain weighting should materially change

## Final Decision State

**ACCEPTED**
