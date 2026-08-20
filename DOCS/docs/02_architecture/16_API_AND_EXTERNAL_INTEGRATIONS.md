# Investment Intelligence OS
## API and External Integration Architecture — v0.1

---

## 1. API Purpose

The API is the governed transport boundary for the command center and future approved clients.

It exposes application capabilities without exposing database internals.

---

## 2. API Style

V1 uses versioned HTTP JSON APIs.

Base path:

```text
/api/v1/
```

Long-running commands return a job or workflow ID.

The API provides an OpenAPI contract generated from typed request and response models.

---

## 3. Resource Groups

Recommended route groups:

```text
/api/v1/health
/api/v1/system
/api/v1/sources
/api/v1/ingestion
/api/v1/events
/api/v1/entities
/api/v1/world-state
/api/v1/evidence
/api/v1/claims
/api/v1/hypotheses
/api/v1/theses
/api/v1/agents
/api/v1/committee
/api/v1/risk
/api/v1/portfolios
/api/v1/orders
/api/v1/research
/api/v1/scenarios
/api/v1/journal
/api/v1/audit
/api/v1/jobs
/api/v1/reports
```

---

## 4. Command Pattern

Example:

```http
POST /api/v1/committee/sessions
```

Response:

```json
{
  "job_id": "uuid",
  "status": "QUEUED",
  "correlation_id": "uuid"
}
```

The command is validated and durably recorded before work begins.

---

## 5. Query Pattern

Queries support:

- stable IDs;
- filters;
- pagination;
- sorting;
- time cutoff;
- version selection;
- include flags for related evidence;
- environment selection where authorized.

Large exports run as jobs and return artifact references.

---

## 6. Error Model

Canonical error response:

```json
{
  "error": {
    "code": "THESIS_LINEAGE_INCOMPLETE",
    "message": "The thesis cannot be promoted because required evidence lineage is missing.",
    "correlation_id": "uuid",
    "details": {},
    "retryable": false
  }
}
```

Do not expose stack traces or secrets.

---

## 7. Idempotency

State-changing endpoints accept an idempotency key.

Examples:

- create hypothesis;
- convene committee;
- run risk;
- create paper order;
- launch backtest;
- generate report.

A repeated request returns the prior result or current status.

---

## 8. Authentication

V1 may use one local authenticated owner account.

The architecture must support later:

- multiple users;
- roles;
- service identities;
- API tokens;
- session revocation;
- stronger authentication;
- tenant scope.

Authentication is not replaced by “the app only runs on my machine.”

---

## 9. Authorization

Authorization checks:

- actor;
- role;
- environment;
- resource ownership;
- requested action;
- current system mode;
- risk and stand-down state.

Backend authorization is mandatory.

---

## 10. Pagination

List endpoints use cursor-based pagination for high-volume or changing records.

Responses include:

- items;
- next cursor;
- count when efficient;
- sort order;
- cutoff time.

---

## 11. Job Status

Long-running operations expose:

- queued;
- running;
- percent or stage where meaningful;
- retrying;
- completed;
- failed;
- cancelled;
- result reference;
- warnings.

Updates may use polling or server-sent events.

---

## 12. External Adapter Interfaces

### Market Data Provider

Capabilities:

- instrument lookup;
- historical bars;
- current quote or delayed quote;
- corporate actions;
- calendars;
- derivatives metadata where supported.

### Model Provider

Capabilities:

- structured completion;
- embeddings;
- token accounting;
- timeout and retry;
- model identity.

### Paper Broker

Capabilities:

- submit;
- cancel;
- query order;
- query fills;
- query positions;
- query account;
- reconcile.

### Object Storage

Capabilities:

- put immutable object;
- get;
- head;
- list by prefix;
- version or content hash;
- delete under policy;
- signed or controlled retrieval.

### Observability Exporter

Capabilities:

- log;
- metric;
- trace;
- health.

---

## 13. Adapter Rules

Adapters must:

- translate provider errors;
- record provider request IDs;
- enforce timeouts;
- enforce rate limits;
- preserve raw provider data where permitted;
- use canonical objects at the domain boundary;
- expose capability flags;
- support fixtures;
- avoid provider SDK types in domain logic.

---

## 14. Webhooks

Inbound webhooks are disabled unless an approved provider requires them.

When enabled:

- verify signature;
- verify timestamp;
- prevent replay;
- store raw payload;
- process asynchronously;
- return quickly;
- audit.

---

## 15. API Security Controls

- request-size limits;
- rate limits;
- strict content types;
- schema validation;
- output encoding;
- correlation IDs;
- secure cookies or token storage;
- CORS allow-list;
- CSRF protection where relevant;
- no secrets in URLs;
- audit for privileged commands.

---

## 16. Compatibility

Breaking API changes require a new version or migration period.

Internal UI and API may evolve together before `1.0`, but versioned contracts and tests remain mandatory.

---

## 17. API Acceptance Tests

- OpenAPI schema is generated;
- invalid input returns stable error;
- duplicate command is idempotent;
- long job returns durable job ID;
- unauthorized action is rejected;
- paper mode rejects live route;
- provider error is normalized;
- API cannot bypass domain invariants;
- pagination is stable;
- stale data is visible in response metadata;
- correlation ID links request to workflow and audit.
