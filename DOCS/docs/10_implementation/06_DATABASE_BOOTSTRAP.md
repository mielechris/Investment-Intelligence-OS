# Database Bootstrap

## PostgreSQL Is Authoritative

All durable operational state belongs in PostgreSQL or references immutable object storage.

## Logical Schemas

Create migrations for:

```sql
CREATE SCHEMA platform;
CREATE SCHEMA source;
CREATE SCHEMA ingest;
CREATE SCHEMA market;
CREATE SCHEMA knowledge;
CREATE SCHEMA evidence;
CREATE SCHEMA reasoning;
CREATE SCHEMA agents;
CREATE SCHEMA decision;
CREATE SCHEMA portfolio;
CREATE SCHEMA risk;
CREATE SCHEMA execution;
CREATE SCHEMA research;
CREATE SCHEMA learning;
CREATE SCHEMA workflow;
CREATE SCHEMA audit;
```

## Extensions

Enable approved extensions required for:

- UUID support if needed;
- text search;
- pgvector.

## SQLAlchemy Base

Create a shared metadata registry without allowing cross-module write ownership.

Recommended common fields:

```python
id
schema_version
created_at
updated_at
environment
correlation_id
```

## Time

Use timezone-aware database timestamps.

## Transactions

Create an application transaction boundary / unit of work.

Avoid global implicit sessions.

## Test Database

Integration tests must use PostgreSQL behavior.

Do not rely on SQLite as the only database test target.

## Smoke Test

Create migration, insert one Source, retrieve it, roll back test data.
