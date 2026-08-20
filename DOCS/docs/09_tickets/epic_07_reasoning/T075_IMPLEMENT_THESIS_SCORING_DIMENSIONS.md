# T075 — Implement thesis scoring dimensions

**Epic:** E07 — Reasoning and Hypothesis  
**Priority:** P0/P1  
**Status:** BACKLOG  
**Estimate:** 2-6h  
**Specifications:** SPEC-029  
**Dependencies:** T072,T050,T062  
**Risk references:** See Package 01 Risk Register as applicable

---

## Objective

Compute decomposed thesis-quality dimensions without using a composite to bypass hard gates.

## Why This Matters

Prevents headline-to-trade behavior by requiring falsifiable mechanisms, counter-cases, and invalidation.

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

- [ ] All configured dimensions visible
- [ ] Missing data explicit
- [ ] Composite optional/decomposable
- [ ] No position sizing here

## Required Tests

- Strong score
- Missing dimension
- Hard gate dominates

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
- [ ] Commit references `T075`.

## Suggested Commit

`feat(reasoning): implement thesis scoring dimensions [T075]`
