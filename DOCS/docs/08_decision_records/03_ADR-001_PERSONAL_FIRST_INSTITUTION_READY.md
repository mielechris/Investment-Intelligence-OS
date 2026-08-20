# ADR-001 — Personal-First, Institution-Ready

**Status:** ACCEPTED  
**Decision owner:** Founder / Architecture  
**Initial decision date:** 2026-08-20  
**Applies to:** V0.1  
**Supersedes:** None  
**Superseded by:** None

---

## Context

V1 is designed for one owner/operator, but foundational contracts, audit, provenance, permissions, and modular boundaries must allow future institutional evolution.

## Decision Drivers

- correctness;
- auditability;
- risk control;
- implementation speed;
- future institutional readiness;
- reversibility;
- operational simplicity.

## Options Considered

1. Build purely as a personal script
2. Build full institutional SaaS immediately
3. Build personal-first with institution-ready boundaries

## Decision

Build personal-first with institution-ready boundaries.

## Rationale

Maximizes speed while preserving a credible future path. It avoids both a throwaway script and premature enterprise complexity.

## Positive Consequences

- Faster V1 development
- Simpler user model
- Clear migration path

## Negative Consequences / Trade-Offs

- Some future features remain deferred
- Requires discipline in interfaces even for one user

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

- Multi-user or institutional pilot begins
- Tenant isolation or formal approval workflows become necessary

## Final Decision State

**ACCEPTED**
