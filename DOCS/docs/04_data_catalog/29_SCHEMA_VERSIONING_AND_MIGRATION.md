# Schema Versioning and Migration

## Canonical Versions

Examples:

```text
canonical_event.v1
evidence.v1
investment_thesis.v1
agent_output.v1
risk_decision.v1
```

## Compatible Changes

Examples:

- optional field added;
- safe enum value added;
- new metadata field;
- new relationship predicate.

Compatible changes still require tests and release notes.

## Breaking Changes

Examples:

- field semantics changed;
- required field removed;
- identifier meaning changed;
- timestamp meaning changed;
- money/unit representation changed.

Breaking changes require:

- ADR when material;
- migration;
- compatibility plan;
- replay plan;
- updated fixtures;
- updated tests;
- release note.

## Database Migration Record

Must capture:

- migration ID;
- created time;
- schema changes;
- backfill requirements;
- expected lock/impact;
- rollback or forward repair;
- tested versions.

## Replay

Schema/parser changes MAY replay derived artifacts.

Operational orders and fills MUST NOT be recreated by generic replay.
