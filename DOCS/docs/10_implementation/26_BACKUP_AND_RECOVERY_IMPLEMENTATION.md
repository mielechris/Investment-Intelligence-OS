# Backup and Recovery Implementation

## Backup Command

Create a script/command that:

1. records release version;
2. records migration version;
3. exports PostgreSQL backup;
4. snapshots or exports object storage;
5. writes manifest;
6. hashes artifacts;
7. records backup audit.

## Suggested Layout

```text
backups/
└── YYYY-MM-DD_HHMM/
    ├── database.dump
    ├── object_manifest.json
    ├── release_manifest.json
    └── backup_manifest.json
```

Do not commit backup contents to Git.

## Restore Command

Restore into TEST by default.

Procedure:

1. restore DB;
2. restore object data;
3. verify migration version;
4. verify object links;
5. verify audit;
6. verify portfolio accounting;
7. run golden trace.

## Production/Paper Recovery

Never resume new paper risk until:

- reconciliation passes;
- risk healthy;
- source health known;
- environment confirmed;
- operator resumes.
