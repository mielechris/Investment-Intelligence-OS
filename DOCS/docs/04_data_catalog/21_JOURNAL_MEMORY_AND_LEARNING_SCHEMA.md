# Journal, Memory, and Learning Schema

---

## `JournalEntry`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Entry |
| `entry_type` | string | yes | Entry type |
| `related_object_type` | string | yes | Object type |
| `related_object_id` | UUID | yes | Object |
| `source_cutoff_at` | timestamptz | no | Cutoff |
| `world_state_snapshot_id` | UUID | no | World state |
| `summary` | text | yes | Summary |
| `evidence_ids` | JSONB | no | Evidence |
| `created_at` | timestamptz | yes | Time |
| `correlation_id` | UUID | no | Correlation |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `Postmortem`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Postmortem |
| `thesis_id` | UUID | yes | Thesis |
| `position_id` | UUID | no | Position |
| `expected_path` | text | yes | Expected |
| `actual_path` | text | yes | Actual |
| `process_quality_score` | decimal | no | Process |
| `outcome_score` | decimal | no | Outcome |
| `lessons` | JSONB | yes | Lessons |
| `completed_at` | timestamptz | yes | Completion |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `BeliefUpdate`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Update |
| `belief_id` | UUID | yes | Belief |
| `prior_confidence` | decimal | no | Prior |
| `new_confidence` | decimal | no | New |
| `reason` | text | yes | Reason |
| `evidence_result_ids` | JSONB | yes | Evidence/results |
| `created_at` | timestamptz | yes | Time |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
