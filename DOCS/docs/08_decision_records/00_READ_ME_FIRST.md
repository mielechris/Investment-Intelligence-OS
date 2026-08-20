# Investment Intelligence OS
## Package 08 — Decision Records — v0.1

**Destination:** `docs/08_decision_records/`  
**Governing packages:** 01 Project Charter, 02 Architecture, 03 Specifications, 04 Data Catalog, 05 Agent Cards, 06 Research, 07 Operations  
**Operating mode:** Research, backtesting, scenario analysis, and paper trading only

---

## Purpose

This package preserves **why** IIOS was designed the way it was.

A decision record exists so that six months from now the team does not have to guess:

- what problem existed;
- what options were considered;
- what was selected;
- why it was selected;
- what risks were accepted;
- what controls were required;
- what would cause the decision to be revisited.

Decision Records are append-preserving.

A changed direction MUST supersede an old decision rather than silently rewrite history.

---

## Decision Record Index

| ADR | Decision |
|---|---|
| ADR-001 | Personal-first, institution-ready |
| ADR-002 | Paper before live |
| ADR-003 | Public or properly licensed information only |
| ADR-004 | Policy intelligence is a component, not an oracle |
| ADR-005 | Separate fact, inference, hypothesis, thesis, and decision |
| ADR-006 | Preserve point-in-time timestamp integrity |
| ADR-007 | Benchmark complexity against simple baselines |
| ADR-008 | Deterministic risk veto authority |
| ADR-009 | Preserve dissent |
| ADR-010 | Require complete decision lineage |
| ADR-011 | Use a modular monolith for V1 |
| ADR-012 | Separate API, worker, scheduler, and frontend processes |
| ADR-013 | PostgreSQL as transactional system of record |
| ADR-014 | Immutable object storage for raw and large artifacts |
| ADR-015 | Use pgvector initially |
| ADR-016 | Defer dedicated graph database |
| ADR-017 | Use PostgreSQL-backed durable job ledger |
| ADR-018 | Use transactional outbox and consumer inbox |
| ADR-019 | Assume at-least-once delivery and enforce idempotent effects |
| ADR-020 | Separate retrieval, parsing, normalization, and interpretation |
| ADR-021 | Bounded AI through one model gateway |
| ADR-022 | Paper broker adapter mirrors future broker interface |
| ADR-023 | Versioned HTTP API with OpenAPI |
| ADR-024 | Typed React command center; backend remains authoritative |
| ADR-025 | Opaque canonical IDs and external identity mappings |
| ADR-026 | Require explainability packets for material decisions |
| ADR-027 | Require golden end-to-end trace in release testing |
| ADR-028 | Defer vendor-specific market data, broker, and cloud decisions |

---

## Record Precedence

When implementation conflicts with an accepted ADR:

1. stop;
2. determine whether the ADR is still valid;
3. if direction must change, write a new ADR;
4. mark the old ADR superseded;
5. update affected architecture/specs/tests;
6. then change code.

Do not use an implementation ticket to quietly reverse architecture.

---

## Status Vocabulary

```text
PROPOSED
ACCEPTED
SUPERSEDED
DEPRECATED
REJECTED
RETIRED
DEFERRED
```

---

## Review Rule

Each accepted decision MUST have either:

- a specific review date;
- or a measurable review trigger.
