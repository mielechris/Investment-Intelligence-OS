# Observability and Alerting

## Logs

Structured fields:

- timestamp;
- severity;
- process;
- environment;
- correlation ID;
- causation ID;
- actor;
- object IDs;
- job ID;
- error class;
- code version.

## Metrics

Track:

### Data

- freshness;
- retrieval success;
- parse failures;
- revisions;
- quarantines.

### Workflow

- queued jobs;
- retries;
- failures;
- workflow duration.

### AI

- calls;
- cost;
- latency;
- abstention;
- schema failure;
- unsupported claims.

### Risk/Portfolio

- NAV;
- drawdown;
- exposure;
- vetoes;
- accounting mismatches.

## Critical Alerts

- live adapter present in V1;
- risk engine unavailable;
- accounting mismatch;
- critical stale data;
- duplicate order/fill;
- prohibited data;
- backup failure;
- kill switch.

## Alert Rule

Alerts must identify:

- severity;
- component;
- correlation ID;
- immediate action;
- owner.
