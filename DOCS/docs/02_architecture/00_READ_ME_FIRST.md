# Investment Intelligence OS
## Architecture Package — Read Me First — v0.1

**Package:** 02 — Architecture  
**Build date:** August 20, 2026  
**Status:** Approved design baseline for Version 1  
**Operating mode:** Research, backtesting, scenario analysis, and paper trading  
**Primary user:** One founder/operator  
**Architecture posture:** Personal-first, institution-ready  
**Governing documents:** `../01_project_charter/`

---

## Purpose

This folder defines how the Investment Intelligence OS (IIOS) is constructed.

It turns the Project Charter and System Constitution into a technical design that engineers and AI coding agents can implement without inventing foundational decisions during coding.

The architecture is intentionally designed to:

- prove one complete source-to-paper-decision loop quickly;
- preserve point-in-time data and complete decision lineage;
- separate deterministic controls from probabilistic AI reasoning;
- avoid premature microservices;
- support multiple data sources, asset classes, strategies, models, and brokers through adapters;
- fail safely when critical information or services are unreliable;
- grow into an institutional platform without requiring a complete rewrite.

---

## Architecture Decision Summary

V1 uses a **modular monolith** with independently runnable API, worker, scheduler, and frontend processes.

The system of record is **PostgreSQL**. Immutable source payloads and larger artifacts live in an **object store**. Embeddings remain colocated with governed records through **pgvector** unless scale proves a separate vector system is necessary. Internal workflows use a database-backed job ledger and transactional outbox so reliability does not depend on memory-only queues.

AI agents are bounded analysts. They do not own source truth, risk limits, portfolio accounting, or live execution.

The Risk Engine is deterministic and may veto every proposed action.

Autonomous live-money execution is disabled.

---

## Reading Order

| Order | File | Purpose |
|---:|---|---|
| 1 | `01_ARCHITECTURE_OVERVIEW.md` | Executive view of the complete architecture |
| 2 | `02_ARCHITECTURE_PRINCIPLES.md` | Non-negotiable technical design principles |
| 3 | `03_SYSTEM_CONTEXT_AND_BOUNDARIES.md` | Actors, external systems, trust boundaries, and prohibited flows |
| 4 | `04_LOGICAL_COMPONENT_MODEL.md` | Modules, ownership, permitted dependencies, and service boundaries |
| 5 | `05_PROCESS_AND_DEPLOYMENT_MODEL.md` | Runtime processes, environments, containers, and deployment shape |
| 6 | `06_DATA_FLOW_AND_EVENT_LIFECYCLE.md` | How information moves from source to learning |
| 7 | `07_CANONICAL_OBJECT_AND_IDENTITY_MODEL.md` | Core object families, IDs, time semantics, and entity identity |
| 8 | `08_STORAGE_AND_DATABASE_ARCHITECTURE.md` | PostgreSQL, object storage, embeddings, indexing, retention, and backup |
| 9 | `09_CONNECTOR_AND_INGESTION_ARCHITECTURE.md` | Source adapters, raw capture, normalization, revisions, and health |
| 10 | `10_EVENTING_ORCHESTRATION_AND_IDEMPOTENCY.md` | Jobs, schedules, outbox events, retries, and safe replay |
| 11 | `11_WORLD_MODEL_AND_EVIDENCE_GRAPH.md` | Economic state, entities, relationships, evidence, and policy lifecycle |
| 12 | `12_REASONING_HYPOTHESIS_AND_EXPLAINABILITY.md` | Claims, causal chains, counter-cases, hypotheses, theses, and explanations |
| 13 | `13_AGENT_AND_COMMITTEE_ARCHITECTURE.md` | Agent runtime, model gateway, permissions, debate, and committee |
| 14 | `14_PORTFOLIO_RISK_AND_PAPER_EXECUTION.md` | Portfolio state, deterministic risk, paper orders, fills, and accounting |
| 15 | `15_RESEARCH_BACKTESTING_AND_LEARNING.md` | Point-in-time research, event studies, strategy tests, and feedback |
| 16 | `16_API_AND_EXTERNAL_INTEGRATIONS.md` | API conventions and vendor-neutral integration interfaces |
| 17 | `17_FRONTEND_COMMAND_CENTER.md` | Personal command-center information architecture |
| 18 | `18_SECURITY_PRIVACY_AND_SECRETS.md` | Threat model, least privilege, secrets, model security, and incident handling |
| 19 | `19_OBSERVABILITY_RELIABILITY_AND_RECOVERY.md` | Logs, metrics, traces, health, backup, recovery, and stand-down |
| 20 | `20_SCALABILITY_AND_INSTITUTIONAL_EVOLUTION.md` | How V1 grows without premature complexity |
| 21 | `21_TECHNOLOGY_STACK_AND_DEPENDENCY_POLICY.md` | Selected stack, alternatives, and dependency rules |
| 22 | `22_ARCHITECTURE_TEST_STRATEGY.md` | Architecture-level tests and failure demonstrations |
| 23 | `23_ARCHITECTURE_DECISION_INDEX.md` | Initial technical decisions that later receive full ADRs |
| 24 | `24_INITIAL_REPOSITORY_STRUCTURE.md` | Target repository tree and ownership rules |
| 25 | `25_SEVEN_DAY_VERTICAL_SLICE.md` | Exact first implementation sequence |
| 26 | `26_ARCHITECTURE_ACCEPTANCE_CHECKLIST.md` | Completion checklist for this architecture |
| 27 | `27_CONSTITUTION_TRACEABILITY_MATRIX.md` | Maps constitutional controls into components and tests |
| 28 | `28_DEFERRED_DECISIONS_AND_OPEN_QUESTIONS.md` | Decisions intentionally delayed until evidence exists |

---

## Document Precedence

When architecture documents conflict, use this order:

1. `../01_project_charter/02_SYSTEM_CONSTITUTION.md`
2. Approved Architecture Decision Records
3. `../01_project_charter/01_PROJECT_CHARTER.md`
4. `../01_project_charter/03_V1_SCOPE_AND_SUCCESS_GATES.md`
5. This Architecture Package
6. Detailed specifications
7. Tickets
8. Implementation notes

A lower-level document may add detail but may not weaken a higher-level control.

---

## First Build Target

The first implementation must prove this exact lineage:

```text
official public source
→ immutable raw record
→ normalized event
→ resolved entities
→ evidence and claims
→ causal chain and counter-chain
→ policy, macro, and skeptic analyses
→ investment committee
→ deterministic risk review
→ paper order or explicit no-trade
→ portfolio state
→ command center
→ decision journal
→ postmortem and learning
```

The architecture is not accepted merely because individual pieces run. The complete loop must be reconstructable.

---

## Repository Placement

Place this entire folder at:

```text
docs/02_architecture/
```

Do not copy its files into `docs/01_project_charter/`.

---

## Change Rule

A material architecture change requires:

- an Architecture Decision Record;
- an updated Decision Register entry;
- affected diagrams and contracts updated;
- risk analysis;
- migration and rollback analysis;
- test changes;
- Engineering Log entry;
- version change.

Do not silently alter architecture through a coding ticket.
