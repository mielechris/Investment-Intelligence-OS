# CI and Release Implementation

## CI Stages

Recommended:

```text
format
lint
typecheck
unit
integration
security
migration
architecture
constitutional
golden-trace
frontend-build
```

## Merge Gate

Do not merge if:

- tests fail;
- migration fails;
- secret scan fails;
- architecture boundary fails;
- constitutional invariant fails.

## Release Manifest

Generate:

```json
{
  "release": "0.1.0",
  "commit": "...",
  "migration": "...",
  "dependency_lock_hash": "...",
  "models": [],
  "prompts": [],
  "environment": "PAPER",
  "known_limitations": []
}
```

## Release Procedure

1. clean Git;
2. run CI locally or remotely;
3. backup;
4. tag release;
5. migrate;
6. deploy;
7. health check;
8. golden smoke;
9. confirm PAPER;
10. record release.

## Rollback

Rollback must preserve audit and paper history.
