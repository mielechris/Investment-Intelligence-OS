# Observability Implementation

## Structured Logging

Common fields:

```text
timestamp
severity
process
environment
correlation_id
causation_id
actor
job_id
source_id
thesis_id
portfolio_id
error_class
code_version
```

## Metrics

Initial metrics:

### Data

- fetch success;
- parse success;
- source freshness;
- quarantine count.

### Workflow

- ready jobs;
- retries;
- failures;
- workflow duration.

### AI

- model calls;
- tokens;
- cost;
- latency;
- abstention;
- schema failure.

### Decision

- candidates;
- no-trades;
- vetoes.

### Portfolio

- NAV;
- drawdown;
- gross exposure;
- accounting mismatch.

## Health

Aggregate:

```text
database
object store
critical sources
market data
worker
scheduler
model gateway
risk
accounting
backup
```

## Stand-Down

Critical health failures may escalate system health to STAND_DOWN.

## Tracing

Begin with correlation IDs.

Add distributed tracing exporter as runtime complexity warrants.
