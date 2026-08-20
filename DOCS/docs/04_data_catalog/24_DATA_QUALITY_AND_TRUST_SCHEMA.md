# Data Quality and Trust Schema

---

## `SourceTrustAssessment`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `source_id` | UUID | yes | Source |
| `assessed_at` | timestamptz | yes | Assessment time |
| `provenance_confidence` | decimal | yes | Provenance |
| `directness` | decimal | yes | Primary/directness |
| `historical_reliability` | decimal | no | Historical reliability |
| `correction_behavior` | decimal | no | Correction pattern |
| `reporting_delay_score` | decimal | no | Delay |
| `rights_confidence` | decimal | yes | Rights |
| `independence` | decimal | no | Independence |
| `explanation` | JSONB | yes | Explanation |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `DataQualityAssessment`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `object_type` | string | yes | Object type |
| `object_id` | UUID | yes | Object |
| `assessed_at` | timestamptz | yes | Time |
| `freshness` | decimal | yes | Freshness |
| `completeness` | decimal | yes | Completeness |
| `schema_validity` | decimal | yes | Validity |
| `consistency` | decimal | no | Consistency |
| `revision_risk` | decimal | no | Revision risk |
| `extraction_confidence` | decimal | no | Extraction |
| `quality_status` | string | yes | Status |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
