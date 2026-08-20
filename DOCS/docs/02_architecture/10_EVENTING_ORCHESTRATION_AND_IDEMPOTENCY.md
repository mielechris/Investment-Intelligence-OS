# Investment Intelligence OS
## Eventing, Orchestration, and Idempotency — v0.1

---

## 1. V1 Orchestration Choice

V1 uses:

- a database-backed job ledger;
- scheduler-created jobs;
- worker leases;
- transactional outbox events;
- idempotent handlers;
- bounded retries;
- explicit dead-letter or quarantine state.

A distributed event broker is deferred until throughput or independent-service scale justifies it.

---

## 2. Why Durable Jobs

Long-running work must survive:

- process restart;
- laptop restart;
- container replacement;
- network failure;
- model-provider timeout;
- source outage;
- partial downstream failure.

A job exists durably before a worker begins it.

---

## 3. Job Definition

A job record includes:

- job ID;
- job type;
- schema version;
- payload reference;
- priority;
- status;
- scheduled time;
- attempt count;
- maximum attempts;
- lease owner;
- lease expiration;
- idempotency key;
- correlation ID;
- causation ID;
- environment;
- created and completed times;
- error class;
- result reference.

---

## 4. Job States

```text
SCHEDULED
→ READY
→ LEASED
→ RUNNING
→ SUCCEEDED
```

Failure paths:

```text
RUNNING → RETRY_WAIT → READY
RUNNING → QUARANTINED
RUNNING → FAILED_PERMANENT
RUNNING → CANCELLED
RUNNING → TIMED_OUT
```

A lost worker lease returns eligible work to `READY`.

---

## 5. Workflow Versus Job

A workflow is a durable graph of jobs.

Example daily briefing workflow:

1. source-health check;
2. ingest official sources;
3. ingest market data;
4. normalize;
5. update entities and world state;
6. build event ranking;
7. generate evidence and chains;
8. run specialist agents;
9. run skeptic;
10. convene committee;
11. risk review;
12. paper execution;
13. produce briefing;
14. journal run;
15. publish workflow status.

Each step has independent state.

---

## 6. Internal Event Envelope

Every internal event includes:

```json
{
  "event_id": "uuid",
  "event_type": "CanonicalEventCreated",
  "event_version": "1",
  "occurred_at": "UTC timestamp",
  "recorded_at": "UTC timestamp",
  "producer": "ingestion",
  "environment": "paper",
  "correlation_id": "uuid",
  "causation_id": "uuid",
  "aggregate_type": "canonical_event",
  "aggregate_id": "uuid",
  "payload": {},
  "trace_context": {}
}
```

Large payloads are referenced rather than embedded.

---

## 7. Transactional Outbox

The producing module commits domain state and outbox event in one transaction.

The dispatcher:

1. claims unpublished rows;
2. invokes internal handlers;
3. records delivery;
4. retries failures;
5. marks success.

Future migration to an external broker preserves the event envelope.

---

## 8. Consumer Inbox

Each consumer records:

- consumer ID;
- event ID;
- received time;
- processing status;
- result reference.

A unique constraint on consumer and event prevents duplicate effects.

---

## 9. Idempotency Keys

Examples:

- source retrieval: source plus native ID plus revision;
- daily workflow: workflow type plus market date plus environment;
- agent run: agent version plus thesis version plus context hash;
- risk review: thesis version plus portfolio snapshot plus risk-policy version;
- paper order: risk-decision ID plus order-intent version;
- backtest: strategy version plus dataset manifest plus parameter hash.

---

## 10. Retry Policy

Retry only when failure is plausibly transient.

Retryable:

- timeout;
- connection reset;
- temporary source outage;
- rate limit;
- model-provider temporary error;
- worker crash.

Non-retryable without change:

- invalid schema;
- prohibited source;
- unsupported instrument;
- missing required lineage;
- risk violation;
- malformed configuration;
- permanent authentication denial.

---

## 11. Backoff and Jitter

Retries use:

- exponential delay;
- random jitter;
- provider-specific caps;
- maximum attempts;
- cooldown for repeated source failure.

High-priority risk and accounting jobs may use different policies from research jobs.

---

## 12. Concurrency Controls

Concurrency may be limited by:

- connector;
- source;
- provider;
- model;
- portfolio;
- strategy;
- workflow;
- resource class.

Portfolio-changing paper commands use serialization or optimistic concurrency to prevent conflicting updates.

---

## 13. Scheduling

Schedules include:

- pre-market or morning briefing;
- intraday source polling;
- scheduled macro releases;
- source freshness checks;
- post-close reconciliation;
- nightly backups;
- weekly calibration;
- monthly strategy and risk review.

Calendar logic uses canonical market calendars rather than assuming every weekday is a trading day.

---

## 14. Cancellation

A job may be cancelled by:

- user;
- stand-down;
- superseding workflow;
- timeout;
- risk invalidation;
- deployment.

Cancellation is cooperative where safe.

Completed durable effects are not rolled back by merely marking a job cancelled.

---

## 15. Stand-Down Propagation

A critical stand-down event must:

- stop creation of new order intents;
- cancel queued nonessential decision workflows;
- allow reconciliation and diagnostics;
- preserve ingestion where safe;
- preserve audit and backup;
- require explicit resolution before resuming.

---

## 16. Replay

Replay types:

- deterministic development replay;
- parser repair;
- world-model rebuild;
- research replay;
- incident recovery;
- audit reconstruction.

Operational replay defaults to `execution_disabled=true`.

---

## 17. Orchestration Acceptance Tests

- scheduler duplicate creates one daily workflow;
- worker death releases job after lease expiry;
- outbox event is not lost after commit;
- event redelivery creates one consumer effect;
- permanent data error does not retry forever;
- stand-down stops new paper order intents;
- replay does not create duplicate paper fills;
- job correlation reconstructs the full daily workflow;
- deployment interruption resumes safely.
