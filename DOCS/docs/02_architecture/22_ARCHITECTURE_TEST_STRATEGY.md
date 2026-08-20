# Investment Intelligence OS
## Architecture Test Strategy — v0.1

---

## 1. Test Doctrine

IIOS must prove not only that the happy path works, but that the system refuses unsafe work.

The most valuable tests often demonstrate:

- no future data leaks backward;
- no missing evidence becomes a trade;
- no duplicate event becomes a duplicate order;
- no stale critical feed creates new risk;
- no AI output bypasses deterministic controls.

---

## 2. Test Layers

### Unit Tests

Test:

- domain invariants;
- state transitions;
- scoring functions;
- risk rules;
- accounting;
- parsers;
- timestamp conversions;
- ID and deduplication rules.

### Property-Based Tests

Test broad invariants such as:

- cash and positions reconcile after arbitrary valid fills;
- duplicate event processing is idempotent;
- no position exceeds configured limits;
- timestamps never move backward in a lifecycle;
- invalid order transitions are rejected.

### Contract Tests

Test:

- connectors;
- market-data adapters;
- model gateway;
- object storage;
- paper broker;
- API contracts;
- event schemas.

### Integration Tests

Use real PostgreSQL and object storage to test:

- transactions;
- migrations;
- outbox;
- worker leases;
- source-to-event pipeline;
- paper accounting;
- backup and restore.

### End-to-End Tests

Test through the frontend or API:

- golden vertical slice;
- no-trade path;
- risk-veto path;
- stand-down path;
- source outage path.

---

## 3. Golden Trace

Maintain one deterministic reference scenario:

```text
official source fixture
→ raw record
→ event
→ entities
→ evidence
→ causal and counter-chain
→ agent outputs
→ committee candidate
→ risk decision
→ paper order and fill
→ portfolio state
→ journal
→ postmortem
```

Every release verifies the complete trace.

---

## 4. Point-in-Time Tests

Required cases:

- revised macro data is unavailable before revision;
- filing is unavailable before publication;
- event discovered later does not enter earlier research;
- symbol and constituent history are correct;
- market calendar and timezone are correct;
- policy stage reflects evidence available at the time.

---

## 5. Leakage Tests

Automated leakage tests include:

- feature timestamp less than or equal to decision cutoff;
- label columns unavailable to feature builder;
- source revision time after cutoff excluded;
- random timestamp shift test;
- intentional future-data fixture causes failure;
- holdout access is logged and restricted.

---

## 6. Ingestion Tests

- source fixture retrieval;
- raw immutability;
- content hash;
- duplicate handling;
- revision handling;
- malformed payload;
- timeout;
- rate limit;
- parser version replay;
- quarantine;
- source-health degradation.

---

## 7. Evidence and Reasoning Tests

- unsupported claim rejected;
- contradictory evidence linked;
- fact versus inference classification preserved;
- missing counter-chain blocks high-confidence promotion;
- missing invalidation blocks thesis;
- source retraction triggers review;
- explainability packet includes lineage.

---

## 8. Agent Tests

- structured output validation;
- missing citation;
- hallucinated evidence ID;
- prompt injection;
- unapproved tool;
- model timeout;
- fallback model;
- abstention;
- cost limit;
- debate round limit;
- agent disagreement.

Use fixed fixtures and recorded model responses where possible.

---

## 9. Risk Tests

Invariants:

- risk veto always blocks order;
- position cap enforced;
- theme cap enforced;
- gross and net limits enforced;
- stale critical data blocks new risk;
- drawdown threshold activates state;
- duplicate approval cannot duplicate order;
- expired approval rejected;
- kill switch blocks activity.

---

## 10. Paper Accounting Tests

- buy fill;
- sell fill;
- partial fill;
- cancel;
- fee;
- split or corporate action where supported;
- futures multiplier;
- option multiplier;
- realized and unrealized P&L;
- reconciliation from event ledger;
- duplicate fill rejection.

---

## 11. Research Tests

- benchmark included;
- gross and net results;
- deterministic seed;
- walk-forward windows;
- no overlap errors;
- parameter perturbation;
- event deduplication;
- cost sensitivity;
- failed run preserved;
- reproducibility manifest.

---

## 12. API and UI Tests

- authentication;
- authorization;
- idempotency;
- stable errors;
- pagination;
- stale metadata;
- paper-mode label;
- no live action;
- decision detail lineage;
- error, empty, stale, and stand-down UI states.

---

## 13. Security Tests

- secret scanning;
- dependency scanning;
- role permissions;
- prompt injection;
- unsafe file handling;
- forged webhook;
- replayed webhook;
- cross-environment credential check;
- model payload redaction;
- audit integrity.

---

## 14. Reliability Tests

- worker crash;
- scheduler duplication;
- database restart;
- cache loss;
- object-store outage;
- source outage;
- model outage;
- partial deployment;
- backup restore;
- clock skew simulation;
- disk or quota warning.

---

## 15. Performance Tests

Initial performance tests focus on:

- daily workflow duration;
- query latency for command center;
- source-ingestion throughput;
- worker backlog;
- vector and text retrieval under filters;
- backtest memory use;
- model call concurrency;
- portfolio reconciliation time.

Performance tests must not weaken correctness filters.

---

## 16. Test Data

Use:

- synthetic records;
- official-source fixtures;
- recorded and rights-approved responses;
- small point-in-time market datasets;
- deliberately malformed data;
- adversarial documents;
- known leakage traps;
- known accounting scenarios.

Do not use unapproved confidential data in tests.

---

## 17. Continuous Integration Gates

A merge requires:

- formatting;
- linting;
- type checks;
- unit tests;
- integration tests for affected modules;
- migration checks;
- secret scan;
- schema compatibility check;
- architecture dependency check;
- documentation link check.

Release adds:

- golden trace;
- backup/restore smoke test;
- paper-mode assertion;
- risk and accounting suite.

---

## 18. Test Evidence

Each test run records:

- code commit;
- dependency lock;
- environment;
- test data version;
- results;
- duration;
- failures;
- artifacts.

---

## 19. Architecture Acceptance

The architecture is testable when every critical design claim has at least one verifying test and one relevant failure-path test.
