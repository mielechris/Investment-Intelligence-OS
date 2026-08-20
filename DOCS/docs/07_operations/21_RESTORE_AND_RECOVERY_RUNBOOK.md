# Restore and Recovery Runbook

## Restore Preconditions

- identify target restore point;
- identify release/schema version;
- activate maintenance or stand-down;
- preserve current broken state if forensic value exists.

## Restore Sequence

1. restore PostgreSQL;
2. restore object-store snapshot/version;
3. apply compatible application release;
4. validate schema;
5. validate raw object references;
6. verify audit sequence;
7. reconcile paper cash and positions;
8. verify job/outbox state;
9. verify environment;
10. verify risk policy;
11. run golden trace smoke test;
12. resume only after approval.

## Recovery Validation

Must prove:

- decision lineage intact;
- paper accounting reconciled;
- no duplicate jobs/fills;
- critical sources restart safely.
