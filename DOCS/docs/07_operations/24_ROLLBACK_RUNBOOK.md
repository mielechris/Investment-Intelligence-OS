# Rollback Runbook

## Trigger

Rollback when a release causes:

- critical errors;
- data corruption risk;
- agent regression;
- risk-control failure;
- accounting mismatch;
- source-processing failure;
- security issue.

## Procedure

1. activate stand-down;
2. identify last known-good release;
3. preserve incident evidence;
4. revert application images/code;
5. reverse migration only if safe, otherwise forward-repair;
6. restore configuration;
7. verify model/prompt versions;
8. verify database integrity;
9. run golden trace;
10. reconcile paper state;
11. explicitly resume.

## Rule

Rollback must not erase:

- audit history;
- paper trades;
- decisions;
- incidents;
- prior research.
