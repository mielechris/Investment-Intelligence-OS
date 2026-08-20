# Backup Runbook

## Backup Scope

Include:

- PostgreSQL;
- object storage;
- configuration versions;
- source registry;
- model/prompt registry;
- migrations;
- release manifest.

## Backup Frequency

At minimum for personal paper production:

- daily database backup;
- daily object-store snapshot/version verification;
- pre-release backup;
- pre-migration backup.

## Backup Verification

A successful backup means more than file creation.

Verify:

- readable;
- complete;
- encrypted where required;
- timestamped;
- associated with release/schema version.

## Retention

Maintain multiple restore points.

Exact retention is configured by policy.

## Backup Failure

Repeated backup failure becomes operationally critical.
