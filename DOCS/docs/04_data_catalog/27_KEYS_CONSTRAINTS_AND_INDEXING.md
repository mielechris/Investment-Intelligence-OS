# Keys, Constraints, and Indexing

## Canonical Key Rules

Primary keys use UUIDs.

Provider natural keys receive explicit unique constraints where appropriate.

Examples:

```text
RawRecord(source_id, source_native_id, revision_id, content_hash)
EntityIdentifier(namespace, identifier, valid_from)
InstrumentIdentifier(namespace, identifier, venue_id, valid_from)
InboxReceipt(consumer_id, event_id)
PaperFill(order_id, idempotency_key)
JobRun(job_type, environment, idempotency_key)
```

## Check Constraints

Required concepts include:

- confidence within 0–1;
- `valid_to >= valid_from`;
- filled quantity not greater than submitted quantity;
- expiry after creation;
- amount requires currency;
- order environment must be PAPER in V1;
- required lineage IDs are not null for promoted states.

## Foreign Key Intent

Protect:

- evidence → source/raw record;
- claim links → evidence;
- thesis → hypothesis;
- committee decision → thesis;
- risk decision → committee decision;
- order intent → risk decision;
- fill → order;
- position → portfolio/instrument;
- postmortem → thesis/position;
- job → workflow.

## Initial Index Intent

High-value indexes:

- `market_available_at`;
- `published_at`;
- event type + time;
- entity + validity interval;
- instrument + timestamp;
- active thesis status;
- portfolio + status;
- job status + scheduled time;
- unpublished outbox state;
- audit correlation ID;
- source freshness;
- full-text search;
- vector search with metadata filters.

Indexes are added based on actual query plans and critical workflow requirements.
