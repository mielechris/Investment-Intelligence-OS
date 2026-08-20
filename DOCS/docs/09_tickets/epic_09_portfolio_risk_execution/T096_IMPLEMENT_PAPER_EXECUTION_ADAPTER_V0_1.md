# T096 — Implement paper execution adapter V0.1

**Epic:** E09 — Portfolio Risk and Paper Execution  
**Priority:** P0  
**Status:** BACKLOG  
**Estimate:** 2-6h  
**Specifications:** SPEC-009  
**Dependencies:** T095,T055  
**Risk references:** See Package 01 Risk Register as applicable

---

## Objective

Simulate submit/cancel/query/fill operations behind the future broker interface.

## Why This Matters

Separates idea quality from portfolio suitability and proves safe paper execution/accounting.

## Scope

### In Scope

- Implement this ticket's objective.
- Follow the referenced specification(s) and Package 02 architecture.
- Use canonical objects from Package 04.
- Preserve point-in-time, provenance, security, audit, and paper-only boundaries.
- Add required tests and operational telemetry.

### Out of Scope

- Unrelated feature expansion.
- Live-money execution.
- Undocumented architecture changes.
- Provider lock-in outside approved adapters.
- Weakening constitutional or risk controls.

## Implementation Guidance

1. Read the referenced specification(s).
2. Read the owning architecture module.
3. Confirm dependencies are complete.
4. Implement through the owning module/application interface.
5. Preserve typed/versioned contracts.
6. Make retriable work idempotent.
7. Add structured logs/correlation IDs where operational.
8. Update documentation if behavior changes.
9. Run the required tests.
10. Use an ADR for material architecture changes.

## Acceptance Criteria

- [ ] No live route
- [ ] Order states validated
- [ ] Market calendar respected where applicable
- [ ] Provider-neutral interface

## Required Tests

- Submit
- Cancel
- Invalid state

## Observability / Audit

- Material state changes are traceable.
- Operational workflows carry correlation IDs.
- Errors use the normalized error taxonomy.
- Model/provider versions are recorded where applicable.
- Privileged or safety-critical actions produce audit evidence.

## Security / Data Boundary

- Public or properly licensed information only.
- Quarantined/prohibited information is excluded.
- No secrets in source control or logs.
- PAPER mode remains enforced.
- Agents and frontend code cannot bypass deterministic risk.

## Definition of Done

- [ ] All acceptance criteria pass.
- [ ] Required tests pass.
- [ ] Relevant failure paths are verified.
- [ ] Documentation is updated.
- [ ] No unresolved critical defect remains.
- [ ] Relevant versions are recorded.
- [ ] Engineering Log updated if material.
- [ ] Commit references `T096`.

## Suggested Commit

`feat(portfolio_risk_execution): implement paper execution adapter v0.1 [T096]`
