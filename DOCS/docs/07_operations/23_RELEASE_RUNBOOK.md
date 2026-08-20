# Release Runbook

## Release Preconditions

- included tickets complete;
- tests pass;
- golden trace passes;
- migration reviewed;
- secret scan passes;
- paper-mode assertion passes;
- known limitations documented;
- backup current;
- rollback prepared.

## Release Sequence

1. assign version;
2. freeze release commit;
3. build immutable artifacts;
4. apply migrations;
5. deploy backend processes;
6. deploy frontend;
7. verify environment;
8. verify health;
9. run smoke tests;
10. run risk/paper assertions;
11. record release audit.

## Release Notes

Include:

- added;
- changed;
- fixed;
- schema changes;
- model/prompt changes;
- risk changes;
- known issues;
- rollback instructions.

## Release Failure

If a critical check fails, stop and roll back.
