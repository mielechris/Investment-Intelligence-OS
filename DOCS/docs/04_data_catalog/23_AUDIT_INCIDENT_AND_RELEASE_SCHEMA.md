# Audit, Incident, Configuration, and Release Schema

---

## `AuditEvent`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Audit event |
| `actor_type` | string | yes | Actor type |
| `actor_id` | string | yes | Actor |
| `action` | string | yes | Action |
| `resource_type` | string | yes | Resource |
| `resource_id` | string | yes | Resource ID |
| `environment` | enum | yes | Environment |
| `occurred_at` | timestamptz | yes | Time |
| `correlation_id` | UUID | no | Correlation |
| `reason` | text | no | Reason |
| `before_reference` | JSONB | no | Before |
| `after_reference` | JSONB | no | After |
| `code_version` | string | yes | Code |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `Incident`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Incident |
| `severity` | string | yes | Severity |
| `category` | string | yes | Category |
| `detected_at` | timestamptz | yes | Detected |
| `affected_components` | JSONB | yes | Components |
| `stand_down_activated` | boolean | yes | Stand-down |
| `root_cause` | text | no | Root cause |
| `corrective_actions` | JSONB | no | Actions |
| `status` | string | yes | Status |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `ReleaseVersion`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `version` | string | yes | Release |
| `release_date` | date | yes | Date |
| `code_commit` | string | yes | Commit |
| `dependency_lock_hash` | string | yes | Dependencies |
| `schema_migration_version` | string | yes | Migration |
| `environment` | enum | yes | Environment |
| `rollback_reference` | string | yes | Rollback |
| `status` | string | yes | Status |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
