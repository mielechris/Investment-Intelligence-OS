# Investment Intelligence OS
## Technology Stack and Dependency Policy — v0.1

---

## 1. Stack Decision

The initial stack favors Python, PostgreSQL, typed contracts, containers, and a modern TypeScript frontend.

The stack is selected for speed of implementation, auditability, data and quantitative tooling, and a clean migration path.

Exact dependency versions belong in lock files and are updated through tested releases.

---

## 2. Selected V1 Stack

| Concern | Selection | Architectural Reason |
|---|---|---|
| Backend language | Python | Strong data, quantitative, AI, API, and testing ecosystem |
| API | FastAPI | Typed Python API contracts and generated OpenAPI support |
| Validation and settings | Pydantic | Typed runtime validation and configuration |
| Relational access | SQLAlchemy | Explicit transaction and persistence abstraction |
| Database migrations | Alembic | Version-controlled relational schema migrations |
| System of record | PostgreSQL | Transactions, relational integrity, JSON-capable metadata, text search, indexing |
| Embeddings | pgvector in PostgreSQL | Colocates semantic retrieval with permissions, time, and provenance |
| Raw and large artifacts | S3-compatible object-storage interface | Immutable files and portable storage contract |
| Scheduler | Application scheduler behind an interface | Fast V1 scheduling without adopting a distributed platform early |
| Job execution | PostgreSQL-backed job ledger and workers | Durable, replayable work with low infrastructure overhead |
| Transient cache and locks | Redis, optional | Disposable acceleration and coordination only |
| Frontend | React with TypeScript | Component-oriented typed command-center UI |
| Frontend build | Vite or approved React framework decision | Fast development; final choice remains adapter-like at UI boundary |
| API client | Generated or typed client from OpenAPI | Reduces drift between backend and frontend |
| Testing | Pytest and property-based tests; frontend unit and browser tests | Invariants, deterministic replay, and end-to-end verification |
| Formatting and linting | Automated Python and TypeScript toolchain | Consistent code and CI enforcement |
| Containers | Docker and Docker Compose | Reproducible multi-process local and controlled-host deployment |
| Observability | Structured logs and OpenTelemetry-compatible instrumentation | Correlated traces, metrics, and logs with vendor-neutral export |
| Documentation | Markdown and Mermaid | Version-controlled, reviewable, and renderable design docs |
| Source control | Git | Reviewable history and release traceability |

---

## 3. Technology Rationale

Official technology documentation reviewed for this architecture supports the following design assumptions:

- FastAPI uses standard Python type hints and generates API documentation through OpenAPI.
- PostgreSQL provides relational constraints, JSON and JSONB data types, full-text search, and multiple index types.
- pgvector adds vector-similarity capabilities to PostgreSQL.
- Docker Compose defines and operates multi-container applications through a declarative application model.
- OpenTelemetry provides vendor-neutral instrumentation for traces, metrics, and logs.
- React supports component-based user interfaces, and its official guidance supports modern build tools and frameworks rather than the retired Create React App workflow.

These capabilities support the selected modular-monolith and colocated-governance design.

---

## 4. Why PostgreSQL Plus Object Storage

This combination avoids:

- a separate graph database;
- a separate vector database;
- a separate document database;
- a separate workflow database;
- a separate audit database.

V1 needs strong consistency and traceability more than specialized peak throughput.

Additional stores may be added later when measured need exists.

---

## 5. Why a Modular Monolith

The project has:

- one owner;
- evolving domain contracts;
- a one-week vertical-slice goal;
- limited operational capacity;
- strong cross-domain transaction needs.

A modular monolith lowers operational complexity while preserving extraction boundaries.

---

## 6. Why an API Boundary

Even for one user, an API boundary:

- separates frontend and domain logic;
- creates typed contracts;
- supports future clients;
- enables testing;
- protects database access;
- makes permissions explicit.

---

## 7. Scheduler and Worker Policy

The scheduler creates durable jobs.

Workers process jobs.

The system does not rely on an in-memory timer as authoritative workflow state.

A future workflow platform may replace the implementation behind the job and orchestration interfaces.

---

## 8. Dependency Rules

A new dependency requires:

- clear use case;
- active maintenance review;
- license review;
- security review;
- size and transitive-dependency review;
- comparison with standard library or existing dependency;
- tests;
- lock-file update;
- changelog or ticket.

---

## 9. Version Pinning

Use lock files for reproducible installation.

Policy:

- application dependencies are constrained and locked;
- container base images use controlled tags or digests;
- provider model identifiers are recorded;
- frontend dependencies are locked;
- automatic upgrades do not deploy without tests;
- critical security upgrades receive expedited review.

---

## 10. Provider SDK Isolation

Provider SDKs live only in adapters.

Examples:

- market-data SDK;
- broker SDK;
- model SDK;
- object-storage SDK;
- observability exporter.

Domain logic depends on internal protocols.

---

## 11. Prohibited Stack Shortcuts

- SQLite as the long-term operational system of record;
- direct frontend database access;
- spreadsheets as authoritative portfolio state;
- unversioned notebooks as production strategy;
- secrets in source code;
- model-provider calls scattered through modules;
- broker SDK calls outside execution adapters;
- ORM models shared as public API contracts;
- cache used as durable job state.

SQLite may still be used for isolated tests if behavior differences are understood, but PostgreSQL-backed integration tests are mandatory.

---

## 12. Notebook Policy

Notebooks may be used for exploration.

Promotion requires:

- reusable modules;
- dataset manifest;
- deterministic configuration;
- tests;
- registered output;
- no hidden notebook state.

---

## 13. Technology Review Triggers

Review the stack when:

- workload exceeds current design;
- provider cost or reliability changes materially;
- a security issue requires replacement;
- institutional requirements add a boundary;
- a technology becomes unsupported;
- a simpler supported alternative emerges;
- a repeated operational failure occurs.

---

## 14. Dependency Acceptance Checklist

- use case documented;
- simpler alternative considered;
- license acceptable;
- security posture reviewed;
- dependency locked;
- adapter boundary defined;
- tests added;
- failure behavior documented;
- observability added;
- removal path understood.
