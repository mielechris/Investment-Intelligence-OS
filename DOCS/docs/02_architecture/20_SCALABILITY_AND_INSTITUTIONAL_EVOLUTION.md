# Investment Intelligence OS
## Scalability and Institutional Evolution — v0.1

---

## 1. Evolution Doctrine

IIOS is built for one operator first.

Institutional readiness means preserving:

- modular boundaries;
- provenance;
- audit;
- permissions;
- versioning;
- environment separation;
- adapter interfaces;
- deterministic risk.

It does not mean deploying institutional complexity on Day 1.

---

## 2. Evolution Stages

### Stage 0 — Vertical Slice

- one host;
- one database;
- one worker;
- three source domains;
- three agents;
- one paper portfolio;
- simple frontend.

### Stage 1 — Personal Production

- scheduled daily workflow;
- broader sources;
- more agents;
- reliable backups;
- source and model monitoring;
- multiple paper strategies;
- hardened local or hosted deployment.

### Stage 2 — Multi-Portfolio Research

- several paper portfolios;
- separate strategy workers;
- more market-data volume;
- read replicas or analytical exports;
- stronger auth;
- role separation.

### Stage 3 — Small Private Team

- multiple users;
- role-based access;
- approval workflows;
- tenant or workspace concept;
- centralized secrets;
- controlled environments;
- stronger incident response.

### Stage 4 — Institutional Product

- legal and compliance program;
- licensed data enforcement;
- tenant isolation;
- live broker controls;
- change approvals;
- model risk governance;
- disaster recovery;
- service-level commitments;
- independent risk and compliance oversight.

---

## 3. Scale Vertically Before Splitting

First improve:

- indexes;
- query plans;
- caching;
- batching;
- worker concurrency;
- read models;
- object-storage use;
- partitioning for measured high-volume tables.

Do not extract a service to solve an unmeasured problem.

---

## 4. Service Extraction Criteria

A module may become a service when at least one is true:

- independent scaling materially lowers cost or latency;
- distinct security boundary is required;
- separate deployment cadence is required;
- failure isolation is valuable;
- separate team owns it;
- different data locality is required;
- database contention is measured;
- external institutional contract requires separation.

Extraction requires an ADR and migration plan.

---

## 5. Likely Future Services

Potential extractions:

- market-data service;
- ingestion service;
- model gateway;
- research compute service;
- notification service;
- execution service;
- audit service;
- identity and access service.

Risk and execution separation receives special review before live deployment.

---

## 6. Event Broker Evolution

V1 uses database outbox and job ledger.

An external broker may be introduced when:

- event volume exceeds database dispatcher capacity;
- independent services require asynchronous decoupling;
- fan-out becomes substantial;
- replay retention requires a log;
- separate consumer teams exist.

The canonical event envelope remains stable.

---

## 7. Data Evolution

### V1

- PostgreSQL operational store;
- object storage;
- pgvector;
- read models.

### Later

Possible additions:

- analytical warehouse or lakehouse;
- time-series optimized store;
- dedicated graph system;
- separate vector system;
- stream processor.

Each addition must have a measurable query, volume, isolation, or cost requirement.

---

## 8. Multi-Tenancy

Future tenant-aware objects include:

- user;
- organization;
- workspace;
- portfolio;
- source license;
- model permission;
- broker account;
- audit scope.

Tenant ID must become a first-class authorization boundary before external users are added.

Do not add a nullable tenant field everywhere without a complete isolation design.

---

## 9. Institutional Approval Workflows

Future workflows may require:

- researcher proposes;
- reviewer validates;
- risk approves;
- compliance approves;
- operator executes;
- independent audit observes.

The V1 decision and audit model must preserve enough structure to add these stages.

---

## 10. Data Licensing at Scale

Institutional evolution requires:

- source entitlements;
- user-level access;
- retention enforcement;
- derived-data rights;
- export restrictions;
- model-provider use restrictions;
- deletion workflows;
- vendor audit.

Source-rights metadata is therefore included in V1 architecture.

---

## 11. Live Trading Evolution

A live environment requires:

- separate infrastructure;
- separate credentials;
- separate permissions;
- broker reconciliation;
- pre-trade risk;
- post-trade controls;
- operational support;
- legal and compliance review;
- limited initial notional;
- rollback and kill switch;
- independent approval.

Paper and live may share interfaces, not hidden state.

---

## 12. Performance Scaling

Potential techniques:

- asynchronous ingestion;
- batch normalization;
- precomputed read models;
- partitioned high-volume market data;
- parallel research workers;
- model-response caching where allowed;
- embedding batching;
- source-specific concurrency;
- read replicas;
- query result caching.

Correctness and rights filters remain before speed.

---

## 13. Cost Scaling

Track cost by:

- source;
- model;
- agent;
- workflow;
- strategy;
- user or future tenant;
- storage class;
- research run.

Use less expensive models or deterministic methods for tasks that do not require advanced reasoning.

---

## 14. Evolution Acceptance

The architecture is institution-ready when:

- module boundaries can be extracted;
- every action has identity;
- source rights are modeled;
- environment mode is enforced;
- audit is complete;
- models and prompts are versioned;
- risk is independent;
- paper and live interfaces are separated;
- data can be scoped to a future tenant;
- migrations and releases are controlled.

It is not institution-ready merely because it uses containers or a cloud provider.
