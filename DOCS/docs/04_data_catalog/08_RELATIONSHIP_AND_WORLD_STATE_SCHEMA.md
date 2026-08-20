# Relationship and World State Schema

---

## `EntityRelationship`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Relationship |
| `subject_entity_id` | UUID | yes | Subject |
| `predicate` | string | yes | Relationship type |
| `object_entity_id` | UUID | yes | Object |
| `evidence_ids` | JSONB | yes | Evidence |
| `confidence` | decimal | yes | Confidence |
| `valid_from` | timestamptz | no | Validity start |
| `valid_to` | timestamptz | no | Validity end |
| `market_available_at` | timestamptz | yes | Point-in-time availability |
| `status` | string | yes | Status |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `WorldStateSnapshot`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Snapshot |
| `cutoff_at` | timestamptz | yes | Information cutoff |
| `generated_at` | timestamptz | yes | Generation |
| `source_version_hash` | string | yes | Included source/version set |
| `stale_domains` | JSONB | no | Stale domains |
| `data_health_summary` | JSONB | yes | Health |
| `snapshot_hash` | string | yes | Immutable hash |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `PolicyState`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Policy state |
| `policy_entity_id` | UUID | yes | Policy/action identity |
| `lifecycle_stage` | enum | yes | Policy stage |
| `legal_authority` | string | no | Authority |
| `implementation_agency_id` | UUID | no | Agency |
| `implementation_probability` | decimal | no | Estimated probability |
| `evidence_ids` | JSONB | yes | Evidence |
| `valid_from` | timestamptz | yes | Validity |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `RegimeAssessment`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Assessment |
| `cutoff_at` | timestamptz | yes | Cutoff |
| `dimension` | string | yes | Growth/inflation/liquidity/etc. |
| `state` | string | yes | Regime state |
| `probability` | decimal | yes | Probability |
| `supporting_indicator_ids` | JSONB | no | Support |
| `contradictory_indicator_ids` | JSONB | no | Contradiction |
| `transition_risk` | decimal | no | Transition risk |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
