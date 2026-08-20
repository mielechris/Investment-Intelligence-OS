# Database Migration Runbook

## Before Migration

- backup;
- review migration;
- review lock impact;
- review data backfill;
- verify rollback/forward repair;
- test on nonproduction copy;
- activate maintenance if required.

## Migration

1. stop incompatible writers;
2. apply migration;
3. verify migration version;
4. run schema checks;
5. run data integrity checks;
6. restart application;
7. run smoke tests.

## Destructive Changes

Use staged migration:

1. add new structure;
2. dual-read/write if needed;
3. backfill;
4. migrate consumers;
5. validate;
6. remove old structure in later release.

## Failure

If migration fails:

- stop;
- preserve logs;
- decide rollback or forward repair;
- do not continue normal operation with unknown schema state.
