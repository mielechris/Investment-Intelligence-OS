# Build Board

Use:

```text
BACKLOG
READY
IN_PROGRESS
BLOCKED
IN_REVIEW
TESTING
DONE
```

## BACKLOG → READY

Requires dependencies, specification, acceptance criteria, and no unresolved architectural blocker.

## READY → IN_PROGRESS

Assign owner and implementation context.

## IN_PROGRESS → IN_REVIEW

Implementation complete, local tests pass, docs updated.

## IN_REVIEW → TESTING

Review findings resolved.

## TESTING → DONE

All acceptance criteria, required tests, and Definition of Done pass.

## BLOCKED

Record blocker, owner, next action, and unblock condition.
