# Workflow, Job, and Internal Event Schema

---

## `JobRun`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Job |
| `job_type` | string | yes | Type |
| `workflow_run_id` | UUID | no | Workflow |
| `status` | enum | yes | Status |
| `priority` | integer | yes | Priority |
| `scheduled_at` | timestamptz | yes | Schedule |
| `lease_owner` | string | no | Worker |
| `lease_expires_at` | timestamptz | no | Lease |
| `attempt_count` | integer | yes | Attempts |
| `max_attempts` | integer | yes | Max |
| `idempotency_key` | string | yes | Idempotency |
| `environment` | enum | yes | Environment |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `WorkflowRun`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Workflow |
| `workflow_type` | string | yes | Type |
| `schedule_key` | string | no | Schedule identity |
| `environment` | enum | yes | Environment |
| `status` | string | yes | Status |
| `current_stage` | string | no | Stage |
| `correlation_id` | UUID | yes | Correlation |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `OutboxEvent`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `event_id` | UUID | yes | Event |
| `event_type` | string | yes | Type |
| `event_version` | string | yes | Version |
| `producer` | string | yes | Producer |
| `aggregate_type` | string | yes | Aggregate |
| `aggregate_id` | UUID | yes | Aggregate ID |
| `occurred_at` | timestamptz | yes | Occurrence |
| `correlation_id` | UUID | yes | Correlation |
| `payload` | JSONB | yes | Payload |
| `published_at` | timestamptz | no | Publish |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `InboxReceipt`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `consumer_id` | string | yes | Consumer |
| `event_id` | UUID | yes | Event |
| `received_at` | timestamptz | yes | Received |
| `processing_status` | string | yes | Status |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
