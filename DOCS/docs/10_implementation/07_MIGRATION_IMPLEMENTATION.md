# Migration Implementation

## Tool

Use the approved migration framework from Package 02.

## Migration Rules

Every schema change gets a migration.

Never manually alter the database and leave migration history behind.

## First Migration Sequence

1. create logical schemas;
2. extensions;
3. common platform tables;
4. source/ingestion;
5. market;
6. knowledge/evidence/reasoning;
7. agents/decision;
8. portfolio/risk/execution;
9. research/learning;
10. workflow/audit.

## Development Workflow

```bash
alembic revision --autogenerate -m "create source registry"
alembic upgrade head
```

Review generated migrations manually.

## Destructive Migration

Use staged migration:

```text
add new column/table
→ backfill
→ move readers/writers
→ verify
→ remove old field in later release
```

## Migration Tests

For every release:

- empty DB → head;
- prior release → head;
- application starts;
- constraints work;
- golden trace survives migration where relevant.
