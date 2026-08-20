# Investment Intelligence OS
## Architecture Decision Index — v0.1

**Purpose:** Record the initial technical direction. Full decision records belong in Package 08 — Decision Records.

---

## Status Vocabulary

- Accepted
- Proposed
- Superseded
- Rejected
- Deferred

---

## Initial Architecture Decisions

| ID | Status | Decision | Reason |
|---|---|---|---|
| ADR-ARCH-001 | Accepted | Use a modular monolith for V1 | Fast implementation, strong transactions, low operational burden, clean future extraction |
| ADR-ARCH-002 | Accepted | Run API, worker, scheduler, and frontend as separate processes | Isolates workloads without premature service decomposition |
| ADR-ARCH-003 | Accepted | Use PostgreSQL as the transactional system of record | Integrity, transactions, flexible metadata, text search, audit, and broad tooling |
| ADR-ARCH-004 | Accepted | Use immutable object storage for raw and large artifacts | Reprocessing, provenance, retention, and scalable file storage |
| ADR-ARCH-005 | Accepted | Use pgvector inside PostgreSQL initially | Colocates semantic search with permissions, time filters, and provenance |
| ADR-ARCH-006 | Accepted | Do not use a dedicated graph database in V1 | PostgreSQL can support initial evidence-graph queries with lower complexity |
| ADR-ARCH-007 | Accepted | Use a database-backed job ledger | Durable work without operating a distributed workflow platform immediately |
| ADR-ARCH-008 | Accepted | Use a transactional outbox and consumer inbox | Reliable state-to-event propagation and idempotent effects |
| ADR-ARCH-009 | Accepted | Assume at-least-once delivery and enforce idempotency | Honest reliability model that tolerates retries and crashes |
| ADR-ARCH-010 | Accepted | Preserve four primary time semantics | Point-in-time correctness and policy/market timing |
| ADR-ARCH-011 | Accepted | Separate raw retrieval, parsing, normalization, and interpretation | Replayability, versioning, and reduced hidden coupling |
| ADR-ARCH-012 | Accepted | Use bounded AI agents through a model gateway | Permission, cost, audit, structured output, and provider portability |
| ADR-ARCH-013 | Accepted | Keep risk deterministic and independent | AI may explain, but risk enforcement must be tested and authoritative |
| ADR-ARCH-014 | Accepted | Use a paper-broker adapter matching the future broker interface | Test execution architecture without live capital |
| ADR-ARCH-015 | Accepted | Enforce paper/live separation in backend configuration and credentials | Prevent accidental live authority |
| ADR-ARCH-016 | Accepted | Use versioned REST/JSON APIs with OpenAPI | Typed frontend contract and future client support |
| ADR-ARCH-017 | Accepted | Use a typed React command center | Clear component model and API separation |
| ADR-ARCH-018 | Accepted | Keep authoritative calculations out of the browser | Protect portfolio and risk integrity |
| ADR-ARCH-019 | Accepted | Use vendor-neutral instrumentation | Preserve observability portability |
| ADR-ARCH-020 | Accepted | Lock dependencies and isolate provider SDKs in adapters | Reproducibility, security, and vendor replacement |
| ADR-ARCH-021 | Accepted | Model entities with opaque canonical IDs and external mappings | Avoid ticker, name, and provider identity errors |
| ADR-ARCH-022 | Accepted | Preserve dissent rather than average agent outputs | Avoid false consensus and improve learning |
| ADR-ARCH-023 | Accepted | Require explainability packets for candidate decisions | Complete evidence and assumption lineage |
| ADR-ARCH-024 | Accepted | Treat public strategy reverse engineering as hypothesis testing | Avoid false claims of exact replication |
| ADR-ARCH-025 | Accepted | Use point-in-time dataset manifests for research | Prevent leakage and enable reproduction |
| ADR-ARCH-026 | Accepted | Require a golden end-to-end trace in release tests | Verify the architecture as a system |
| ADR-ARCH-027 | Deferred | Select specific market-data vendor | Depends on asset coverage, rights, cost, and latency |
| ADR-ARCH-028 | Deferred | Select future live broker | Live mode is out of V1 scope |
| ADR-ARCH-029 | Deferred | Select cloud host | Local and portable container design comes first |
| ADR-ARCH-030 | Deferred | Adopt external event broker | Requires measured volume or service extraction |
| ADR-ARCH-031 | Deferred | Adopt dedicated vector or graph database | Requires measured query or scale need |
| ADR-ARCH-032 | Deferred | Select final production authentication provider | V1 has one owner; future roles remain designed |

---

## Decision Promotion Rule

A deferred decision becomes accepted only after:

- requirements are documented;
- alternatives are compared;
- cost and risk are assessed;
- migration impact is understood;
- acceptance tests are defined;
- a full ADR is approved.

---

## Decision Change Rule

Do not edit an accepted row to hide a changed direction.

Create a new ADR and mark the old one superseded.
