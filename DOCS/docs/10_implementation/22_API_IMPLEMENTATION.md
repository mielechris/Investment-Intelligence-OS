# API Implementation

## Application

Create FastAPI application under:

```text
backend/src/iios/api/
```

## Routes

Initial groups:

```text
/api/v1/health
/api/v1/system
/api/v1/sources
/api/v1/events
/api/v1/entities
/api/v1/world-state
/api/v1/evidence
/api/v1/hypotheses
/api/v1/theses
/api/v1/agents
/api/v1/committee
/api/v1/risk
/api/v1/portfolios
/api/v1/orders
/api/v1/research
/api/v1/journal
/api/v1/jobs
```

## Rules

Routes call application services.

Routes do not contain domain logic.

## Commands

Long-running command response:

```json
{
  "job_id": "...",
  "status": "QUEUED",
  "correlation_id": "..."
}
```

## Errors

Canonical error:

```json
{
  "error": {
    "code": "RISK_VETOED",
    "message": "The candidate was rejected by risk controls.",
    "correlation_id": "...",
    "retryable": false
  }
}
```

## Authentication

Require owner identity for privileged commands.

## OpenAPI

Generate API contract and use it to generate or validate frontend types.
