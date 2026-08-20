# Causal Chain Schema

---

## `CausalChain`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Chain |
| `title` | string | yes | Title |
| `originating_event_id` | UUID | no | Trigger event |
| `expected_overall_sign` | string | no | Expected sign |
| `expected_overall_lag` | string | no | Expected lag |
| `confidence` | decimal | no | Confidence |
| `source_cutoff_at` | timestamptz | yes | Cutoff |
| `version` | integer | yes | Version |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `CausalStep`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Step |
| `chain_id` | UUID | yes | Parent chain |
| `sequence` | integer | yes | Order |
| `cause_reference` | JSONB | yes | Cause |
| `effect_reference` | JSONB | yes | Effect |
| `mechanism` | text | yes | Economic mechanism |
| `expected_sign` | string | no | Sign |
| `lag_min_seconds` | integer | no | Min lag |
| `lag_max_seconds` | integer | no | Max lag |
| `evidence_ids` | JSONB | no | Evidence |
| `assumption_ids` | JSONB | no | Assumptions |
| `confidence` | decimal | no | Confidence |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `CounterChain`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Counter-chain |
| `parent_chain_id` | UUID | yes | Parent |
| `alternative_mechanism` | text | yes | Alternative mechanism |
| `evidence_ids` | JSONB | no | Evidence |
| `confidence` | decimal | no | Confidence |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `Falsifier`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Falsifier |
| `statement` | text | yes | Condition |
| `evaluation_horizon` | string | no | Horizon |
| `triggered_at` | timestamptz | no | Trigger time |
| `status` | string | yes | Status |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
