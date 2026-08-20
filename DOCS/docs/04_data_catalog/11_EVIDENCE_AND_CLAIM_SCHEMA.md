# Evidence and Claim Schema

---

## `Evidence`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Evidence identity |
| `source_id` | UUID | yes | Source |
| `raw_record_id` | UUID | yes | Raw source |
| `canonical_event_id` | UUID | no | Related event |
| `source_span` | string | no | Field/span reference |
| `evidence_type` | string | yes | Evidence type |
| `published_at` | timestamptz | no | Publication |
| `market_available_at` | timestamptz | yes | Availability |
| `directness` | decimal | yes | Directness |
| `source_trust_score` | decimal | yes | Trust |
| `data_quality_score` | decimal | yes | Quality |
| `extraction_method` | string | yes | Parser/model/manual |
| `extraction_confidence` | decimal | no | Confidence |
| `rights_classification` | enum | yes | Rights |
| `status` | string | yes | Status |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `Claim`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Claim |
| `claim_type` | enum | yes | FACT/INFERENCE/HYPOTHESIS |
| `statement` | text | yes | Claim text |
| `subject_entity_ids` | JSONB | no | Subjects |
| `object_entity_ids` | JSONB | no | Objects |
| `confidence` | decimal | no | Confidence |
| `status` | string | yes | Status |
| `source_cutoff_at` | timestamptz | yes | Cutoff |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `ClaimEvidenceLink`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `claim_id` | UUID | yes | Claim |
| `evidence_id` | UUID | yes | Evidence |
| `link_type` | enum | yes | Supports/contradicts/etc. |
| `strength` | decimal | no | Strength |
| `explanation` | text | no | Why linked |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
