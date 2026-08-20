# Investment Intelligence OS
## Observability, Reliability, and Recovery Architecture — v0.1

---

## 1. Reliability Objective

The system must reveal when it cannot be trusted.

Availability without correctness is not sufficient.

A command center that loads while critical feeds, risk, or accounting are broken is unhealthy.

---

## 2. Observability Signals

IIOS emits:

- structured logs;
- metrics;
- traces;
- health states;
- audit events;
- job history;
- source-health assessments;
- model and cost telemetry.

Correlation IDs connect these signals.

---

## 3. Structured Logs

Common fields:

- timestamp;
- severity;
- service or process;
- environment;
- correlation ID;
- causation ID;
- trace and span IDs where enabled;
- actor;
- job ID;
- source ID;
- thesis ID;
- portfolio ID;
- code version;
- message;
- error class;
- retryability.

Logs must not contain secrets.

---

## 4. Metrics

### Ingestion

- retrieval success;
- latency;
- freshness;
- parse success;
- duplicates;
- revisions;
- quarantine count.

### Workflow

- queued jobs;
- running jobs;
- retry count;
- failure count;
- age of oldest ready job;
- workflow completion time.

### AI

- calls;
- tokens;
- cost;
- latency;
- schema failures;
- unsupported claims;
- abstentions;
- provider failures.

### Decision

- candidates;
- no-trades;
- vetoes;
- missing-information blocks;
- time from event to decision.

### Portfolio

- NAV;
- exposure;
- drawdown;
- concentration;
- accounting mismatch;
- rejected orders;
- slippage.

### Research

- run duration;
- dataset size;
- leakage failures;
- reproducibility failures;
- promoted and retired strategies.

---

## 5. Traces

Trace spans may cover:

```text
HTTP request
→ application command
→ job creation
→ worker claim
→ source retrieval
→ normalization
→ agent calls
→ committee
→ risk
→ paper order
→ journal
```

External provider request IDs are attached when available.

---

## 6. Health Model

Health levels:

- `HEALTHY`
- `DEGRADED`
- `UNHEALTHY`
- `STAND_DOWN`

Health dimensions:

- database;
- object storage;
- critical sources;
- market data;
- worker backlog;
- scheduler;
- model gateway;
- risk engine;
- paper accounting;
- security;
- backup status.

Overall health is not a simple average. A critical unhealthy dimension may force stand-down.

---

## 7. Service-Level Indicators

Initial indicators:

- daily workflow completion;
- source freshness within source-specific threshold;
- job success after retry;
- API query latency;
- decision lineage completeness;
- paper-ledger reconciliation;
- backup success;
- restore verification;
- model structured-output success;
- critical-alert delivery.

Targets are configured and reviewed rather than presented as guarantees.

---

## 8. Alerts

Critical alerts:

- live adapter detected in V1;
- risk engine unavailable;
- accounting mismatch;
- duplicate order or fill;
- stale critical market data;
- missing audit lineage;
- prohibited data incident;
- database failure;
- backup failure beyond threshold;
- kill switch;
- unusual model behavior.

Warnings:

- source degradation;
- elevated retries;
- model cost spike;
- stale noncritical domain;
- slow backtest;
- growing queue.

---

## 9. Failure Modes

The architecture plans for:

- source outage;
- source schema change;
- model outage;
- model behavior change;
- database outage;
- object-store outage;
- cache loss;
- worker crash;
- scheduler duplication;
- partial deployment;
- corrupted migration;
- disk exhaustion;
- clock or timezone error;
- market-data delay;
- broker reconciliation mismatch;
- security incident.

---

## 10. Safe Degradation

Examples:

- model unavailable: continue ingestion, defer analysis;
- noncritical source stale: mark domain degraded, lower confidence;
- critical market data stale: no new risk;
- cache unavailable: slower operation, no state loss;
- frontend unavailable: backend jobs may continue;
- paper broker unavailable: preserve order intent, do not invent fills;
- risk unavailable: reject new order intent.

---

## 11. Backup

Back up:

- PostgreSQL;
- object storage;
- source and rights registry;
- configuration versions;
- model and prompt registry;
- migrations;
- release manifest.

Secrets require separate secure backup or recovery process.

---

## 12. Restore

Restore procedure verifies:

1. database schema;
2. object references;
3. latest audit sequence;
4. paper cash and position reconciliation;
5. job and outbox state;
6. environment mode;
7. risk policy;
8. source registry;
9. model registry;
10. command-center read path.

---

## 13. Recovery Objectives

V1 prioritizes correctness over instant recovery.

Recovery targets are documented per component after actual deployment constraints are known.

No target may justify losing audit or portfolio integrity.

---

## 14. Incident Record

An incident includes:

- start and detection time;
- severity;
- affected components;
- affected data and decisions;
- stand-down state;
- timeline;
- root cause;
- recovery;
- verification;
- corrective actions;
- owner;
- closure date.

---

## 15. Operational Reconciliation

At least daily:

- paper orders versus fills;
- fills versus cash and positions;
- position totals versus snapshot;
- source checkpoints versus raw records;
- outbox versus consumer receipts;
- model calls versus agent runs;
- decisions versus journal entries.

Mismatch is a defect, not a cosmetic warning.

---

## 16. Observability Technology Posture

Use vendor-neutral instrumentation for traces, metrics, and logs where practical.

Exporters may change without changing application semantics.

Local structured logs remain available for a simple V1 deployment.

---

## 17. Reliability Acceptance Tests

- critical source stale produces visible degraded or stand-down state;
- risk outage prevents new orders;
- worker crash is recoverable;
- cache loss loses no authoritative state;
- duplicate scheduler is harmless;
- accounting mismatch triggers critical alert;
- backup restores golden trace;
- model outage preserves job state;
- correlation ID links logs, job, model call, decision, and order;
- failed deployment can roll back without erasing audit.
