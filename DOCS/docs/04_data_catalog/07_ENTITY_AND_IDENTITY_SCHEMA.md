# Entity and Identity Schema

---

## `Entity`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Canonical identity |
| `entity_type` | string | yes | Person/company/country/etc. |
| `canonical_name` | string | yes | Canonical display name |
| `legal_name` | string | no | Legal name |
| `country_code` | string | no | Country |
| `valid_from` | timestamptz | no | Validity start |
| `valid_to` | timestamptz | no | Validity end |
| `status` | string | yes | Lifecycle |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `EntityAlias`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Alias ID |
| `entity_id` | UUID | yes | Entity |
| `alias` | string | yes | Alias value |
| `alias_type` | string | yes | Ticker/name/acronym/etc. |
| `source_id` | UUID | no | Source |
| `valid_from` | timestamptz | no | Validity |
| `valid_to` | timestamptz | no | Validity |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `EntityIdentifier`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `entity_id` | UUID | yes | Entity |
| `namespace` | string | yes | CIK/LEI/ISIN/provider/etc. |
| `identifier` | string | yes | Identifier value |
| `provider` | string | no | Provider |
| `valid_from` | timestamptz | no | Validity |
| `valid_to` | timestamptz | no | Validity |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `EntityMerge`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Merge record |
| `surviving_entity_id` | UUID | yes | Canonical survivor |
| `merged_entity_id` | UUID | yes | Merged ID |
| `reason` | string | yes | Reason |
| `evidence_ids` | JSONB | yes | Evidence |
| `merged_at` | timestamptz | yes | Time |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
