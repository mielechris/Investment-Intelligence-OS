# Decision Lifecycle and Supersession

## Lifecycle

```text
PROPOSED
→ ACCEPTED
→ SUPERSEDED / DEPRECATED / RETIRED
```

Alternative:

```text
PROPOSED → REJECTED
```

Deferred direction:

```text
PROPOSED → DEFERRED → ACCEPTED / REJECTED
```

## Supersession Rule

A new ADR that changes an accepted direction MUST include:

- `Supersedes: ADR-XXX`
- reason;
- migration;
- risks;
- rollback;
- affected packages;
- updated tests.

The old record becomes `SUPERSEDED`.

## Deprecation

Use `DEPRECATED` when:

- direction remains temporarily supported;
- replacement exists;
- removal is scheduled.

## Retirement

Use `RETIRED` when a decision is no longer relevant because the capability itself is removed.

## Deferred

Use `DEFERRED` when the team deliberately refuses to decide before evidence exists.

Deferral is not indecision when the cost of early lock-in exceeds the value of choosing immediately.
