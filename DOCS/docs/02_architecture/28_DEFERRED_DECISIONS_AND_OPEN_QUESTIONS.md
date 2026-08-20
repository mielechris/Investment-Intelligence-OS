# Investment Intelligence OS
## Deferred Decisions and Open Questions — v0.1

---

## Purpose

Some decisions should not be guessed before requirements and evidence exist.

Deferral is deliberate. It prevents premature lock-in while preserving the question, decision criteria, owner, and trigger.

---

## 1. Market-Data Provider

**Status:** Deferred  
**Needed for:** Reliable prices, historical bars, reference data, and later derivatives  
**Decision criteria:**

- asset-class coverage;
- historical depth;
- point-in-time and corporate-action quality;
- timestamp quality;
- licensing and derived-data rights;
- paper and future live latency;
- cost;
- API reliability;
- rate limits;
- symbol mapping;
- support.

**Trigger:** Before production-quality market reaction and paper fill modeling.

---

## 2. Initial Tradable Asset Set

**Status:** Deferred within multi-asset architecture  
**Options:**

- liquid U.S. equities and ETFs first;
- equities plus crypto;
- futures for commodity expression;
- options after underlying architecture is stable.

**Decision criteria:**

- market data;
- simulator support;
- risk complexity;
- liquidity;
- user priority;
- implementation time.

**Trigger:** Before Day 5 paper execution implementation.

---

## 3. Paper Broker Versus Internal Simulator

**Status:** Proposed hybrid  
**Options:**

- internal deterministic simulator;
- external broker paper account;
- both, reconciled.

**Decision criteria:**

- API availability;
- asset support;
- fill realism;
- reproducibility;
- outage behavior;
- cost;
- future migration.

**Trigger:** Before execution adapter implementation.

---

## 4. Future Live Broker

**Status:** Deferred  
**Reason:** Live authority is out of V1 scope.  
**Trigger:** Formal live-pilot project after forward paper evidence and professional review.

---

## 5. Cloud Host

**Status:** Deferred  
**Initial posture:** Local Docker Compose or one controlled host  
**Decision criteria:**

- reliability;
- security;
- cost;
- managed PostgreSQL;
- object storage;
- backup;
- network egress;
- secrets;
- jurisdiction.

**Trigger:** When the owner needs always-on operation beyond local machine.

---

## 6. Object-Storage Implementation

**Status:** Interface accepted, provider deferred  
**Options:**

- local filesystem adapter for earliest development;
- local S3-compatible service;
- managed object storage.

**Trigger:** Day 1 bootstrap decision.

---

## 7. Scheduler Library

**Status:** Interface accepted, exact library deferred  
**Initial requirement:**

- periodic triggers;
- timezone support;
- job creation only;
- leader or lease behavior;
- testability.

**Trigger:** Day 1 implementation.

---

## 8. Redis

**Status:** Optional  
**Use only for:**

- transient cache;
- short-lived locks;
- rate-limit coordination.

**Do not use for:** Authoritative jobs, decisions, positions, or audit.  
**Trigger:** Measured need.

---

## 9. LLM Providers and Model Routing

**Status:** Deferred behind Model Gateway  
**Decision criteria:**

- structured output;
- reasoning quality;
- evidence discipline;
- tool controls;
- cost;
- latency;
- retention and data terms;
- reliability;
- model identity stability.

**Trigger:** Day 4 agent implementation.

---

## 10. Embedding Provider and Model

**Status:** Deferred  
**Decision criteria:**

- retrieval quality;
- dimensions;
- cost;
- local versus remote;
- source-rights compatibility;
- multilingual need;
- re-embedding cost.

**Trigger:** When semantic retrieval enters the slice.

---

## 11. Authentication Provider

**Status:** Deferred  
**V1 requirement:** One authenticated owner  
**Future requirement:** Roles, revocation, stronger identity, organizations  
**Trigger:** Before remote exposure or additional users.

---

## 12. Dedicated Graph Database

**Status:** Deferred  
**Initial decision:** PostgreSQL graph-like relational model  
**Trigger:**

- measured recursive-query bottleneck;
- graph algorithms become central;
- operational isolation is needed;
- PostgreSQL model becomes materially unmaintainable.

---

## 13. Dedicated Vector Database

**Status:** Deferred  
**Initial decision:** pgvector  
**Trigger:**

- corpus or query volume exceeds measured PostgreSQL capacity;
- filtering and tenancy require isolation;
- latency or cost materially improves elsewhere.

---

## 14. External Event Broker or Workflow Platform

**Status:** Deferred  
**Initial decision:** PostgreSQL job ledger and outbox  
**Trigger:**

- extracted services;
- high fan-out;
- throughput bottleneck;
- durable stream replay requirement;
- independent teams.

---

## 15. Graphical Chart Library

**Status:** Deferred  
**Decision criteria:**

- financial-chart requirements;
- licensing;
- performance;
- annotation support;
- accessibility;
- TypeScript support.

**Trigger:** Day 6 command-center implementation.

---

## 16. News and Research Licensing

**Status:** Deferred beyond official-source-first slice  
**Decision criteria:**

- use rights;
- retention;
- model-use rights;
- redistribution;
- coverage;
- cost;
- duplicate and primary-source quality.

**Trigger:** Before adding paid news or research providers.

---

## 17. Live Legal, Tax, and Compliance Design

**Status:** Deferred and mandatory before live or institutional use  
**Review areas:**

- securities and commodities rules;
- investment-adviser or broker obligations;
- market-data agreements;
- privacy;
- alternative data;
- recordkeeping;
- jurisdiction;
- taxes;
- user disclosures.

**Trigger:** Before live pilot, external users, or customer funds.

---

## 18. Initial Risk Defaults

**Status:** Provisional  
**Current defaults:** Defined in V1 Scope and Success Gates  
**Trigger:** Reevaluate after paper portfolio, asset selection, volatility, and execution model exist.

---

## 19. Initial Golden Scenario

**Status:** Open  
**Requirements:**

- lawful public event;
- clear timestamp;
- identifiable entities;
- plausible causal mechanism;
- market data;
- counter-case;
- no need for private information.

**Trigger:** Before Day 2 fixtures are finalized.

---

## 20. Decision Procedure

For every deferred item:

1. create a research or architecture ticket;
2. define requirements;
3. compare at least two viable options;
4. assess security, rights, cost, and migration;
5. run a small proof where needed;
6. write an ADR;
7. update this document and the Decision Register;
8. add acceptance tests.
