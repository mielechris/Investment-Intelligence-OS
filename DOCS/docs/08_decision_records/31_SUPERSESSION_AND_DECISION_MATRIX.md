# Supersession and Decision Matrix

## Current Accepted / Deferred Baseline

| ADR | Status | Core Direction |
|---|---|---|
| ADR-001 | ACCEPTED | Personal-first, institution-ready |
| ADR-002 | ACCEPTED | Paper before live |
| ADR-003 | ACCEPTED | Public/licensed information only |
| ADR-004 | ACCEPTED | Policy is a component, not oracle |
| ADR-005 | ACCEPTED | Separate reasoning layers |
| ADR-006 | ACCEPTED | Point-in-time timestamp integrity |
| ADR-007 | ACCEPTED | Benchmark complexity |
| ADR-008 | ACCEPTED | Deterministic risk veto |
| ADR-009 | ACCEPTED | Preserve dissent |
| ADR-010 | ACCEPTED | Complete decision lineage |
| ADR-011 | ACCEPTED | Modular monolith |
| ADR-012 | ACCEPTED | Separate runtime processes |
| ADR-013 | ACCEPTED | PostgreSQL system of record |
| ADR-014 | ACCEPTED | Immutable object storage |
| ADR-015 | ACCEPTED | pgvector initially |
| ADR-016 | ACCEPTED | No dedicated graph DB in V1 |
| ADR-017 | ACCEPTED | Durable PostgreSQL jobs |
| ADR-018 | ACCEPTED | Transactional outbox/inbox |
| ADR-019 | ACCEPTED | At-least-once with idempotent effects |
| ADR-020 | ACCEPTED | Separate acquisition/transformation/interpretation |
| ADR-021 | ACCEPTED | Model Gateway |
| ADR-022 | ACCEPTED | Paper broker adapter |
| ADR-023 | ACCEPTED | Versioned HTTP/OpenAPI |
| ADR-024 | ACCEPTED | Typed React, backend authority |
| ADR-025 | ACCEPTED | Opaque canonical IDs |
| ADR-026 | ACCEPTED | Explainability packets |
| ADR-027 | ACCEPTED | Golden trace |
| ADR-028 | DEFERRED | Vendor selections deferred |

## Supersession Procedure

When a new ADR supersedes one above:

1. update old ADR `Superseded by`;
2. update this matrix;
3. update Project Decision Register;
4. update Architecture Decision Index;
5. update affected specifications;
6. update tests;
7. update release notes.

## No Silent Exceptions

If implementation temporarily violates an ADR:

- create an exception record;
- identify duration;
- identify risk;
- identify compensating control;
- identify owner;
- define removal date.
