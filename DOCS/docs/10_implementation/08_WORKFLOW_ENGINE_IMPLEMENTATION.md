# Workflow Engine Implementation

## V0.1 Strategy

Use PostgreSQL-backed durable jobs.

Do not begin with a distributed broker unless required by measured load.

## Core Tables

Implement:

- `workflow.job_definition`;
- `workflow.job_run`;
- `workflow.workflow_run`;
- `workflow.outbox_event`;
- `workflow.inbox_receipt`.

## Worker Algorithm

Conceptual loop:

```python
while running:
    job = claim_ready_job(worker_id, lease_seconds=...)
    if not job:
        sleep()
        continue

    try:
        result = handler(job)
        mark_succeeded(job, result)
    except RetryableError as exc:
        schedule_retry(job, exc)
    except PermanentError as exc:
        mark_failed(job, exc)
```

## Lease

Claim atomically.

A crashed worker leaves the job reclaimable after lease expiration.

## Outbox

When domain state changes:

```text
BEGIN
write domain state
write outbox event
COMMIT
```

Dispatcher sends after commit.

## Inbox

Consumer records:

```text
consumer_id + event_id
```

before or atomically with durable effect.

## Scheduler

Scheduler creates durable jobs.

It does not perform the work itself.

## Replay

Replay flag defaults to:

```text
execution_disabled = true
```

## Tests

- duplicate schedule;
- worker crash;
- retry;
- permanent failure;
- duplicate event;
- replay without duplicate paper fill.
